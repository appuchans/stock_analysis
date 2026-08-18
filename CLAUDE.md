# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Guiding Principle: commonsense minimalism

**Solve the problem that was actually reported, with the least machinery that
holds.** This is a single-user local app, not a platform. Prefer the obvious
solution a sensible person would reach for first.

In practice:

- **Fix it where the problem is.** Guard the endpoint the user actually hits;
  don't thread a flag through four layers so every hypothetical caller is
  covered. If callers that bypass the fix are already deliberate user actions
  (a scheduled run, a bulk "analyze all"), that is not a gap to close.
- **Don't build abstractions for one caller.** A custom exception class, a
  structured error payload, and a settings knob to pass one number is worse
  than a plain 409 with a readable message.
- **Prefer config and prompts over Python.** Stage behaviour lives in
  `flow_tasks.yaml`; `_desc_for` already resolves stock/ETF variants. Adding a
  YAML key beats adding a code path.
- **Test what would actually break.** Two tests that pin the real behaviour beat
  eight that enumerate every branch. Edge cases written reflexively are cost,
  not coverage.
- **Reuse before adding.** `price_series.py`, `_http.SESSION`, `cache.py`, the
  provider `ROUTER`, and the shared JS modules exist so features don't each grow
  their own version. Extend them.

When a change starts sprawling — new classes, new plumbing, new flags — stop and
ask whether the five-line version would hold. It usually does. If it genuinely
would not, say why in a comment where the complexity lives.

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

# Run the local web UI (http://127.0.0.1:8000 by default)
python -m stock_analysis.web

# Docker (full stack: app + Redis + PostgreSQL)
docker compose up
docker compose exec app python -m stock_analysis.main AAPL
```

## Architecture Overview

A **multi-agent stock analysis system** built on **CrewAI 1.x**. Eleven specialised agents (`agents/`, roles in `config/agents.yaml`) collaborate to produce investment reports. Two entry points share one engine: the CLI (`main.py`) and a local FastAPI web UI (`web/`), both wrapping `StockAnalysisApp.analyze_stock`.

### LLM Initialisation

`BaseAgent` (`agents/base_agent.py`) uses `crewai.LLM` directly — **not** LangChain wrappers.

- **Config priority** (highest wins, `BaseAgent._resolve_llm_config`): constructor args > `agents.yaml` per-agent `llm_config` > `llm_config.yaml` per-agent overrides > env vars (`settings`) > `llm_config.yaml` global defaults.
- `preflight_llm_credentials()` must check **every layer that can select a provider** (CLI override, `llm_config.yaml` per-agent, `agents.yaml` per-agent) — otherwise a misconfigured agent-level override slips past the fast-fail check. `main.py` calls it before any work so a missing API key fails in ~1s instead of dying deep in the flow.
- Provider names are **not whitelisted** — `settings.validate_llm_provider` only normalises case/whitespace, because `_build_llm` resolves any provider through LiteLLM's generic `"<provider>/<model>"` convention. `llm_config.yaml`'s `provider_prefixes` documents known ones; unlisted providers still work. Do not reintroduce a validation whitelist.
- **Per-agent defaults** (all overridable in `agents.yaml`): `max_execution_time` 300s, `max_rpm` 10/min, `max_retry_limit` 1, `inject_date=True` (current date in task context), `cache=True` (CrewAI tool-result cache — identical calls return cached results, letting the repeated-call guard break tool loops). Prose tasks set `markdown=True`; the flow's narrative task has a native `guardrail` (rejects status-summary answers, 1 retry).

**Two traps worth their own paragraph:**

- crewai is **pinned to 1.14.5** — 1.14.6+ requires lancedb builds unavailable on this platform.
- **Reasoning mode is deliberately disabled.** CrewAI 1.14.5's `create_reasoning_plan` sends a function schema OpenAI's strict mode rejects, producing infinite retry loops (a PEGA run burned ~8,000 LLM calls). Opt back in per agent via `llm_config.reasoning` **only** after verifying the schema bug is fixed upstream.

**Budget vs. metering** — two different mechanisms, don't conflate them:

- `llm_budget.py` is the *safety stop*: a hard per-run call cap (`MAX_LLM_CALLS_PER_RUN`, default 300). `BaseAgent._build_llm` wraps every LLM instance's `call`/`acall` via `_with_budget`, so past the cap no request can reach the provider. Crews call `llm_budget.reset()` at each run start (batch runs scale the allowance by symbol count).
- `token_meter.py` is *spend visibility*: it accumulates each crew's `usage_metrics` (`_run_crew` calls `token_meter.add`; the flow resets it per run and returns `token_usage` + `llm_calls`). `main.py` prints them; `check_alert()` logs a WARNING when a run exceeds `LLM_TOKEN_ALERT` (0 = off).

### Agent Orchestration

Agent roles, goals, and backstories live in `config/agents.yaml`. Flow-pipeline stage prompts (including the shared rigor footer and collected-data wrapper) live in `config/flow_tasks.yaml` — **no prompt text is hardcoded in Python**. Flow YAML placeholders (`{symbol}`, `{technical_data}`, `{analyses_summary}`, …) are interpolated by CrewAI at kickoff from the inputs dict; `tests/test_flow_tasks_config.py` guards that every placeholder has a matching input. `ConfigLoader` (`config/loader.py`) lazily loads and caches these YAMLs.

Agents inherit from `BaseAgent`; each specialised agent only overrides `_get_tools()` — tool wiring is the only thing that stays in the agent `.py` files.

Memory is configured **at the Crew level only** — individual agents do not have `memory: true` (removed per CrewAI 1.x best practices).

### Pipeline

One pipeline: `StockAnalysisFlow` (`crew/flow_crew.py`), selected with `--depth quick|standard|deep`. (A second sequential crew once existed but was removed — it duplicated the flow with lossy LLM-forwarded data and a kitchen-sink report.)

- **Flow API**: `Flow[StockAnalysisState]` with `@start`, `@listen`, `@router`, `or_()`. `analysis_depth` routes to `"quick"` / `"standard"` / `"deep"` listener methods. Independent stages run **concurrently** (`_run_stages`, capped by `MAX_WORKERS`).
- **Deterministic data collection**: `collect_data` runs a structured fetch — one shared `yf.Ticker` feeds the `yf_summaries` summarizers in parallel, and results pass verbatim into prompts as `{analyst_data}`, `{financials_data}`, `{ownership_data}`, `{sentiment_data}`, `{technical_data}` side-channels (no LLM in the loop).
- **Fetch is split three ways**: `_fetch_structured` (cache-aware dispatcher) → `_fetch_structured_uncached` (returns a `{structured, technical_summary, chart}` bundle) → `_apply_structured_bundle` (restores state + writes chart JSON, recomputing `sentiment_history` so it stays fresh on cache hits). The bundle is cached cross-process by symbol for `data_cache_ttl` (default 86400s/24h; `DATA_CACHE_TTL=0` disables), so a same-day repeat skips **all** network collection — the main cross-run optimisation, since the raw summarizers are otherwise uncached. `--no-cache` (→ `StockAnalysisFlow(use_data_cache=False)`) ignores the cached bundle on read while still refreshing the store for later runs.
- **Premium enrichment** (`_enrich_with_premium_providers`): on **deep** runs only, and only when `FMP_API_KEY` is set, the provider `ROUTER` populates two extra prompt side-channels (`{statements_10y_data}`, `{transcript_data}`, wired into `flow_tasks.yaml`'s fundamental-analyst task) and enriches `structured["analyst"]["estimate_revisions"]` / `structured["ownership"]["insider_trades_detail"]` in place. Everything degrades to yfinance when unset.
- **Output files** are written directly by `_write_report_file`, **not** via `Task.output_file` — CrewAI strips the leading slash from absolute non-template paths.
- **HTML rendering is deterministic**: `render_html_report()` runs in code *after* the flow completes, so a report exists even when the report agent never invokes a tool, or when the report/recommendation crew raises (`generate_report`/`synthesize_recommendation` catch and log rather than aborting the flow with zero artifact).

`crew/event_listener.py` registers a `BaseEventListener` at import time for structured observability (task complete, agent action, crew complete).

### Market Data Providers

`tools/providers/` is a pluggable market-data layer that **wraps rather than replaces** `free_data_collection.py` / `yf_summaries.py`.

- `base.py` — `MarketDataProvider` `Protocol` with 8 capability methods (`get_quote`, `get_daily_bars`, `get_statements`, `get_estimates`, `get_transcript`, `get_insider_trades`, `get_calendar`, `get_etf_holdings`). Each returns `{}` for a genuine **capability gap** vs. `{"error": ...}` for a **failure** — the router treats these differently, so preserve the distinction. `ProviderBase` supplies no-op defaults; a provider overrides only what it supports.
- `router.py` — module-level `ROUTER` singleton with per-capability chains: price/bars → Polygon → yfinance; fundamentals/depth → FMP → yfinance. **yfinance is always the keyless last resort**, so the app needs zero configuration. Premium providers are only constructed when their key is set, and are built fresh per call (not cached) so a key added mid-process takes effect immediately.
- `yfinance_provider.py` — thin adapter giving the existing `yf_summaries` functions the same shape as premium providers.
- `fmp.py` / `polygon.py` — REST clients over the shared `tools/_http.py` session. `fmp.screener()` exists but is **not yet wired to anything**.

Two independent consumers: the flow's deep-run enrichment (above) and the web layer (portfolio dashboard live pricing, price-rule polling, `price_series.py` chart bars, and `GET /api/watchlist/quotes`). Note `get_batch_quotes` is **Polygon-only** and outside the 8-method Protocol — callers must handle an empty result as a no-op when Polygon isn't configured, not as an error.

### Web UI

A local single-user interface in `src/stock_analysis/web/` — FastAPI backend + no-build vanilla-JS/Chart.js frontend, launched with `python -m stock_analysis.web` (`__main__.py`; reuses `main.py` logging, warns-not-exits on missing keys, `uvicorn` with **`workers=1`**).

**Run serialization is mandatory.** `token_meter`/`llm_budget` are process-global and reset per run, so runs must never overlap. `jobs.py` `JobManager` uses a `ThreadPoolExecutor(max_workers=1)`; a second submit while one is active returns **HTTP 409**. The blocking analysis runs in the worker thread (never the async handler), so `GET /api/jobs/{id}` stays responsive and is **polled every 1s** (not SSE).

- **Live progress** with no new flow plumbing: the status endpoint reads `token_meter.snapshot()` + `llm_budget.used()` directly; `progress.py` registers one persistent CrewAI-event-bus listener (`CrewKickoffCompleteEvent`) forwarding to the active run's `StageTracker`, mapping completed crews → stage label + 0–1 fraction (set-active/clear-active around each run avoids the unsubscribe problem).
- **Cancel / Refresh**: `POST /api/jobs/{id}/cancel` sets a flag + `llm_budget.request_abort()`, making the next `check_and_increment()` raise `AnalysisAbortedError` (cooperative — stops at the next LLM call). `_run()` decides the final state from the **result, not the flag**: a `status: completed` result always wins (a run that finished is finished, even if cancellation raced completion); only an incomplete result with `cancel_requested` is `aborted`, otherwise `failed`. **Refresh** is just `POST /api/analyze` with `use_cache:false` — no separate endpoint.
- **History**: every run writes a `<SYM>_run_status.json` marker so the gallery shows aborted/failed/completed even with no report. Ordering uses a **stable analysis timestamp** (`_analyzed_at`: status marker → newest *data* artifact mtime, excluding the re-render-bumped HTML).
- **Reuse over rebuild**: `routes/results.py` serves the existing self-contained HTML report (iframe-embedded) plus `<SYM>_chart_data.json`; `dashboard.js` builds the interactive Overview from that JSON (ETF reports show fund facts from `chart_data.etf_profile`/`asset_type` instead of stock tiles); `reports_index.py` scans `report_output_dir` for the gallery.
- **Path safety**: `_paths.py` guards every file path with a strict symbol regex + `report_output_dir` containment check (traversal-safe). Use it for any new file-serving route.
- **Live price series**: `price_series.py` is the single source for "N symbols, one period, back from today" — both the report Overview chart (`GET /api/reports/{symbol}/prices?period=&compare=`) and the Compare page (`GET /api/compare/prices`) go through it. It fetches via `ROUTER.get_daily_bars`, caps at `MAX_SYMBOLS` (4), and caches 15 min to bound repeated provider calls on rapid UI toggling. **A symbol the provider chain can't serve is dropped into `omitted`, never a hard error** — one bad ticker must not break a chart showing three good ones. Put any new multi-symbol price fetch here rather than adding a second path.
- **Compare** (`routes/compare.py`, `#/compare`) puts 2–4 arbitrary symbols side by side and **works for symbols that have never been analyzed**: `/api/compare/metrics` fetches key stats + analyst consensus live and in parallel (`_key_metrics` is shared with `yf_summaries`), then `_report_overlay()` best-effort layers sentiment/valuation from an existing `chart_data.json` when there is one. Same omit-don't-error contract as above.
- **Frontend** (`static/`) is a no-build SPA: left-sidebar shell, **light/dark theme** via `[data-theme]` on `<html>` (localStorage + `prefers-color-scheme`), bundled **Inter** font (`static/fonts/`), Chart.js themed live from CSS vars (`util.theme()`). `app.py` sets `Cache-Control: no-cache` on `/static` + `/api/reports` so edits and re-runs show immediately. Shared UI modules — `priceChart.js` (`renderPriceChart`), `chartControls.js` (`periodSelector`, `symbolChipInput`), and `util.js`'s `makeSortable`/`attachSortHeaders`/`debounce` — are reused across dashboard, compare, watchlist, portfolio, and history; extend these rather than re-implementing per view.

#### Persistence

`web/db.py` is a **SQLite** store at `data/app.db` (WAL mode, `busy_timeout=5000`) — tables: `watchlist`, `jobs`, `rec_history`, `alerts_log`, `settings_kv`, `schedules`, `rules`, `transactions`. It is the source of truth; in-memory structures are derived. On startup the FastAPI `lifespan` hook runs `manager.recover()` (resumes jobs still queued when the process last stopped, marks orphaned `running` rows) and a best-effort `backfill_rec_history()` (idempotent; never blocks startup), then `scheduler.start()` / `scheduler.stop()` on shutdown.

#### Portfolio

`tools/portfolio_ledger.py` is **pure functions, no I/O** — keep it that way; DB access belongs in `routes/portfolio.py`.

- **Transactions are the source of truth**: `compute_positions()` re-derives open qty / avg cost / realized P&L (FIFO) from the full transaction list every time; positions are never stored.
- `parse_transactions_csv()` handles broker-export import; `build_value_series()` reconstructs historical value from transaction step-functions × daily closes; `compute_benchmark_comparison()` gives alpha/beta/Sharpe vs. a benchmark (e.g. SPY).
- Routes: CRUD on `/api/portfolio/transactions` (+ `/import`), `/api/portfolio/positions`, `/api/portfolio/dashboard` (live-priced positions, totals, value/benchmark series) — rendered by `static/js/portfolio.js`.
- `PortfolioAnalysisTool.analyze` now defaults to **holdings-derived weights** (`_holdings_weights`) rather than the optimizer when every requested symbol is an open position.

#### Automation

`web/scheduler.py` (APScheduler `BackgroundScheduler`) + `web/rules.py`, CRUD at `/api/schedules` and `/api/rules` (`routes/automation.py`), UI in `static/js/automation.js`.

- **Schedules**: cron-based re-analysis. SQLite is the source of truth; **APScheduler is a stateless executor reloaded on restart**. A schedule fires either a full analysis (queued through the existing single-worker `JobManager` with `origin="scheduled"`) or a `monitor_only` data-only refresh (`_fetch_structured()` directly — **zero LLM calls**). An optional `daily_llm_call_cap` (in `settings_kv`) throttles scheduled-origin runs only.
- **Rules**, two families with different evaluation points:
  - *Price* (`price_above`, `price_below`, `pct_move_day`) — evaluated by a periodic quote-poll job (every 15 min via `ROUTER`), with per-rule cooldown.
  - *Post-run* (`target_price_hit`, `stop_loss_hit`, `recommendation_changed`, `confidence_dropped`) — evaluated from `alerts.check_and_dispatch` right after an analysis completes.
  - Both dispatch through the existing `alerts.py` email/webhook/log machinery.
  - ⚠️ **Known gap**: `earnings_within_days` is accepted by `schemas.py` (and required to carry a threshold) but has **no evaluator in `rules.py`** — such a rule can be created and will silently never fire. Fix the evaluator or reject the type; don't assume it works.
- `GET /api/providers/status` (`routes/providers.py`) reports which of FMP / Polygon / yfinance are configured.

**Tests**: `tests/test_web_*.py` use FastAPI `TestClient` with `analyze_stock` mocked; an autouse fixture points `report_output_dir` at a tmp dir so worker status markers never touch the real `reports/`.

### Data Flow

All data is typed via **Pydantic v2** models in `models/stock_data.py` (`@field_validator` / `@model_validator`, not deprecated `@validator`). There is no unified container class — only models the running code actually consumes are kept: `CompanyInfo`, `MarketData`, `FundamentalData`, `NewsData`, `EconomicData` (built by collectors) and `InvestmentRecommendation` (validated against the advisor's structured output).

Tools in `tools/`:

- `free_data_collection.py` — Yahoo Finance (incl. short interest), SEC EDGAR, FRED (with yfinance market-proxy fallback: VIX/10Y/S&P/WTI/DXY), news with fallback chain (Google News → Bing News → Yahoo per-symbol RSS), DuckDuckGo; parallel fetch via `ThreadPoolExecutor` (`ParallelDataCollectionTool`, which also merges analyst/statements/ownership/social blocks)
- `yf_summaries.py` — compact, prompt-sized summarizers over a shared `yf.Ticker` (analyst consensus, ownership, 3-year statements, options put/call, dividends, ETF portfolio); every accessor guarded, partial results on failure
- `providers/` — pluggable premium/free provider router (see **Market Data Providers**)
- `company_intel.py` — cached tool wrappers: `AnalystDataTool`, `OwnershipTool`, `FinancialStatementsTool`, `OptionsSentimentTool`, `ETFPortfolioTool`
- `social_sentiment.py` — `SocialSentimentTool`: Stocktwits (keyless, labeled bullish/bearish), Reddit (JSON with automatic RSS fallback), CNN Fear & Greed (market-wide); per-source failure isolation with neutral notes (never raw errors), top-level `error` only when **all** sources fail (so total failures aren't cached)
- `analysis_tools.py` — technical indicators (pure pandas/numpy, see `_indicators.py`) and fundamental ratio analysis. Risk/technical scores normalise over **metrics actually present**, never a hardcoded denominator — a missing metric must not read as max or min risk (see `tests/test_risk_signal_bugfixes.py`)
- `calculation_tools.py` — DCF, dividend discount, VaR, Sharpe (annualised); DCF guards `discount_rate <= terminal_growth_rate`
- `portfolio_tools.py` — correlation matrix, portfolio Sharpe/VaR, and true covariance-based SLSQP minimum-variance optimisation (long-only, fully invested), falling back to the inverse-variance proxy only when the optimizer fails to converge; the response's `allocation_method` distinguishes `minimum_variance` from `minimum_variance_proxy`. Wired to the investment advisor
- `portfolio_ledger.py` — FIFO cost basis, CSV import, value/benchmark series (see **Portfolio**)
- `backtest_tools.py` — SMA crossover and RSI-reversion back-tests (wired to the technical analyst)
- `cache.py` — three-tier cache (`@cached_tool()` + `get_cached`/`set_cached`): Redis (shared, authoritative when up) → in-process memory → **filesystem** (`data/.tool_cache/`, survives between CLI invocations). **Never caches error dicts.** With Redis down, reads fall through memory→disk and writes populate both; the disk tier is what lets a same-symbol re-run reuse data cross-process without Redis. A one-time `_sweep_disk_cache` bounds the dir (age cap 7d, count cap 512)
- `_http.py` — shared `requests.Session` (`SESSION`, plus `get`/`post`) with connection pooling, `urllib3 Retry` (2 retries, backoff, on 429/5xx), default 10s timeout. **All tool HTTP traffic goes through it.** Tests patch `tools._http.SESSION.get`, *not* module-level `requests.get`
- `_svg_charts.py` — dependency-free inline SVG line/bar charts
- `report_tools.py` — Jinja2 HTML reports with SVG charts, keyless company logo (Google favicon service), chart data from `{SYM}_chart_data.json` (guarded live fallback); `render_html_report()` is the deterministic LLM-free entry point

Output paths are **anchored to the project root** (`settings.PROJECT_ROOT`): `REPORT_OUTPUT_DIR`, `DATA_OUTPUT_DIR`, and `CREW_LOG_FILE` resolve relative values against the project directory regardless of cwd.

### Configuration

All runtime settings live in `config/settings.py` as a Pydantic `BaseSettings` class.

| Variable | Default | Purpose |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | — | LLM provider credentials |
| `LLM_PROVIDER` | `openai` | Any LiteLLM provider (not whitelisted — see LLM Initialisation) |
| `LLM_MODEL` | `gpt-4o` | Model name |
| `MAX_LLM_CALLS_PER_RUN` | `300` | Hard per-run call cap (safety stop) |
| `LLM_TOKEN_ALERT` | `0` | Warn above N tokens/run; 0 = off |
| `DATA_CACHE_TTL` | `86400` | Structured-fetch bundle TTL; 0 = always re-fetch |
| `FRED_API_KEY` | `demo` | Federal Reserve data (`demo` = rate-limited free access) |
| `SEC_EDGAR_EMAIL` | `contact@example.com` | Required by SEC EDGAR ToS; warns at startup if left at default |
| `FMP_API_KEY` / `POLYGON_API_KEY` | — | **Optional** premium providers; absent = yfinance-only, fully functional |
| `*_ENABLED` flags (e.g. `SEC_EDGAR_ENABLED`) | `true` | Toggle individual data sources on/off |
| `WEB_HOST` / `WEB_PORT` | `127.0.0.1` / `8000` | Local web UI bind address |
| `CREW_LOG_FILE` | `logs/crew_output.log` | Persistent crew execution log |
| `DEBUG` | `false` | Debug mode flag |

### Docker

`docker-compose.yml` runs three services: `app`, `redis` (caching/Celery), `db` (PostgreSQL). Output is written to volume-mounted `data/`, `reports/`, `logs/`.
