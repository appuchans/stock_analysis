"""Configuration loader for agents, tasks, flows, and LLM settings."""

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
    tools: Optional[List[str]] = None
    # Per-agent LLM overrides (provider, model, temperature, max_tokens,
    # reasoning, max_reasoning_attempts)
    llm_config: Optional[Dict[str, Any]] = None


class TaskConfig(BaseModel):
    """Task configuration model."""
    description: str
    expected_output: str
    context: List[str] = Field(default_factory=list)
    output_file: Optional[str] = None
    async_execution: bool = False
    timeout: Optional[int] = None
    retry_on_failure: bool = True
    max_retries: int = 2


class FlowPhaseConfig(BaseModel):
    """Flow phase configuration model."""
    name: str
    type: str
    tasks: List[str]
    max_concurrent: Optional[int] = None
    depends_on: Optional[List[str]] = None
    validation: Optional[Dict[str, Any]] = None


class FlowConfig(BaseModel):
    """Flow configuration model."""
    name: str
    description: str
    structure: Dict[str, Any]
    execution: Dict[str, Any]
    memory: Optional[Dict[str, Any]] = None
    human_input: Optional[Dict[str, Any]] = None


# ── LLM config models ─────────────────────────────────────────────────────────

class LLMGlobalConfig(BaseModel):
    """Global LLM defaults loaded from llm_config.yaml."""
    provider: str = "openai"
    model: str = "gpt-4o"
    temperature: float = 0.1
    max_tokens: int = 4000


class LLMEmbedderConfig(BaseModel):
    """Embedder configuration for Crew-level memory."""
    provider: str = "openai"
    model: str = "text-embedding-3-small"


class LLMConfig(BaseModel):
    """Root LLM configuration loaded from llm_config.yaml."""
    global_defaults: LLMGlobalConfig = Field(default_factory=LLMGlobalConfig, alias="global")
    agents: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    embedder: LLMEmbedderConfig = Field(default_factory=LLMEmbedderConfig)
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
    """Configuration loader for agents, tasks, flows, and LLM settings."""

    def __init__(self, config_dir: Optional[Path] = None):
        if config_dir is None:
            config_dir = Path(__file__).parent
        self.config_dir = Path(config_dir)
        self._agents_config: Optional[Dict[str, AgentConfig]] = None
        self._tasks_config: Optional[Dict[str, TaskConfig]] = None
        self._flows_config: Optional[Dict[str, FlowConfig]] = None
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

    # ── tasks ─────────────────────────────────────────────────────────────────

    def load_tasks_config(self) -> Dict[str, TaskConfig]:
        if self._tasks_config is None:
            tasks_file = self.config_dir / "tasks.yaml"
            try:
                with open(tasks_file, "r", encoding="utf-8") as f:
                    tasks_data = yaml.safe_load(f)
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Task configuration file not found: {tasks_file}. "
                    "Ensure the config directory is correctly set."
                )
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {tasks_file}: {e}")
            self._tasks_config = {
                name: TaskConfig(**config)
                for name, config in tasks_data.items()
            }
        return self._tasks_config

    # ── flows ─────────────────────────────────────────────────────────────────

    def load_flows_config(self) -> Dict[str, FlowConfig]:
        if self._flows_config is None:
            flows_file = self.config_dir / "flows.yaml"
            try:
                with open(flows_file, "r", encoding="utf-8") as f:
                    flows_data = yaml.safe_load(f)
            except FileNotFoundError:
                raise FileNotFoundError(
                    f"Flow configuration file not found: {flows_file}. "
                    "Ensure the config directory is correctly set."
                )
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {flows_file}: {e}")
            self._flows_config = {
                name: FlowConfig(**config)
                for name, config in flows_data.items()
            }
        return self._flows_config

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

    def get_task_config(self, task_name: str) -> TaskConfig:
        tasks_config = self.load_tasks_config()
        if task_name not in tasks_config:
            raise ValueError(f"Task '{task_name}' not found in configuration")
        return tasks_config[task_name]

    def get_flow_config(self, flow_name: str) -> FlowConfig:
        flows_config = self.load_flows_config()
        if flow_name not in flows_config:
            raise ValueError(f"Flow '{flow_name}' not found in configuration")
        return flows_config[flow_name]

    def reload_configs(self) -> None:
        """Invalidate all cached configs so they are reloaded on next access."""
        self._agents_config = None
        self._tasks_config = None
        self._flows_config = None
        self._llm_config = None


# Global configuration loader instance
config_loader = ConfigLoader()
