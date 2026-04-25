# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

All commands run from `comprehensive_stock_analysis/`.

```bash
# Install dependencies
pip install -r requirements.txt
# or editable install with dev extras
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_stock_analysis.py

# Run a single test by name
pytest tests/test_stock_analysis.py::TestValuationCalculatorTool::test_dcf_valid

# Run tests by marker
pytest -m unit
pytest -m integration
pytest -m "not slow"

# Format and lint
black src/ tests/
isort src/ tests/
flake8 src/
mypy src/

# Run CLI analysis
python -m stock_analysis.main AAPL
python -m stock_analysis.main AAPL MSFT GOOGL --output reports/
python -m stock_analysis.main AAPL --crew-type flow --analysis-depth deep
python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-sonnet-4-6

# Docker (full stack: app + Redis + PostgreSQL)
docker compose up
docker compose exec app python -m stock_analysis.main AAPL
```

## Architecture Overview

This is a **multi-agent stock analysis system** built on **CrewAI 1.x**. Eleven specialised agents collaborate to produce investment reports.

### LLM Initialisation

`BaseAgent` (`agents/base_agent.py`) uses `crewai.LLM` (not LangChain wrappers) to initialise the model. Provider and model are passed at construction time or read from `settings.py`. The `investment_advisor` and `report_generator` agents have `reasoning: true` in `agents.yaml`, which tells `_create_agent()` to set `reasoning=True` on the CrewAI Agent.

### Agent Orchestration

All agent roles, goals, and backstories are defined in `config/agents.yaml`. Tasks are defined in `config/tasks.yaml`. The `ConfigLoader` (`config/loader.py`) lazily loads and caches these YAML files. Agents inherit from `BaseAgent`; each specialised agent only needs to override `_get_tools()`.

Memory is configured **at the Crew level only** — individual agents do not have `memory: true` (removed per CrewAI 1.x best practices).

### Crew Types

Four crew implementations in `crew/`:

| Class | File | Key feature |
|---|---|---|
| `StockAnalysisCrew` | `stock_analysis_crew.py` | `@CrewBase` with `output_pydantic`, guardrail on recommendation task, `step_callback` |
| `ModernStockAnalysisCrew` | `modern_crew.py` | YAML-config tasks; `akickoff_for_each()` for async parallel batch analysis |
| `StockAnalysisFlowCrew` | `flow_crew.py` | Standard-depth Flow (technical/fundamental/risk/sentiment) |
| `QuickAnalysisFlowCrew` | `flow_crew.py` | Quick-depth Flow (technical + fundamental only) |
| `DeepDiveAnalysisFlowCrew` | `flow_crew.py` | Deep-depth Flow (all eight specialist agents) |

`flow_crew.py` uses the real CrewAI 1.x Flow API: `Flow[StockAnalysisState]` with `@start`, `@listen`, `@router`, and `or_()` decorators. `analysis_depth` is set on `StockAnalysisState` and the `@router` routes to `"quick"` / `"standard"` / `"deep"` listener methods.

`main.py` selects the crew type and is the entry point for both CLI and programmatic use.

### Data Flow

All data is typed via **Pydantic v2** models in `models/stock_data.py` (uses `@field_validator`, `@model_validator`, not deprecated `@validator`). The master container is `StockData`.

Tools in `tools/`:
- `free_data_collection.py` — Yahoo Finance, SEC EDGAR, FRED, RSS, DuckDuckGo; parallel fetch via `ThreadPoolExecutor` (`ParallelDataCollectionTool`)
- `analysis_tools.py` — technical indicators (`ta-lib`) and fundamental ratio analysis
- `calculation_tools.py` — DCF, dividend discount, VaR, Sharpe; DCF guards `discount_rate <= terminal_growth_rate`
- `cache.py` — `@cached_tool()` Redis decorator; degrades gracefully when Redis is absent
- `backtest_tools.py` — SMA crossover and RSI-reversion back-tests
- `portfolio_tools.py` — correlation matrix, min-variance weights, portfolio Sharpe/VaR
- `report_tools.py` — Jinja2 HTML reports with JSON fallback

`tasks/task_factory.py` handles dynamic task creation. It sets `create_directory=True` on every `Task` and logs a warning (rather than silently dropping) if a circular dependency is detected.

### Configuration

All runtime settings are in `config/settings.py` as a Pydantic `BaseSettings` class. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | LLM provider credentials |
| `LLM_PROVIDER` | `openai` | `openai`, `anthropic`, or `ollama` |
| `LLM_MODEL` | `gpt-4o` | Model name |
| `FRED_API_KEY` | `demo` | Federal Reserve data (`demo` = rate-limited free access) |
| `ENABLE_*` flags | `true` | Toggle individual data sources on/off |
| `DEBUG` | `false` | Bypasses secret key validation when `true` |

### Docker

`docker-compose.yml` runs three services: `app`, `redis` (caching/Celery), `db` (PostgreSQL). Output written to `data/`, `reports/`, `logs/` which are volume-mounted.
