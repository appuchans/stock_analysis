"""Calculation tools for stock analysis."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
import ta
from scipy import stats
from scipy.optimize import minimize
import warnings
warnings.filterwarnings('ignore')

from crewai_tools import BaseTool
from pydantic import BaseModel, Field

from ..models.stock_data import RiskLevel, RecommendationType


class FinancialCalculatorTool(BaseTool):
    """Tool for financial calculations."""
    
    name: str = "Financial Calculator Tool"
    description: str = "Performs various financial calculations including ratios, returns, and valuations"
    
    def _run(self, calculation_type: str, **kwargs) -> Dict[str, Any]:
        """Perform financial calculations."""
        try:
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
    
    def _calculate_ratios(self, price: float, earnings: float, book_value: float, 
                         sales: float, market_cap: float, **kwargs) -> Dict[str, Any]:
        """Calculate financial ratios."""
        ratios = {}
        
        if earnings and earnings > 0:
            ratios["pe_ratio"] = price / earnings
        
        if book_value and book_value > 0:
            ratios["pb_ratio"] = price / book_value
        
        if sales and sales > 0:
            ratios["ps_ratio"] = market_cap / sales
        
        if earnings and earnings > 0 and kwargs.get("growth_rate"):
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
        
        return {
            "returns": returns,
            "mean_return": np.mean(returns_array),
            "std_return": np.std(returns_array),
            "total_return": (prices[-1] - prices[0]) / prices[0],
            "annualized_return": np.mean(returns_array) * 252,  # Assuming daily data
            "annualized_volatility": np.std(returns_array) * np.sqrt(252)
        }
    
    def _calculate_valuation(self, current_price: float, earnings: float, 
                           growth_rate: float, discount_rate: float, 
                           terminal_growth_rate: float = 0.02) -> Dict[str, Any]:
        """Calculate intrinsic value using DCF."""
        if not all([earnings, growth_rate, discount_rate]):
            return {"error": "Missing required parameters for valuation"}
        
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
        terminal_value = projected_earnings[-1] / (discount_rate - terminal_growth_rate)
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
            "present_value_terminal": pv_terminal
        }
    
    def _calculate_risk_metrics(self, returns: List[float], risk_free_rate: float = 0.02) -> Dict[str, Any]:
        """Calculate risk metrics."""
        if not returns:
            return {"error": "No returns data provided"}
        
        returns_array = np.array(returns)
        
        # Basic risk metrics
        mean_return = np.mean(returns_array)
        volatility = np.std(returns_array)
        
        # Sharpe ratio
        excess_return = mean_return - risk_free_rate
        sharpe_ratio = excess_return / volatility if volatility > 0 else 0
        
        # Sortino ratio (downside deviation)
        downside_returns = returns_array[returns_array < 0]
        downside_deviation = np.std(downside_returns) if len(downside_returns) > 0 else 0
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
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown": max_drawdown,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "risk_level": self._determine_risk_level(volatility, max_drawdown)
        }
    
    def _determine_risk_level(self, volatility: float, max_drawdown: float) -> str:
        """Determine risk level based on volatility and drawdown."""
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
    
    def _run(self, price_data: List[Dict], indicator_type: str, **kwargs) -> Dict[str, Any]:
        """Calculate technical indicators."""
        try:
            df = pd.DataFrame(price_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
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
    
    def _calculate_moving_averages(self, df: pd.DataFrame, periods: List[int] = [20, 50, 200]) -> Dict[str, Any]:
        """Calculate moving averages."""
        indicators = {}
        
        for period in periods:
            indicators[f"sma_{period}"] = ta.trend.sma_indicator(df['close'], window=period).iloc[-1]
            indicators[f"ema_{period}"] = ta.trend.ema_indicator(df['close'], window=period).iloc[-1]
        
        return indicators
    
    def _calculate_momentum_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate momentum indicators."""
        indicators = {}
        
        # RSI
        indicators["rsi"] = ta.momentum.rsi(df['close'], window=14).iloc[-1]
        
        # MACD
        macd = ta.trend.macd(df['close'])
        indicators["macd"] = macd.iloc[-1]
        indicators["macd_signal"] = ta.trend.macd_signal(df['close']).iloc[-1]
        indicators["macd_histogram"] = ta.trend.macd_diff(df['close']).iloc[-1]
        
        # Stochastic
        stoch = ta.momentum.stoch(df['high'], df['low'], df['close'])
        indicators["stochastic_k"] = stoch.iloc[-1]
        indicators["stochastic_d"] = ta.momentum.stoch_signal(df['high'], df['low'], df['close']).iloc[-1]
        
        # Williams %R
        indicators["williams_r"] = ta.momentum.williams_r(df['high'], df['low'], df['close']).iloc[-1]
        
        # Rate of Change
        indicators["roc"] = ta.momentum.roc(df['close'], window=10).iloc[-1]
        
        return indicators
    
    def _calculate_volatility_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate volatility indicators."""
        indicators = {}
        
        # Bollinger Bands
        bb_upper = ta.volatility.bollinger_hband(df['close'])
        bb_middle = ta.volatility.bollinger_mavg(df['close'])
        bb_lower = ta.volatility.bollinger_lband(df['close'])
        
        indicators["bollinger_upper"] = bb_upper.iloc[-1]
        indicators["bollinger_middle"] = bb_middle.iloc[-1]
        indicators["bollinger_lower"] = bb_lower.iloc[-1]
        indicators["bollinger_width"] = (bb_upper.iloc[-1] - bb_lower.iloc[-1]) / bb_middle.iloc[-1]
        
        # Average True Range
        indicators["atr"] = ta.volatility.average_true_range(df['high'], df['low'], df['close']).iloc[-1]
        
        # Keltner Channels
        kc_upper = ta.volatility.keltner_channel_hband(df['high'], df['low'], df['close'])
        kc_middle = ta.volatility.keltner_channel_mband(df['high'], df['low'], df['close'])
        kc_lower = ta.volatility.keltner_channel_lband(df['high'], df['low'], df['close'])
        
        indicators["keltner_upper"] = kc_upper.iloc[-1]
        indicators["keltner_middle"] = kc_middle.iloc[-1]
        indicators["keltner_lower"] = kc_lower.iloc[-1]
        
        return indicators
    
    def _calculate_volume_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate volume indicators."""
        indicators = {}
        
        # On-Balance Volume
        indicators["obv"] = ta.volume.on_balance_volume(df['close'], df['volume']).iloc[-1]
        
        # Accumulation/Distribution Line
        indicators["ad_line"] = ta.volume.acc_dist_index(df['high'], df['low'], df['close'], df['volume']).iloc[-1]
        
        # Money Flow Index
        indicators["mfi"] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume']).iloc[-1]
        
        # Volume Price Trend
        indicators["vpt"] = ta.volume.volume_price_trend(df['close'], df['volume']).iloc[-1]
        
        # Chaikin Money Flow
        indicators["cmf"] = ta.volume.chaikin_money_flow(df['high'], df['low'], df['close'], df['volume']).iloc[-1]
        
        return indicators
    
    def _calculate_trend_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate trend indicators."""
        indicators = {}
        
        # Average Directional Index
        indicators["adx"] = ta.trend.adx(df['high'], df['low'], df['close']).iloc[-1]
        
        # Commodity Channel Index
        indicators["cci"] = ta.trend.cci(df['high'], df['low'], df['close']).iloc[-1]
        
        # Aroon
        aroon = ta.trend.aroon(df['high'], df['low'])
        indicators["aroon_up"] = aroon['aroon_up'].iloc[-1]
        indicators["aroon_down"] = aroon['aroon_down'].iloc[-1]
        
        # Parabolic SAR
        indicators["psar"] = ta.trend.psar_up(df['high'], df['low'], df['close']).iloc[-1]
        
        # Ichimoku Cloud
        ichimoku = ta.trend.ichimoku_a(df['high'], df['low'])
        indicators["ichimoku_a"] = ichimoku.iloc[-1]
        indicators["ichimoku_b"] = ta.trend.ichimoku_b(df['high'], df['low']).iloc[-1]
        
        return indicators


class RiskCalculatorTool(BaseTool):
    """Tool for risk calculations."""
    
    name: str = "Risk Calculator Tool"
    description: str = "Calculates various risk metrics and assessments"
    
    def _run(self, price_data: List[Dict], risk_free_rate: float = 0.02) -> Dict[str, Any]:
        """Calculate risk metrics."""
        try:
            df = pd.DataFrame(price_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Calculate returns
            returns = df['close'].pct_change().dropna()
            
            if len(returns) < 2:
                return {"error": "Insufficient data for risk calculation"}
            
            # Basic risk metrics
            risk_metrics = self._calculate_basic_risk_metrics(returns, risk_free_rate)
            
            # Advanced risk metrics
            advanced_metrics = self._calculate_advanced_risk_metrics(returns)
            
            # Risk assessment
            risk_assessment = self._assess_risk_level(risk_metrics, advanced_metrics)
            
            return {
                "basic_metrics": risk_metrics,
                "advanced_metrics": advanced_metrics,
                "risk_assessment": risk_assessment
            }
            
        except Exception as e:
            return {"error": f"Risk calculation failed: {str(e)}"}
    
    def _calculate_basic_risk_metrics(self, returns: pd.Series, risk_free_rate: float) -> Dict[str, Any]:
        """Calculate basic risk metrics."""
        mean_return = returns.mean()
        volatility = returns.std()
        excess_return = mean_return - risk_free_rate
        
        # Sharpe ratio
        sharpe_ratio = excess_return / volatility if volatility > 0 else 0
        
        # Sortino ratio
        downside_returns = returns[returns < 0]
        downside_deviation = downside_returns.std() if len(downside_returns) > 0 else 0
        sortino_ratio = excess_return / downside_deviation if downside_deviation > 0 else 0
        
        return {
            "mean_return": mean_return,
            "volatility": volatility,
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "excess_return": excess_return
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
        
        # Beta (if market data available)
        beta = None  # Would need market returns to calculate
        
        return {
            "max_drawdown": max_drawdown,
            "var_95": var_95,
            "cvar_95": cvar_95,
            "skewness": skewness,
            "kurtosis": kurtosis,
            "beta": beta
        }
    
    def _assess_risk_level(self, basic_metrics: Dict, advanced_metrics: Dict) -> Dict[str, Any]:
        """Assess overall risk level."""
        volatility = basic_metrics["volatility"]
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
            "return_risk": "Low" if sharpe_ratio > 0.5 else "High"
        }


class ValuationCalculatorTool(BaseTool):
    """Tool for valuation calculations."""
    
    name: str = "Valuation Calculator Tool"
    description: str = "Calculates various valuation metrics and models"
    
    def _run(self, valuation_type: str, **kwargs) -> Dict[str, Any]:
        """Calculate valuation metrics."""
        try:
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
    
    def _calculate_dcf(self, current_earnings: float, growth_rate: float, 
                      discount_rate: float, terminal_growth_rate: float = 0.02,
                      years: int = 5) -> Dict[str, Any]:
        """Calculate DCF valuation."""
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
        terminal_value = projected_earnings[-1] / (discount_rate - terminal_growth_rate)
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
                "years": years
            }
        }
    
    def _calculate_comparable_valuation(self, current_price: float, 
                                      pe_ratio: float, industry_pe: float,
                                      pb_ratio: float, industry_pb: float) -> Dict[str, Any]:
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
            "upside_potential": (avg_valuation - current_price) / current_price * 100 if avg_valuation else None
        }
    
    def _calculate_asset_based_valuation(self, total_assets: float, total_liabilities: float,
                                       intangible_assets: float = 0) -> Dict[str, Any]:
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
                "intangible_assets": intangible_assets
            }
        }
    
    def _calculate_dividend_discount(self, current_dividend: float, dividend_growth_rate: float,
                                   required_return: float) -> Dict[str, Any]:
        """Calculate dividend discount model valuation."""
        if required_return <= dividend_growth_rate:
            return {"error": "Required return must be greater than dividend growth rate"}
        
        intrinsic_value = current_dividend * (1 + dividend_growth_rate) / (required_return - dividend_growth_rate)
        
        return {
            "intrinsic_value": intrinsic_value,
            "current_dividend": current_dividend,
            "dividend_growth_rate": dividend_growth_rate,
            "required_return": required_return,
            "assumptions": {
                "constant_growth": True,
                "perpetual_dividends": True
            }
        }
