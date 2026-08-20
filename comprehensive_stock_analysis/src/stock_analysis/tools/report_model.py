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
    def price_label(self) -> str:
        """How the price must be described, in words the reader can trust.

        The fetch timestamp is not the price date. Labelling a settled close
        "as of 2026-08-19 15:42" states the figure is an hour old when it is a
        prior-session close, and mid-session the two genuinely disagree.
        """
        date = str(self.snapshot.get("price_date") or "")[:10]
        basis = str(self.snapshot.get("price_basis") or "").strip()
        if date and basis:
            return f"{basis.capitalize()} {date}"
        if date:
            return f"Close {date}"
        return f"As of {self.as_of}" if self.as_of else ""

    # A house target more than this far from the traded price is a unit, share
    # class or sign error rather than a view: GOOG printed $55.78 against a
    # $341 close and carried a Hold.
    _TARGET_PRICE_BAND = (0.4, 3.0)

    @property
    def target(self) -> Optional[float]:
        """The house target, or None when it cannot be defended.

        Suppressed rather than printed when it is implausible against the
        traded price. A note with no house target and a stated margin-of-safety
        view is publishable; a note asserting a price one-sixth of the tape is
        not, and no amount of surrounding prose repairs it. Withholding is also
        what a reviewer asked for: kill the number, do not swap it for the
        Street's.
        """
        raw = _num(self.rec.get("target_price"))
        price = _num(self.snapshot.get("price")) or _num(
            (self.chart.get("key_stats") or {}).get("current_price")
        )
        if raw is None or not price or price <= 0:
            return raw
        lo, hi = self._TARGET_PRICE_BAND
        if not lo <= raw / price <= hi:
            _logger.warning(
                "%s: target %.2f vs price %.2f is outside the defensible band; "
                "publishing no house target",
                self.symbol,
                raw,
                price,
            )
            return None
        return raw

    @property
    def target_withheld(self) -> bool:
        """Whether a target existed but was suppressed, so the note can say so."""
        return _num(self.rec.get("target_price")) is not None and self.target is None

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

    @property
    def target_bridge_required(self) -> bool:
        """Whether the target needs an explanation the note may not have given.

        True when a published target sits outside the modelled range, or lands
        on the consensus mean while the model says something different. Both
        are publishable — with the bridging assumption stated. Neither is
        publishable silently, which is what "the alignment with Street is a
        cross-check rather than the basis" amounted to when the target was the
        Street mean to within sixteen cents.
        """
        if self.target is None:
            return False
        rng = self.valuation_range
        if rng and not rng[0] <= self.target <= rng[1]:
            return True
        mean = ((self.chart.get("analyst") or {}).get("price_targets") or {}).get(
            "mean"
        )
        if isinstance(mean, (int, float)) and mean:
            # Within 1% of consensus is an echo, not an independent view.
            if abs(self.target - mean) / mean < 0.01 and rng:
                base = next(
                    (
                        s["intrinsic_per_share"]
                        for s in self.scenarios
                        if str(s.get("scenario", "")).lower() == "base"
                    ),
                    None,
                )
                if base and abs(self.target - base) / base > 0.05:
                    return True
        return False

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
        return split_sections(self._readable_narrative())

    # "with a **$325.0 target price**", "target price of $325.0", "$325.0
    # target price", "target of $325" — including a leading article and
    # markdown emphasis markers on either side of the figure, all consumed in
    # one match so the replacement never leaves an orphaned "**" or "a".
    _TARGET_CLAIM = re.compile(
        r"\b(?:a|an)\s+\**(?:price\s+)?target(?:\s+price)?\s+(?:of\s+)?"
        r"\**\$\s?[\d,]+(?:\.\d+)?\**"
        r"|\**(?:price\s+)?target(?:\s+price)?\s+(?:of\s+)?"
        r"\**\$\s?[\d,]+(?:\.\d+)?\**"
        r"|\b(?:a|an)\s+\**\$\s?[\d,]+(?:\.\d+)?\**\s+(?:price\s+)?"
        r"target(?:\s+price)?\**"
        r"|\**\$\s?[\d,]+(?:\.\d+)?\**\s+(?:price\s+)?target(?:\s+price)?\**",
        re.IGNORECASE,
    )

    @property
    def prose_asserts_a_target(self) -> bool:
        """Whether the narrative names a target the document does not publish.

        The advisor declined to set one — target_price was null, and the cover
        correctly showed no target tile — while the narrative wrote "$325.0
        target price" twice, taken from the consensus median it had printed a
        page earlier. The prose is published unchecked, so a refusal upstream
        does not reach the reader.
        """
        return self.target is None and bool(self._TARGET_CLAIM.search(self.narrative))

    def _readable_narrative(self) -> str:
        """The narrative with a withheld target removed from the prose.

        Suppressing the target tile while the text still says "Target price:
        $55.78" is worse than either alone — page one then contradicts itself
        in consecutive paragraphs. The figure is known exactly, so the edit is
        a literal replacement rather than an attempt to rewrite the sentence.
        """
        text = self.narrative
        # No target published, but the prose names one anyway: strike the claim
        # in one pass, article and emphasis markers included, rather than
        # letting the document contradict its own cover.
        if self.target is None:
            text = self._TARGET_CLAIM.sub("no published price target", text)
        raw = _num(self.rec.get("target_price"))
        if not self.target_withheld or raw is None:
            return text
        for pattern in (
            rf"\$\s*{raw:,.2f}",
            rf"\$\s*{raw:.2f}",
            rf"\$\s*{raw:,.0f}\b",
        ):
            text = re.sub(pattern, "no published target", text)
        return text

    @property
    def summary(self) -> str:
        """The advisor's plain-English summary, else the opening section."""
        s = str(self.rec.get("summary") or "").strip()
        if self.target_withheld:
            raw = _num(self.rec.get("target_price"))
            if raw is not None:
                s = re.sub(rf"\$\s*{raw:,.2f}|\$\s*{raw:.2f}", "no published target", s)
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
            # Labelled because it is a market-data TTM multiple, not the ratio
            # a reader gets by dividing the fiscal-year figures in the
            # financials section: Amazon shows 21.0x TTM against 36.3x on
            # FY2025 earnings.
            tiles.append(("P/E (TTM)", f"{pe:,.1f}x"))
        horizon = str(self.rec.get("time_horizon") or "").strip()
        if horizon:
            tiles.append(("Horizon", horizon))
        risk = str(self.rec.get("risk_level") or "").strip()
        if risk:
            tiles.append(("Risk", risk))
        # The appendix defines a confidence scale; nothing printed the value it
        # scores until this tile — the figure existed only in the HTML view's
        # separate raw-reasoning block, so the PDF carried a scale with
        # nothing on it to read against.
        conf = self.rec.get("confidence")
        if isinstance(conf, (int, float)):
            tiles.append(("Confidence", f"{conf * 100:.0f}%"))
        return tiles

    def peers(self) -> List[Dict[str, Any]]:
        return [p for p in (self.chart.get("peers") or []) if isinstance(p, dict)]

    def catalysts(self) -> List[Tuple[str, str]]:
        """Dated events still ahead of the note's own as-of date.

        A calendar is a forward-looking exhibit. yfinance returns the last
        ex-dividend date as readily as the next one, so an IBM note dated
        19 August listed an ex-dividend of 9 August — ten days past — under
        "Calendar", which tells the reader nothing and undermines the rest.
        """
        c = self.chart.get("catalysts") or {}
        labels = [
            ("next_earnings_date", "Next earnings"),
            ("ex_dividend_date", "Ex-dividend"),
            ("dividend_date", "Dividend paid"),
        ]
        cutoff = (self.snapshot.get("price_date") or self.as_of or "")[:10]
        out = []
        for key, label in labels:
            value = str(c.get(key) or "")[:10]
            if value and (not cutoff or value >= cutoff):
                out.append((label, value))
        return out

    def is_renderable(self) -> bool:
        """Enough to produce a document at all."""
        return bool(self.narrative or self.rec or self.chart)
