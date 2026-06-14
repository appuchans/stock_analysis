#!/usr/bin/env python3
"""Setup script for comprehensive stock analysis solution."""

import os
import sys
import subprocess
from pathlib import Path


def run_command(command, description):
    """Run a command and handle errors."""
    print(f"🔄 {description}...")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return False


def main():
    """Main setup function."""
    print("🚀 Setting up Comprehensive Stock Analysis Solution")
    print("=" * 60)
    
    # Check Python version
    if sys.version_info < (3, 8):
        print("❌ Python 3.8 or higher is required")
        sys.exit(1)
    
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} detected")
    
    # Create necessary directories
    directories = ["data", "reports", "logs", "tests"]
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Created directory: {directory}")
    
    # Install dependencies
    if not run_command("pip install -e .", "Installing dependencies"):
        print("❌ Failed to install dependencies")
        sys.exit(1)
    
    # Install development dependencies
    if not run_command("pip install -e .[dev]", "Installing development dependencies"):
        print("⚠️  Warning: Failed to install development dependencies")
    
    # Copy environment file
    if not Path(".env").exists():
        if Path("env.example").exists():
            run_command("cp env.example .env", "Creating environment file")
            print("📝 Please edit .env file with your API keys")
        else:
            print("⚠️  Warning: env.example file not found")
    
    # Run tests
    if not run_command("python -m pytest tests/ -v", "Running tests"):
        print("⚠️  Warning: Some tests failed")
    
    print("\n" + "=" * 60)
    print("🎉 Setup completed successfully!")
    print("\nNext steps:")
    print("1. Edit .env file with your API keys")
    print("2. Run: python -m stock_analysis.main AAPL")
    print("3. Check the reports/ directory for results")
    print("\nFor more information, see README.md")


if __name__ == "__main__":
    main()
