"""The explicit forecast, and the value that falls out of it.

Its absence was the standing objection to every note this system produced:
drivers were described, never measured, so the target had nothing underneath it
and defaulted to the Street's number.
"""

import pytest

from src.stock_analysis.tools.forecast import (
    build_forecast,
    current_ev_ebit,
    value_by_exit_multiple,
    value_forecast,
)

# Amazon FY2023-25 as filed.
INCOME = {
    "2023-12-31": {"revenue_m": 574785.0, "operating_income_m": 36852.0},
    "2024-12-31": {"revenue_m": 637959.0, "operating_income_m": 68593.0},
    "2025-12-31": {"revenue_m": 716924.0, "operating_income_m": 79975.0},
}
CASHFLOW = {
    "2023-12-31": {"operating_cf_m": 84946.0, "capex_m": -52729.0},
    "2024-12-31": {"operating_cf_m": 115877.0, "capex_m": -82999.0},
    "2025-12-31": {"operating_cf_m": 139514.0, "capex_m": -131819.0},
}
REVENUE_EST = {"0y": {"avg": 828157.2}, "+1y": {"avg": 946377.2}}


class TestBuildForecast:
    def test_revenue_follows_consensus_then_fades(self):
        rows = build_forecast(INCOME, CASHFLOW, REVENUE_EST)["years"]
        assert [r["year"] for r in rows] == [2026, 2027, 2028]
        assert rows[0]["revenue_m"] == pytest.approx(828157.2, rel=1e-6)
        assert rows[1]["revenue_m"] == pytest.approx(946377.2, rel=1e-6)
        # Beyond consensus, growth fades rather than repeating.
        assert rows[2]["revenue_growth_pct"] < rows[1]["revenue_growth_pct"]

    def test_margin_expansion_is_damped_and_capped(self):
        """A company that added 240bps last year is not assumed to repeat it."""
        a = build_forecast(INCOME, CASHFLOW, REVENUE_EST)["assumptions"]
        assert 0 < a["margin_change_ppt_per_year"] <= 1.5

    def test_elevated_capex_reverts_rather_than_persisting(self):
        """Amazon's capex ran 18.4% of revenue against a 13.5% average."""
        out = build_forecast(INCOME, CASHFLOW, REVENUE_EST)
        a, rows = out["assumptions"], out["years"]
        assert a["capex_pct_now"] > a["capex_pct_reverting_to"]
        assert rows[-1]["capex_pct_of_revenue"] < rows[0]["capex_pct_of_revenue"]

    def test_every_assumption_is_returned_for_disclosure(self):
        a = build_forecast(INCOME, CASHFLOW, REVENUE_EST)["assumptions"]
        for key in (
            "revenue_basis",
            "base_operating_margin_pct",
            "margin_change_ppt_per_year",
            "operating_cf_margin_pct",
            "capex_pct_now",
            "capex_pct_reverting_to",
        ):
            assert key in a

    def test_thin_history_yields_nothing_rather_than_a_guess(self):
        assert build_forecast({}, {}) == {}
        assert build_forecast(INCOME, {}) == {}


class TestValuation:
    SHARES, NET_DEBT = 10629.0, -50000.0

    def test_exit_multiple_value_falls_out_of_the_forecast(self):
        f = build_forecast(INCOME, CASHFLOW, REVENUE_EST)
        v = value_by_exit_multiple(f, self.SHARES, 35.3, self.NET_DEBT, 9.0)
        # 2028 EBIT x 35.3, discounted three years, less net debt, per share.
        ebit = f["years"][-1]["operating_income_m"]
        expected = (ebit * 35.3 / 1.09**3 - self.NET_DEBT) / self.SHARES
        # abs=0.01 because value_per_share is reported to the cent.
        assert v["value_per_share"] == pytest.approx(expected, abs=0.01)
        assert "EV/EBIT" in v["method"]

    def test_current_multiple_is_the_default_and_is_disclosed(self):
        mult = current_ev_ebit(
            market_cap_m=2819400.0, net_debt_m=-50000.0, operating_income_m=79975.0
        )
        assert mult == pytest.approx((2819400.0 - 50000.0) / 79975.0)

    def test_no_multiple_means_no_value(self):
        f = build_forecast(INCOME, CASHFLOW, REVENUE_EST)
        assert value_by_exit_multiple(f, self.SHARES, None, self.NET_DEBT) == {}
        assert value_by_exit_multiple(f, 0, 35.3, self.NET_DEBT) == {}

    def test_fcf_discount_is_available_as_a_cross_check(self):
        f = build_forecast(INCOME, CASHFLOW, REVENUE_EST)
        v = value_forecast(f, self.SHARES, self.NET_DEBT, 9.0)
        # Amazon mid-build-out: the cash-flow view is far below the multiple
        # view, which is the finding rather than a fault.
        assert v["value_per_share"] > 0
        assert v["terminal_share_pct"] > 50

    def test_negative_terminal_cash_flow_produces_no_value(self):
        """A terminal value on negative cash flow is meaningless."""
        heavy = {k: {**v, "capex_m": -400000.0} for k, v in CASHFLOW.items()}
        f = build_forecast(INCOME, heavy, REVENUE_EST)
        assert value_forecast(f, self.SHARES, self.NET_DEBT, 9.0) == {}
