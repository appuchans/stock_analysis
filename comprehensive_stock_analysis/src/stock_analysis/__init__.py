"""
Comprehensive Stock Analysis Solution

A production-ready agent-based stock analysis solution using CrewAI framework.
This package provides comprehensive analysis of stocks including fundamentals,
technical analysis, market sentiment, risk assessment, and investment recommendations.
"""

__version__ = "0.1.0"
__author__ = "Stock Analysis Team"
__email__ = "team@stockanalysis.com"

__all__ = [
    "Settings",
    "StockAnalysisFlow",
]


def __getattr__(name: str):
    if name == "Settings":
        from .config.settings import Settings
        return Settings
    if name == "StockAnalysisFlow":
        from .crew.flow_crew import StockAnalysisFlow
        return StockAnalysisFlow
    raise AttributeError(f"module 'stock_analysis' has no attribute {name!r}")
