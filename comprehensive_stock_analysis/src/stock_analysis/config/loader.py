"""Configuration loader for agents, tasks, and flows."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class AgentConfig(BaseModel):
    """Agent configuration model."""
    role: str
    goal: str
    backstory: str
    verbose: bool = True
    allow_delegation: bool = False
    max_iter: int = 3
    memory: bool = True
    tools: Optional[List[str]] = None
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


class ConfigLoader:
    """Configuration loader for agents, tasks, and flows."""
    
    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize the configuration loader."""
        if config_dir is None:
            config_dir = Path(__file__).parent
        
        self.config_dir = Path(config_dir)
        self._agents_config: Optional[Dict[str, AgentConfig]] = None
        self._tasks_config: Optional[Dict[str, TaskConfig]] = None
        self._flows_config: Optional[Dict[str, FlowConfig]] = None
    
    def load_agents_config(self) -> Dict[str, AgentConfig]:
        """Load agent configurations."""
        if self._agents_config is None:
            agents_file = self.config_dir / "agents.yaml"
            with open(agents_file, 'r', encoding='utf-8') as f:
                agents_data = yaml.safe_load(f)
            
            self._agents_config = {
                name: AgentConfig(**config)
                for name, config in agents_data.items()
            }
        
        return self._agents_config
    
    def load_tasks_config(self) -> Dict[str, TaskConfig]:
        """Load task configurations."""
        if self._tasks_config is None:
            tasks_file = self.config_dir / "tasks.yaml"
            with open(tasks_file, 'r', encoding='utf-8') as f:
                tasks_data = yaml.safe_load(f)
            
            self._tasks_config = {
                name: TaskConfig(**config)
                for name, config in tasks_data.items()
            }
        
        return self._tasks_config
    
    def load_flows_config(self) -> Dict[str, FlowConfig]:
        """Load flow configurations."""
        if self._flows_config is None:
            flows_file = self.config_dir / "flows.yaml"
            with open(flows_file, 'r', encoding='utf-8') as f:
                flows_data = yaml.safe_load(f)
            
            self._flows_config = {
                name: FlowConfig(**config)
                for name, config in flows_data.items()
            }
        
        return self._flows_config
    
    def get_agent_config(self, agent_name: str) -> AgentConfig:
        """Get configuration for a specific agent."""
        agents_config = self.load_agents_config()
        if agent_name not in agents_config:
            raise ValueError(f"Agent '{agent_name}' not found in configuration")
        return agents_config[agent_name]
    
    def get_task_config(self, task_name: str) -> TaskConfig:
        """Get configuration for a specific task."""
        tasks_config = self.load_tasks_config()
        if task_name not in tasks_config:
            raise ValueError(f"Task '{task_name}' not found in configuration")
        return tasks_config[task_name]
    
    def get_flow_config(self, flow_name: str) -> FlowConfig:
        """Get configuration for a specific flow."""
        flows_config = self.load_flows_config()
        if flow_name not in flows_config:
            raise ValueError(f"Flow '{flow_name}' not found in configuration")
        return flows_config[flow_name]
    
    def reload_configs(self):
        """Reload all configurations from files."""
        self._agents_config = None
        self._tasks_config = None
        self._flows_config = None


# Global configuration loader instance
config_loader = ConfigLoader()
