#!/usr/bin/env python3
"""
Enhanced Futures Position Management Service
Handles dynamic leverage, margin allocation, and precise order formatting for Bitget futures.
"""

import asyncio
import json
import hmac
import hashlib
import base64
import time
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Dict, List, Optional, Tuple
import aiohttp
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import logging

# Import our futures configuration
import sys
sys.path.append('/home/ubuntu/ai-trading-system-futures')
from futures_symbols_config import (
    get_symbol_config, format_price, format_quantity, 
    validate_order_size, calculate_margin_required, get_optimal_leverage
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Futures Position Manager", version="2.0.0")

# Bitget API Configuration
BITGET_API_KEY = "bg_f483546274ffb2bfa567328e98dba6c0"
BITGET_API_SECRET = "387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0"
BITGET_API_PASSPHRASE = "2609Luiza"
BITGET_BASE_URL = "https://api.bitget.com"

class BitgetFuturesAPI:
    """Enhanced Bitget Futures API client with proper order formatting."""
    
    def __init__(self):
        self.api_key = BITGET_API_KEY
        self.api_secret = BITGET_API_SECRET
        self.passphrase = BITGET_API_PASSPHRASE
        self.base_url = BITGET_BASE_URL
        
    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Generate API signature for Bitget."""
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        return signature
    
    def _get_headers(self, timestamp: str, method: str, request_path: str, body: str = "") -> Dict:
        """Get API headers for Bitget requests."""
        signature = self._generate_signature(timestamp, method, request_path, body)
        return {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json',
            'locale': 'en-US'
        }
    
    async def get_account_info(self) -> Dict:
        """Get futures account information."""
        timestamp = str(int(time.time() * 1000))
        request_path = "/api/mix/v1/account/account"

        headers = self._get_headers(timestamp, 'GET', request_path)

        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}{request_path}",
                headers=headers,
                params={'productType': 'umcbl'}  # USDT-M futures
            ) as response:
                data = await response.json()
                return data

    async def set_position_mode(self, mode: str = "hedge_mode") -> Dict:
        """Set position mode to hedge or one-way."""
        timestamp = str(int(time.time() * 1000))
        request_path = "/api/mix/v1/account/setPositionMode"

        body_data = {
            "productType": "umcbl",  # USDT-M futures
            "posMode": mode  # "hedge_mode" or "one_way_mode"
        }
        body = json.dumps(body_data)

        headers = self._get_headers(timestamp, 'POST', request_path, body)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}{request_path}",
                headers=headers,
                data=body
            ) as response:
                data = await response.json()
                return data
    
    async def get_positions(self, symbol: str = None) -> List[Dict]:
        """Get current futures positions."""
        timestamp = str(int(time.time() * 1000))
        request_path = "/api/mix/v1/position/allPosition"
        
        headers = self._get_headers(timestamp, 'GET', request_path)
        params = {'productType': 'umcbl'}
        if symbol:
            params['symbol'] = symbol
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}{request_path}",
                headers=headers,
                params=params
            ) as response:
                data = await response.json()
                return data.get('data', [])
    
    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'cross') -> Dict:
        """Set leverage for a symbol."""
        timestamp = str(int(time.time() * 1000))
        request_path = "/api/mix/v1/account/setLeverage"
        
        body_data = {
            'symbol': symbol,
            'marginCoin': 'USDT',
            'leverage': str(leverage),
            'holdSide': 'long'  # Set for both long and short
        }
        body = json.dumps(body_data)
        
        headers = self._get_headers(timestamp, 'POST', request_path, body)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}{request_path}",
                headers=headers,
                data=body
            ) as response:
                data = await response.json()
                
                # Also set for short side
                body_data['holdSide'] = 'short'
                body = json.dumps(body_data)
                headers = self._get_headers(timestamp, 'POST', request_path, body)
                
                async with session.post(
                    f"{self.base_url}{request_path}",
                    headers=headers,
                    data=body
                ) as response2:
                    data2 = await response2.json()
                
                return data
    
    async def place_order(self, order_data: Dict) -> Dict:
        """Place a futures order with proper formatting."""
        # Ensure position mode is set to hedge
        await self.set_position_mode("hedge_mode")

        timestamp = str(int(time.time() * 1000))
        request_path = "/api/mix/v1/order/placeOrder"

        # Format order data according to Bitget requirements
        formatted_order = self._format_order_data(order_data)
        body = json.dumps(formatted_order)
        
        headers = self._get_headers(timestamp, 'POST', request_path, body)
        
        logger.info(f"Placing order: {formatted_order}")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}{request_path}",
                headers=headers,
                data=body
            ) as response:
                data = await response.json()
                logger.info(f"Order response: {data}")
                return data
    
    def _format_order_data(self, order_data: Dict) -> Dict:
        """Format order data according to Bitget futures API requirements."""
        symbol = order_data['symbol']
        config = get_symbol_config(symbol)
        
        if not config:
            raise ValueError(f"No configuration found for symbol {symbol}")
        
        # Format price and quantity with proper precision
        price = format_price(symbol, float(order_data['price']))
        quantity = format_quantity(symbol, float(order_data['quantity']))
        
        # Validate order size
        is_valid, message = validate_order_size(symbol, quantity, price)
        if not is_valid:
            raise ValueError(f"Invalid order size: {message}")
        
        # Determine holdSide for hedge mode
        side = order_data['side'].lower()
        hold_side = 'long' if side == 'buy' else 'short'

        formatted_order = {
            'symbol': symbol,
            'productType': 'umcbl',  # USDT-M futures
            'marginCoin': 'USDT',
            'size': str(quantity),
            'price': str(price),
            'side': side,  # 'buy' or 'sell'
            'holdSide': hold_side,  # 'long' or 'short' for hedge mode
            'orderType': order_data.get('orderType', 'limit').lower(),
            'timeInForceValue': order_data.get('timeInForce', 'GTC'),
            'clientOid': order_data.get('clientOrderId', f"futures_{int(time.time() * 1000)}")
        }
        
        # Add stop loss and take profit if provided
        if 'stopLoss' in order_data:
            formatted_order['presetTakeProfitPrice'] = str(format_price(symbol, float(order_data['stopLoss'])))
        
        if 'takeProfit' in order_data:
            formatted_order['presetStopLossPrice'] = str(format_price(symbol, float(order_data['takeProfit'])))
        
        return formatted_order
    
    async def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """Cancel a futures order."""
        timestamp = str(int(time.time() * 1000))
        request_path = "/api/mix/v1/order/cancel-order"
        
        body_data = {
            'symbol': symbol,
            'orderId': order_id
        }
        body = json.dumps(body_data)
        
        headers = self._get_headers(timestamp, 'POST', request_path, body)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}{request_path}",
                headers=headers,
                data=body
            ) as response:
                data = await response.json()
                return data

class FuturesPositionManager:
    """Enhanced futures position manager with dynamic leverage and margin allocation."""
    
    def __init__(self):
        self.bitget_api = BitgetFuturesAPI()
        self.redis_client = redis.Redis(host='localhost', port=6379, db=0)
        self.positions = {}
        self.margin_allocation = {}
        
    async def calculate_position_size(self, symbol: str, signal_strength: float, 
                                    available_margin: float, risk_per_trade: float = 0.02) -> Dict:
        """Calculate optimal position size with dynamic leverage."""
        config = get_symbol_config(symbol)
        if not config:
            raise ValueError(f"No configuration for symbol {symbol}")
        
        # Get optimal leverage based on signal strength
        optimal_leverage = get_optimal_leverage(symbol, signal_strength)
        
        # Calculate position size based on risk management
        risk_amount = available_margin * risk_per_trade
        
        # Get current price (simplified - in production, get from market data)
        current_price = 50000.0  # This should come from real market data
        
        # Calculate position size
        max_position_value = available_margin * optimal_leverage * 0.8  # 80% of max
        risk_based_position_value = risk_amount * optimal_leverage
        
        position_value = min(max_position_value, risk_based_position_value)
        quantity = position_value / current_price
        
        # Format according to symbol requirements
        formatted_quantity = format_quantity(symbol, quantity)
        
        # Validate the order
        is_valid, message = validate_order_size(symbol, formatted_quantity, current_price)
        if not is_valid:
            # Adjust to minimum if too small
            formatted_quantity = config['min_quantity']
            position_value = formatted_quantity * current_price
        
        # Calculate margin requirements
        margin_info = calculate_margin_required(symbol, formatted_quantity, current_price, optimal_leverage)
        
        return {
            'symbol': symbol,
            'quantity': formatted_quantity,
            'price': format_price(symbol, current_price),
            'leverage': optimal_leverage,
            'position_value': position_value,
            'margin_required': margin_info['initial_margin'],
            'maintenance_margin': margin_info['maintenance_margin'],
            'risk_amount': risk_amount,
            'signal_strength': signal_strength
        }
    
    async def open_position(self, symbol: str, side: str, signal_strength: float, 
                          stop_loss_pct: float = 0.02, take_profit_pct: float = 0.04) -> Dict:
        """Open a futures position with dynamic leverage and proper risk management."""
        try:
            # Get account info to check available margin
            account_info = await self.bitget_api.get_account_info()
            available_margin = float(account_info.get('data', {}).get('available', 0))
            
            if available_margin < 10:  # Minimum margin requirement
                raise ValueError("Insufficient margin available")
            
            # Calculate optimal position size
            position_calc = await self.calculate_position_size(symbol, signal_strength, available_margin)
            
            # Set leverage for the symbol
            await self.bitget_api.set_leverage(symbol, position_calc['leverage'])
            
            # Calculate stop loss and take profit prices
            entry_price = position_calc['price']
            if side.lower() == 'buy':
                stop_loss_price = entry_price * (1 - stop_loss_pct)
                take_profit_price = entry_price * (1 + take_profit_pct)
            else:
                stop_loss_price = entry_price * (1 + stop_loss_pct)
                take_profit_price = entry_price * (1 - take_profit_pct)
            
            # Prepare order data
            order_data = {
                'symbol': symbol,
                'side': side,
                'quantity': position_calc['quantity'],
                'price': entry_price,
                'orderType': 'limit',
                'timeInForce': 'GTC',
                'stopLoss': format_price(symbol, stop_loss_price),
                'takeProfit': format_price(symbol, take_profit_price),
                'clientOrderId': f"futures_{symbol}_{int(time.time() * 1000)}"
            }
            
            # Place the order
            order_result = await self.bitget_api.place_order(order_data)
            
            if order_result.get('code') == '00000':  # Success
                position_data = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': position_calc['quantity'],
                    'entry_price': entry_price,
                    'leverage': position_calc['leverage'],
                    'margin_used': position_calc['margin_required'],
                    'stop_loss': stop_loss_price,
                    'take_profit': take_profit_price,
                    'order_id': order_result.get('data', {}).get('orderId'),
                    'timestamp': datetime.now().isoformat(),
                    'signal_strength': signal_strength
                }
                
                # Store position data
                self.positions[f"{symbol}_{side}"] = position_data
                self.redis_client.set(f"position:{symbol}_{side}", json.dumps(position_data))
                
                logger.info(f"Position opened successfully: {position_data}")
                return position_data
            else:
                raise ValueError(f"Failed to place order: {order_result}")
                
        except Exception as e:
            logger.error(f"Error opening position: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))
    
    async def close_position(self, symbol: str, side: str, reason: str = "manual") -> Dict:
        """Close a futures position."""
        try:
            position_key = f"{symbol}_{side}"
            position_data = self.positions.get(position_key)
            
            if not position_data:
                # Try to get from Redis
                stored_data = self.redis_client.get(f"position:{position_key}")
                if stored_data:
                    position_data = json.loads(stored_data)
                else:
                    raise ValueError(f"No position found for {position_key}")
            
            # Get current positions from exchange
            current_positions = await self.bitget_api.get_positions(symbol)
            
            # Find the matching position
            target_position = None
            for pos in current_positions:
                if pos['symbol'] == symbol and pos['holdSide'] == side:
                    target_position = pos
                    break
            
            if not target_position or float(target_position['total']) == 0:
                logger.info(f"No open position found for {position_key}")
                return {'status': 'no_position', 'message': 'Position already closed or not found'}
            
            # Place closing order (opposite side)
            close_side = 'sell' if side == 'buy' else 'buy'
            current_price = float(target_position['markPrice'])
            quantity = abs(float(target_position['total']))
            
            close_order_data = {
                'symbol': symbol,
                'side': close_side,
                'quantity': quantity,
                'price': format_price(symbol, current_price),
                'orderType': 'market',  # Use market order for immediate execution
                'clientOrderId': f"close_{symbol}_{int(time.time() * 1000)}"
            }
            
            # Place closing order
            close_result = await self.bitget_api.place_order(close_order_data)
            
            if close_result.get('code') == '00000':
                # Calculate P&L
                entry_price = float(position_data['entry_price'])
                exit_price = current_price
                
                if side == 'buy':
                    pnl = (exit_price - entry_price) * quantity
                else:
                    pnl = (entry_price - exit_price) * quantity
                
                # Apply leverage to P&L
                leveraged_pnl = pnl * float(position_data['leverage'])
                
                close_data = {
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'pnl': leveraged_pnl,
                    'pnl_percentage': (leveraged_pnl / float(position_data['margin_used'])) * 100,
                    'leverage': position_data['leverage'],
                    'close_reason': reason,
                    'close_order_id': close_result.get('data', {}).get('orderId'),
                    'timestamp': datetime.now().isoformat()
                }
                
                # Remove position from storage
                if position_key in self.positions:
                    del self.positions[position_key]
                self.redis_client.delete(f"position:{position_key}")
                
                logger.info(f"Position closed successfully: {close_data}")
                return close_data
            else:
                raise ValueError(f"Failed to close position: {close_result}")
                
        except Exception as e:
            logger.error(f"Error closing position: {str(e)}")
            raise HTTPException(status_code=400, detail=str(e))

# Initialize the position manager
position_manager = FuturesPositionManager()

# API Models
class OpenPositionRequest(BaseModel):
    symbol: str
    side: str  # 'buy' or 'sell'
    signal_strength: float
    stop_loss_pct: float = 0.02
    take_profit_pct: float = 0.04

class ClosePositionRequest(BaseModel):
    symbol: str
    side: str
    reason: str = "manual"

# API Endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "futures-position-manager", "version": "2.0.0"}

@app.post("/positions/open")
async def open_position(request: OpenPositionRequest):
    """Open a new futures position with dynamic leverage."""
    return await position_manager.open_position(
        request.symbol,
        request.side,
        request.signal_strength,
        request.stop_loss_pct,
        request.take_profit_pct
    )

@app.post("/positions/close")
async def close_position(request: ClosePositionRequest):
    """Close an existing futures position."""
    return await position_manager.close_position(
        request.symbol,
        request.side,
        request.reason
    )

@app.get("/positions")
async def get_positions():
    """Get all current positions."""
    return await position_manager.bitget_api.get_positions()

@app.get("/account")
async def get_account_info():
    """Get futures account information."""
    return await position_manager.bitget_api.get_account_info()

@app.get("/symbols/{symbol}/config")
async def get_symbol_configuration(symbol: str):
    """Get configuration for a specific symbol."""
    config = get_symbol_config(symbol)
    if not config:
        raise HTTPException(status_code=404, detail="Symbol configuration not found")
    return config

@app.post("/leverage/{symbol}/{leverage}")
async def set_symbol_leverage(symbol: str, leverage: int):
    """Set leverage for a specific symbol."""
    return await position_manager.bitget_api.set_leverage(symbol, leverage)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)
