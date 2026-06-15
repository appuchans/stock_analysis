# Comprehensive Stock Analysis Solution

A multi-agent stock and ETF analysis system built on **CrewAI 1.x** with event-driven
Flow orchestration, Pydantic v2 typed outputs, Redis caching, and **free-only data sources**
(no paid data API keys required — only an LLM key).

---

## Features

### Multi-Agent Architecture (CrewAI 1.x)
- **11 specialised agents** — Data Collector, Technical Analyst, Fundamental Analyst, Risk Analyst,
  Sentiment Analyst, Market Analyst, Industry Analyst, Competitor Analyst, Economic Analyst,
  Investment Advisor, Report Generator
- **Native `crewai.LLM`** — no LangChain wrapper; supports OpenAI, Anthropic, and Ollama models
- **Hard execution timeouts** on every agent (`max_execution_time`, default 300s) and
  CrewAI-native tool-result caching (`cache=True`) so hung calls and tool loops self-terminate
- **Hard LLM-call budget** (`MAX_LLM_CALLS_PER_RUN`, default 300) enforced inside the LLM
  wrapper itself — once exhausted, no request can physically reach the provider, capping
  the worst-case cost of any runaway loop
- **Parallel execution** — independent analysis stages run concurrently in the Flow pipeline;
  data sources are fetched in parallel via `ThreadPoolExecutor`

### Deterministic data pipeline
Real numbers reach the analysts verbatim — structured data is fetched in code (not via LLM
paraphrase) and passed into every analysis prompt as separate inputs:
- Pre-computed technical indicators (SMA 20/50/90, RSI-14, MACD, Bollinger Bands, ATR, volume)
- Analyst consensus: price targets with implied upside, buy/hold/sell trend, upgrades/downgrades
  by firm, EPS/revenue estimates and 30-day revisions
- 3-year financial statements: revenue/margins YoY, cash flow, capex, FCF, buybacks, debt
- Ownership: insider transactions with buy/sell summary, top institutional holders
- Sentiment: Stocktwits bullish/bearish ratios, Reddit activity, options put/call positioning,
  news headlines

### Analysis Capabilities
| Domain | What is produced |
|---|---|
| Technical | SMA/EMA, RSI, MACD, Bollinger Bands, ATR, Stochastic, ADX, OBV, MFI (pure pandas — see `tools/_indicators.py`) plus backtest-validated signals |
| Fundamental | P/E, P/B, P/S, PEG, EV/EBITDA, ROE/ROA, 3-year statement trends, DCF with disclosed assumptions |
| Risk | Beta (live vs S&P 500), Sharpe, Sortino, VaR 95%, max drawdown, CVaR — all annualised |
| Sentiment | Stocktwits bullish/bearish ratio, Reddit activity, analyst rating trend and revisions, options put/call, news tone |
| Backtesting | SMA crossover and RSI-reversion simulation (`BacktestTool`, wired to the Technical Analyst) |
| Portfolio | Correlation vs SPY, min-variance weights, portfolio Sharpe/VaR (`PortfolioAnalysisTool`, wired to the Investment Advisor) |
| ETFs | Expense/AUM/returns profile, sector weightings, asset classes, top holdings, peer comparison |
| Reports | Professional HTML report with inline SVG price/revenue/sector charts, company logo, recommendation card, and all specialist sections |

### Data Sources (free, keyless — every source has a fallback)
- **Yahoo Finance** — prices, fundamentals, statements, analyst consensus, estimates,
  insider/institutional ownership, short interest, options chains, ETF fund data
- **SEC EDGAR** — 10-K/10-Q MD&A and Risk Factors extraction
- **FRED** — Federal Reserve economic indicators (`demo` key works); falls back to
  market-traded macro proxies via yfinance (VIX, 10Y yield, S&P 500, WTI, dollar index)
- **Stocktwits** — retail sentiment with explicit bullish/bearish labels
- **Reddit** — post volume in r/stocks, r/wallstreetbets, r/investing; JSON API with
  automatic RSS-feed fallback when the API is blocked
- **CNN Fear & Greed index** — market-wide sentiment context
- **News** — Google News RSS, falling back to Bing News RSS, then Yahoo per-symbol feed
- **DuckDuckGo** — web search for industry/competitor context and qualitative gap-filling

When a source is unavailable, agents are instructed to cover that angle qualitatively
(web search or general knowledge, explicitly qualified) — reports never contain raw
error messages or HTTP status codes.

### Output rigor
Every specialist report must cite each number with its period and source, disclose
methodology (VaR confidence/horizon, beta window, DCF assumptions), and end with a
**Data Sources & Gaps** section. Agents are instructed to note missing data instead of
refusing or inventing numbers.

### Caching (minimizes API calls, reuses data across runs)
Three tiers (`tools/cache.py`), tried by locality: **Redis** (shared, authoritative when
reachable) → **in-process memory** → **filesystem** (`data/.tool_cache/`, survives between
CLI invocations). `@cached_tool()` decorates individual tools with per-source TTLs
(news/social 30 min, options 1 h, analyst/ownership 12 h, statements/SEC 24 h) and never
caches errors.

The whole structured data fetch is also cached as one bundle keyed by symbol for
`DATA_CACHE_TTL` (default **24 h**), so **re-analyzing the same ticker within a day skips all
network collection** — even without Redis, thanks to the disk tier. Use `--no-cache` to force
a fresh pull (which still refreshes the store for later runs), or set `DATA_CACHE_TTL=0` to
disable. A one-time sweep keeps the disk cache bounded.

### Reliability & observability
- **Fail-fast credential preflight** — a misconfigured run (wrong provider / missing key)
  stops in ~1 s with a clear message, before any data is fetched.
- **Shared HTTP session** with connection pooling and retry/backoff (429 + 5xx) across all
  free-data calls, so a momentary blip becomes a success instead of a Data Gap.
- **Per-run token + LLM-call accounting** printed at the end of each run; set
  `LLM_TOKEN_ALERT` to log a WARNING when a run's token total exceeds a threshold.

---

## Quick Start

```bash
cd comprehensive_stock_analysis
pip install -r requirements.txt        # or: pip install -e ".[dev]"
```

Set at minimum one LLM key in `.env`:
```
OPENAI_API_KEY=sk-...        # or ANTHROPIC_API_KEY
FRED_API_KEY=demo            # optional; "demo" gives rate-limited access
```

Run:
```bash
# Single stock — standard depth (stages run in parallel)
python -m stock_analysis.main AAPL

# Depth control: quick (fundamental) / standard (+ownership/risk/sentiment) / deep (all)
python -m stock_analysis.main AAPL --depth quick
python -m stock_analysis.main AAPL --depth deep

# Force a fresh data pull (ignore the ≤24h cached bundle; still refreshes it)
python -m stock_analysis.main AAPL --no-cache

# Multiple stocks
python -m stock_analysis.main AAPL MSFT GOOGL

# ETFs are auto-detected (or force with --asset-type etf)
python -m stock_analysis.main VOO

# Override LLM at runtime
python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-sonnet-4-6
```

Reports land in `reports/<SYMBOL>/` (markdown per specialist + `html/` for the final report),
regardless of the directory you run from.

---

## Web UI (local)

A professional local web interface — run analyses, watch **live progress**, and browse past
reports. FastAPI backend + a no-build frontend (vanilla JS + Chart.js). Modern analytics-dashboard
design: left-sidebar app shell, **light/dark theme toggle** (persisted; respects
`prefers-color-scheme`), bundled **Inter** font with tabular figures, and themed charts.

```bash
python -m stock_analysis.web              # → http://127.0.0.1:8000
python -m stock_analysis.web --port 9000  # custom port
```

- **New Analysis** — enter a ticker, pick depth/asset/cache, run; a **stage stepper** + progress bar
  show the current stage with live token + LLM-call chips, and a **Cancel** button aborts the run.
  On completion it opens the report.
- **Report** — tabbed: an interactive **Overview** dashboard from `chart_data.json` (price, revenue,
  analyst ratings, valuation scenarios, sentiment, peers — or ETF fund facts + sector weightings for
  funds) plus the **Full Report** (the self-contained HTML, embedded). A **Refresh** button re-runs
  the analysis with fresh data.
- **History** — a gallery of every past analysis with recommendation/status badges, price
  sparklines, key stats, and a per-card **Refresh**. Aborted/failed runs are shown with their status;
  cards are ordered by true analysis time (newest first).

Design notes: single-user, localhost-only, **one analysis at a time** (runs are serialized because
`token_meter`/`llm_budget` are process-global). A second concurrent submit returns HTTP 409. The
blocking analysis runs in a worker thread, so the status endpoint (polled every 1s) stays
responsive. **Cancel** is cooperative (`llm_budget.request_abort()` stops at the next LLM call).
**Refresh** is just `POST /api/analyze` with `use_cache:false`. Host/port via `WEB_HOST`/`WEB_PORT`.

## Python API

```python
from stock_analysis import StockAnalysisFlow

# Event-driven Flow pipeline with depth control
flow = StockAnalysisFlow()
result = flow.analyze_stock("NVDA", analysis_depth="deep")   # result["report"] → HTML path

# Direct tool access (no LLM needed)
from stock_analysis.tools import (
    AnalystDataTool, FinancialStatementsTool, OwnershipTool,
    OptionsSentimentTool, SocialSentimentTool, ETFPortfolioTool,
    BacktestTool, PortfolioAnalysisTool,
)
print(AnalystDataTool()._run("NVDA"))          # price targets, ratings, estimates
print(SocialSentimentTool()._run("NVDA"))      # Stocktwits/Reddit sentiment
print(BacktestTool()._run("AAPL", strategy="sma_crossover", period="2y"))

# Render the HTML report from files on disk (deterministic, LLM-free)
from stock_analysis.tools.report_tools import render_html_report
render_html_report("NVDA")
```

---

## Configuration

### `config/agents.yaml`
All 11 agents (roles, goals, backstories, per-agent `llm_config`, `max_execution_time`).
Memory is crew-level only. Reasoning mode is deliberately off — it caused tool loops and
hangs with small models; re-enable per agent via `llm_config.reasoning: true` if desired.

### `config/flow_tasks.yaml`
Every pipeline-stage prompt (per-specialist descriptions, the shared rigor footer, the
final research-narrative spec). No prompt text is hardcoded in Python; `{symbol}` and the
structured data side-channels are interpolated at kickoff.

### `config/llm_config.yaml`
Central LLM defaults and per-agent overrides. Priority: constructor args > agents.yaml
`llm_config` > llm_config.yaml per-agent > env vars > llm_config.yaml global defaults.

### Settings (`config/settings.py`)
| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` / `LLM_MODEL` | from llm_config.yaml | Global LLM override |
| `FRED_API_KEY` | `demo` | FRED economic data |
| `SEC_EDGAR_ENABLED` | `true` | Toggle SEC filing collection |
| `RSS_FEEDS_ENABLED` | `true` | Toggle news collection |
| `WEB_SCRAPING_ENABLED` | `true` | Toggle DuckDuckGo search |
| `REPORT_OUTPUT_DIR` | `<project>/reports` | Output location (relative values anchor to project root) |
| `MAX_WORKERS` | `4` | Parallelism for data fetch and analysis stages |
| `MAX_LLM_CALLS_PER_RUN` | `300` | Hard LLM-call budget per run (scales by symbol count in batch) |
| `LLM_TOKEN_ALERT` | `0` | Log a WARNING when a run's total tokens exceed this (0 = off) |
| `DATA_CACHE_TTL` | `86400` | Cross-run data-bundle reuse window in seconds (0 = always re-fetch) |
| `CACHE_TTL` | `3600` | Default per-tool cache TTL |
| `REDIS_URL` | `redis://localhost:6379/0` | Cache backend (optional; disk tier used when absent) |

---

## Docker

```bash
docker compose up                  # app + Redis + PostgreSQL
docker compose exec app python -m stock_analysis.main AAPL
```

The image runs as a non-root user and ships a `HEALTHCHECK` that verifies the package
imports. With Redis present, the cache becomes shared across containers/runs.

---

## Testing

```bash
pytest tests/ -q                   # full suite — network-free, all sources mocked
pytest tests/test_yf_summaries.py  # data summarizers
pytest tests/test_social_sentiment.py
pytest tests/test_report_tools.py  # HTML rendering, charts, logo
pytest tests/test_cache.py         # 3-tier cache + cross-run reuse + --no-cache
pytest tests/test_observability.py # token meter, credential preflight, HTTP session
```

CI (`.github/workflows/ci.yml`) runs the suite on every push/PR; style and type checks
(`black`, `isort`, `flake8`, `mypy`) run as advisory steps. **Run against the project's
virtualenv** — `python3` on a dev machine may resolve to a different interpreter with a
different CrewAI version (the project targets `crewai==1.14.5`).

---

## Project Structure

```
comprehensive_stock_analysis/
├── src/stock_analysis/
│   ├── agents/          # 11 specialist agents (extend BaseAgent)
│   ├── config/          # agents.yaml, flow_tasks.yaml, llm_config.yaml, settings.py, loader.py
│   ├── crew/            # flow_crew.py (event-driven parallel Flow pipeline)
│   ├── models/          # Pydantic v2 data models
│   ├── llm_budget.py    # hard per-run LLM-call cap (safety stop)
│   ├── token_meter.py   # per-run token accounting + quota alert
│   ├── web/             # FastAPI UI: app, jobs (single-worker queue), progress, routes, static/, templates/
│   └── tools/           # data collection, summarizers, sentiment, analysis,
│                        #   calculation, cache (3-tier), _http (shared session),
│                        #   backtest, portfolio, SVG charts, report
├── tests/               # network-free test suite
├── docs/
├── docker-compose.yml
├── Dockerfile           # non-root, healthcheck
├── pyproject.toml
└── requirements.txt
.github/workflows/ci.yml  # tests + lint on push/PR (repo root)
```

---

## Disclaimer

This tool is for educational and research purposes only. It does not constitute financial advice.
Always consult a qualified financial advisor before making investment decisions. Past performance
does not guarantee future results.
