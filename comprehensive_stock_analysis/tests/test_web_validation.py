"""Input validation on the analyze endpoint + unknown job handling."""

from fastapi.testclient import TestClient

from src.stock_analysis.web.app import app

client = TestClient(app)


def test_invalid_symbol_422():
    assert client.post("/api/analyze", json={"symbol": "../etc"}).status_code == 422
    assert client.post("/api/analyze", json={"symbol": ""}).status_code == 422
    assert client.post("/api/analyze", json={"symbol": "TOOLONGSYMBOL"}).status_code == 422


def test_invalid_depth_or_asset_422():
    assert client.post("/api/analyze", json={"symbol": "AAPL", "depth": "ultra"}).status_code == 422
    assert client.post("/api/analyze", json={"symbol": "AAPL", "asset_type": "crypto"}).status_code == 422


def test_unknown_job_404():
    assert client.get("/api/jobs/does-not-exist").status_code == 404
