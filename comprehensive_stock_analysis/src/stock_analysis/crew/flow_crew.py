"""Flow-based crew implementation using CrewAI 1.x Flow API."""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

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
from ..config.settings import settings
from ..models.stock_data import InvestmentRecommendation, RiskMetrics, TechnicalIndicators

_logger = logging.getLogger(__name__)


# ── Typed flow state ──────────────────────────────────────────────────────────

class StockAnalysisState(BaseModel):
    """Shared state carried through the analysis flow."""
    symbol: str = ""
    analysis_depth: str = "standard"  # "quick" | "standard" | "deep"
    llm_provider: str = "openai"
    model: str = "gpt-4o"
    data: Dict[str, Any] = Field(default_factory=dict)
    technical: Dict[str, Any] = Field(default_factory=dict)
    fundamental: Dict[str, Any] = Field(default_factory=dict)
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
        verbose=True,
        memory=True,
        step_callback=_step_callback,
    )
    return c.kickoff(inputs=inputs)


# ── Main analysis flow ────────────────────────────────────────────────────────

class StockAnalysisFlow(Flow[StockAnalysisState]):
    """
    Event-driven flow for comprehensive stock analysis.

    Stages:
      collect_data  →  (router)  →  quick / standard / deep  →  synthesize  →  report
    """

    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4o", **kwargs: Any):
        super().__init__(**kwargs)
        self._llm_provider = llm_provider
        self._model = model

    # ── helpers ───────────────────────────────────────────────────────────────

    def _make_agent(self, cls: type) -> Any:
        return cls(self._llm_provider, self._model).get_agent()

    def _inputs(self) -> dict:
        return {"symbol": self.state.symbol}

    # ── stage 1: data collection ──────────────────────────────────────────────

    @start()
    def collect_data(self) -> None:
        """Collect raw stock data from all free sources."""
        agent = self._make_agent(DataCollectorAgent)
        t = Task(
            description=f"Collect comprehensive market data, fundamentals, SEC filings, "
                        f"economic indicators, and news for {self.state.symbol}.",
            expected_output="Structured data package with price history, fundamentals, "
                            "news, and economic data.",
            agent=agent,
            create_directory=True,
            output_file=f"reports/{self.state.symbol}_data.json",
        )
        result = _run_crew([agent], [t], self._inputs())
        self.state.data = {"raw": str(result)}

    # ── stage 2: route by depth ────────────────────────────────────────────────

    @router(collect_data)
    def route_by_depth(self) -> str:
        """Route to quick, standard, or deep analysis based on analysis_depth."""
        return self.state.analysis_depth  # returns "quick" | "standard" | "deep"

    # ── stage 3a: quick path (technical + fundamental only) ───────────────────

    @listen("quick")
    def quick_analysis(self) -> None:
        """Run only technical and fundamental analysis (fast path)."""
        ta_agent = self._make_agent(TechnicalAnalystAgent)
        fa_agent = self._make_agent(FundamentalAnalystAgent)
        inputs = self._inputs()

        ta_task = Task(
            description=f"Perform technical analysis for {self.state.symbol}: "
                        "compute RSI, MACD, moving averages, identify trend and signals.",
            expected_output="Technical indicators and trading signal.",
            agent=ta_agent,
            output_pydantic=TechnicalIndicators,
            create_directory=True,
            output_file=f"reports/{self.state.symbol}_technical.json",
        )
        fa_task = Task(
            description=f"Perform fundamental analysis for {self.state.symbol}: "
                        "valuation ratios, profitability, financial health.",
            expected_output="Fundamental metrics and investment quality score.",
            agent=fa_agent,
            create_directory=True,
            output_file=f"reports/{self.state.symbol}_fundamental.json",
        )

        tech_result = _run_crew([ta_agent], [ta_task], inputs)
        fund_result = _run_crew([fa_agent], [fa_task], inputs)

        self.state.technical = {"result": str(tech_result)}
        self.state.fundamental = {"result": str(fund_result)}

    # ── stage 3b: standard path (+ risk + sentiment) ──────────────────────────

    @listen("standard")
    def standard_analysis(self) -> None:
        """Run technical, fundamental, risk, and sentiment analysis."""
        agents_tasks = [
            (TechnicalAnalystAgent, f"Technical analysis for {self.state.symbol}.", TechnicalIndicators),
            (FundamentalAnalystAgent, f"Fundamental analysis for {self.state.symbol}.", None),
            (RiskAnalystAgent, f"Risk analysis for {self.state.symbol}: beta, VaR, drawdown.", RiskMetrics),
            (SentimentAnalystAgent, f"Sentiment analysis for {self.state.symbol}.", None),
        ]
        state_keys = ["technical", "fundamental", "risk", "sentiment"]
        inputs = self._inputs()

        for (cls, desc, pydantic_model), key in zip(agents_tasks, state_keys):
            ag = self._make_agent(cls)
            task_kwargs: dict = dict(
                description=desc,
                expected_output=f"Analysis output for {key}.",
                agent=ag,
                create_directory=True,
                output_file=f"reports/{self.state.symbol}_{key}.json",
            )
            if pydantic_model:
                task_kwargs["output_pydantic"] = pydantic_model
            t = Task(**task_kwargs)
            result = _run_crew([ag], [t], inputs)
            setattr(self.state, key, {"result": str(result)})

    # ── stage 3c: deep path (all analysts) ────────────────────────────────────

    @listen("deep")
    def deep_analysis(self) -> None:
        """Run all specialist analyses in sequence."""
        pipeline = [
            (TechnicalAnalystAgent, "technical", TechnicalIndicators),
            (FundamentalAnalystAgent, "fundamental", None),
            (RiskAnalystAgent, "risk", RiskMetrics),
            (SentimentAnalystAgent, "sentiment", None),
            (MarketAnalystAgent, "market", None),
            (IndustryAnalystAgent, "industry", None),
            (CompetitorAnalystAgent, "competitor", None),
            (EconomicAnalystAgent, "economic", None),
        ]
        inputs = self._inputs()

        for cls, key, pydantic_model in pipeline:
            ag = self._make_agent(cls)
            task_kwargs: dict = dict(
                description=f"Comprehensive {key} analysis for {self.state.symbol}.",
                expected_output=f"Detailed {key} analysis.",
                agent=ag,
                create_directory=True,
                output_file=f"reports/{self.state.symbol}_{key}.json",
            )
            if pydantic_model:
                task_kwargs["output_pydantic"] = pydantic_model
            t = Task(**task_kwargs)
            result = _run_crew([ag], [t], inputs)
            setattr(self.state, key, {"result": str(result)})

    # ── stage 4: synthesize recommendation ────────────────────────────────────

    @listen(or_(quick_analysis, standard_analysis, deep_analysis))
    def synthesize_recommendation(self) -> None:
        """Generate investment recommendation from all completed analyses."""
        context_summary = "\n".join(
            f"{k}: {v.get('result', '')[:300]}"
            for k, v in {
                "technical": self.state.technical,
                "fundamental": self.state.fundamental,
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
        t = Task(
            description=f"Based on the following analyses, produce an investment recommendation "
                        f"for {self.state.symbol}:\n{context_summary}",
            expected_output="Investment recommendation: type, target price, stop-loss, "
                            "time horizon, confidence, reasoning, risks, opportunities.",
            agent=agent,
            output_pydantic=InvestmentRecommendation,
            create_directory=True,
            output_file=f"reports/{self.state.symbol}_recommendation.json",
        )
        result = _run_crew([agent], [t], self._inputs())
        self.state.recommendation = {"result": str(result)}

    # ── stage 5: generate report ───────────────────────────────────────────────

    @listen(synthesize_recommendation)
    def generate_report(self) -> None:
        """Produce the final comprehensive investment report."""
        agent = self._make_agent(ReportGeneratorAgent)
        all_analyses = {
            "data": self.state.data,
            "technical": self.state.technical,
            "fundamental": self.state.fundamental,
            "risk": self.state.risk,
            "sentiment": self.state.sentiment,
            "market": self.state.market,
            "industry": self.state.industry,
            "competitor": self.state.competitor,
            "economic": self.state.economic,
            "recommendation": self.state.recommendation,
        }
        summary = "\n".join(
            f"### {k}\n{v.get('result', 'N/A')[:500]}"
            for k, v in all_analyses.items() if v
        )

        t = Task(
            description=f"Write a professional investment report for {self.state.symbol}. "
                        f"Use these analyses:\n{summary}",
            expected_output="Complete investment report with executive summary, "
                            "analysis sections, recommendation, and risk disclaimer.",
            agent=agent,
            create_directory=True,
            output_file=f"reports/{self.state.symbol}_report.md",
        )
        result = _run_crew([agent], [t], self._inputs())
        self.state.report = str(result)

    # ── public API ─────────────────────────────────────────────────────────────

    def analyze_stock(self, symbol: str, analysis_depth: str = "standard", **kwargs: Any) -> Dict[str, Any]:
        """Run the full flow for a single stock."""
        try:
            result = self.kickoff(inputs={
                "symbol": symbol,
                "analysis_depth": analysis_depth,
                "llm_provider": self._llm_provider,
                "model": self._model,
                **kwargs,
            })
            return {
                "symbol": symbol,
                "analysis_depth": analysis_depth,
                "report": self.state.report,
                "recommendation": self.state.recommendation,
                "status": "completed",
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


# ── Convenience subclasses ────────────────────────────────────────────────────

class QuickAnalysisFlowCrew(StockAnalysisFlow):
    """Quick (technical + fundamental only) analysis flow."""

    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4o"):
        super().__init__(llm_provider=llm_provider, model=model)

    def analyze_stock(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[override]
        return super().analyze_stock(symbol, analysis_depth="quick", **kwargs)


class StockAnalysisFlowCrew(StockAnalysisFlow):
    """Standard analysis flow (technical, fundamental, risk, sentiment)."""

    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4o"):
        super().__init__(llm_provider=llm_provider, model=model)

    def analyze_stock(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[override]
        return super().analyze_stock(symbol, analysis_depth="standard", **kwargs)


class DeepDiveAnalysisFlowCrew(StockAnalysisFlow):
    """Deep-dive analysis flow (all eight specialist agents)."""

    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4o"):
        super().__init__(llm_provider=llm_provider, model=model)

    def analyze_stock(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[override]
        return super().analyze_stock(symbol, analysis_depth="deep", **kwargs)
