# Comprehensive Stock Analysis Solution

A production-ready, agent-based stock analysis solution built using CrewAI framework. This system provides comprehensive analysis of stocks including fundamentals, technical analysis, market sentiment, risk assessment, and investment recommendations.

## Features

### 🏗️ Modern Architecture
- **Configuration-Based**: Agents and tasks defined in YAML files
- **CrewAI Flows**: Advanced orchestration with parallel and sequential execution
- **Multiple Crew Types**: Modern, Flow, Quick, and Deep Dive analysis crews
- **Separation of Concerns**: Clean architecture with configurable components
- **Task Factory**: Dynamic task creation with dependency management

### 🤖 Specialized AI Agents
- **Data Collector Agent**: Gathers data from multiple sources (Yahoo Finance, Alpha Vantage, SEC, FRED, etc.)
- **Technical Analyst Agent**: Performs technical analysis with indicators, patterns, and signals
- **Fundamental Analyst Agent**: Analyzes financial statements, valuation, and growth metrics
- **Risk Analyst Agent**: Assesses market, credit, liquidity, and operational risks
- **Sentiment Analyst Agent**: Analyzes news, social media, and analyst sentiment
- **Market Analyst Agent**: Evaluates market conditions and trends
- **Industry Analyst Agent**: Analyzes industry dynamics and competitive landscape
- **Competitor Analyst Agent**: Compares against industry peers
- **Economic Analyst Agent**: Assesses macroeconomic factors
- **Investment Advisor Agent**: Synthesizes all analysis into investment recommendations
- **Report Generator Agent**: Creates comprehensive investment reports

### 📊 Comprehensive Analysis
- **Technical Analysis**: 20+ technical indicators, chart patterns, trend analysis
- **Fundamental Analysis**: Financial ratios, valuation metrics, growth analysis
- **Risk Assessment**: Market risk, credit risk, liquidity risk, operational risk
- **Sentiment Analysis**: News sentiment, analyst opinions, market psychology
- **Market Analysis**: Market conditions, sector trends, volatility analysis
- **Industry Analysis**: Industry trends, competitive dynamics, regulatory factors
- **Economic Analysis**: Macroeconomic indicators, monetary policy, economic cycles

### 🛠️ Advanced Tools
- **Data Collection Tools**: Multiple free data sources with fallback mechanisms
- **Analysis Tools**: Sophisticated analysis algorithms and calculations
- **Calculation Tools**: Financial calculations, risk metrics, valuation models
- **Comparison Tools**: Peer comparison, industry benchmarking

### 💰 Free APIs Only
- **Yahoo Finance**: Free stock data and company information
- **SEC EDGAR**: Free access to regulatory filings
- **FRED**: Free economic indicators from Federal Reserve
- **RSS Feeds**: Free news and market updates
- **Web Scraping**: Free data from financial websites
- **DuckDuckGo**: Free web search capabilities

### 📈 Investment Recommendations
- **Buy/Hold/Sell Recommendations**: Based on comprehensive analysis
- **Target Price**: Calculated using multiple valuation methods
- **Risk Assessment**: Risk level and key risk factors
- **Time Horizon**: Short, medium, or long-term investment outlook
- **Portfolio Positioning**: Allocation and diversification advice

## Installation

### Prerequisites
- Python 3.8 or higher
- API keys for data sources (optional but recommended)

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd comprehensive_stock_analysis
```

2. **Install dependencies**
```bash
pip install -e .
```

3. **Set up environment variables**
```bash
cp env.example .env
# Edit .env with your API keys
```

4. **Configure API keys** (optional)
```bash
# Required for full functionality
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key

# Optional but recommended
ALPHA_VANTAGE_API_KEY=your_alpha_vantage_api_key
SEC_API_KEY=your_sec_api_key
FRED_API_KEY=your_fred_api_key
QUANDL_API_KEY=your_quandl_api_key
TAVILY_API_KEY=your_tavily_api_key
SERPAPI_API_KEY=your_serpapi_api_key
```

## Usage

### Command Line Interface

```bash
# Analyze a single stock with modern crew
python -m stock_analysis.main AAPL

# Analyze with flow-based crew
python -m stock_analysis.main AAPL --crew-type flow

# Quick analysis
python -m stock_analysis.main AAPL --crew-type quick

# Deep dive analysis
python -m stock_analysis.main AAPL --crew-type deep_dive

# Analyze multiple stocks
python -m stock_analysis.main AAPL MSFT GOOGL

# Specify output file
python -m stock_analysis.main AAPL --output reports/aapl_analysis.json

# Use different LLM provider
python -m stock_analysis.main AAPL --llm-provider anthropic --model claude-3-sonnet

# Specify analysis timeframe
python -m stock_analysis.main AAPL --timeframe 2y
```

### Python API

```python
# Modern configuration-based crew
from stock_analysis import ModernStockAnalysisCrew

crew = ModernStockAnalysisCrew(llm_provider="openai", model="gpt-4")
result = crew.analyze_stock("AAPL")

# Flow-based crew
from stock_analysis import StockAnalysisFlowCrew

crew = StockAnalysisFlowCrew(llm_provider="openai", model="gpt-4")
result = crew.analyze_stock("AAPL")

# Quick analysis
from stock_analysis import QuickAnalysisFlowCrew

crew = QuickAnalysisFlowCrew(llm_provider="openai", model="gpt-4")
result = crew.analyze_stock("AAPL")

# Deep dive analysis
from stock_analysis import DeepDiveAnalysisFlowCrew

crew = DeepDiveAnalysisFlowCrew(llm_provider="openai", model="gpt-4")
result = crew.analyze_stock("AAPL")
```

### Configuration

Create a configuration file to customize analysis parameters:

```json
{
    "timeframe": "1y",
    "technical_indicators": ["SMA", "EMA", "RSI", "MACD", "BB"],
    "fundamental_metrics": ["PE", "PB", "PS", "PEG", "ROE"],
    "risk_metrics": ["volatility", "beta", "var", "max_drawdown"],
    "analysis_depth": "comprehensive"
}
```

## Data Sources

### Primary Sources
- **Yahoo Finance**: Price data, fundamentals, company information
- **Alpha Vantage**: Additional financial data and indicators
- **SEC Filings**: 10-K, 10-Q, 8-K forms and regulatory data
- **FRED**: Economic indicators and macroeconomic data
- **Quandl**: Financial and economic datasets

### News and Sentiment
- **Tavily**: News search and sentiment analysis
- **SerpAPI**: Google search results and news
- **RSS Feeds**: Financial news feeds

### Fallback Mechanisms
- Multiple data sources with automatic fallback
- Caching to reduce API calls
- Error handling and retry logic

## Analysis Components

### Technical Analysis
- **Moving Averages**: SMA, EMA, WMA
- **Momentum Indicators**: RSI, MACD, Stochastic, Williams %R
- **Volatility Indicators**: Bollinger Bands, ATR, Keltner Channels
- **Trend Indicators**: ADX, CCI, Aroon, Parabolic SAR
- **Volume Indicators**: OBV, A/D Line, MFI, VPT
- **Pattern Recognition**: Double tops/bottoms, triangles, flags

### Fundamental Analysis
- **Valuation Metrics**: P/E, P/B, P/S, PEG, EV/EBITDA
- **Profitability**: ROE, ROA, ROIC, margins
- **Financial Health**: Debt ratios, liquidity ratios, coverage ratios
- **Growth Metrics**: Revenue growth, earnings growth, book value growth
- **Valuation Models**: DCF, Comparable, Asset-based

### Risk Analysis
- **Market Risk**: Volatility, beta, VaR, maximum drawdown
- **Credit Risk**: Debt levels, coverage ratios, credit scores
- **Liquidity Risk**: Current ratio, quick ratio, cash ratio
- **Operational Risk**: Growth metrics, efficiency ratios

### Sentiment Analysis
- **News Sentiment**: Keyword-based sentiment scoring
- **Analyst Sentiment**: Recommendation analysis
- **Social Media**: Sentiment from social platforms
- **Market Sentiment**: Fear/greed indicators

## Output Formats

### JSON Output
```json
{
    "symbol": "AAPL",
    "analysis_result": {
        "technical_analysis": {...},
        "fundamental_analysis": {...},
        "risk_analysis": {...},
        "sentiment_analysis": {...},
        "investment_recommendation": {...}
    },
    "status": "completed",
    "timestamp": "2024-01-01T00:00:00Z"
}
```

### PDF Report
- Executive summary
- Detailed analysis sections
- Charts and visualizations
- Investment recommendation
- Risk assessment
- Supporting data

## Performance and Scalability

### Optimization Features
- **Parallel Processing**: Multiple agents work simultaneously
- **Caching**: Reduces API calls and improves performance
- **Rate Limiting**: Respects API rate limits
- **Error Handling**: Robust error handling and recovery

### Scalability
- **Horizontal Scaling**: Can be deployed across multiple instances
- **Database Integration**: Supports SQLite, PostgreSQL, MySQL
- **Queue System**: Celery integration for background processing
- **API Endpoints**: RESTful API for integration

## Monitoring and Logging

### Logging
- **Structured Logging**: JSON-formatted logs
- **Log Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Log Rotation**: Automatic log file rotation
- **Centralized Logging**: Support for centralized log aggregation

### Monitoring
- **Performance Metrics**: Response times, success rates
- **Error Tracking**: Error rates and types
- **Resource Usage**: CPU, memory, disk usage
- **API Usage**: API call counts and costs

## Testing

### Test Suite
```bash
# Run all tests
pytest

# Run specific test categories
pytest -m unit
pytest -m integration
pytest -m slow

# Run with coverage
pytest --cov=src/stock_analysis
```

### Test Categories
- **Unit Tests**: Individual component testing
- **Integration Tests**: End-to-end workflow testing
- **Performance Tests**: Load and stress testing
- **API Tests**: External API integration testing

## Deployment

### Docker Deployment
```bash
# Build Docker image
docker build -t stock-analysis .

# Run container
docker run -p 8000:8000 stock-analysis
```

### Production Deployment
- **Environment Variables**: Secure configuration management
- **Secrets Management**: API keys and sensitive data
- **Health Checks**: Application health monitoring
- **Auto-scaling**: Automatic scaling based on load

## Contributing

### Development Setup
```bash
# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Run linting
black src/
isort src/
flake8 src/
mypy src/
```

### Code Quality
- **Black**: Code formatting
- **isort**: Import sorting
- **flake8**: Linting
- **mypy**: Type checking
- **pytest**: Testing

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support and questions:
- Create an issue on GitHub
- Check the documentation
- Review the examples

## Roadmap

### Upcoming Features
- [ ] Real-time analysis updates
- [ ] Portfolio optimization
- [ ] Backtesting capabilities
- [ ] Machine learning integration
- [ ] Advanced visualization
- [ ] Mobile application
- [ ] API rate limiting
- [ ] Advanced caching strategies

### Version History
- **v0.1.0**: Initial release with basic functionality
- **v0.2.0**: Enhanced analysis capabilities
- **v0.3.0**: Advanced reporting features
- **v1.0.0**: Production-ready release

## Disclaimer

This tool is for educational and research purposes only. It does not provide financial advice. Always consult with a qualified financial advisor before making investment decisions. Past performance does not guarantee future results.
