"""Task factory for creating tasks from configuration."""

import logging
from typing import Dict, Any, List, Optional
from crewai import Task
from crewai.project import task

_logger = logging.getLogger(__name__)

from ..config.loader import config_loader, TaskConfig
from ..agents.base_agent import BaseAgent


class TaskFactory:
    """Factory for creating tasks from configuration."""
    
    def __init__(self):
        """Initialize the task factory."""
        self.tasks_config = config_loader.load_tasks_config()
    
    def create_task(self, task_name: str, agent: BaseAgent, symbol: str = None, **kwargs) -> Task:
        """Create a task from configuration."""
        if task_name not in self.tasks_config:
            raise ValueError(f"Task '{task_name}' not found in configuration")
        
        task_config = self.tasks_config[task_name]
        
        # Format description and expected output with symbol
        description = task_config.description
        expected_output = task_config.expected_output
        
        if symbol:
            description = description.format(symbol=symbol)
            expected_output = expected_output.format(symbol=symbol)
        
        output_file = (
            task_config.output_file.format(symbol=symbol)
            if task_config.output_file and symbol
            else task_config.output_file
        )
        # Create task
        task = Task(
            description=description,
            expected_output=expected_output,
            agent=agent.get_agent(),
            context=task_config.context,
            output_file=output_file,
            create_directory=True,
            async_execution=task_config.async_execution,
            **kwargs
        )
        
        return task
    
    def create_all_tasks(self, agents: Dict[str, BaseAgent], symbol: str = None) -> Dict[str, Task]:
        """Create all tasks from configuration."""
        tasks = {}
        
        for task_name in self.tasks_config.keys():
            # Get the appropriate agent for the task
            agent_name = self._get_agent_name_for_task(task_name)
            if agent_name in agents:
                task = self.create_task(task_name, agents[agent_name], symbol)
                tasks[task_name] = task
        
        return tasks
    
    def _get_agent_name_for_task(self, task_name: str) -> str:
        """Get the agent name for a task."""
        task_agent_mapping = {
            "data_collection": "data_collector",
            "technical_analysis": "technical_analyst",
            "fundamental_analysis": "fundamental_analyst",
            "risk_analysis": "risk_analyst",
            "sentiment_analysis": "sentiment_analyst",
            "market_analysis": "market_analyst",
            "industry_analysis": "industry_analyst",
            "competitor_analysis": "competitor_analyst",
            "economic_analysis": "economic_analyst",
            "investment_recommendation": "investment_advisor",
            "report_generation": "report_generator"
        }
        
        return task_agent_mapping.get(task_name, "data_collector")
    
    def get_task_dependencies(self, task_name: str) -> List[str]:
        """Get task dependencies."""
        if task_name not in self.tasks_config:
            return []
        
        return self.tasks_config[task_name].context
    
    def get_task_execution_order(self) -> List[str]:
        """Get the execution order of tasks based on dependencies."""
        tasks = list(self.tasks_config.keys())
        ordered_tasks = []
        remaining_tasks = tasks.copy()
        
        while remaining_tasks:
            # Find tasks with no unmet dependencies
            ready_tasks = []
            for task in remaining_tasks:
                dependencies = self.get_task_dependencies(task)
                if all(dep in ordered_tasks for dep in dependencies):
                    ready_tasks.append(task)
            
            if not ready_tasks:
                _logger.warning(
                    "Circular dependency detected; appending remaining tasks in original order: %s",
                    remaining_tasks,
                )
                ordered_tasks.extend(remaining_tasks)
                break
            
            # Add ready tasks to ordered list
            ordered_tasks.extend(ready_tasks)
            remaining_tasks = [t for t in remaining_tasks if t not in ready_tasks]
        
        return ordered_tasks


# Global task factory instance
task_factory = TaskFactory()
