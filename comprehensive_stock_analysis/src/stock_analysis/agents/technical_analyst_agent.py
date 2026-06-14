"""Technical Analyst Agent for technical analysis of stocks."""

from typing import List, Any, Optional

from .base_agent import BaseAgent
from ..tools.analysis_tools import TechnicalAnalysisTool
from ..tools.backtest_tools import BacktestTool
from ..tools.calculation_tools import TechnicalIndicatorTool, FinancialCalculatorTool
from ..tools.free_data_collection import YahooFinanceTool


class TechnicalAnalystAgent(BaseAgent):
    """Agent responsible for technical analysis of stocks."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the Technical Analyst Agent."""
        super().__init__("technical_analyst", llm_provider, model)

    def _get_tools(self) -> List[Any]:
        """Get technical analysis tools.

        YahooFinanceTool is included so the agent can fetch fresh OHLCV data
        and pre-computed technical indicators (RSI, MACD, Bollinger Bands, ATR)
        directly rather than relying on whatever the data collector happened to
        pass through.
        """
        return [
            YahooFinanceTool(),
            TechnicalAnalysisTool(),
            TechnicalIndicatorTool(),
            FinancialCalculatorTool(),
            BacktestTool(),
        ]
