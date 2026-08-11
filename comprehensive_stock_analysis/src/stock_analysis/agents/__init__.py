"""Specialized agents for stock analysis."""

from .competitor_analyst_agent import CompetitorAnalystAgent
from .data_collector_agent import DataCollectorAgent
from .economic_analyst_agent import EconomicAnalystAgent
from .fundamental_analyst_agent import FundamentalAnalystAgent
from .industry_analyst_agent import IndustryAnalystAgent
from .investment_advisor_agent import InvestmentAdvisorAgent
from .market_analyst_agent import MarketAnalystAgent
from .report_generator_agent import ReportGeneratorAgent
from .risk_analyst_agent import RiskAnalystAgent
from .sentiment_analyst_agent import SentimentAnalystAgent
from .technical_analyst_agent import TechnicalAnalystAgent

__all__ = [
    "DataCollectorAgent",
    "TechnicalAnalystAgent",
    "FundamentalAnalystAgent",
    "RiskAnalystAgent",
    "SentimentAnalystAgent",
    "MarketAnalystAgent",
    "IndustryAnalystAgent",
    "CompetitorAnalystAgent",
    "EconomicAnalystAgent",
    "InvestmentAdvisorAgent",
    "ReportGeneratorAgent",
]
