"""Crew implementation using configuration-based agents and tasks."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from crewai import Crew, LLM, Process

from ..agents import (
    CompetitorAnalystAgent,
    DataCollectorAgent,
    EconomicAnalystAgent,
    FundamentalAnalystAgent,
    IndustryAnalystAgent,
    InvestmentAdvisorAgent,
    MarketAnalystAgent,
    ReportGeneratorAgent,
    RiskAnalystAgent,
    SentimentAnalystAgent,
    TechnicalAnalystAgent,
)
from ..config.loader import config_loader
from ..config.settings import settings
from ..tasks.task_factory import task_factory
from .event_listener import event_listener  # noqa: F401 — registers event handlers on import

_logger = logging.getLogger(__name__)


def _build_planning_llm() -> LLM:
    return LLM(model=config_loader.build_planning_llm_model_string())


class StockAnalysisCrew:
    """Comprehensive stock analysis crew using YAML-configured agents and tasks."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        self.llm_provider = llm_provider
        self.model = model
        self._crew_instance: Optional[Crew] = None
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        self.agents_map: Dict[str, Any] = {
            "data_collector":     DataCollectorAgent(self.llm_provider, self.model),
            "technical_analyst":  TechnicalAnalystAgent(self.llm_provider, self.model),
            "fundamental_analyst": FundamentalAnalystAgent(self.llm_provider, self.model),
            "risk_analyst":       RiskAnalystAgent(self.llm_provider, self.model),
            "sentiment_analyst":  SentimentAnalystAgent(self.llm_provider, self.model),
            "market_analyst":     MarketAnalystAgent(self.llm_provider, self.model),
            "industry_analyst":   IndustryAnalystAgent(self.llm_provider, self.model),
            "competitor_analyst": CompetitorAnalystAgent(self.llm_provider, self.model),
            "economic_analyst":   EconomicAnalystAgent(self.llm_provider, self.model),
            "investment_advisor": InvestmentAdvisorAgent(self.llm_provider, self.model),
            "report_generator":   ReportGeneratorAgent(self.llm_provider, self.model),
        }

    # ── internal crew builder ─────────────────────────────────────────────────

    def _get_crew(self) -> Crew:
        """Return cached Crew instance (built once per StockAnalysisCrew lifetime).

        Passes "{symbol}" so CrewAI interpolates it from the kickoff inputs dict.
        """
        if self._crew_instance is None:
            tasks = task_factory.create_all_tasks(self.agents_map, "{symbol}")
            self._crew_instance = Crew(
                agents=[a.get_agent() for a in self.agents_map.values()],
                tasks=list(tasks.values()),
                process=Process.sequential,
                verbose=True,
                memory=True,
                planning=True,
                planning_llm=_build_planning_llm(),
                embedder=config_loader.build_embedder_config(),
                output_log_file=settings.crew_log_file,
            )
        return self._crew_instance

    # ── public API ────────────────────────────────────────────────────────────

    def analyze_stock(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:
        """Analyze a single stock symbol."""
        try:
            result = self._get_crew().kickoff(inputs={"symbol": symbol, **kwargs})
            return {
                "symbol": symbol,
                "analysis_result": result,
                "token_usage": result.token_usage.model_dump() if result.token_usage else None,
                "status": "completed",
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            _logger.error("Analysis failed for %s: %s", symbol, e)
            return {
                "symbol": symbol,
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
            }

    def analyze_multiple_stocks(self, symbols: List[str], **kwargs: Any) -> Dict[str, Any]:
        """Analyze multiple stocks in parallel using akickoff_for_each."""
        return asyncio.run(self.analyze_multiple_stocks_async(symbols, **kwargs))

    async def analyze_multiple_stocks_async(
        self, symbols: List[str], **kwargs: Any
    ) -> Dict[str, Any]:
        """Async batch analysis using CrewAI's akickoff_for_each for true parallelism."""
        try:
            tasks_map = task_factory.create_all_tasks(self.agents_map, "{symbol}")
            batch_crew = Crew(
                agents=[a.get_agent() for a in self.agents_map.values()],
                tasks=list(tasks_map.values()),
                process=Process.sequential,
                verbose=True,
                memory=True,
                planning=True,
                planning_llm=_build_planning_llm(),
                embedder=config_loader.build_embedder_config(),
                output_log_file=settings.crew_log_file,
            )
            inputs_list = [{"symbol": s, **kwargs} for s in symbols]
            crew_results = await batch_crew.akickoff_for_each(inputs=inputs_list)

            results: Dict[str, Any] = {}
            for symbol, crew_result in zip(symbols, crew_results):
                results[symbol] = {
                    "symbol": symbol,
                    "analysis_result": crew_result,
                    "token_usage": crew_result.token_usage.model_dump() if crew_result.token_usage else None,
                    "status": "completed",
                    "timestamp": datetime.now().isoformat(),
                }

            completed = sum(1 for r in results.values() if r["status"] == "completed")
            failed = len(symbols) - completed
            return {
                "results": results,
                "summary": {"total": len(symbols), "completed": completed, "failed": failed},
                "timestamp": datetime.now().isoformat(),
            }
        except Exception as e:
            _logger.error("Batch analysis failed: %s", e)
            return {
                "error": str(e),
                "status": "failed",
                "timestamp": datetime.now().isoformat(),
            }


# Backward-compatible alias
ModernStockAnalysisCrew = StockAnalysisCrew
