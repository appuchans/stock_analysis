"""Tests for stock analysis functionality."""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

from src.stock_analysis.tools.data_collection import YahooFinanceTool
from src.stock_analysis.tools.analysis_tools import TechnicalAnalysisTool, FundamentalAnalysisTool
from src.stock_analysis.tools.calculation_tools import FinancialCalculatorTool
from src.stock_analysis.models.stock_data import PriceData, VolumeData, CompanyInfo, MarketData


class TestYahooFinanceTool:
    """Test Yahoo Finance data collection tool."""
    
    def test_yahoo_finance_tool_initialization(self):
        """Test tool initialization."""
        tool = YahooFinanceTool()
        assert tool.name == "Yahoo Finance Data Collector"
        assert tool.description is not None
    
    @patch('yfinance.Ticker')
    def test_collect_data_success(self, mock_ticker):
        """Test successful data collection."""
        # Mock the ticker and its methods
        mock_ticker_instance = Mock()
        mock_ticker.return_value = mock_ticker_instance
        
        # Mock info data
        mock_ticker_instance.info = {
            'longName': 'Apple Inc.',
            'sector': 'Technology',
            'industry': 'Consumer Electronics',
            'country': 'US',
            'exchange': 'NASDAQ',
            'currency': 'USD',
            'website': 'https://www.apple.com',
            'longBusinessSummary': 'Apple Inc. designs, manufactures, and markets...',
            'fullTimeEmployees': 164000,
            'founded': 1976,
            'companyOfficers': [{'name': 'Tim Cook'}],
            'city': 'Cupertino',
            'state': 'CA',
            'previousClose': 150.0,
            'averageVolume': 50000000,
            'marketCap': 2500000000000,
            'fiftyTwoWeekHigh': 200.0,
            'fiftyTwoWeekLow': 120.0,
            'beta': 1.2,
            'trailingPE': 25.0,
            'priceToBook': 5.0,
            'priceToSalesTrailing12Months': 6.0,
            'pegRatio': 1.5,
            'enterpriseToEbitda': 20.0,
            'returnOnEquity': 0.15,
            'returnOnAssets': 0.08,
            'grossMargins': 0.38,
            'operatingMargins': 0.25,
            'profitMargins': 0.20,
            'debtToEquity': 0.5,
            'currentRatio': 1.5,
            'quickRatio': 1.2,
            'enterpriseValue': 2600000000000,
            'totalRevenue': 400000000000,
            'netIncomeToCommon': 80000000000,
            'totalAssets': 350000000000,
            'totalLiab': 200000000000,
            'totalStockholderEquity': 150000000000,
            'freeCashflow': 100000000000,
            'dividendYield': 0.005,
            'dividendRate': 0.75,
            'payoutRatio': 0.25
        }
        
        # Mock historical data
        mock_hist = pd.DataFrame({
            'Open': [150.0, 151.0, 152.0],
            'High': [155.0, 156.0, 157.0],
            'Low': [149.0, 150.0, 151.0],
            'Close': [154.0, 155.0, 156.0],
            'Adj Close': [153.0, 154.0, 155.0],
            'Volume': [50000000, 51000000, 52000000]
        }, index=pd.date_range('2024-01-01', periods=3))
        
        mock_ticker_instance.history.return_value = mock_hist
        
        # Test the tool
        tool = YahooFinanceTool()
        result = tool._run("AAPL", period="1y", interval="1d")
        
        # Assertions
        assert "company_info" in result
        assert "market_data" in result
        assert "price_history" in result
        assert "volume_history" in result
        assert "fundamental_data" in result
        
        # Check company info
        company_info = result["company_info"]
        assert company_info["symbol"] == "AAPL"
        assert company_info["name"] == "Apple Inc."
        assert company_info["sector"] == "Technology"
        
        # Check market data
        market_data = result["market_data"]
        assert market_data["symbol"] == "AAPL"
        assert market_data["current_price"] == 156.0
        
        # Check price history
        price_history = result["price_history"]
        assert len(price_history) == 3
        assert price_history[0]["open"] == 150.0
        assert price_history[0]["close"] == 154.0


class TestTechnicalAnalysisTool:
    """Test technical analysis tool."""
    
    def test_technical_analysis_tool_initialization(self):
        """Test tool initialization."""
        tool = TechnicalAnalysisTool()
        assert tool.name == "Technical Analysis Tool"
        assert tool.description is not None
    
    def test_calculate_indicators(self):
        """Test technical indicator calculations."""
        # Create sample data
        dates = pd.date_range('2024-01-01', periods=100)
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        
        df = pd.DataFrame({
            'open': prices * 0.99,
            'high': prices * 1.01,
            'low': prices * 0.98,
            'close': prices,
            'volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
        
        tool = TechnicalAnalysisTool()
        indicators = tool._calculate_indicators(df)
        
        # Check that indicators are calculated
        assert 'sma_20' in indicators
        assert 'rsi' in indicators
        assert 'macd' in indicators
        assert 'bollinger_upper' in indicators
        
        # Check that values are reasonable
        assert indicators['sma_20'] is not None
        assert 0 <= indicators['rsi'] <= 100 if indicators['rsi'] is not None else True
    
    def test_generate_signals(self):
        """Test signal generation."""
        # Create sample data
        dates = pd.date_range('2024-01-01', periods=100)
        np.random.seed(42)
        prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
        
        df = pd.DataFrame({
            'open': prices * 0.99,
            'high': prices * 1.01,
            'low': prices * 0.98,
            'close': prices,
            'volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
        
        tool = TechnicalAnalysisTool()
        indicators = tool._calculate_indicators(df)
        signals = tool._generate_signals(df, indicators)
        
        # Check signal structure
        assert 'buy_signals' in signals
        assert 'sell_signals' in signals
        assert 'neutral_signals' in signals
        assert 'signal_strength' in signals
        assert 'recommendation' in signals
        
        # Check signal values
        assert isinstance(signals['buy_signals'], int)
        assert isinstance(signals['sell_signals'], int)
        assert isinstance(signals['neutral_signals'], int)
        assert 0 <= signals['signal_strength'] <= 1
        assert signals['recommendation'] in ['BUY', 'SELL', 'HOLD']


class TestFundamentalAnalysisTool:
    """Test fundamental analysis tool."""
    
    def test_fundamental_analysis_tool_initialization(self):
        """Test tool initialization."""
        tool = FundamentalAnalysisTool()
        assert tool.name == "Fundamental Analysis Tool"
        assert tool.description is not None
    
    def test_analyze_valuation(self):
        """Test valuation analysis."""
        fundamental_data = {
            'pe_ratio': 20.0,
            'pb_ratio': 3.0,
            'ps_ratio': 5.0,
            'peg_ratio': 1.2,
            'ev_ebitda': 15.0
        }
        
        market_data = {
            'current_price': 150.0
        }
        
        tool = FundamentalAnalysisTool()
        valuation = tool._analyze_valuation(fundamental_data, market_data)
        
        # Check valuation structure
        assert 'pe_ratio' in valuation
        assert 'pb_ratio' in valuation
        assert 'score' in valuation
        assert 'assessment' in valuation
        
        # Check values
        assert valuation['pe_ratio'] == 20.0
        assert valuation['pb_ratio'] == 3.0
        assert 0 <= valuation['score'] <= 1
        assert valuation['assessment'] in ['undervalued', 'fairly_valued', 'overvalued']
    
    def test_analyze_profitability(self):
        """Test profitability analysis."""
        fundamental_data = {
            'roe': 0.15,
            'roa': 0.08,
            'roic': 0.12,
            'gross_margin': 0.38,
            'operating_margin': 0.25,
            'net_margin': 0.20
        }
        
        tool = FundamentalAnalysisTool()
        profitability = tool._analyze_profitability(fundamental_data)
        
        # Check profitability structure
        assert 'roe' in profitability
        assert 'roa' in profitability
        assert 'score' in profitability
        assert 'assessment' in profitability
        
        # Check values
        assert profitability['roe'] == 0.15
        assert profitability['roa'] == 0.08
        assert 0 <= profitability['score'] <= 1
        assert profitability['assessment'] in ['excellent', 'good', 'average', 'poor']


class TestFinancialCalculatorTool:
    """Test financial calculator tool."""
    
    def test_financial_calculator_tool_initialization(self):
        """Test tool initialization."""
        tool = FinancialCalculatorTool()
        assert tool.name == "Financial Calculator Tool"
        assert tool.description is not None
    
    def test_calculate_ratios(self):
        """Test ratio calculations."""
        tool = FinancialCalculatorTool()
        
        ratios = tool._calculate_ratios(
            price=150.0,
            earnings=6.0,
            book_value=50.0,
            sales=100.0,
            market_cap=2500000000000
        )
        
        # Check ratio calculations
        assert 'pe_ratio' in ratios
        assert 'pb_ratio' in ratios
        assert 'ps_ratio' in ratios
        
        assert ratios['pe_ratio'] == 25.0  # 150 / 6
        assert ratios['pb_ratio'] == 3.0   # 150 / 50
        assert ratios['ps_ratio'] == 2500000000000 / 100.0
    
    def test_calculate_returns(self):
        """Test return calculations."""
        tool = FinancialCalculatorTool()
        
        prices = [100.0, 105.0, 110.0, 108.0, 115.0]
        returns = tool._calculate_returns(prices)
        
        # Check return structure
        assert 'returns' in returns
        assert 'mean_return' in returns
        assert 'std_return' in returns
        assert 'total_return' in returns
        
        # Check values
        assert len(returns['returns']) == 4  # One less than input prices
        assert returns['total_return'] == 0.15  # (115 - 100) / 100
        assert isinstance(returns['mean_return'], float)
        assert isinstance(returns['std_return'], float)


class TestDataModels:
    """Test data models."""
    
    def test_price_data_model(self):
        """Test PriceData model."""
        price_data = PriceData(
            open=150.0,
            high=155.0,
            low=149.0,
            close=154.0,
            timestamp=datetime.now()
        )
        
        assert price_data.open == 150.0
        assert price_data.high == 155.0
        assert price_data.low == 149.0
        assert price_data.close == 154.0
        assert isinstance(price_data.timestamp, datetime)
    
    def test_company_info_model(self):
        """Test CompanyInfo model."""
        company_info = CompanyInfo(
            symbol="AAPL",
            name="Apple Inc.",
            sector="Technology",
            industry="Consumer Electronics",
            country="US",
            exchange="NASDAQ",
            currency="USD"
        )
        
        assert company_info.symbol == "AAPL"
        assert company_info.name == "Apple Inc."
        assert company_info.sector == "Technology"
        assert company_info.industry == "Consumer Electronics"
    
    def test_market_data_model(self):
        """Test MarketData model."""
        market_data = MarketData(
            symbol="AAPL",
            current_price=150.0,
            volume=50000000,
            timestamp=datetime.now()
        )
        
        assert market_data.symbol == "AAPL"
        assert market_data.current_price == 150.0
        assert market_data.volume == 50000000
        assert isinstance(market_data.timestamp, datetime)


@pytest.fixture
def sample_price_data():
    """Sample price data for testing."""
    dates = pd.date_range('2024-01-01', periods=100)
    np.random.seed(42)
    prices = 100 + np.cumsum(np.random.randn(100) * 0.5)
    
    return [
        {
            'open': prices[i] * 0.99,
            'high': prices[i] * 1.01,
            'low': prices[i] * 0.98,
            'close': prices[i],
            'timestamp': dates[i].to_pydatetime()
        }
        for i in range(100)
    ]


@pytest.fixture
def sample_volume_data():
    """Sample volume data for testing."""
    dates = pd.date_range('2024-01-01', periods=100)
    np.random.seed(42)
    volumes = np.random.randint(1000000, 5000000, 100)
    
    return [
        {
            'volume': volumes[i],
            'timestamp': dates[i].to_pydatetime()
        }
        for i in range(100)
    ]


def test_technical_analysis_integration(sample_price_data, sample_volume_data):
    """Test technical analysis with sample data."""
    tool = TechnicalAnalysisTool()
    result = tool._run(sample_price_data, sample_volume_data)
    
    assert "indicators" in result
    assert "patterns" in result
    assert "signals" in result
    assert "trend_strength" in result
    assert "support_resistance" in result
    assert "analysis_timestamp" in result


if __name__ == "__main__":
    pytest.main([__file__])
