"""
Comprehensive Stock Analysis Solution

A production-ready agent-based stock analysis solution using CrewAI framework.
This package provides comprehensive analysis of stocks including fundamentals,
technical analysis, market sentiment, risk assessment, and investment recommendations.
"""

__version__ = "0.1.0"
__author__ = "Stock Analysis Team"
__email__ = "team@stockanalysis.com"

from .config.settings import Settings
from .crew.stock_analysis_crew import StockAnalysisCrew
from .crew.modern_crew import ModernStockAnalysisCrew
from .crew.flow_crew import StockAnalysisFlowCrew, QuickAnalysisFlowCrew, DeepDiveAnalysisFlowCrew
from .tools.backtest_tools import BacktestTool
from .tools.portfolio_tools import PortfolioAnalysisTool
from .tools.report_tools import ReportGeneratorTool

__all__ = [
    "Settings",
    "StockAnalysisCrew",
    "ModernStockAnalysisCrew",
    "StockAnalysisFlowCrew",
    "QuickAnalysisFlowCrew",
    "DeepDiveAnalysisFlowCrew",
    "BacktestTool",
    "PortfolioAnalysisTool",
    "ReportGeneratorTool",
]
