"""Modern example of using the comprehensive stock analysis solution with flows."""

import os
import sys
from pathlib import Path

# Add the src directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from stock_analysis import (
    ModernStockAnalysisCrew, 
    StockAnalysisFlowCrew, 
    QuickAnalysisFlowCrew,
    DeepDiveAnalysisFlowCrew
)
from stock_analysis.config.settings import settings


def main():
    """Run modern stock analysis examples."""
    
    # Set up API keys (you can also use environment variables)
    # settings.openai_api_key = "your-openai-api-key"
    # settings.anthropic_api_key = "your-anthropic-api-key"
    
    print("🚀 Modern Stock Analysis Examples")
    print("=" * 50)
    
    # Example 1: Modern Configuration-Based Crew
    print("\n1. Modern Configuration-Based Crew")
    print("-" * 40)
    
    modern_crew = ModernStockAnalysisCrew(
        llm_provider="openai",
        model="gpt-4"
    )
    
    print("✅ Modern crew initialized with configuration-based agents and tasks")
    
    # Example 2: Flow-Based Crew
    print("\n2. Flow-Based Crew")
    print("-" * 40)
    
    flow_crew = StockAnalysisFlowCrew(
        llm_provider="openai",
        model="gpt-4",
        flow_name="stock_analysis_flow"
    )
    
    print("✅ Flow-based crew initialized with modern CrewAI flows")
    print(f"   Flow status: {flow_crew.get_flow_status()}")
    
    # Example 3: Quick Analysis Flow
    print("\n3. Quick Analysis Flow")
    print("-" * 40)
    
    quick_crew = QuickAnalysisFlowCrew(
        llm_provider="openai",
        model="gpt-4"
    )
    
    print("✅ Quick analysis crew initialized for streamlined analysis")
    
    # Example 4: Deep Dive Analysis Flow
    print("\n4. Deep Dive Analysis Flow")
    print("-" * 40)
    
    deep_dive_crew = DeepDiveAnalysisFlowCrew(
        llm_provider="openai",
        model="gpt-4"
    )
    
    print("✅ Deep dive analysis crew initialized for comprehensive analysis")
    
    # Example 5: Analyze a stock with different crew types
    symbol = "AAPL"
    print(f"\n5. Analyzing {symbol} with different crew types")
    print("-" * 40)
    
    crews = {
        "Modern": modern_crew,
        "Flow": flow_crew,
        "Quick": quick_crew,
        "Deep Dive": deep_dive_crew
    }
    
    for crew_name, crew in crews.items():
        print(f"\n🔍 {crew_name} Crew Analysis:")
        try:
            result = crew.analyze_stock(symbol)
            if result["status"] == "completed":
                print(f"   ✅ Analysis completed successfully")
                print(f"   📊 Result: {result.get('analysis_result', 'No result')}")
            else:
                print(f"   ❌ Analysis failed: {result.get('error', 'Unknown error')}")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")
    
    # Example 6: Configuration management
    print(f"\n6. Configuration Management")
    print("-" * 40)
    
    from stock_analysis.config.loader import config_loader
    
    # Load agent configurations
    agents_config = config_loader.load_agents_config()
    print(f"✅ Loaded {len(agents_config)} agent configurations")
    
    # Load task configurations
    tasks_config = config_loader.load_tasks_config()
    print(f"✅ Loaded {len(tasks_config)} task configurations")
    
    # Load flow configurations
    flows_config = config_loader.load_flows_config()
    print(f"✅ Loaded {len(flows_config)} flow configurations")
    
    # Example 7: Task factory usage
    print(f"\n7. Task Factory Usage")
    print("-" * 40)
    
    from stock_analysis.tasks.task_factory import task_factory
    
    # Get task execution order
    execution_order = task_factory.get_task_execution_order()
    print(f"✅ Task execution order: {' -> '.join(execution_order)}")
    
    # Get task dependencies
    for task_name in ["technical_analysis", "fundamental_analysis", "investment_recommendation"]:
        dependencies = task_factory.get_task_dependencies(task_name)
        print(f"   {task_name} depends on: {dependencies}")
    
    print(f"\n🎉 Modern analysis examples completed!")
    print(f"\nKey Features Demonstrated:")
    print(f"  ✅ Configuration-based agents and tasks")
    print(f"  ✅ Modern CrewAI flows")
    print(f"  ✅ Multiple crew types (modern, flow, quick, deep dive)")
    print(f"  ✅ Task factory and dependency management")
    print(f"  ✅ Flexible crew selection")
    print(f"  ✅ Separation of concerns")


if __name__ == "__main__":
    main()
