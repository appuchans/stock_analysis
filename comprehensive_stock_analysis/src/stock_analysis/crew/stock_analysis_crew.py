"""Main crew orchestration for comprehensive stock analysis."""

import logging
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

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
from ..models.stock_data import InvestmentRecommendation, RiskMetrics, TechnicalIndicators

_logger = logging.getLogger(__name__)


def _build_embedder_config() -> dict:
    """Build the embedder dict for Crew memory from settings / llm_config.yaml."""
    llm_cfg = config_loader.load_llm_config()
    provider = settings.embedder_provider or llm_cfg.embedder.provider
    model = settings.embedder_model or llm_cfg.embedder.model
    return {"provider": provider, "config": {"model": model}}


def _recommendation_guardrail(result: Any) -> Tuple[bool, Any]:
    """Validate investment recommendation output before accepting it."""
    text = str(result)
    required = ["recommendation", "target_price", "time_horizon", "reasoning"]
    missing = [k for k in required if k.lower() not in text.lower()]
    if missing:
        return False, f"Recommendation output is missing required fields: {missing}"
    return True, result


def _step_callback(step_output: Any) -> None:
    """Log each agent step for observability."""
    _logger.info("[step] %s", str(step_output)[:200])


@CrewBase
class StockAnalysisCrew:
    """Main crew for comprehensive stock analysis."""

    def __init__(self, llm_provider: Optional[str] = None, model: Optional[str] = None):
        """Initialize the stock analysis crew.

        Pass llm_provider / model to override config/llm_config.yaml globally for
        all agents in this crew.  None means "read from config".
        """
        self.llm_provider = llm_provider
        self.model = model
        self._initialize_agents()
        self._crew_instance: Optional[Crew] = None

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
        return Task(
            description="""Collect comprehensive stock data for {symbol} from all available
            free sources: Yahoo Finance (price history, fundamentals, analyst data),
            SEC EDGAR (filings), FRED (economic indicators), RSS news feeds, and web search.
            Return all raw data in a structured format.""",
            expected_output="""Structured data package containing: current price and market data,
            1-year price history, fundamental metrics, recent news articles, economic indicators,
            and SEC filing summaries for {symbol}.""",
            agent=self.data_collector_agent(),
            create_directory=True,
            output_file="reports/{symbol}_data.json",
        )

    @task
    def technical_analysis_task(self) -> Task:
        return Task(
            description="""Perform comprehensive technical analysis for {symbol}:
            1. Calculate RSI, MACD, Bollinger Bands, moving averages (SMA 20/50/200)
            2. Identify chart patterns and trend direction
            3. Determine support/resistance levels
            4. Assess momentum and volume signals
            5. Generate overall technical score and trading signal.""",
            expected_output="""Technical analysis with all indicator values, trend direction,
            support/resistance levels, trading signals, and an overall technical score for {symbol}.""",
            agent=self.technical_analyst_agent(),
            context=[self.data_collection_task()],
            output_pydantic=TechnicalIndicators,
            create_directory=True,
            output_file="reports/{symbol}_technical_analysis.json",
        )

    @task
    def fundamental_analysis_task(self) -> Task:
        return Task(
            description="""Conduct thorough fundamental analysis for {symbol}:
            1. Analyze P/E, P/B, P/S, PEG, EV/EBITDA ratios
            2. Assess profitability margins and return metrics (ROE, ROA, ROIC)
            3. Evaluate financial health (debt/equity, current ratio, interest coverage)
            4. Calculate intrinsic value via DCF and dividend discount models
            5. Compare to industry benchmarks.""",
            expected_output="""Fundamental analysis report with valuation ratios, profitability
            metrics, financial health assessment, intrinsic value estimates, and industry
            comparison for {symbol}.""",
            agent=self.fundamental_analyst_agent(),
            context=[self.data_collection_task()],
            create_directory=True,
            output_file="reports/{symbol}_fundamental_analysis.json",
        )

    @task
    def risk_analysis_task(self) -> Task:
        return Task(
            description="""Perform comprehensive risk analysis for {symbol}:
            1. Compute beta, annualized volatility, Sharpe and Sortino ratios
            2. Calculate VaR (95%) and max drawdown
            3. Assess credit risk (debt levels, coverage ratios)
            4. Identify liquidity and operational risks
            5. Assign overall risk level (Very Low / Low / Medium / High / Very High).""",
            expected_output="""Risk metrics report containing beta, volatility, Sharpe ratio,
            Sortino ratio, VaR, max drawdown, and an overall risk level for {symbol}.""",
            agent=self.risk_analyst_agent(),
            context=[self.data_collection_task()],
            output_pydantic=RiskMetrics,
            create_directory=True,
            output_file="reports/{symbol}_risk_analysis.json",
        )

    @task
    def sentiment_analysis_task(self) -> Task:
        return Task(
            description="""Analyze market sentiment for {symbol}:
            1. Compute aggregate news sentiment score
            2. Summarize analyst consensus and recent upgrades/downgrades
            3. Identify sentiment trend (improving/deteriorating)
            4. Assess social media buzz if data is available.""",
            expected_output="""Sentiment report with aggregate sentiment score (-1 to 1),
            analyst consensus, sentiment trend, and key sentiment drivers for {symbol}.""",
            agent=self.sentiment_analyst_agent(),
            context=[self.data_collection_task()],
            create_directory=True,
            output_file="reports/{symbol}_sentiment_analysis.json",
        )

    @task
    def market_analysis_task(self) -> Task:
        return Task(
            description="""Analyze market conditions affecting {symbol}:
            1. Assess overall market trend (bull/bear/neutral)
            2. Evaluate sector performance and rotation
            3. Identify macro headwinds and tailwinds
            4. Measure correlation with major indices.""",
            expected_output="""Market analysis with current market regime, sector trends,
            macro factors, and correlation metrics for {symbol}.""",
            agent=self.market_analyst_agent(),
            context=[self.data_collection_task()],
            create_directory=True,
            output_file="reports/{symbol}_market_analysis.json",
        )

    @task
    def industry_analysis_task(self) -> Task:
        return Task(
            description="""Analyze industry dynamics for {symbol}:
            1. Assess industry growth trajectory and major trends
            2. Map the competitive landscape (Porter's Five Forces)
            3. Identify regulatory changes and technological disruptions
            4. Evaluate the company's positioning within the industry.""",
            expected_output="""Industry analysis with growth outlook, competitive dynamics,
            key risks/opportunities, and {symbol}'s industry positioning.""",
            agent=self.industry_analyst_agent(),
            context=[self.data_collection_task()],
            create_directory=True,
            output_file="reports/{symbol}_industry_analysis.json",
        )

    @task
    def competitor_analysis_task(self) -> Task:
        return Task(
            description="""Analyze competitive positioning for {symbol}:
            1. Identify top 3-5 direct competitors
            2. Compare key financial ratios head-to-head
            3. Evaluate competitive moat and differentiators
            4. Assess market share trends.""",
            expected_output="""Competitor comparison table, moat assessment, and competitive
            positioning summary for {symbol}.""",
            agent=self.competitor_analyst_agent(),
            context=[self.data_collection_task()],
            create_directory=True,
            output_file="reports/{symbol}_competitor_analysis.json",
        )

    @task
    def economic_analysis_task(self) -> Task:
        return Task(
            description="""Analyze macroeconomic factors affecting {symbol}:
            1. Review GDP growth, inflation, and interest rate environment
            2. Assess monetary and fiscal policy implications
            3. Evaluate global economic risks (trade, geopolitics)
            4. Quantify sensitivity of the business to economic cycles.""",
            expected_output="""Macro analysis with key economic indicators, policy outlook,
            and sensitivity assessment for {symbol}.""",
            agent=self.economic_analyst_agent(),
            context=[self.data_collection_task()],
            create_directory=True,
            output_file="reports/{symbol}_economic_analysis.json",
        )

    @task
    def investment_recommendation_task(self) -> Task:
        return Task(
            description="""Synthesize all specialist analyses and produce a final investment
            recommendation for {symbol}:
            1. Weight and integrate technical, fundamental, risk, sentiment, market,
               industry, competitor, and economic analyses
            2. State recommendation: Strong Buy / Buy / Hold / Sell / Strong Sell
            3. Provide target price and stop-loss level
            4. Specify time horizon (short / medium / long term)
            5. List top 3 risks and top 3 opportunities
            6. Assign confidence level (0-1).""",
            expected_output="""Investment recommendation containing: recommendation type,
            target price, stop-loss, time horizon, confidence, reasoning, key risks,
            and key opportunities for {symbol}.""",
            agent=self.investment_advisor_agent(),
            context=[
                self.technical_analysis_task(),
                self.fundamental_analysis_task(),
                self.risk_analysis_task(),
                self.sentiment_analysis_task(),
                self.market_analysis_task(),
                self.industry_analysis_task(),
                self.competitor_analysis_task(),
                self.economic_analysis_task(),
            ],
            output_pydantic=InvestmentRecommendation,
            guardrail=_recommendation_guardrail,
            create_directory=True,
            output_file="reports/{symbol}_investment_recommendation.json",
        )

    @task
    def report_generation_task(self) -> Task:
        return Task(
            description="""Generate a comprehensive, professional investment report for {symbol}
            that consolidates all specialist analyses:
            1. Write an executive summary (3-5 bullet points)
            2. Present technical, fundamental, risk, sentiment, market, industry,
               competitor, and economic findings
            3. Include the final investment recommendation with supporting rationale
            4. Add a risk disclaimer section.""",
            expected_output="""A complete investment report with executive summary,
            analysis sections, final recommendation, and risk disclaimer for {symbol}.""",
            agent=self.report_generator_agent(),
            context=[
                self.data_collection_task(),
                self.technical_analysis_task(),
                self.fundamental_analysis_task(),
                self.risk_analysis_task(),
                self.sentiment_analysis_task(),
                self.market_analysis_task(),
                self.industry_analysis_task(),
                self.competitor_analysis_task(),
                self.economic_analysis_task(),
                self.investment_recommendation_task(),
            ],
            create_directory=True,
            output_file="reports/{symbol}_comprehensive_report.md",
        )

    # ── crew ──────────────────────────────────────────────────────────────────

    @crew
    def crew(self) -> Crew:
        """Create the comprehensive stock analysis crew."""
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
        """Run the full analysis pipeline for a single stock symbol."""
        try:
            inputs = {"symbol": symbol, **kwargs}
            if self._crew_instance is None:
                self._crew_instance = self.crew()
            result = self._crew_instance.kickoff(inputs=inputs)
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
