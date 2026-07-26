"""Tests for GET /api/providers/status."""

from fastapi.testclient import TestClient

from src.stock_analysis.web.app import app

client = TestClient(app)


def test_providers_status_reports_yfinance_always_configured():
    r = client.get("/api/providers/status")
    assert r.status_code == 200
    body = r.json()
    assert body["yfinance"]["configured"] is True


def test_providers_status_reflects_missing_premium_keys(monkeypatch):
    from src.stock_analysis.config.settings import settings

    monkeypatch.setattr(settings, "fmp_api_key", None)
    monkeypatch.setattr(settings, "polygon_api_key", None)
    body = client.get("/api/providers/status").json()
    assert body["fmp"]["configured"] is False
    assert body["polygon"]["configured"] is False


def test_providers_status_reflects_configured_premium_key(monkeypatch):
    from src.stock_analysis.config.settings import settings

    monkeypatch.setattr(settings, "fmp_api_key", "test-key")
    body = client.get("/api/providers/status").json()
    assert body["fmp"]["configured"] is True
