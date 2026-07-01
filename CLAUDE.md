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
pytest tests/test_stock_analysis.py::TestValuationCalculatorTool::test_dcf_valid_inputs

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
python -m stock_analysis.main AAPL MSFT GOOGL
python -m stock_analysis.main AAPL --depth deep
python -m stock_analysis.main AAPL --no-cache   # force a fresh data pull
python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-sonnet-4-6

# Docker (full stack: app + Redis + PostgreSQL)
docker compose up
docker compose exec app python -m stock_analysis.main AAPL
```

## Architecture Overview

This is a **multi-agent stock analysis system** built on **CrewAI 1.x**. Eleven specialised agents collaborate to produce investment reports.

### LLM Initialisation

`BaseAgent` (`agents/base_agent.py`) uses `crewai.LLM` (not LangChain wrappers) to initialise the model. Provider and model are passed at construction time or read from `settings.py`. Every agent gets `max_execution_time` (default 300s), `max_rpm` (default 10/min), `max_retry_limit` (1), `inject_date=True` (current date in task context), and `cache=True` (CrewAI tool-result cache — identical tool calls return cached results, letting the repeated-call guard break tool loops); all configurable per agent in `agents.yaml`. Prose tasks set `markdown=True`; the flow's narrative task has a native `guardrail` (rejects status-summary answers, 1 retry). crewai is **pinned to 1.14.5** — 1.14.6+ requires lancedb builds unavailable on this platform. Reasoning mode is deliberately disabled — CrewAI 1.14.5's `create_reasoning_plan` sends a function schema OpenAI's strict mode rejects, producing infinite retry loops (a PEGA run burned ~8,000 LLM calls); opt back in per agent via `llm_config.reasoning` only after verifying the schema bug is fixed upstream. As the last line of defense, `llm_budget.py` enforces a hard per-run LLM-call cap (`MAX_LLM_CALLS_PER_RUN`, default 300): `BaseAgent._build_llm` wraps every LLM instance's `call`/`acall` via `_with_budget`, so past the cap no request can reach the provider; crews call `llm_budget.reset()` at each run start (batch runs scale the allowance by symbol count). Before any work, `main.py` calls `preflight_llm_credentials()` (in `base_agent.py`) to fail fast in ~1s when the resolved provider's API key is missing, instead of dying deep in the flow. Observability is separate from the safety stop: `token_meter.py` accumulates each crew's `usage_metrics` (`_run_crew` calls `token_meter.add`; flow resets it per run and returns `token_usage`+`llm_calls`); `main.py` prints them, and `token_meter.check_alert()` logs a WARNING when a run's total tokens exceed `LLM_TOKEN_ALERT` (0 = off). Budget = call-count safety; token meter = spend visibility.

### Agent Orchestration

All agent roles, goals, and backstories are defined in `config/agents.yaml`. Flow-pipeline stage prompts (including the shared rigor footer and collected-data wrapper) live in `config/flow_tasks.yaml` — no prompt text is hardcoded in Python. Flow YAML placeholders (`{symbol}`, `{technical_data}`, `{analyses_summary}`, …) are interpolated by CrewAI at kickoff from the inputs dict; `tests/test_flow_tasks_config.py` guards that every placeholder has a matching input. The `ConfigLoader` (`config/loader.py`) lazily loads and caches these YAML files. Agents inherit from `BaseAgent`; each specialised agent only needs to override `_get_tools()` (tool wiring is the only thing that stays in the agent `.py` files).

Memory is configured **at the Crew level only** — individual agents do not have `memory: true` (removed per CrewAI 1.x best practices).

### Pipeline

A single pipeline: `StockAnalysisFlow` (`crew/flow_crew.py`), selected with `--depth quick|standard|deep`. (A second sequential crew once existed but was removed — it duplicated the flow with lossy LLM-forwarded data and a kitchen-sink report; the flow is the only path now.)

`flow_crew.py` uses the CrewAI 1.x Flow API: `Flow[StockAnalysisState]` with `@start`, `@listen`, `@router`, and `or_()` decorators. `analysis_depth` on `StockAnalysisState` routes to `"quick"` / `"standard"` / `"deep"` listener methods. Independent analysis stages run **concurrently** (`_run_stages`, capped by `MAX_WORKERS`). `collect_data` performs a deterministic structured fetch (`_fetch_structured`): one shared `yf.Ticker` feeds the `yf_summaries` summarizers in parallel, and the results are passed verbatim into task prompts as `{analyst_data}`, `{financials_data}`, `{ownership_data}`, `{sentiment_data}`, and `{technical_data}` side-channels. The entire fetch is split into `_fetch_structured` (a cache-aware dispatcher) → `_fetch_structured_uncached` (returns a `{structured, technical_summary, chart}` bundle) → `_apply_structured_bundle` (restores state + writes chart JSON, recomputing `sentiment_history` so it stays fresh on cache hits). The bundle is cached cross-process by symbol for `data_cache_ttl` (default 86400s/24h; `DATA_CACHE_TTL=0` to always re-fetch), so a repeat analysis of the same ticker that day skips **all** network collection — this is the main cross-run optimisation, since the raw summarizers are otherwise uncached. The CLI flag `--no-cache` (→ `StockAnalysisFlow(use_data_cache=False)`) forces a fresh pull for one run, ignoring the cached bundle on read while still refreshing the store for later runs. Stage output files are written directly by `_write_report_file` (NOT via `Task.output_file` — CrewAI strips the leading slash from absolute non-template paths). HTML rendering is deterministic: `render_html_report()` runs in code after the flow completes, so a report is produced even when the report agent doesn't invoke a tool.

`crew/event_listener.py` registers a `BaseEventListener` at import time for structured observability (task complete, agent action, crew complete events).

`main.py` is the entry point for both CLI and programmatic use.

### Web UI

A local single-user web interface lives in `src/stock_analysis/web/` (FastAPI backend + no-build vanilla-JS/Chart.js frontend), launched with `python -m stock_analysis.web` (`__main__.py`; reuses `main.py` logging, warns-not-exits on missing keys, `uvicorn` with **`workers=1`**). It wraps the same `StockAnalysisApp.analyze_stock`. Key design points:
- **Serialization is mandatory**: `token_meter`/`llm_budget` are process-global and reset per run, so runs must never overlap. `jobs.py` `JobManager` uses a `ThreadPoolExecutor(max_workers=1)`; a second submit while one is active returns **HTTP 409**. The blocking analysis runs in the worker thread (never the async handler), so `GET /api/jobs/{id}` stays responsive and is **polled every 1s** (not SSE).
- **Live progress** with no new flow plumbing: the status endpoint reads `token_meter.snapshot()` + `llm_budget.used()` directly; `progress.py` registers one persistent CrewAI-event-bus listener (`CrewKickoffCompleteEvent`) that forwards to the active run's `StageTracker`, mapping completed crews → stage label + 0–1 fraction (set-active/clear-active around each run avoids the unsubscribe problem).
- **Cancel / Refresh**: `POST /api/jobs/{id}/cancel` → `JobManager.cancel` sets a flag + `llm_budget.request_abort()`, which makes the next `check_and_increment()` raise `AnalysisAbortedError` (cooperative — stops at the next LLM call); the worker marks the job `aborted`. **Refresh** is just `POST /api/analyze` with `use_cache:false` (forces a fresh data pull so format/ETF-field changes regenerate) — used by the History and Report refresh buttons; no separate endpoint. Every run writes a `<SYM>_run_status.json` marker so the history gallery shows aborted/failed/completed even when no report was produced; history is ordered by a **stable analysis timestamp** (`_analyzed_at`: status marker → newest *data* artifact mtime, excluding the re-render-bumped HTML).
- **Reuse over rebuild**: `routes/results.py` serves the existing self-contained HTML report (iframe-embedded) and `<SYM>_chart_data.json`; `dashboard.js` builds the interactive Overview from that JSON (ETF reports show fund facts from `chart_data.etf_profile`/`asset_type` instead of stock tiles); `reports_index.py` scans `report_output_dir` for the history gallery. `_paths.py` guards every file path with a strict symbol regex + `report_output_dir` containment check (traversal-safe). Frontend (`static/`) is a no-build SPA: left-sidebar app shell, **light/dark theme** via `[data-theme]` on `<html>` (localStorage + `prefers-color-scheme`), bundled **Inter** font (`static/fonts/`), Chart.js themed live from CSS vars (`util.theme()`). `app.py` sets `Cache-Control: no-cache` on `/static` + `/api/reports` so edits and re-runs show immediately. Tests: `tests/test_web_*.py` (FastAPI `TestClient`, `analyze_stock` mocked; an autouse fixture points `report_output_dir` at a tmp dir so the worker's status markers never touch the real `reports/`). New settings `web_host`/`web_port`.

### Data Flow

All data is typed via **Pydantic v2** models in `models/stock_data.py` (uses `@field_validator`, `@model_validator`, not deprecated `@validator`). There is no single unified container class — only the models actually consumed by the running code are kept: `CompanyInfo`, `MarketData`, `FundamentalData`, `NewsData`, `EconomicData` (built by the data collectors) and `InvestmentRecommendation` (validated against the advisor's structured output).

Tools in `tools/`:
- `free_data_collection.py` — Yahoo Finance (incl. short interest), SEC EDGAR, FRED (with yfinance market-proxy fallback: VIX/10Y/S&P/WTI/DXY), news with fallback chain (Google News → Bing News → Yahoo per-symbol RSS), DuckDuckGo; parallel fetch via `ThreadPoolExecutor` (`ParallelDataCollectionTool`, which also merges analyst/statements/ownership/social blocks)
- `yf_summaries.py` — compact, prompt-sized summarizers over a shared `yf.Ticker` (analyst consensus, ownership, 3-year statements, options put/call, dividends, ETF portfolio); every accessor guarded, partial results on failure
- `company_intel.py` — cached tool wrappers: `AnalystDataTool`, `OwnershipTool`, `FinancialStatementsTool`, `OptionsSentimentTool`, `ETFPortfolioTool`
- `social_sentiment.py` — `SocialSentimentTool`: Stocktwits (keyless, labeled bullish/bearish), Reddit (JSON with automatic RSS fallback), CNN Fear & Greed (market-wide); per-source failure isolation with neutral notes (never raw errors), top-level `error` only when all sources fail (so total failures aren't cached)
- `analysis_tools.py` — technical indicators (pure pandas/numpy, see `_indicators.py`) and fundamental ratio analysis
- `calculation_tools.py` — DCF, dividend discount, VaR, Sharpe (annualised); DCF guards `discount_rate <= terminal_growth_rate`
- `cache.py` — three-tier cache (`@cached_tool()` decorator + `get_cached`/`set_cached` helpers): Redis (shared, authoritative when up) → in-process memory → **filesystem** (`data/.tool_cache/`, survives between CLI invocations). Never caches error dicts. With Redis down, reads fall through memory→disk and writes populate both; the disk tier is what lets a same-symbol re-run reuse data cross-process without Redis. A one-time `_sweep_disk_cache` on first dir use bounds the dir (age cap `_DISK_SWEEP_MAX_AGE` 7d, count cap `_MAX_DISK_CACHE_FILES` 512)
- `_http.py` — shared `requests.Session` (`SESSION`, plus `get`/`post` helpers) with connection pooling, `urllib3 Retry` (2 retries, backoff, on 429/5xx), and a default 10s timeout. **All tool HTTP traffic goes through it** — `free_data_collection.py`, `social_sentiment.py`, `yf_summaries.py` call `_http.get`. Tests patch `tools._http.SESSION.get` (not module-level `requests.get`)
- `backtest_tools.py` — SMA crossover and RSI-reversion back-tests (wired to the technical analyst)
- `portfolio_tools.py` — correlation matrix, min-variance weights, portfolio Sharpe/VaR (wired to the investment advisor)
- `_svg_charts.py` — dependency-free inline SVG line/bar charts
- `report_tools.py` — Jinja2 HTML reports with SVG charts, keyless company logo (Google favicon service), chart data from `{SYM}_chart_data.json` (guarded live fallback); `render_html_report()` is the deterministic LLM-free entry point

Output paths are **anchored to the project root** (`settings.PROJECT_ROOT`): `REPORT_OUTPUT_DIR`, `DATA_OUTPUT_DIR`, and `CREW_LOG_FILE` resolve relative values against the project directory regardless of cwd.

### Configuration

All runtime settings are in `config/settings.py` as a Pydantic `BaseSettings` class. Key variables:

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | LLM provider credentials |
| `LLM_PROVIDER` | `openai` | `openai`, `anthropic`, or `ollama` |
| `LLM_MODEL` | `gpt-4o` | Model name |
| `FRED_API_KEY` | `demo` | Federal Reserve data (`demo` = rate-limited free access) |
| `*_ENABLED` flags (e.g. `SEC_EDGAR_ENABLED`) | `true` | Toggle individual data sources on/off |
| `CREW_LOG_FILE` | `logs/crew_output.log` | Persistent crew execution log |
| `DEBUG` | `false` | Debug mode flag |

### Docker

`docker-compose.yml` runs three services: `app`, `redis` (caching/Celery), `db` (PostgreSQL). Output written to `data/`, `reports/`, `logs/` which are volume-mounted.
