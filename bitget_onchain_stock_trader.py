#!/usr/bin/env python3
"""
Bitget Onchain Stock Trader
============================
Trades REAL tokenized stocks via Bitget's Onchain platform.

Tokenized Stock Symbols (xStocks via Bitget Onchain):
- NVDAX_USDT (NVIDIA)
- TSLAx_USDT (Tesla)
- AAPLx_USDT (Apple)
- AMZNx_USDT (Amazon)
- GOOGLx_USDT (Google/Alphabet)
- MSFTx_USDT (Microsoft)
- METAx_USDT (Meta)
- QQQx_USDT (NASDAQ-100 ETF)
- SPYx_USDT (S&P 500 ETF)
- COINx_USDT (Coinbase)

Also supports Ondo-backed tokens:
- ASMLon_USDT (ASML Holding)

API Reference:
- REST: https://api.bitget.com/api/v2/spot/...
- WebSocket: wss://ws.bitget.com/v2/ws/public

Note: Uses USDT/USDC for trading. Requires Bitget API keys with spot trading permissions.
"""

import asyncio
import hashlib
import hmac
import base64
import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
import aiohttp
import websockets
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class StockTicker:
    """Real-time ticker data for a tokenized stock"""
    symbol: str
    last_price: float
    bid: float
    ask: float
    high_24h: float
    low_24h: float
    volume_24h: float
    change_24h: float
    timestamp: int


@dataclass
class StockOrder:
    """Order result"""
    order_id: str
    symbol: str
    side: str
    order_type: str
    price: float
    quantity: float
    status: str
    filled_quantity: float = 0.0
    timestamp: int = 0


class BitgetOnchainStockTrader:
    """
    Trade tokenized stocks on Bitget's Onchain platform.

    Implements Bitget Spot Trading API V2 for xStocks.
    """

    # Base URLs
    REST_URL = "https://api.bitget.com"
    WS_PUBLIC_URL = "wss://ws.bitget.com/v2/ws/public"
    WS_PRIVATE_URL = "wss://ws.bitget.com/v2/ws/private"

    # Tokenized stock symbols (xStocks)
    TOKENIZED_STOCKS = {
        # US Tech Giants
        'NVDA': 'NVDAUSDT',      # NVIDIA Corporation
        'TSLA': 'TSLAUSDT',      # Tesla Inc
        'AAPL': 'AAPLUSDT',      # Apple Inc
        'AMZN': 'AMZNUSDT',      # Amazon.com Inc
        'GOOGL': 'GOOGLUSDT',    # Alphabet Inc (Google)
        'MSFT': 'MSFTUSDT',      # Microsoft Corporation
        'META': 'METAUSDT',      # Meta Platforms Inc
        'COIN': 'COINUSDT',      # Coinbase Global Inc
        'ASML': 'ASMUSDT',       # ASML Holding NV
        # ETFs
        'QQQ': 'QQQUSDT',        # Invesco QQQ (NASDAQ-100)
        'SPY': 'SPYUSDT',        # SPDR S&P 500 ETF
        # Precious Metals (tokenized)
        'XAU': 'XAUUSDT',        # Gold
        'XAG': 'XAGUSDT',        # Silver
    }

    # Alternative symbol formats (xStock format)
    XSTOCK_SYMBOLS = {
        'NVDAX': 'NVDAX_USDT',
        'TSLAx': 'TSLAx_USDT',
        'AAPLx': 'AAPLx_USDT',
        'AMZNx': 'AMZNx_USDT',
        'GOOGLx': 'GOOGLx_USDT',
        'MSFTx': 'MSFTx_USDT',
        'METAx': 'METAx_USDT',
        'QQQx': 'QQQx_USDT',
        'SPYx': 'SPYx_USDT',
    }

    def __init__(
        self,
        api_key: str = None,
        api_secret: str = None,
        passphrase: str = None,
        demo_mode: bool = False
    ):
        """
        Initialize the Bitget Onchain Stock Trader.

        Args:
            api_key: Bitget API key (or from env BITGET_API_KEY)
            api_secret: Bitget API secret (or from env BITGET_API_SECRET)
            passphrase: Bitget API passphrase (or from env BITGET_API_PASSPHRASE)
            demo_mode: Use demo environment for testing
        """
        self.api_key = api_key or os.getenv('BITGET_API_KEY')
        self.api_secret = api_secret or os.getenv('BITGET_API_SECRET')
        self.passphrase = passphrase or os.getenv('BITGET_API_PASSPHRASE')

        if demo_mode:
            self.REST_URL = "https://demo-api.bitget.com"

        self._session: Optional[aiohttp.ClientSession] = None
        self._ws_connection = None
        self._ws_callbacks: Dict[str, Callable] = {}
        self._available_symbols: Dict[str, dict] = {}

        logger.info(f"BitgetOnchainStockTrader initialized (demo={demo_mode})")

    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """Generate HMAC-SHA256 signature for API authentication."""
        message = timestamp + method.upper() + request_path + body
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
        return base64.b64encode(signature).decode('utf-8')

    def _get_headers(self, method: str, request_path: str, body: str = '') -> dict:
        """Generate authenticated headers for API requests."""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, request_path, body)

        return {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json',
            'locale': 'en-US'
        }

    async def _ensure_session(self):
        """Ensure aiohttp session is created."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()

    async def close(self):
        """Close all connections."""
        if self._session and not self._session.closed:
            await self._session.close()
        if self._ws_connection:
            await self._ws_connection.close()

    # =========================================================================
    # PUBLIC ENDPOINTS (No Authentication Required)
    # =========================================================================

    async def get_symbols(self, filter_stocks: bool = True) -> List[dict]:
        """
        Get all available spot trading symbols.

        Args:
            filter_stocks: If True, only return tokenized stocks/metals

        Returns:
            List of symbol info dictionaries
        """
        await self._ensure_session()

        url = f"{self.REST_URL}/api/v2/spot/public/symbols"

        async with self._session.get(url) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"API Error: {data.get('msg')}")

            symbols = data.get('data', [])

            if filter_stocks:
                # Filter for tokenized stocks and metals
                stock_bases = list(self.TOKENIZED_STOCKS.keys()) + ['XAUT', 'PAXG']
                symbols = [s for s in symbols if s.get('baseCoin') in stock_bases]

            # Cache available symbols
            for s in symbols:
                self._available_symbols[s.get('symbol')] = s

            return symbols

    async def get_ticker(self, symbol: str) -> StockTicker:
        """
        Get real-time ticker data for a tokenized stock.

        Args:
            symbol: Trading symbol (e.g., 'NVDAUSDT' or 'NVDA')

        Returns:
            StockTicker with current market data
        """
        await self._ensure_session()

        # Normalize symbol
        if symbol in self.TOKENIZED_STOCKS:
            symbol = self.TOKENIZED_STOCKS[symbol]

        url = f"{self.REST_URL}/api/v2/spot/market/tickers"
        params = {'symbol': symbol}

        async with self._session.get(url, params=params) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"API Error: {data.get('msg')}")

            tickers = data.get('data', [])
            if not tickers:
                raise Exception(f"No ticker data for {symbol}")

            t = tickers[0]
            return StockTicker(
                symbol=t.get('symbol'),
                last_price=float(t.get('lastPr', 0)),
                bid=float(t.get('bidPr', 0)),
                ask=float(t.get('askPr', 0)),
                high_24h=float(t.get('high24h', 0)),
                low_24h=float(t.get('low24h', 0)),
                volume_24h=float(t.get('quoteVolume', 0)),
                change_24h=float(t.get('change24h', 0)),
                timestamp=int(t.get('ts', 0))
            )

    async def get_all_stock_tickers(self) -> Dict[str, StockTicker]:
        """
        Get tickers for all available tokenized stocks.

        Returns:
            Dictionary of symbol -> StockTicker
        """
        await self._ensure_session()

        url = f"{self.REST_URL}/api/v2/spot/market/tickers"

        async with self._session.get(url) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"API Error: {data.get('msg')}")

            tickers = {}
            stock_symbols = set(self.TOKENIZED_STOCKS.values())
            stock_symbols.update(['XAUTUSDT', 'PAXGUSDT'])  # Add gold

            for t in data.get('data', []):
                symbol = t.get('symbol')
                if symbol in stock_symbols:
                    tickers[symbol] = StockTicker(
                        symbol=symbol,
                        last_price=float(t.get('lastPr', 0)),
                        bid=float(t.get('bidPr', 0)),
                        ask=float(t.get('askPr', 0)),
                        high_24h=float(t.get('high24h', 0)),
                        low_24h=float(t.get('low24h', 0)),
                        volume_24h=float(t.get('quoteVolume', 0)),
                        change_24h=float(t.get('change24h', 0)),
                        timestamp=int(t.get('ts', 0))
                    )

            return tickers

    async def get_candles(
        self,
        symbol: str,
        granularity: str = '1D',
        limit: int = 100
    ) -> List[List]:
        """
        Get historical OHLCV candles for a tokenized stock.

        Args:
            symbol: Trading symbol
            granularity: Candle interval (1m, 5m, 15m, 1H, 4H, 1D, 1W)
            limit: Number of candles (max 1000)

        Returns:
            List of [timestamp, open, high, low, close, volume]
        """
        await self._ensure_session()

        # Normalize symbol
        if symbol in self.TOKENIZED_STOCKS:
            symbol = self.TOKENIZED_STOCKS[symbol]

        url = f"{self.REST_URL}/api/v2/spot/market/candles"
        params = {
            'symbol': symbol,
            'granularity': granularity,
            'limit': str(limit)
        }

        async with self._session.get(url, params=params) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"API Error: {data.get('msg')}")

            return data.get('data', [])

    async def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """
        Get order book depth for a tokenized stock.

        Args:
            symbol: Trading symbol
            limit: Number of levels (max 50)

        Returns:
            Dictionary with 'asks', 'bids', 'timestamp'
        """
        await self._ensure_session()

        # Normalize symbol
        if symbol in self.TOKENIZED_STOCKS:
            symbol = self.TOKENIZED_STOCKS[symbol]

        url = f"{self.REST_URL}/api/v2/spot/market/orderbook"
        params = {'symbol': symbol, 'limit': str(limit)}

        async with self._session.get(url, params=params) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"API Error: {data.get('msg')}")

            return data.get('data', {})

    # =========================================================================
    # PRIVATE ENDPOINTS (Authentication Required)
    # =========================================================================

    async def get_balance(self, coin: str = 'USDT') -> dict:
        """
        Get spot account balance.

        Args:
            coin: Coin to check (default USDT)

        Returns:
            Balance info dictionary
        """
        await self._ensure_session()

        request_path = '/api/v2/spot/account/assets'
        url = f"{self.REST_URL}{request_path}"
        params = {'coin': coin}
        query_string = f"?coin={coin}"

        headers = self._get_headers('GET', request_path + query_string)

        async with self._session.get(url, params=params, headers=headers) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"API Error: {data.get('msg')}")

            assets = data.get('data', [])
            for asset in assets:
                if asset.get('coin') == coin:
                    return {
                        'coin': coin,
                        'available': float(asset.get('available', 0)),
                        'frozen': float(asset.get('frozen', 0)),
                        'total': float(asset.get('available', 0)) + float(asset.get('frozen', 0))
                    }

            return {'coin': coin, 'available': 0, 'frozen': 0, 'total': 0}

    async def place_market_order(
        self,
        symbol: str,
        side: str,
        quantity: float = None,
        quote_amount: float = None
    ) -> StockOrder:
        """
        Place a market order for a tokenized stock.

        Args:
            symbol: Trading symbol (e.g., 'NVDA' or 'NVDAUSDT')
            side: 'buy' or 'sell'
            quantity: Amount in base currency (e.g., shares of NVDA)
            quote_amount: Amount in quote currency (e.g., USDT to spend)

        Returns:
            StockOrder with order details
        """
        # Normalize symbol
        if symbol in self.TOKENIZED_STOCKS:
            symbol = self.TOKENIZED_STOCKS[symbol]

        return await self._place_order(
            symbol=symbol,
            side=side,
            order_type='market',
            quantity=quantity,
            quote_amount=quote_amount
        )

    async def place_limit_order(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float
    ) -> StockOrder:
        """
        Place a limit order for a tokenized stock.

        Args:
            symbol: Trading symbol
            side: 'buy' or 'sell'
            price: Limit price
            quantity: Amount in base currency

        Returns:
            StockOrder with order details
        """
        # Normalize symbol
        if symbol in self.TOKENIZED_STOCKS:
            symbol = self.TOKENIZED_STOCKS[symbol]

        return await self._place_order(
            symbol=symbol,
            side=side,
            order_type='limit',
            price=price,
            quantity=quantity
        )

    async def _place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        price: float = None,
        quantity: float = None,
        quote_amount: float = None
    ) -> StockOrder:
        """Internal method to place orders."""
        await self._ensure_session()

        request_path = '/api/v2/spot/trade/place-order'
        url = f"{self.REST_URL}{request_path}"

        body = {
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'force': 'gtc'  # Good till cancelled
        }

        if order_type == 'market':
            if quote_amount:
                body['quoteSize'] = str(quote_amount)
            elif quantity:
                body['size'] = str(quantity)
        else:  # limit order
            body['price'] = str(price)
            body['size'] = str(quantity)

        body_str = json.dumps(body)
        headers = self._get_headers('POST', request_path, body_str)

        async with self._session.post(url, json=body, headers=headers) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"Order failed: {data.get('msg')}")

            order_data = data.get('data', {})
            return StockOrder(
                order_id=order_data.get('orderId', ''),
                symbol=symbol,
                side=side,
                order_type=order_type,
                price=price or 0,
                quantity=quantity or 0,
                status='submitted',
                timestamp=int(time.time() * 1000)
            )

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        await self._ensure_session()

        # Normalize symbol
        if symbol in self.TOKENIZED_STOCKS:
            symbol = self.TOKENIZED_STOCKS[symbol]

        request_path = '/api/v2/spot/trade/cancel-order'
        url = f"{self.REST_URL}{request_path}"

        body = {
            'symbol': symbol,
            'orderId': order_id
        }

        body_str = json.dumps(body)
        headers = self._get_headers('POST', request_path, body_str)

        async with self._session.post(url, json=body, headers=headers) as response:
            data = await response.json()
            return data.get('code') == '00000'

    async def get_open_orders(self, symbol: str = None) -> List[StockOrder]:
        """
        Get all open orders.

        Args:
            symbol: Optional symbol filter

        Returns:
            List of open StockOrder objects
        """
        await self._ensure_session()

        request_path = '/api/v2/spot/trade/unfilled-orders'
        params = {}

        if symbol:
            if symbol in self.TOKENIZED_STOCKS:
                symbol = self.TOKENIZED_STOCKS[symbol]
            params['symbol'] = symbol

        query_string = '?' + '&'.join(f"{k}={v}" for k, v in params.items()) if params else ''
        url = f"{self.REST_URL}{request_path}{query_string}"

        headers = self._get_headers('GET', request_path + query_string)

        async with self._session.get(url, headers=headers) as response:
            data = await response.json()

            if data.get('code') != '00000':
                raise Exception(f"API Error: {data.get('msg')}")

            orders = []
            for o in data.get('data', {}).get('orderList', []):
                orders.append(StockOrder(
                    order_id=o.get('orderId'),
                    symbol=o.get('symbol'),
                    side=o.get('side'),
                    order_type=o.get('orderType'),
                    price=float(o.get('price', 0)),
                    quantity=float(o.get('size', 0)),
                    status=o.get('status'),
                    filled_quantity=float(o.get('filledSize', 0)),
                    timestamp=int(o.get('cTime', 0))
                ))

            return orders

    # =========================================================================
    # WEBSOCKET STREAMING
    # =========================================================================

    async def subscribe_ticker(
        self,
        symbols: List[str],
        callback: Callable[[StockTicker], None]
    ):
        """
        Subscribe to real-time ticker updates via WebSocket.

        Args:
            symbols: List of symbols to subscribe
            callback: Function to call with ticker updates
        """
        # Normalize symbols
        normalized = []
        for s in symbols:
            if s in self.TOKENIZED_STOCKS:
                normalized.append(self.TOKENIZED_STOCKS[s])
            else:
                normalized.append(s)

        async with websockets.connect(self.WS_PUBLIC_URL) as ws:
            # Subscribe to tickers
            subscribe_msg = {
                "op": "subscribe",
                "args": [
                    {"instType": "SPOT", "channel": "ticker", "instId": sym}
                    for sym in normalized
                ]
            }
            await ws.send(json.dumps(subscribe_msg))

            # Keep connection alive and process messages
            while True:
                try:
                    msg = await asyncio.wait_for(ws.recv(), timeout=30)
                    data = json.loads(msg)

                    if data.get('action') == 'snapshot' or data.get('action') == 'update':
                        for tick in data.get('data', []):
                            ticker = StockTicker(
                                symbol=tick.get('instId'),
                                last_price=float(tick.get('last', 0)),
                                bid=float(tick.get('bidPr', 0)),
                                ask=float(tick.get('askPr', 0)),
                                high_24h=float(tick.get('high24h', 0)),
                                low_24h=float(tick.get('low24h', 0)),
                                volume_24h=float(tick.get('vol24h', 0)),
                                change_24h=float(tick.get('change', 0)),
                                timestamp=int(tick.get('ts', 0))
                            )
                            await callback(ticker)

                except asyncio.TimeoutError:
                    # Send ping to keep alive
                    await ws.send('ping')


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

async def main():
    """Example usage of BitgetOnchainStockTrader."""

    trader = BitgetOnchainStockTrader()

    try:
        # Get available symbols
        print("\n=== Available Tokenized Stocks ===")
        symbols = await trader.get_symbols(filter_stocks=True)
        for s in symbols[:10]:
            print(f"  {s.get('symbol')}: {s.get('baseCoin')}/{s.get('quoteCoin')}")

        # Get ticker for NVIDIA
        print("\n=== NVIDIA Ticker ===")
        try:
            ticker = await trader.get_ticker('NVDA')
            print(f"  Symbol: {ticker.symbol}")
            print(f"  Price: ${ticker.last_price:.2f}")
            print(f"  24h Change: {ticker.change_24h:.2%}")
            print(f"  24h Volume: ${ticker.volume_24h:,.0f}")
        except Exception as e:
            print(f"  Not available: {e}")

        # Get all stock tickers
        print("\n=== All Stock Tickers ===")
        tickers = await trader.get_all_stock_tickers()
        for symbol, t in tickers.items():
            print(f"  {symbol}: ${t.last_price:.2f} ({t.change_24h:+.2%})")

        # Get balance
        print("\n=== USDT Balance ===")
        balance = await trader.get_balance('USDT')
        print(f"  Available: ${balance['available']:.2f}")
        print(f"  Total: ${balance['total']:.2f}")

        # Get NVIDIA candles
        print("\n=== NVIDIA Daily Candles (last 5) ===")
        try:
            candles = await trader.get_candles('NVDA', '1D', 5)
            for c in candles:
                ts, o, h, l, close, vol = c[0], c[1], c[2], c[3], c[4], c[5]
                print(f"  {datetime.fromtimestamp(int(ts)/1000).strftime('%Y-%m-%d')}: "
                      f"O={o} H={h} L={l} C={close} V={vol}")
        except Exception as e:
            print(f"  Not available: {e}")

    finally:
        await trader.close()


if __name__ == "__main__":
    asyncio.run(main())
