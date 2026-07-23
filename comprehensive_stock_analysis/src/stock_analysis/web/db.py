"""SQLite persistence for the local single-user app.

One database file (``data/app.db``, WAL mode) holds every bit of app *state*
that must outlive a process: the watchlist, the job queue/history, per-run
recommendation snapshots, the alert log, user-defined alert rules, and a small
key/value settings store. Report *content* stays on the filesystem — this DB
only holds index/state.

Connections are opened per call (never shared across threads) so the worker
thread and the asyncio event loop can both touch the DB safely; WAL mode keeps
their reads/writes from blocking each other.
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..config.settings import settings

_initialized: bool = False


def _db_path() -> Path:
    return Path(settings.data_output_dir) / "app.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist (
    symbol   TEXT PRIMARY KEY,
    added_at TEXT NOT NULL,
    notes    TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS jobs (
    id            TEXT PRIMARY KEY,
    symbol        TEXT NOT NULL,
    depth         TEXT NOT NULL,
    asset_type    TEXT NOT NULL,
    use_cache     INTEGER NOT NULL DEFAULT 1,
    origin        TEXT NOT NULL DEFAULT 'manual',
    state         TEXT NOT NULL DEFAULT 'queued',
    stage         TEXT,
    error         TEXT,
    company_name  TEXT,
    progress      REAL DEFAULT 0.0,
    llm_calls     INTEGER DEFAULT 0,
    total_tokens  INTEGER DEFAULT 0,
    created_at    TEXT NOT NULL,
    started_at    TEXT,
    finished_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_state   ON jobs(state);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);
CREATE TABLE IF NOT EXISTS rec_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol         TEXT NOT NULL,
    recorded_at    TEXT NOT NULL,
    recommendation TEXT,
    target_price   REAL,
    stop_loss      REAL,
    confidence     REAL,
    price_at_rec   REAL,
    UNIQUE(symbol, recorded_at)
);
CREATE INDEX IF NOT EXISTS idx_rec_symbol ON rec_history(symbol);
CREATE TABLE IF NOT EXISTS alerts_log (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol             TEXT NOT NULL,
    fired_at           TEXT NOT NULL,
    reason             TEXT NOT NULL,
    old_recommendation TEXT,
    new_recommendation TEXT,
    old_confidence     REAL,
    new_confidence     REAL
);
CREATE INDEX IF NOT EXISTS idx_alerts_fired ON alerts_log(fired_at);
CREATE TABLE IF NOT EXISTS settings_kv (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def init_db() -> None:
    """Create all tables if they do not exist (idempotent)."""
    global _initialized
    if _initialized:
        return
    _db_path().parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.executescript(_SCHEMA)
        conn.commit()
    _import_legacy_watchlist()
    _initialized = True


def _import_legacy_watchlist() -> None:
    """One-time migration of a pre-consolidation ``watchlist.db`` into app.db.

    Best-effort: if the legacy file exists and the new watchlist table is
    empty, copy its rows across so a user's saved symbols survive the switch.
    """
    legacy = _db_path().parent / "watchlist.db"
    if not legacy.exists() or legacy == _db_path():
        return
    try:
        with _connect() as conn:
            if conn.execute("SELECT 1 FROM watchlist LIMIT 1").fetchone():
                return  # already populated — don't clobber
            src = sqlite3.connect(legacy, timeout=10)
            try:
                src.row_factory = sqlite3.Row
                rows = src.execute("SELECT symbol, added_at, notes FROM watchlist").fetchall()
            finally:
                src.close()
            for r in rows:
                conn.execute(
                    "INSERT OR IGNORE INTO watchlist (symbol, added_at, notes) VALUES (?, ?, ?)",
                    (r["symbol"], r["added_at"], r["notes"]),
                )
            conn.commit()
    except sqlite3.Error:
        pass  # legacy import is best-effort; never block startup


def _ensure() -> None:
    if not _initialized:
        init_db()


# ── Watchlist ────────────────────────────────────────────────────────────────
def add_symbol(symbol: str, notes: str = "") -> bool:
    """Insert *symbol*. Returns True if newly inserted, False if it existed."""
    _ensure()
    with _connect() as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, added_at, notes) VALUES (?, ?, ?)",
            (symbol, _now_iso(), notes),
        )
        conn.commit()
        return cursor.rowcount == 1


def remove_symbol(symbol: str) -> bool:
    """Delete *symbol*. Returns True if it was present."""
    _ensure()
    with _connect() as conn:
        cursor = conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        conn.commit()
        return cursor.rowcount == 1


def list_symbols() -> List[Dict[str, str]]:
    """Return all watchlist entries, newest first."""
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT symbol, added_at, notes FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def symbol_exists(symbol: str) -> bool:
    _ensure()
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM watchlist WHERE symbol = ?", (symbol,)).fetchone()
    return row is not None


# ── Jobs ─────────────────────────────────────────────────────────────────────
def upsert_job(job: Dict[str, Any]) -> None:
    """Insert or update a job row from a plain dict (best-effort persistence)."""
    _ensure()
    cols = (
        "id", "symbol", "depth", "asset_type", "use_cache", "origin", "state",
        "stage", "error", "company_name", "progress", "llm_calls", "total_tokens",
        "created_at", "started_at", "finished_at",
    )
    values = [job.get(c) for c in cols]
    placeholders = ", ".join("?" for _ in cols)
    updates = ", ".join(f"{c}=excluded.{c}" for c in cols if c != "id")
    with _connect() as conn:
        conn.execute(
            f"INSERT INTO jobs ({', '.join(cols)}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {updates}",
            values,
        )
        conn.commit()


def list_jobs(limit: int = 50) -> List[Dict[str, Any]]:
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def queued_jobs() -> List[Dict[str, Any]]:
    """Jobs still queued at startup — candidates to resume, oldest first."""
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE state = 'queued' ORDER BY created_at ASC"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_orphaned_running() -> int:
    """A row left in 'running' means the process died mid-run: mark interrupted."""
    _ensure()
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE jobs SET state = 'interrupted', finished_at = ? "
            "WHERE state = 'running'",
            (_now_iso(),),
        )
        conn.commit()
        return cursor.rowcount


# ── Recommendation history ───────────────────────────────────────────────────
def record_recommendation(
    symbol: str,
    recorded_at: str,
    recommendation: Optional[str],
    target_price: Optional[float],
    stop_loss: Optional[float],
    confidence: Optional[float],
    price_at_rec: Optional[float],
) -> None:
    """Append a recommendation snapshot (idempotent on symbol+timestamp)."""
    _ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO rec_history "
            "(symbol, recorded_at, recommendation, target_price, stop_loss, "
            " confidence, price_at_rec) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (symbol, recorded_at, recommendation, target_price, stop_loss,
             confidence, price_at_rec),
        )
        conn.commit()


def list_rec_history(symbol: str) -> List[Dict[str, Any]]:
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM rec_history WHERE symbol = ? ORDER BY recorded_at ASC",
            (symbol,),
        ).fetchall()
    return [dict(r) for r in rows]


# ── Alert log ────────────────────────────────────────────────────────────────
def append_alert(entry: Dict[str, Any]) -> None:
    _ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO alerts_log "
            "(symbol, fired_at, reason, old_recommendation, new_recommendation, "
            " old_confidence, new_confidence) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                entry.get("symbol", ""),
                entry.get("fired_at", _now_iso()),
                entry.get("reason", ""),
                entry.get("old_recommendation"),
                entry.get("new_recommendation"),
                entry.get("old_confidence"),
                entry.get("new_confidence"),
            ),
        )
        conn.commit()


def list_alerts(limit: int = 200) -> List[Dict[str, Any]]:
    _ensure()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts_log ORDER BY fired_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# ── Settings key/value ───────────────────────────────────────────────────────
def get_setting(key: str) -> Optional[str]:
    _ensure()
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings_kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_setting(key: str, value: Optional[str]) -> None:
    _ensure()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings_kv (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()


def all_settings() -> Dict[str, str]:
    _ensure()
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings_kv").fetchall()
    return {r["key"]: r["value"] for r in rows}


try:
    init_db()
except Exception:
    pass
