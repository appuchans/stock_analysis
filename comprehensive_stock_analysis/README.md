# Comprehensive Stock Analysis Solution

A production-ready, multi-agent stock analysis system built on **CrewAI 1.x** with event-driven
Flow orchestration, Pydantic v2 typed outputs, Redis caching, and free-only data sources.

---

## Features

### Multi-Agent Architecture (CrewAI 1.x)
- **11 specialised agents** — Data Collector, Technical Analyst, Fundamental Analyst, Risk Analyst,
  Sentiment Analyst, Market Analyst, Industry Analyst, Competitor Analyst, Economic Analyst,
  Investment Advisor, Report Generator
- **Native `crewai.LLM`** — no LangChain wrapper; supports OpenAI, Anthropic, and Ollama models
- **Per-agent reasoning** — Investment Advisor and Report Generator use `reasoning=True` for
  pre-task reflection (configurable in `config/agents.yaml`)
- **Crew-level memory** with OpenAI embeddings for cross-task context retention
- **`step_callback`** on every crew for structured observability logging

### Flow-Based Orchestration
- **`StockAnalysisFlow`** (`flow_crew.py`) — event-driven with `@start` / `@listen` / `@router`
  decorators; routes to `quick`, `standard`, or `deep` analysis based on `analysis_depth`
- **`ModernStockAnalysisCrew`** (`modern_crew.py`) — YAML-config-driven sequential crew with
  `akickoff_for_each()` async batch execution across multiple symbols
- **`StockAnalysisCrew`** (`stock_analysis_crew.py`) — `@CrewBase` decorator pattern with
  `output_pydantic` typed task outputs and a guardrail on the recommendation task

### Typed Outputs & Validation
- Task outputs typed with **Pydantic v2** models (`TechnicalIndicators`, `RiskMetrics`,
  `InvestmentRecommendation`) via `output_pydantic=` on Task
- **Recommendation guardrail** — rejects output missing required fields before it is accepted
- All models use `@field_validator` / `@model_validator` (Pydantic v2 API)

### Analysis Capabilities
| Domain | What is produced |
|---|---|
| Technical | RSI, MACD, Bollinger Bands, SMA/EMA (20/50/200), ADX, ATR, Stochastic, OBV |
| Fundamental | P/E, P/B, P/S, PEG, EV/EBITDA, ROE/ROA/ROIC, DCF intrinsic value |
| Risk | Beta (live vs S&P 500), Sharpe, Sortino, VaR 95%, max drawdown, CVaR |
| Sentiment | News sentiment aggregation, analyst consensus, trend direction |
| Backtesting | SMA crossover and RSI-reversion strategy simulation (`BacktestTool`) |
| Portfolio | Correlation matrix, min-variance weights, portfolio Sharpe/VaR (`PortfolioAnalysisTool`) |
| Reports | Jinja2 HTML report with embedded charts; JSON fallback (`ReportGeneratorTool`) |

### Data Sources (Free Only)
- **Yahoo Finance** — price history, fundamentals, analyst ratings, company info
- **SEC EDGAR** — 10-K, 10-Q, 8-K filings (no API key required)
- **FRED** — Federal Reserve economic indicators (`demo` key available)
- **RSS feeds** — financial news from major outlets
- **DuckDuckGo** — free web search for industry/competitor context
- Parallel data collection via `ThreadPoolExecutor` for sub-second multi-source fetches

### Caching
- `@cached_tool()` decorator (`tools/cache.py`) wraps tool `_run` methods with Redis-backed
  caching; falls back silently to uncached execution when Redis is unavailable

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/appuchans/stock_analysis.git
cd stock_analysis/comprehensive_stock_analysis

# Minimal install
pip install -r requirements.txt

# Or editable install with dev extras
pip install -e ".[dev]"
```

### 2. Configure environment

```bash
cp env.example .env
# Edit .env — at minimum set one LLM key
```

Required for any analysis:
```
OPENAI_API_KEY=sk-...           # or ANTHROPIC_API_KEY
```

Optional (free-tier or no-cost alternatives available):
```
FRED_API_KEY=demo               # Federal Reserve data; "demo" gives rate-limited access
LLM_PROVIDER=openai             # or: anthropic, ollama
LLM_MODEL=gpt-4o                # or: claude-sonnet-4-6, llama3, etc.
```

### 3. Run

```bash
# Single stock — standard crew
python -m stock_analysis.main AAPL

# Multiple stocks in parallel (akickoff_for_each)
python -m stock_analysis.main AAPL MSFT GOOGL

# Choose analysis depth via Flow crew
python -m stock_analysis.main AAPL --crew-type flow
python -m stock_analysis.main AAPL --crew-type flow --analysis-depth quick
python -m stock_analysis.main AAPL --crew-type flow --analysis-depth deep

# Use Anthropic
python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-sonnet-4-6

# Write output to a specific file
python -m stock_analysis.main AAPL --output reports/aapl.json
```

---

## Python API

```python
# Standard sequential crew (all 11 agents)
from stock_analysis import StockAnalysisCrew

crew = StockAnalysisCrew(llm_provider="openai", model="gpt-4o")
result = crew.analyze_stock("AAPL")

# Config-driven crew with async batch analysis
from stock_analysis import ModernStockAnalysisCrew

crew = ModernStockAnalysisCrew()
result = crew.analyze_multiple_stocks(["AAPL", "MSFT", "GOOGL"])

# Flow crew — choose depth at runtime
from stock_analysis import QuickAnalysisFlowCrew, StockAnalysisFlowCrew, DeepDiveAnalysisFlowCrew

quick = QuickAnalysisFlowCrew()           # technical + fundamental only
standard = StockAnalysisFlowCrew()        # + risk + sentiment
deep = DeepDiveAnalysisFlowCrew()         # all eight specialist agents

result = deep.analyze_stock("NVDA")

# Backtesting
from stock_analysis.tools.backtest_tools import BacktestTool

bt = BacktestTool()
result = bt._run("AAPL", strategy="sma_crossover", period="2y")

# Portfolio analysis
from stock_analysis.tools.portfolio_tools import PortfolioAnalysisTool

pt = PortfolioAnalysisTool()
result = pt._run(["AAPL", "MSFT", "GOOGL", "AMZN"])

# HTML report generation
from stock_analysis.tools.report_tools import ReportGeneratorTool

rt = ReportGeneratorTool()
result = rt._run("AAPL", analysis_data={...})
```

---

## Crew Types

| Class | File | Description |
|---|---|---|
| `StockAnalysisCrew` | `crew/stock_analysis_crew.py` | `@CrewBase` with typed outputs, guardrail, `step_callback` |
| `ModernStockAnalysisCrew` | `crew/modern_crew.py` | YAML-config tasks; `akickoff_for_each` batch async |
| `StockAnalysisFlowCrew` | `crew/flow_crew.py` | Standard depth Flow (technical/fundamental/risk/sentiment) |
| `QuickAnalysisFlowCrew` | `crew/flow_crew.py` | Quick depth Flow (technical + fundamental only) |
| `DeepDiveAnalysisFlowCrew` | `crew/flow_crew.py` | Deep depth Flow (all eight analysts) |

---

## Configuration

### Agent configuration (`config/agents.yaml`)
All 11 agents are defined here. Memory is **crew-level only** (not per-agent, per CrewAI 1.x
best practices). The `investment_advisor` and `report_generator` have `reasoning: true` enabled
to trigger pre-task reflection.

### Task configuration (`config/tasks.yaml`)
Task descriptions, expected outputs, dependencies, and output file paths. All paths accept
a `{symbol}` placeholder that is substituted at runtime. Tasks are built via `TaskFactory`
which automatically sets `create_directory=True`.

### Settings (`config/settings.py`)
All runtime settings are Pydantic `BaseSettings` loaded from environment variables. Key flags:

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `openai` | `openai`, `anthropic`, or `ollama` |
| `LLM_MODEL` | `gpt-4o` | Model identifier |
| `FRED_API_KEY` | `demo` | FRED economic data |
| `ENABLE_SEC_EDGAR` | `true` | Toggle SEC filing collection |
| `ENABLE_RSS_FEEDS` | `true` | Toggle RSS news collection |
| `ENABLE_WEB_SCRAPING` | `true` | Toggle DuckDuckGo search |
| `DEBUG` | `false` | Enable debug mode (also bypasses secret key validation) |
| `SECRET_KEY` | — | Must be set in production (validated at startup) |

---

## Docker

```bash
# Start full stack (app + Redis + PostgreSQL)
docker compose up

# App only
docker compose up app

# Run analysis inside container
docker compose exec app python -m stock_analysis.main AAPL
```

Services defined in `docker-compose.yml`:
- `app` — main analysis service (port 8000)
- `redis` — caching and Celery broker
- `db` — PostgreSQL persistence

---

## Testing

```bash
# All tests
pytest tests/ -v

# By marker
pytest -m unit
pytest -m integration
pytest -m "not slow"

# Single test
pytest tests/test_stock_analysis.py::TestValuationCalculatorTool::test_dcf_valid -v

# With coverage report
pytest --cov=src/stock_analysis --cov-report=html
```

Key test classes: `TestYahooFinanceTool`, `TestRiskCalculatorTool`,
`TestTechnicalIndicatorTool`, `TestValuationCalculatorTool`, `TestTaskFactory`,
`TestAPIFailureHandling`.

---

## Project Structure

```
comprehensive_stock_analysis/
├── src/stock_analysis/
│   ├── agents/          # 11 specialist agents (all extend BaseAgent)
│   ├── config/          # agents.yaml, tasks.yaml, flows.yaml, settings.py, loader.py
│   ├── crew/            # stock_analysis_crew.py, modern_crew.py, flow_crew.py
│   ├── models/          # Pydantic v2 data models (StockData, RiskMetrics, …)
│   ├── tasks/           # TaskFactory with dependency-ordered execution
│   └── tools/           # data collection, analysis, calculation, cache, backtest, portfolio, report
├── tests/
├── docs/
├── examples/
├── docker-compose.yml
├── pyproject.toml
├── requirements.txt
└── env.example
```

---

## Code Quality

```bash
black src/ tests/       # formatting
isort src/ tests/       # import sorting
flake8 src/             # linting
mypy src/               # type checking
pre-commit install      # install git hooks
```

---

## Disclaimer

This tool is for educational and research purposes only. It does not constitute financial advice.
Always consult a qualified financial advisor before making investment decisions. Past performance
does not guarantee future results.
