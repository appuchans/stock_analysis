"""Modern flow-based crew implementation for stock analysis."""

from typing import Dict, Any, Optional, List
from crewai import Flow, Crew, Process
from crewai.flow import FlowExecutor
from crewai.project import CrewBase, agent, crew, task

from ..agents import (
    DataCollectorAgent, TechnicalAnalystAgent, FundamentalAnalystAgent,
    RiskAnalystAgent, SentimentAnalystAgent, MarketAnalystAgent,
    IndustryAnalystAgent, CompetitorAnalystAgent, EconomicAnalystAgent,
    InvestmentAdvisorAgent, ReportGeneratorAgent
)
from ..config.loader import config_loader
from ..config.settings import settings


class StockAnalysisFlowCrew:
    """Modern flow-based crew for comprehensive stock analysis."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4", flow_name: str = "stock_analysis_flow"):
        """Initialize the flow-based crew."""
        self.llm_provider = llm_provider
        self.model = model
        self.flow_name = flow_name
        self.flow_config = config_loader.get_flow_config(flow_name)
        self._initialize_agents()
        self.flow = self._create_flow()
    
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
    
    def _create_flow(self) -> Flow:
        """Create the flow based on configuration."""
        # Get task configurations
        tasks_config = config_loader.load_tasks_config()
        
        # Create flow definition
        flow_definition = {
            "name": self.flow_config.name,
            "description": self.flow_config.description,
            "structure": self.flow_config.structure,
            "execution": self.flow_config.execution,
            "memory": self.flow_config.memory,
            "human_input": self.flow_config.human_input
        }
        
        # Create the flow
        flow = Flow(
            name=flow_definition["name"],
            description=flow_definition["description"],
            structure=flow_definition["structure"],
            execution=flow_definition["execution"],
            memory=flow_definition.get("memory", {}),
            human_input=flow_definition.get("human_input", {})
        )
        
        return flow
    
    def _create_tasks(self, symbol: str) -> Dict[str, Any]:
        """Create tasks based on configuration."""
        tasks_config = config_loader.load_tasks_config()
        tasks = {}
        
        for task_name, task_config in tasks_config.items():
            # Get the appropriate agent
            agent = self._get_agent_for_task(task_name)
            
            # Create task
            task = {
                "name": task_name,
                "description": task_config.description.format(symbol=symbol),
                "expected_output": task_config.expected_output.format(symbol=symbol),
                "agent": agent,
                "context": task_config.context,
                "output_file": task_config.output_file.format(symbol=symbol) if task_config.output_file else None,
                "async_execution": task_config.async_execution,
                "timeout": task_config.timeout,
                "retry_on_failure": task_config.retry_on_failure,
                "max_retries": task_config.max_retries
            }
            
            tasks[task_name] = task
        
        return tasks
    
    def _get_agent_for_task(self, task_name: str):
        """Get the appropriate agent for a task."""
        agent_mapping = {
            "data_collection": self.data_collector.get_agent(),
            "technical_analysis": self.technical_analyst.get_agent(),
            "fundamental_analysis": self.fundamental_analyst.get_agent(),
            "risk_analysis": self.risk_analyst.get_agent(),
            "sentiment_analysis": self.sentiment_analyst.get_agent(),
            "market_analysis": self.market_analyst.get_agent(),
            "industry_analysis": self.industry_analyst.get_agent(),
            "competitor_analysis": self.competitor_analyst.get_agent(),
            "economic_analysis": self.economic_analyst.get_agent(),
            "investment_recommendation": self.investment_advisor.get_agent(),
            "report_generation": self.report_generator.get_agent()
        }
        
        return agent_mapping.get(task_name, self.data_collector.get_agent())
    
    def analyze_stock(self, symbol: str, **kwargs) -> Dict[str, Any]:
        """Analyze a stock using the flow-based crew."""
        try:
            # Create tasks
            tasks = self._create_tasks(symbol)
            
            # Create flow executor
            executor = FlowExecutor(self.flow)
            
            # Prepare inputs
            inputs = {
                "symbol": symbol,
                "tasks": tasks,
                **kwargs
            }
            
            # Execute the flow
            result = executor.execute(inputs)
            
            return {
                "symbol": symbol,
                "analysis_result": result,
                "status": "completed",
                "flow_name": self.flow_name,
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "symbol": symbol,
                "error": str(e),
                "status": "failed",
                "flow_name": self.flow_name,
                "timestamp": self._get_timestamp()
            }
    
    def analyze_multiple_stocks(self, symbols: List[str], **kwargs) -> Dict[str, Any]:
        """Analyze multiple stocks using parallel flows."""
        try:
            results = {}
            
            # Create parallel flow execution
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
                "flow_name": self.flow_name,
                "timestamp": self._get_timestamp()
            }
            
        except Exception as e:
            return {
                "error": str(e),
                "status": "failed",
                "flow_name": self.flow_name,
                "timestamp": self._get_timestamp()
            }
    
    def get_flow_status(self) -> Dict[str, Any]:
        """Get the current flow status."""
        return {
            "flow_name": self.flow_name,
            "flow_config": self.flow_config.dict(),
            "agents_loaded": len(self._get_agent_list()),
            "status": "ready"
        }
    
    def _get_agent_list(self) -> List[Any]:
        """Get list of all agents."""
        return [
            self.data_collector,
            self.technical_analyst,
            self.fundamental_analyst,
            self.risk_analyst,
            self.sentiment_analyst,
            self.market_analyst,
            self.industry_analyst,
            self.competitor_analyst,
            self.economic_analyst,
            self.investment_advisor,
            self.report_generator
        ]
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        from datetime import datetime
        return datetime.now().isoformat()


class QuickAnalysisFlowCrew(StockAnalysisFlowCrew):
    """Quick analysis flow crew."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the quick analysis flow crew."""
        super().__init__(llm_provider, model, "quick_analysis_flow")


class DeepDiveAnalysisFlowCrew(StockAnalysisFlowCrew):
    """Deep dive analysis flow crew."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the deep dive analysis flow crew."""
        super().__init__(llm_provider, model, "deep_dive_flow")


class BatchAnalysisFlowCrew(StockAnalysisFlowCrew):
    """Batch analysis flow crew."""
    
    def __init__(self, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the batch analysis flow crew."""
        super().__init__(llm_provider, model, "batch_analysis_flow")
