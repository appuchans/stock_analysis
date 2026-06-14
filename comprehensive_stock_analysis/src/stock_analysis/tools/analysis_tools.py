"""Analysis tools for stock analysis."""

import json
import pandas as pd
import numpy as np
from datetime import datetime
from typing import List, Dict, Any
from ._indicators import (
    sma, ema, rsi, macd_line, macd_signal_line, macd_diff,
    stoch, stoch_signal, williams_r, roc,
    atr, bollinger_upper, bollinger_middle, bollinger_lower,
    adx, cci, aroon_up, aroon_down,
    obv, acc_dist_index, money_flow_index,
    _last,
)
try:
    from scipy import stats
except ImportError:
    stats = None  # type: ignore[assignment]

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


class TechnicalAnalysisTool(BaseTool):
    """Tool for technical analysis of stocks."""
    
    name: str = "Technical Analysis Tool"
    description: str = "Performs comprehensive technical analysis including indicators, patterns, and signals"
    
    def _run(self, price_data: str, volume_data: str) -> Dict[str, Any]:
        """Perform technical analysis. price_data and volume_data are JSON arrays of OHLCV records."""
        try:
            price_list = _parse_list(price_data)
            vol_list = _parse_list(volume_data)
            if not price_list:
                return {"error": "price_data is empty or null — pass a JSON array of OHLCV records"}
            # Convert to DataFrame
            df = pd.DataFrame(price_list)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)

            if vol_list:
                vol_df = pd.DataFrame(vol_list)
                vol_df['timestamp'] = pd.to_datetime(vol_df['timestamp'])
                vol_df.set_index('timestamp', inplace=True)
                # Drop columns already present in the price frame to avoid join collisions
                vol_df = vol_df[[c for c in vol_df.columns if c not in df.columns]]
                df = df.join(vol_df, how='left')
            if 'volume' not in df.columns:
                df['volume'] = float('nan')
            
            # Calculate technical indicators
            indicators = self._calculate_indicators(df)
            
            # Identify patterns
            patterns = self._identify_patterns(df)
            
            # Generate signals
            signals = self._generate_signals(df, indicators)
            
            # Calculate trend strength
            trend_strength = self._calculate_trend_strength(df)
            
            # Calculate support and resistance
            support_resistance = self._calculate_support_resistance(df)
            
            return {
                "indicators": indicators,
                "patterns": patterns,
                "signals": signals,
                "trend_strength": trend_strength,
                "support_resistance": support_resistance,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Technical analysis failed: {str(e)}"}
    
    def _calculate_indicators(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate technical indicators."""
        c, h, l, v = df['close'], df['high'], df['low'], df['volume']
        return {
            # Moving averages
            'sma_20':          _last(sma(c, 20)),
            'sma_50':          _last(sma(c, 50)),
            'sma_200':         _last(sma(c, 200)),
            'ema_12':          _last(ema(c, 12)),
            'ema_26':          _last(ema(c, 26)),
            # Momentum
            'rsi':             _last(rsi(c, 14)),
            'macd':            _last(macd_line(c)),
            'macd_signal':     _last(macd_signal_line(c)),
            'macd_histogram':  _last(macd_diff(c)),
            'stochastic_k':    _last(stoch(h, l, c)),
            'stochastic_d':    _last(stoch_signal(h, l, c)),
            'williams_r':      _last(williams_r(h, l, c)),
            'momentum':        _last(roc(c, 10)),
            # Volatility
            'bollinger_upper': _last(bollinger_upper(c)),
            'bollinger_middle': _last(bollinger_middle(c)),
            'bollinger_lower': _last(bollinger_lower(c)),
            'atr':             _last(atr(h, l, c)),
            # Trend
            'adx':             _last(adx(h, l, c)),
            'cci':             _last(cci(h, l, c)),
            'aroon_up':        _last(aroon_up(h)),
            'aroon_down':      _last(aroon_down(l)),
            # Volume
            'obv':             _last(obv(c, v)),
            'ad_line':         _last(acc_dist_index(h, l, c, v)),
            'mfi':             _last(money_flow_index(h, l, c, v)),
        }
    
    def _identify_patterns(self, df: pd.DataFrame) -> List[Dict[str, Any]]:
        """Identify chart patterns."""
        patterns = []
        
        # Simple pattern detection
        recent_data = df.tail(20)
        
        # Double top/bottom detection
        if len(recent_data) >= 10:
            highs = recent_data['high'].rolling(window=3).max()
            lows = recent_data['low'].rolling(window=3).min()
            
            # Check for double top
            if len(highs.dropna()) >= 2:
                peak1 = highs.nlargest(2).iloc[0]
                peak2 = highs.nlargest(2).iloc[1]
                if abs(peak1 - peak2) / peak1 < 0.02:  # Within 2%
                    patterns.append({
                        "type": "double_top",
                        "strength": 0.7,
                        "description": "Double top pattern detected"
                    })
            
            # Check for double bottom
            if len(lows.dropna()) >= 2:
                trough1 = lows.nsmallest(2).iloc[0]
                trough2 = lows.nsmallest(2).iloc[1]
                if abs(trough1 - trough2) / trough1 < 0.02:  # Within 2%
                    patterns.append({
                        "type": "double_bottom",
                        "strength": 0.7,
                        "description": "Double bottom pattern detected"
                    })
        
        return patterns
    
    def _generate_signals(self, df: pd.DataFrame, indicators: Dict[str, Any]) -> Dict[str, Any]:
        """Generate trading signals."""
        signals = {
            "buy_signals": 0,
            "sell_signals": 0,
            "neutral_signals": 0,
            "signal_strength": 0.0,
            "recommendation": "HOLD"
        }
        
        buy_count = 0
        sell_count = 0
        
        # RSI signals
        if indicators.get('rsi'):
            if indicators['rsi'] < 30:
                buy_count += 1
            elif indicators['rsi'] > 70:
                sell_count += 1
        
        # MACD signals
        if indicators.get('macd') and indicators.get('macd_signal'):
            if indicators['macd'] > indicators['macd_signal']:
                buy_count += 1
            else:
                sell_count += 1
        
        # Moving average signals
        if indicators.get('sma_20') and indicators.get('sma_50'):
            if indicators['sma_20'] > indicators['sma_50']:
                buy_count += 1
            else:
                sell_count += 1
        
        # Stochastic signals
        if indicators.get('stochastic_k') and indicators.get('stochastic_d'):
            if indicators['stochastic_k'] > indicators['stochastic_d']:
                buy_count += 1
            else:
                sell_count += 1
        
        signals["buy_signals"] = buy_count
        signals["sell_signals"] = sell_count
        signals["neutral_signals"] = 4 - buy_count - sell_count
        
        # Calculate signal strength
        total_signals = buy_count + sell_count
        if total_signals > 0:
            signals["signal_strength"] = abs(buy_count - sell_count) / total_signals
        
        # Generate recommendation
        if buy_count > sell_count:
            signals["recommendation"] = "BUY"
        elif sell_count > buy_count:
            signals["recommendation"] = "SELL"
        else:
            signals["recommendation"] = "HOLD"
        
        return signals
    
    def _calculate_trend_strength(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate trend strength."""
        if len(df) < 20:
            return {"trend": "insufficient_data", "strength": 0.0}
        if stats is None:
            return {"trend": "unknown", "strength": 0.0, "note": "scipy not installed"}

        # Calculate linear regression slope
        x = np.arange(len(df))
        y = df['close'].values
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)
        
        # Determine trend direction
        if slope > 0:
            trend = "uptrend"
        elif slope < 0:
            trend = "downtrend"
        else:
            trend = "sideways"
        
        # Calculate trend strength (R-squared)
        strength = r_value ** 2
        
        return {
            "trend": trend,
            "strength": strength,
            "slope": slope,
            "r_squared": strength,
            "p_value": p_value
        }
    
    def _calculate_support_resistance(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculate support and resistance levels."""
        if len(df) < 20:
            return {"support": None, "resistance": None}
        
        recent_data = df.tail(50)
        
        # Find local maxima and minima
        highs = recent_data['high']
        lows = recent_data['low']
        
        # Simple support/resistance calculation
        resistance = highs.rolling(window=5).max().max()
        support = lows.rolling(window=5).min().min()
        
        return {
            "support": support,
            "resistance": resistance,
            "current_price": df['close'].iloc[-1],
            "support_distance": (df['close'].iloc[-1] - support) / df['close'].iloc[-1] * 100,
            "resistance_distance": (resistance - df['close'].iloc[-1]) / df['close'].iloc[-1] * 100
        }


class FundamentalAnalysisTool(BaseTool):
    """Tool for fundamental analysis of stocks."""
    
    name: str = "Fundamental Analysis Tool"
    description: str = "Performs comprehensive fundamental analysis including valuation, profitability, and financial health"
    
    def _run(self, fundamental_data: str, market_data: str) -> Dict[str, Any]:
        """Perform fundamental analysis. fundamental_data and market_data are JSON objects."""
        try:
            fundamental_data = _parse_dict(fundamental_data)
            market_data = _parse_dict(market_data)
            analysis = {}

            # Valuation Analysis
            valuation = self._analyze_valuation(fundamental_data, market_data)
            analysis["valuation"] = valuation

            # Profitability Analysis
            profitability = self._analyze_profitability(fundamental_data)
            analysis["profitability"] = profitability

            # Financial Health Analysis
            financial_health = self._analyze_financial_health(fundamental_data)
            analysis["financial_health"] = financial_health
            
            # Growth Analysis
            growth = self._analyze_growth(fundamental_data)
            analysis["growth"] = growth
            
            # Overall Score
            overall_score = self._calculate_overall_score(valuation, profitability, financial_health, growth)
            analysis["overall_score"] = overall_score
            
            return analysis
            
        except Exception as e:
            return {"error": f"Fundamental analysis failed: {str(e)}"}
    
    def _analyze_valuation(self, fundamental_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze valuation metrics."""
        valuation = {
            "pe_ratio": fundamental_data.get("pe_ratio"),
            "pb_ratio": fundamental_data.get("pb_ratio"),
            "ps_ratio": fundamental_data.get("ps_ratio"),
            "peg_ratio": fundamental_data.get("peg_ratio"),
            "ev_ebitda": fundamental_data.get("ev_ebitda"),
            "score": 0.0,
            "assessment": "neutral"
        }
        
        # Score based on valuation metrics
        score = 0
        total_metrics = 0
        
        if valuation["pe_ratio"]:
            total_metrics += 1
            if 10 <= valuation["pe_ratio"] <= 20:
                score += 1
            elif 5 <= valuation["pe_ratio"] < 10 or 20 < valuation["pe_ratio"] <= 30:
                score += 0.5
        
        if valuation["pb_ratio"]:
            total_metrics += 1
            if 1 <= valuation["pb_ratio"] <= 3:
                score += 1
            elif 0.5 <= valuation["pb_ratio"] < 1 or 3 < valuation["pb_ratio"] <= 5:
                score += 0.5
        
        if valuation["peg_ratio"]:
            total_metrics += 1
            if 0.5 <= valuation["peg_ratio"] <= 1.5:
                score += 1
            elif 0.3 <= valuation["peg_ratio"] < 0.5 or 1.5 < valuation["peg_ratio"] <= 2:
                score += 0.5
        
        if total_metrics > 0:
            valuation["score"] = score / total_metrics
        
        # Assessment
        if valuation["score"] >= 0.8:
            valuation["assessment"] = "undervalued"
        elif valuation["score"] <= 0.3:
            valuation["assessment"] = "overvalued"
        else:
            valuation["assessment"] = "fairly_valued"
        
        return valuation
    
    def _analyze_profitability(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze profitability metrics."""
        profitability = {
            "roe": fundamental_data.get("roe"),
            "roa": fundamental_data.get("roa"),
            "roic": fundamental_data.get("roic"),
            "gross_margin": fundamental_data.get("gross_margin"),
            "operating_margin": fundamental_data.get("operating_margin"),
            "net_margin": fundamental_data.get("net_margin"),
            "score": 0.0,
            "assessment": "neutral"
        }
        
        # Score based on profitability metrics
        score = 0
        total_metrics = 0
        
        if profitability["roe"]:
            total_metrics += 1
            if profitability["roe"] >= 15:
                score += 1
            elif profitability["roe"] >= 10:
                score += 0.5
        
        if profitability["roa"]:
            total_metrics += 1
            if profitability["roa"] >= 5:
                score += 1
            elif profitability["roa"] >= 3:
                score += 0.5
        
        if profitability["net_margin"]:
            total_metrics += 1
            if profitability["net_margin"] >= 10:
                score += 1
            elif profitability["net_margin"] >= 5:
                score += 0.5
        
        if total_metrics > 0:
            profitability["score"] = score / total_metrics
        
        # Assessment
        if profitability["score"] >= 0.8:
            profitability["assessment"] = "excellent"
        elif profitability["score"] >= 0.6:
            profitability["assessment"] = "good"
        elif profitability["score"] >= 0.4:
            profitability["assessment"] = "average"
        else:
            profitability["assessment"] = "poor"
        
        return profitability
    
    def _analyze_financial_health(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze financial health metrics."""
        financial_health = {
            "debt_to_equity": fundamental_data.get("debt_to_equity"),
            "current_ratio": fundamental_data.get("current_ratio"),
            "quick_ratio": fundamental_data.get("quick_ratio"),
            "interest_coverage": fundamental_data.get("interest_coverage"),
            "score": 0.0,
            "assessment": "neutral"
        }
        
        # Score based on financial health metrics
        score = 0
        total_metrics = 0
        
        if financial_health["debt_to_equity"]:
            total_metrics += 1
            if financial_health["debt_to_equity"] <= 0.5:
                score += 1
            elif financial_health["debt_to_equity"] <= 1.0:
                score += 0.5
        
        if financial_health["current_ratio"]:
            total_metrics += 1
            if 1.5 <= financial_health["current_ratio"] <= 3.0:
                score += 1
            elif 1.0 <= financial_health["current_ratio"] < 1.5 or 3.0 < financial_health["current_ratio"] <= 5.0:
                score += 0.5
        
        if financial_health["quick_ratio"]:
            total_metrics += 1
            if financial_health["quick_ratio"] >= 1.0:
                score += 1
            elif financial_health["quick_ratio"] >= 0.5:
                score += 0.5
        
        if total_metrics > 0:
            financial_health["score"] = score / total_metrics
        
        # Assessment
        if financial_health["score"] >= 0.8:
            financial_health["assessment"] = "excellent"
        elif financial_health["score"] >= 0.6:
            financial_health["assessment"] = "good"
        elif financial_health["score"] >= 0.4:
            financial_health["assessment"] = "average"
        else:
            financial_health["assessment"] = "poor"
        
        return financial_health
    
    def _analyze_growth(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze growth metrics."""
        growth = {
            "revenue_growth": fundamental_data.get("revenue_growth"),
            "earnings_growth": fundamental_data.get("earnings_growth"),
            "book_value_growth": fundamental_data.get("book_value_growth"),
            "score": 0.0,
            "assessment": "neutral"
        }
        
        # Score based on growth metrics
        score = 0
        total_metrics = 0
        
        if growth["revenue_growth"]:
            total_metrics += 1
            if growth["revenue_growth"] >= 10:
                score += 1
            elif growth["revenue_growth"] >= 5:
                score += 0.5
        
        if growth["earnings_growth"]:
            total_metrics += 1
            if growth["earnings_growth"] >= 15:
                score += 1
            elif growth["earnings_growth"] >= 10:
                score += 0.5
        
        if total_metrics > 0:
            growth["score"] = score / total_metrics
        
        # Assessment
        if growth["score"] >= 0.8:
            growth["assessment"] = "high_growth"
        elif growth["score"] >= 0.6:
            growth["assessment"] = "moderate_growth"
        elif growth["score"] >= 0.4:
            growth["assessment"] = "slow_growth"
        else:
            growth["assessment"] = "declining"
        
        return growth
    
    def _calculate_overall_score(self, valuation: Dict, profitability: Dict, 
                               financial_health: Dict, growth: Dict) -> Dict[str, Any]:
        """Calculate overall fundamental analysis score."""
        scores = []
        
        if valuation["score"] > 0:
            scores.append(valuation["score"])
        if profitability["score"] > 0:
            scores.append(profitability["score"])
        if financial_health["score"] > 0:
            scores.append(financial_health["score"])
        if growth["score"] > 0:
            scores.append(growth["score"])
        
        if not scores:
            return {"overall_score": 0.0, "assessment": "insufficient_data"}
        
        overall_score = sum(scores) / len(scores)
        
        if overall_score >= 0.8:
            assessment = "excellent"
        elif overall_score >= 0.6:
            assessment = "good"
        elif overall_score >= 0.4:
            assessment = "average"
        else:
            assessment = "poor"
        
        return {
            "overall_score": overall_score,
            "assessment": assessment,
            "component_scores": {
                "valuation": valuation["score"],
                "profitability": profitability["score"],
                "financial_health": financial_health["score"],
                "growth": growth["score"]
            }
        }


class RiskAnalysisTool(BaseTool):
    """Tool for risk analysis of stocks."""
    
    name: str = "Risk Analysis Tool"
    description: str = "Performs comprehensive risk analysis including market risk, credit risk, and operational risk"
    
    def _run(self, price_data: str, fundamental_data: str) -> Dict[str, Any]:
        """Perform risk analysis. price_data is a JSON array of OHLCV records; fundamental_data is a JSON object."""
        try:
            fundamental_data = _parse_dict(fundamental_data)
            price_list = _parse_list(price_data)
            if not price_list:
                return {"error": "price_data is empty or null"}
            df = pd.DataFrame(price_list)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Calculate returns
            returns = df['close'].pct_change().dropna()
            
            if len(returns) < 2:
                return {"error": "Insufficient data for risk analysis"}
            
            # Market Risk Analysis
            market_risk = self._analyze_market_risk(returns)
            
            # Credit Risk Analysis
            credit_risk = self._analyze_credit_risk(fundamental_data)
            
            # Liquidity Risk Analysis
            liquidity_risk = self._analyze_liquidity_risk(fundamental_data)
            
            # Operational Risk Analysis
            operational_risk = self._analyze_operational_risk(fundamental_data)
            
            # Overall Risk Assessment
            overall_risk = self._assess_overall_risk(market_risk, credit_risk, liquidity_risk, operational_risk)
            
            return {
                "market_risk": market_risk,
                "credit_risk": credit_risk,
                "liquidity_risk": liquidity_risk,
                "operational_risk": operational_risk,
                "overall_risk": overall_risk,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Risk analysis failed: {str(e)}"}
    
    def _analyze_market_risk(self, returns: pd.Series) -> Dict[str, Any]:
        """Analyze market risk."""
        volatility = returns.std() * np.sqrt(252)  # Annualized volatility
        
        # Value at Risk (95% confidence)
        var_95 = returns.quantile(0.05)
        
        # Maximum drawdown
        cumulative_returns = (1 + returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # Beta (would need market data)
        beta = None
        
        return {
            "volatility": volatility,
            "var_95": var_95,
            "max_drawdown": max_drawdown,
            "beta": beta,
            "risk_level": "High" if volatility > 0.3 else "Medium" if volatility > 0.2 else "Low"
        }
    
    def _analyze_credit_risk(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze credit risk."""
        debt_to_equity = fundamental_data.get("debt_to_equity") or 0
        interest_coverage = fundamental_data.get("interest_coverage") or 0
        current_ratio = fundamental_data.get("current_ratio") or 0
        
        # Credit risk score
        credit_score = 0
        if debt_to_equity <= 0.5:
            credit_score += 1
        elif debt_to_equity <= 1.0:
            credit_score += 0.5
        
        if interest_coverage >= 5:
            credit_score += 1
        elif interest_coverage >= 2.5:
            credit_score += 0.5
        
        if current_ratio >= 1.5:
            credit_score += 1
        elif current_ratio >= 1.0:
            credit_score += 0.5
        
        risk_level = "Low" if credit_score >= 2.5 else "Medium" if credit_score >= 1.5 else "High"
        
        return {
            "debt_to_equity": debt_to_equity,
            "interest_coverage": interest_coverage,
            "current_ratio": current_ratio,
            "credit_score": credit_score,
            "risk_level": risk_level
        }
    
    def _analyze_liquidity_risk(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze liquidity risk."""
        current_ratio = fundamental_data.get("current_ratio") or 0
        quick_ratio = fundamental_data.get("quick_ratio") or 0
        cash_ratio = fundamental_data.get("cash_ratio") or 0
        
        # Liquidity risk score
        liquidity_score = 0
        if current_ratio >= 2.0:
            liquidity_score += 1
        elif current_ratio >= 1.5:
            liquidity_score += 0.5
        
        if quick_ratio >= 1.0:
            liquidity_score += 1
        elif quick_ratio >= 0.5:
            liquidity_score += 0.5
        
        risk_level = "Low" if liquidity_score >= 2.0 else "Medium" if liquidity_score >= 1.0 else "High"
        
        return {
            "current_ratio": current_ratio,
            "quick_ratio": quick_ratio,
            "cash_ratio": cash_ratio,
            "liquidity_score": liquidity_score,
            "risk_level": risk_level
        }
    
    def _analyze_operational_risk(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze operational risk."""
        # This is a simplified operational risk analysis
        # In practice, this would involve more complex metrics
        
        revenue_growth = fundamental_data.get("revenue_growth") or 0
        earnings_growth = fundamental_data.get("earnings_growth") or 0
        roe = fundamental_data.get("roe") or 0
        
        # Operational risk score
        operational_score = 0
        if revenue_growth >= 10:
            operational_score += 1
        elif revenue_growth >= 5:
            operational_score += 0.5
        
        if earnings_growth >= 15:
            operational_score += 1
        elif earnings_growth >= 10:
            operational_score += 0.5
        
        if roe >= 15:
            operational_score += 1
        elif roe >= 10:
            operational_score += 0.5
        
        risk_level = "Low" if operational_score >= 2.5 else "Medium" if operational_score >= 1.5 else "High"
        
        return {
            "revenue_growth": revenue_growth,
            "earnings_growth": earnings_growth,
            "roe": roe,
            "operational_score": operational_score,
            "risk_level": risk_level
        }
    
    def _assess_overall_risk(self, market_risk: Dict, credit_risk: Dict, 
                           liquidity_risk: Dict, operational_risk: Dict) -> Dict[str, Any]:
        """Assess overall risk level."""
        risk_scores = []
        
        # Convert risk levels to scores
        risk_level_scores = {"Low": 1, "Medium": 2, "High": 3}
        
        risk_scores.append(risk_level_scores.get(market_risk["risk_level"], 2))
        risk_scores.append(risk_level_scores.get(credit_risk["risk_level"], 2))
        risk_scores.append(risk_level_scores.get(liquidity_risk["risk_level"], 2))
        risk_scores.append(risk_level_scores.get(operational_risk["risk_level"], 2))
        
        avg_risk_score = sum(risk_scores) / len(risk_scores)
        
        if avg_risk_score <= 1.5:
            overall_risk_level = RiskLevel.LOW
        elif avg_risk_score <= 2.5:
            overall_risk_level = RiskLevel.MEDIUM
        else:
            overall_risk_level = RiskLevel.HIGH
        
        return {
            "overall_risk_level": overall_risk_level,
            "risk_score": avg_risk_score,
            "component_risks": {
                "market_risk": market_risk["risk_level"],
                "credit_risk": credit_risk["risk_level"],
                "liquidity_risk": liquidity_risk["risk_level"],
                "operational_risk": operational_risk["risk_level"]
            }
        }


class ValuationTool(BaseTool):
    """Tool for valuation analysis."""
    
    name: str = "Valuation Tool"
    description: str = "Performs comprehensive valuation analysis using multiple methodologies"
    
    def _run(self, fundamental_data: str, market_data: str) -> Dict[str, Any]:
        """Perform valuation analysis. fundamental_data and market_data are JSON objects."""
        try:
            fundamental_data = _parse_dict(fundamental_data)
            market_data = _parse_dict(market_data)
            current_price = market_data.get("current_price") or 0
            
            # DCF Valuation
            dcf_valuation = self._dcf_valuation(fundamental_data)
            
            # Comparable Valuation
            comparable_valuation = self._comparable_valuation(fundamental_data, market_data)
            
            # Asset-based Valuation
            asset_valuation = self._asset_based_valuation(fundamental_data)
            
            # Overall Valuation
            overall_valuation = self._calculate_overall_valuation(
                dcf_valuation, comparable_valuation, asset_valuation, current_price
            )
            
            return {
                "dcf_valuation": dcf_valuation,
                "comparable_valuation": comparable_valuation,
                "asset_valuation": asset_valuation,
                "overall_valuation": overall_valuation,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Valuation analysis failed: {str(e)}"}
    
    def _dcf_valuation(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """DCF valuation analysis."""
        # Simplified DCF calculation
        current_earnings = fundamental_data.get("net_income") or 0
        growth_rate = fundamental_data.get("earnings_growth") or 0.05  # Default 5%
        discount_rate = 0.10  # Default 10%

        if current_earnings <= 0:
            return {"intrinsic_value": None, "method": "DCF", "status": "insufficient_data"}

        # The Gordon growth model breaks down when growth >= discount rate
        if growth_rate >= discount_rate:
            return {
                "intrinsic_value": None,
                "method": "DCF",
                "status": "not_applicable",
                "note": "Earnings growth exceeds discount rate; perpetuity model not valid",
            }

        # Simple perpetuity growth model
        intrinsic_value = current_earnings * (1 + growth_rate) / (discount_rate - growth_rate)
        
        return {
            "intrinsic_value": intrinsic_value,
            "method": "DCF",
            "assumptions": {
                "growth_rate": growth_rate,
                "discount_rate": discount_rate
            },
            "status": "calculated"
        }
    
    def _comparable_valuation(self, fundamental_data: Dict[str, Any], market_data: Dict[str, Any], industry_pe: float = 15.0) -> Dict[str, Any]:
        """Comparable valuation analysis."""
        current_price = market_data.get("current_price") or 0
        pe_ratio = fundamental_data.get("pe_ratio") or 0

        if pe_ratio <= 0:
            return {"intrinsic_value": None, "method": "Comparable", "status": "insufficient_data"}

        intrinsic_value = current_price * (industry_pe / pe_ratio)
        
        return {
            "intrinsic_value": intrinsic_value,
            "method": "Comparable",
            "assumptions": {
                "industry_pe": industry_pe,
                "current_pe": pe_ratio
            },
            "status": "calculated"
        }
    
    def _asset_based_valuation(self, fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Asset-based valuation analysis."""
        total_assets = fundamental_data.get("total_assets") or 0
        total_liabilities = fundamental_data.get("total_liabilities") or 0

        if total_assets <= 0:
            return {"intrinsic_value": None, "method": "Asset-based", "status": "insufficient_data"}
        
        book_value = total_assets - total_liabilities
        intrinsic_value = book_value  # Simplified: intrinsic value = book value
        
        return {
            "intrinsic_value": intrinsic_value,
            "method": "Asset-based",
            "assumptions": {
                "total_assets": total_assets,
                "total_liabilities": total_liabilities
            },
            "status": "calculated"
        }
    
    def _calculate_overall_valuation(self, dcf_valuation: Dict, comparable_valuation: Dict, 
                                   asset_valuation: Dict, current_price: float) -> Dict[str, Any]:
        """Calculate overall valuation."""
        valuations = []
        
        if dcf_valuation.get("intrinsic_value"):
            valuations.append(dcf_valuation["intrinsic_value"])
        if comparable_valuation.get("intrinsic_value"):
            valuations.append(comparable_valuation["intrinsic_value"])
        if asset_valuation.get("intrinsic_value"):
            valuations.append(asset_valuation["intrinsic_value"])
        
        if not valuations:
            return {"intrinsic_value": None, "upside_potential": None, "assessment": "insufficient_data"}
        
        intrinsic_value = sum(valuations) / len(valuations)
        upside_potential = (intrinsic_value - current_price) / current_price * 100 if current_price > 0 else None

        if upside_potential is None:
            assessment = "unknown"
        elif upside_potential > 20:
            assessment = "undervalued"
        elif upside_potential < -20:
            assessment = "overvalued"
        else:
            assessment = "fairly_valued"
        
        return {
            "intrinsic_value": intrinsic_value,
            "current_price": current_price,
            "upside_potential": upside_potential,
            "assessment": assessment,
            "valuation_count": len(valuations)
        }


class ComparisonTool(BaseTool):
    """Tool for comparing stocks and industries."""
    
    name: str = "Comparison Tool"
    description: str = "Compares stocks against industry peers and market benchmarks"
    
    def _run(self, stock_data: str, industry_data: str) -> Dict[str, Any]:
        """Perform comparison analysis. stock_data and industry_data are JSON objects."""
        try:
            stock_data = _parse_dict(stock_data)
            industry_data = _parse_dict(industry_data)
            # Industry comparison
            industry_comparison = self._compare_industry(stock_data, industry_data)

            # Peer comparison (simplified)
            peer_comparison = self._compare_peers(stock_data)

            # Market comparison
            market_comparison = self._compare_market(stock_data)
            
            return {
                "industry_comparison": industry_comparison,
                "peer_comparison": peer_comparison,
                "market_comparison": market_comparison,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Comparison analysis failed: {str(e)}"}
    
    def _compare_industry(self, stock_data: Dict[str, Any], industry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compare against industry averages."""
        stock_pe = stock_data.get("pe_ratio") or 0
        industry_pe = industry_data.get("pe_ratio_avg") or 0
        
        pe_comparison = "above" if stock_pe > industry_pe else "below" if stock_pe < industry_pe else "equal"
        
        return {
            "pe_comparison": pe_comparison,
            "stock_pe": stock_pe,
            "industry_pe": industry_pe,
            "pe_difference": stock_pe - industry_pe if industry_pe > 0 else None
        }
    
    def _compare_peers(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compare against peer companies (simplified)."""
        # This would typically involve comparing against a list of peer companies
        return {
            "peer_count": 0,
            "comparison_status": "insufficient_data",
            "note": "Peer comparison requires additional data"
        }
    
    def _compare_market(self, stock_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compare against market benchmarks."""
        # This would typically involve comparing against market indices
        return {
            "market_comparison": "insufficient_data",
            "note": "Market comparison requires additional data"
        }