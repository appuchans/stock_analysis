# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Commands

All commands run from `comprehensive_stock_analysis/`.

```bash
# Install
pip install -r requirements.txt
pip install -e ".[dev]"          # editable install with dev extras

# Run analysis (CLI)
python -m stock_analysis.main AAPL
python -m stock_analysis.main AAPL MSFT GOOGL
python -m stock_analysis.main AAPL --depth deep
python -m stock_analysis.main AAPL --no-cache        # force fresh data pull
python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-sonnet-4-6

# Web UI
python -m stock_analysis.web                         # starts FastAPI + uvicorn on default port

# Tests
pytest tests/
pytest tests/test_stock_analysis.py
pytest tests/test_stock_analysis.py::TestValuationCalculatorTool::test_dcf_valid_inputs
pytest -m unit
pytest -m "not slow"

# Lint / type-check
black src/ tests/
isort src/ tests/
flake8 src/
mypy src/

# Docker (app + Redis + PostgreSQL)
docker compose up
docker compose exec app python -m stock_analysis.main AAPL
```

## Architecture Overview

This is a **multi-agent stock analysis system** built on **CrewAI 1.x** (pinned to **1.14.5** — 1.14.6+ requires lancedb builds unavailable on this platform). Eleven specialised agents collaborate in a single pipeline to produce investment reports.

### Agents

`BaseAgent` (`agents/base_agent.py`) initialises `crewai.LLM` directly (not LangChain wrappers). All agent roles, goals, and backstories live in `config/agents.yaml`; tool wiring is the only thing that stays in each agent's `.py` file. Every agent gets `max_execution_time=300s`, `max_rpm=10`, `max_retry_limit=1`, `inject_date=True`, and `cache=True` (CrewAI tool-result cache). Memory is configured at the **Crew level only** — individual agents do not have `memory: true`.

**Reasoning mode is deliberately disabled.** CrewAI 1.14.5's `create_reasoning_plan` sends a function schema that OpenAI's strict mode rejects, causing infinite retry loops. Do not enable per-agent `llm_config.reasoning` until the upstream schema bug is fixed.

### Pipeline / Flow

`StockAnalysisFlow` (`crew/flow_crew.py`) uses the CrewAI 1.x Flow API (`Flow[StockAnalysisState]`, `@start`, `@listen`, `@router`, `or_()`). The `--depth quick|standard|deep` flag routes to different listener methods; independent stages run concurrently via `_run_stages` (capped by `MAX_WORKERS`).

`collect_data` performs a deterministic structured fetch (`_fetch_structured`): one shared `yf.Ticker` feeds summarizers in parallel; results are injected verbatim into task prompts as side-channel variables (`{analyst_data}`, `{financials_data}`, `{ownership_data}`, `{sentiment_data}`, `{technical_data}`). No LLM paraphrasing of raw data.

Stage output files are written by `_write_report_file`, **not** via `Task.output_file` (CrewAI strips leading slashes from absolute non-template paths). HTML rendering runs deterministically in code after the flow, so a report is always produced even when the report agent skips the tool.

### Configuration Files

| File | Purpose |
|---|---|
| `config/agents.yaml` | Agent roles, goals, backstories, per-agent `llm_config` overrides |
| `config/flow_tasks.yaml` | All pipeline stage prompts and shared rigor footer — **no prompt text is hardcoded in Python** |
| `config/llm_config.yaml` | Global + per-agent LLM provider/model/temperature defaults |
| `config/settings.py` | Pydantic `BaseSettings` — all runtime env vars (`LLM_PROVIDER`, `LLM_MODEL`, `FRED_API_KEY`, `*_ENABLED` flags, `MAX_LLM_CALLS_PER_RUN`, `DATA_CACHE_TTL`, etc.) |
| `config/loader.py` | Lazily loads and caches YAML files |

`flow_tasks.yaml` placeholders (`{symbol}`, `{technical_data}`, …) are interpolated by CrewAI at kickoff from the inputs dict. `tests/test_flow_tasks_config.py` guards that every placeholder has a matching input.

### Safety & Observability

- **LLM budget** (`llm_budget.py`): hard per-run cap (`MAX_LLM_CALLS_PER_RUN`, default 300). `BaseAgent._build_llm` wraps every LLM instance's `call`/`acall` via `_with_budget`. Past the cap, no request reaches the provider. Each run calls `llm_budget.reset()` at start; batch runs scale the allowance by symbol count.
- **Token meter** (`token_meter.py`): accumulates `usage_metrics` per crew; `check_alert()` logs WARNING above `LLM_TOKEN_ALERT`. Spend visibility only — not a safety stop.
- **Credential preflight**: `main.py` calls `preflight_llm_credentials()` (in `base_agent.py`) before any work, failing fast (~1s) when the resolved provider key is missing.

### Caching

Three-tier: **Redis** (shared, authoritative when up) → **in-process memory** → **filesystem** (`data/.tool_cache/`, survives between CLI invocations). With Redis down, reads fall through memory→disk; writes populate both. Tool results are decorated with `@cached_tool()` (`tools/cache.py`). Error dicts are never cached.

The **data bundle** (`_fetch_structured`) is cached cross-process by symbol for `DATA_CACHE_TTL` (default 86400s / 24h). `--no-cache` ignores the cached bundle on read but still refreshes the store for later runs.

### Web UI

FastAPI + vanilla JS SPA (`src/stock_analysis/web/`), launched with `python -m stock_analysis.web`. Key constraints:

- **`workers=1` (uvicorn)** — `token_meter`/`llm_budget` are process-global; runs must never overlap. `JobManager` (`jobs.py`) uses `ThreadPoolExecutor(max_workers=1)`; a second submit returns **HTTP 409**.
- Live progress polls `GET /api/jobs/{id}` every 1s (no SSE); status endpoint reads `token_meter.snapshot()` + `llm_budget.used()` directly.
- Cancel: sets a flag + calls `llm_budget.request_abort()`, which raises `AnalysisAbortedError` at the next LLM call (cooperative stop).
- Refresh is `POST /api/analyze` with `use_cache:false` — no separate endpoint.
- History is ordered by `_analyzed_at` (status marker mtime → newest data artifact mtime, excluding the re-render-bumped HTML).
- `_paths.py` enforces a strict symbol regex + `report_output_dir` containment check on every file path (traversal-safe).
- Tests (`tests/test_web_*.py`) use FastAPI `TestClient` with `analyze_stock` mocked; an autouse fixture redirects `report_output_dir` to a tmp dir.

### Data Models & Tools

All structured data uses **Pydantic v2** (`models/stock_data.py`; uses `@field_validator`/`@model_validator`, not deprecated `@validator`). Master container: `StockData`.

Key non-obvious tool facts:
- All HTTP traffic goes through the shared `requests.Session` in `tools/_http.py` (connection pooling, `urllib3 Retry` on 429/5xx, 10s timeout). Tests patch `tools._http.SESSION.get`, not `requests.get`.
- `free_data_collection.py` has a news fallback chain: Google News → Bing News → Yahoo per-symbol RSS.
- FRED data falls back to yfinance market proxies (VIX/10Y/S&P/WTI/DXY) when FRED is unavailable.
- `social_sentiment.py` never returns raw errors in per-source failures — only a neutral note. The top-level `error` key is set only when **all** sources fail (so total failures aren't cached).
- DCF in `calculation_tools.py` guards `discount_rate <= terminal_growth_rate` (would produce a nonsensical result otherwise).
- Output paths are anchored to `settings.PROJECT_ROOT` (`REPORT_OUTPUT_DIR`, `DATA_OUTPUT_DIR`, `CREW_LOG_FILE`) regardless of cwd.
