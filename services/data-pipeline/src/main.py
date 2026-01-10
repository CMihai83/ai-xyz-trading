"""
Data Pipeline - Real-time data ingestion using Bitget API
Supports: Crypto, Tokenized Stocks, RWAs (Gold/Silver)
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio
import os
import aiohttp
import hmac
import hashlib
import base64
import time
import redis
import json
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Data Pipeline - Bitget API",
    description="Real-time data ingestion for Crypto, Stocks, and RWAs via Bitget",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class BitgetDataPipeline:
    """
    Real-time data pipeline using Bitget Spot API V2.
    Supports: Crypto, Tokenized Stocks, RWAs (Gold/Silver)
    """

    # Bitget API endpoints
    BASE_URL = "https://api.bitget.com"

    # Asset categories with Bitget symbols
    CRYPTO_SYMBOLS = [
        "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT",
        "DOGEUSDT", "LINKUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
        "LTCUSDT", "UNIUSDT", "ATOMUSDT", "NEARUSDT", "AAVEUSDT"
    ]

    # Tokenized Stocks (via xStock/Ondo on Bitget)
    STOCK_SYMBOLS = [
        "NVDAUSDT",   # NVIDIA
        "TSLAUSDT",   # Tesla
        "AAPLUSDT",   # Apple
        "MSFTUSDT",   # Microsoft
        "AMZNUSDT",   # Amazon
        "GOOGLAUSDT", # Google
        "METAUSDT",   # Meta
        "NFLXUSDT",   # Netflix
        "AMDUSDT",    # AMD
        "INTCUSDT",   # Intel
    ]

    # RWAs - Real World Assets (Gold, Silver, etc.)
    RWA_SYMBOLS = [
        "XAUTUSDT",   # Tether Gold (tokenized gold)
        "PAXGUSDT",   # Paxos Gold
        "XAGUSDT",    # Tokenized Silver (if available)
    ]

    def __init__(self):
        # Redis connection
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=4, decode_responses=True)

        # API credentials (optional - for private endpoints)
        self.api_key = os.getenv('BITGET_API_KEY', '')
        self.api_secret = os.getenv('BITGET_API_SECRET', '')
        self.api_passphrase = os.getenv('BITGET_API_PASSPHRASE', '')

        # Combine all symbols
        self.symbols = {
            'crypto': self.CRYPTO_SYMBOLS,
            'stocks': self.STOCK_SYMBOLS,
            'rwa': self.RWA_SYMBOLS
        }
        self.all_symbols = self.CRYPTO_SYMBOLS + self.STOCK_SYMBOLS + self.RWA_SYMBOLS

        # Available symbols cache (validated against Bitget)
        self.available_symbols = set()

        self.running = False
        self.session: Optional[aiohttp.ClientSession] = None

        logger.info(f"BitgetDataPipeline initialized with {len(self.all_symbols)} symbols")

    async def create_session(self):
        """Create aiohttp session."""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close_session(self):
        """Close aiohttp session."""
        if self.session:
            await self.session.close()
            self.session = None

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Generate HMAC SHA256 signature for authenticated requests."""
        message = timestamp + method + request_path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode()

    def _get_headers(self, method: str = "GET", request_path: str = "", body: str = "") -> Dict:
        """Get headers for API request."""
        timestamp = str(int(time.time() * 1000))
        headers = {
            "Content-Type": "application/json",
            "locale": "en-US"
        }

        # Add authentication if credentials available
        if self.api_key and self.api_secret:
            headers.update({
                "ACCESS-KEY": self.api_key,
                "ACCESS-SIGN": self._generate_signature(timestamp, method, request_path, body),
                "ACCESS-TIMESTAMP": timestamp,
                "ACCESS-PASSPHRASE": self.api_passphrase
            })

        return headers

    async def fetch_available_symbols(self) -> List[str]:
        """Fetch all available spot symbols from Bitget."""
        try:
            url = f"{self.BASE_URL}/api/v2/spot/public/symbols"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '00000':
                        symbols = [item['symbol'] for item in data.get('data', [])]
                        self.available_symbols = set(symbols)
                        logger.info(f"Fetched {len(symbols)} available symbols from Bitget")
                        return symbols

            return []
        except Exception as e:
            logger.error(f"Error fetching available symbols: {e}")
            return []

    async def fetch_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Fetch real-time ticker data for a symbol.
        GET /api/v2/spot/market/tickers
        """
        try:
            url = f"{self.BASE_URL}/api/v2/spot/market/tickers"
            params = {"symbol": symbol}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '00000' and data.get('data'):
                        ticker = data['data'][0] if isinstance(data['data'], list) else data['data']
                        return {
                            'symbol': symbol,
                            'price': float(ticker.get('lastPr', 0)),
                            'open24h': float(ticker.get('open', 0)),
                            'high24h': float(ticker.get('high24h', 0)),
                            'low24h': float(ticker.get('low24h', 0)),
                            'volume24h': float(ticker.get('baseVolume', 0)),
                            'quoteVolume24h': float(ticker.get('quoteVolume', 0)),
                            'change24h': float(ticker.get('change24h', 0)),
                            'changePercent24h': float(ticker.get('changeUtc24h', 0)),
                            'bid': float(ticker.get('bidPr', 0)),
                            'ask': float(ticker.get('askPr', 0)),
                            'timestamp': ticker.get('ts', str(int(time.time() * 1000))),
                            'source': 'bitget'
                        }
                elif response.status == 429:
                    logger.warning(f"Rate limited for {symbol}, waiting...")
                    await asyncio.sleep(5)

            return None
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None

    async def fetch_all_tickers(self) -> List[Dict]:
        """Fetch all tickers at once (more efficient)."""
        try:
            url = f"{self.BASE_URL}/api/v2/spot/market/tickers"

            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '00000':
                        tickers = []
                        for ticker in data.get('data', []):
                            symbol = ticker.get('symbol', '')
                            if symbol in self.all_symbols or symbol.replace('USDT', '') in [s.replace('USDT', '') for s in self.all_symbols]:
                                tickers.append({
                                    'symbol': symbol,
                                    'price': float(ticker.get('lastPr', 0)),
                                    'open24h': float(ticker.get('open', 0)),
                                    'high24h': float(ticker.get('high24h', 0)),
                                    'low24h': float(ticker.get('low24h', 0)),
                                    'volume24h': float(ticker.get('baseVolume', 0)),
                                    'quoteVolume24h': float(ticker.get('quoteVolume', 0)),
                                    'change24h': float(ticker.get('change24h', 0)),
                                    'changePercent24h': float(ticker.get('changeUtc24h', 0)),
                                    'bid': float(ticker.get('bidPr', 0)),
                                    'ask': float(ticker.get('askPr', 0)),
                                    'timestamp': ticker.get('ts', str(int(time.time() * 1000))),
                                    'source': 'bitget'
                                })
                        return tickers
            return []
        except Exception as e:
            logger.error(f"Error fetching all tickers: {e}")
            return []

    async def fetch_candles(self, symbol: str, granularity: str = "1H", limit: int = 100) -> List[Dict]:
        """
        Fetch historical candle data.
        GET /api/v2/spot/market/candles

        Granularity options: 1min, 5min, 15min, 30min, 1H, 4H, 1D, 1W
        """
        try:
            url = f"{self.BASE_URL}/api/v2/spot/market/candles"
            params = {
                "symbol": symbol,
                "granularity": granularity,
                "limit": str(limit)
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '00000':
                        candles = []
                        for candle in data.get('data', []):
                            # Bitget returns: [ts, open, high, low, close, volume, quoteVolume]
                            candles.append({
                                'timestamp': candle[0],
                                'open': float(candle[1]),
                                'high': float(candle[2]),
                                'low': float(candle[3]),
                                'close': float(candle[4]),
                                'volume': float(candle[5]),
                                'quoteVolume': float(candle[6]) if len(candle) > 6 else 0
                            })
                        return candles
            return []
        except Exception as e:
            logger.error(f"Error fetching candles for {symbol}: {e}")
            return []

    async def fetch_orderbook(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """
        Fetch order book depth.
        GET /api/v2/spot/market/orderbook
        """
        try:
            url = f"{self.BASE_URL}/api/v2/spot/market/orderbook"
            params = {
                "symbol": symbol,
                "limit": str(limit)
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '00000':
                        book = data.get('data', {})
                        return {
                            'symbol': symbol,
                            'bids': [[float(b[0]), float(b[1])] for b in book.get('bids', [])],
                            'asks': [[float(a[0]), float(a[1])] for a in book.get('asks', [])],
                            'timestamp': book.get('ts', str(int(time.time() * 1000)))
                        }
            return None
        except Exception as e:
            logger.error(f"Error fetching orderbook for {symbol}: {e}")
            return None

    async def fetch_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """
        Fetch recent trades.
        GET /api/v2/spot/market/fills
        """
        try:
            url = f"{self.BASE_URL}/api/v2/spot/market/fills"
            params = {
                "symbol": symbol,
                "limit": str(limit)
            }

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data.get('code') == '00000':
                        trades = []
                        for trade in data.get('data', []):
                            trades.append({
                                'tradeId': trade.get('tradeId'),
                                'price': float(trade.get('price', 0)),
                                'size': float(trade.get('size', 0)),
                                'side': trade.get('side'),
                                'timestamp': trade.get('ts')
                            })
                        return trades
            return []
        except Exception as e:
            logger.error(f"Error fetching trades for {symbol}: {e}")
            return []

    async def start_pipeline(self):
        """Start the data pipeline."""
        self.running = True
        await self.create_session()

        # Fetch available symbols first
        await self.fetch_available_symbols()

        logger.info("Starting Bitget data pipeline...")
        logger.info(f"  Crypto: {len(self.CRYPTO_SYMBOLS)} symbols")
        logger.info(f"  Stocks: {len(self.STOCK_SYMBOLS)} symbols")
        logger.info(f"  RWAs: {len(self.RWA_SYMBOLS)} symbols")

        # Start background tasks
        asyncio.create_task(self.real_time_data_task())
        asyncio.create_task(self.historical_data_task())
        asyncio.create_task(self.data_cleanup_task())

    async def stop_pipeline(self):
        """Stop the data pipeline."""
        self.running = False
        await self.close_session()
        logger.info("Stopped Bitget data pipeline")

    async def real_time_data_task(self):
        """Continuously fetch real-time market data."""
        while self.running:
            try:
                # Fetch all tickers at once (efficient)
                tickers = await self.fetch_all_tickers()

                for ticker in tickers:
                    symbol = ticker['symbol']

                    # Categorize the asset
                    category = 'crypto'
                    if symbol in self.STOCK_SYMBOLS or any(s in symbol for s in ['NVDA', 'TSLA', 'AAPL', 'MSFT', 'AMZN', 'GOOGL', 'META', 'NFLX', 'AMD', 'INTC']):
                        category = 'stocks'
                    elif symbol in self.RWA_SYMBOLS or any(s in symbol for s in ['XAU', 'PAXG', 'XAG']):
                        category = 'rwa'

                    ticker['category'] = category

                    # Store in Redis
                    key = f"realtime:{symbol}"
                    self.redis_client.setex(key, 300, json.dumps(ticker))

                    # Store in time series
                    ts_key = f"timeseries:{symbol}:{datetime.now().strftime('%Y%m%d')}"
                    self.redis_client.lpush(ts_key, json.dumps(ticker))
                    self.redis_client.expire(ts_key, 86400)
                    self.redis_client.ltrim(ts_key, 0, 999)

                logger.info(f"Updated {len(tickers)} tickers from Bitget")
                await asyncio.sleep(30)  # Update every 30 seconds

            except Exception as e:
                logger.error(f"Error in real-time data task: {e}")
                await asyncio.sleep(60)

    async def historical_data_task(self):
        """Fetch and update historical data."""
        while self.running:
            try:
                for symbol in self.all_symbols:
                    # Check if symbol exists on Bitget
                    if self.available_symbols and symbol not in self.available_symbols:
                        continue

                    # Fetch different timeframes
                    timeframes = {
                        '1D': 100,   # Daily candles
                        '1H': 100,   # Hourly candles
                        '15min': 100  # 15-minute candles
                    }

                    for granularity, limit in timeframes.items():
                        candles = await self.fetch_candles(symbol, granularity, limit)

                        if candles:
                            key = f"historical:{symbol}:{granularity}"
                            self.redis_client.setex(key, 3600, json.dumps(candles))
                            logger.debug(f"Updated {symbol} {granularity}: {len(candles)} candles")

                        await asyncio.sleep(0.5)  # Rate limiting

                    await asyncio.sleep(1)  # Between symbols

                await asyncio.sleep(3600)  # Update hourly

            except Exception as e:
                logger.error(f"Error in historical data task: {e}")
                await asyncio.sleep(1800)

    async def data_cleanup_task(self):
        """Clean up old data from Redis."""
        while self.running:
            try:
                await asyncio.sleep(3600)

                all_keys = self.redis_client.keys("timeseries:*")
                cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')

                deleted = 0
                for key in all_keys:
                    parts = key.split(':')
                    if len(parts) >= 3 and parts[-1] < cutoff_date:
                        self.redis_client.delete(key)
                        deleted += 1

                if deleted:
                    logger.info(f"Cleaned up {deleted} old time series keys")

            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(3600)

    async def get_real_time_data(self, symbol: str) -> Optional[Dict]:
        """Get real-time data for a symbol."""
        try:
            key = f"realtime:{symbol}"
            data = self.redis_client.get(key)

            if data:
                return json.loads(data)

            # Fetch fresh if not cached
            ticker = await self.fetch_ticker(symbol)
            if ticker:
                self.redis_client.setex(key, 300, json.dumps(ticker))
            return ticker

        except Exception as e:
            logger.error(f"Error getting real-time data for {symbol}: {e}")
            return None

    async def get_historical_data(self, symbol: str, granularity: str = "1D") -> List[Dict]:
        """Get historical data for a symbol."""
        try:
            key = f"historical:{symbol}:{granularity}"
            data = self.redis_client.get(key)

            if data:
                return json.loads(data)

            # Fetch fresh if not cached
            candles = await self.fetch_candles(symbol, granularity)
            if candles:
                self.redis_client.setex(key, 3600, json.dumps(candles))
            return candles

        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return []

    async def get_time_series_data(self, symbol: str, date: str = None) -> List[Dict]:
        """Get intraday time series data."""
        try:
            if not date:
                date = datetime.now().strftime('%Y%m%d')

            key = f"timeseries:{symbol}:{date}"
            data = self.redis_client.lrange(key, 0, -1)

            return [json.loads(item) for item in data]

        except Exception as e:
            logger.error(f"Error getting time series for {symbol}: {e}")
            return []

    async def get_pipeline_status(self) -> Dict:
        """Get pipeline status."""
        try:
            realtime_keys = self.redis_client.keys("realtime:*")
            historical_keys = self.redis_client.keys("historical:*")
            timeseries_keys = self.redis_client.keys("timeseries:*")
            memory_info = self.redis_client.info('memory')

            return {
                'running': self.running,
                'source': 'bitget',
                'symbols': {
                    'crypto': len(self.CRYPTO_SYMBOLS),
                    'stocks': len(self.STOCK_SYMBOLS),
                    'rwa': len(self.RWA_SYMBOLS),
                    'total': len(self.all_symbols)
                },
                'available_on_exchange': len(self.available_symbols),
                'cached': {
                    'realtime': len(realtime_keys),
                    'historical': len(historical_keys),
                    'timeseries': len(timeseries_keys)
                },
                'memory_used_mb': memory_info.get('used_memory', 0) / 1024 / 1024,
                'last_update': datetime.now().isoformat()
            }

        except Exception as e:
            logger.error(f"Error getting pipeline status: {e}")
            return {'error': str(e)}

    def get_symbols_by_category(self, category: str) -> List[str]:
        """Get symbols by category."""
        return self.symbols.get(category, [])


# Initialize pipeline
data_pipeline = BitgetDataPipeline()


@app.on_event("startup")
async def startup_event():
    """Start pipeline on startup."""
    await data_pipeline.start_pipeline()


@app.on_event("shutdown")
async def shutdown_event():
    """Stop pipeline on shutdown."""
    await data_pipeline.stop_pipeline()


@app.get("/")
async def root():
    return {
        "service": "data-pipeline",
        "version": "2.0.0",
        "source": "bitget",
        "status": "operational",
        "assets": {
            "crypto": len(data_pipeline.CRYPTO_SYMBOLS),
            "stocks": len(data_pipeline.STOCK_SYMBOLS),
            "rwa": len(data_pipeline.RWA_SYMBOLS)
        },
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "data-pipeline",
        "source": "bitget",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/status")
async def get_pipeline_status():
    """Get pipeline status."""
    try:
        return await data_pipeline.get_pipeline_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/symbols")
async def get_symbols():
    """Get all tracked symbols by category."""
    return {
        "crypto": data_pipeline.CRYPTO_SYMBOLS,
        "stocks": data_pipeline.STOCK_SYMBOLS,
        "rwa": data_pipeline.RWA_SYMBOLS,
        "all": data_pipeline.all_symbols,
        "count": len(data_pipeline.all_symbols),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/symbols/{category}")
async def get_symbols_by_category(category: str):
    """Get symbols by category (crypto, stocks, rwa)."""
    symbols = data_pipeline.get_symbols_by_category(category)
    if not symbols:
        raise HTTPException(status_code=404, detail=f"Category '{category}' not found")
    return {
        "category": category,
        "symbols": symbols,
        "count": len(symbols),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/data/realtime/{symbol}")
async def get_real_time_data(symbol: str):
    """Get real-time ticker data for a symbol."""
    try:
        data = await data_pipeline.get_real_time_data(symbol.upper())
        if data:
            return data
        raise HTTPException(status_code=404, detail=f"No data found for {symbol}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/data/historical/{symbol}")
async def get_historical_data(symbol: str, granularity: str = "1D"):
    """Get historical candle data for a symbol."""
    try:
        data = await data_pipeline.get_historical_data(symbol.upper(), granularity)
        return {
            "symbol": symbol.upper(),
            "granularity": granularity,
            "data": data,
            "count": len(data),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/data/timeseries/{symbol}")
async def get_time_series_data(symbol: str, date: str = None):
    """Get intraday time series data."""
    try:
        data = await data_pipeline.get_time_series_data(symbol.upper(), date)
        return {
            "symbol": symbol.upper(),
            "date": date or datetime.now().strftime('%Y%m%d'),
            "data": data,
            "count": len(data),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/data/orderbook/{symbol}")
async def get_orderbook(symbol: str, limit: int = 20):
    """Get order book for a symbol."""
    try:
        data = await data_pipeline.fetch_orderbook(symbol.upper(), limit)
        if data:
            return data
        raise HTTPException(status_code=404, detail=f"No orderbook found for {symbol}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/data/trades/{symbol}")
async def get_trades(symbol: str, limit: int = 100):
    """Get recent trades for a symbol."""
    try:
        data = await data_pipeline.fetch_recent_trades(symbol.upper(), limit)
        return {
            "symbol": symbol.upper(),
            "trades": data,
            "count": len(data),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/symbols/{symbol}")
async def add_symbol(symbol: str, category: str = "crypto"):
    """Add a symbol to tracking."""
    try:
        symbol = symbol.upper()
        if category == "crypto":
            if symbol not in data_pipeline.CRYPTO_SYMBOLS:
                data_pipeline.CRYPTO_SYMBOLS.append(symbol)
        elif category == "stocks":
            if symbol not in data_pipeline.STOCK_SYMBOLS:
                data_pipeline.STOCK_SYMBOLS.append(symbol)
        elif category == "rwa":
            if symbol not in data_pipeline.RWA_SYMBOLS:
                data_pipeline.RWA_SYMBOLS.append(symbol)

        data_pipeline.all_symbols = (
            data_pipeline.CRYPTO_SYMBOLS +
            data_pipeline.STOCK_SYMBOLS +
            data_pipeline.RWA_SYMBOLS
        )

        return {
            "message": f"Symbol {symbol} added to {category}",
            "symbols": data_pipeline.get_symbols_by_category(category),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/symbols/{symbol}")
async def remove_symbol(symbol: str):
    """Remove a symbol from tracking."""
    try:
        symbol = symbol.upper()
        for category in ['CRYPTO_SYMBOLS', 'STOCK_SYMBOLS', 'RWA_SYMBOLS']:
            symbols_list = getattr(data_pipeline, category)
            if symbol in symbols_list:
                symbols_list.remove(symbol)

        data_pipeline.all_symbols = (
            data_pipeline.CRYPTO_SYMBOLS +
            data_pipeline.STOCK_SYMBOLS +
            data_pipeline.RWA_SYMBOLS
        )

        return {
            "message": f"Symbol {symbol} removed",
            "total_symbols": len(data_pipeline.all_symbols),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
