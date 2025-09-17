"""Modern crew implementation with configuration-based agents and tasks."""

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
class ModernStockAnalysisCrew:
    """Modern crew for comprehensive stock analysis using configuration-based approach."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the modern stock analysis crew."""
        self.llm_provider = llm_provider
        self.model = model
        self._initialize_agents()
    
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
        return task_factory.create_task("technical_analysis", self.technical_analyst)
    
    @task
    def fundamental_analysis_task(self) -> Task:
        """Fundamental analysis task."""
        return task_factory.create_task("fundamental_analysis", self.fundamental_analyst)
    
    @task
    def risk_analysis_task(self) -> Task:
        """Risk analysis task."""
        return task_factory.create_task("risk_analysis", self.risk_analyst)
    
    @task
    def sentiment_analysis_task(self) -> Task:
        """Sentiment analysis task."""
        return task_factory.create_task("sentiment_analysis", self.sentiment_analyst)
    
    @task
    def market_analysis_task(self) -> Task:
        """Market analysis task."""
        return task_factory.create_task("market_analysis", self.market_analyst)
    
    @task
    def industry_analysis_task(self) -> Task:
        """Industry analysis task."""
        return task_factory.create_task("industry_analysis", self.industry_analyst)
    
    @task
    def competitor_analysis_task(self) -> Task:
        """Competitor analysis task."""
        return task_factory.create_task("competitor_analysis", self.competitor_analyst)
    
    @task
    def economic_analysis_task(self) -> Task:
        """Economic analysis task."""
        return task_factory.create_task("economic_analysis", self.economic_analyst)
    
    @task
    def investment_recommendation_task(self) -> Task:
        """Investment recommendation task."""
        return task_factory.create_task("investment_recommendation", self.investment_advisor)
    
    @task
    def report_generation_task(self) -> Task:
        """Report generation task."""
        return task_factory.create_task("report_generation", self.report_generator)
    
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
        """Analyze a stock using the modern crew."""
        try:
            # Create tasks with symbol
            tasks = task_factory.create_all_tasks(self.agents, symbol)
            
            # Create crew with tasks
            crew = Crew(
                agents=[agent.get_agent() for agent in self.agents.values()],
                tasks=list(tasks.values()),
                process=Process.sequential,
                verbose=True,
                memory=True,
                planning=True
            )
            
            # Prepare inputs
            inputs = {
                "symbol": symbol,
                **kwargs
            }
            
            # Run the crew
            result = crew.kickoff(inputs=inputs)
            
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
    
    def analyze_multiple_stocks(self, symbols: List[str], **kwargs) -> Dict[str, Any]:
        """Analyze multiple stocks using the modern crew."""
        try:
            results = {}
            
            for symbol in symbols:
                result = self.analyze_stock(symbol, **kwargs)
                results[symbol] = result
            
            # Summary
            completed = sum(1 for r in results.values() if r["status"] == "completed")
            failed = sum(1 for r in results.values() if r["status"] == "failed")
            
            return {
                "results": results,
                "summary": {
                    "total": len(symbols),
                    "completed": completed,
                    "failed": failed
                },
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed",
                "timestamp": self._get_timestamp()
            }
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()
