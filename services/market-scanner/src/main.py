"""
Market Scanner Service - Real-time market data processing and signal generation.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import os
import time
import redis
import json
from datetime import datetime, timedelta
import structlog
from futures_scanner import futures_scanner

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Market Scanner Service",
    description="Real-time futures market data processing and signal generation",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection for caching
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6379))
redis_client = redis.Redis(host=redis_host, port=redis_port, db=1, decode_responses=True)

# Popular trading symbols
SYMBOLS = [
    'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
    'SPY', 'QQQ', 'IWM', 'GLD', 'SLV', 'TLT', 'VIX', 'EURUSD=X'
]

class TechnicalIndicators:
    """Technical analysis indicators."""
    
    @staticmethod
    def sma(data: pd.Series, window: int) -> pd.Series:
        """Simple Moving Average."""
        return data.rolling(window=window).mean()
    
    @staticmethod
    def ema(data: pd.Series, window: int) -> pd.Series:
        """Exponential Moving Average."""
        return data.ewm(span=window).mean()
    
    @staticmethod
    def rsi(data: pd.Series, window: int = 14) -> pd.Series:
        """Relative Strength Index."""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def bollinger_bands(data: pd.Series, window: int = 20, num_std: float = 2):
        """Bollinger Bands."""
        sma = data.rolling(window=window).mean()
        std = data.rolling(window=window).std()
        upper = sma + (std * num_std)
        lower = sma - (std * num_std)
        return upper, sma, lower
    
    @staticmethod
    def macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD indicator."""
        ema_fast = data.ewm(span=fast).mean()
        ema_slow = data.ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

class SignalGenerator:
    """Generate trading signals based on technical analysis."""
    
    def __init__(self):
        self.indicators = TechnicalIndicators()
    
    def generate_signals(self, data: pd.DataFrame) -> Dict:
        """Generate comprehensive trading signals."""
        signals = {
            'symbol': data.attrs.get('symbol', 'UNKNOWN'),
            'timestamp': datetime.now().isoformat(),
            'price': float(data['Close'].iloc[-1]),
            'signals': []
        }
        
        # RSI signals
        rsi = self.indicators.rsi(data['Close'])
        current_rsi = rsi.iloc[-1]
        
        if current_rsi < 30:
            signals['signals'].append({
                'type': 'BUY',
                'indicator': 'RSI',
                'strength': 0.8,
                'reason': f'RSI oversold at {current_rsi:.2f}'
            })
        elif current_rsi > 70:
            signals['signals'].append({
                'type': 'SELL',
                'indicator': 'RSI',
                'strength': 0.8,
                'reason': f'RSI overbought at {current_rsi:.2f}'
            })
        
        # Moving Average Crossover
        sma_20 = self.indicators.sma(data['Close'], 20)
        sma_50 = self.indicators.sma(data['Close'], 50)
        
        if sma_20.iloc[-1] > sma_50.iloc[-1] and sma_20.iloc[-2] <= sma_50.iloc[-2]:
            signals['signals'].append({
                'type': 'BUY',
                'indicator': 'MA_CROSSOVER',
                'strength': 0.7,
                'reason': 'SMA 20 crossed above SMA 50'
            })
        elif sma_20.iloc[-1] < sma_50.iloc[-1] and sma_20.iloc[-2] >= sma_50.iloc[-2]:
            signals['signals'].append({
                'type': 'SELL',
                'indicator': 'MA_CROSSOVER',
                'strength': 0.7,
                'reason': 'SMA 20 crossed below SMA 50'
            })
        
        # Bollinger Bands
        bb_upper, bb_middle, bb_lower = self.indicators.bollinger_bands(data['Close'])
        current_price = data['Close'].iloc[-1]
        
        if current_price <= bb_lower.iloc[-1]:
            signals['signals'].append({
                'type': 'BUY',
                'indicator': 'BOLLINGER_BANDS',
                'strength': 0.6,
                'reason': 'Price touched lower Bollinger Band'
            })
        elif current_price >= bb_upper.iloc[-1]:
            signals['signals'].append({
                'type': 'SELL',
                'indicator': 'BOLLINGER_BANDS',
                'strength': 0.6,
                'reason': 'Price touched upper Bollinger Band'
            })
        
        # MACD
        macd_line, signal_line, histogram = self.indicators.macd(data['Close'])
        
        if macd_line.iloc[-1] > signal_line.iloc[-1] and macd_line.iloc[-2] <= signal_line.iloc[-2]:
            signals['signals'].append({
                'type': 'BUY',
                'indicator': 'MACD',
                'strength': 0.7,
                'reason': 'MACD line crossed above signal line'
            })
        elif macd_line.iloc[-1] < signal_line.iloc[-1] and macd_line.iloc[-2] >= signal_line.iloc[-2]:
            signals['signals'].append({
                'type': 'SELL',
                'indicator': 'MACD',
                'strength': 0.7,
                'reason': 'MACD line crossed below signal line'
            })
        
        return signals

signal_generator = SignalGenerator()

@app.get("/")
async def root():
    return {
        "service": "market-scanner",
        "status": "operational",
        "mode": "futures",
        "timestamp": time.time(),
        "symbols_tracked": len(SYMBOLS)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "market-scanner",
        "timestamp": time.time(),
        "redis_connected": redis_client.ping()
    }

@app.get("/symbols")
async def get_symbols():
    """Get list of available symbols."""
    return {
        "symbols": SYMBOLS,
        "count": len(SYMBOLS),
        "timestamp": time.time()
    }

@app.get("/quotes/{symbol}")
async def get_quote(symbol: str):
    """Get real-time quote for a symbol."""
    try:
        # Check cache first
        cached_quote = redis_client.get(f"quote:{symbol}")
        if cached_quote:
            return json.loads(cached_quote)
        
        # Fetch from Yahoo Finance
        ticker = yf.Ticker(symbol)
        info = ticker.info
        
        quote = {
            "symbol": symbol,
            "price": info.get('currentPrice', info.get('regularMarketPrice', 0)),
            "change": info.get('regularMarketChange', 0),
            "changePercent": info.get('regularMarketChangePercent', 0),
            "volume": info.get('regularMarketVolume', 0),
            "marketCap": info.get('marketCap', 0),
            "timestamp": time.time()
        }
        
        # Cache for 30 seconds
        redis_client.setex(f"quote:{symbol}", 30, json.dumps(quote))
        
        return quote
        
    except Exception as e:
        logger.error(f"Error fetching quote for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching quote: {str(e)}")

@app.get("/historical/{symbol}")
async def get_historical_data(symbol: str, period: str = "1mo", interval: str = "1d"):
    """Get historical market data."""
    try:
        ticker = yf.Ticker(symbol)
        data = ticker.history(period=period, interval=interval)
        
        if data.empty:
            raise HTTPException(status_code=404, detail="No data found for symbol")
        
        # Convert to JSON-serializable format
        data_dict = {
            "symbol": symbol,
            "period": period,
            "interval": interval,
            "data": []
        }
        
        for index, row in data.iterrows():
            data_dict["data"].append({
                "timestamp": index.isoformat(),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume'])
            })
        
        return data_dict
        
    except Exception as e:
        logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error fetching historical data: {str(e)}")

@app.get("/signals/{symbol}")
async def get_trading_signals(symbol: str):
    """Get trading signals for a symbol."""
    try:
        # Check cache first
        cached_signals = redis_client.get(f"signals:{symbol}")
        if cached_signals:
            return json.loads(cached_signals)
        
        # Fetch historical data for analysis
        ticker = yf.Ticker(symbol)
        data = ticker.history(period="3mo", interval="1d")
        
        if data.empty:
            raise HTTPException(status_code=404, detail="No data found for symbol")
        
        # Add symbol to data attributes
        data.attrs['symbol'] = symbol
        
        # Generate signals
        signals = signal_generator.generate_signals(data)
        
        # Cache for 5 minutes
        redis_client.setex(f"signals:{symbol}", 300, json.dumps(signals))
        
        return signals
        
    except Exception as e:
        logger.error(f"Error generating signals for {symbol}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generating signals: {str(e)}")

@app.get("/scan")
async def scan_market():
    """Scan futures markets for trading opportunities."""
    try:
        # Use futures scanner for crypto futures
        results = await futures_scanner.scan_futures_markets()
        
        return {
            "scan_results": results,
            "total_symbols_scanned": len(futures_scanner.futures_symbols),
            "opportunities_found": len(results),
            "mode": "futures",
            "timestamp": time.time()
        }
        
    except Exception as e:
        logger.error(f"Error scanning market: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error scanning market: {str(e)}")

# Add futures scanning endpoint
@app.get("/scan/futures")
async def scan_futures():
    """Dedicated endpoint for futures scanning."""
    try:
        results = await futures_scanner.scan_futures_markets()
        return {
            "futures_signals": results,
            "count": len(results),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error scanning futures: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error scanning futures: {str(e)}")

# Background task to update market data
async def update_market_data():
    """Background task to continuously update market data."""
    while True:
        try:
            # Scan futures markets periodically
            await futures_scanner.scan_futures_markets()
            logger.info("Completed futures market scan")
            
            await asyncio.sleep(30)  # Wait 30 seconds before next update cycle
            
        except Exception as e:
            logger.error(f"Error in background market data update: {str(e)}")
            await asyncio.sleep(60)  # Wait longer on error

@app.on_event("startup")
async def startup_event():
    """Start background tasks."""
    asyncio.create_task(update_market_data())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
