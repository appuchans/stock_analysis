# Planned Phases

Future work identified during the 2026-06-30 full-codebase review and fix pass, deliberately
left out of scope at the time. Nothing below is fabricated roadmap — each item was explicitly
flagged as a follow-up by the review/fix agents while working the codebase. See `docs/DESIGN.md`
for the architecture these build on.

> **Note on numbering:** these phases are unrelated to the `Phase 1/2/3` commit series in git
> history (persistent job queue → provider router/portfolio/automation → tool telemetry). That
> was a separate workstream that has shipped.

**Status as of 2026-08-11** (verified against code, not assumed):

| Phase | Status |
|---|---|
| 1 — Web UI security hardening | **Not started (0/3).** Deferred: feature work comes first before shipping. |
| 2 — Zero-value truthy checks | **Done (2/2)** — but the same bug class survives in unlisted methods, see below. |
| 3 — Dev tooling housekeeping | **Partially done** — formatting resolved and now blocking in CI; flake8/mypy still open. |

## Phase 1 — Web UI security hardening — ⬜ NOT STARTED

**Deliberately deferred** (2026-08-11): more features are going in before shipping, and every
item below is conditional on the local-single-user assumption changing, which it hasn't.
Revisit before any deployment that binds off-loopback or exposes the settings endpoint.


The web UI is currently designed for local, single-user use only (`127.0.0.1`, no auth — see
`docs/DESIGN.md`'s Known Limitations). This phase is for if/when that assumption needs to
change.

- **Full SSRF protection for the alert webhook URL.** The current fix only validates the URL
  scheme is `http`/`https`. It does not block loopback/private/link-local IP ranges, so a
  webhook URL pointed at internal infrastructure would still be reachable from
  `alerts.py::_send_webhook`. Needed if the settings endpoint is ever exposed to less-trusted
  input than "the single local user."
- **Authentication layer**, if the app is ever bound to `0.0.0.0`/a non-loopback host instead
  of `127.0.0.1`. Today `WEB_HOST` has no guard preventing this misconfiguration, and nothing
  in the app would notice.
- **Validate the remaining `AlertSettingsRequest` fields** (`alert_email`, `alert_smtp_host`,
  `alert_smtp_port`, `alert_smtp_user`) — only `alert_webhook_url` got a format validator in
  the last pass. A malformed SMTP host/port currently fails silently inside `_send_email`'s
  broad `except Exception`.

## Phase 2 — Remaining zero-value truthy-check bugs — ✅ DONE

The same class of bug fixed in `analysis_tools.py` (a legitimate `0.0` metric silently
treated as "missing" by an `if value:` check instead of `if value is not None:`) was found
in two more places. Both are now fixed:

- ✅ `RiskAnalysisTool._analyze_credit_risk` / `_analyze_liquidity_risk` /
  `_analyze_operational_risk` (`tools/analysis_tools.py`) now read via plain
  `fundamental_data.get(...)` and guard each metric with `if x is not None`. The
  `or 0` pattern is gone from all three.
- ✅ `TechnicalAnalysisTool._generate_signals` now computes
  `neutral_signals = evaluated_groups - buy_count - sell_count`, so a genuinely missing
  indicator no longer inflates the neutral count.

### Still open: the same bug class in methods that were never enumerated

The original list only covered the three risk methods. `or 0` is still live in roughly nine
other spots in `tools/analysis_tools.py` — valuation and peer-comparison code around
`current_price`, `net_income`, `pe_ratio`, `total_assets`, `total_liabilities`. Identical
failure mode: a real `0` reads as "missing". Worth a sweep of the whole file rather than
another enumerated list, since enumerating is what let these slip the first time.

## Phase 3 — Dev tooling housekeeping — 🟡 PARTIALLY DONE

- ✅ **The one-time reformatting pass is done.** `black` + `isort` were run across `src/` and
  `tests/` in a dedicated commit with no functional change (80 files, +2906/−1228; suite
  unchanged at 467 passed). `black --check` and `isort --check-only` now pass clean on all
  111 files.
- ✅ **black and isort are now blocking in CI**, with versions pinned (`black==26.5.1`,
  `isort==8.0.1`) so an unpinned formatter release can't fail the build on a version bump
  alone. Bump those pins deliberately and reformat in the same PR.
- 🟡 **Dev venv drift is only partly resolved.** `black`, `isort`, and `flake8` are now
  installed in the working `.venv`; **`mypy` still is not**, so `mypy src/` from `CLAUDE.md`
  fails locally even though CI installs it. There is still no `make setup` or CI check that
  fails loudly when the dev venv drifts from `pyproject.toml`'s `dev` extra.
- ⬜ **flake8 and mypy remain advisory** (`continue-on-error: true`). flake8 reports ~204
  findings (down from 478 — the reformat absorbed the rest) and mypy has never been run
  clean. Each can be promoted to blocking independently once its backlog is cleared.
