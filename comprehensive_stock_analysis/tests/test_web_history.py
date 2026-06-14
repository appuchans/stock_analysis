"""History gallery built from a seeded reports directory."""

import json

import pytest
from fastapi.testclient import TestClient

from src.stock_analysis.config import settings as settings_mod
from src.stock_analysis.web.app import app

client = TestClient(app)


def _seed(root, sym, *, html=True, chart=True, rec=True):
    d = root / sym
    if html:
        (d / "html").mkdir(parents=True, exist_ok=True)
        (d / "html" / f"{sym}_report.html").write_text("<html>ok</html>", encoding="utf-8")
    else:
        d.mkdir(parents=True, exist_ok=True)
    if chart:
        (d / f"{sym}_chart_data.json").write_text(json.dumps({
            "company": {"name": f"{sym} Inc", "sector": "Tech"},
            "key_stats": {"current_price": 100.0, "market_cap": 2e12, "pe_ratio": 25.0,
                          "high_52w": 120.0, "low_52w": 80.0},
        }), encoding="utf-8")
    if rec:
        (d / f"{sym}_investment_recommendation.json").write_text(json.dumps({
            "recommendation": "Buy", "target_price": 130.0, "confidence": 0.8, "risk_level": "Medium",
        }), encoding="utf-8")


@pytest.fixture(autouse=True)
def _temp_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))
    yield tmp_path


def test_history_lists_seeded_reports(_temp_reports):
    _seed(_temp_reports, "AAPL")
    items = client.get("/api/history").json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["symbol"] == "AAPL"
    assert it["name"] == "AAPL Inc"
    assert it["recommendation"] == "Buy"
    assert it["target_price"] == 130.0
    assert it["current_price"] == 100.0
    assert it["has_html"] and it["has_chart"]


def test_symbol_without_html_is_skipped(_temp_reports):
    _seed(_temp_reports, "AAPL")
    _seed(_temp_reports, "NOHTML", html=False)
    syms = {it["symbol"] for it in client.get("/api/history").json()["items"]}
    assert syms == {"AAPL"}


def test_partial_files_tolerated(_temp_reports):
    _seed(_temp_reports, "BARE", chart=False, rec=False)
    items = client.get("/api/history").json()["items"]
    assert items[0]["symbol"] == "BARE"
    assert items[0]["has_chart"] is False
    assert items[0]["recommendation"] is None
