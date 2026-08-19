"""The typeset research note, served over HTTP.

Until this existed the PDF renderer was unreachable: nothing called it, and the
UI's Download button opened the HTML report and invoked window.print(), which
stamped the browser's own chrome — including a localhost URL — onto every page.
"""

import pytest
from fastapi.testclient import TestClient

from src.stock_analysis.web.app import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    from src.stock_analysis.config.settings import settings

    monkeypatch.setattr(settings, "report_output_dir", str(tmp_path))
    return TestClient(app)


def _seed(tmp_path, symbol="TEST"):
    import json

    d = tmp_path / symbol
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{symbol}_chart_data.json").write_text(
        json.dumps(
            {
                "asset_type": "stock",
                "company": {"name": "Test Corp", "exchange": "NYQ"},
                "key_stats": {
                    "current_price": 100.0,
                    "low_52w": 80.0,
                    "high_52w": 120.0,
                },
                "snapshot": {"as_of": "2026-08-19T09:00:00", "price": 100.0},
                "valuation_scenarios": [
                    {
                        "scenario": "Base",
                        "intrinsic_per_share": 110.0,
                        "growth_pct": 5.0,
                        "discount_pct": 9.0,
                        "terminal_pct": 2.5,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (d / f"{symbol}_investment_recommendation.json").write_text(
        json.dumps(
            {
                "recommendation": "Hold",
                "target_price": 105.0,
                "summary": "A test summary.",
                "time_horizon": "12 months",
            }
        ),
        encoding="utf-8",
    )
    (d / f"{symbol}_comprehensive_report.md").write_text(
        "## Investment Thesis\n\nThe **thesis** rests on one pillar.\n",
        encoding="utf-8",
    )


class TestPdfEndpoint:
    def test_serves_a_real_pdf(self, client, tmp_path):
        _seed(tmp_path)
        r = client.get("/api/reports/TEST/pdf")
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content.startswith(b"%PDF-")
        assert "TEST_research_note.pdf" in r.headers.get("content-disposition", "")

    def test_unknown_symbol_is_404_not_a_stack_trace(self, client):
        assert client.get("/api/reports/NOPE/pdf").status_code == 404

    def test_path_traversal_is_refused(self, client):
        assert client.get("/api/reports/..%2F..%2Fetc/pdf").status_code == 404
