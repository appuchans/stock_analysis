"""Tests for report diffing (GET /api/reports/{symbol}/diff) and alert system."""

import json

import pytest
from fastapi.testclient import TestClient

from src.stock_analysis.config import settings as settings_mod
from src.stock_analysis.web.app import app

client = TestClient(app)

_REC_BUY = {
    "symbol": "AAPL",
    "recommendation": "Buy",
    "target_price": 210.0,
    "confidence": 0.78,
    "risk_level": "Medium",
    "reasoning": "strong earnings",
    "key_factors": ["growth"],
    "risks": ["macro risk", "competition"],
    "opportunities": ["AI upside"],
    "time_horizon": "12 months",
}

_REC_SELL = {
    "symbol": "AAPL",
    "recommendation": "Sell",
    "target_price": 175.0,
    "confidence": 0.55,
    "risk_level": "High",
    "reasoning": "valuation stretched",
    "key_factors": ["PE multiple"],
    "risks": ["competition", "regulation"],
    "opportunities": ["buyback"],
    "time_horizon": "6 months",
}


@pytest.fixture(autouse=True)
def _temp_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))
    monkeypatch.setattr(settings_mod.settings, "data_output_dir", str(tmp_path / "data"))
    yield tmp_path


# ── diff endpoint ──────────────────────────────────────────────────────────────

def test_diff_invalid_symbol_400(_temp_reports):
    r = client.get("/api/reports/AAPL$/diff")
    assert r.status_code == 400


def test_diff_no_current_rec_404(_temp_reports):
    r = client.get("/api/reports/AAPL/diff")
    assert r.status_code == 404


def test_diff_only_one_run_returns_no_diff(_temp_reports, tmp_path):
    sym_dir = tmp_path / "AAPL"
    sym_dir.mkdir(parents=True, exist_ok=True)
    (sym_dir / "AAPL_investment_recommendation.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    r = client.get("/api/reports/AAPL/diff")
    assert r.status_code == 200
    data = r.json()
    assert data["has_diff"] is False
    assert "Only one run" in data["message"]


def test_diff_detects_recommendation_change(_temp_reports, tmp_path):
    sym_dir = tmp_path / "AAPL"
    sym_dir.mkdir(parents=True, exist_ok=True)
    (sym_dir / "AAPL_investment_recommendation.json").write_text(
        json.dumps(_REC_SELL), encoding="utf-8"
    )
    (sym_dir / "AAPL_investment_recommendation_prev.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    r = client.get("/api/reports/AAPL/diff")
    assert r.status_code == 200
    data = r.json()
    assert data["has_diff"] is True
    assert data["recommendation_changed"] is True
    assert data["current"]["recommendation"] == "Sell"
    assert data["previous"]["recommendation"] == "Buy"


def test_diff_target_price_delta(_temp_reports, tmp_path):
    sym_dir = tmp_path / "AAPL"
    sym_dir.mkdir(parents=True, exist_ok=True)
    (sym_dir / "AAPL_investment_recommendation.json").write_text(
        json.dumps(_REC_SELL), encoding="utf-8"
    )
    (sym_dir / "AAPL_investment_recommendation_prev.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    data = client.get("/api/reports/AAPL/diff").json()
    assert data["target_price_delta"] == pytest.approx(175.0 - 210.0)


def test_diff_confidence_delta(_temp_reports, tmp_path):
    sym_dir = tmp_path / "AAPL"
    sym_dir.mkdir(parents=True, exist_ok=True)
    (sym_dir / "AAPL_investment_recommendation.json").write_text(
        json.dumps(_REC_SELL), encoding="utf-8"
    )
    (sym_dir / "AAPL_investment_recommendation_prev.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    data = client.get("/api/reports/AAPL/diff").json()
    assert data["confidence_delta"] == pytest.approx(0.55 - 0.78)


def test_diff_new_and_removed_risks(_temp_reports, tmp_path):
    sym_dir = tmp_path / "AAPL"
    sym_dir.mkdir(parents=True, exist_ok=True)
    (sym_dir / "AAPL_investment_recommendation.json").write_text(
        json.dumps(_REC_SELL), encoding="utf-8"
    )
    (sym_dir / "AAPL_investment_recommendation_prev.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    data = client.get("/api/reports/AAPL/diff").json()
    # "macro risk" was in prev but not cur -> removed
    assert "macro risk" in data["removed_risks"]
    # "regulation" is in cur but not prev -> new
    assert "regulation" in data["new_risks"]
    # "competition" is in both -> not in either list
    assert "competition" not in data["new_risks"]
    assert "competition" not in data["removed_risks"]


def test_diff_new_and_removed_opportunities(_temp_reports, tmp_path):
    sym_dir = tmp_path / "AAPL"
    sym_dir.mkdir(parents=True, exist_ok=True)
    (sym_dir / "AAPL_investment_recommendation.json").write_text(
        json.dumps(_REC_SELL), encoding="utf-8"
    )
    (sym_dir / "AAPL_investment_recommendation_prev.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    data = client.get("/api/reports/AAPL/diff").json()
    assert "AI upside" in data["removed_opportunities"]
    assert "buyback" in data["new_opportunities"]


def test_diff_same_recommendation_not_changed(_temp_reports, tmp_path):
    sym_dir = tmp_path / "AAPL"
    sym_dir.mkdir(parents=True, exist_ok=True)
    (sym_dir / "AAPL_investment_recommendation.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    # prev is identical to cur
    (sym_dir / "AAPL_investment_recommendation_prev.json").write_text(
        json.dumps(_REC_BUY), encoding="utf-8"
    )
    data = client.get("/api/reports/AAPL/diff").json()
    assert data["has_diff"] is True
    assert data["recommendation_changed"] is False
    assert data["target_price_delta"] == pytest.approx(0.0)
    assert data["new_risks"] == []
    assert data["removed_risks"] == []


# ── alert system ──────────────────────────────────────────────────────────────

def test_alerts_list_empty(_temp_reports):
    r = client.get("/api/alerts")
    assert r.status_code == 200
    assert r.json() == []


def test_alerts_list_returns_persisted_entries(_temp_reports, tmp_path):
    from src.stock_analysis.web.alerts import _append_alert
    entry = {"symbol": "AAPL", "fired_at": "2026-01-01T10:00:00", "reason": "test"}
    _append_alert(entry)
    r = client.get("/api/alerts")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    assert items[0]["symbol"] == "AAPL"


def test_check_and_dispatch_fires_on_recommendation_flip(_temp_reports, tmp_path):
    from src.stock_analysis.web.alerts import check_and_dispatch, get_alert_log
    check_and_dispatch("MSFT", _REC_SELL, _REC_BUY)
    log = get_alert_log()
    assert len(log) == 1
    assert log[0]["symbol"] == "MSFT"
    assert "recommendation changed" in log[0]["reason"]


def test_recommendation_flip_without_confidence_still_dispatches(_temp_reports, monkeypatch):
    from src.stock_analysis.web import alerts

    sent = []
    monkeypatch.setattr(alerts, "_send_email", lambda subject, body: sent.append(body))
    monkeypatch.setattr(alerts, "_send_webhook", lambda payload: sent.append(payload))

    alerts.check_and_dispatch(
        "MSFT", {"recommendation": "Sell"}, {"recommendation": "Buy"}
    )

    assert "confidence N/A" in sent[0]
    assert sent[1]["new_confidence"] is None


def test_check_and_dispatch_fires_on_confidence_drop(_temp_reports, tmp_path):
    from src.stock_analysis.web.alerts import check_and_dispatch, get_alert_log
    new_rec = dict(_REC_BUY, confidence=0.50)
    old_rec = dict(_REC_BUY, confidence=0.80)
    check_and_dispatch("NVDA", new_rec, old_rec)
    log = get_alert_log()
    assert any("confidence dropped" in e["reason"] for e in log)


def test_check_and_dispatch_no_alert_for_small_drop(_temp_reports, tmp_path):
    from src.stock_analysis.web.alerts import check_and_dispatch, get_alert_log
    new_rec = dict(_REC_BUY, confidence=0.70)
    old_rec = dict(_REC_BUY, confidence=0.75)
    check_and_dispatch("GOOG", new_rec, old_rec)
    assert get_alert_log() == []


def test_check_and_dispatch_no_alert_same_rec(_temp_reports):
    from src.stock_analysis.web.alerts import check_and_dispatch, get_alert_log
    check_and_dispatch("AAPL", _REC_BUY, _REC_BUY)
    assert get_alert_log() == []


def test_check_and_dispatch_skips_when_missing(_temp_reports):
    from src.stock_analysis.web.alerts import check_and_dispatch, get_alert_log
    check_and_dispatch("AAPL", None, _REC_BUY)
    check_and_dispatch("AAPL", _REC_BUY, None)
    assert get_alert_log() == []


def test_save_alert_settings_endpoint(_temp_reports):
    r = client.post("/api/settings/alerts", json={"alert_email": "test@example.com"})
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
    # Verify the in-memory setting was updated
    assert settings_mod.settings.alert_email == "test@example.com"


def test_alert_log_capped_at_50(_temp_reports):
    from src.stock_analysis.web.alerts import _append_alert, get_alert_log
    for i in range(60):
        _append_alert({"symbol": f"S{i}", "fired_at": "2026-01-01", "reason": "x"})
    log = get_alert_log()
    assert len(log) == 50
    # Most recent entry should be first (last appended = S59)
    assert log[0]["symbol"] == "S59"


# ── _paths helpers ─────────────────────────────────────────────────────────────

@pytest.mark.unit
def test_prev_recommendation_path_returns_correct_filename(_temp_reports):
    from src.stock_analysis.web._paths import prev_recommendation_path
    p = prev_recommendation_path("AAPL")
    assert p is not None
    assert p.name == "AAPL_investment_recommendation_prev.json"


@pytest.mark.unit
def test_prev_recommendation_path_invalid_symbol(_temp_reports):
    from src.stock_analysis.web._paths import prev_recommendation_path
    assert prev_recommendation_path("AAPL$") is None
    assert prev_recommendation_path("") is None
