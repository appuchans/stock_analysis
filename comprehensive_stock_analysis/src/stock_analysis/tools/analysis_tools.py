"""Analysis tools for stock analysis."""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    from sklearn.decomposition import PCA
except ImportError:
    StandardScaler = None  # type: ignore[assignment,misc]
    KMeans = None  # type: ignore[assignment,misc]
    PCA = None  # type: ignore[assignment,misc]
try:
    import ta
except ImportError:
    ta = None  # type: ignore[assignment]
try:
    from scipy import stats
    from scipy.optimize import minimize
except ImportError:
    stats = None  # type: ignore[assignment]
    minimize = None  # type: ignore[assignment]
import warnings
warnings.filterwarnings('ignore')

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from ..models.stock_data import (
    TechnicalIndicators, FundamentalData, RiskMetrics, 
    AnalysisResult, InvestmentRecommendation, RecommendationType, RiskLevel
)


class TechnicalAnalysisTool(BaseTool):
    """Tool for technical analysis of stocks."""
    
    name: str = "Technical Analysis Tool"
    description: str = "Performs comprehensive technical analysis including indicators, patterns, and signals"
    
    def _run(self, price_data: List[Dict], volume_data: List[Dict]) -> Dict[str, Any]:
        """Perform technical analysis."""
        try:
            # Convert to DataFrame
            df = pd.DataFrame(price_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            vol_df = pd.DataFrame(volume_data)
            vol_df['timestamp'] = pd.to_datetime(vol_df['timestamp'])
            vol_df.set_index('timestamp', inplace=True)
            
            # Merge data
            df = df.join(vol_df, how='left')
            
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
        indicators = {}
        
        # Moving Averages
        indicators['sma_20'] = ta.trend.sma_indicator(df['close'], window=20).iloc[-1]
        indicators['sma_50'] = ta.trend.sma_indicator(df['close'], window=50).iloc[-1]
        indicators['sma_200'] = ta.trend.sma_indicator(df['close'], window=200).iloc[-1]
        indicators['ema_12'] = ta.trend.ema_indicator(df['close'], window=12).iloc[-1]
        indicators['ema_26'] = ta.trend.ema_indicator(df['close'], window=26).iloc[-1]
        
        # Momentum Indicators
        indicators['rsi'] = ta.momentum.rsi(df['close'], window=14).iloc[-1]
        macd_data = ta.trend.macd(df['close'])
        indicators['macd'] = macd_data.iloc[-1]
        indicators['macd_signal'] = ta.trend.macd_signal(df['close']).iloc[-1]
        indicators['macd_histogram'] = ta.trend.macd_diff(df['close']).iloc[-1]
        
        stoch = ta.momentum.stoch(df['high'], df['low'], df['close'])
        indicators['stochastic_k'] = stoch.iloc[-1]
        indicators['stochastic_d'] = ta.momentum.stoch_signal(df['high'], df['low'], df['close']).iloc[-1]
        indicators['williams_r'] = ta.momentum.williams_r(df['high'], df['low'], df['close']).iloc[-1]
        indicators['momentum'] = ta.momentum.roc(df['close'], window=10).iloc[-1]
        
        # Volatility Indicators
        bb = ta.volatility.bollinger_hband(df['close'])
        indicators['bollinger_upper'] = bb.iloc[-1]
        indicators['bollinger_middle'] = ta.volatility.bollinger_mavg(df['close']).iloc[-1]
        indicators['bollinger_lower'] = ta.volatility.bollinger_lband(df['close']).iloc[-1]
        indicators['atr'] = ta.volatility.average_true_range(df['high'], df['low'], df['close']).iloc[-1]
        
        # Trend Indicators
        indicators['adx'] = ta.trend.adx(df['high'], df['low'], df['close']).iloc[-1]
        indicators['cci'] = ta.trend.cci(df['high'], df['low'], df['close']).iloc[-1]
        aroon = ta.trend.aroon(df['high'], df['low'])
        indicators['aroon_up'] = aroon['aroon_up'].iloc[-1]
        indicators['aroon_down'] = aroon['aroon_down'].iloc[-1]
        
        # Volume Indicators
        indicators['obv'] = ta.volume.on_balance_volume(df['close'], df['volume']).iloc[-1]
        indicators['ad_line'] = ta.volume.acc_dist_index(df['high'], df['low'], df['close'], df['volume']).iloc[-1]
        indicators['mfi'] = ta.volume.money_flow_index(df['high'], df['low'], df['close'], df['volume']).iloc[-1]
        
        return indicators
    
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
    
    def _run(self, fundamental_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform fundamental analysis."""
        try:
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
    
    def _run(self, price_data: List[Dict], fundamental_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform risk analysis."""
        try:
            df = pd.DataFrame(price_data)
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
        debt_to_equity = fundamental_data.get("debt_to_equity", 0)
        interest_coverage = fundamental_data.get("interest_coverage", 0)
        current_ratio = fundamental_data.get("current_ratio", 0)
        
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
        current_ratio = fundamental_data.get("current_ratio", 0)
        quick_ratio = fundamental_data.get("quick_ratio", 0)
        cash_ratio = fundamental_data.get("cash_ratio", 0)
        
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
        
        revenue_growth = fundamental_data.get("revenue_growth", 0)
        earnings_growth = fundamental_data.get("earnings_growth", 0)
        roe = fundamental_data.get("roe", 0)
        
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


class SentimentAnalysisTool(BaseTool):
    """Tool for sentiment analysis of stocks."""
    
    name: str = "Sentiment Analysis Tool"
    description: str = "Performs sentiment analysis on news, social media, and analyst opinions"
    
    def _run(self, news_data: List[Dict], analyst_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform sentiment analysis."""
        try:
            # News sentiment analysis
            news_sentiment = self._analyze_news_sentiment(news_data)
            
            # Analyst sentiment analysis
            analyst_sentiment = self._analyze_analyst_sentiment(analyst_data)
            
            # Overall sentiment
            overall_sentiment = self._calculate_overall_sentiment(news_sentiment, analyst_sentiment)
            
            return {
                "news_sentiment": news_sentiment,
                "analyst_sentiment": analyst_sentiment,
                "overall_sentiment": overall_sentiment,
                "analysis_timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {"error": f"Sentiment analysis failed: {str(e)}"}
    
    def _analyze_news_sentiment(self, news_data: List[Dict]) -> Dict[str, Any]:
        """Analyze news sentiment."""
        if not news_data:
            return {"sentiment_score": 0.0, "sentiment": "neutral", "confidence": 0.0}
        
        # Simple sentiment analysis based on keywords
        positive_keywords = ["positive", "growth", "strong", "beat", "exceed", "outperform", "bullish", "upgrade"]
        negative_keywords = ["negative", "decline", "weak", "miss", "underperform", "bearish", "downgrade", "concern"]
        
        total_score = 0
        total_articles = len(news_data)
        
        for article in news_data:
            title = article.get("title", "").lower()
            summary = article.get("summary", "").lower()
            content = title + " " + summary
            
            positive_count = sum(1 for keyword in positive_keywords if keyword in content)
            negative_count = sum(1 for keyword in negative_keywords if keyword in content)
            
            article_score = (positive_count - negative_count) / max(positive_count + negative_count, 1)
            total_score += article_score
        
        avg_sentiment_score = total_score / total_articles if total_articles > 0 else 0
        
        if avg_sentiment_score > 0.1:
            sentiment = "positive"
        elif avg_sentiment_score < -0.1:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment_score": avg_sentiment_score,
            "sentiment": sentiment,
            "confidence": min(abs(avg_sentiment_score) * 2, 1.0),
            "total_articles": total_articles
        }
    
    def _analyze_analyst_sentiment(self, analyst_data: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze analyst sentiment."""
        if not analyst_data:
            return {"sentiment_score": 0.0, "sentiment": "neutral", "confidence": 0.0}
        
        # Analyze analyst recommendations
        strong_buy = analyst_data.get("strong_buy", 0)
        buy = analyst_data.get("buy", 0)
        hold = analyst_data.get("hold", 0)
        sell = analyst_data.get("sell", 0)
        strong_sell = analyst_data.get("strong_sell", 0)
        
        total_analysts = strong_buy + buy + hold + sell + strong_sell
        
        if total_analysts == 0:
            return {"sentiment_score": 0.0, "sentiment": "neutral", "confidence": 0.0}
        
        # Calculate weighted sentiment score
        sentiment_score = (strong_buy * 2 + buy * 1 + hold * 0 + sell * -1 + strong_sell * -2) / total_analysts
        
        if sentiment_score > 0.5:
            sentiment = "positive"
        elif sentiment_score < -0.5:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment_score": sentiment_score,
            "sentiment": sentiment,
            "confidence": min(abs(sentiment_score), 1.0),
            "total_analysts": total_analysts,
            "recommendations": {
                "strong_buy": strong_buy,
                "buy": buy,
                "hold": hold,
                "sell": sell,
                "strong_sell": strong_sell
            }
        }
    
    def _calculate_overall_sentiment(self, news_sentiment: Dict, analyst_sentiment: Dict) -> Dict[str, Any]:
        """Calculate overall sentiment."""
        news_score = news_sentiment.get("sentiment_score", 0)
        analyst_score = analyst_sentiment.get("sentiment_score", 0)
        
        # Weighted average (news and analyst sentiment equally weighted)
        overall_score = (news_score + analyst_score) / 2
        
        if overall_score > 0.2:
            sentiment = "positive"
        elif overall_score < -0.2:
            sentiment = "negative"
        else:
            sentiment = "neutral"
        
        return {
            "sentiment_score": overall_score,
            "sentiment": sentiment,
            "confidence": (news_sentiment.get("confidence", 0) + analyst_sentiment.get("confidence", 0)) / 2
        }


class ValuationTool(BaseTool):
    """Tool for valuation analysis."""
    
    name: str = "Valuation Tool"
    description: str = "Performs comprehensive valuation analysis using multiple methodologies"
    
    def _run(self, fundamental_data: Dict[str, Any], market_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform valuation analysis."""
        try:
            current_price = market_data.get("current_price", 0)
            
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
        current_earnings = fundamental_data.get("net_income", 0)
        growth_rate = fundamental_data.get("earnings_growth", 0.05)  # Default 5%
        discount_rate = 0.10  # Default 10%
        
        if current_earnings <= 0:
            return {"intrinsic_value": None, "method": "DCF", "status": "insufficient_data"}
        
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
        current_price = market_data.get("current_price", 0)
        pe_ratio = fundamental_data.get("pe_ratio", 0)

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
        total_assets = fundamental_data.get("total_assets", 0)
        total_liabilities = fundamental_data.get("total_liabilities", 0)
        
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
        
        if upside_potential > 20:
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
    
    def _run(self, stock_data: Dict[str, Any], industry_data: Dict[str, Any]) -> Dict[str, Any]:
        """Perform comparison analysis."""
        try:
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
        stock_pe = stock_data.get("pe_ratio", 0)
        industry_pe = industry_data.get("pe_ratio_avg", 0)
        
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