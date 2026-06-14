"""Serving the HTML report and chart JSON, with traversal/validation guards."""

import json

import pytest
from fastapi.testclient import TestClient

from src.stock_analysis.config import settings as settings_mod
from src.stock_analysis.web.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _temp_reports(monkeypatch, tmp_path):
    monkeypatch.setattr(settings_mod.settings, "report_output_dir", str(tmp_path))
    sym = "AAPL"
    (tmp_path / sym / "html").mkdir(parents=True)
    (tmp_path / sym / "html" / f"{sym}_report.html").write_text("<html>report</html>", encoding="utf-8")
    (tmp_path / sym / f"{sym}_chart_data.json").write_text(json.dumps({"k": 1}), encoding="utf-8")
    yield tmp_path


def test_serves_html_report():
    r = client.get("/api/reports/AAPL/html")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "report" in r.text


def test_serves_chart_json():
    r = client.get("/api/reports/AAPL/chart")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json() == {"k": 1}


def test_missing_symbol_404():
    assert client.get("/api/reports/ZZZZ/html").status_code == 404
    assert client.get("/api/reports/ZZZZ/chart").status_code == 404


@pytest.mark.parametrize("bad", ["..", "a/b", "%2e%2e", "../../etc", "AAPL$", "1ABC"])
def test_invalid_or_traversal_symbol_rejected(bad):
    r = client.get(f"/api/reports/{bad}/html")
    assert r.status_code == 404


def test_lowercase_symbol_case_folds_to_report():
    # Case-insensitive convenience: lowercase resolves to the stored report.
    assert client.get("/api/reports/aapl/html").status_code == 200
