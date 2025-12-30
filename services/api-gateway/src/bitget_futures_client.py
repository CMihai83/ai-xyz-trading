"""
Bitget Futures API Client for futures/perpetual trading operations.
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

class BitgetFuturesClient:
    """Bitget API client for futures/perpetual trading operations."""
    
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
            logger.error(f"Bitget Futures API request failed: {str(e)}")
            raise
    
    # Account Information - Futures
    def get_futures_account(self, product_type: str = "USDT-FUTURES") -> List[Dict]:
        """Get futures account information using v2 API.
        product_type: USDT-FUTURES, USDC-FUTURES, COIN-FUTURES
        """
        # Try v2 API first
        try:
            return self._request('GET', f'/api/v2/mix/account/accounts?productType={product_type}')
        except:
            # Fallback to v1 API with old format
            old_type = "umcbl" if product_type == "USDT-FUTURES" else product_type
            return self._request('GET', f'/api/mix/v1/account/accounts?productType={old_type}')
    
    def get_futures_balance(self, symbol: str, margin_coin: str = "USDT") -> Dict:
        """Get futures account balance for a specific symbol."""
        params = {
            'symbol': symbol,
            'marginCoin': margin_coin
        }
        return self._request('GET', '/api/mix/v1/account/account', params=params)
    
    # Market Data - Futures
    def get_futures_ticker(self, symbol: str) -> Dict:
        """Get futures ticker for a symbol."""
        params = {'symbol': symbol}
        return self._request('GET', '/api/mix/v1/market/ticker', params=params)
    
    def get_all_futures_tickers(self, product_type: str = "umcbl") -> List[Dict]:
        """Get all futures tickers.
        product_type: umcbl (USDT perpetual), dmcbl (USDC perpetual), cmcbl (Coin perpetual)
        """
        params = {'productType': product_type}
        return self._request('GET', '/api/mix/v1/market/tickers', params=params)
    
    def get_futures_klines(self, symbol: str, granularity: str, limit: int = 100) -> List[List]:
        """Get futures candlestick data.
        granularity: 1m, 5m, 15m, 30m, 1H, 4H, 12H, 1D, 1W, 1M
        """
        params = {
            'symbol': symbol,
            'granularity': granularity,
            'limit': limit
        }
        return self._request('GET', '/api/mix/v1/market/candles', params=params)
    
    # Trading Operations - Futures
    def place_futures_order(self, symbol: str, margin_coin: str, size: str, side: str, 
                          order_type: str, price: str = None, client_order_id: str = None,
                          reduce_only: bool = False, time_in_force: str = None,
                          stop_loss_price: str = None, take_profit_price: str = None,
                          margin_mode: str = 'isolated') -> Dict:
        """Place a futures order with isolated margin mode by default."""
        data = {
            'symbol': symbol,
            'marginCoin': margin_coin,
            'size': size,
            'side': side.lower(),  # open_long, open_short, close_long, close_short
            'orderType': order_type.lower(),  # limit, market
            'marginMode': margin_mode,  # 'isolated' or 'crossed' - default to isolated
        }
        
        if price and order_type.lower() == 'limit':
            data['price'] = price
            
        if client_order_id:
            data['clientOid'] = client_order_id
            
        if reduce_only:
            data['reduceOnly'] = 'YES'
            
        if time_in_force:
            data['timeInForceValue'] = time_in_force
            
        if stop_loss_price:
            data['presetStopLossPrice'] = stop_loss_price
            
        if take_profit_price:
            data['presetTakeProfitPrice'] = take_profit_price
        
        return self._request('POST', '/api/mix/v1/order/placeOrder', data=data)
    
    def cancel_futures_order(self, symbol: str, margin_coin: str, order_id: str = None, client_order_id: str = None) -> Dict:
        """Cancel a futures order."""
        data = {
            'symbol': symbol,
            'marginCoin': margin_coin
        }
        
        if order_id:
            data['orderId'] = order_id
        elif client_order_id:
            data['clientOid'] = client_order_id
        else:
            raise ValueError("Either order_id or client_order_id must be provided")
        
        return self._request('POST', '/api/mix/v1/order/cancel-order', data=data)
    
    def get_futures_order(self, symbol: str, order_id: str = None, client_order_id: str = None) -> Dict:
        """Get futures order details."""
        params = {'symbol': symbol}
        
        if order_id:
            params['orderId'] = order_id
        elif client_order_id:
            params['clientOid'] = client_order_id
        
        return self._request('GET', '/api/mix/v1/order/detail', params=params)
    
    def get_futures_open_orders(self, symbol: str = None, product_type: str = "USDT-FUTURES") -> List[Dict]:
        """Get open futures orders."""
        params = {'productType': product_type}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', '/api/mix/v1/order/current', params=params)
    
    def get_futures_order_history(self, symbol: str, start_time: str = None, end_time: str = None, limit: int = 100) -> List[Dict]:
        """Get futures order history."""
        params = {
            'symbol': symbol,
            'pageSize': limit
        }
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        return self._request('GET', '/api/mix/v1/order/history', params=params)
    
    # Position Management - Futures
    def get_all_positions(self, product_type: str = "USDT-FUTURES") -> List[Dict]:
        """Get all futures positions."""
        # Direct implementation that works
        try:
            url = f"{self.base_url}/api/mix/v1/position/allPosition-v2"
            params = {'productType': 'umcbl'}
            
            # Generate signature
            timestamp = str(int(time.time() * 1000))
            request_path = '/api/mix/v1/position/allPosition-v2?productType=umcbl'
            signature = self._generate_signature(timestamp, 'GET', request_path, '')
            
            headers = {
                'ACCESS-KEY': self.api_key,
                'ACCESS-SIGN': signature,
                'ACCESS-TIMESTAMP': timestamp,
                'ACCESS-PASSPHRASE': self.passphrase,
                'Content-Type': 'application/json',
                'locale': 'en-US'
            }
            
            response = self.session.get(url, headers=headers, params=params)
            if response.status_code == 200:
                result = response.json()
                if result.get('code') == '00000':
                    return result.get('data', [])
            return []
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return []
    
    def get_futures_positions(self, product_type: str = "USDT-FUTURES") -> List[Dict]:
        """Alias for get_all_positions for compatibility."""
        return self.get_all_positions(product_type)
    
    def get_single_position(self, symbol: str, margin_coin: str = "USDT") -> Dict:
        """Get single futures position."""
        params = {
            'symbol': symbol,
            'marginCoin': margin_coin
        }
        return self._request('GET', '/api/mix/v1/position/singlePosition', params=params)
    
    def close_all_positions(self, product_type: str = "USDT-FUTURES") -> Dict:
        """Close all futures positions."""
        data = {'productType': product_type}
        return self._request('POST', '/api/mix/v1/order/close-all-positions', data=data)
    
    def set_leverage(self, symbol: str, margin_coin: str, leverage: int, hold_side: str = None) -> Dict:
        """Set leverage for futures trading.
        hold_side: long, short, or None for both
        """
        data = {
            'symbol': symbol,
            'marginCoin': margin_coin,
            'leverage': str(leverage)
        }
        if hold_side:
            data['holdSide'] = hold_side
        return self._request('POST', '/api/mix/v1/account/setLeverage', data=data)
    
    def set_margin_mode(self, symbol: str, margin_coin: str, margin_mode: str) -> Dict:
        """Set margin mode for futures trading.
        margin_mode: 'isolated' or 'crossed'
        """
        data = {
            'symbol': symbol,
            'marginCoin': margin_coin,
            'marginMode': margin_mode
        }
        return self._request('POST', '/api/mix/v1/account/setMarginMode', data=data)
    
    def set_position_mode(self, product_type: str, position_mode: str) -> Dict:
        """Set position mode for futures trading.
        position_mode: 'one_way' or 'double_hold' (hedge mode)
        """
        data = {
            'productType': product_type,
            'holdMode': position_mode
        }
        return self._request('POST', '/api/mix/v1/account/setPositionMode', data=data)
    
    # Risk Management - Futures
    def set_stop_loss_take_profit(self, symbol: str, margin_coin: str, plan_type: str,
                                   trigger_price: str, trigger_type: str,
                                   hold_side: str = 'long') -> Dict:
        """Set stop loss or take profit for a position.
        plan_type: 'profit_plan' or 'loss_plan'
        trigger_type: 'fill_price' or 'mark_price'
        """
        data = {
            'symbol': symbol,
            'marginCoin': margin_coin,
            'planType': plan_type,
            'triggerPrice': trigger_price,
            'triggerType': trigger_type,
            'holdSide': hold_side
        }
        return self._request('POST', '/api/mix/v1/plan/placePlan', data=data)
    
    def get_account_bill(self, product_type: str = "umcbl", business_type: str = None, 
                          start_time: str = None, end_time: str = None, limit: int = 100) -> List[Dict]:
        """Get account bill history.
        business_type: 'open_long', 'open_short', 'close_long', 'close_short', 'burst_long', 'burst_short'
        """
        params = {
            'productType': product_type,
            'pageSize': limit
        }
        if business_type:
            params['business'] = business_type
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        return self._request('GET', '/api/mix/v1/account/accountBill', params=params)
    
    def modify_position_margin(self, symbol: str, margin_coin: str, amount: str, hold_side: str = 'long') -> Dict:
        """Add or reduce position margin.
        amount: positive to add, negative to reduce
        """
        data = {
            'symbol': symbol,
            'marginCoin': margin_coin,
            'amount': amount,
            'holdSide': hold_side
        }
        return self._request('POST', '/api/mix/v1/position/changeMargin', data=data)


def test_bitget_futures_connection(api_key: str, api_secret: str, passphrase: str) -> bool:
    """Test Bitget Futures API connection."""
    try:
        client = BitgetFuturesClient(api_key, api_secret, passphrase)
        # Try multiple product types in case one format works
        for product_type in ['USDT-FUTURES', 'umcbl']:
            try:
                account_info = client.get_futures_account(product_type)
                if account_info:
                    return True
            except:
                continue
        return False
    except Exception as e:
        logger.error(f"Bitget Futures connection test failed: {str(e)}")
        return False