"""Main crew orchestration for comprehensive stock analysis."""

from typing import List, Dict, Any, Optional
from crewai import Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task

from ..agents import (
    DataCollectorAgent, TechnicalAnalystAgent, FundamentalAnalystAgent,
    RiskAnalystAgent, SentimentAnalystAgent, MarketAnalystAgent,
    IndustryAnalystAgent, CompetitorAnalystAgent, EconomicAnalystAgent,
    InvestmentAdvisorAgent, ReportGeneratorAgent
)
from ..config.settings import settings
from ..tasks.task_factory import task_factory


@CrewBase
class StockAnalysisCrew:
    """Main crew for comprehensive stock analysis using modern configuration-based approach."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the stock analysis crew."""
        self.llm_provider = llm_provider
        self.model = model
        self._initialize_agents()
        self._crew_instance = None
    
    def _initialize_agents(self):
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
        
        # Create agents dictionary for task factory
        self.agents = {
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
            "report_generator": self.report_generator
        }
    
    @agent
    def data_collector_agent(self) -> Any:
        """Data collection agent."""
        return self.data_collector.get_agent()
    
    @agent
    def technical_analyst_agent(self) -> Any:
        """Technical analysis agent."""
        return self.technical_analyst.get_agent()
    
    @agent
    def fundamental_analyst_agent(self) -> Any:
        """Fundamental analysis agent."""
        return self.fundamental_analyst.get_agent()
    
    @agent
    def risk_analyst_agent(self) -> Any:
        """Risk analysis agent."""
        return self.risk_analyst.get_agent()
    
    @agent
    def sentiment_analyst_agent(self) -> Any:
        """Sentiment analysis agent."""
        return self.sentiment_analyst.get_agent()
    
    @agent
    def market_analyst_agent(self) -> Any:
        """Market analysis agent."""
        return self.market_analyst.get_agent()
    
    @agent
    def industry_analyst_agent(self) -> Any:
        """Industry analysis agent."""
        return self.industry_analyst.get_agent()
    
    @agent
    def competitor_analyst_agent(self) -> Any:
        """Competitor analysis agent."""
        return self.competitor_analyst.get_agent()
    
    @agent
    def economic_analyst_agent(self) -> Any:
        """Economic analysis agent."""
        return self.economic_analyst.get_agent()
    
    @agent
    def investment_advisor_agent(self) -> Any:
        """Investment advisory agent."""
        return self.investment_advisor.get_agent()
    
    @agent
    def report_generator_agent(self) -> Any:
        """Report generation agent."""
        return self.report_generator.get_agent()
    
    @task
    def data_collection_task(self) -> Task:
        """Data collection task."""
        return task_factory.create_task("data_collection", self.data_collector)
    
    @task
    def technical_analysis_task(self) -> Task:
        """Technical analysis task."""
        return Task(
            description="""Perform comprehensive technical analysis for {symbol} including:
            1. Calculate technical indicators (RSI, MACD, Moving Averages, etc.)
            2. Identify chart patterns and trends
            3. Analyze support and resistance levels
            4. Generate trading signals and recommendations
            5. Assess momentum and volatility
            6. Evaluate volume patterns
            
            Provide actionable insights based on technical analysis principles.""",
            expected_output="""A detailed technical analysis report with:
            - Technical indicators and their interpretations
            - Chart patterns and trend analysis
            - Support/resistance levels
            - Trading signals and recommendations
            - Risk assessment from technical perspective""",
            agent=self.technical_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_technical_analysis.json"
        )
    
    @task
    def fundamental_analysis_task(self) -> Task:
        """Fundamental analysis task."""
        return Task(
            description="""Conduct thorough fundamental analysis for {symbol} including:
            1. Analyze financial statements and key metrics
            2. Evaluate valuation ratios (P/E, P/B, P/S, PEG, etc.)
            3. Assess profitability and growth metrics
            4. Examine financial health and debt levels
            5. Calculate intrinsic value using DCF and other methods
            6. Compare against industry benchmarks
            
            Focus on long-term value and investment potential.""",
            expected_output="""A comprehensive fundamental analysis report with:
            - Financial statement analysis
            - Valuation metrics and ratios
            - Profitability and growth assessment
            - Financial health evaluation
            - Intrinsic value calculations
            - Investment quality score""",
            agent=self.fundamental_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_fundamental_analysis.json"
        )
    
    @task
    def risk_analysis_task(self) -> Task:
        """Risk analysis task."""
        return Task(
            description="""Perform comprehensive risk analysis for {symbol} including:
            1. Market risk assessment (volatility, beta, VaR)
            2. Credit risk evaluation (debt levels, coverage ratios)
            3. Liquidity risk analysis
            4. Operational risk factors
            5. Regulatory and compliance risks
            6. ESG risk considerations
            
            Quantify risks and provide risk management recommendations.""",
            expected_output="""A detailed risk analysis report with:
            - Market risk metrics and assessment
            - Credit risk evaluation
            - Liquidity risk analysis
            - Operational risk factors
            - Overall risk score and level
            - Risk management recommendations""",
            agent=self.risk_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_risk_analysis.json"
        )
    
    @task
    def sentiment_analysis_task(self) -> Task:
        """Sentiment analysis task."""
        return Task(
            description="""Analyze market sentiment for {symbol} including:
            1. News sentiment analysis
            2. Social media sentiment
            3. Analyst opinion analysis
            4. Market sentiment indicators
            5. Sentiment trends and changes
            6. Impact on stock price movements
            
            Provide insights into market psychology and sentiment drivers.""",
            expected_output="""A comprehensive sentiment analysis report with:
            - News sentiment scores and trends
            - Social media sentiment analysis
            - Analyst opinion summary
            - Market sentiment indicators
            - Sentiment impact assessment
            - Sentiment-based recommendations""",
            agent=self.sentiment_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_sentiment_analysis.json"
        )
    
    @task
    def market_analysis_task(self) -> Task:
        """Market analysis task."""
        return Task(
            description="""Analyze market conditions and trends affecting {symbol} including:
            1. Overall market conditions and trends
            2. Sector performance and rotation
            3. Market volatility and sentiment
            4. Economic indicators and their impact
            5. Market cycles and positioning
            6. Correlation with market indices
            
            Provide context for how market conditions affect the stock.""",
            expected_output="""A detailed market analysis report with:
            - Market condition assessment
            - Sector analysis and trends
            - Volatility and sentiment analysis
            - Economic indicator impact
            - Market cycle positioning
            - Correlation analysis""",
            agent=self.market_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_market_analysis.json"
        )
    
    @task
    def industry_analysis_task(self) -> Task:
        """Industry analysis task."""
        return Task(
            description="""Analyze industry trends and dynamics for {symbol} including:
            1. Industry growth prospects and trends
            2. Competitive landscape and dynamics
            3. Regulatory environment and changes
            4. Technological disruptions and innovations
            5. Industry challenges and opportunities
            6. Market share and positioning analysis
            
            Focus on industry-specific factors affecting the company.""",
            expected_output="""A comprehensive industry analysis report with:
            - Industry growth and trend analysis
            - Competitive landscape assessment
            - Regulatory environment review
            - Technological disruption analysis
            - Industry challenges and opportunities
            - Market positioning evaluation""",
            agent=self.industry_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_industry_analysis.json"
        )
    
    @task
    def competitor_analysis_task(self) -> Task:
        """Competitor analysis task."""
        return Task(
            description="""Analyze competitive positioning for {symbol} including:
            1. Identify key competitors and their performance
            2. Compare financial metrics and ratios
            3. Analyze competitive advantages and disadvantages
            4. Evaluate market share and positioning
            5. Assess competitive threats and opportunities
            6. Review strategic initiatives and responses
            
            Provide insights into competitive positioning and strategy.""",
            expected_output="""A detailed competitor analysis report with:
            - Key competitor identification
            - Financial performance comparison
            - Competitive advantage analysis
            - Market share assessment
            - Competitive threat evaluation
            - Strategic positioning insights""",
            agent=self.competitor_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_competitor_analysis.json"
        )
    
    @task
    def economic_analysis_task(self) -> Task:
        """Economic analysis task."""
        return Task(
            description="""Analyze macroeconomic factors affecting {symbol} including:
            1. Economic indicators and trends
            2. Monetary policy and interest rates
            3. Fiscal policy and government spending
            4. Inflation and economic growth
            5. Global economic conditions
            6. Currency and trade impacts
            
            Assess how macroeconomic factors influence the stock.""",
            expected_output="""A comprehensive economic analysis report with:
            - Economic indicator analysis
            - Monetary policy assessment
            - Fiscal policy impact
            - Inflation and growth analysis
            - Global economic conditions
            - Currency and trade impacts""",
            agent=self.economic_analyst_agent(),
            context=[self.data_collection_task()],
            output_file="reports/{symbol}_economic_analysis.json"
        )
    
    @task
    def investment_recommendation_task(self) -> Task:
        """Investment recommendation task."""
        return Task(
            description="""Synthesize all analysis to provide investment recommendations for {symbol} including:
            1. Review and integrate all previous analyses
            2. Weight different factors based on importance
            3. Generate investment recommendation (Buy/Hold/Sell)
            4. Provide target price and time horizon
            5. Identify key risks and opportunities
            6. Suggest portfolio positioning and allocation
            
            Create actionable investment advice based on comprehensive analysis.""",
            expected_output="""A comprehensive investment recommendation report with:
            - Investment recommendation (Buy/Hold/Sell)
            - Target price and time horizon
            - Key investment thesis
            - Risk and opportunity assessment
            - Portfolio positioning advice
            - Implementation strategy""",
            agent=self.investment_advisor_agent(),
            context=[
                self.technical_analysis_task(),
                self.fundamental_analysis_task(),
                self.risk_analysis_task(),
                self.sentiment_analysis_task(),
                self.market_analysis_task(),
                self.industry_analysis_task(),
                self.competitor_analysis_task(),
                self.economic_analysis_task()
            ],
            output_file="reports/{symbol}_investment_recommendation.json"
        )
    
    @task
    def report_generation_task(self) -> Task:
        """Report generation task."""
        return Task(
            description="""Generate a comprehensive investment report for {symbol} including:
            1. Executive summary with key findings
            2. Detailed analysis sections from all specialists
            3. Charts, graphs, and visualizations
            4. Investment recommendation and rationale
            5. Risk assessment and mitigation strategies
            6. Appendices with supporting data
            
            Create a professional, well-structured report for investors.""",
            expected_output="""A comprehensive investment report with:
            - Executive summary
            - Detailed analysis sections
            - Visual charts and graphs
            - Investment recommendation
            - Risk assessment
            - Supporting data and appendices""",
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
                self.investment_recommendation_task()
            ],
            output_file="reports/{symbol}_comprehensive_report.pdf"
        )
    
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
            embedder={
                "provider": "openai",
                "config": {
                    "model": "text-embedding-3-small"
                }
            }
        )
    
    def analyze_stock(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """Analyze a stock using the comprehensive crew."""
        try:
            # Prepare inputs
            inputs = {
                "symbol": symbol,
                **kwargs
            }
            
            # Run the crew (cache to avoid rebuilding on every call)
            if self._crew_instance is None:
                self._crew_instance = self.crew()
            result = self._crew_instance.kickoff(inputs=inputs)
            
            return {
                "symbol": symbol,
                "analysis_result": result,
                "status": "completed",
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "symbol": symbol,
                "error": str(e),
                "status": "failed",
                "timestamp": self._get_timestamp()
            }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
