"""Scorecard grading against synthetic bars — no network."""

from datetime import date, timedelta

from fastapi.testclient import TestClient

from src.stock_analysis.tools.providers import ROUTER
from src.stock_analysis.web import db
from src.stock_analysis.web.app import app
from src.stock_analysis.web.scorecard import grade_direction

client = TestClient(app)


def _bars(symbol, start, end):
    """Daily closes rising 1%/day from `start` — deterministic forward returns."""
    bars, px = [], 100.0
    d = date.fromisoformat(start)
    while d <= date.fromisoformat(end):
        bars.append({"date": d.isoformat(), "close": round(px, 2)})
        px *= 1.01
        d += timedelta(days=1)
    return {"symbol": symbol, "bars": bars}


def test_scorecard_grades_buy_against_rising_prices(monkeypatch):
    monkeypatch.setattr(ROUTER, "get_daily_bars", lambda s, a, b: _bars(s, a, b))
    rec_date = date.today() - timedelta(days=120)
    db.record_recommendation(
        "AAPL", rec_date.isoformat(), "buy", None, None, 0.8, 100.0
    )
    r = client.get("/api/scorecard")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["graded"] >= 1
    item = next(i for i in body["items"] if i["symbol"] == "AAPL")
    assert item["returns"]["30"] is not None and item["returns"]["30"] > 0
    assert item["grade"] == "correct"


def test_grade_direction_rules():
    assert grade_direction("hold", 3.0) == "correct"
    assert grade_direction("hold", 25.0) == "wrong"
    assert grade_direction("sell", -5.0) == "correct"
    assert grade_direction("buy", -5.0) == "wrong"
    assert grade_direction(None, 5.0) is None
    assert grade_direction("buy", None) is None
    # Unknown recommendation families stay ungradeable, not forced into a bucket.
    assert grade_direction("accumulate", 5.0) is None


def test_ungradeable_records_still_appear(monkeypatch):
    monkeypatch.setattr(
        ROUTER, "get_daily_bars", lambda s, a, b: {"symbol": s, "bars": []}
    )
    db.record_recommendation(
        "ZZZZ", "2026-08-20T00:00:00", "buy", None, None, None, None
    )
    r = client.get("/api/scorecard")
    item = next(i for i in r.json()["items"] if i["symbol"] == "ZZZZ")
    assert item["grade"] is None and item["returns"] == {}
