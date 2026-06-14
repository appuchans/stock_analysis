"""Flow-based crew implementation using CrewAI 1.x Flow API."""

import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from crewai import Crew, Process, Task
from crewai.flow.flow import Flow, listen, router, start, or_
from pydantic import BaseModel, Field

from ..agents import (
    CompetitorAnalystAgent,
    DataCollectorAgent,
    EconomicAnalystAgent,
    FundamentalAnalystAgent,
    IndustryAnalystAgent,
    InvestmentAdvisorAgent,
    MarketAnalystAgent,
    ReportGeneratorAgent,
    RiskAnalystAgent,
    SentimentAnalystAgent,
    TechnicalAnalystAgent,
)
from ..config.loader import config_loader
from ..config.settings import settings
from ..models.stock_data import InvestmentRecommendation
from .event_listener import event_listener  # noqa: F401 — registers event handlers on import

_logger = logging.getLogger(__name__)


def _report_path(symbol: str, filename: str) -> str:
    """Build an output path inside the configured reports directory."""
    return str(Path(settings.report_output_dir) / symbol / filename)


def _strip_md_fences(text: str) -> str:
    """Remove a wrapping markdown code fence the LLM may have added."""
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


def _write_report_file(symbol: str, filename: str, content: str) -> None:
    """Write a stage output file into the configured reports directory.

    Files are written directly (not via Task.output_file) because CrewAI strips
    the leading slash from absolute non-template output_file paths, which would
    silently redirect output to a cwd-relative location.
    """
    try:
        path = Path(_report_path(symbol, filename))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except Exception as exc:
        _logger.warning("Could not write %s: %s", filename, exc)


# ── Typed flow state ──────────────────────────────────────────────────────────

class StockAnalysisState(BaseModel):
    """Shared state carried through the analysis flow."""
    symbol: str = ""
    analysis_depth: str = "standard"  # "quick" | "standard" | "deep"
    asset_type: str = "stock"         # "stock" | "etf"
    # None = resolved by BaseAgent from llm_config.yaml + env vars
    llm_provider: Optional[str] = None
    model: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)
    technical: Dict[str, Any] = Field(default_factory=dict)
    fundamental: Dict[str, Any] = Field(default_factory=dict)
    ownership: Dict[str, Any] = Field(default_factory=dict)
    risk: Dict[str, Any] = Field(default_factory=dict)
    sentiment: Dict[str, Any] = Field(default_factory=dict)
    market: Dict[str, Any] = Field(default_factory=dict)
    industry: Dict[str, Any] = Field(default_factory=dict)
    competitor: Dict[str, Any] = Field(default_factory=dict)
    economic: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Dict[str, Any] = Field(default_factory=dict)
    report: str = ""
    errors: List[str] = Field(default_factory=list)


def _step_callback(step_output: Any) -> None:
    _logger.info("[flow-step] %s", str(step_output)[:200])


def _run_crew(agents_list: list, tasks_list: list, inputs: dict) -> Any:
    """Helper: build and kick off a mini crew, returning the raw result."""
    c = Crew(
        agents=agents_list,
        tasks=tasks_list,
        process=Process.sequential,
        verbose=False,
        memory=False,
        output_log_file=settings.crew_log_file,
    )
    result = c.kickoff(inputs=inputs)
    # Accumulate this crew's token usage into the per-run total (otherwise
    # discarded — the flow builds a fresh crew per stage).
    try:
        from ..token_meter import add as _add_tokens
        _add_tokens(getattr(c, "usage_metrics", None))
    except Exception:
        pass
    return result


# CrewAI appends the full Pydantic schema prompt to the task output when
# output_pydantic is set.  Strip it so it doesn't pollute stored results.
_SCHEMA_LEAK_RE = re.compile(
    r"\n*This is the expected criteria for your final answer:.*",
    re.DOTALL,
)


def _narrative_guardrail(output: Any) -> Tuple[bool, Any]:
    """Task guardrail: the answer must be the thesis-led narrative document.

    Catches two failure modes: a status summary about the work instead of the
    document, and a sectioned summary without the opening Investment Thesis.
    """
    text = _strip_md_fences(str(getattr(output, "raw", output)))
    headings = [l.strip() for l in text.splitlines() if l.strip().startswith("## ")]
    if len(headings) >= 3 and "thesis" in headings[0].lower():
        return (True, text)
    return (
        False,
        "Your answer must be ONLY the research narrative document itself in "
        "markdown, beginning with '## Investment Thesis' and containing all "
        "required '## ' sections — not a summary of what you did.",
    )


def _result_str(result: Any) -> str:
    """Serialize a crew result to a clean string.

    Prefers JSON when the task had output_pydantic so that downstream
    consumers get structured data rather than Python Decimal/datetime reprs.
    Also strips the CrewAI schema-leak suffix that appears in raw output.
    """
    if hasattr(result, "pydantic") and result.pydantic is not None:
        return result.pydantic.model_dump_json()
    if hasattr(result, "json_dict") and result.json_dict:
        return json.dumps(result.json_dict)
    raw = str(result)
    return _SCHEMA_LEAK_RE.sub("", raw).strip()


# ── Main analysis flow ────────────────────────────────────────────────────────

class StockAnalysisFlow(Flow[StockAnalysisState]):
    """
    Event-driven flow for comprehensive stock analysis.

    Stages:
      collect_data  →  (router)  →  quick / standard / deep  →  synthesize  →  report
    """

    def __init__(
        self,
        llm_provider: Optional[str] = None,
        model: Optional[str] = None,
        asset_type: str = "auto",
        use_data_cache: bool = True,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self._llm_provider = llm_provider  # None = read from config
        self._model = model
        self._raw_asset_type = asset_type
        self._use_data_cache = use_data_cache  # False = force a fresh data pull

    # ── helpers ───────────────────────────────────────────────────────────────

    def _make_agent(self, cls: type) -> Any:
        return cls(self._llm_provider, self._model).get_agent()

    def _inputs(self) -> dict:
        base = {"symbol": self.state.symbol, "asset_type": self.state.asset_type}
        raw = self.state.data.get("raw", "")
        if raw:
            # Strip markdown code fences the data-collection agent may have added
            raw = re.sub(r"^```(?:json)?\s*\n?", "", raw.strip())
            raw = re.sub(r"\n?```\s*$", "", raw)
            # Truncate at a clean newline boundary so we never cut mid-value
            limit = 8000
            if len(raw) > limit:
                cut = raw.rfind("\n", 0, limit)
                raw = raw[: cut if cut > 0 else limit]
            base["collected_data"] = raw.strip()
        else:
            base["collected_data"] = "No pre-collected data available."

        # Pre-computed technical indicators — guaranteed to reach the technical analyst
        # even when the data-collector LLM didn't forward them.
        tech = self.state.data.get("technical_summary", {})
        if tech:
            base["technical_data"] = json.dumps(tech, indent=2)
        else:
            base["technical_data"] = "No pre-computed technical indicators available."

        # Structured data side-channels — fetched deterministically in collect_data
        # so real numbers reach the analysts verbatim, not via LLM paraphrase.
        structured = self.state.data.get("structured", {})

        def _blob(key: str, cap: int = 5000) -> str:
            v = structured.get(key)
            if not v:
                return "Not available — note this in your Data Sources & Gaps section."
            s = json.dumps(v, separators=(",", ":"), default=str)
            return s[:cap]

        base["analyst_data"] = _blob("analyst")
        base["financials_data"] = _blob("financials")
        base["ownership_data"] = _blob("ownership")
        base["sentiment_data"] = _blob("sentiment", 6000)

        return base

    @property
    def _prompts(self) -> Dict[str, Any]:
        """Stage prompt configuration (config/flow_tasks.yaml)."""
        return config_loader.load_flow_tasks_config()

    def _with_data(self, description: str) -> str:
        """Append collected-data context and rigor rules to a task description."""
        shared = self._prompts["shared"]
        return (
            description.strip()
            + "\n\n" + shared["with_data_suffix"].strip()
            + "\n\n" + shared["rigor_footer"].strip()
        )

    def _resolve_asset_type(self, symbol: str) -> str:
        if self._raw_asset_type != "auto":
            return self._raw_asset_type
        from ..tools.free_data_collection import _detect_asset_type
        return _detect_asset_type(symbol)

    @property
    def _is_etf(self) -> bool:
        return self.state.asset_type == "etf"

    def _stage_filename(self, key: str) -> str:
        """Output filename for a stage, using the ETF-specific slugs the
        report generator looks for when the asset is an ETF."""
        etf_map = {
            "fundamental": "etf_fundamental_analysis",
            "industry": "etf_holdings_analysis",
            "competitor": "etf_peer_analysis",
        }
        slug = etf_map.get(key, f"{key}_analysis") if self._is_etf else f"{key}_analysis"
        return f"{self.state.symbol}_{slug}.md"

    # ── stage 1: data collection ──────────────────────────────────────────────

    @start()
    def collect_data(self) -> None:
        """Collect raw stock data from all free sources."""
        agent = self._make_agent(DataCollectorAgent)
        cd = self._prompts["collect_data"]
        t = Task(
            description=cd["description"],
            expected_output=cd["expected_output"],
            agent=agent,
        )
        result = _run_crew([agent], [t], self._inputs())
        raw = _result_str(result)
        self.state.data = {"raw": raw}
        _write_report_file(
            self.state.symbol, f"{self.state.symbol}_data.json", _strip_md_fences(raw)
        )

        # Deterministic structured fetch — bypasses LLM summarisation so real
        # numbers (indicators, analyst consensus, statements, ownership,
        # sentiment) always reach the specialist analysts verbatim.
        try:
            self._fetch_structured()
        except Exception as _exc:
            _logger.warning("Structured data fetch failed: %s", _exc)

    def _fetch_structured(self) -> None:
        """Reuse a recent structured fetch for this symbol, else fetch fresh.

        The full data bundle (structured blocks, technical summary, chart data)
        is cached cross-process keyed by symbol for `data_cache_ttl` (24h by
        default), so a repeat analysis of the same ticker that day skips all
        network collection. Set DATA_CACHE_TTL=0 to always re-fetch.
        """
        from ..tools.cache import get_cached, set_cached

        sym = self.state.symbol
        caching_enabled = settings.data_cache_ttl > 0
        bundle: Optional[Dict[str, Any]] = None
        if caching_enabled and self._use_data_cache:
            bundle = get_cached("structured", sym)
        if bundle is not None:
            _logger.info(
                "[collect_data] reusing cached structured data for %s "
                "(within %ds TTL) — no network fetch", sym, settings.data_cache_ttl
            )
        else:
            bundle = self._fetch_structured_uncached()
            # Always refresh the store after a fresh pull (even with --no-cache),
            # so the next normal run can reuse it.
            if bundle and caching_enabled:
                set_cached("structured", sym, bundle, settings.data_cache_ttl)
        if bundle:
            self._apply_structured_bundle(bundle)

    def _apply_structured_bundle(self, bundle: Dict[str, Any]) -> None:
        """Restore state from a (fresh or cached) bundle and write chart data."""
        sym = self.state.symbol
        structured = bundle.get("structured") or {}
        self.state.data["structured"] = structured
        if bundle.get("technical_summary") is not None:
            self.state.data["technical_summary"] = bundle["technical_summary"]
        _logger.info("[collect_data] structured blocks for %s: %s", sym, list(structured.keys()))

        chart = bundle.get("chart")
        if chart:
            chart = dict(chart)
            # Recomputed at apply time so the trend stays fresh and is appended
            # at most once per day even when the rest of the bundle was cached.
            chart["sentiment_history"] = self._update_sentiment_history(
                chart.get("sentiment_snapshot") or {}
            )
            _write_report_file(sym, f"{sym}_chart_data.json", json.dumps(chart, indent=2))

    def _fetch_structured_uncached(self) -> Dict[str, Any]:
        """Fetch all structured data with one shared Ticker + parallel summarizers.

        One cached YahooFinanceTool call covers snapshot/technical/news; the
        remaining summaries share a single yf.Ticker to minimize API calls.
        Returns a bundle {structured, technical_summary, chart} for caching.
        """
        import yfinance as yf

        from ..tools import yf_summaries as ys
        from ..tools.free_data_collection import YahooFinanceTool
        from ..tools.social_sentiment import SocialSentimentTool

        sym = self.state.symbol
        structured: Dict[str, Any] = {}
        technical_summary: Optional[Dict[str, Any]] = None

        yf_result: Dict[str, Any] = {}
        try:
            yf_result = YahooFinanceTool()._run(sym)  # Redis-cached
        except Exception as exc:
            _logger.warning("YahooFinanceTool failed in structured fetch: %s", exc)
        if yf_result and "error" not in yf_result:
            technical_summary = yf_result.get("technical_summary", {})
            structured["snapshot"] = {
                "market_data": yf_result.get("market_data", {}),
                "fundamentals": yf_result.get("fundamental_data", {}),
                "quarterly_income": yf_result.get("quarterly_income", {}),
                "earnings_history": yf_result.get("earnings_history", []),
            }
            if yf_result.get("etf_profile"):
                structured["etf_profile"] = yf_result["etf_profile"]

        ticker = yf.Ticker(sym)
        jobs: Dict[str, Any] = {
            "analyst": lambda: ys.summarize_analyst_data(ticker),
            "financials": lambda: {
                **ys.summarize_financial_statements(ticker),
                **ys.summarize_dividends_splits(ticker),
            },
            "ownership": lambda: ys.summarize_ownership(ticker),
            "options": lambda: ys.summarize_options_sentiment(ticker),
            "social": lambda: SocialSentimentTool()._run(sym),
        }
        jobs["catalysts"] = lambda: ys.summarize_catalysts(ticker)
        jobs["search_interest"] = lambda: ys.summarize_search_interest(sym)
        if self._is_etf:
            jobs["etf_portfolio"] = lambda: ys.summarize_etf_portfolio(ticker)
        else:
            jobs["peers"] = lambda: ys.summarize_peers(sym)

        fetched: Dict[str, Any] = {}
        with ThreadPoolExecutor(max_workers=min(len(jobs), settings.max_workers)) as ex:
            futures = {ex.submit(fn): name for name, fn in jobs.items()}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    fetched[name] = fut.result()
                except Exception as exc:
                    _logger.warning("Structured fetch '%s' failed: %s", name, exc)

        for key in ("analyst", "financials", "ownership", "etf_portfolio"):
            if fetched.get(key):
                structured[key] = fetched[key]

        headlines = [
            n.get("title", "") for n in (yf_result.get("recent_news") or [])[:10]
        ]
        structured["sentiment"] = {
            "social": fetched.get("social") or {"note": "social sources unavailable"},
            "options_positioning": fetched.get("options") or {"available": False},
            "short_interest": (yf_result or {}).get("short_interest") or {},
            "search_interest": fetched.get("search_interest") or {},
            "recent_news_headlines": headlines,
        }
        if fetched.get("catalysts"):
            structured["catalysts"] = fetched["catalysts"]
        if fetched.get("peers"):
            structured["peers"] = fetched["peers"]

        bundle: Dict[str, Any] = {"structured": structured, "technical_summary": technical_summary}

        # Chart data for the HTML report (1y weekly closes + quarterly revenue)
        try:
            hist = ticker.history(period="1y", interval="1wk")
            chart: Dict[str, Any] = {}
            ci = (yf_result or {}).get("company_info") or {}
            chart["company"] = {
                "name": ci.get("name"),
                "website": ci.get("website"),
                "sector": ci.get("sector"),
                "industry": ci.get("industry"),
                "exchange": ci.get("exchange"),
            }
            if hist is not None and not hist.empty:
                chart["price_history"] = [
                    {"date": idx.date().isoformat(), "close": round(float(row["Close"]), 2)}
                    for idx, row in hist.iterrows()
                    if row["Close"] == row["Close"]
                ]
            q = structured.get("snapshot", {}).get("quarterly_income", {})
            chart["quarterly_revenue_m"] = {
                label: round(vals["total_revenue"] / 1e6, 1)
                for label, vals in sorted(q.items())
                if isinstance(vals, dict) and vals.get("total_revenue")
            }
            etf_p = structured.get("etf_portfolio") or {}
            if etf_p.get("sector_weightings_pct"):
                chart["sector_weightings_pct"] = etf_p["sector_weightings_pct"]

            def _f(v: Any) -> Optional[float]:
                try:
                    x = float(v)
                    return None if x != x else x
                except (TypeError, ValueError):
                    return None

            md = (yf_result or {}).get("market_data") or {}
            fd = (yf_result or {}).get("fundamental_data") or {}
            chart["key_stats"] = {
                "current_price": _f(md.get("current_price")),
                "market_cap": _f(md.get("market_cap")),
                "pe_ratio": _f(fd.get("pe_ratio")),
                "high_52w": _f(md.get("high_52w")),
                "low_52w": _f(md.get("low_52w")),
                "beta": _f(md.get("beta")),
            }
            an = structured.get("analyst") or {}
            chart["analyst"] = {
                "price_targets": an.get("price_targets") or {},
                "rating_counts": (an.get("recommendation_trend") or [{}])[0],
            }
            sent = structured.get("sentiment") or {}
            st = (sent.get("social") or {}).get("stocktwits") or {}
            opt = sent.get("options_positioning") or {}
            mood = (sent.get("social") or {}).get("market_mood") or {}
            si = sent.get("short_interest") or {}
            search = sent.get("search_interest") or {}
            chart["sentiment_snapshot"] = {
                "stocktwits_bullish_pct": st.get("bullish_ratio_pct"),
                "stocktwits_labeled": (st.get("bullish") or 0) + (st.get("bearish") or 0),
                "watchers": st.get("watchers"),
                "put_call_oi_ratio": opt.get("put_call_oi_ratio"),
                "short_pct_of_float": si.get("short_pct_of_float"),
                "fear_greed_score": mood.get("fear_greed_score"),
                "fear_greed_rating": mood.get("rating"),
                "search_momentum_pct": search.get("momentum_pct"),
            }
            if structured.get("catalysts"):
                chart["catalysts"] = structured["catalysts"]
            peer_rows = (structured.get("peers") or {}).get("rows") or []
            if peer_rows:
                chart["peers"] = peer_rows
            # Valuation scenarios from street EPS estimates (assumptions disclosed)
            eps_est = (an.get("eps_estimates") or {})
            eps_base = (eps_est.get("0y") or {}).get("avg")
            growth = (eps_est.get("+1y") or {}).get("growth_pct")
            if eps_base:
                scen = ys.dcf_scenarios(eps_base, growth if growth is not None else 8.0)
                if scen:
                    chart["valuation_scenarios"] = scen
            # sentiment_history is appended at apply time (kept fresh on cache
            # hits), so it is intentionally not stored in the cached chart here.
            bundle["chart"] = chart
        except Exception as exc:
            _logger.warning("Chart data generation failed: %s", exc)

        return bundle

    def _update_sentiment_history(self, snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Append today's sentiment snapshot to the per-symbol history file.

        Enables trend statements like 'retail bullishness up from 62% to 82%
        over two weeks' across runs. One entry per day, capped at 120 days.
        """
        import datetime as _dt

        path = (
            Path(settings.data_output_dir)
            / f"{self.state.symbol.upper()}_sentiment_history.json"
        )
        history: List[Dict[str, Any]] = []
        try:
            if path.exists():
                history = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            history = []
        today = _dt.date.today().isoformat()
        entry = {
            "date": today,
            "stocktwits_bullish_pct": snapshot.get("stocktwits_bullish_pct"),
            "put_call_oi_ratio": snapshot.get("put_call_oi_ratio"),
            "short_pct_of_float": snapshot.get("short_pct_of_float"),
            "fear_greed_score": snapshot.get("fear_greed_score"),
        }
        history = [h for h in history if h.get("date") != today] + [entry]
        history = history[-120:]
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(history, indent=1), encoding="utf-8")
        except Exception as exc:
            _logger.warning("Could not persist sentiment history: %s", exc)
        return history

    # ── stage runner ───────────────────────────────────────────────────────────

    def _run_stages(self, stages: List[Tuple[type, str, str]]) -> None:
        """Run independent analysis stages concurrently.

        Each stage is its own mini-crew (own agent + task), so they parallelize
        cleanly; results land in state and on disk as they complete.
        """
        inputs = self._inputs()
        sym = self.state.symbol

        stage_expected = self._prompts["shared"]["stage_expected_output"]

        def _one(spec: Tuple[type, str, str]) -> Tuple[str, str]:
            cls, key, desc = spec
            ag = self._make_agent(cls)
            t = Task(
                description=self._with_data(desc),
                expected_output=stage_expected,
                agent=ag,
                markdown=True,
            )
            stage_inputs = dict(inputs, analysis_key=key)
            return key, _result_str(_run_crew([ag], [t], stage_inputs))

        max_workers = max(1, min(len(stages), settings.max_workers))
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_one, s): s[1] for s in stages}
            for fut in as_completed(futures):
                key = futures[fut]
                try:
                    k, text = fut.result()
                    setattr(self.state, k, {"result": text})
                    _write_report_file(sym, self._stage_filename(k), text)
                    print(f"  ✓ {k.replace('_', ' ').title()} analysis", flush=True)
                except Exception as exc:
                    _logger.error("Stage '%s' failed: %s", key, exc)
                    self.state.errors.append(f"{key}: {exc}")

    # ── stage 2: route by depth ────────────────────────────────────────────────

    @router(collect_data)
    def route_by_depth(self) -> str:
        """Route to quick, standard, or deep analysis based on analysis_depth."""
        return self.state.analysis_depth  # returns "quick" | "standard" | "deep"

    # ── stage descriptions (shared between depths) ────────────────────────────

    def _desc_technical(self, brief: bool = False, backtest: bool = False) -> str:
        t = self._prompts["technical"]
        desc = (t["brief"] if brief else t["comprehensive"]) + " " + t["indicators_source"]
        if backtest:
            desc += " " + t["backtest_addendum"]
        return desc

    def _desc_for(self, key: str) -> str:
        """Stage description from flow_tasks.yaml, honouring stock/ETF variants."""
        spec = self._prompts[key]
        if isinstance(spec, dict) and ("stock" in spec or "etf" in spec):
            return spec["etf" if self._is_etf else "stock"]
        return spec["description"] if isinstance(spec, dict) else str(spec)

    def _stages_for(self, depth: str) -> List[Tuple[type, str, str]]:
        sym = self.state.symbol
        stages: List[Tuple[type, str, str]] = []
        # Investor-first report: technical analysis only runs in deep mode and is
        # framed as a timing footnote; the standard path covers ownership instead.
        if depth == "deep" and not self._is_etf:
            stages.append((
                TechnicalAnalystAgent, "technical",
                self._desc_technical(brief=False, backtest=True),
            ))
        stages.append((FundamentalAnalystAgent, "fundamental", self._desc_for("fundamental")))
        if depth in ("standard", "deep"):
            if not self._is_etf:
                stages.append((FundamentalAnalystAgent, "ownership", self._desc_for("ownership")))
            stages += [
                (RiskAnalystAgent, "risk", self._desc_for("risk")),
                (SentimentAnalystAgent, "sentiment", self._desc_for("sentiment")),
            ]
        if depth == "deep":
            stages += [
                (MarketAnalystAgent, "market", self._desc_for("market")),
                (IndustryAnalystAgent, "industry", self._desc_for("industry")),
                (CompetitorAnalystAgent, "competitor", self._desc_for("competitor")),
                (EconomicAnalystAgent, "economic", self._desc_for("economic")),
            ]
        return stages

    # ── stage 3: analysis paths (stages run concurrently) ─────────────────────

    @listen("quick")
    def quick_analysis(self) -> None:
        """Fast path: fundamental (and technical for stocks)."""
        self._run_stages(self._stages_for("quick"))

    @listen("standard")
    def standard_analysis(self) -> None:
        """Standard path: technical, fundamental, risk, and sentiment."""
        self._run_stages(self._stages_for("standard"))

    @listen("deep")
    def deep_analysis(self) -> None:
        """Deep path: all specialist analysts."""
        self._run_stages(self._stages_for("deep"))

    # ── stage 4: synthesize recommendation ────────────────────────────────────

    @listen(or_(quick_analysis, standard_analysis, deep_analysis))
    def synthesize_recommendation(self) -> None:
        """Generate investment recommendation from all completed analyses."""
        context_summary = "\n".join(
            f"{k}: {v.get('result', '')[:1500]}"
            for k, v in {
                "technical": self.state.technical,
                "fundamental": self.state.fundamental,
                "ownership": self.state.ownership,
                "risk": self.state.risk,
                "sentiment": self.state.sentiment,
                "market": self.state.market,
                "industry": self.state.industry,
                "competitor": self.state.competitor,
                "economic": self.state.economic,
            }.items()
            if v
        )

        agent = self._make_agent(InvestmentAdvisorAgent)
        rec = self._prompts["recommendation"]
        t = Task(
            description=rec["description"],
            expected_output=rec["expected_output"],
            agent=agent,
            output_pydantic=InvestmentRecommendation,
        )
        inputs = dict(self._inputs(), analyses_summary=context_summary)
        result = _run_crew([agent], [t], inputs)
        rec_text = _result_str(result)
        self.state.recommendation = {"result": rec_text}
        # _result_str returns clean JSON when output_pydantic parsed successfully
        _write_report_file(
            self.state.symbol,
            f"{self.state.symbol}_investment_recommendation.json",
            _strip_md_fences(rec_text),
        )

    # ── stage 5: generate report ───────────────────────────────────────────────

    @listen(synthesize_recommendation)
    def generate_report(self) -> None:
        """Write the synthesized research narrative, then render the HTML report.

        The agent's job is the one thing an LLM is needed for: a single
        coherently-voiced narrative that becomes the body of the HTML report.
        Rendering itself is deterministic templating done in code afterwards —
        no tool calls, no loop risk.
        """
        sym = self.state.symbol
        agent = self._make_agent(ReportGeneratorAgent)
        all_analyses = {
            "technical": self.state.technical,
            "fundamental": self.state.fundamental,
            "ownership": self.state.ownership,
            "risk": self.state.risk,
            "sentiment": self.state.sentiment,
            "market": self.state.market,
            "industry": self.state.industry,
            "competitor": self.state.competitor,
            "economic": self.state.economic,
            "recommendation": self.state.recommendation,
        }
        summary = "\n".join(
            f"### {k}\n{v.get('result', 'N/A')[:3000]}"
            for k, v in all_analyses.items() if v
        )

        rep = self._prompts["report"]
        t = Task(
            description=rep["description"],
            expected_output=rep["expected_output"],
            agent=agent,
            # Native output validation: CrewAI re-prompts the agent with the
            # guardrail feedback when the answer isn't the narrative document
            guardrail=_narrative_guardrail,
            guardrail_max_retries=1,
            markdown=True,
        )
        report_inputs = dict(self._inputs(), analyses_summary=summary)
        result = _run_crew([agent], [t], report_inputs)
        narrative = _strip_md_fences(_result_str(result))

        if narrative.count("## ") >= 3:
            self.state.report = narrative
            _write_report_file(sym, f"{sym}_comprehensive_report.md", narrative)
        else:
            _logger.warning(
                "Narrative still malformed; HTML will fall back to the executive summary"
            )
            self.state.report = narrative

        # Rendering is deterministic — always done in code, never by the LLM.
        from ..tools.report_tools import render_html_report
        try:
            rendered = render_html_report(sym, asset_type=self.state.asset_type)
            if rendered.get("report_path"):
                self.state.report = rendered["report_path"]
        except Exception as exc:
            _logger.warning("HTML render failed for %s: %s", sym, exc)

    # ── public API ─────────────────────────────────────────────────────────────

    def analyze_stock(self, symbol: str, analysis_depth: str = "standard", **kwargs: Any) -> Dict[str, Any]:
        """Run the full flow for a single stock or ETF."""
        try:
            from ..llm_budget import reset as _reset_llm_budget
            from ..llm_budget import used as _llm_calls_used
            from .. import token_meter
            _reset_llm_budget()
            token_meter.reset()
            resolved_type = self._resolve_asset_type(symbol)
            result = self.kickoff(inputs={
                "symbol": symbol,
                "analysis_depth": analysis_depth,
                "asset_type": resolved_type,
                "llm_provider": self._llm_provider,
                "model": self._model,
                **kwargs,
            })
            token_meter.check_alert()
            return {
                "symbol": symbol,
                "analysis_depth": analysis_depth,
                "report": self.state.report,
                "recommendation": self.state.recommendation,
                "status": "completed",
                "token_usage": token_meter.snapshot(),
                "llm_calls": _llm_calls_used(),
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            _logger.error("Flow analysis failed for %s: %s", symbol, e)
            return {
                "symbol": symbol,
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
            }

