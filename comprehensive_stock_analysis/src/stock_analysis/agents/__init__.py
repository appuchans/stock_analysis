"""Specialized agents for stock analysis."""

from .data_collector_agent import DataCollectorAgent
from .technical_analyst_agent import TechnicalAnalystAgent
from .fundamental_analyst_agent import FundamentalAnalystAgent
from .risk_analyst_agent import RiskAnalystAgent
from .sentiment_analyst_agent import SentimentAnalystAgent
from .market_analyst_agent import MarketAnalystAgent
from .industry_analyst_agent import IndustryAnalystAgent
from .competitor_analyst_agent import CompetitorAnalystAgent
from .economic_analyst_agent import EconomicAnalystAgent
from .investment_advisor_agent import InvestmentAdvisorAgent
from .report_generator_agent import ReportGeneratorAgent

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
