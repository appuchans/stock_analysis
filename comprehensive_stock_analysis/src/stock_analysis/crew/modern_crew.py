"""Modern crew implementation with configuration-based agents and tasks."""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from crewai import Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

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

_logger = logging.getLogger(__name__)


def _build_embedder_config() -> dict:
    llm_cfg = config_loader.load_llm_config()
    provider = settings.embedder_provider or llm_cfg.embedder.provider
    model = settings.embedder_model or llm_cfg.embedder.model
    return {"provider": provider, "config": {"model": model}}


def _step_callback(step_output: Any) -> None:
    _logger.info("[step] %s", str(step_output)[:200])


@CrewBase
class ModernStockAnalysisCrew:
    """Modern crew for comprehensive stock analysis using configuration-based approach."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the modern stock analysis crew.  None = read from config."""
        self.llm_provider = llm_provider
        self.model = model
        self._initialize_agents()

    def _initialize_agents(self) -> None:
        """Initialize all specialized agents."""
        self.data_collector = DataCollectorAgent(self.llm_provider, self.model)
        self.technical_analyst = TechnicalAnalystAgent(self.llm_provider, self.model)
        self.fundamental_analyst = FundamentalAnalystAgent(self.llm_provider, self.model)
        self.risk_analyst = RiskAnalystAgent(self.llm_provider, self.model)
        self.sentiment_analyst = SentimentAnalystAgent(self.llm_provider, self.model)
        self.market_analyst = MarketAnalystAgent(self.llm_provider, self.model)
        self.industry_analyst = IndustryAnalystAgent(self.llm_provider, self.model)
        self.competitor_analyst = CompetitorAnalystAgent(self.llm_provider, self.model)
        self.economic_analyst = EconomicAnalystAgent(self.llm_provider, self.model)
        self.investment_advisor = InvestmentAdvisorAgent(self.llm_provider, self.model)
        self.report_generator = ReportGeneratorAgent(self.llm_provider, self.model)

        self.agents_map: Dict[str, Any] = {
            "data_collector": self.data_collector,
            "technical_analyst": self.technical_analyst,
            "fundamental_analyst": self.fundamental_analyst,
            "risk_analyst": self.risk_analyst,
            "sentiment_analyst": self.sentiment_analyst,
            "market_analyst": self.market_analyst,
            "industry_analyst": self.industry_analyst,
            "competitor_analyst": self.competitor_analyst,
            "economic_analyst": self.economic_analyst,
            "investment_advisor": self.investment_advisor,
            "report_generator": self.report_generator,
        }

    # ── agents ───────────────────────────────────────────────────────────────

    @agent
    def data_collector_agent(self) -> Any:
        return self.data_collector.get_agent()

    @agent
    def technical_analyst_agent(self) -> Any:
        return self.technical_analyst.get_agent()

    @agent
    def fundamental_analyst_agent(self) -> Any:
        return self.fundamental_analyst.get_agent()

    @agent
    def risk_analyst_agent(self) -> Any:
        return self.risk_analyst.get_agent()

    @agent
    def sentiment_analyst_agent(self) -> Any:
        return self.sentiment_analyst.get_agent()

    @agent
    def market_analyst_agent(self) -> Any:
        return self.market_analyst.get_agent()

    @agent
    def industry_analyst_agent(self) -> Any:
        return self.industry_analyst.get_agent()

    @agent
    def competitor_analyst_agent(self) -> Any:
        return self.competitor_analyst.get_agent()

    @agent
    def economic_analyst_agent(self) -> Any:
        return self.economic_analyst.get_agent()

    @agent
    def investment_advisor_agent(self) -> Any:
        return self.investment_advisor.get_agent()

    @agent
    def report_generator_agent(self) -> Any:
        return self.report_generator.get_agent()

    # ── tasks ─────────────────────────────────────────────────────────────────

    @task
    def data_collection_task(self) -> Task:
        return task_factory.create_task("data_collection", self.data_collector)

    @task
    def technical_analysis_task(self) -> Task:
        return task_factory.create_task("technical_analysis", self.technical_analyst)

    @task
    def fundamental_analysis_task(self) -> Task:
        return task_factory.create_task("fundamental_analysis", self.fundamental_analyst)

    @task
    def risk_analysis_task(self) -> Task:
        return task_factory.create_task("risk_analysis", self.risk_analyst)

    @task
    def sentiment_analysis_task(self) -> Task:
        return task_factory.create_task("sentiment_analysis", self.sentiment_analyst)

    @task
    def market_analysis_task(self) -> Task:
        return task_factory.create_task("market_analysis", self.market_analyst)

    @task
    def industry_analysis_task(self) -> Task:
        return task_factory.create_task("industry_analysis", self.industry_analyst)

    @task
    def competitor_analysis_task(self) -> Task:
        return task_factory.create_task("competitor_analysis", self.competitor_analyst)

    @task
    def economic_analysis_task(self) -> Task:
        return task_factory.create_task("economic_analysis", self.economic_analyst)

    @task
    def investment_recommendation_task(self) -> Task:
        return task_factory.create_task("investment_recommendation", self.investment_advisor)

    @task
    def report_generation_task(self) -> Task:
        return task_factory.create_task("report_generation", self.report_generator)

    # ── crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        """Create the crew (used by @CrewBase machinery for self.tasks / self.agents)."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=True,
            planning=True,
            step_callback=_step_callback,
            embedder=_build_embedder_config(),
        )

    # ── public API ────────────────────────────────────────────────────────────

    def analyze_stock(self, symbol: str, **kwargs: Any) -> Dict[str, Any]:
        """Analyze a single stock symbol."""
        try:
            tasks = task_factory.create_all_tasks(self.agents_map, symbol)
            c = Crew(
                agents=[a.get_agent() for a in self.agents_map.values()],
                tasks=list(tasks.values()),
                process=Process.sequential,
                verbose=True,
                memory=True,
                planning=True,
                step_callback=_step_callback,
            )
            result = c.kickoff(inputs={"symbol": symbol, **kwargs})
            return {
                "symbol": symbol,
                "analysis_result": result,
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
                step_callback=_step_callback,
            )
            inputs_list = [{"symbol": s, **kwargs} for s in symbols]
            crew_results = await batch_crew.akickoff_for_each(inputs=inputs_list)

            results: Dict[str, Any] = {}
            for symbol, crew_result in zip(symbols, crew_results):
                results[symbol] = {
                    "symbol": symbol,
                    "analysis_result": crew_result,
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
