"""Calculation tools for stock analysis."""

import json
import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ._indicators import (
    _last,
    acc_dist_index,
    adx,
    aroon_down,
    aroon_up,
    atr,
    bollinger_lower,
    bollinger_middle,
    bollinger_upper,
    cci,
    chaikin_money_flow,
    ema,
    ichimoku_a,
    ichimoku_b,
    keltner_lower,
    keltner_middle,
    keltner_upper,
    macd_diff,
    macd_line,
    macd_signal_line,
    money_flow_index,
    obv,
    psar_approx,
    roc,
    rsi,
    sma,
    stoch,
    stoch_signal,
    volume_price_trend,
    williams_r,
)

_logger = logging.getLogger(__name__)

from crewai.tools import BaseTool

from ..models.stock_data import RiskLevel


def _parse_list(value, default=None):
    """Accept a JSON-array string OR a Python list. Strips whitespace; treats null/empty as default."""
    if default is None:
        default = []
    if value is None:
        return default
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        v = value.strip()
        if not v or v == "null":
            return default
        result = json.loads(v)
        return result if isinstance(result, list) else default
    return default


def _parse_dict(value, default=None):
    """Accept a JSON-object string OR a Python dict. Strips whitespace; treats null/empty as default."""
    if default is None:
        default = {}
    if value is None:
        return default
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        v = value.strip()
        if not v or v == "null":
            return default
        result = json.loads(v)
        return result if isinstance(result, dict) else default
    return default


class FinancialCalculatorTool(BaseTool):
    """Tool for financial calculations."""

    name: str = "Financial Calculator Tool"
    description: str = (
        "Performs various financial calculations including ratios, returns, and valuations"
    )

    def _run(self, calculation_type: str, params: str = "{}") -> Dict[str, Any]:
        """Perform financial calculations. params is a JSON object of keyword arguments for the chosen calculation_type."""
        try:
            kwargs = _parse_dict(params)
            if calculation_type == "ratios":
                return self._calculate_ratios(**kwargs)
            elif calculation_type == "returns":
                return self._calculate_returns(**kwargs)
            elif calculation_type == "valuation":
                return self._calculate_valuation(**kwargs)
            elif calculation_type == "risk_metrics":
                return self._calculate_risk_metrics(**kwargs)
            else:
                return {"error": f"Unknown calculation type: {calculation_type}"}

        except Exception as e:
            return {"error": f"Calculation failed: {str(e)}"}

    def _calculate_ratios(
        self,
        price: float = 0.0,
        earnings: Optional[float] = None,
        book_value: Optional[float] = None,
        sales: Optional[float] = None,
        market_cap: Optional[float] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """Calculate financial ratios.

        Note: `growth_rate` (via kwargs, used for peg_ratio) is expected as a
        whole-number percentage (e.g. 10 for 10% growth) per conventional PEG
        math (PEG = PE / growth%). This is inconsistent with `analysis_tools.py`,
        which treats fractions like roe/revenue_growth as decimals (e.g. 0.10)
        — callers must convert accordingly before passing growth_rate here.
        """
        ratios = {}

        if price and earnings and earnings > 0:
            ratios["pe_ratio"] = price / earnings

        if book_value and book_value > 0:
            ratios["pb_ratio"] = price / book_value

        if sales and sales > 0 and market_cap:
            ratios["ps_ratio"] = market_cap / sales

        if price and earnings and earnings > 0 and kwargs.get("growth_rate"):
            ratios["peg_ratio"] = ratios.get("pe_ratio", 0) / kwargs["growth_rate"]

        return ratios

    def _calculate_returns(self, prices: List[float], periods: int = 1) -> Dict[str, Any]:
        """Calculate returns."""
        if len(prices) < 2:
            return {"error": "Insufficient price data"}

        returns = []
        for i in range(periods, len(prices)):
            ret = (prices[i] - prices[i - periods]) / prices[i - periods]
            returns.append(ret)

        if not returns:
            return {"error": "No returns calculated"}

        returns_array = np.array(returns)
        # Scale the annualization factor by `periods` (e.g. periods=5 for weekly
        # returns from daily prices means ~50.4 periods/year, not 252).
        trading_periods_per_year = 252 / periods if periods > 0 else 252

        return {
            "returns": returns,
            "mean_return": np.mean(returns_array),
            "std_return": np.std(returns_array),
            "total_return": (prices[-1] - prices[0]) / prices[0],
            "annualized_return": np.mean(returns_array) * trading_periods_per_year,
            "annualized_volatility": np.std(returns_array) * np.sqrt(trading_periods_per_year),
        }

    def _calculate_valuation(
        self,
        current_price: float,
        earnings: float,
        growth_rate: float,
        discount_rate: float,
        terminal_growth_rate: float = 0.02,
    ) -> Dict[str, Any]:
        """Calculate intrinsic value using DCF."""
        if earnings is None or growth_rate is None or discount_rate is None:
            return {"error": "Missing required parameters for valuation"}
        if discount_rate <= 0:
            return {"error": "discount_rate must be positive"}
        if earnings <= 0:
            return {"error": "earnings must be positive for DCF"}
        if discount_rate <= terminal_growth_rate:
            return {"error": "discount_rate must be greater than terminal_growth_rate"}

        # Simple DCF calculation
        years = 5
        projected_earnings = []

        for year in range(1, years + 1):
            if year <= 3:  # High growth period
                projected_earnings.append(earnings * ((1 + growth_rate) ** year))
            else:  # Terminal growth period
                projected_earnings.append(projected_earnings[-1] * (1 + terminal_growth_rate))

        # Calculate present value of projected earnings
        pv_earnings = []
        for i, earning in enumerate(projected_earnings):
            pv = earning / ((1 + discount_rate) ** (i + 1))
            pv_earnings.append(pv)

        # Terminal value
        terminal_value = (
            projected_earnings[-1]
            * (1 + terminal_growth_rate)
            / (discount_rate - terminal_growth_rate)
        )
        pv_terminal = terminal_value / ((1 + discount_rate) ** years)

        # Intrinsic value
        intrinsic_value = sum(pv_earnings) + pv_terminal

        return {
            "intrinsic_value": intrinsic_value,
            "current_price": current_price,
            "upside_potential": (intrinsic_value - current_price) / current_price * 100,
            "projected_earnings": projected_earnings,
            "present_value_earnings": pv_earnings,
            "terminal_value": terminal_value,
            "present_value_terminal": pv_terminal,
        }

    def _calculate_risk_metrics(
        self, returns: List[float], risk_free_rate: float = 0.02
    ) -> Dict[str, Any]:
        """Calculate risk metrics from daily returns. risk_free_rate is annual."""
        if not returns:
            return {"error": "No returns data provided"}

        returns_array = np.array(returns)

        # Basic risk metrics (annualised, assuming daily returns)
        mean_return = np.mean(returns_array)
        volatility = np.std(returns_array)
        annualized_return = mean_return * 252
        annualized_volatility = volatility * np.sqrt(252)

        # Sharpe ratio — annual excess return over annual volatility
        excess_return = annualized_return - risk_free_rate
        sharpe_ratio = excess_return / annualized_volatility if annualized_volatility > 0 else 0

        # Sortino ratio (annualised downside deviation)
        downside_returns = returns_array[returns_array < 0]
        downside_deviation = (
            np.std(downside_returns) * np.sqrt(252) if len(downside_returns) > 0 else 0
        )
        sortino_ratio = excess_return / downside_deviation if downside_deviation > 0 else 0

        # Maximum drawdown
        cumulative_returns = np.cumprod(1 + returns_array)
        running_max = np.maximum.accumulate(cumulative_returns)
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = np.min(drawdown)

        # Value at Risk (95% confidence)
        var_95 = np.percentile(returns_array, 5)

        # Conditional Value at Risk
        cvar_95 = np.mean(returns_array[returns_array <= var_95])

        return {
            "mean_return": mean_return,
            "volatility": volatility,
            "annualized_return": annualized_return,
            "annualized_volatility": annualized_volatility,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown": max_drawdown,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "risk_level": self._determine_risk_level(annualized_volatility, max_drawdown),
        }

    def _determine_risk_level(self, volatility: float, max_drawdown: float) -> str:
        """Determine risk level based on annualised volatility and drawdown."""
        if volatility < 0.15 and abs(max_drawdown) < 0.1:
            return RiskLevel.VERY_LOW
        elif volatility < 0.25 and abs(max_drawdown) < 0.2:
            return RiskLevel.LOW
        elif volatility < 0.35 and abs(max_drawdown) < 0.3:
            return RiskLevel.MEDIUM
        elif volatility < 0.5 and abs(max_drawdown) < 0.4:
            return RiskLevel.HIGH
        else:
            return RiskLevel.VERY_HIGH


class TechnicalIndicatorTool(BaseTool):
    """Tool for technical indicator calculations."""

    name: str = "Technical Indicator Tool"
    description: str = "Calculates various technical indicators for stock analysis"

    def _run(self, price_data: str, indicator_type: str, params: str = "{}") -> Dict[str, Any]:
        """Calculate technical indicators. price_data is a JSON array of OHLCV records; params is an optional JSON object of extra kwargs."""
        try:
            kwargs = _parse_dict(params)
            price_list = _parse_list(price_data)
            if not price_list:
                return {"error": "price_data is empty or null"}
            df = pd.DataFrame(price_list)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)

            if indicator_type == "moving_averages":
                return self._calculate_moving_averages(df, **kwargs)
            elif indicator_type == "momentum":
                return self._calculate_momentum_indicators(df, **kwargs)
            elif indicator_type == "volatility":
                return self._calculate_volatility_indicators(df, **kwargs)
            elif indicator_type == "volume":
                return self._calculate_volume_indicators(df, **kwargs)
            elif indicator_type == "trend":
                return self._calculate_trend_indicators(df, **kwargs)
            else:
                return {"error": f"Unknown indicator type: {indicator_type}"}

        except Exception as e:
            return {"error": f"Technical indicator calculation failed: {str(e)}"}

    def _calculate_moving_averages(
        self, df: pd.DataFrame, periods: List[int] = [20, 50, 200]
    ) -> Dict[str, Any]:
        """Calculate moving averages."""
        c = df["close"]
        return {f"sma_{p}": _last(sma(c, p)) for p in periods} | {
            f"ema_{p}": _last(ema(c, p)) for p in periods
        }

    def _calculate_momentum_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate momentum indicators."""
        c, h, l = df["close"], df["high"], df["low"]
        return {
            "rsi": _last(rsi(c, 14)),
            "macd": _last(macd_line(c)),
            "macd_signal": _last(macd_signal_line(c)),
            "macd_histogram": _last(macd_diff(c)),
            "stochastic_k": _last(stoch(h, l, c)),
            "stochastic_d": _last(stoch_signal(h, l, c)),
            "williams_r": _last(williams_r(h, l, c)),
            "roc": _last(roc(c, 10)),
        }

    def _calculate_volatility_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate volatility indicators."""
        c, h, l = df["close"], df["high"], df["low"]
        bb_u = bollinger_upper(c)
        bb_m = bollinger_middle(c)
        bb_l = bollinger_lower(c)
        bb_width = None
        if bb_u.iloc[-1] == bb_u.iloc[-1] and bb_m.iloc[-1] and bb_m.iloc[-1] != 0:
            bb_width = round(
                (float(bb_u.iloc[-1]) - float(bb_l.iloc[-1])) / float(bb_m.iloc[-1]), 4
            )
        return {
            "bollinger_upper": _last(bb_u),
            "bollinger_middle": _last(bb_m),
            "bollinger_lower": _last(bb_l),
            "bollinger_width": bb_width,
            "atr": _last(atr(h, l, c)),
            "keltner_upper": _last(keltner_upper(h, l, c)),
            "keltner_middle": _last(keltner_middle(c)),
            "keltner_lower": _last(keltner_lower(h, l, c)),
        }

    def _calculate_volume_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate volume indicators."""
        c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
        return {
            "obv": _last(obv(c, v)),
            "ad_line": _last(acc_dist_index(h, l, c, v)),
            "mfi": _last(money_flow_index(h, l, c, v)),
            "vpt": _last(volume_price_trend(c, v)),
            "cmf": _last(chaikin_money_flow(h, l, c, v)),
        }

    def _calculate_trend_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate trend indicators."""
        c, h, l = df["close"], df["high"], df["low"]
        return {
            "adx": _last(adx(h, l, c)),
            "cci": _last(cci(h, l, c)),
            "aroon_up": _last(aroon_up(h)),
            "aroon_down": _last(aroon_down(l)),
            "psar": _last(psar_approx(h, l, c)),
            "ichimoku_a": _last(ichimoku_a(h, l)),
            "ichimoku_b": _last(ichimoku_b(h, l)),
        }


class RiskCalculatorTool(BaseTool):
    """Tool for risk calculations."""

    name: str = "Risk Calculator Tool"
    description: str = (
        "Calculates risk metrics (annualised volatility, Sharpe, Sortino, VaR 95%, "
        "CVaR, max drawdown, beta vs S&P 500). Preferred usage: pass symbol='TICKER' "
        "and the tool fetches 1 year of daily prices itself. Alternatively pass "
        "price_data as a JSON array of OHLCV records."
    )

    def _run(
        self, price_data: str = "", risk_free_rate: float = 0.02, symbol: str = ""
    ) -> Dict[str, Any]:
        """Calculate risk metrics from price_data (JSON OHLCV array) or a symbol."""
        try:
            returns: Optional[pd.Series] = None
            price_list = _parse_list(price_data)
            if price_list:
                df = pd.DataFrame(price_list)
                df["timestamp"] = pd.to_datetime(df["timestamp"])
                df.set_index("timestamp", inplace=True)
                returns = df["close"].pct_change().dropna()
            elif symbol:
                import yfinance as yf

                hist = yf.Ticker(symbol.strip().upper()).history(period="1y")
                if hist is not None and not hist.empty:
                    returns = hist["Close"].pct_change().dropna()

            if returns is None or len(returns) < 2:
                return {"error": "Provide price_data (JSON OHLCV array) or a valid symbol"}

            # Basic risk metrics
            risk_metrics = self._calculate_basic_risk_metrics(returns, risk_free_rate)

            # Advanced risk metrics
            advanced_metrics = self._calculate_advanced_risk_metrics(returns)

            # Beta against S&P 500 — fetched live and aligned by date
            beta = self._calculate_beta(returns)
            if beta is not None:
                advanced_metrics["beta"] = beta

            # Risk assessment
            risk_assessment = self._assess_risk_level(risk_metrics, advanced_metrics)

            return {
                "basic_metrics": risk_metrics,
                "advanced_metrics": advanced_metrics,
                "risk_assessment": risk_assessment,
            }

        except Exception as e:
            return {"error": f"Risk calculation failed: {str(e)}"}

    def _calculate_basic_risk_metrics(
        self, returns: pd.Series, risk_free_rate: float
    ) -> Dict[str, Any]:
        """Calculate basic risk metrics from daily returns. risk_free_rate is annual."""
        mean_return = returns.mean()
        volatility = returns.std()
        annualized_return = mean_return * 252
        annualized_volatility = volatility * np.sqrt(252)
        excess_return = annualized_return - risk_free_rate

        # Sharpe ratio — annual excess return over annual volatility
        sharpe_ratio = excess_return / annualized_volatility if annualized_volatility > 0 else 0

        # Sortino ratio (annualised downside deviation)
        downside_returns = returns[returns < 0]
        downside_deviation = (
            downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        )
        sortino_ratio = excess_return / downside_deviation if downside_deviation > 0 else 0

        return {
            "mean_return": mean_return,
            "volatility": volatility,
            "annualized_return": annualized_return,
            "annualized_volatility": annualized_volatility,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "excess_return": excess_return,
        }

    def _calculate_advanced_risk_metrics(self, returns: pd.Series) -> Dict[str, Any]:
        """Calculate advanced risk metrics."""
        # Maximum drawdown
        cumulative_returns = (1 + returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()

        # Value at Risk (95% confidence)
        var_95 = returns.quantile(0.05)

        # Conditional Value at Risk
        cvar_95 = returns[returns <= var_95].mean()

        # Skewness and Kurtosis
        skewness = returns.skew()
        kurtosis = returns.kurtosis()

        return {
            "max_drawdown": max_drawdown,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "skewness": skewness,
            "kurtosis": kurtosis,
            "beta": None,  # populated by _calculate_beta in _run
        }

    def _calculate_beta(self, returns: pd.Series) -> Optional[float]:
        """Calculate beta vs. S&P 500 using date-aligned returns."""
        try:
            import yfinance as yf

            start = returns.index.min()
            end = returns.index.max()
            # Strip timezone for yfinance compatibility
            start_str = pd.Timestamp(start).tz_localize(None).strftime("%Y-%m-%d")
            end_str = pd.Timestamp(end).tz_localize(None).strftime("%Y-%m-%d")

            market_hist = yf.download(
                "^GSPC", start=start_str, end=end_str, progress=False, auto_adjust=True
            )
            if market_hist.empty:
                return None

            market_returns = market_hist["Close"].squeeze().pct_change().dropna()

            # Normalise both indexes to timezone-naive dates for alignment
            r = returns.copy()
            r.index = pd.DatetimeIndex(r.index).tz_localize(None).normalize()
            m = market_returns.copy()
            m.index = pd.DatetimeIndex(m.index).tz_localize(None).normalize()

            common = r.index.intersection(m.index)
            if len(common) < 5:
                return None

            r_aligned = r.loc[common]
            m_aligned = m.loc[common]

            market_var = float(m_aligned.var())
            if market_var == 0:
                return None

            return round(float(r_aligned.cov(m_aligned)) / market_var, 4)

        except Exception as exc:
            _logger.debug("Beta calculation skipped: %s", exc)
            return None

    def _assess_risk_level(self, basic_metrics: Dict, advanced_metrics: Dict) -> Dict[str, Any]:
        """Assess overall risk level (volatility thresholds are annualised)."""
        volatility = basic_metrics.get("annualized_volatility", basic_metrics["volatility"])
        max_drawdown = abs(advanced_metrics["max_drawdown"])
        sharpe_ratio = basic_metrics["sharpe_ratio"]

        # Risk score (0-100, higher = riskier)
        risk_score = 0

        # Volatility component (0-40 points)
        if volatility < 0.1:
            risk_score += 10
        elif volatility < 0.2:
            risk_score += 20
        elif volatility < 0.3:
            risk_score += 30
        else:
            risk_score += 40

        # Drawdown component (0-30 points)
        if max_drawdown < 0.1:
            risk_score += 10
        elif max_drawdown < 0.2:
            risk_score += 20
        else:
            risk_score += 30

        # Sharpe ratio component (0-30 points)
        if sharpe_ratio > 1.0:
            risk_score += 0
        elif sharpe_ratio > 0.5:
            risk_score += 10
        elif sharpe_ratio > 0:
            risk_score += 20
        else:
            risk_score += 30

        # Determine risk level
        if risk_score < 20:
            risk_level = RiskLevel.VERY_LOW
        elif risk_score < 40:
            risk_level = RiskLevel.LOW
        elif risk_score < 60:
            risk_level = RiskLevel.MEDIUM
        elif risk_score < 80:
            risk_level = RiskLevel.HIGH
        else:
            risk_level = RiskLevel.VERY_HIGH

        return {
            "risk_score": risk_score,
            "risk_level": risk_level,
            "volatility_risk": "Low" if volatility < 0.2 else "High",
            "drawdown_risk": "Low" if max_drawdown < 0.2 else "High",
            "return_risk": "Low" if sharpe_ratio > 0.5 else "High",
        }


class ValuationCalculatorTool(BaseTool):
    """Tool for valuation calculations."""

    name: str = "Valuation Calculator Tool"
    description: str = "Calculates various valuation metrics and models"

    def _run(self, valuation_type: str, params: str = "{}") -> Dict[str, Any]:
        """Calculate valuation metrics. params is a JSON object of keyword arguments for the chosen valuation_type."""
        try:
            kwargs = _parse_dict(params)
            if valuation_type == "dcf":
                return self._calculate_dcf(**kwargs)
            elif valuation_type == "comparable":
                return self._calculate_comparable_valuation(**kwargs)
            elif valuation_type == "asset_based":
                return self._calculate_asset_based_valuation(**kwargs)
            elif valuation_type == "dividend_discount":
                return self._calculate_dividend_discount(**kwargs)
            else:
                return {"error": f"Unknown valuation type: {valuation_type}"}

        except Exception as e:
            return {"error": f"Valuation calculation failed: {str(e)}"}

    def _calculate_dcf(
        self,
        current_earnings: float,
        growth_rate: float,
        discount_rate: float,
        terminal_growth_rate: float = 0.02,
        years: int = 5,
    ) -> Dict[str, Any]:
        """Calculate DCF valuation."""
        if not discount_rate or discount_rate <= 0:
            return {"error": "discount_rate must be positive"}
        if current_earnings <= 0:
            return {"error": "current_earnings must be positive for DCF"}
        if discount_rate <= terminal_growth_rate:
            return {"error": "discount_rate must be greater than terminal_growth_rate"}

        projected_earnings = []
        pv_earnings = []

        for year in range(1, years + 1):
            if year <= 3:  # High growth period
                earning = current_earnings * ((1 + growth_rate) ** year)
            else:  # Terminal growth period
                earning = projected_earnings[-1] * (1 + terminal_growth_rate)

            projected_earnings.append(earning)
            pv = earning / ((1 + discount_rate) ** year)
            pv_earnings.append(pv)

        # Terminal value
        terminal_value = (
            projected_earnings[-1]
            * (1 + terminal_growth_rate)
            / (discount_rate - terminal_growth_rate)
        )
        pv_terminal = terminal_value / ((1 + discount_rate) ** years)

        # Intrinsic value
        intrinsic_value = sum(pv_earnings) + pv_terminal

        return {
            "intrinsic_value": intrinsic_value,
            "projected_earnings": projected_earnings,
            "present_value_earnings": pv_earnings,
            "terminal_value": terminal_value,
            "present_value_terminal": pv_terminal,
            "assumptions": {
                "growth_rate": growth_rate,
                "discount_rate": discount_rate,
                "terminal_growth_rate": terminal_growth_rate,
                "years": years,
            },
        }

    def _calculate_comparable_valuation(
        self,
        current_price: float,
        pe_ratio: float,
        industry_pe: float,
        pb_ratio: float,
        industry_pb: float,
    ) -> Dict[str, Any]:
        """Calculate comparable valuation."""
        # PE-based valuation
        pe_valuation = current_price * (industry_pe / pe_ratio) if pe_ratio > 0 else None

        # PB-based valuation
        pb_valuation = current_price * (industry_pb / pb_ratio) if pb_ratio > 0 else None

        # Average valuation
        valuations = [v for v in [pe_valuation, pb_valuation] if v is not None]
        avg_valuation = sum(valuations) / len(valuations) if valuations else None

        return {
            "pe_valuation": pe_valuation,
            "pb_valuation": pb_valuation,
            "average_valuation": avg_valuation,
            "current_price": current_price,
            "upside_potential": (
                (avg_valuation - current_price) / current_price * 100 if avg_valuation else None
            ),
        }

    def _calculate_asset_based_valuation(
        self, total_assets: float, total_liabilities: float, intangible_assets: float = 0
    ) -> Dict[str, Any]:
        """Calculate asset-based valuation."""
        book_value = total_assets - total_liabilities
        tangible_book_value = book_value - intangible_assets

        return {
            "book_value": book_value,
            "tangible_book_value": tangible_book_value,
            "asset_valuation": tangible_book_value,
            "assumptions": {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities,
                "intangible_assets": intangible_assets,
            },
        }

    def _calculate_dividend_discount(
        self, current_dividend: float, dividend_growth_rate: float, required_return: float
    ) -> Dict[str, Any]:
        """Calculate dividend discount model valuation."""
        if required_return <= dividend_growth_rate:
            return {"error": "Required return must be greater than dividend growth rate"}

        intrinsic_value = (
            current_dividend * (1 + dividend_growth_rate) / (required_return - dividend_growth_rate)
        )

        return {
            "intrinsic_value": intrinsic_value,
            "current_dividend": current_dividend,
            "dividend_growth_rate": dividend_growth_rate,
            "required_return": required_return,
            "assumptions": {"constant_growth": True, "perpetual_dividends": True},
        }
