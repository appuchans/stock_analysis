"""Network-free tests for the research exhibits.

These assert the contract callers rely on — a valid SVG, or "" meaning "omit
this exhibit" — rather than pixel output, which is not usefully testable.
"""

from src.stock_analysis.tools import _charts as C


def _is_svg(s):
    return s.startswith("<svg") and s.rstrip().endswith("</svg>")


class TestFootballField:
    def test_renders_with_bands_and_markers(self):
        svg = C.football_field(
            [("52-week range", 199.0, 332.0), ("DCF bear-bull", 185.0, 325.0)],
            current_price=231.02,
            target_price=245.0,
        )
        assert _is_svg(svg)

    def test_no_bands_is_omitted_not_an_error(self):
        assert C.football_field([]) == ""

    def test_inverted_band_is_dropped(self):
        """high < low is bad data, not something to draw."""
        assert C.football_field([("bad", 300.0, 100.0)]) == ""


class TestPriceVsBenchmark:
    def test_renders_both_series(self):
        price = [{"date": f"2026-0{i}-01", "close": 100.0 + i} for i in range(1, 9)]
        bench = [{"date": f"2026-0{i}-01", "close": 200.0 + i} for i in range(1, 9)]
        assert _is_svg(C.price_vs_benchmark(price, bench, symbol="IBM"))

    def test_renders_without_a_benchmark(self):
        price = [{"date": f"2026-0{i}-01", "close": 100.0 + i} for i in range(1, 9)]
        assert _is_svg(C.price_vs_benchmark(price, None, symbol="IBM"))

    def test_single_point_cannot_make_a_line(self):
        assert C.price_vs_benchmark([{"date": "2026-01-01", "close": 1.0}]) == ""

    def test_non_numeric_closes_are_skipped(self):
        assert C.price_vs_benchmark([{"date": "x", "close": None}] * 5) == ""


class TestPeerScatter:
    def test_renders_with_subject_highlighted(self):
        rows = [
            {
                "symbol": "IBM",
                "fwd_pe": 17.7,
                "revenue_growth_pct": 1.1,
                "market_cap_b": 219.8,
                "is_subject": True,
            },
            {
                "symbol": "ACN",
                "fwd_pe": 12.1,
                "revenue_growth_pct": 5.6,
                "market_cap_b": 108.7,
            },
        ]
        assert _is_svg(C.peer_scatter(rows))

    def test_one_plottable_row_is_not_a_comparison(self):
        rows = [
            {"symbol": "IBM", "fwd_pe": 17.7, "revenue_growth_pct": 1.1},
            {"symbol": "X", "fwd_pe": None, "revenue_growth_pct": None},
        ]
        assert C.peer_scatter(rows) == ""


class TestFcfVsCapex:
    def test_renders_and_tolerates_capex_sign(self):
        """yfinance reports capex negative; magnitude is what is plotted."""
        neg = C.fcf_vs_capex(
            ["2024", "2025"], [100.0, 110.0], [-40.0, -45.0], [60.0, 65.0]
        )
        pos = C.fcf_vs_capex(
            ["2024", "2025"], [100.0, 110.0], [40.0, 45.0], [60.0, 65.0]
        )
        assert _is_svg(neg) and _is_svg(pos)

    def test_no_periods_is_omitted(self):
        assert C.fcf_vs_capex([], [], [], []) == ""


class TestSegmentMix:
    def test_renders_and_shortens_labels(self):
        svg = C.segment_mix(
            {
                "Microsoft Three Six Five Commercial Products And Cloud Services": 1e11,
                "Server Products And Cloud Services": 1.3e11,
            },
            total=3.3e11,
        )
        assert _is_svg(svg)

    def test_shorten_segment_is_readable_and_bounded(self):
        out = C.shorten_segment(
            "Microsoft Three Six Five Commercial Products And Cloud Services"
        )
        assert len(out) <= 26
        assert "365" in out

    def test_short_label_is_left_alone(self):
        assert C.shorten_segment("Windows") == "Windows"

    def test_empty_or_zero_segments_omitted(self):
        assert C.segment_mix({}) == ""
        assert C.segment_mix({"A": 0.0}) == ""


class TestGuard:
    def test_a_broken_exhibit_returns_empty_rather_than_raising(self):
        """A chart failure must never take a report down with it."""
        assert C.football_field([("x", "not-a-number", 10.0)]) == ""
