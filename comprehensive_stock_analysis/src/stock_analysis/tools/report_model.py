"""One assembled view of a finished run, for whichever renderer wants it.

The HTML report and the PDF previously each reached into `reports/<SYM>/` on
their own and derived their own numbers, which is how a single document came to
quote four different "current prices" and two different analyst counts. This
module reads the artifacts once and resolves every derived figure — price,
upside, valuation range, rating — so both renderers state the same thing by
construction rather than by coincidence.

Reading only. It never fetches, and a missing artifact yields an absent field
rather than an exception: a partial run still has to render.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..config.settings import settings

_logger = logging.getLogger(__name__)


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def split_sections(markdown: str) -> List[Tuple[str, str]]:
    """Split a narrative on its ``## `` headings into (title, body) pairs.

    Content before the first heading is dropped: it is invariably a preamble
    the document does not want.
    """
    parts = re.split(r"^##\s+(.+?)\s*$", markdown or "", flags=re.MULTILINE)
    out: List[Tuple[str, str]] = []
    for i in range(1, len(parts) - 1, 2):
        title, body = parts[i].strip(), parts[i + 1].strip()
        if title and body:
            out.append((title, body))
    return out


class ReportModel:
    """Everything a renderer needs about one symbol's finished run."""

    def __init__(self, symbol: str, asset_type: Optional[str] = None) -> None:
        self.symbol = symbol.upper()
        d = Path(settings.report_output_dir) / self.symbol
        self.dir = d
        self.chart = _read_json(d / f"{self.symbol}_chart_data.json")
        self.rec = _read_json(d / f"{self.symbol}_investment_recommendation.json")
        self.narrative = _read_text(d / f"{self.symbol}_comprehensive_report.md")
        self.asset_type = asset_type or self.chart.get("asset_type") or "stock"

    # ── identity ──────────────────────────────────────────────────────────────

    @property
    def company(self) -> Dict[str, Any]:
        return self.chart.get("company") or {}

    @property
    def name(self) -> str:
        return str(self.company.get("name") or self.symbol)

    @property
    def subtitle(self) -> str:
        bits = [
            self.symbol,
            self.company.get("exchange"),
            self.company.get("industry") or self.company.get("sector"),
        ]
        return " · ".join(str(b) for b in bits if b)

    # ── the one price, and everything derived from it ────────────────────────

    @property
    def snapshot(self) -> Dict[str, Any]:
        return self.chart.get("snapshot") or {}

    @property
    def price(self) -> Optional[float]:
        """The run's authoritative price.

        Prefers the snapshot; falls back to key_stats only for reports written
        before snapshots existed, so old artifacts still render.
        """
        return _num(self.snapshot.get("price")) or _num(
            (self.chart.get("key_stats") or {}).get("current_price")
        )

    @property
    def as_of(self) -> str:
        raw = str(self.snapshot.get("as_of") or self.chart.get("data_fetched_at") or "")
        return raw[:16].replace("T", " ")

    @property
    def target(self) -> Optional[float]:
        return _num(self.rec.get("target_price"))

    @property
    def upside_pct(self) -> Optional[float]:
        p, t = self.price, self.target
        return round((t - p) / p * 100, 1) if p and t else None

    @property
    def rating(self) -> str:
        return str(self.rec.get("recommendation") or "").strip()

    # ── valuation ─────────────────────────────────────────────────────────────

    @property
    def scenarios(self) -> List[Dict[str, Any]]:
        return [
            s
            for s in (self.chart.get("valuation_scenarios") or [])
            if isinstance(s, dict) and _num(s.get("intrinsic_per_share")) is not None
        ]

    @property
    def valuation_range(self) -> Optional[Tuple[float, float]]:
        vals = [float(s["intrinsic_per_share"]) for s in self.scenarios]
        return (min(vals), max(vals)) if vals else None

    @property
    def target_reconciles(self) -> Optional[bool]:
        """Whether the published target sits inside the modelled range.

        None when there is nothing to compare. The renderer surfaces this
        rather than hiding it — a target outside the range is publishable, but
        only alongside the reason.
        """
        rng, t = self.valuation_range, self.target
        return None if not rng or t is None else rng[0] <= t <= rng[1]

    def football_field_bands(self) -> List[Tuple[str, float, float]]:
        """Comparable value ranges, widest context first."""
        bands: List[Tuple[str, float, float]] = []
        ks = self.chart.get("key_stats") or {}
        lo52, hi52 = _num(ks.get("low_52w")), _num(ks.get("high_52w"))
        if lo52 and hi52 and hi52 > lo52:
            bands.append(("52-week range", lo52, hi52))
        pt = (self.chart.get("analyst") or {}).get("price_targets") or {}
        plo, phi = _num(pt.get("low")), _num(pt.get("high"))
        if plo and phi and phi > plo:
            bands.append(("Street targets", plo, phi))
        rng = self.valuation_range
        if rng and rng[1] > rng[0]:
            bands.append(("DCF bear–bull", rng[0], rng[1]))
        return bands

    # ── narrative ─────────────────────────────────────────────────────────────

    @property
    def sections(self) -> List[Tuple[str, str]]:
        return split_sections(self.narrative)

    @property
    def summary(self) -> str:
        """The advisor's plain-English summary, else the opening section."""
        s = str(self.rec.get("summary") or "").strip()
        if s:
            return s
        secs = self.sections
        return secs[0][1] if secs else ""

    def key_stat_tiles(self) -> List[Tuple[str, str]]:
        """The header strip: label/value pairs, already formatted."""
        ks = self.chart.get("key_stats") or {}
        tiles: List[Tuple[str, str]] = []
        if self.rating:
            tiles.append(("Rating", self.rating.upper()))
        if self.target:
            tiles.append(("Target", f"${self.target:,.2f}"))
        if self.price:
            tiles.append(("Price", f"${self.price:,.2f}"))
        if self.upside_pct is not None:
            tiles.append(("Upside", f"{self.upside_pct:+.1f}%"))
        mcap = _num(ks.get("market_cap"))
        if mcap:
            tiles.append(("Market cap", f"${mcap / 1e9:,.1f}B"))
        pe = _num(ks.get("pe_ratio"))
        if pe:
            tiles.append(("P/E", f"{pe:,.1f}x"))
        horizon = str(self.rec.get("time_horizon") or "").strip()
        if horizon:
            tiles.append(("Horizon", horizon))
        risk = str(self.rec.get("risk_level") or "").strip()
        if risk:
            tiles.append(("Risk", risk))
        return tiles

    def peers(self) -> List[Dict[str, Any]]:
        return [p for p in (self.chart.get("peers") or []) if isinstance(p, dict)]

    def catalysts(self) -> List[Tuple[str, str]]:
        c = self.chart.get("catalysts") or {}
        labels = [
            ("next_earnings_date", "Next earnings"),
            ("ex_dividend_date", "Ex-dividend"),
            ("dividend_date", "Dividend paid"),
        ]
        return [(lb, str(c[k])[:10]) for k, lb in labels if c.get(k)]

    def is_renderable(self) -> bool:
        """Enough to produce a document at all."""
        return bool(self.narrative or self.rec or self.chart)
