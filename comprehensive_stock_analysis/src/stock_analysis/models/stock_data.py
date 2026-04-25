"""Data models for stock analysis."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator
from enum import Enum


class TimeFrame(str, Enum):
    """Time frame enumeration."""
    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    MINUTE_30 = "30m"
    HOUR_1 = "1h"
    HOUR_4 = "4h"
    DAY_1 = "1d"
    WEEK_1 = "1wk"
    MONTH_1 = "1mo"
    YEAR_1 = "1y"
    YEAR_2 = "2y"
    YEAR_5 = "5y"
    YEAR_10 = "10y"
    MAX = "max"


class RecommendationType(str, Enum):
    """Investment recommendation types."""
    STRONG_BUY = "Strong Buy"
    BUY = "Buy"
    HOLD = "Hold"
    SELL = "Sell"
    STRONG_SELL = "Strong Sell"


class RiskLevel(str, Enum):
    """Risk level enumeration."""
    VERY_LOW = "Very Low"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    VERY_HIGH = "Very High"


class PriceData(BaseModel):
    """Price data model."""
    open: Decimal = Field(..., description="Opening price")
    high: Decimal = Field(..., description="Highest price")
    low: Decimal = Field(..., description="Lowest price")
    close: Decimal = Field(..., description="Closing price")
    adjusted_close: Optional[Decimal] = Field(None, description="Adjusted closing price")
    timestamp: datetime = Field(..., description="Timestamp of the price data")

    @field_validator("open", "high", "low", "close")
    @classmethod
    def validate_positive_prices(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("Prices must be positive")
        return v

    @model_validator(mode="after")
    def validate_high_low(self) -> "PriceData":
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("High price must be >= low price")
        return self


class VolumeData(BaseModel):
    """Volume data model."""
    volume: int = Field(..., description="Trading volume")
    timestamp: datetime = Field(..., description="Timestamp of the volume data")

    @field_validator("volume")
    @classmethod
    def validate_positive_volume(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Volume must be non-negative")
        return v


class TechnicalIndicators(BaseModel):
    """Technical indicators model."""
    # Moving Averages
    sma_20: Optional[Decimal] = Field(None, description="20-day Simple Moving Average")
    sma_50: Optional[Decimal] = Field(None, description="50-day Simple Moving Average")
    sma_200: Optional[Decimal] = Field(None, description="200-day Simple Moving Average")
    ema_12: Optional[Decimal] = Field(None, description="12-day Exponential Moving Average")
    ema_26: Optional[Decimal] = Field(None, description="26-day Exponential Moving Average")

    # Momentum Indicators
    rsi: Optional[Decimal] = Field(None, description="Relative Strength Index")
    macd: Optional[Decimal] = Field(None, description="MACD")
    macd_signal: Optional[Decimal] = Field(None, description="MACD Signal")
    macd_histogram: Optional[Decimal] = Field(None, description="MACD Histogram")
    stochastic_k: Optional[Decimal] = Field(None, description="Stochastic %K")
    stochastic_d: Optional[Decimal] = Field(None, description="Stochastic %D")
    williams_r: Optional[Decimal] = Field(None, description="Williams %R")
    momentum: Optional[Decimal] = Field(None, description="Momentum")

    # Volatility Indicators
    bollinger_upper: Optional[Decimal] = Field(None, description="Bollinger Bands Upper")
    bollinger_middle: Optional[Decimal] = Field(None, description="Bollinger Bands Middle")
    bollinger_lower: Optional[Decimal] = Field(None, description="Bollinger Bands Lower")
    atr: Optional[Decimal] = Field(None, description="Average True Range")

    # Trend Indicators
    adx: Optional[Decimal] = Field(None, description="Average Directional Index")
    cci: Optional[Decimal] = Field(None, description="Commodity Channel Index")
    aroon_up: Optional[Decimal] = Field(None, description="Aroon Up")
    aroon_down: Optional[Decimal] = Field(None, description="Aroon Down")

    # Volume Indicators
    obv: Optional[Decimal] = Field(None, description="On-Balance Volume")
    ad_line: Optional[Decimal] = Field(None, description="A/D Line")
    mfi: Optional[Decimal] = Field(None, description="Money Flow Index")

    timestamp: datetime = Field(..., description="Timestamp of the indicators")


class FundamentalData(BaseModel):
    """Fundamental data model."""
    # Valuation Metrics
    pe_ratio: Optional[Decimal] = Field(None, description="Price-to-Earnings ratio")
    pb_ratio: Optional[Decimal] = Field(None, description="Price-to-Book ratio")
    ps_ratio: Optional[Decimal] = Field(None, description="Price-to-Sales ratio")
    peg_ratio: Optional[Decimal] = Field(None, description="PEG ratio")
    ev_ebitda: Optional[Decimal] = Field(None, description="EV/EBITDA ratio")

    # Profitability Metrics
    roe: Optional[Decimal] = Field(None, description="Return on Equity")
    roa: Optional[Decimal] = Field(None, description="Return on Assets")
    roic: Optional[Decimal] = Field(None, description="Return on Invested Capital")
    gross_margin: Optional[Decimal] = Field(None, description="Gross Margin")
    operating_margin: Optional[Decimal] = Field(None, description="Operating Margin")
    net_margin: Optional[Decimal] = Field(None, description="Net Margin")

    # Financial Health Metrics
    debt_to_equity: Optional[Decimal] = Field(None, description="Debt-to-Equity ratio")
    current_ratio: Optional[Decimal] = Field(None, description="Current Ratio")
    quick_ratio: Optional[Decimal] = Field(None, description="Quick Ratio")
    interest_coverage: Optional[Decimal] = Field(None, description="Interest Coverage ratio")

    # Growth Metrics
    revenue_growth: Optional[Decimal] = Field(None, description="Revenue Growth")
    earnings_growth: Optional[Decimal] = Field(None, description="Earnings Growth")
    book_value_growth: Optional[Decimal] = Field(None, description="Book Value Growth")

    # Financial Statements Data
    market_cap: Optional[Decimal] = Field(None, description="Market Capitalization")
    enterprise_value: Optional[Decimal] = Field(None, description="Enterprise Value")
    total_revenue: Optional[Decimal] = Field(None, description="Total Revenue")
    net_income: Optional[Decimal] = Field(None, description="Net Income")
    total_assets: Optional[Decimal] = Field(None, description="Total Assets")
    total_liabilities: Optional[Decimal] = Field(None, description="Total Liabilities")
    total_equity: Optional[Decimal] = Field(None, description="Total Equity")
    free_cash_flow: Optional[Decimal] = Field(None, description="Free Cash Flow")

    # Dividend Information
    dividend_yield: Optional[Decimal] = Field(None, description="Dividend Yield")
    dividend_per_share: Optional[Decimal] = Field(None, description="Dividend per Share")
    payout_ratio: Optional[Decimal] = Field(None, description="Payout Ratio")

    timestamp: datetime = Field(..., description="Timestamp of the fundamental data")


class CompanyInfo(BaseModel):
    """Company information model."""
    symbol: str = Field(..., description="Stock symbol")
    name: str = Field(..., description="Company name")
    sector: Optional[str] = Field(None, description="Sector")
    industry: Optional[str] = Field(None, description="Industry")
    country: Optional[str] = Field(None, description="Country")
    exchange: Optional[str] = Field(None, description="Exchange")
    currency: Optional[str] = Field(None, description="Currency")
    website: Optional[str] = Field(None, description="Company website")
    description: Optional[str] = Field(None, description="Company description")
    employees: Optional[int] = Field(None, description="Number of employees")
    founded_year: Optional[int] = Field(None, description="Year founded")
    ceo: Optional[str] = Field(None, description="CEO name")
    headquarters: Optional[str] = Field(None, description="Headquarters location")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, v: str) -> str:
        if not v or not (1 <= len(v) <= 10):
            raise ValueError("Symbol must be 1-10 characters")
        return v.upper()


class MarketData(BaseModel):
    """Market data model."""
    symbol: str = Field(..., description="Stock symbol")
    current_price: Decimal = Field(..., description="Current price")
    previous_close: Optional[Decimal] = Field(None, description="Previous close")
    day_change: Optional[Decimal] = Field(None, description="Day change")
    day_change_percent: Optional[Decimal] = Field(None, description="Day change percentage")
    volume: int = Field(..., description="Current volume")
    avg_volume: Optional[int] = Field(None, description="Average volume")
    market_cap: Optional[Decimal] = Field(None, description="Market capitalization")
    high_52w: Optional[Decimal] = Field(None, description="52-week high")
    low_52w: Optional[Decimal] = Field(None, description="52-week low")
    beta: Optional[Decimal] = Field(None, description="Beta")
    timestamp: datetime = Field(..., description="Timestamp of the market data")


class NewsData(BaseModel):
    """News data model."""
    title: str = Field(..., description="News title")
    summary: Optional[str] = Field(None, description="News summary")
    content: Optional[str] = Field(None, description="News content")
    url: str = Field(..., description="News URL")
    source: str = Field(..., description="News source")
    published_at: datetime = Field(..., description="Publication timestamp")
    sentiment_score: Optional[float] = Field(None, description="Sentiment score (-1 to 1)")
    relevance_score: Optional[float] = Field(None, description="Relevance score (0 to 1)")
    tags: List[str] = Field(default_factory=list, description="News tags")

    @field_validator("sentiment_score")
    @classmethod
    def validate_sentiment_score(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not -1 <= v <= 1:
            raise ValueError("Sentiment score must be between -1 and 1")
        return v

    @field_validator("relevance_score")
    @classmethod
    def validate_relevance_score(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not 0 <= v <= 1:
            raise ValueError("Relevance score must be between 0 and 1")
        return v


class EarningsData(BaseModel):
    """Earnings data model."""
    symbol: str = Field(..., description="Stock symbol")
    quarter: str = Field(..., description="Quarter (e.g., Q1 2024)")
    fiscal_year: int = Field(..., description="Fiscal year")
    earnings_per_share: Optional[Decimal] = Field(None, description="Earnings per share")
    revenue: Optional[Decimal] = Field(None, description="Revenue")
    net_income: Optional[Decimal] = Field(None, description="Net income")
    eps_estimate: Optional[Decimal] = Field(None, description="EPS estimate")
    revenue_estimate: Optional[Decimal] = Field(None, description="Revenue estimate")
    eps_surprise: Optional[Decimal] = Field(None, description="EPS surprise")
    revenue_surprise: Optional[Decimal] = Field(None, description="Revenue surprise")
    report_date: datetime = Field(..., description="Report date")
    announcement_date: Optional[datetime] = Field(None, description="Announcement date")


class AnalystData(BaseModel):
    """Analyst data model."""
    symbol: str = Field(..., description="Stock symbol")
    target_price: Optional[Decimal] = Field(None, description="Target price")
    recommendation: Optional[RecommendationType] = Field(None, description="Recommendation")
    strong_buy: Optional[int] = Field(None, description="Strong buy count")
    buy: Optional[int] = Field(None, description="Buy count")
    hold: Optional[int] = Field(None, description="Hold count")
    sell: Optional[int] = Field(None, description="Sell count")
    strong_sell: Optional[int] = Field(None, description="Strong sell count")
    total_analysts: Optional[int] = Field(None, description="Total analysts")
    last_updated: datetime = Field(..., description="Last updated timestamp")


class RiskMetrics(BaseModel):
    """Risk metrics model."""
    symbol: str = Field(..., description="Stock symbol")
    beta: Optional[Decimal] = Field(None, description="Beta")
    volatility: Optional[Decimal] = Field(None, description="Volatility (annualized)")
    sharpe_ratio: Optional[Decimal] = Field(None, description="Sharpe ratio")
    sortino_ratio: Optional[Decimal] = Field(None, description="Sortino ratio")
    max_drawdown: Optional[Decimal] = Field(None, description="Maximum drawdown")
    var_95: Optional[Decimal] = Field(None, description="Value at Risk (95%)")
    cvar_95: Optional[Decimal] = Field(None, description="Conditional Value at Risk (95%)")
    risk_level: Optional[RiskLevel] = Field(None, description="Overall risk level")
    timestamp: datetime = Field(..., description="Timestamp of the risk metrics")


class IndustryData(BaseModel):
    """Industry data model."""
    industry: str = Field(..., description="Industry name")
    sector: str = Field(..., description="Sector name")
    market_cap: Optional[Decimal] = Field(None, description="Total market cap")
    pe_ratio_avg: Optional[Decimal] = Field(None, description="Average PE ratio")
    growth_rate: Optional[Decimal] = Field(None, description="Growth rate")
    trends: List[str] = Field(default_factory=list, description="Industry trends")
    outlook: Optional[str] = Field(None, description="Industry outlook")
    key_players: List[str] = Field(default_factory=list, description="Key players")
    timestamp: datetime = Field(..., description="Timestamp of the industry data")


class CompetitorData(BaseModel):
    """Competitor data model."""
    symbol: str = Field(..., description="Stock symbol")
    competitor_symbols: List[str] = Field(..., description="Competitor symbols")
    market_share: Optional[Decimal] = Field(None, description="Market share")
    competitive_position: Optional[str] = Field(None, description="Competitive position")
    advantages: List[str] = Field(default_factory=list, description="Competitive advantages")
    disadvantages: List[str] = Field(default_factory=list, description="Competitive disadvantages")
    timestamp: datetime = Field(..., description="Timestamp of the competitor data")


class EconomicData(BaseModel):
    """Economic data model."""
    gdp_growth: Optional[Decimal] = Field(None, description="GDP growth rate")
    inflation_rate: Optional[Decimal] = Field(None, description="Inflation rate")
    interest_rate: Optional[Decimal] = Field(None, description="Interest rate")
    unemployment_rate: Optional[Decimal] = Field(None, description="Unemployment rate")
    consumer_confidence: Optional[Decimal] = Field(None, description="Consumer confidence")
    business_confidence: Optional[Decimal] = Field(None, description="Business confidence")
    currency_strength: Optional[Decimal] = Field(None, description="Currency strength")
    country: str = Field(..., description="Country")
    timestamp: datetime = Field(..., description="Timestamp of the economic data")


class AnalysisResult(BaseModel):
    """Analysis result model."""
    symbol: str = Field(..., description="Stock symbol")
    analysis_type: str = Field(..., description="Type of analysis")
    score: float = Field(..., description="Analysis score (0-100)")
    confidence: float = Field(..., description="Confidence level (0-1)")
    summary: str = Field(..., description="Analysis summary")
    details: Dict[str, Any] = Field(default_factory=dict, description="Analysis details")
    timestamp: datetime = Field(..., description="Timestamp of the analysis")

    @field_validator("score")
    @classmethod
    def validate_score(cls, v: float) -> float:
        if not 0 <= v <= 100:
            raise ValueError("Score must be between 0 and 100")
        return v

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v


class InvestmentRecommendation(BaseModel):
    """Investment recommendation model."""
    symbol: str = Field(..., description="Stock symbol")
    recommendation: RecommendationType = Field(..., description="Investment recommendation")
    target_price: Optional[Decimal] = Field(None, description="Target price")
    stop_loss: Optional[Decimal] = Field(None, description="Stop loss price")
    time_horizon: str = Field(..., description="Investment time horizon")
    risk_level: RiskLevel = Field(..., description="Risk level")
    confidence: float = Field(..., description="Confidence level (0-1)")
    reasoning: str = Field(..., description="Reasoning for recommendation")
    key_factors: List[str] = Field(..., description="Key factors influencing recommendation")
    risks: List[str] = Field(default_factory=list, description="Key risks")
    opportunities: List[str] = Field(default_factory=list, description="Key opportunities")
    timestamp: datetime = Field(..., description="Timestamp of the recommendation")

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v


class StockData(BaseModel):
    """Comprehensive stock data model."""
    symbol: str = Field(..., description="Stock symbol")
    company_info: CompanyInfo = Field(..., description="Company information")
    market_data: MarketData = Field(..., description="Market data")
    price_history: List[PriceData] = Field(default_factory=list, description="Price history")
    volume_history: List[VolumeData] = Field(default_factory=list, description="Volume history")
    technical_indicators: Optional[TechnicalIndicators] = Field(None, description="Technical indicators")
    fundamental_data: Optional[FundamentalData] = Field(None, description="Fundamental data")
    news_data: List[NewsData] = Field(default_factory=list, description="News data")
    earnings_data: List[EarningsData] = Field(default_factory=list, description="Earnings data")
    analyst_data: Optional[AnalystData] = Field(None, description="Analyst data")
    risk_metrics: Optional[RiskMetrics] = Field(None, description="Risk metrics")
    industry_data: Optional[IndustryData] = Field(None, description="Industry data")
    competitor_data: Optional[CompetitorData] = Field(None, description="Competitor data")
    economic_data: Optional[EconomicData] = Field(None, description="Economic data")
    analysis_results: List[AnalysisResult] = Field(default_factory=list, description="Analysis results")
    recommendation: Optional[InvestmentRecommendation] = Field(None, description="Investment recommendation")
    last_updated: datetime = Field(..., description="Last updated timestamp")
