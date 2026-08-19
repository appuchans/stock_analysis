"""Research-grade exhibits as self-contained SVG, rendered with matplotlib.

Why matplotlib rather than the hand-rolled ``_svg_charts``: the exhibits a
research note needs — a football field, a scatter with a size dimension, a
grouped bar with a legend — are exactly what that module has no primitives for,
and hand-rolling legends and axis scaling is reimplementing this library badly.

Two properties matter for how these are consumed:

* **Text is emitted as paths** (``svg.fonttype = "path"``). The same SVG is
  inlined into the HTML report and embedded by the Typst PDF; as paths it
  renders identically in both without either needing the font installed.
* **The palette is the frontend's palette** (``static/js/util.js`` ``theme()``).
  Server-rendered charts and the Chart.js dashboard previously drew the same
  data in two different colour schemes, so one report disagreed with itself
  visually as well as numerically.

Every function returns an SVG string, or ``""`` when the inputs cannot make an
honest chart. Callers treat empty as "omit this exhibit" — never as an error.
"""

import io
import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")  # no display; must precede pyplot
import matplotlib.pyplot as plt  # noqa: E402

_logger = logging.getLogger(__name__)

# Mirrors static/js/util.js theme(). Keep the two in step — they render the
# same numbers side by side in the UI.
ACCENT = "#2563eb"
ACCENT_2 = "#3b82f6"
POS = "#15803d"
NEG = "#b91c1c"
WARN = "#b45309"
TEXT = "#4a5a70"
FAINT = "#8a98ab"
GRID = "#e6eaf1"
INK = "#1f2937"
SERIES = (
    "#2563eb",
    "#16a34a",
    "#d97706",
    "#7c3aed",
    "#dc2626",
    "#0891b2",
    "#db2777",
    "#65a30d",
    "#ea580c",
    "#475569",
)

_BASE_RC = {
    "svg.fonttype": "path",
    "font.size": 8.5,
    "text.color": TEXT,
    "axes.edgecolor": GRID,
    "axes.labelcolor": TEXT,
    "axes.titlesize": 9.5,
    "axes.titleweight": "bold",
    "axes.titlecolor": INK,
    "xtick.color": TEXT,
    "ytick.color": TEXT,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "figure.dpi": 100,
}


def _fig(width: float, height: float):
    """A figure with the house style applied and the top/right spines gone."""
    fig, ax = plt.subplots(figsize=(width, height))
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.tick_params(length=0)
    return fig, ax


def _to_svg(fig) -> str:
    """Serialize and close, returning the ``<svg>`` element alone.

    The XML declaration and DOCTYPE are stripped so the result can be inlined
    into an HTML document directly.
    """
    try:
        buf = io.StringIO()
        fig.savefig(buf, format="svg", bbox_inches="tight", transparent=True)
        svg = buf.getvalue()
    finally:
        plt.close(fig)
    idx = svg.find("<svg")
    return svg[idx:] if idx != -1 else ""


def _guard(fn):
    """An exhibit that cannot be drawn is omitted, never fatal to a report."""

    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            with matplotlib.rc_context(_BASE_RC):
                return fn(*args, **kwargs)
        except Exception as exc:  # pragma: no cover - defensive
            _logger.warning("chart %s failed: %s", fn.__name__, exc)
            return ""

    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper


@_guard
def football_field(
    bands: Sequence[Tuple[str, float, float]],
    current_price: Optional[float] = None,
    target_price: Optional[float] = None,
    currency: str = "$",
    width: float = 6.6,
    height: float = 2.6,
) -> str:
    """Valuation ranges stacked against the traded price and the target.

    The exhibit that makes a valuation argument checkable at a glance: if the
    published target sits outside every band, or the price sits above all of
    them, the reader sees it immediately. That was the defect a reviewer caught
    by reading numbers out of two different tables.

    ``bands`` is ``[(label, low, high), ...]``, drawn bottom-up in the order
    given.
    """
    rows = [(str(lb), float(lo), float(hi)) for lb, lo, hi in bands if hi >= lo]
    if not rows:
        return ""

    fig, ax = _fig(width, height)
    for i, (label, lo, hi) in enumerate(rows):
        ax.barh(i, hi - lo, left=lo, height=0.42, color=ACCENT, alpha=0.28)
        ax.plot([lo, hi], [i, i], color=ACCENT, lw=1.3, solid_capstyle="round")
        for x in (lo, hi):
            ax.plot([x, x], [i - 0.16, i + 0.16], color=ACCENT, lw=1.3)
        ax.annotate(
            f"{currency}{lo:,.0f}",
            (lo, i),
            textcoords="offset points",
            xytext=(-4, 0),
            ha="right",
            va="center",
            fontsize=7.5,
            color=FAINT,
        )
        ax.annotate(
            f"{currency}{hi:,.0f}",
            (hi, i),
            textcoords="offset points",
            xytext=(4, 0),
            ha="left",
            va="center",
            fontsize=7.5,
            color=FAINT,
        )

    handles = []
    if current_price:
        ax.axvline(current_price, color=INK, lw=1.4, zorder=3)
        handles.append(("Price " + f"{currency}{current_price:,.2f}", INK, "-"))
    if target_price:
        ax.axvline(target_price, color=POS, lw=1.4, ls="--", zorder=3)
        handles.append(("Target " + f"{currency}{target_price:,.2f}", POS, "--"))

    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels([r[0] for r in rows], fontsize=8)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel(f"Value per share ({currency})")
    ax.grid(axis="x", alpha=0.5)
    ax.set_axisbelow(True)
    # Room for the end-of-bar value labels, which otherwise collide with the
    # row labels on the left and run off the figure on the right.
    ax.margins(x=0.20, y=0.22)
    # The low-end value label sits left of the bar, right where the row label
    # ends; without extra pad the two run together ("DCF bear-bull$185").
    ax.tick_params(axis="y", pad=7)
    if handles:
        # Below the axes: inside the plot it sat on top of the bars.
        ax.legend(
            handles=[
                plt.Line2D([], [], color=c, ls=s, lw=1.4, label=lab)
                for lab, c, s in handles
            ],
            loc="upper center",
            bbox_to_anchor=(0.5, -0.24),
            ncol=2,
            frameon=False,
            fontsize=7.5,
        )
    return _to_svg(fig)


@_guard
def price_vs_benchmark(
    price_history: Sequence[Dict[str, Any]],
    benchmark_history: Optional[Sequence[Dict[str, Any]]] = None,
    symbol: str = "",
    benchmark_label: str = "Benchmark",
    width: float = 6.6,
    height: float = 2.3,
) -> str:
    """Total-return style comparison, both series indexed to 100 at the start.

    Indexing is what makes it answer the only question worth asking here — did
    the holder beat the alternative — rather than showing two lines on
    incomparable scales. chart_data already carries a date-aligned benchmark
    that nothing plotted.
    """
    pts = [
        (str(p.get("date")), float(p["close"]))
        for p in price_history or []
        if isinstance(p, dict) and isinstance(p.get("close"), (int, float))
    ]
    if len(pts) < 2:
        return ""

    fig, ax = _fig(width, height)
    base = pts[0][1]
    xs = list(range(len(pts)))
    ax.plot(
        xs,
        [v / base * 100 for _, v in pts],
        color=ACCENT,
        lw=1.6,
        label=symbol or "Subject",
    )

    bm = [
        (str(p.get("date")), float(p["close"]))
        for p in benchmark_history or []
        if isinstance(p, dict) and isinstance(p.get("close"), (int, float))
    ]
    if len(bm) >= 2:
        bbase = bm[0][1]
        ax.plot(
            list(range(len(bm))),
            [v / bbase * 100 for _, v in bm],
            color=FAINT,
            lw=1.2,
            ls="--",
            label=benchmark_label,
        )

    ax.axhline(100, color=GRID, lw=0.8, zorder=0)
    step = max(1, len(pts) // 6)
    ax.set_xticks(xs[::step])
    ax.set_xticklabels([pts[i][0][:7] for i in xs[::step]], fontsize=7.5)
    ax.set_ylabel("Indexed to 100")
    ax.grid(axis="y", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(
        loc="lower left",
        bbox_to_anchor=(0, 1.01),
        ncol=2,
        frameon=False,
        fontsize=7.5,
    )
    return _to_svg(fig)


@_guard
def fcf_vs_capex(
    periods: Sequence[str],
    operating_cf: Sequence[Optional[float]],
    capex: Sequence[Optional[float]],
    free_cf: Sequence[Optional[float]],
    width: float = 6.6,
    height: float = 2.6,
) -> str:
    """Cash generated against cash reinvested, with the residual on top.

    For a company in a heavy investment cycle this is the argument, not a
    footnote: a reviewer's central objection to one report was that capex of
    $116B against $67B of free cash flow sat in an appendix.

    ``capex`` may be signed either way; magnitude is what is plotted.
    """
    n = len(periods)
    if not n:
        return ""
    fig, ax = _fig(width, height)
    xs = list(range(n))
    w = 0.38

    def _v(seq: Sequence[Optional[float]]) -> List[float]:
        return [float(x) if isinstance(x, (int, float)) else 0.0 for x in seq]

    ocf, cpx = _v(operating_cf), [abs(v) for v in _v(capex)]
    ax.bar([x - w / 2 for x in xs], ocf, w, label="Operating cash flow", color=ACCENT)
    ax.bar([x + w / 2 for x in xs], cpx, w, label="Capital expenditure", color=WARN)

    fcf = _v(free_cf)
    if any(fcf):
        ax.plot(xs, fcf, color=POS, lw=1.6, marker="o", ms=3.5, label="Free cash flow")

    ax.set_xticks(xs)
    ax.set_xticklabels([str(p)[:7] for p in periods], fontsize=7.5)
    ax.set_ylabel("USD millions")
    ax.grid(axis="y", alpha=0.5)
    ax.set_axisbelow(True)
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        ncol=3,
        frameon=False,
        fontsize=7.5,
    )
    return _to_svg(fig)


@_guard
def peer_scatter(
    rows: Sequence[Dict[str, Any]],
    x_key: str = "revenue_growth_pct",
    y_key: str = "fwd_pe",
    width: float = 6.0,
    height: float = 2.9,
) -> str:
    """Where the subject trades relative to peers, on growth against multiple.

    A table of multiples tells you the numbers; this tells you whether the
    subject is cheap *for its growth*, which is the actual comparable question.
    The subject is drawn filled and labelled, peers hollow.
    """
    pts = [
        r
        for r in rows or []
        if isinstance(r.get(x_key), (int, float))
        and isinstance(r.get(y_key), (int, float))
    ]
    if len(pts) < 2:
        return ""

    fig, ax = _fig(width, height)
    for r in pts:
        subject = bool(r.get("is_subject"))
        cap = r.get("market_cap_b")
        size = 40.0
        if isinstance(cap, (int, float)) and cap > 0:
            size = max(30.0, min(320.0, float(cap) ** 0.5 * 9))
        ax.scatter(
            r[x_key],
            r[y_key],
            s=size,
            color=ACCENT if subject else "none",
            edgecolor=ACCENT if subject else FAINT,
            linewidth=1.3,
            zorder=3 if subject else 2,
        )
        ax.annotate(
            str(r.get("symbol", "")),
            (r[x_key], r[y_key]),
            textcoords="offset points",
            xytext=(0, 9),
            ha="center",
            fontsize=7.5,
            color=INK if subject else FAINT,
            fontweight="bold" if subject else "normal",
        )

    ax.set_xlabel("Revenue growth (%)")
    ax.set_ylabel("Forward P/E (x)")
    ax.grid(alpha=0.5)
    ax.set_axisbelow(True)
    ax.margins(0.16)
    return _to_svg(fig)


def shorten_segment(name: str, limit: int = 26) -> str:
    """Make an XBRL segment label readable on an axis.

    yfinance returns spelled-out tags — "Microsoft Three Six Five Commercial
    Products And Cloud Services" — which are unreadable as tick labels.
    """
    cleaned = " ".join(str(name).split())
    for long, short in (
        ("Three Six Five", "365"),
        ("And Cloud Services", "Cloud"),
        ("Products And", ""),
        ("Corporation", ""),
        (" And ", " & "),
    ):
        cleaned = cleaned.replace(long, short)
    cleaned = " ".join(cleaned.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


@_guard
def segment_mix(
    segments: Dict[str, float],
    total: Optional[float] = None,
    top: int = 8,
    width: float = 6.2,
    height: float = 2.8,
) -> str:
    """Revenue by segment, largest first, labelled with share of total."""
    items = [
        (str(k), float(v))
        for k, v in (segments or {}).items()
        if isinstance(v, (int, float)) and v > 0
    ]
    if not items:
        return ""
    items.sort(key=lambda kv: kv[1], reverse=True)
    items = items[:top][::-1]  # barh draws bottom-up
    denom = float(total) if total else sum(v for _, v in items)

    fig, ax = _fig(width, height)
    ys = range(len(items))
    scale = 1e9 if max(v for _, v in items) > 1e9 else 1e6
    unit = "USD billions" if scale == 1e9 else "USD millions"
    ax.barh(list(ys), [v / scale for _, v in items], color=ACCENT, height=0.62)
    for i, (_, v) in enumerate(items):
        if denom:
            ax.annotate(
                f"{v / denom * 100:.0f}%",
                (v / scale, i),
                textcoords="offset points",
                xytext=(4, 0),
                va="center",
                fontsize=7.5,
                color=FAINT,
            )
    ax.set_yticks(list(ys))
    ax.set_yticklabels([shorten_segment(k) for k, _ in items], fontsize=8)
    ax.spines["left"].set_visible(False)
    ax.set_xlabel(unit)
    ax.grid(axis="x", alpha=0.5)
    ax.set_axisbelow(True)
    ax.margins(x=0.12)
    return _to_svg(fig)
