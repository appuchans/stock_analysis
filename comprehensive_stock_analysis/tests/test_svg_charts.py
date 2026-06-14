"""Tests for the dependency-free SVG chart builders."""

from src.stock_analysis.tools._svg_charts import bar_chart_svg, line_chart_svg


class TestLineChart:
    def test_renders_polyline_and_labels(self):
        pts = [("01-01", 100.0), ("02-01", 110.0), ("03-01", 105.0)]
        svg = line_chart_svg(pts, title="Price")
        assert svg.startswith("<svg")
        assert "<polyline" in svg and "<polygon" in svg
        assert "Price" in svg
        assert "$105" in svg  # last-value marker label

    def test_insufficient_points_returns_empty(self):
        assert line_chart_svg([]) == ""
        assert line_chart_svg([("01-01", 100.0)]) == ""
        assert line_chart_svg([("01-01", None), ("02-01", None)]) == ""

    def test_flat_series_does_not_divide_by_zero(self):
        svg = line_chart_svg([("a", 50.0), ("b", 50.0)])
        assert "<svg" in svg


class TestBarChart:
    def test_vertical_bars_with_values(self):
        svg = bar_chart_svg(["Q1", "Q2", "Q3"], [100.0, 200.0, 150.0], title="Revenue")
        assert svg.count("<rect") == 3
        assert "Revenue" in svg and "Q2" in svg
        assert "$200M" in svg

    def test_negative_values_colored_red(self):
        svg = bar_chart_svg(["a", "b"], [100.0, -40.0])
        assert "#c53030" in svg

    def test_horizontal_mode(self):
        svg = bar_chart_svg(
            ["Technology", "Healthcare"], [32.0, 10.0],
            unit="", suffix="%", horizontal=True,
        )
        assert svg.count("<rect") == 2
        assert "32%" in svg

    def test_empty_returns_empty(self):
        assert bar_chart_svg([], []) == ""
