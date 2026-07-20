"""Path helpers with a containment guard against directory traversal."""

from pathlib import Path
from typing import Optional

from ..config.settings import settings
from ..symbols import safe_symbol


def reports_root() -> Path:
    return Path(settings.report_output_dir).resolve()


def _inside_reports(p: Path) -> bool:
    try:
        p.resolve().relative_to(reports_root())
        return True
    except (ValueError, OSError):
        return False


def report_dir(symbol: str) -> Optional[Path]:
    sym = safe_symbol(symbol)
    if not sym:
        return None
    d = reports_root() / sym
    return d if _inside_reports(d) else None


def html_path(symbol: str) -> Optional[Path]:
    d = report_dir(symbol)
    sym = safe_symbol(symbol)
    return d / "html" / f"{sym}_report.html" if d else None


def chart_path(symbol: str) -> Optional[Path]:
    d = report_dir(symbol)
    sym = safe_symbol(symbol)
    return d / f"{sym}_chart_data.json" if d else None


def recommendation_path(symbol: str) -> Optional[Path]:
    d = report_dir(symbol)
    sym = safe_symbol(symbol)
    return d / f"{sym}_investment_recommendation.json" if d else None


def prev_recommendation_path(symbol: str) -> Optional[Path]:
    d = report_dir(symbol)
    sym = safe_symbol(symbol)
    return d / f"{sym}_investment_recommendation_prev.json" if d else None


def status_path(symbol: str) -> Optional[Path]:
    d = report_dir(symbol)
    sym = safe_symbol(symbol)
    return d / f"{sym}_run_status.json" if d else None
