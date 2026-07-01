"""SQLite persistence for the watchlist (single-user, synchronous)."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from ..config.settings import settings

_initialized: bool = False


def _db_path() -> Path:
    return Path(settings.data_output_dir) / "watchlist.db"


def init_db() -> None:
    """Create the watchlist table if it does not exist."""
    global _initialized
    if _initialized:
        return
    _db_path().parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_db_path()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                symbol   TEXT PRIMARY KEY,
                added_at TEXT NOT NULL,
                notes    TEXT DEFAULT ''
            )
            """)
        conn.commit()
    _initialized = True


def _ensure() -> None:
    if not _initialized:
        init_db()


def add_symbol(symbol: str, notes: str = "") -> bool:
    """Insert *symbol* into the watchlist.

    Returns True if the row was newly inserted, False if it already existed.
    """
    _ensure()
    added_at = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(_db_path()) as conn:
        cursor = conn.execute(
            "INSERT OR IGNORE INTO watchlist (symbol, added_at, notes) VALUES (?, ?, ?)",
            (symbol, added_at, notes),
        )
        conn.commit()
        return cursor.rowcount == 1


def remove_symbol(symbol: str) -> bool:
    """Delete *symbol* from the watchlist.

    Returns True if the row was found and deleted, False if it was not present.
    """
    _ensure()
    with sqlite3.connect(_db_path()) as conn:
        cursor = conn.execute("DELETE FROM watchlist WHERE symbol = ?", (symbol,))
        conn.commit()
        return cursor.rowcount == 1


def list_symbols() -> List[Dict[str, str]]:
    """Return all watchlist entries ordered by *added_at* descending."""
    _ensure()
    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT symbol, added_at, notes FROM watchlist ORDER BY added_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def symbol_exists(symbol: str) -> bool:
    _ensure()
    with sqlite3.connect(_db_path()) as conn:
        row = conn.execute("SELECT 1 FROM watchlist WHERE symbol = ?", (symbol,)).fetchone()
    return row is not None


try:
    init_db()
except Exception:
    pass
