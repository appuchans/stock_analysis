"""Tools for stock analysis."""

from .data_collection import (
    YahooFinanceTool,
    AlphaVantageTool,
    SECFilingTool,
    FREDTool,
    QuandlTool,
    NewsTool,
    EconomicDataTool,
)
from .free_data_collection import ParallelDataCollectionTool
from .analysis_tools import (
    TechnicalAnalysisTool,
    FundamentalAnalysisTool,
    RiskAnalysisTool,
    SentimentAnalysisTool,
    ValuationTool,
    ComparisonTool,
)
from .calculation_tools import (
    FinancialCalculatorTool,
    TechnicalIndicatorTool,
    RiskCalculatorTool,
    ValuationCalculatorTool,
)
from .backtest_tools import BacktestTool
from .portfolio_tools import PortfolioAnalysisTool
from .report_tools import ReportGeneratorTool

__all__ = [
    # Data Collection Tools
    "YahooFinanceTool",
    "AlphaVantageTool",
    "SECFilingTool",
    "FREDTool",
    "QuandlTool",
    "NewsTool",
    "EconomicDataTool",
    "ParallelDataCollectionTool",
    # Analysis Tools
    "TechnicalAnalysisTool",
    "FundamentalAnalysisTool",
    "RiskAnalysisTool",
    "SentimentAnalysisTool",
    "ValuationTool",
    "ComparisonTool",
    # Calculation Tools
    "FinancialCalculatorTool",
    "TechnicalIndicatorTool",
    "RiskCalculatorTool",
    "ValuationCalculatorTool",
    # New Tools
    "BacktestTool",
    "PortfolioAnalysisTool",
    "ReportGeneratorTool",
]
