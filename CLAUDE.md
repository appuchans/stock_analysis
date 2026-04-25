# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_stock_analysis.py

# Run a single test by name
pytest tests/test_stock_analysis.py::TestYahooFinanceTool::test_collect_stock_data

# Run tests by marker
pytest -m unit
pytest -m integration
pytest -m "not slow"

# Format code
black src/ tests/
isort src/ tests/

# Type checking
mypy src/

# Run CLI analysis
python -m stock_analysis.main AAPL
python -m stock_analysis.main AAPL MSFT GOOGL --output reports/
python -m stock_analysis.main AAPL --crew-type flow --llm-provider anthropic --model claude-sonnet-4-6
```

## Architecture Overview

This is a **multi-agent stock analysis system** built on [CrewAI](https://github.com/joaomdmoura/crewAI). Eleven specialized agents collaborate to produce investment reports.

### Agent Orchestration

All agent roles, goals, and backstories are defined in `src/stock_analysis/config/agents.yaml`. Tasks are defined in `config/tasks.yaml`. Flows (execution ordering) are defined in `config/flows.yaml`. The `ConfigLoader` (`config/loader.py`) lazily loads and caches these YAML files — modifying YAML is the primary way to change agent behavior without touching Python.

Agents inherit from `BaseAgent` (`agents/base_agent.py`), which handles LLM initialization (OpenAI or Anthropic), tool assignment, and CrewAI Agent creation. Each specialized agent only needs to override `_get_tools()`.

### Crew Types

There are four crew implementations in `crew/`, selected at runtime via `--crew-type`:
- **`modern_crew.py`** (`ModernStockAnalysisCrew`): Traditional CrewAI `@CrewBase` decorator pattern; default.
- **`flow_crew.py`** (`StockAnalysisFlowCrew`): Flow-based with parallel execution of the 8 analysis agents, then sequential recommendation + report generation. Also contains `QuickAnalysisFlowCrew` (3 agents, ~30 min), `DeepDiveAnalysisFlowCrew`, and `BatchAnalysisFlowCrew`.

`main.py` selects the crew type and is the entry point for both CLI and programmatic use.

### Data Flow

All data is typed via Pydantic models in `models/stock_data.py`. The master container is `StockData`, which aggregates `MarketData`, `TechnicalIndicators`, `FundamentalData`, `RiskMetrics`, `NewsData`, `InvestmentRecommendation`, etc.

Tools in `tools/` perform actual data fetching and calculations:
- `free_data_collection.py`: All external data (Yahoo Finance, SEC EDGAR via EDGAR API, FRED, RSS news, DuckDuckGo) — **no paid APIs are used**.
- `analysis_tools.py`: Technical indicator calculation (`ta-lib`) and fundamental ratio analysis.
- `calculation_tools.py`: Lower-level financial math helpers.

`tasks/task_factory.py` handles dynamic task creation, including string substitution of `{symbol}` placeholders from `tasks.yaml`.

### Configuration

All runtime settings live in `config/settings.py` as a Pydantic `BaseSettings` class. Values are loaded from environment variables (see `env.example` for the full list). The key ones are:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM provider credentials |
| `LLM_PROVIDER` | `openai` (default) or `anthropic` |
| `LLM_MODEL` | Model name, e.g. `gpt-4` or `claude-sonnet-4-6` |
| `FRED_API_KEY` | Federal Reserve economic data (use `demo` for rate-limited free access) |
| `ENABLE_*` flags | Toggle individual data sources on/off |

### Docker

`docker-compose.yml` runs three services: the main app, Redis (caching/Celery), and PostgreSQL. The app writes output to `data/`, `reports/`, and `logs/` directories which are volume-mounted.
