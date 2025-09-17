# Modern Architecture Documentation

## Overview

The comprehensive stock analysis solution has been refactored to use modern CrewAI capabilities including flows, configuration-based agents and tasks, and separation of concerns. This document explains the new architecture and how to use it.

## Architecture Components

### 1. Configuration Management

#### Agent Configuration (`config/agents.yaml`)
- Centralized agent definitions with roles, goals, backstories
- Consistent configuration across all agents
- Easy modification without code changes
- Support for different agent types and specializations

#### Task Configuration (`config/tasks.yaml`)
- Task descriptions and expected outputs
- Context and dependency management
- Output file specifications
- Execution parameters (timeout, retries, etc.)

#### Flow Configuration (`config/flows.yaml`)
- Multiple flow types for different analysis needs
- Parallel and sequential execution patterns
- Human input checkpoints
- Memory and context management

### 2. Base Agent Class

```python
class BaseAgent:
    """Base agent class with configuration loading capabilities."""
    
    def __init__(self, agent_name: str, llm_provider: str, model: str):
        # Loads configuration from YAML files
        # Initializes LLM and tools
        # Creates CrewAI Agent instance
```

**Benefits:**
- Consistent agent initialization
- Configuration-driven behavior
- Easy to extend and modify
- Reduced code duplication

### 3. Task Factory

```python
class TaskFactory:
    """Factory for creating tasks from configuration."""
    
    def create_task(self, task_name: str, agent: BaseAgent, symbol: str = None):
        # Creates tasks from configuration
        # Handles symbol substitution
        # Manages dependencies and context
```

**Benefits:**
- Dynamic task creation
- Configuration-driven task definitions
- Automatic dependency management
- Symbol substitution for multiple stocks

### 4. Modern Crew Implementations

#### ModernStockAnalysisCrew
- Configuration-based agents and tasks
- Traditional CrewAI approach with modern patterns
- Easy to understand and maintain

#### StockAnalysisFlowCrew
- Uses CrewAI flows for orchestration
- Supports parallel and sequential execution
- Human input checkpoints
- Memory and context management

#### Specialized Flow Crews
- **QuickAnalysisFlowCrew**: Streamlined analysis
- **DeepDiveAnalysisFlowCrew**: Comprehensive analysis
- **BatchAnalysisFlowCrew**: Multiple stock analysis

## Usage Examples

### 1. Basic Modern Crew

```python
from stock_analysis import ModernStockAnalysisCrew

# Initialize crew
crew = ModernStockAnalysisCrew(
    llm_provider="openai",
    model="gpt-4"
)

# Analyze a stock
result = crew.analyze_stock("AAPL")
```

### 2. Flow-Based Crew

```python
from stock_analysis import StockAnalysisFlowCrew

# Initialize flow crew
crew = StockAnalysisFlowCrew(
    llm_provider="openai",
    model="gpt-4",
    flow_name="stock_analysis_flow"
)

# Analyze with flow orchestration
result = crew.analyze_stock("AAPL")
```

### 3. Quick Analysis

```python
from stock_analysis import QuickAnalysisFlowCrew

# Initialize quick analysis crew
crew = QuickAnalysisFlowCrew(
    llm_provider="openai",
    model="gpt-4"
)

# Fast analysis
result = crew.analyze_stock("AAPL")
```

### 4. Deep Dive Analysis

```python
from stock_analysis import DeepDiveAnalysisFlowCrew

# Initialize deep dive crew
crew = DeepDiveAnalysisFlowCrew(
    llm_provider="openai",
    model="gpt-4"
)

# Comprehensive analysis
result = crew.analyze_stock("AAPL")
```

## Configuration Files

### Agent Configuration Structure

```yaml
agent_name:
  role: "Agent Role"
  goal: "Agent Goal"
  backstory: "Agent Backstory"
  verbose: true
  allow_delegation: false
  max_iter: 3
  memory: true
```

### Task Configuration Structure

```yaml
task_name:
  description: "Task description with {symbol} placeholder"
  expected_output: "Expected output description"
  context: ["dependency_task1", "dependency_task2"]
  output_file: "reports/{symbol}_task_output.json"
  async_execution: false
  timeout: 300
  retry_on_failure: true
  max_retries: 2
```

### Flow Configuration Structure

```yaml
flow_name:
  name: "Flow Name"
  description: "Flow Description"
  structure:
    type: "sequential_with_parallel"
    phases:
      - name: "phase_name"
        type: "parallel"
        tasks: ["task1", "task2"]
        max_concurrent: 2
        depends_on: ["previous_phase"]
  execution:
    max_iterations: 3
    timeout: 3600
    retry_on_failure: true
    max_retries: 2
  memory:
    enabled: true
    type: "persistent"
  human_input:
    enabled: true
    checkpoints:
      - after: "task_name"
        prompt: "Review prompt"
        required: false
```

## Benefits of Modern Architecture

### 1. Separation of Concerns
- **Agents**: Focus on their specific analysis domain
- **Tasks**: Define what needs to be done
- **Flows**: Orchestrate execution patterns
- **Configuration**: Externalize behavior

### 2. Maintainability
- Easy to modify agent behavior through configuration
- Clear separation between logic and configuration
- Consistent patterns across all components
- Reduced code duplication

### 3. Flexibility
- Multiple crew types for different use cases
- Easy to add new agents or tasks
- Configurable execution patterns
- Support for different analysis depths

### 4. Scalability
- Flow-based execution supports parallel processing
- Configuration-driven approach scales well
- Easy to add new analysis types
- Support for batch processing

### 5. Modern CrewAI Features
- **Flows**: Advanced orchestration patterns
- **Memory**: Persistent context across tasks
- **Human Input**: Interactive checkpoints
- **Planning**: Dynamic task planning
- **Embeddings**: Enhanced context understanding

## Migration from Legacy Architecture

### 1. Agent Migration
```python
# Old approach
class TechnicalAnalystAgent:
    def __init__(self, llm_provider, model):
        # Hardcoded configuration
        self.agent = Agent(
            role="Senior Technical Analyst",
            goal="...",
            backstory="..."
        )

# New approach
class TechnicalAnalystAgent(BaseAgent):
    def __init__(self, llm_provider, model):
        super().__init__("technical_analyst", llm_provider, model)
        # Configuration loaded from YAML
```

### 2. Task Migration
```python
# Old approach
@task
def technical_analysis_task(self) -> Task:
    return Task(
        description="...",
        expected_output="...",
        agent=self.technical_analyst_agent(),
        context=[]
    )

# New approach
@task
def technical_analysis_task(self) -> Task:
    return task_factory.create_task("technical_analysis", self.technical_analyst)
```

### 3. Crew Migration
```python
# Old approach
@crew
def crew(self) -> Crew:
    return Crew(
        agents=self.agents,
        tasks=self.tasks,
        process=Process.sequential
    )

# New approach - Multiple options
# Modern crew
crew = ModernStockAnalysisCrew(llm_provider, model)

# Flow crew
crew = StockAnalysisFlowCrew(llm_provider, model, flow_name)

# Specialized crews
crew = QuickAnalysisFlowCrew(llm_provider, model)
crew = DeepDiveAnalysisFlowCrew(llm_provider, model)
```

## Best Practices

### 1. Configuration Management
- Keep agent configurations in `config/agents.yaml`
- Keep task configurations in `config/tasks.yaml`
- Keep flow configurations in `config/flows.yaml`
- Use meaningful names and descriptions
- Document configuration options

### 2. Agent Development
- Inherit from `BaseAgent`
- Override `_get_tools()` method
- Use configuration for behavior
- Keep agents focused on single domain

### 3. Task Development
- Define tasks in configuration files
- Use symbol substitution for multiple stocks
- Define clear dependencies
- Specify output formats

### 4. Flow Development
- Design flows for specific use cases
- Use parallel execution where possible
- Add human input checkpoints strategically
- Consider memory and context requirements

### 5. Testing
- Test individual agents
- Test task creation and execution
- Test flow orchestration
- Test configuration loading

## Troubleshooting

### Common Issues

1. **Configuration Loading Errors**
   - Check YAML syntax
   - Verify file paths
   - Ensure all required fields are present

2. **Agent Initialization Errors**
   - Check LLM provider configuration
   - Verify API keys
   - Check tool dependencies

3. **Task Creation Errors**
   - Verify task names in configuration
   - Check agent assignments
   - Validate symbol substitution

4. **Flow Execution Errors**
   - Check flow configuration
   - Verify task dependencies
   - Check execution parameters

### Debugging Tips

1. **Enable Verbose Logging**
   ```python
   crew = ModernStockAnalysisCrew(verbose=True)
   ```

2. **Check Configuration Loading**
   ```python
   from stock_analysis.config.loader import config_loader
   agents = config_loader.load_agents_config()
   print(agents)
   ```

3. **Test Individual Components**
   ```python
   # Test agent
   agent = TechnicalAnalystAgent("openai", "gpt-4")
   print(agent.get_agent())
   
   # Test task creation
   from stock_analysis.tasks.task_factory import task_factory
   task = task_factory.create_task("technical_analysis", agent, "AAPL")
   print(task)
   ```

## Future Enhancements

### 1. Advanced Flows
- Conditional execution paths
- Dynamic task selection
- Real-time monitoring
- Auto-scaling

### 2. Configuration Management
- Environment-specific configurations
- Configuration validation
- Dynamic configuration updates
- Configuration versioning

### 3. Monitoring and Observability
- Flow execution metrics
- Agent performance tracking
- Task completion rates
- Error rate monitoring

### 4. Integration Features
- API endpoints for crew management
- Webhook support
- Database integration
- Caching strategies

This modern architecture provides a solid foundation for scalable, maintainable, and flexible stock analysis using CrewAI's advanced capabilities.
