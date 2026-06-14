"""Pydantic v2 data models used by the analysis pipeline.

Only the models actually consumed by the running code are kept: the data
collectors build CompanyInfo / MarketData / FundamentalData / NewsData /
EconomicData, the flow validates the advisor's output against
InvestmentRecommendation, and the calculators use the RiskLevel /
RecommendationType enums.
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


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


class FundamentalData(BaseModel):
    """Fundamental data model."""
    # Valuation
    pe_ratio: Optional[Decimal] = Field(None, description="Price-to-Earnings ratio")
    pb_ratio: Optional[Decimal] = Field(None, description="Price-to-Book ratio")
    ps_ratio: Optional[Decimal] = Field(None, description="Price-to-Sales ratio")
    peg_ratio: Optional[Decimal] = Field(None, description="PEG ratio")
    ev_ebitda: Optional[Decimal] = Field(None, description="EV/EBITDA ratio")
    # Profitability
    roe: Optional[Decimal] = Field(None, description="Return on Equity")
    roa: Optional[Decimal] = Field(None, description="Return on Assets")
    gross_margin: Optional[Decimal] = Field(None, description="Gross Margin")
    operating_margin: Optional[Decimal] = Field(None, description="Operating Margin")
    net_margin: Optional[Decimal] = Field(None, description="Net Margin")
    # Financial health
    debt_to_equity: Optional[Decimal] = Field(None, description="Debt-to-Equity ratio")
    current_ratio: Optional[Decimal] = Field(None, description="Current Ratio")
    quick_ratio: Optional[Decimal] = Field(None, description="Quick Ratio")
    # Statements
    market_cap: Optional[Decimal] = Field(None, description="Market Capitalization")
    enterprise_value: Optional[Decimal] = Field(None, description="Enterprise Value")
    total_revenue: Optional[Decimal] = Field(None, description="Total Revenue")
    net_income: Optional[Decimal] = Field(None, description="Net Income")
    total_assets: Optional[Decimal] = Field(None, description="Total Assets")
    total_liabilities: Optional[Decimal] = Field(None, description="Total Liabilities")
    total_equity: Optional[Decimal] = Field(None, description="Total Equity")
    free_cash_flow: Optional[Decimal] = Field(None, description="Free Cash Flow")
    # Dividends
    dividend_yield: Optional[Decimal] = Field(None, description="Dividend Yield")
    dividend_per_share: Optional[Decimal] = Field(None, description="Dividend per Share")
    payout_ratio: Optional[Decimal] = Field(None, description="Payout Ratio")
    timestamp: datetime = Field(..., description="Timestamp of the fundamental data")


class NewsData(BaseModel):
    """News data model."""
    title: str = Field(..., description="News title")
    summary: Optional[str] = Field(None, description="News summary")
    url: str = Field(..., description="News URL")
    source: str = Field(..., description="News source")
    published_at: datetime = Field(..., description="Publication timestamp")
    sentiment_score: Optional[float] = Field(None, description="Sentiment score (-1 to 1)")
    relevance_score: Optional[float] = Field(None, description="Relevance score (0 to 1)")
    tags: List[str] = Field(default_factory=list, description="News tags")


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


class InvestmentRecommendation(BaseModel):
    """Investment recommendation — the advisor stage's validated output."""
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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc),
                                description="Timestamp of the recommendation")

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, v: float) -> float:
        if not 0 <= v <= 1:
            raise ValueError("Confidence must be between 0 and 1")
        return v
