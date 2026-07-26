"""Tests for historical recommendation context formatting."""

from unittest.mock import MagicMock, patch

import pytest

from src.stock_analysis.crew.flow_crew import StockAnalysisFlow


class TestFormatHistoricalContext:
    def test_empty_history_returns_fallback(self):
        """When no prior analyses exist, return a safe fallback string."""
        flow = StockAnalysisFlow()
        flow.state.symbol = "AAPL"
        with patch("src.stock_analysis.web.db.list_rec_history", return_value=[]):
            context = flow._format_historical_context()
            assert "No prior analysis" in context
            assert "AAPL" in context

    def test_formats_multiple_prior_recommendations(self):
        """Format the last 5 entries from rec_history as a readable block."""
        flow = StockAnalysisFlow()
        flow.state.symbol = "AAPL"
        history = [
            {
                "recorded_at": "2025-01-10T10:00:00",
                "recommendation": "Buy",
                "confidence": 0.75,
                "target_price": 210.0,
                "price_at_rec": 195.0,
            },
            {
                "recorded_at": "2025-01-15T10:00:00",
                "recommendation": "Hold",
                "confidence": 0.65,
                "target_price": 215.0,
                "price_at_rec": 205.0,
            },
        ]
        with patch("src.stock_analysis.web.db.list_rec_history", return_value=history):
            context = flow._format_historical_context()
            assert "Prior analyses" in context
            assert "2025-01-15" in context  # newest should appear first
            assert "2025-01-10" in context
            assert "Hold" in context
            assert "Buy" in context
            assert "0.65" in context

    def test_takes_last_5_entries_only(self):
        """When history has more than 5 entries, take only the last 5."""
        flow = StockAnalysisFlow()
        flow.state.symbol = "AAPL"
        history = [
            {
                "recorded_at": f"2025-01-{i:02d}T10:00:00",
                "recommendation": "Buy",
                "confidence": 0.7,
                "target_price": 200.0,
                "price_at_rec": 190.0,
            }
            for i in range(1, 11)  # 10 entries
        ]
        with patch("src.stock_analysis.web.db.list_rec_history", return_value=history):
            context = flow._format_historical_context()
            # Should show only entries 6-10 (last 5), not entry 1 or 2
            assert "2025-01-10" in context
            assert "2025-01-06" in context
            assert "2025-01-05" not in context
            assert "2025-01-01" not in context

    def test_gracefully_handles_db_error(self):
        """When db.list_rec_history raises an exception, degrade to fallback."""
        flow = StockAnalysisFlow()
        flow.state.symbol = "AAPL"
        with patch(
            "src.stock_analysis.web.db.list_rec_history",
            side_effect=Exception("DB connection failed"),
        ):
            context = flow._format_historical_context()
            assert "No prior analysis" in context
            assert "AAPL" in context

    def test_gracefully_handles_missing_fields_in_history_entry(self):
        """Missing fields in history entries should be shown as '?', not crash."""
        flow = StockAnalysisFlow()
        flow.state.symbol = "AAPL"
        history = [
            {
                "recorded_at": "2025-01-10T10:00:00",
                "recommendation": "Buy",
                # missing confidence, target_price, price_at_rec
            },
        ]
        with patch("src.stock_analysis.web.db.list_rec_history", return_value=history):
            context = flow._format_historical_context()
            assert "2025-01-10" in context
            assert "Buy" in context
            assert "?" in context  # fallback for missing fields
            # Should not raise

    def test_formats_as_multiline_block(self):
        """Context should be formatted with proper newlines for readability."""
        flow = StockAnalysisFlow()
        flow.state.symbol = "AAPL"
        history = [
            {
                "recorded_at": "2025-01-10T10:00:00",
                "recommendation": "Buy",
                "confidence": 0.75,
                "target_price": 210.0,
                "price_at_rec": 195.0,
            },
        ]
        with patch("src.stock_analysis.web.db.list_rec_history", return_value=history):
            context = flow._format_historical_context()
            lines = context.split("\n")
            assert len(lines) >= 2  # header + at least one entry
            assert lines[0].startswith("Prior analyses")
