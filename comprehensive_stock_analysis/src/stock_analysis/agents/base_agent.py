"""Base agent class with configuration loading."""

from typing import List, Any, Optional
from crewai import Agent
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

from ..config.loader import config_loader, AgentConfig
from ..config.settings import settings


class BaseAgent:
    """Base agent class with configuration loading capabilities."""
    
    def __init__(self, agent_name: str, llm_provider: str = "openai", model: str = "gpt-4"):
        """Initialize the base agent."""
        self.agent_name = agent_name
        self.llm_provider = llm_provider
        self.model = model
        self.config = config_loader.get_agent_config(agent_name)
        self.llm = self._get_llm()
        self.tools = self._get_tools()
        self.agent = self._create_agent()
    
    def _get_llm(self):
        """Get the appropriate LLM based on provider."""
        if self.llm_provider == "openai":
            return ChatOpenAI(
                model=self.model,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                api_key=settings.openai_api_key
            )
        elif self.llm_provider == "anthropic":
            return ChatAnthropic(
                model=self.model,
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                api_key=settings.anthropic_api_key
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")
    
    def _get_tools(self) -> List[Any]:
        """Get tools for the agent. Override in subclasses."""
        return []
    
    def _create_agent(self) -> Agent:
        """Create the agent using configuration."""
        return Agent(
            role=self.config.role,
            goal=self.config.goal,
            backstory=self.config.backstory,
            verbose=self.config.verbose,
            allow_delegation=self.config.allow_delegation,
            tools=self.tools,
            llm=self.llm,
            max_iter=self.config.max_iter,
            memory=self.config.memory
        )
    
    def get_agent(self) -> Agent:
        """Get the configured agent."""
        return self.agent
    
    def get_config(self) -> AgentConfig:
        """Get the agent configuration."""
        return self.config
