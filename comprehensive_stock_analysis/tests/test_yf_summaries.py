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
        analyst_price_targets={
            "current": 100.0,
            "low": 90.0,
            "mean": 120.0,
            "median": 118.0,
            "high": 150.0,
        },
        recommendations=pd.DataFrame(
            {
                "period": ["0m", "-1m"],
                "strongBuy": [10, 9],
                "buy": [40, 41],
                "hold": [5, 5],
                "sell": [1, 1],
                "strongSell": [0, 0],
            }
        ),
        upgrades_downgrades=pd.DataFrame(
            {
                "Firm": ["Acme"],
                "ToGrade": ["Buy"],
                "FromGrade": ["Hold"],
                "Action": ["up"],
                "currentPriceTarget": [130.0],
            },
            index=pd.DatetimeIndex(
                [pd.Timestamp.now() - pd.Timedelta(days=10)], name="GradeDate"
            ),
        ),
        earnings_estimate=pd.DataFrame(
            {
                "avg": [2.0],
                "low": [1.8],
                "high": [2.3],
                "yearAgoEps": [1.0],
                "numberOfAnalysts": [40],
                "growth": [1.0],
            },
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
                index=[
                    "insidersPercentHeld",
                    "institutionsPercentHeld",
                    "institutionsFloatPercentHeld",
                    "institutionsCount",
                ],
            ),
            institutional_holders=pd.DataFrame(
                {
                    "Holder": ["Big Fund"],
                    "pctHeld": [0.08],
                    "Value": [400_000_000_000],
                }
            ),
            insider_transactions=pd.DataFrame(
                {
                    "Shares": [1000, 2000],
                    "Value": [100000, 0],
                    "Text": ["Sale at price 100", "Purchase at price 90"],
                    "Insider": ["CEO A", "CFO B"],
                    "Position": ["CEO", "CFO"],
                    "Transaction": ["", ""],
                    "Start Date": [
                        pd.Timestamp("2026-06-01"),
                        pd.Timestamp("2026-05-20"),
                    ],
                }
            ),
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
            calls = pd.DataFrame(
                {
                    "strike": [100.0],
                    "openInterest": [200],
                    "volume": [100],
                    "impliedVolatility": [0.4],
                }
            )
            puts = pd.DataFrame(
                {
                    "strike": [100.0],
                    "openInterest": [100],
                    "volume": [50],
                    "impliedVolatility": [0.45],
                }
            )

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
            splits=pd.Series(
                [10.0], index=pd.DatetimeIndex([pd.Timestamp("2024-06-10")])
            ),
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

        ticker = _FakeTicker(
            calendar={
                "Earnings Date": [datetime.date(2026, 8, 26)],
                "Earnings Average": 2.07925,
                "Revenue Average": 91_728_642_100,
                "Ex-Dividend Date": datetime.date(2026, 6, 3),
                "Dividend Date": datetime.date(2026, 6, 25),
            }
        )
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

        monkeypatch.setattr(ys, "fetch_peer_symbols", lambda s, **kwargs: ["PEER"])

        class _YF:
            class Ticker:
                def __init__(self, sym):
                    self._sym = sym

                @property
                def info(self):
                    return {
                        "marketCap": 1e12,
                        "shortName": f"{self._sym} Co",
                        "trailingPE": 30.0,
                        "forwardPE": 25.0,
                        "revenueGrowth": 0.4,
                        "operatingMargins": 0.5,
                    }

        out = ys.summarize_peers("SUBJ", yf_module=_YF)
        rows = out["rows"]
        assert len(rows) == 2
        assert rows[0]["is_subject"] is True
        assert rows[1]["symbol"] == "PEER"
        assert rows[0]["market_cap_b"] == 1000.0
        assert rows[0]["revenue_growth_pct"] == 40.0

    def test_fetch_peer_symbols_web_search_filters_junk_and_sector_mismatch(
        self, monkeypatch
    ):
        """Web-search peer discovery should keep only real, sector-matching
        competitors and drop stopword noise and cross-sector false positives
        (the bug this replaces: Yahoo's recommendation endpoint pairing PEGA
        with an unrelated fleet-payments company)."""
        from src.stock_analysis.tools import _http
        from src.stock_analysis.tools import yf_summaries as ys

        html = b"""
        <div class="result">
          <a class="result__a">GWRE and PRGS are top PEGA competitors</a>
          <a class="result__snippet">Also mentioned: WEX and THE market</a>
        </div>
        """

        class _Resp:
            content = html

            def raise_for_status(self):
                pass

        monkeypatch.setattr(_http, "get", lambda *a, **k: _Resp())

        class _FakeYFTicker:
            def __init__(self, sym):
                self._sym = sym

            @property
            def info(self):
                data = {
                    "GWRE": {"marketCap": 1e10, "sector": "Technology"},
                    "PRGS": {"marketCap": 2e9, "sector": "Technology"},
                    "WEX": {"marketCap": 5e9, "sector": "Financial Services"},
                }
                return data.get(self._sym, {})

        class _FakeYF:
            Ticker = _FakeYFTicker

        import sys

        monkeypatch.setitem(sys.modules, "yfinance", _FakeYF)

        peers = ys.fetch_peer_symbols("PEGA", sector="Technology", limit=4)

        assert "GWRE" in peers
        assert "PRGS" in peers
        assert "WEX" not in peers  # sector mismatch — not a real peer
        assert "THE" not in peers  # stopword, not a ticker

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


class TestHolderAggregation:
    """13F filer rows must collapse to economic owners before truncation."""

    def test_filers_merge_into_one_family(self):
        from src.stock_analysis.tools.yf_summaries import _aggregate_holders

        rows = _aggregate_holders(
            [
                {
                    "Holder": "Vanguard Capital Management",
                    "pctHeld": 0.065,
                    "Value": 240_000_000_000,
                },
                {
                    "Holder": "Vanguard Portfolio Management",
                    "pctHeld": 0.0226,
                    "Value": 83_000_000_000,
                },
                {
                    "Holder": "Blackrock Inc.",
                    "pctHeld": 0.071,
                    "Value": 262_000_000_000,
                },
            ]
        )
        vanguard = next(r for r in rows if r["holder"] == "Vanguard Group")
        # 6.50% + 2.26% — reported separately this understated the real stake.
        assert vanguard["pct_held"] == 8.76
        assert vanguard["filers"] == 2
        # A single-filer holder carries no filer count.
        assert "filers" not in next(r for r in rows if r["holder"] == "BlackRock")

    def test_merge_happens_before_truncation(self):
        """A split holder must not lose slots to its own duplicate rows."""
        from src.stock_analysis.tools.yf_summaries import _aggregate_holders

        records = [
            {"Holder": f"Vanguard Fund {i}", "pctHeld": 0.01, "Value": 1e9}
            for i in range(8)
        ] + [{"Holder": "Real Holder", "pctHeld": 0.05, "Value": 5e9}]
        rows = _aggregate_holders(records, top=2)
        assert [r["holder"] for r in rows] == ["Vanguard Group", "Real Holder"]


class TestDividendCagr:
    def test_partial_current_year_excluded(self):
        """The in-progress year must not be compared against full years.

        MSFT scored -4.6% while the payout was rising, because 2026 had only
        two of four payments banked.
        """
        from datetime import datetime

        from src.stock_analysis.tools.yf_summaries import summarize_dividends_splits

        this_year = datetime.now().year
        first_year = this_year - 6
        dates, amounts = [], []
        for year in range(first_year, this_year + 1):
            paid = 2 if year == this_year else 4  # current year still in progress
            for q in range(paid):
                dates.append(pd.Timestamp(f"{year}-{3 * q + 1:02d}-15"))
                amounts.append(0.50 + 0.05 * (year - first_year))
        out = summarize_dividends_splits(
            _FakeTicker(dividends=pd.Series(amounts, index=pd.DatetimeIndex(dates)))
        )
        assert out["dividend_cagr_5y_pct"] > 0
        assert out["dividend_cagr_window"] == f"{first_year}-{this_year - 1}"


class TestFcfDcf:
    """The valuation model the reviewer called unusable, rebuilt on cash flow."""

    def test_equity_bridge_and_ordering(self):
        from src.stock_analysis.tools.yf_summaries import fcf_dcf_scenarios

        rows = fcf_dcf_scenarios(
            fcf_m=12_000,
            shares_m=930,
            net_debt_m=47_000,
            base_wacc_pct=8.5,
            growth_pct=6.0,
        )
        assert [r["scenario"] for r in rows] == ["Bear", "Base", "Bull"]
        # More growth must be worth more; the old grid tied the cheapest
        # discount rate to the highest growth and could invert this.
        assert rows[0]["intrinsic_per_share"] < rows[1]["intrinsic_per_share"]
        assert rows[1]["intrinsic_per_share"] < rows[2]["intrinsic_per_share"]
        # Equity = EV - net debt, per share.
        base = rows[1]
        expected = (base["enterprise_value_m"] - 47_000) / 930
        # abs=0.01 because intrinsic_per_share is reported to the cent.
        assert base["intrinsic_per_share"] == pytest.approx(expected, abs=0.01)

    def test_terminal_spread_is_floored(self):
        """A tiny WACC-minus-g spread makes the residual swamp the forecast."""
        from src.stock_analysis.tools.yf_summaries import fcf_dcf_scenarios

        rows = fcf_dcf_scenarios(
            fcf_m=1_000,
            shares_m=100,
            base_wacc_pct=3.0,  # below terminal+5
            growth_pct=5.0,
            terminal_pct=2.5,
        )
        assert all(r["discount_pct"] >= 7.5 for r in rows)

    def test_net_cash_raises_value_above_enterprise_value(self):
        from src.stock_analysis.tools.yf_summaries import fcf_dcf_scenarios

        rows = fcf_dcf_scenarios(
            fcf_m=5_000, shares_m=1_000, net_debt_m=-10_000, base_wacc_pct=9.0
        )
        base = rows[1]
        assert base["intrinsic_per_share"] > base["enterprise_value_m"] / 1_000

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"fcf_m": 0, "shares_m": 100},
            {"fcf_m": -500, "shares_m": 100},  # loss-making: model doesn't apply
            {"fcf_m": 1_000, "shares_m": 0},
        ],
    )
    def test_guards_return_empty(self, kwargs):
        from src.stock_analysis.tools.yf_summaries import fcf_dcf_scenarios

        assert fcf_dcf_scenarios(**kwargs) == []

    def test_wacc_blends_equity_and_after_tax_debt(self):
        from src.stock_analysis.tools.yf_summaries import wacc_pct

        # All equity, beta 1.0 -> pure CAPM: 4 + 1*5 = 9.
        assert wacc_pct(beta=1.0, market_cap_m=1_000, total_debt_m=0) == 9.0
        # Adding debt must pull it down (after-tax debt is cheaper than equity).
        assert wacc_pct(beta=1.0, market_cap_m=1_000, total_debt_m=1_000) < 9.0
        # Missing beta falls back to 1.0 rather than exploding.
        assert wacc_pct(beta=None, market_cap_m=1_000, total_debt_m=0) == 9.0


class TestPeerSymbolOverride:
    """Provider-supplied peers must be usable when web discovery finds none.

    IBM shipped a peer table whose every cell read "Not available" because
    fetch_peer_symbols (a keyless web search) returned nothing — while the
    provider chain had already supplied MU/CSCO/SAP/CRM/ACN/INFY.
    """

    class _YF:
        class Ticker:
            def __init__(self, sym):
                self._sym = sym

            @property
            def info(self):
                return {
                    "marketCap": 2e11,
                    "shortName": f"{self._sym} Co",
                    "trailingPE": 20.0,
                    "forwardPE": 17.0,
                    "revenueGrowth": 0.05,
                    "operatingMargins": 0.16,
                }

    def test_explicit_peers_skip_web_discovery(self, monkeypatch):
        from src.stock_analysis.tools import yf_summaries as ys

        def _boom(*a, **k):
            raise AssertionError("discovery must not run when peers are supplied")

        monkeypatch.setattr(ys, "fetch_peer_symbols", _boom)
        out = ys.summarize_peers(
            "IBM", yf_module=self._YF, peer_symbols=["CSCO", "SAP"]
        )
        assert [r["symbol"] for r in out["rows"]] == ["IBM", "CSCO", "SAP"]
        assert out["rows"][0]["is_subject"] is True
        # The whole point: peers carry real multiples, not blanks.
        assert all(r["pe_ttm"] == 20.0 for r in out["rows"])

    def test_falls_back_to_discovery_when_no_peers_supplied(self, monkeypatch):
        from src.stock_analysis.tools import yf_summaries as ys

        monkeypatch.setattr(ys, "fetch_peer_symbols", lambda *a, **k: ["ACN"])
        out = ys.summarize_peers("IBM", yf_module=self._YF)
        assert [r["symbol"] for r in out["rows"]] == ["IBM", "ACN"]


class TestValuationMultiples:
    """EV/EBITDA, PEG and FCF yield — the multiples a reviewer asked for.

    Nothing computed these, so a report asserted "16.8 times enterprise value
    to EBITDA" from the model's own knowledge. It happened to be right, which
    is worse than being wrong: unsourced and unverifiable either way. All three
    are present in ticker.info and were simply never read.
    """

    class _YF:
        class Ticker:
            def __init__(self, sym):
                self._sym = sym

            @property
            def info(self):
                return {
                    "marketCap": 2.0e11,
                    "shortName": "Test Co",
                    "enterpriseToEbitda": 16.781,
                    "trailingPegRatio": 2.329,
                    "freeCashflow": 1.08e10,
                }

    def test_multiples_are_read_and_fcf_yield_derived(self):
        from src.stock_analysis.tools.yf_summaries import _key_metrics

        m = _key_metrics("IBM", yf_module=self._YF)
        assert m["ev_to_ebitda"] == 16.8
        assert m["peg"] == 2.33
        # 10.8bn / 200bn = 5.4%
        assert m["fcf_yield_pct"] == 5.4

    def test_absent_inputs_yield_none_not_a_guess(self):
        from src.stock_analysis.tools.yf_summaries import _key_metrics

        class _Bare:
            class Ticker:
                def __init__(self, sym):
                    pass

                @property
                def info(self):
                    return {"marketCap": 1e11, "shortName": "X"}

        m = _key_metrics("X", yf_module=_Bare)
        assert m["ev_to_ebitda"] is None
        assert m["peg"] is None
        assert m["fcf_yield_pct"] is None


class TestSelectComparables:
    """A provider's peer list is not a comparables set.

    FMP returns Micron for IBM — memory semiconductors against enterprise IT
    services — ranked by market capitalisation, so taking the largest names put
    the least similar business at the top of the table. It also reported Micron
    at $1,055B, several times its real size, so the ranking key was wrong too.
    """

    SUBJECT = {
        "symbol": "IBM",
        "is_subject": True,
        "sector": "Technology",
        "industry": "Information Technology Services",
        "market_cap_b": 223.8,
    }

    def _rows(self):
        return [
            self.SUBJECT,
            {
                "symbol": "MU",
                "sector": "Technology",
                "industry": "Semiconductors",
                "market_cap_b": 1055.3,
            },
            {
                "symbol": "CSCO",
                "sector": "Technology",
                "industry": "Communication Equipment",
                "market_cap_b": 441.0,
            },
            {
                "symbol": "ACN",
                "sector": "Technology",
                "industry": "Information Technology Services",
                "market_cap_b": 112.9,
            },
            {
                "symbol": "INFY",
                "sector": "Technology",
                "industry": "Information Technology Services",
                "market_cap_b": 49.4,
            },
            {
                "symbol": "JPM",
                "sector": "Financial Services",
                "industry": "Banks",
                "market_cap_b": 700.0,
            },
        ]

    def test_industry_match_wins_over_size(self):
        from src.stock_analysis.tools.yf_summaries import select_comparables

        picked = [r["symbol"] for r in select_comparables(self._rows())]
        assert picked[0] == "IBM"
        assert set(picked[1:]) == {"ACN", "INFY"}
        assert "MU" not in picked  # bigger, and not the same business

    def test_falls_back_to_sector_when_industry_is_too_thin(self):
        from src.stock_analysis.tools.yf_summaries import select_comparables

        rows = [r for r in self._rows() if r["symbol"] not in ("ACN", "INFY")]
        picked = [r["symbol"] for r in select_comparables(rows)]
        assert "JPM" not in picked  # wrong sector even so
        assert set(picked[1:]) == {"CSCO", "MU"}

    def test_ranks_by_size_similarity_not_size(self):
        """CSCO at 441bn is a better comparable for a 224bn company than MU."""
        from src.stock_analysis.tools.yf_summaries import select_comparables

        rows = [r for r in self._rows() if r["symbol"] not in ("ACN", "INFY", "JPM")]
        picked = [r["symbol"] for r in select_comparables(rows)]
        assert picked[1] == "CSCO"

    def test_subject_always_leads_and_limit_is_respected(self):
        from src.stock_analysis.tools.yf_summaries import select_comparables

        picked = select_comparables(self._rows(), limit=1)
        assert picked[0]["is_subject"] is True
        assert len(picked) == 2

    def test_no_subject_row_degrades_rather_than_raising(self):
        from src.stock_analysis.tools.yf_summaries import select_comparables

        rows = [{"symbol": "A"}, {"symbol": "B"}]
        assert len(select_comparables(rows)) == 2
