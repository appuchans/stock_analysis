# Design Document — Comprehensive Stock Analysis

This document captures the *why* behind the architecture: goals, components, data flow, and
the key decisions that shaped the system. It is a living document — update it when a
design decision changes, not just when code changes. For operational quick-reference
(commands, file locations, non-obvious implementation facts), see `/CLAUDE.md` at the repo
root. For planned future work, see `docs/PHASES.md`.

## Goals

- Produce equity/ETF research reports (technical, fundamental, risk, sentiment, ownership,
  macro) using only **free, keyless data sources** — no paid market-data subscription required,
  only an LLM API key.
- Keep numeric facts (prices, ratios, ratings, statements) **deterministic and LLM-free** —
  the LLM narrates and synthesizes, it never originates a number. This is the difference
  between a report you can audit and one you can't.
- Make runaway cost/looping structurally impossible, not just discouraged — a bug in a
  prompt, a framework retry storm, or a hung tool call should have a hard ceiling on both
  wall-clock time and dollars spent, enforced in code that no agent behavior can bypass.
- Support both a CLI (batch-friendly, scriptable) and a local single-user web UI (interactive,
  live progress) against the exact same analysis engine — no duplicated business logic.

## System Context

Two entry points, one engine:

```
CLI (main.py)  ─┐
                 ├─▶ StockAnalysisApp.analyze_stock ─▶ StockAnalysisFlow ─▶ report + recommendation
Web UI (jobs.py)─┘
```

The web UI is a thin, serialized wrapper around the same `analyze_stock` call the CLI makes —
it does not reimplement analysis logic, only job queuing, progress polling, and report
browsing. This was a deliberate choice after an earlier design (a second, sequential
CrewAI crew) was found to duplicate the flow with lossy LLM-forwarded data; it was removed
in favor of a single pipeline.

## Components

### 1. Data collection (`tools/free_data_collection.py`, `tools/yf_summaries.py`, `tools/social_sentiment.py`, `tools/company_intel.py`)

One shared `yf.Ticker` feeds a set of independent summarizer functions in parallel
(`ThreadPoolExecutor`), each producing a compact, prompt-sized JSON block: analyst
consensus, ownership, 3-year financial statements, options positioning, ETF portfolio,
social sentiment (Stocktwits/Reddit/Fear&Greed), news (with a source fallback chain), SEC
filings, and FRED macro data (with a yfinance market-proxy fallback). Every accessor is
individually guarded so one field's failure never drops the whole block — partial data
beats no data, and reports are instructed to disclose gaps rather than fabricate.

All outbound HTTP goes through one shared, retrying, connection-pooled `requests.Session`
(`tools/_http.py`), so a single flaky endpoint degrades gracefully instead of hanging a
whole analysis stage.

### 2. Caching (`tools/cache.py`)

Three tiers, tried by locality: **Redis** (shared/authoritative when reachable) → **in-process
memory** → **filesystem** (survives across CLI invocations without Redis). Individual tool
results are cached with source-appropriate TTLs (news 30 min, options 1 h, statements 24 h);
error dicts are never cached, so a transient failure doesn't poison the cache for its TTL
window. On top of per-tool caching, the *entire* structured data fetch for a symbol is cached
as one bundle for 24 h, so re-analyzing the same ticker same-day skips network collection
entirely — this is the dominant cross-run cost optimization, not the per-tool tier.

### 3. Multi-agent pipeline (`crew/flow_crew.py`, `agents/`, `config/`)

Built on CrewAI 1.x's **Flow** API (`@start`/`@listen`/`@router`/`or_()`), not the older
sequential-Crew pattern — this gives explicit control over which stages run concurrently
and which depend on which, versus a Crew's implicit task-list ordering.

- **Depth routing**: `--depth quick|standard|deep` selects which of the 9 specialist stages
  run (`_stages_for`). Independent stages execute concurrently, each as its own mini-Crew
  (own agent, own task, own LLM budget accounting), capped by `MAX_WORKERS`.
- **Deterministic data injection**: the structured data collected in step 1 is passed
  verbatim into each stage's prompt as a side-channel variable (`{analyst_data}`,
  `{financials_data}`, …) — never paraphrased by an intermediate LLM call. This is the
  mechanism that makes the "no LLM-originated numbers" goal actually hold in practice.
  The synthesis stages (recommendation, report) subsequently reference the specialist
  stages' own text output rather than the raw structured data.
  - **`StockAnalysisState` is fully reset before every `kickoff()`** — all nine per-stage
    result fields, not just the terminal ones — because a `StockAnalysisFlow` instance is
    reused across a batch CLI run, and any field left over from a prior symbol's run would
    silently leak into the next symbol's synthesis if that symbol's stage set skips it
    (e.g. an ETF has no `ownership` stage).
- **Configuration lives in YAML, not Python**: agent roles/goals/backstories
  (`config/agents.yaml`) and every stage prompt (`config/flow_tasks.yaml`) are data, not
  code — an agent `.py` file's only job is `_get_tools()`. This keeps prompt iteration a
  content change, not a code change, and keeps the Python layer reviewable independent of
  prompt wording.
- **Report generation is deterministic-first, LLM-second**: the final HTML report is always
  rendered in code (`render_html_report`) from state that exists regardless of whether the
  narrative-writing LLM call succeeds — a guardrail failure or budget exhaustion during
  narrative generation degrades the report's prose, it does not delete the report. The same
  applies to the recommendation stage: a failed recommendation crew is caught and logged
  rather than aborting the flow, so a report still renders with an N/A rating instead of zero
  artifact.

### 4. Safety & observability (`llm_budget.py`, `token_meter.py`, `preflight_llm_credentials`)

Three independent layers, deliberately not merged into one mechanism:

| Layer | Question it answers | Enforcement point |
|---|---|---|
| Credential preflight | "Will this run be able to call its LLM at all?" | Before any work starts (~1s) |
| LLM call budget | "Has this run made too many LLM calls?" | Inside every `LLM.call`/`acall`, before the network request |
| Token meter | "How much did this run actually cost?" | After each crew completes; alert-only, not a stop |

The budget is a hard ceiling enforced at the lowest possible layer (the LLM client wrapper
itself) specifically so that no higher-level bug — a bad prompt, a framework retry, an
agent stuck re-planning — can bypass it by construction. It exists because a prior incident
(reasoning mode's schema bug) burned ~8,000 LLM calls in one run before this cap existed.

### 5. Web UI (`web/`)

FastAPI + a no-build vanilla-JS SPA, run with `uvicorn --workers 1`. The single-worker
constraint is not a scalability afterthought — `token_meter` and `llm_budget` are
process-global by design (see above), so this app can only ever run one analysis at a time
per process, and the whole web layer (`JobManager`'s single-worker queue, HTTP 409 on
overlap, cooperative cancellation) exists to make that constraint safe and legible rather
than to work around it. Cancellation is cooperative (checked at the next LLM call) rather
than preemptive, trading a small latency for never leaving the process in a half-torn-down
state; the job's final status is derived from whether the analysis actually completed, not
from whether cancellation was requested, so a race between "cancel" and "finished" can never
mislabel a successful report as aborted.

## Data Flow (single analysis)

```
symbol ─▶ collect_data (parallel structured fetch, cache-aware)
       ─▶ route by depth
       ─▶ N specialist stages (parallel mini-Crews, data injected verbatim)
       ─▶ synthesize_recommendation (Pydantic-validated structured output)
       ─▶ generate_report (LLM narrative + deterministic HTML render)
       ─▶ {report, recommendation, token_usage, llm_calls, status}
```

## Testing Strategy

The suite (`tests/`) is network-free — every external call is mocked at the shared-session
boundary (`tools._http.SESSION`) rather than per-library, so the mocking surface stays small
as data sources are added or changed. Web UI tests use FastAPI's `TestClient` with
`analyze_stock` mocked and an autouse fixture redirecting output paths to a temp directory,
so tests never touch real report/cache state on disk.

## Known Limitations (by design, for now)

- **No authentication** on the web UI — it's built for local, single-user use on
  `127.0.0.1`. Exposing it beyond localhost changes the threat model; see `docs/PHASES.md`.
- **Single analysis at a time**, by construction (see §5). Horizontal scaling would require
  making `token_meter`/`llm_budget` per-run instead of process-global, which is a real
  redesign, not a config change.
- **`ollama` and other local providers** skip credential preflight entirely (no key to
  check) — a misconfigured local endpoint still fails inside the flow, not before it.
