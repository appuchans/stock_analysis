"""Configuration loader for agents, tasks, and LLM settings."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


# ── Agent / Task / Flow config models ────────────────────────────────────────

class AgentConfig(BaseModel):
    """Agent configuration model."""
    role: str
    goal: str
    backstory: str
    verbose: bool = True
    allow_delegation: bool = False
    max_iter: int = 3
    # Hard cap per task execution — prevents a hung LLM call from stalling
    # the whole pipeline (CrewAI Agent.max_execution_time)
    max_execution_time: int = 300
    # Requests-per-minute throttle — second brake on runaway loops and a
    # politeness cap toward the provider (CrewAI Agent.max_rpm)
    max_rpm: int = 10
    # Retries after an agent execution error (CrewAI default is 2; one is
    # enough — multiplicative retry layers caused call storms)
    max_retry_limit: int = 1
    # Inject the current date into task context so 'as of' statements are right
    inject_date: bool = True
    tools: Optional[List[str]] = None
    # Per-agent LLM overrides (provider, model, temperature, max_tokens,
    # reasoning, max_reasoning_attempts)
    llm_config: Optional[Dict[str, Any]] = None


# ── LLM config models ─────────────────────────────────────────────────────────

class LLMGlobalConfig(BaseModel):
    """Global LLM defaults loaded from llm_config.yaml."""
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4000
    timeout: int = 120
    max_retries: int = 3


class LLMConfig(BaseModel):
    """Root LLM configuration loaded from llm_config.yaml."""
    global_defaults: LLMGlobalConfig = Field(default_factory=LLMGlobalConfig, alias="global")
    agents: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    provider_prefixes: Dict[str, str] = Field(default_factory=lambda: {
        "openai": "openai/",
        "anthropic": "anthropic/",
        "ollama": "ollama/",
        "azure": "azure/",
        "groq": "groq/",
        "mistral": "mistral/",
        "cohere": "cohere/",
        "bedrock": "bedrock/",
        "huggingface": "huggingface/",
        "vertexai": "vertexai/",
    })

    model_config = {"populate_by_name": True}


# ── Loader ────────────────────────────────────────────────────────────────────

class ConfigLoader:
    """Configuration loader for agents, tasks, and LLM settings."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).parent
        self.config_dir = Path(config_dir)
        self._agents_config: Optional[Dict[str, AgentConfig]] = None
        self._flow_tasks_config: Optional[Dict[str, Any]] = None
        self._llm_config: Optional[LLMConfig] = None

    # ── agents ────────────────────────────────────────────────────────────────

    def load_agents_config(self) -> Dict[str, AgentConfig]:
        if self._agents_config is None:
            agents_file = self.config_dir / "agents.yaml"
            try:
                with open(agents_file, "r", encoding="utf-8") as f:
                    agents_data = yaml.safe_load(f)
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Agent configuration file not found: {agents_file}. "
                    "Ensure the config directory is correctly set."
                )
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {agents_file}: {e}")
            self._agents_config = {
                name: AgentConfig(**config)
                for name, config in agents_data.items()
            }
        return self._agents_config

    # ── flow stage prompts ────────────────────────────────────────────────────

    def load_flow_tasks_config(self) -> Dict[str, Any]:
        """Load Flow-pipeline stage prompts from flow_tasks.yaml."""
        if self._flow_tasks_config is None:
            flow_file = self.config_dir / "flow_tasks.yaml"
            try:
                with open(flow_file, "r", encoding="utf-8") as f:
                    self._flow_tasks_config = yaml.safe_load(f) or {}
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Flow task configuration file not found: {flow_file}. "
                    "Ensure the config directory is correctly set."
                )
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {flow_file}: {e}")
        return self._flow_tasks_config

    # ── LLM config ────────────────────────────────────────────────────────────

    def load_llm_config(self) -> LLMConfig:
        """Load LLM configuration from llm_config.yaml."""
        if self._llm_config is None:
            llm_file = self.config_dir / "llm_config.yaml"
            try:
                with open(llm_file, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except FileNotFoundError:
                # Fall back to all defaults if the file is missing
                data = {}
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {llm_file}: {e}")
            self._llm_config = LLMConfig(**data)
        return self._llm_config

    # ── convenience getters ───────────────────────────────────────────────────

    def get_agent_config(self, agent_name: str) -> AgentConfig:
        agents_config = self.load_agents_config()
        if agent_name not in agents_config:
            raise ValueError(f"Agent '{agent_name}' not found in configuration")
        return agents_config[agent_name]

    def reload_configs(self) -> None:
        """Invalidate all cached configs so they are reloaded on next access."""
        self._agents_config = None
        self._flow_tasks_config = None
        self._llm_config = None


# Global configuration loader instance
config_loader = ConfigLoader()
