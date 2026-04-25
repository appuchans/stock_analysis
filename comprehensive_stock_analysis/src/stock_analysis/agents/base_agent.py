"""Base agent class with configuration loading."""

from typing import List, Any, Optional
from crewai import Agent, LLM

from ..config.loader import config_loader, AgentConfig
from ..config.settings import settings


class BaseAgent:
    """Base agent class with configuration loading capabilities."""

    def __init__(self, agent_name: str, llm_provider: str = "openai", model: str = "gpt-4o"):
        """Initialize the base agent."""
        self.agent_name = agent_name
        self.llm_provider = llm_provider
        self.model = model
        self.config = config_loader.get_agent_config(agent_name)
        self.llm = self._get_llm()
        self.tools = self._get_tools()
        self.agent = self._create_agent()

    def _get_llm(self) -> LLM:
        """Get the appropriate LLM using CrewAI's native LLM class."""
        if self.llm_provider == "openai":
            if not settings.openai_api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Set the OPENAI_API_KEY environment variable."
                )
            return LLM(
                model=f"openai/{self.model}",
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                api_key=settings.openai_api_key,
            )
        elif self.llm_provider == "anthropic":
            if not settings.anthropic_api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY is not set. Set the ANTHROPIC_API_KEY environment variable."
                )
            return LLM(
                model=f"anthropic/{self.model}",
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
                api_key=settings.anthropic_api_key,
            )
        elif self.llm_provider == "ollama":
            return LLM(
                model=f"ollama/{self.model}",
                temperature=settings.temperature,
                max_tokens=settings.max_tokens,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {self.llm_provider}")

    def _get_tools(self) -> List[Any]:
        """Get tools for the agent. Override in subclasses."""
        return []

    def _create_agent(self) -> Agent:
        """Create the agent using configuration."""
        agent_kwargs: dict = dict(
            role=self.config.role,
            goal=self.config.goal,
            backstory=self.config.backstory,
            verbose=self.config.verbose,
            allow_delegation=self.config.allow_delegation,
            tools=self.tools,
            llm=self.llm,
            max_iter=self.config.max_iter,
        )
        # reasoning and max_reasoning_attempts are opt-in per-agent via agents.yaml
        llm_cfg = self.config.llm_config or {}
        if llm_cfg.get("reasoning"):
            agent_kwargs["reasoning"] = True
            agent_kwargs["max_reasoning_attempts"] = llm_cfg.get("max_reasoning_attempts", 3)
        return Agent(**agent_kwargs)

    def get_agent(self) -> Agent:
        """Get the configured agent."""
        return self.agent

    def get_config(self) -> AgentConfig:
        """Get the agent configuration."""
        return self.config
