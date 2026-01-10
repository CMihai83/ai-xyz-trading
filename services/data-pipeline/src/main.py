"""
Data Pipeline - Real-time data ingestion and processing.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio
import os
import pandas as pd
import numpy as np
import yfinance as yf
import redis
import json
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Data Pipeline",
    description="Real-time data ingestion and processing",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class DataPipeline:
    """Real-time data pipeline for market data."""
    
    def __init__(self):
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=4, decode_responses=True)
        self.data_sources = {
            'yahoo_finance': self.fetch_yahoo_finance_data,
            'alpha_vantage': self.fetch_alpha_vantage_data,
            'polygon': self.fetch_polygon_data
        }
        self.symbols = [
            'AAPL', 'GOOGL', 'MSFT', 'AMZN', 'TSLA', 'META', 'NVDA', 'NFLX',
            'SPY', 'QQQ', 'IWM', 'GLD', 'SLV', 'TLT', 'VIX'
        ]
        self.running = False
    
    async def start_pipeline(self):
        """Start the data pipeline."""
        self.running = True
        logger.info("Starting data pipeline...")
        
        # Start background tasks
        asyncio.create_task(self.real_time_data_task())
        asyncio.create_task(self.historical_data_task())
        asyncio.create_task(self.data_cleanup_task())
    
    async def stop_pipeline(self):
        """Stop the data pipeline."""
        self.running = False
        logger.info("Stopping data pipeline...")
    
    async def real_time_data_task(self):
        """Continuously fetch real-time market data."""
        while self.running:
            try:
                for symbol in self.symbols:
                    await self.fetch_and_store_real_time_data(symbol)
                    await asyncio.sleep(1)  # Rate limiting
                
                await asyncio.sleep(30)  # Wait 30 seconds before next cycle
                
            except Exception as e:
                logger.error(f"Error in real-time data task: {str(e)}")
                await asyncio.sleep(60)
    
    async def historical_data_task(self):
        """Fetch and update historical data."""
        while self.running:
            try:
                for symbol in self.symbols:
                    await self.fetch_and_store_historical_data(symbol)
                    await asyncio.sleep(5)  # Rate limiting
                
                await asyncio.sleep(3600)  # Update every hour
                
            except Exception as e:
                logger.error(f"Error in historical data task: {str(e)}")
                await asyncio.sleep(1800)  # Wait 30 minutes on error
    
    async def data_cleanup_task(self):
        """Clean up old data to manage storage."""
        while self.running:
            try:
                await self.cleanup_old_data()
                await asyncio.sleep(3600)  # Run every hour
                
            except Exception as e:
                logger.error(f"Error in data cleanup task: {str(e)}")
                await asyncio.sleep(3600)
    
    async def fetch_and_store_real_time_data(self, symbol: str):
        """Fetch and store real-time data for a symbol."""
        try:
            # Fetch current quote
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            real_time_data = {
                'symbol': symbol,
                'price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                'change': info.get('regularMarketChange', 0),
                'change_percent': info.get('regularMarketChangePercent', 0),
                'volume': info.get('regularMarketVolume', 0),
                'bid': info.get('bid', 0),
                'ask': info.get('ask', 0),
                'bid_size': info.get('bidSize', 0),
                'ask_size': info.get('askSize', 0),
                'market_cap': info.get('marketCap', 0),
                'timestamp': datetime.now().isoformat()
            }
            
            # Store in Redis with expiration
            key = f"realtime:{symbol}"
            self.redis_client.setex(key, 300, json.dumps(real_time_data))  # 5 minute expiration
            
            # Also store in time series for charts
            ts_key = f"timeseries:{symbol}:{datetime.now().strftime('%Y%m%d')}"
            self.redis_client.lpush(ts_key, json.dumps(real_time_data))
            self.redis_client.expire(ts_key, 86400)  # 24 hour expiration
            
            # Keep only last 1000 entries per day
            self.redis_client.ltrim(ts_key, 0, 999)
            
        except Exception as e:
            logger.error(f"Error fetching real-time data for {symbol}: {str(e)}")
    
    async def fetch_and_store_historical_data(self, symbol: str):
        """Fetch and store historical data for a symbol."""
        try:
            ticker = yf.Ticker(symbol)
            
            # Fetch different timeframes
            timeframes = {
                '1d': '1y',    # 1 day bars for 1 year
                '1h': '1mo',   # 1 hour bars for 1 month
                '5m': '5d'     # 5 minute bars for 5 days
            }
            
            for interval, period in timeframes.items():
                df = ticker.history(period=period, interval=interval)
                
                if not df.empty:
                    # Convert to JSON format
                    historical_data = []
                    for index, row in df.iterrows():
                        historical_data.append({
                            'timestamp': index.isoformat(),
                            'open': float(row['Open']),
                            'high': float(row['High']),
                            'low': float(row['Low']),
                            'close': float(row['Close']),
                            'volume': int(row['Volume'])
                        })
                    
                    # Store in Redis
                    key = f"historical:{symbol}:{interval}"
                    self.redis_client.setex(key, 3600, json.dumps(historical_data))  # 1 hour expiration
                    
                    logger.info(f"Updated historical data for {symbol} ({interval}): {len(historical_data)} bars")
        
        except Exception as e:
            logger.error(f"Error fetching historical data for {symbol}: {str(e)}")
    
    async def fetch_yahoo_finance_data(self, symbol: str, period: str = "1d") -> Dict:
        """Fetch data from Yahoo Finance."""
        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period)
            
            if df.empty:
                return {}
            
            latest = df.iloc[-1]
            return {
                'source': 'yahoo_finance',
                'symbol': symbol,
                'price': float(latest['Close']),
                'volume': int(latest['Volume']),
                'high': float(latest['High']),
                'low': float(latest['Low']),
                'open': float(latest['Open']),
                'timestamp': df.index[-1].isoformat()
            }
            
        except Exception as e:
            logger.error(f"Yahoo Finance fetch error for {symbol}: {str(e)}")
            return {}
    
    async def fetch_alpha_vantage_data(self, symbol: str) -> Dict:
        """Fetch data from Alpha Vantage (placeholder)."""
        # Placeholder for Alpha Vantage integration
        return {
            'source': 'alpha_vantage',
            'symbol': symbol,
            'status': 'not_implemented'
        }
    
    async def fetch_polygon_data(self, symbol: str) -> Dict:
        """Fetch data from Polygon.io (placeholder)."""
        # Placeholder for Polygon.io integration
        return {
            'source': 'polygon',
            'symbol': symbol,
            'status': 'not_implemented'
        }
    
    async def get_real_time_data(self, symbol: str) -> Optional[Dict]:
        """Get real-time data for a symbol."""
        try:
            key = f"realtime:{symbol}"
            data = self.redis_client.get(key)
            
            if data:
                return json.loads(data)
            else:
                # Fetch fresh data if not in cache
                await self.fetch_and_store_real_time_data(symbol)
                data = self.redis_client.get(key)
                return json.loads(data) if data else None
                
        except Exception as e:
            logger.error(f"Error getting real-time data for {symbol}: {str(e)}")
            return None
    
    async def get_historical_data(self, symbol: str, interval: str = "1d") -> Optional[List[Dict]]:
        """Get historical data for a symbol."""
        try:
            key = f"historical:{symbol}:{interval}"
            data = self.redis_client.get(key)
            
            if data:
                return json.loads(data)
            else:
                # Fetch fresh data if not in cache
                await self.fetch_and_store_historical_data(symbol)
                data = self.redis_client.get(key)
                return json.loads(data) if data else []
                
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {str(e)}")
            return []
    
    async def get_time_series_data(self, symbol: str, date: str = None) -> List[Dict]:
        """Get intraday time series data for a symbol."""
        try:
            if not date:
                date = datetime.now().strftime('%Y%m%d')
            
            key = f"timeseries:{symbol}:{date}"
            data = self.redis_client.lrange(key, 0, -1)
            
            return [json.loads(item) for item in data]
            
        except Exception as e:
            logger.error(f"Error getting time series data for {symbol}: {str(e)}")
            return []
    
    async def cleanup_old_data(self):
        """Clean up old data from Redis."""
        try:
            # Get all keys
            all_keys = self.redis_client.keys("*")
            
            # Clean up old time series data (older than 7 days)
            cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
            
            for key in all_keys:
                if key.startswith('timeseries:') and key.split(':')[-1] < cutoff_date:
                    self.redis_client.delete(key)
                    logger.info(f"Deleted old time series data: {key}")
            
        except Exception as e:
            logger.error(f"Error cleaning up old data: {str(e)}")
    
    async def get_pipeline_status(self) -> Dict:
        """Get data pipeline status."""
        try:
            # Count cached symbols
            realtime_keys = self.redis_client.keys("realtime:*")
            historical_keys = self.redis_client.keys("historical:*")
            timeseries_keys = self.redis_client.keys("timeseries:*")
            
            # Get memory usage
            memory_info = self.redis_client.info('memory')
            
            return {
                'running': self.running,
                'symbols_tracked': len(self.symbols),
                'realtime_cached': len(realtime_keys),
                'historical_cached': len(historical_keys),
                'timeseries_cached': len(timeseries_keys),
                'memory_used_mb': memory_info.get('used_memory', 0) / 1024 / 1024,
                'data_sources': list(self.data_sources.keys()),
                'last_update': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting pipeline status: {str(e)}")
            return {'error': str(e)}

# Initialize data pipeline
data_pipeline = DataPipeline()

@app.on_event("startup")
async def startup_event():
    """Start data pipeline on startup."""
    await data_pipeline.start_pipeline()

@app.on_event("shutdown")
async def shutdown_event():
    """Stop data pipeline on shutdown."""
    await data_pipeline.stop_pipeline()

@app.get("/")
async def root():
    return {
        "service": "data-pipeline",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "symbols_tracked": len(data_pipeline.symbols)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "data-pipeline",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/status")
async def get_pipeline_status():
    """Get data pipeline status."""
    try:
        status = await data_pipeline.get_pipeline_status()
        return status
    except Exception as e:
        logger.error(f"Error getting pipeline status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting pipeline status: {str(e)}")

@app.get("/data/realtime/{symbol}")
async def get_real_time_data(symbol: str):
    """Get real-time data for a symbol."""
    try:
        data = await data_pipeline.get_real_time_data(symbol.upper())
        if data:
            return data
        else:
            raise HTTPException(status_code=404, detail=f"No real-time data found for {symbol}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting real-time data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting real-time data: {str(e)}")

@app.get("/data/historical/{symbol}")
async def get_historical_data(symbol: str, interval: str = "1d"):
    """Get historical data for a symbol."""
    try:
        data = await data_pipeline.get_historical_data(symbol.upper(), interval)
        return {
            "symbol": symbol,
            "interval": interval,
            "data": data,
            "count": len(data),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting historical data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting historical data: {str(e)}")

@app.get("/data/timeseries/{symbol}")
async def get_time_series_data(symbol: str, date: str = None):
    """Get intraday time series data for a symbol."""
    try:
        data = await data_pipeline.get_time_series_data(symbol.upper(), date)
        return {
            "symbol": symbol,
            "date": date or datetime.now().strftime('%Y%m%d'),
            "data": data,
            "count": len(data),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting time series data: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting time series data: {str(e)}")

@app.get("/symbols")
async def get_tracked_symbols():
    """Get list of tracked symbols."""
    return {
        "symbols": data_pipeline.symbols,
        "count": len(data_pipeline.symbols),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/symbols/{symbol}")
async def add_symbol(symbol: str):
    """Add a symbol to tracking."""
    try:
        symbol = symbol.upper()
        if symbol not in data_pipeline.symbols:
            data_pipeline.symbols.append(symbol)
            # Immediately fetch data for the new symbol
            await data_pipeline.fetch_and_store_real_time_data(symbol)
            await data_pipeline.fetch_and_store_historical_data(symbol)
            
        return {
            "message": f"Symbol {symbol} added to tracking",
            "symbols": data_pipeline.symbols,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error adding symbol: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error adding symbol: {str(e)}")

@app.delete("/symbols/{symbol}")
async def remove_symbol(symbol: str):
    """Remove a symbol from tracking."""
    try:
        symbol = symbol.upper()
        if symbol in data_pipeline.symbols:
            data_pipeline.symbols.remove(symbol)
            
        return {
            "message": f"Symbol {symbol} removed from tracking",
            "symbols": data_pipeline.symbols,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error removing symbol: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error removing symbol: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
