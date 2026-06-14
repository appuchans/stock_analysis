"""Network-free tests for the compact yfinance summarizers."""

import pandas as pd
import pytest

from src.stock_analysis.tools.yf_summaries import (
    summarize_analyst_data,
    summarize_dividends_splits,
    summarize_etf_portfolio,
    summarize_financial_statements,
    summarize_options_sentiment,
    summarize_ownership,
)


class _RaisingTicker:
    """Mimics yfinance behaviour where property access raises (e.g. 404)."""

    def __getattr__(self, name):
        raise RuntimeError(f"HTTP Error 404 for {name}")


class _FakeTicker:
    """Minimal stand-in with the attributes the summarizers read."""

    def __init__(self, **attrs):
        for k, v in attrs.items():
            setattr(self, k, v)

    def __getattr__(self, name):  # anything not provided behaves as missing
        raise AttributeError(name)


def _analyst_ticker():
    return _FakeTicker(
        analyst_price_targets={"current": 100.0, "low": 90.0, "mean": 120.0,
                               "median": 118.0, "high": 150.0},
        recommendations=pd.DataFrame({
            "period": ["0m", "-1m"],
            "strongBuy": [10, 9], "buy": [40, 41], "hold": [5, 5],
            "sell": [1, 1], "strongSell": [0, 0],
        }),
        upgrades_downgrades=pd.DataFrame(
            {"Firm": ["Acme"], "ToGrade": ["Buy"], "FromGrade": ["Hold"],
             "Action": ["up"], "currentPriceTarget": [130.0]},
            index=pd.DatetimeIndex([pd.Timestamp.now() - pd.Timedelta(days=10)],
                                   name="GradeDate"),
        ),
        earnings_estimate=pd.DataFrame(
            {"avg": [2.0], "low": [1.8], "high": [2.3], "yearAgoEps": [1.0],
             "numberOfAnalysts": [40], "growth": [1.0]},
            index=pd.Index(["0q"], name="period"),
        ),
        revenue_estimate=pd.DataFrame(
            {"avg": [50_000_000_000.0], "growth": [0.5], "numberOfAnalysts": [40]},
            index=pd.Index(["0q"], name="period"),
        ),
        eps_revisions=pd.DataFrame(
            {"upLast30days": [30], "downLast30days": [2]},
            index=pd.Index(["0q"], name="period"),
        ),
    )


class TestAnalystData:
    def test_full_summary(self):
        out = summarize_analyst_data(_analyst_ticker())
        assert out["price_targets"]["implied_upside_pct"] == 20.0
        assert out["recommendation_trend"][0]["buy"] == 40
        assert out["recent_rating_changes"][0]["firm"] == "Acme"
        assert out["eps_estimates"]["0q"]["avg"] == 2.0
        assert out["revenue_estimates_m"]["0q"]["avg"] == 50000.0
        assert out["eps_revisions"]["0q"]["up_30d"] == 30

    def test_raising_ticker_returns_partial_not_exception(self):
        out = summarize_analyst_data(_RaisingTicker())
        assert out == {}


class TestOwnership:
    def test_summary(self):
        ticker = _FakeTicker(
            major_holders=pd.DataFrame(
                {"Value": [0.04, 0.71, 0.74, 7000.0]},
                index=["insidersPercentHeld", "institutionsPercentHeld",
                       "institutionsFloatPercentHeld", "institutionsCount"],
            ),
            institutional_holders=pd.DataFrame({
                "Holder": ["Big Fund"], "pctHeld": [0.08],
                "Value": [400_000_000_000],
            }),
            insider_transactions=pd.DataFrame({
                "Shares": [1000, 2000],
                "Value": [100000, 0],
                "Text": ["Sale at price 100", "Purchase at price 90"],
                "Insider": ["CEO A", "CFO B"],
                "Position": ["CEO", "CFO"],
                "Transaction": ["", ""],
                "Start Date": [pd.Timestamp("2026-06-01"), pd.Timestamp("2026-05-20")],
            }),
        )
        out = summarize_ownership(ticker)
        assert out["holders_breakdown"]["insider_pct"] == 4.0
        assert out["top_institutions"][0]["holder"] == "Big Fund"
        assert out["insider_recent_summary"] == {"buys": 1, "sells": 1, "sampled": 2}

    def test_raising_ticker(self):
        assert summarize_ownership(_RaisingTicker()) == {}


class TestFinancialStatements:
    def test_income_yoy(self):
        cols = [pd.Timestamp("2026-01-31"), pd.Timestamp("2025-01-31")]
        ticker = _FakeTicker(
            income_stmt=pd.DataFrame(
                {cols[0]: [200e9, 120e9], cols[1]: [100e9, 60e9]},
                index=["Total Revenue", "Net Income"],
            ),
            balance_sheet=pd.DataFrame(
                {cols[0]: [300e9, 50e9]},
                index=["Total Assets", "Total Debt"],
            ),
            cashflow=pd.DataFrame(
                {cols[0]: [80e9, -10e9, 70e9]},
                index=["Operating Cash Flow", "Capital Expenditure", "Free Cash Flow"],
            ),
        )
        out = summarize_financial_statements(ticker)
        fy = out["annual_income"]["2026-01-31"]
        assert fy["revenue_m"] == 200000.0
        assert fy["revenue_yoy_pct"] == 100.0
        assert out["balance_sheet"]["2026-01-31"]["total_debt_m"] == 50000.0
        assert out["cash_flow"]["2026-01-31"]["free_cash_flow_m"] == 70000.0

    def test_raising_ticker(self):
        assert summarize_financial_statements(_RaisingTicker()) == {}


class TestOptionsSentiment:
    def test_no_options(self):
        out = summarize_options_sentiment(_FakeTicker(options=()))
        assert out["available"] is False

    def test_put_call_ratio(self):
        class _Chain:
            calls = pd.DataFrame({"strike": [100.0], "openInterest": [200],
                                  "volume": [100], "impliedVolatility": [0.4]})
            puts = pd.DataFrame({"strike": [100.0], "openInterest": [100],
                                 "volume": [50], "impliedVolatility": [0.45]})

        future = (pd.Timestamp.now() + pd.Timedelta(days=21)).strftime("%Y-%m-%d")
        ticker = _FakeTicker(
            options=(future,),
            option_chain=lambda expiry: _Chain(),
            analyst_price_targets={"current": 100.0},
        )
        out = summarize_options_sentiment(ticker)
        assert out["available"] is True
        assert out["put_call_oi_ratio"] == 0.5
        assert out["atm_call_iv_pct"] == 40.0


class TestDividendsAndETF:
    def test_dividends(self):
        idx = pd.DatetimeIndex([pd.Timestamp("2026-03-11"), pd.Timestamp("2026-06-04")])
        ticker = _FakeTicker(
            dividends=pd.Series([0.01, 0.25], index=idx),
            splits=pd.Series([10.0], index=pd.DatetimeIndex([pd.Timestamp("2024-06-10")])),
        )
        out = summarize_dividends_splits(ticker)
        assert out["recent_dividends"][-1] == {"date": "2026-06-04", "amount": 0.25}
        assert out["last_split"]["ratio"] == 10.0

    def test_etf_portfolio(self):
        class _Funds:
            sector_weightings = {"technology": 0.32, "healthcare": 0.10}
            asset_classes = {"stockPosition": 0.99}
            top_holdings = pd.DataFrame({"Name": ["Apple"], "Holding Percent": [0.07]})

        out = summarize_etf_portfolio(_FakeTicker(funds_data=_Funds()))
        assert out["sector_weightings_pct"]["technology"] == 32.0
        assert out["asset_classes_pct"]["stockPosition"] == 99.0
        assert len(out["top_holdings"]) == 1

    def test_etf_portfolio_raising(self):
        assert summarize_etf_portfolio(_RaisingTicker()) == {}


class TestInvestorFeatureSummarizers:
    def test_dcf_scenarios_math_and_guards(self):
        from src.stock_analysis.tools.yf_summaries import dcf_scenarios

        scen = dcf_scenarios(10.0, 20.0)
        assert [s["scenario"] for s in scen] == ["Bear", "Base", "Bull"]
        # Bull must exceed base must exceed bear
        vals = [s["intrinsic_per_share"] for s in scen]
        assert vals[0] < vals[1] < vals[2]
        assert dcf_scenarios(0, 20.0) == []
        assert dcf_scenarios(None, 20.0) == []
        # Growth is capped at 30%
        assert dcf_scenarios(10.0, 90.0)[1]["growth_pct"] == 30.0

    def test_catalysts_from_calendar(self):
        import datetime
        ticker = _FakeTicker(calendar={
            "Earnings Date": [datetime.date(2026, 8, 26)],
            "Earnings Average": 2.07925,
            "Revenue Average": 91_728_642_100,
            "Ex-Dividend Date": datetime.date(2026, 6, 3),
            "Dividend Date": datetime.date(2026, 6, 25),
        })
        from src.stock_analysis.tools.yf_summaries import summarize_catalysts

        out = summarize_catalysts(ticker)
        assert out["next_earnings_date"] == "2026-08-26"
        assert out["earnings_eps_estimate"] == 2.08
        assert out["earnings_revenue_estimate_m"] == 91728.6
        assert out["ex_dividend_date"] == "2026-06-03"

    def test_catalysts_raising_ticker(self):
        from src.stock_analysis.tools.yf_summaries import summarize_catalysts
        assert summarize_catalysts(_RaisingTicker()) == {}

    def test_peers_with_mocked_endpoint(self, monkeypatch):
        from src.stock_analysis.tools import yf_summaries as ys

        monkeypatch.setattr(ys, "fetch_peer_symbols", lambda s, limit=4: ["PEER"])

        class _YF:
            class Ticker:
                def __init__(self, sym):
                    self._sym = sym

                @property
                def info(self):
                    return {"marketCap": 1e12, "shortName": f"{self._sym} Co",
                            "trailingPE": 30.0, "forwardPE": 25.0,
                            "revenueGrowth": 0.4, "operatingMargins": 0.5}

        out = ys.summarize_peers("SUBJ", yf_module=_YF)
        rows = out["rows"]
        assert len(rows) == 2
        assert rows[0]["is_subject"] is True
        assert rows[1]["symbol"] == "PEER"
        assert rows[0]["market_cap_b"] == 1000.0
        assert rows[0]["revenue_growth_pct"] == 40.0

    def test_search_interest_absent_pytrends_is_graceful(self, monkeypatch):
        import builtins
        from src.stock_analysis.tools import yf_summaries as ys

        real_import = builtins.__import__

        def _no_pytrends(name, *a, **k):
            if name.startswith("pytrends"):
                raise ImportError("not installed")
            return real_import(name, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _no_pytrends)
        assert ys.summarize_search_interest("NVDA") == {}
