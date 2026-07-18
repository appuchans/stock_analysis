# Planned Phases

Future work identified during the 2026-06-30 full-codebase review and fix pass, deliberately
left out of scope at the time. Nothing below is fabricated roadmap — each item was explicitly
flagged as a follow-up by the review/fix agents while working the codebase. See `docs/DESIGN.md`
for the architecture these build on.

## Phase 1 — Web UI security hardening

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

## Phase 2 — Remaining zero-value truthy-check bugs

The same class of bug fixed in `analysis_tools.py` (a legitimate `0.0` metric silently
treated as "missing" by an `if value:` check instead of `if value is not None:`) was found
in two more places but explicitly left untouched because they weren't part of the originally
confirmed bug list:

- `RiskAnalysisTool._analyze_credit_risk` / `_analyze_liquidity_risk` /
  `_analyze_operational_risk` (`tools/analysis_tools.py`) still use a
  `fundamental_data.get(...) or 0` pattern, which has the identical failure mode as the
  bugs already fixed elsewhere in this file.
- `TechnicalAnalysisTool._generate_signals`'s `neutral_signals = 4 - buy_count - sell_count`
  still assumes all 4 indicator groups are always evaluated. If an indicator is genuinely
  missing (`None`, not `0.0`), it's silently excluded from `buy_count`/`sell_count` but
  `neutral_signals` doesn't account for that, slightly overstating the neutral count. This is
  a distinct (smaller) bug from the truthy-check issue already fixed in this method.

## Phase 3 — Dev tooling housekeeping

- `black`, `isort`, `flake8`, and `mypy` are declared in `pyproject.toml`'s `dev` extra but
  were **not actually installed** in the working `.venv` when this review ran — `pip install
  -e ".[dev]"` had not been (re-)synced. `CLAUDE.md`'s documented lint commands silently don't
  work until that's done. Worth a `make setup` / CI check that fails loudly if the dev venv
  drifts from `pyproject.toml`, rather than discovering it mid-review.
- The README states style/type checks run as **advisory** steps in CI (not blocking). Revisit
  once the codebase has been run through `black`/`isort` at least once cleanly — right now a
  full-repo `black` run produces a very large diff (the codebase predates black adoption),
  so this can't be flipped to blocking without a dedicated one-time reformatting pass done in
  its own commit, separate from any functional change.
