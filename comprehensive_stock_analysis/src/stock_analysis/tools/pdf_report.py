"""Typeset the research note as a PDF, via Typst.

Not an HTML-to-PDF conversion. Browsers ignore CSS ``@page`` margin boxes, so
the running headers, footers and page numbers the report already declared were
silently dropped and the browser's own print chrome — including a
``localhost:8000/...`` URL — took their place. Typst is a real typesetting
engine: it honours all of that, paginates deterministically, and ships as a
prebuilt wheel with the compiler bundled, so there is no system dependency.

The document is assembled from ``ReportModel`` and the exhibits in ``_charts``,
which the HTML renderer reads too — both state the same numbers because they
resolve them in the same place.
"""

import logging
import re
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from ..config.settings import settings
from . import _charts
from .report_model import ReportModel

_logger = logging.getLogger(__name__)

# Characters that mean something to Typst's markup parser.
_ESCAPE = str.maketrans({c: "\\" + c for c in "\\#$*_@<>`~[]"})


def _esc(text: str) -> str:
    """Escape a plain string for Typst *content* mode."""
    return str(text).translate(_ESCAPE)


def _str(text: str) -> str:
    """Escape for a Typst *string literal*, where markup escapes are literal.

    Passing content-escaped text into a quoted string renders the backslashes:
    the cover tiles read "\\$245.00" until these were separated.
    """
    return str(text).replace("\\", "\\\\").replace('"', '\\"')


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^*\n]+?)\*(?!\*)")
_CODE = re.compile(r"`([^`\n]+?)`")


def _inline(text: str) -> str:
    """Convert markdown inline emphasis to Typst, escaping everything else.

    Markers are extracted before escaping and re-applied after, so a literal
    asterisk in the prose cannot be mistaken for emphasis and vice versa.
    """
    tokens: List[str] = []

    def stash(rendered: str) -> str:
        tokens.append(rendered)
        return f"\x00{len(tokens) - 1}\x00"

    text = _CODE.sub(lambda m: stash(f"`{m.group(1)}`"), text)
    text = _BOLD.sub(lambda m: stash(f"*{_esc(m.group(1))}*"), text)
    text = _ITALIC.sub(lambda m: stash(f"_{_esc(m.group(1))}_"), text)
    out = _esc(text)
    # The escaper mangles the sentinel's surrounding text but not \x00 itself.
    return re.sub(r"\x00(\d+)\x00", lambda m: tokens[int(m.group(1))], out)


_NUMERIC = re.compile(r"^[\s$€£+\-]*[\d,.]+\s*[%xX]?\s*$")


def _numeric_columns(rows: Sequence[Sequence[str]], cols: int) -> List[bool]:
    """Which columns hold figures, so only those are right-aligned.

    Right-aligning every non-first column pushed sentences to the right margin
    in the rating-definitions table, which read as a layout error.
    """
    flags = []
    for c in range(cols):
        body = [r[c] for r in rows[1:] if c < len(r) and str(r[c]).strip()]
        flags.append(bool(body) and all(_NUMERIC.match(str(v)) for v in body))
    return flags


def _table(rows: Sequence[Sequence[str]], header: bool = True) -> str:
    """A markdown-style table as a Typst table, sized to its widest row."""
    if not rows:
        return ""
    cols = max(len(r) for r in rows)
    numeric = _numeric_columns(rows, cols)
    cells: List[str] = []
    for i, row in enumerate(rows):
        padded = list(row) + [""] * (cols - len(row))
        for cell in padded:
            body = _inline(cell)
            cells.append(f"[*{body}*]" if header and i == 0 else f"[{body}]")
    aligns = ", ".join("right" if n else "left" for n in numeric)
    # The header row repeats when a table breaks across pages. Without it the
    # comparables table spilled onto the next page as bare numbers with no
    # column labels, which is worse than not showing them.
    if header and len(cells) > cols:
        head = ", ".join(cells[:cols])
        cells = [f"table.header({head})"] + cells[cols:]
    return (
        "#table(\n"
        f"  columns: {cols},\n"
        '  stroke: (x, y) => if y == 0 { (bottom: 0.6pt + rgb("#4a5a70")) }'
        ' else { (bottom: 0.3pt + rgb("#e6eaf1")) },\n'
        "  inset: (x: 5pt, y: 4pt),\n"
        f"  align: ({aligns}),\n"
        f"  {', '.join(cells)}\n"
        ")\n"
    )


def markdown_to_typst(md: str) -> str:
    """Convert the narrative subset the stages actually emit.

    Headings, emphasis, bullet and numbered lists, pipe tables and paragraphs —
    which is everything the prompts ask for. Anything else degrades to escaped
    text rather than breaking the compile.
    """
    lines = (md or "").replace("\r\n", "\n").split("\n")
    out: List[str] = []
    table_buf: List[List[str]] = []

    def flush_table() -> None:
        if table_buf:
            out.append(_table(table_buf))
            table_buf.clear()

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            # The |---|---| separator carries no content.
            if not all(set(c) <= set("-: ") for c in cells if c):
                table_buf.append(cells)
            continue
        flush_table()

        if not stripped:
            out.append("")
            continue
        if m := re.match(r"^(#{3,6})\s+(.*)$", stripped):
            # Narrative sections are h2; anything deeper is a sub-heading.
            level = min(len(m.group(1)) - 1, 4)
            out.append(f"\n{'=' * level} {_inline(m.group(2))}\n")
            continue
        if m := re.match(r"^[-*•]\s+(.*)$", stripped):
            out.append(f"- {_inline(m.group(1))}")
            continue
        if m := re.match(r"^(\d+)[.)]\s+(.*)$", stripped):
            out.append(f"+ {_inline(m.group(2))}")
            continue
        if set(stripped) <= set("-_=") and len(stripped) >= 3:
            out.append('#line(length: 100%, stroke: 0.3pt + rgb("#e6eaf1"))')
            continue
        out.append(_inline(stripped))

    flush_table()
    return "\n".join(out)


_CAPTIONS = {
    # Describes the exhibit. The previous wording — "a contradiction the note
    # must explain" — was an instruction to the analyst, printed to the client.
    "football": ("Valuation ranges against the last close and the published target."),
    "relative": "Total return versus benchmark, indexed to 100 at the start.",
    "fcf": (
        "Cash generated against cash reinvested. The gap between operating "
        "cash flow and capital expenditure is what funds returns to holders."
    ),
    "peers": (
        "Comparable companies on growth against forward multiple; bubble area "
        "is market capitalization and the subject is filled. Comparables are "
        "screened to the subject's industry, then ranked by similarity of "
        "size - a provider's raw peer list ranks by size alone and mixes in "
        "businesses that are not comparable."
    ),
    "segments": "Revenue by reporting segment, with share of the total.",
}


# Which exhibit belongs under which narrative heading. First keyword match
# wins, mirroring how the HTML renderer places its visuals.
_EXHIBIT_FOR = (
    ("valuation", "football"),
    ("recommendation", "football"),
    ("financial", "fcf"),
    ("performance", "fcf"),
    ("thesis", "relative"),
    ("competitive", "peers"),
    ("competitor", "peers"),
    ("business overview", "segments"),
)


def _build_exhibits(model: ReportModel, out_dir: Path) -> Dict[str, str]:
    """Render every exhibit the data supports; return {name: filename}."""
    charts: Dict[str, str] = {}

    def save(name: str, svg: str) -> None:
        if svg:
            (out_dir / f"{name}.svg").write_text(svg, encoding="utf-8")
            charts[name] = f"{name}.svg"

    bands = model.football_field_bands()
    if bands:
        save(
            "football",
            _charts.football_field(
                bands, current_price=model.price, target_price=model.target
            ),
        )
    save(
        "relative",
        _charts.price_vs_benchmark(
            model.chart.get("price_history") or [],
            (model.chart.get("benchmark") or {}).get("history"),
            symbol=model.symbol,
            benchmark_label=str(
                (model.chart.get("benchmark") or {}).get("symbol") or "Benchmark"
            ),
        ),
    )
    save("peers", _charts.peer_scatter(model.peers()))

    seg = model.chart.get("revenue_by_segment") or {}
    save(
        "segments",
        _charts.segment_mix(seg.get("segments") or {}, total=seg.get("total")),
    )

    fin = model.chart.get("financials") or {}
    cf = fin.get("cash_flow") or {}
    if cf:
        periods = sorted(cf)
        save(
            "fcf",
            _charts.fcf_vs_capex(
                periods,
                [cf[p].get("operating_cf_m") for p in periods],
                [cf[p].get("capex_m") for p in periods],
                [cf[p].get("free_cash_flow_m") for p in periods],
            ),
        )
    return charts


# A label the reader cannot place on a scale is decoration. A note printed
# "Risk High" and "Confidence 76%" with nothing anywhere saying what either
# meant or what would move them.
_RISK_KEY = [
    ("Low", "Earnings and cash flow are predictable; drawdowns track the market."),
    ("Medium", "Cyclical or competitive pressure can move earnings materially."),
    (
        "High",
        "Realistic scenarios break the thesis, or volatility and drawdown run "
        "well above the market.",
    ),
]

_CONFIDENCE_KEY = [
    ("Above 80%", "Thesis rests on demonstrated, recurring results."),
    ("60-80%", "Direction is well supported; magnitude or timing is uncertain."),
    ("Below 60%", "Thesis depends on an outcome not yet evidenced."),
]

_RATING_KEY = [
    ("Buy", "Total return expected to exceed the market over the stated horizon."),
    ("Hold", "Total return expected to track the market over the stated horizon."),
    ("Sell", "Total return expected to trail the market over the stated horizon."),
]


def _cover(model: ReportModel, charts: Dict[str, str]) -> str:
    tiles = model.key_stat_tiles()
    tile_src = ", ".join(f'(("{_str(lb)}"), ("{_str(val)}"))' for lb, val in tiles)
    parts = [
        f"#align(center)[\n"
        f"  #text(9pt, fill: muted)[{_esc(settings.report_firm_name)}]\n"
        f"  #v(2pt)\n"
        f'  #text(21pt, weight: "bold")[{_esc(model.name)}]\n'
        f"  #v(-5pt)\n"
        f"  #text(10pt, fill: muted)[{_esc(model.subtitle)}]\n"
        f"]\n#v(9pt)\n"
    ]
    if tiles:
        parts.append(
            "#grid(columns: (1fr,) * 4, gutter: 5pt,\n"
            f"  ..(({tile_src},)).map(t => tile(t.at(0), t.at(1)))\n)\n#v(8pt)\n"
        )
    rating = model.rating.upper()
    meaning = next((m for label, m in _RATING_KEY if label.upper() == rating), "")
    if meaning:
        horizon = str(model.rec.get("time_horizon") or "").strip()
        parts.append(
            f"#text(8pt, fill: muted)[*{_esc(rating)}*: {_esc(meaning)}"
            + (f" Horizon {_esc(horizon)}." if horizon else "")
            + "]\n#v(4pt)\n"
        )
    if model.target_withheld:
        # Said plainly on page 1. Silently dropping the tile would leave the
        # reader wondering whether a target existed; this states that one was
        # computed and judged undefensible, which is the honest position and
        # the one a reviewer asked for.
        parts.append(
            '#block(fill: rgb("#fff7ed"), inset: 8pt, radius: 3pt, width: 100%)'
            "[#text(8.5pt)[*No house target.* The valuation model did not "
            "produce a figure that can be defended against the traded price, so "
            "none is published. The rating reflects margin of safety at the "
            "current level, not a computed price objective.]]\n#v(6pt)\n"
        )
    # The firm already heads the page; repeating it as a byline printed
    # "Equity Research" twice in four lines.
    byline = settings.report_author.strip()
    if byline:
        parts.append(f"#text(8pt, fill: muted)[{_esc(byline)}]\n#v(4pt)\n")
    if model.price:
        parts.append(
            f"#text(8pt, fill: muted)[{_esc(model.price_label)}. "
            f'{_esc(str(model.snapshot.get("price_source") or "Market data"))}.]\n'
            "#v(8pt)\n"
        )
    if model.summary:
        parts.append(
            '#block(fill: rgb("#f6f8fb"), inset: 9pt, radius: 3pt, width: 100%)[\n'
            f"  {markdown_to_typst(model.summary)}\n]\n#v(8pt)\n"
        )
    if "relative" in charts:
        parts.append(
            f'#figure(image("{charts["relative"]}", width: 100%),\n'
            f"  caption: [Total return versus benchmark, indexed to 100.])\n#v(6pt)\n"
        )
    cats = model.catalysts()
    if cats:
        parts.append(
            '#text(9pt, weight: "bold")[Calendar]\n#v(2pt)\n'
            + _table([["Event", "Date"]] + [[lb, d] for lb, d in cats])
        )
    return "".join(parts)


def _forecast_table(model: ReportModel) -> str:
    """The explicit three-year forecast, and the value derived from it.

    The absence of this was the standing objection to every note the system
    produced: segments and drivers were described, never measured, so the
    target had nothing underneath it and defaulted to consensus.
    """
    fc = model.chart.get("forecast") or {}
    rows = fc.get("years") or []
    if not rows:
        return ""
    header = [
        "Year",
        "Revenue ($B)",
        "Growth",
        "Op margin",
        "Op income ($B)",
        "Capex (% rev)",
        "FCF ($B)",
    ]
    body = [
        [
            str(r["year"]),
            f"{r['revenue_m'] / 1000:,.1f}",
            f"{r['revenue_growth_pct']:,.1f}%",
            f"{r['operating_margin_pct']:,.1f}%",
            f"{r['operating_income_m'] / 1000:,.1f}",
            f"{r['capex_pct_of_revenue']:,.1f}%",
            f"{r['free_cash_flow_m'] / 1000:,.1f}",
        ]
        for r in rows
    ]
    out = ["\n== Three-year forecast\n\n", _table([header] + body)]

    a = fc.get("assumptions") or {}
    if a:
        out.append(
            "\n#text(7.5pt, fill: muted)[Revenue: "
            f"{_inline(str(a.get('revenue_basis', '')))}. Operating margin from "
            f"{a.get('base_operating_margin_pct')}% moving "
            f"{a.get('margin_change_ppt_per_year')}pp a year. Capital spending "
            f"{a.get('capex_pct_now')}% of revenue reverting toward "
            f"{a.get('capex_pct_reverting_to')}%. Operating cash flow "
            f"{a.get('operating_cf_margin_pct')}% of revenue.]\n"
        )
    v = model.chart.get("forecast_valuation") or {}
    if v.get("value_per_share"):
        out.append(
            f"\n*Value from this forecast: ${v['value_per_share']:,.2f} a share* — "
            f"{_inline(str(v.get('method', '')))}.\n"
        )
    return "".join(out)


def _peer_table(model: ReportModel) -> str:
    """Comparable multiples side by side, rendered from data.

    The note printed a one-column table of the subject's own multiples and
    then described peers in prose — "cheaper than Cisco and SAP" — with no
    figures behind the claim. The numbers exist for every peer; they only had
    to be laid out. Built here rather than asked of the model so no figure is
    transcribed twice.
    """
    rows = model.peers()
    if len(rows) < 2:
        return ""
    header = [
        "Company",
        "Mkt cap ($B)",
        "P/E",
        "Fwd P/E",
        "EV/EBITDA",
        "FCF yield",
        "Op margin",
        "Rev growth",
    ]
    body = []
    for r in rows:

        def _f(key: str, suffix: str = "", digits: int = 1) -> str:
            v = r.get(key)
            return f"{v:,.{digits}f}{suffix}" if isinstance(v, (int, float)) else "—"

        body.append(
            [
                f"{r.get('symbol', '')}{' (subject)' if r.get('is_subject') else ''}",
                _f("market_cap_b"),
                _f("pe_ttm", "x"),
                _f("fwd_pe", "x"),
                _f("ev_to_ebitda", "x"),
                _f("fcf_yield_pct", "%"),
                _f("operating_margin_pct", "%"),
                _f("revenue_growth_pct", "%"),
            ]
        )
    return (
        "\n== Comparable companies\n\n"
        + _table([header] + body)
        + "\n#text(7.5pt, fill: muted)[Multiples are trailing twelve months "
        "from market data and will not tie to the fiscal-year statements "
        "elsewhere in this note.]\n"
    )


def _appendix(model: ReportModel) -> str:
    parts = ["#pagebreak()\n= Appendix\n\n== Rating definitions\n\n"]
    parts.append(_table([["Rating", "Meaning"]] + [list(r) for r in _RATING_KEY]))
    horizon = str(model.rec.get("time_horizon") or "").strip()
    if horizon:
        parts.append(f"\nRatings apply over a {_esc(horizon)} horizon.\n")

    parts.append("\n== Risk and confidence scales\n\n")
    parts.append(_table([["Risk level", "Meaning"]] + [list(r) for r in _RISK_KEY]))
    parts.append(
        _table([["Confidence", "Meaning"]] + [list(r) for r in _CONFIDENCE_KEY])
    )

    parts.append("\n== Valuation method\n\n")
    scen = model.scenarios
    if scen:
        parts.append(
            _table(
                [["Scenario", "Growth", "Discount", "Terminal", "Value / share"]]
                + [
                    [
                        str(s.get("scenario", "")),
                        f"{s.get('growth_pct', '')}%",
                        f"{s.get('discount_pct', '')}%",
                        f"{s.get('terminal_pct', '')}%",
                        f"${float(s['intrinsic_per_share']):,.2f}",
                    ]
                    for s in scen
                ]
            )
        )
        method = str(scen[0].get("method") or "").strip()
        if method:
            parts.append(f"\nMethod: {_esc(method)}.\n")
        if model.target_reconciles is False:
            # Stated plainly rather than buried: the reader is entitled to know
            # the target is not what this model alone would produce.
            parts.append(
                '\n#block(fill: rgb("#fff7ed"), inset: 8pt, radius: 3pt, width: 100%)'
                "[The published target sits outside the modelled range. The"
                " assumption bridging the two is stated in the valuation"
                " section.]\n"
            )
    else:
        parts.append("No discounted-cash-flow model was produced for this run.\n")

    parts.append("\n== Basis and disclosures\n\n")
    disclaimer = (
        settings.report_disclaimer
        or "This report was produced by automated analysis of public data "
        "sources. It is information, not investment advice, and no "
        "recommendation is made as to the suitability of any security for "
        "any particular investor. Figures are as stated on the cover and may "
        "have moved since."
    )
    parts.append(_inline(disclaimer) + "\n")
    if settings.report_author:
        parts.append(f"\nPrepared by {_esc(settings.report_author)}.\n")
    return "".join(parts)


_PREAMBLE = """
#let ink = rgb("#1f2937")
#let muted = rgb("#6b7280")
#let rule = rgb("#e6eaf1")
#let tile(label, value) = block(
  fill: rgb("#f6f8fb"), inset: (x: 7pt, y: 6pt), radius: 3pt, width: 100%,
)[
  #text(7pt, fill: muted)[#upper(label)] \\
  #text(12pt, weight: "bold", fill: ink)[#value]
]
#set page(
  paper: "a4", margin: (x: 18mm, top: 18mm, bottom: 16mm),
  header: context {
    if counter(page).get().first() > 1 [
      #set text(7.5pt, fill: muted)
      #HEADER_LEFT #h(1fr) #HEADER_RIGHT
      #v(-6pt)
      #line(length: 100%, stroke: 0.4pt + rule)
    ]
  },
  footer: context [
    #set text(7.5pt, fill: muted)
    #line(length: 100%, stroke: 0.4pt + rule)
    #v(-2pt)
    #FOOTER_LEFT #h(1fr) Page #counter(page).display("1 of 1", both: true)
  ],
)
#set text(font: ("Helvetica", "Liberation Sans", "DejaVu Sans"), size: 9.3pt,
          fill: ink, lang: "en")
#set par(justify: true, leading: 0.62em, spacing: 0.95em)
#show heading.where(level: 1): it => block(above: 14pt, below: 7pt)[
  #text(13pt, weight: "bold")[#it.body]
  #v(-4pt)
  #line(length: 100%, stroke: 0.6pt + rule)
]
#show heading.where(level: 2): it => block(above: 10pt, below: 4pt)[
  #text(10.5pt, weight: "bold")[#it.body]
]
#show heading.where(level: 3): it => block(above: 8pt, below: 3pt)[
  #text(9.6pt, weight: "bold", fill: muted)[#it.body]
]
#show table: set text(8.3pt)
#set figure(gap: 5pt)
#show figure.caption: set text(7.8pt, fill: muted)
"""


def build_typst_source(model: ReportModel, charts: Dict[str, str]) -> str:
    """The complete Typst document for this run."""
    header_left = _esc(f"{model.symbol} — {model.name}")
    header_right = _esc(settings.report_firm_name)
    footer_left = _esc(
        f"{settings.report_firm_name} · {model.price_label} · not investment advice"
    )
    src = [
        _PREAMBLE.replace("#HEADER_LEFT", header_left)
        .replace("#HEADER_RIGHT", header_right)
        .replace("#FOOTER_LEFT", footer_left),
        _cover(model, charts),
    ]

    # Seeded with what the cover already showed. The cover renders the
    # relative-performance chart, and _EXHIBIT_FOR also maps it to the thesis
    # section, so it appeared twice — once on page 1 and again at the top of
    # page 2.
    used: set = {"relative"} if "relative" in charts else set()
    for title, body in model.sections:
        src.append(f"\n= {_inline(title)}\n\n")
        src.append(markdown_to_typst(body))
        low = title.lower()
        if model.target_bridge_required and (
            "valuation" in low or "recommendation" in low
        ):
            # Tied to the section, not to the chart. Nested under the football
            # exhibit it disappeared whenever that chart could not be drawn —
            # exactly the case where the target is least anchored.
            src.append(
                '\n#block(fill: rgb("#fff7ed"), inset: 8pt, radius: 3pt, '
                "width: 100%)[#text(8.5pt)[*Target reconciliation.* The "
                "published target does not follow from the "
                "discounted-cash-flow work above. Treat it as a judgement "
                "about multiple or execution rather than an output of the "
                "model.]]\n"
            )
        for keyword, exhibit in _EXHIBIT_FOR:
            if keyword in low and exhibit in charts and exhibit not in used:
                used.add(exhibit)
                cap = _CAPTIONS.get(exhibit, "")
                tail = f", caption: [{_inline(cap)}]" if cap else ""
                src.append(
                    f'\n#figure(image("{charts[exhibit]}", width: 100%){tail})\n'
                )
                if exhibit == "football":
                    src.append(_forecast_table(model))
                    src.append(_peer_table(model))
                break

    # Anything the narrative gave no home to still belongs in the document.
    leftovers = [n for n in charts if n not in used and n != "relative"]
    if leftovers:
        # Flowed, not broken onto its own page: forcing a break here stranded
        # the previous section's last two lines on a page of their own and then
        # left the exhibits page two-thirds empty.
        src.append(
            "\n= Exhibits\n\nSupporting charts referenced by the analysis above.\n\n"
        )
        for name in leftovers:
            cap = _CAPTIONS.get(name, "")
            tail = f", caption: [{_inline(cap)}]" if cap else ""
            src.append(
                f'#figure(image("{charts[name]}", width: 100%){tail})\n#v(6pt)\n'
            )

    src.append(_appendix(model))
    return "".join(src)


def render_pdf_report(symbol: str, asset_type: Optional[str] = None) -> Optional[str]:
    """Typeset ``symbol``'s finished run; return the PDF path, or None.

    Returns None rather than raising when there is nothing to typeset — the
    caller decides whether that is a 404 or a degradation.
    """
    model = ReportModel(symbol, asset_type=asset_type)
    if not model.is_renderable():
        _logger.warning("no artifacts to typeset for %s", symbol)
        return None

    out_dir = model.dir / "pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / f"{model.symbol}_report.pdf"

    # Charts are written beside the source so Typst resolves them relatively;
    # a temp dir keeps the SVGs out of the reports tree.
    with tempfile.TemporaryDirectory(prefix=f"typst-{model.symbol}-") as tmp:
        work = Path(tmp)
        charts = _build_exhibits(model, work)
        source = build_typst_source(model, charts)
        (work / "report.typ").write_text(source, encoding="utf-8")
        try:
            import typst

            typst.compile(str(work / "report.typ"), output=str(pdf_path))
        except Exception as exc:
            _logger.warning("typst compile failed for %s: %s", symbol, exc)
            return None
    return str(pdf_path)
