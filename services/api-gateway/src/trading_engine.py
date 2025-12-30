"""
Trading Engine - Orchestrates the entire trading lifecycle with Bitget integration.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import structlog
import httpx
from bitget_client import BitgetClient
from config import settings

logger = structlog.get_logger(__name__)

class TradingEngine:
    """Main trading engine that orchestrates the entire trading lifecycle."""
    
    def __init__(self):
        self.bitget_client = BitgetClient(
            api_key=settings.BITGET_API_KEY,
            api_secret=settings.BITGET_API_SECRET,
            passphrase=settings.BITGET_API_PASSPHRASE
        )
        self.active_positions = {}
        self.running = False
        
    async def start(self):
        """Start the trading engine."""
        logger.info("Starting Trading Engine...")
        self.running = True
        
        # Test Bitget connection
        try:
            account_info = self.bitget_client.get_account_info()
            logger.info("Bitget connection established", account_info=account_info)
        except Exception as e:
            logger.error("Failed to connect to Bitget", error=str(e))
            return False
        
        # Start main trading loop
        asyncio.create_task(self.trading_loop())
        asyncio.create_task(self.position_monitoring_loop())
        
        return True
    
    async def stop(self):
        """Stop the trading engine."""
        logger.info("Stopping Trading Engine...")
        self.running = False
    
    async def trading_loop(self):
        """Main trading loop - scans market and makes trading decisions."""
        while self.running:
            try:
                # Get market scan results
                scan_results = await self.get_market_scan()
                
                # Process each signal
                for signal in scan_results.get('scan_results', []):
                    await self.process_trading_signal(signal)
                
                # Wait before next scan
                await asyncio.sleep(30)  # Scan every 30 seconds
                
            except Exception as e:
                logger.error("Error in trading loop", error=str(e))
                await asyncio.sleep(60)  # Wait longer on error
    
    async def position_monitoring_loop(self):
        """Monitor existing positions and manage their lifecycle."""
        while self.running:
            try:
                # Update all active positions
                await self.update_active_positions()
                
                # Check for position management triggers
                for position_id, position in self.active_positions.items():
                    await self.manage_position_lifecycle(position)
                
                # Wait before next check
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                logger.error("Error in position monitoring", error=str(e))
                await asyncio.sleep(30)
    
    async def get_market_scan(self) -> Dict:
        """Get market scan results from market scanner service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{settings.MARKET_SCANNER_URL}/scan")
                return response.json()
        except Exception as e:
            logger.error("Failed to get market scan", error=str(e))
            return {'scan_results': []}
    
    async def process_trading_signal(self, signal: Dict):
        """Process a trading signal through the AI decision engine."""
        try:
            symbol = signal['symbol']
            
            # Skip if we already have a position in this symbol
            if any(pos['symbol'] == symbol for pos in self.active_positions.values()):
                return
            
            # Get current price
            ticker = self.bitget_client.get_ticker(f"{symbol}USDT")
            current_price = float(ticker['close'])
            
            # Analyze decision through AI engine
            decision = await self.analyze_trading_decision(signal, current_price)
            
            if decision['decision'] == 'BUY' and decision['confidence'] > 0.7:
                await self.execute_buy_order(symbol, current_price, decision)
                
        except Exception as e:
            logger.error("Error processing trading signal", signal=signal, error=str(e))
    
    async def analyze_trading_decision(self, signal: Dict, current_price: float) -> Dict:
        """Send signal to AI decision engine for analysis."""
        try:
            async with httpx.AsyncClient() as client:
                decision_request = {
                    'symbol': signal['symbol'],
                    'signal_type': signal['signals'][0]['type'] if signal['signals'] else 'HOLD',
                    'signal_strength': signal['signals'][0]['strength'] if signal['signals'] else 0.0,
                    'price': current_price,
                    'metadata': signal
                }
                
                response = await client.post(
                    f"{settings.AI_DECISION_ENGINE_URL}/analyze",
                    json=decision_request
                )
                return response.json()
                
        except Exception as e:
            logger.error("Failed to analyze decision", error=str(e))
            return {'decision': 'HOLD', 'confidence': 0.0}
    
    async def execute_buy_order(self, symbol: str, price: float, decision: Dict):
        """Execute a buy order and create position tracking."""
        try:
            # Calculate position size (risk 1% of account)
            account_balance = self.get_account_balance()
            risk_amount = account_balance * 0.01  # 1% risk
            quantity = risk_amount / price
            
            # Place buy order
            order_result = self.bitget_client.place_order(
                symbol=f"{symbol}USDT",
                side='buy',
                order_type='market',
                size=str(quantity)
            )
            
            # Create position in position management service
            position = await self.create_position(symbol, quantity, price, decision)
            
            logger.info("Buy order executed", 
                       symbol=symbol, 
                       quantity=quantity, 
                       price=price,
                       order_id=order_result.get('orderId'))
            
            return position
            
        except Exception as e:
            logger.error("Failed to execute buy order", symbol=symbol, error=str(e))
            return None
    
    async def create_position(self, symbol: str, quantity: float, entry_price: float, decision: Dict) -> Dict:
        """Create position in position management service."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{settings.POSITION_MANAGEMENT_URL}/positions",
                    params={
                        'symbol': symbol,
                        'quantity': quantity,
                        'entry_price': entry_price
                    }
                )
                position = response.json()
                self.active_positions[position['id']] = position
                return position
                
        except Exception as e:
            logger.error("Failed to create position", error=str(e))
            return None
    
    async def update_active_positions(self):
        """Update all active positions with current market prices."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{settings.POSITION_MANAGEMENT_URL}/positions")
                positions = response.json()
                
                for position in positions:
                    # Get current price
                    ticker = self.bitget_client.get_ticker(f"{position['symbol']}USDT")
                    current_price = float(ticker['close'])
                    
                    # Update position price
                    await client.put(
                        f"{settings.POSITION_MANAGEMENT_URL}/positions/{position['id']}/price",
                        json={'current_price': current_price}
                    )
                    
                    self.active_positions[position['id']] = position
                    
        except Exception as e:
            logger.error("Failed to update positions", error=str(e))
    
    async def manage_position_lifecycle(self, position: Dict):
        """Manage position through its lifecycle based on zones."""
        try:
            # Get position zones
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{settings.POSITION_MANAGEMENT_URL}/positions/{position['id']}/zones"
                )
                zones_data = response.json()
            
            # Check for triggered zones
            for zone in zones_data['zones']:
                if zone['triggered'] and zone['active']:
                    await self.execute_zone_action(position, zone)
                    
        except Exception as e:
            logger.error("Failed to manage position lifecycle", position_id=position['id'], error=str(e))
    
    async def execute_zone_action(self, position: Dict, zone: Dict):
        """Execute action for a triggered zone."""
        try:
            zone_type = zone['type']
            symbol = position['symbol']
            
            if zone_type == 'PROFIT_TAKING':
                # Sell portion of position
                sell_quantity = min(zone['quantity'], position['quantity'])
                
                order_result = self.bitget_client.place_order(
                    symbol=f"{symbol}USDT",
                    side='sell',
                    order_type='limit',
                    size=str(sell_quantity),
                    price=str(zone['price'])
                )
                
                logger.info("Profit taking executed", 
                           symbol=symbol, 
                           quantity=sell_quantity, 
                           price=zone['price'])
            
            elif zone_type == 'STOP_LOSS':
                # Close entire position
                order_result = self.bitget_client.place_order(
                    symbol=f"{symbol}USDT",
                    side='sell',
                    order_type='market',
                    size=str(position['quantity'])
                )
                
                logger.info("Stop loss executed", 
                           symbol=symbol, 
                           quantity=position['quantity'])
                
                # Remove from active positions
                if position['id'] in self.active_positions:
                    del self.active_positions[position['id']]
            
            elif zone_type == 'ACCUMULATION':
                # Add to position
                additional_quantity = zone['quantity']
                
                order_result = self.bitget_client.place_order(
                    symbol=f"{symbol}USDT",
                    side='buy',
                    order_type='limit',
                    size=str(additional_quantity),
                    price=str(zone['price'])
                )
                
                logger.info("Accumulation executed", 
                           symbol=symbol, 
                           quantity=additional_quantity, 
                           price=zone['price'])
                
        except Exception as e:
            logger.error("Failed to execute zone action", zone=zone, error=str(e))
    
    def get_account_balance(self) -> float:
        """Get account balance in USDT."""
        try:
            balance_info = self.bitget_client.get_balance('USDT')
            return float(balance_info[0]['available']) if balance_info else 1000.0
        except:
            return 1000.0  # Default balance for testing
    
    async def get_trading_status(self) -> Dict:
        """Get current trading engine status."""
        return {
            'running': self.running,
            'active_positions': len(self.active_positions),
            'account_balance': self.get_account_balance(),
            'positions': list(self.active_positions.values()),
            'timestamp': datetime.now().isoformat()
        }

# Global trading engine instance
trading_engine = TradingEngine()
