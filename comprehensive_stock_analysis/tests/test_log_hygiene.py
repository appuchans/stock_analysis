"""Tests for log rotation and noise filtering."""

import logging

from src.stock_analysis.main import _drop_noise, _quiet_noisy_loggers, _rotate_if_large


class TestLogHygiene:
    def test_rotation_only_when_large(self, tmp_path):
        small = tmp_path / "app.log"
        small.write_text("x" * 100)
        _rotate_if_large(small, max_bytes=1000)
        assert small.exists()  # untouched below threshold

        big = tmp_path / "crew.log"
        big.write_text("x" * 2000)
        _rotate_if_large(big, max_bytes=1000)
        assert not big.exists()
        assert (tmp_path / "crew.log.old").exists()

    def test_rotation_handles_log_txt_double_suffix(self, tmp_path):
        f = tmp_path / "crew_output.log.txt"
        f.write_text("x" * 2000)
        _rotate_if_large(f, max_bytes=1000)
        assert (tmp_path / "crew_output.log.txt.old").exists()

    def test_noise_filter_drops_tool_validation_lines(self):
        def _rec(msg):
            return logging.LogRecord("root", logging.INFO, "", 0, msg, None, None)

        assert _drop_noise(_rec("OpenAI: Successfully validated tool 'valuation_tool'")) is False
        assert _drop_noise(_rec("[token-usage] symbol=NVDA input=1000")) is True
        assert _drop_noise(_rec("Analysis failed for NVDA")) is True

    def test_noisy_loggers_quieted(self):
        _quiet_noisy_loggers()
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("yfinance").level == logging.CRITICAL
