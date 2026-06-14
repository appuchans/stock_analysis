"""Pure-Python inline SVG charts for HTML reports — no plotting dependencies."""

from typing import Dict, Sequence, Tuple

_BLUE = "#2b6cb0"
_BLUE_LIGHT = "#bee3f8"
_GRID = "#e2e8f0"
_TEXT = "#4a5568"
_GREEN_DARK = "#22543d"
_GREEN = "#38a169"
_AMBER = "#d69e2e"
_RED = "#c53030"
_RED_DARK = "#822727"


def _fmt(v: float) -> str:
    """Compact human number: 1234567 → 1.2M, 32.0 → 32, 98.27 → 98.27."""
    a = abs(v)
    for div, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"{v / div:.1f}{suffix}"
    if a < 100:
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    return f"{v:,.0f}"


def line_chart_svg(
    points: Sequence[Tuple[str, float]],
    title: str = "",
    width: int = 860,
    height: int = 280,
    currency: str = "$",
) -> str:
    """Area line chart from (date_label, value) points. Returns '' for <2 points."""
    pts = [(d, float(v)) for d, v in points if v is not None]
    if len(pts) < 2:
        return ""

    pad_l, pad_r, pad_t, pad_b = 64, 16, 30, 28
    plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
    values = [v for _, v in pts]
    vmin, vmax = min(values), max(values)
    vrange = (vmax - vmin) or 1.0
    vmin -= vrange * 0.05
    vmax += vrange * 0.05
    vrange = vmax - vmin

    def x(i: int) -> float:
        return pad_l + i / (len(pts) - 1) * plot_w

    def y(v: float) -> float:
        return pad_t + (1 - (v - vmin) / vrange) * plot_h

    poly = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, (_, v) in enumerate(pts))
    area = f"{pad_l:.1f},{pad_t + plot_h:.1f} {poly} {pad_l + plot_w:.1f},{pad_t + plot_h:.1f}"

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{title}">'
    ]
    if title:
        parts.append(
            f'<text x="{pad_l}" y="18" font-size="13" font-weight="600" fill="{_TEXT}">{title}</text>'
        )
    # Horizontal gridlines + y labels
    for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
        gy = pad_t + frac * plot_h
        val = vmax - frac * vrange
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + plot_w}" y2="{gy:.1f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 8}" y="{gy + 4:.1f}" font-size="11" fill="{_TEXT}" '
            f'text-anchor="end">{currency}{_fmt(val)}</text>'
        )
    # X-axis date ticks (5 evenly spaced)
    for i in range(0, len(pts), max(1, (len(pts) - 1) // 4)):
        parts.append(
            f'<text x="{x(i):.1f}" y="{height - 8}" font-size="11" fill="{_TEXT}" '
            f'text-anchor="middle">{pts[i][0]}</text>'
        )
    parts.append(f'<polygon points="{area}" fill="{_BLUE_LIGHT}" opacity="0.45"/>')
    parts.append(
        f'<polyline points="{poly}" fill="none" stroke="{_BLUE}" stroke-width="2.2" '
        f'stroke-linejoin="round"/>'
    )
    # Last-point marker + label
    lx, ly = x(len(pts) - 1), y(pts[-1][1])
    parts.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{_BLUE}"/>')
    anchor = "end" if lx > width - 90 else "start"
    parts.append(
        f'<text x="{lx - 6 if anchor == "end" else lx + 6:.1f}" y="{ly - 8:.1f}" font-size="12" '
        f'font-weight="600" fill="{_BLUE}" text-anchor="{anchor}">{currency}{_fmt(pts[-1][1])}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def bar_chart_svg(
    labels: Sequence[str],
    values: Sequence[float],
    title: str = "",
    width: int = 860,
    height: int = 260,
    unit: str = "$",
    suffix: str = "M",
    horizontal: bool = False,
) -> str:
    """Bar chart. Vertical by default; horizontal for long category labels."""
    data = [(str(l), float(v)) for l, v in zip(labels, values) if v is not None]
    if not data:
        return ""

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{title}">'
    ]
    if title:
        parts.append(
            f'<text x="16" y="18" font-size="13" font-weight="600" fill="{_TEXT}">{title}</text>'
        )

    if horizontal:
        pad_l, pad_r, pad_t, pad_b = 180, 80, 30, 12
        plot_w = width - pad_l - pad_r
        bar_h = max(12, min(26, (height - pad_t - pad_b) / len(data) - 8))
        vmax = max(abs(v) for _, v in data) or 1.0
        for i, (label, v) in enumerate(data):
            by = pad_t + i * ((height - pad_t - pad_b) / len(data)) + 4
            bw = abs(v) / vmax * plot_w
            parts.append(
                f'<text x="{pad_l - 10}" y="{by + bar_h / 2 + 4:.1f}" font-size="12" '
                f'fill="{_TEXT}" text-anchor="end">{label}</text>'
            )
            parts.append(
                f'<rect x="{pad_l}" y="{by:.1f}" width="{bw:.1f}" height="{bar_h:.1f}" '
                f'rx="3" fill="{_BLUE}"/>'
            )
            parts.append(
                f'<text x="{pad_l + bw + 8:.1f}" y="{by + bar_h / 2 + 4:.1f}" font-size="12" '
                f'font-weight="600" fill="{_TEXT}">{unit}{_fmt(v)}{suffix}</text>'
            )
    else:
        pad_l, pad_r, pad_t, pad_b = 64, 16, 30, 28
        plot_w, plot_h = width - pad_l - pad_r, height - pad_t - pad_b
        vmax = max((v for _, v in data if v > 0), default=1.0) or 1.0
        vmin = min((v for _, v in data), default=0.0)
        floor = min(0.0, vmin)
        vrange = (vmax - floor) or 1.0
        slot = plot_w / len(data)
        bar_w = slot * 0.62
        zero_y = pad_t + (vmax / vrange) * plot_h
        parts.append(
            f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{pad_l + plot_w}" y2="{zero_y:.1f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
        for i, (label, v) in enumerate(data):
            bx = pad_l + i * slot + (slot - bar_w) / 2
            bh = abs(v) / vrange * plot_h
            by = zero_y - bh if v >= 0 else zero_y
            color = _BLUE if v >= 0 else "#c53030"
            parts.append(
                f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{bh:.1f}" '
                f'rx="3" fill="{color}"/>'
            )
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{by - 6 if v >= 0 else by + bh + 14:.1f}" '
                f'font-size="11" font-weight="600" fill="{_TEXT}" text-anchor="middle">'
                f'{unit}{_fmt(v)}{suffix}</text>'
            )
            parts.append(
                f'<text x="{bx + bar_w / 2:.1f}" y="{height - 8}" font-size="11" fill="{_TEXT}" '
                f'text-anchor="middle">{label}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


def range_bar_svg(
    low: float,
    high: float,
    markers: Sequence[Tuple[str, float, str]],
    title: str = "",
    width: int = 860,
    height: int = 96,
    currency: str = "$",
) -> str:
    """Horizontal range band with labelled markers.

    Used for the analyst price-target range (low→high band, markers for the
    current price and mean target) and the 52-week range.
    markers: sequence of (label, value, color).
    """
    try:
        low_f, high_f = float(low), float(high)
    except (TypeError, ValueError):
        return ""
    if high_f <= low_f:
        return ""

    pad_l, pad_r = 70, 70
    band_y, band_h = height - 38, 12
    plot_w = width - pad_l - pad_r
    # Extend domain a touch so out-of-band markers stay visible
    vals = [low_f, high_f] + [float(v) for _, v, _ in markers if v is not None]
    dmin, dmax = min(vals), max(vals)
    span = (dmax - dmin) or 1.0
    dmin -= span * 0.04
    dmax += span * 0.04

    def x(v: float) -> float:
        return pad_l + (v - dmin) / (dmax - dmin) * plot_w

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{title}">'
    ]
    if title:
        parts.append(
            f'<text x="{pad_l}" y="16" font-size="13" font-weight="600" fill="{_TEXT}">{title}</text>'
        )
    # Band
    parts.append(
        f'<rect x="{x(low_f):.1f}" y="{band_y}" width="{x(high_f) - x(low_f):.1f}" '
        f'height="{band_h}" rx="6" fill="{_BLUE_LIGHT}"/>'
    )
    # Band end labels
    parts.append(
        f'<text x="{x(low_f):.1f}" y="{band_y + band_h + 16}" font-size="11" fill="{_TEXT}" '
        f'text-anchor="middle">{currency}{_fmt(low_f)}</text>'
    )
    parts.append(
        f'<text x="{x(high_f):.1f}" y="{band_y + band_h + 16}" font-size="11" fill="{_TEXT}" '
        f'text-anchor="middle">{currency}{_fmt(high_f)}</text>'
    )
    # Markers (staggered label heights to avoid overlap)
    for i, (label, value, color) in enumerate(markers):
        if value is None:
            continue
        mx = x(float(value))
        parts.append(
            f'<line x1="{mx:.1f}" y1="{band_y - 6}" x2="{mx:.1f}" y2="{band_y + band_h + 6}" '
            f'stroke="{color}" stroke-width="2.5"/>'
        )
        ly = band_y - 10 - (i % 2) * 14
        parts.append(
            f'<text x="{mx:.1f}" y="{ly}" font-size="11.5" font-weight="600" fill="{color}" '
            f'text-anchor="middle">{label} {currency}{_fmt(float(value))}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def rating_bar_svg(
    counts: Dict[str, int],
    title: str = "",
    width: int = 860,
    height: int = 86,
) -> str:
    """Stacked analyst-rating distribution bar (strong buy → strong sell)."""
    order = [
        ("strong_buy", "Strong Buy", _GREEN_DARK),
        ("buy", "Buy", _GREEN),
        ("hold", "Hold", _AMBER),
        ("sell", "Sell", _RED),
        ("strong_sell", "Strong Sell", _RED_DARK),
    ]
    total = sum(int(counts.get(k, 0) or 0) for k, _, _ in order)
    if total <= 0:
        return ""

    pad_l, pad_r = 16, 16
    bar_y, bar_h = 34, 22
    plot_w = width - pad_l - pad_r

    parts = [
        f'<svg viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg" '
        f'role="img" aria-label="{title}">'
    ]
    if title:
        parts.append(
            f'<text x="{pad_l}" y="16" font-size="13" font-weight="600" fill="{_TEXT}">'
            f'{title} ({total} analysts)</text>'
        )
    cx = float(pad_l)
    for key, label, color in order:
        n = int(counts.get(key, 0) or 0)
        if n == 0:
            continue
        w = n / total * plot_w
        parts.append(
            f'<rect x="{cx:.1f}" y="{bar_y}" width="{w:.1f}" height="{bar_h}" fill="{color}"/>'
        )
        if w > 34:
            parts.append(
                f'<text x="{cx + w / 2:.1f}" y="{bar_y + bar_h / 2 + 4:.1f}" font-size="11.5" '
                f'font-weight="700" fill="#ffffff" text-anchor="middle">{n}</text>'
            )
        parts.append(
            f'<text x="{cx + w / 2:.1f}" y="{bar_y + bar_h + 16}" font-size="10.5" '
            f'fill="{_TEXT}" text-anchor="middle">{label if w > 70 else ""}</text>'
        )
        cx += w
    parts.append("</svg>")
    return "".join(parts)
