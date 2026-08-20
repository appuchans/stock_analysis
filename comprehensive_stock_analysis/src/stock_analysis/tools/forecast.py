"""An explicit three-year forecast, and a value that falls out of it.

Every valuation in this system used to hang off one number: next year's
consensus EPS growth. That number is a single-year comparison, so a one-off
made it useless — Alphabet's was -28.3%, which as a ten-year cash-flow rate
valued a $341 share at $46, and Amazon's was -15.7% while its revenue consensus
was +14.3%. The model then either printed nonsense or withheld itself, leaving
the target to default to the Street's.

Consensus *revenue* is the sturdier input: it comes from fifty-odd analysts,
it is not distorted by one-off items below the operating line, and it is
published two years out. So the forecast is built revenue-first, and margin and
capital intensity are stated assumptions applied to it rather than things the
model pretends to know.

Three years explicit, then a terminal value. Every assumption is returned
alongside the numbers so the note can print them and a reader can disagree with
a specific one.
"""

import logging
from typing import Any, Dict, List, Optional

_logger = logging.getLogger(__name__)

# Margin improvement is capped and damped: a company that added 200bps last
# year is not assumed to keep doing so for three more.
_MARGIN_TREND_DAMPING = 0.5
_MAX_MARGIN_EXPANSION_PPT = 1.5

# Elevated capital spending is assumed to mean-revert toward its own recent
# average rather than continue forever — Amazon's capex ran 18.4% of revenue in
# FY2025 against a three-year average of 13.5%.
_CAPEX_REVERSION = 0.5

# Growth beyond the consensus horizon fades toward the terminal rate.
_YEAR3_FADE = 0.7


def _avg(values: List[float]) -> Optional[float]:
    vals = [v for v in values if isinstance(v, (int, float))]
    return sum(vals) / len(vals) if vals else None


def build_forecast(
    annual_income: Dict[str, Dict[str, Any]],
    cash_flow: Dict[str, Dict[str, Any]],
    revenue_estimates: Optional[Dict[str, Dict[str, Any]]] = None,
    years: int = 3,
    terminal_growth_pct: float = 2.5,
) -> Dict[str, Any]:
    """Revenue, operating margin, capital intensity and free cash flow by year.

    Returns ``{"years": [...], "assumptions": {...}}``, or ``{}`` when the
    history is too thin to project from. Never raises.
    """
    if not annual_income or not cash_flow:
        return {}
    try:
        periods = sorted(annual_income)
        latest = periods[-1]
        rev_hist = [annual_income[p].get("revenue_m") for p in periods]
        op_hist = [annual_income[p].get("operating_income_m") for p in periods]
        base_rev = rev_hist[-1]
        if not base_rev:
            return {}

        margins = [
            (o / r * 100)
            for r, o in zip(rev_hist, op_hist)
            if isinstance(r, (int, float)) and isinstance(o, (int, float)) and r
        ]
        if not margins:
            return {}
        base_margin = margins[-1]
        # Damped average annual change, so a single strong year does not
        # compound into the forecast.
        trend = 0.0
        if len(margins) >= 2:
            trend = (margins[-1] - margins[0]) / (len(margins) - 1)
        step = max(
            -_MAX_MARGIN_EXPANSION_PPT,
            min(trend * _MARGIN_TREND_DAMPING, _MAX_MARGIN_EXPANSION_PPT),
        )

        cf_periods = sorted(cash_flow)
        ocf_margins, capex_intensity = [], []
        for p in cf_periods:
            rev = (annual_income.get(p) or {}).get("revenue_m")
            row = cash_flow[p]
            if not isinstance(rev, (int, float)) or not rev:
                continue
            if isinstance(row.get("operating_cf_m"), (int, float)):
                ocf_margins.append(row["operating_cf_m"] / rev * 100)
            if isinstance(row.get("capex_m"), (int, float)):
                capex_intensity.append(abs(row["capex_m"]) / rev * 100)
        if not ocf_margins or not capex_intensity:
            return {}
        ocf_margin = ocf_margins[-1]
        capex_now, capex_avg = capex_intensity[-1], _avg(capex_intensity)

        # Revenue: consensus where it exists, then a faded extrapolation.
        est = revenue_estimates or {}
        path: List[float] = []
        for key in ("0y", "+1y"):
            avg = (est.get(key) or {}).get("avg")
            if isinstance(avg, (int, float)) and avg > (path[-1] if path else 0):
                path.append(float(avg))
        if not path:
            # No consensus: carry the last realised growth rate forward, faded.
            g = (
                (rev_hist[-1] / rev_hist[-2] - 1)
                if len(rev_hist) >= 2 and rev_hist[-2]
                else 0.05
            )
            path = [base_rev * (1 + g)]
        while len(path) < years:
            prev_growth = path[-1] / (path[-2] if len(path) >= 2 else base_rev) - 1
            faded = (
                terminal_growth_pct / 100
                + (prev_growth - terminal_growth_pct / 100) * _YEAR3_FADE
            )
            path.append(path[-1] * (1 + faded))
        path = path[:years]

        rows: List[Dict[str, Any]] = []
        prev_rev = base_rev
        base_year = int(str(latest)[:4])
        for i, rev in enumerate(path, start=1):
            margin = base_margin + step * i
            # Capital intensity reverts toward its own recent average.
            intensity = capex_now + (capex_avg - capex_now) * (
                _CAPEX_REVERSION * i / years
            )
            ocf = rev * ocf_margin / 100
            capex = rev * intensity / 100
            rows.append(
                {
                    "year": base_year + i,
                    "revenue_m": round(rev, 1),
                    "revenue_growth_pct": round((rev / prev_rev - 1) * 100, 1),
                    "operating_margin_pct": round(margin, 1),
                    "operating_income_m": round(rev * margin / 100, 1),
                    "capex_pct_of_revenue": round(intensity, 1),
                    "free_cash_flow_m": round(ocf - capex, 1),
                }
            )
            prev_rev = rev

        return {
            "years": rows,
            "assumptions": {
                "revenue_basis": (
                    "analyst consensus for the first two years, then faded "
                    "toward the terminal rate"
                    if len(est) >= 2
                    else "last realised growth, faded"
                ),
                "base_year": base_year,
                "base_revenue_m": round(base_rev, 1),
                "base_operating_margin_pct": round(base_margin, 1),
                "margin_change_ppt_per_year": round(step, 2),
                "operating_cf_margin_pct": round(ocf_margin, 1),
                "capex_pct_now": round(capex_now, 1),
                "capex_pct_reverting_to": round(capex_avg or capex_now, 1),
            },
        }
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning("forecast build failed: %s", exc)
        return {}


def value_by_exit_multiple(
    forecast: Dict[str, Any],
    shares_m: Optional[float],
    exit_ev_ebit: Optional[float],
    net_debt_m: float = 0.0,
    discount_pct: float = 9.0,
) -> Dict[str, Any]:
    """Value the final forecast year on a stated EV/EBIT multiple.

    A three-year free-cash-flow discount structurally undervalues a company in
    the middle of a build-out: the spending is in the forecast and the return
    is past its end. Amazon's FY2025 free cash flow was $7.7bn on $716.9bn of
    revenue after $131.8bn of capital expenditure, and discounting that gave
    $53 a share against a $266 close. The market is not pricing current cash
    flow, and neither should the note.

    So the operating income the forecast projects is capitalised at a multiple
    the note has to state — by default the multiple the shares trade at today,
    which assumes no re-rating in either direction and is the assumption a
    reader can most easily argue with.
    """
    rows = (forecast or {}).get("years") or []
    if not rows or not shares_m or shares_m <= 0 or not exit_ev_ebit:
        return {}
    if exit_ev_ebit <= 0:
        return {}
    try:
        final = rows[-1]
        ebit = final.get("operating_income_m")
        if not isinstance(ebit, (int, float)) or ebit <= 0:
            return {}
        ev_then = ebit * exit_ev_ebit
        years = len(rows)
        ev_now = ev_then / (1 + discount_pct / 100) ** years
        equity = ev_now - (net_debt_m or 0.0)
        if equity <= 0:
            return {}
        return {
            "value_per_share": round(equity / shares_m, 2),
            "method": (
                f"{final['year']} operating income of "
                f"${ebit / 1000:,.1f}bn at {exit_ev_ebit:,.1f}x EV/EBIT, "
                f"discounted {years} years at {discount_pct:,.1f}%"
            ),
            "exit_ev_ebit": round(exit_ev_ebit, 1),
            "terminal_year": final["year"],
            "terminal_ebit_m": round(ebit, 1),
            "discount_pct": round(discount_pct, 2),
        }
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning("exit-multiple valuation failed: %s", exc)
        return {}


def current_ev_ebit(
    market_cap_m: Optional[float],
    net_debt_m: Optional[float],
    operating_income_m: Optional[float],
) -> Optional[float]:
    """What the shares trade at today, as the default exit multiple."""
    if not market_cap_m or not operating_income_m or operating_income_m <= 0:
        return None
    ev = market_cap_m + (net_debt_m or 0.0)
    return ev / operating_income_m if ev > 0 else None


def value_forecast(
    forecast: Dict[str, Any],
    shares_m: Optional[float],
    net_debt_m: float = 0.0,
    wacc_pct: float = 9.0,
    terminal_growth_pct: float = 2.5,
) -> Dict[str, Any]:
    """Discount the forecast to a value per share.

    The point of this function is that the target *falls out of* the forecast
    above rather than being asserted beside it. If the inputs cannot support a
    value, it returns ``{}`` and the note publishes no house target.
    """
    rows = (forecast or {}).get("years") or []
    if not rows or not shares_m or shares_m <= 0:
        return {}
    disc, term = wacc_pct / 100.0, terminal_growth_pct / 100.0
    if disc <= term:
        return {}
    try:
        pv = 0.0
        for i, row in enumerate(rows, start=1):
            fcf = row.get("free_cash_flow_m")
            if not isinstance(fcf, (int, float)):
                return {}
            pv += fcf / (1 + disc) ** i
        final = rows[-1]["free_cash_flow_m"]
        if final <= 0:
            # A terminal value on negative cash flow is meaningless; the note
            # says so rather than printing a number.
            return {}
        tv = final * (1 + term) / (disc - term)
        ev = pv + tv / (1 + disc) ** len(rows)
        equity = ev - (net_debt_m or 0.0)
        if equity <= 0:
            return {}
        return {
            "value_per_share": round(equity / shares_m, 2),
            "enterprise_value_m": round(ev, 1),
            "pv_explicit_m": round(pv, 1),
            "pv_terminal_m": round(tv / (1 + disc) ** len(rows), 1),
            "terminal_share_pct": round(tv / (1 + disc) ** len(rows) / ev * 100, 1),
            "wacc_pct": round(wacc_pct, 2),
            "terminal_growth_pct": terminal_growth_pct,
        }
    except Exception as exc:  # pragma: no cover - defensive
        _logger.warning("forecast valuation failed: %s", exc)
        return {}
