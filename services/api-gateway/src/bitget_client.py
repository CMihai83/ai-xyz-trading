"""
Bitget API Client for real trading operations.
"""

import hmac
import hashlib
import base64
import time
import json
import requests
from typing import Dict, List, Optional, Any
import structlog

logger = structlog.get_logger(__name__)

class BitgetClient:
    """Bitget API client for trading operations."""
    
    def __init__(self, api_key: str, api_secret: str, passphrase: str, sandbox: bool = False):
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = "https://api.bitget.com" if not sandbox else "https://api.bitgetapi.com"
        self.session = requests.Session()
        
    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Generate signature for API authentication."""
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        return signature
    
    def _get_headers(self, method: str, request_path: str, body: str = "") -> Dict[str, str]:
        """Get headers for API request."""
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
    
    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None, data: Optional[Dict] = None) -> Dict:
        """Make authenticated request to Bitget API."""
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data) if data else ""
        headers = self._get_headers(method, endpoint, body)
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, params=params)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=headers, data=body)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') != '00000':
                raise Exception(f"Bitget API error: {result.get('msg', 'Unknown error')}")
            
            return result.get('data', {})
            
        except Exception as e:
            logger.error(f"Bitget API request failed: {str(e)}")
            raise
    
    # Account Information
    def get_account_info(self) -> Dict:
        """Get account information."""
        return self._request('GET', '/api/spot/v1/account/assets')
    
    def get_balance(self, coin: str = None) -> Dict:
        """Get account balance."""
        params = {'coin': coin} if coin else {}
        return self._request('GET', '/api/spot/v1/account/assets', params=params)
    
    # Market Data
    def get_ticker(self, symbol: str) -> Dict:
        """Get ticker information for a symbol."""
        params = {'symbol': symbol}
        return self._request('GET', '/api/spot/v1/market/ticker', params=params)
    
    def get_orderbook(self, symbol: str, limit: int = 100) -> Dict:
        """Get orderbook for a symbol."""
        params = {'symbol': symbol, 'limit': limit}
        return self._request('GET', '/api/spot/v1/market/depth', params=params)
    
    def get_klines(self, symbol: str, granularity: str = '1min', limit: int = 100) -> List[Dict]:
        """Get candlestick data."""
        params = {
            'symbol': symbol,
            'granularity': granularity,
            'limit': limit
        }
        return self._request('GET', '/api/spot/v1/market/candles', params=params)
    
    # Trading Operations
    def place_order(self, symbol: str, side: str, order_type: str, size: str, 
                   price: str = None, client_order_id: str = None) -> Dict:
        """Place a trading order."""
        data = {
            'symbol': symbol,
            'side': side.lower(),  # buy or sell
            'orderType': order_type.lower(),  # limit, market
            'size': size
        }
        
        if price and order_type.lower() == 'limit':
            data['price'] = price
            
        if client_order_id:
            data['clientOrderId'] = client_order_id
        
        return self._request('POST', '/api/spot/v1/trade/orders', data=data)
    
    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel an order."""
        data = {
            'symbol': symbol,
            'orderId': order_id
        }
        return self._request('POST', '/api/spot/v1/trade/cancel-order', data=data)
    
    def get_order(self, symbol: str, order_id: str) -> Dict:
        """Get order details."""
        params = {
            'symbol': symbol,
            'orderId': order_id
        }
        return self._request('GET', '/api/spot/v1/trade/orderInfo', params=params)
    
    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """Get open orders."""
        params = {'symbol': symbol} if symbol else {}
        return self._request('GET', '/api/spot/v1/trade/open-orders', params=params)
    
    def get_order_history(self, symbol: str = None, limit: int = 100) -> List[Dict]:
        """Get order history."""
        params = {
            'limit': limit
        }
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', '/api/spot/v1/trade/history', params=params)
    
    # Position Management
    def get_positions(self) -> List[Dict]:
        """Get current positions (for futures)."""
        return self._request('GET', '/api/mix/v1/position/allPosition')
    
    def close_position(self, symbol: str, margin_coin: str, size: str) -> Dict:
        """Close a position (for futures)."""
        data = {
            'symbol': symbol,
            'marginCoin': margin_coin,
            'size': size
        }
        return self._request('POST', '/api/mix/v1/order/close-position', data=data)

# Test the Bitget connection
def test_bitget_connection(api_key: str, api_secret: str, passphrase: str) -> bool:
    """Test Bitget API connection."""
    try:
        client = BitgetClient(api_key, api_secret, passphrase)
        account_info = client.get_account_info()
        logger.info("Bitget connection successful")
        return True
    except Exception as e:
        logger.error(f"Bitget connection failed: {str(e)}")
        return False
