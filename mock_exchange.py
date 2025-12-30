"""
Mock Exchange for Testing
Simulates Bitget exchange for compliance testing
"""

import asyncio
import random
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import structlog

logger = structlog.get_logger(__name__)

class MockExchange:
    """
    Mock exchange that simulates Bitget API responses
    Used for testing without real money
    """
    
    def __init__(self):
        self.positions = {}
        self.orders = {}
        self.balance = {
            'USDT': {
                'total': 1000.0,
                'free': 900.0,
                'used': 100.0
            }
        }
        self.market_prices = {
            'BTC/USDT:USDT': 50000.0,
            'ETH/USDT:USDT': 3000.0,
            'TEST/USDT:USDT': 100.0
        }
        self.order_id_counter = 1000
        
    async def fetch_balance(self) -> Dict:
        """Simulate fetching account balance"""
        await asyncio.sleep(0.01)  # Simulate network delay
        return self.balance
    
    async def fetch_positions(self) -> List[Dict]:
        """Simulate fetching open positions"""
        await asyncio.sleep(0.01)
        
        positions_list = []
        for key, pos in self.positions.items():
            # Simulate price movement
            symbol = pos['symbol']
            if symbol in self.market_prices:
                # Random price movement (-2% to +2%)
                price_change = random.uniform(0.98, 1.02)
                self.market_prices[symbol] *= price_change
                current_price = self.market_prices[symbol]
                
                # Calculate unrealized PnL
                if pos['side'] == 'LONG':
                    unrealized_pnl = (current_price - pos['entryPrice']) * pos['contracts']
                else:  # SHORT
                    unrealized_pnl = (pos['entryPrice'] - current_price) * pos['contracts']
                
                pos['markPrice'] = current_price
                pos['unrealizedPnl'] = unrealized_pnl
            
            positions_list.append(pos)
        
        return positions_list
    
    async def create_market_order(self, 
                                 symbol: str, 
                                 side: str, 
                                 amount: float,
                                 params: Dict = None) -> Dict:
        """Simulate creating a market order"""
        await asyncio.sleep(0.02)  # Simulate network delay
        
        # Generate order ID
        order_id = f"ORDER_{self.order_id_counter}"
        self.order_id_counter += 1
        
        # Get current price
        price = self.market_prices.get(symbol, 100.0)
        
        # Handle reduce-only orders (closing positions)
        if params and params.get('reduceOnly'):
            # Find and reduce/close position
            for key, pos in list(self.positions.items()):
                if pos['symbol'] == symbol:
                    if pos['contracts'] <= amount:
                        # Close entire position
                        del self.positions[key]
                        logger.info("Mock: Position closed",
                                  symbol=symbol,
                                  size=pos['contracts'])
                    else:
                        # Reduce position
                        pos['contracts'] -= amount
                        logger.info("Mock: Position reduced",
                                  symbol=symbol,
                                  reduced_by=amount,
                                  remaining=pos['contracts'])
                    break
        else:
            # Open new position or add to existing
            position_key = f"{symbol}:{side.upper()}"
            
            if position_key in self.positions:
                # Add to existing position
                pos = self.positions[position_key]
                old_size = pos['contracts']
                old_price = pos['entryPrice']
                new_size = old_size + amount
                
                # Recalculate average entry price
                pos['entryPrice'] = (old_price * old_size + price * amount) / new_size
                pos['contracts'] = new_size
                
                logger.info("Mock: Position increased",
                          symbol=symbol,
                          side=side,
                          added=amount,
                          total=new_size)
            else:
                # Create new position
                self.positions[position_key] = {
                    'symbol': symbol,
                    'side': side.upper(),
                    'contracts': amount,
                    'entryPrice': price,
                    'markPrice': price,
                    'unrealizedPnl': 0.0
                }
                
                logger.info("Mock: Position opened",
                          symbol=symbol,
                          side=side,
                          size=amount,
                          price=price)
        
        # Create order response
        order = {
            'id': order_id,
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'price': price,
            'status': 'closed',  # Market orders execute immediately
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        self.orders[order_id] = order
        return order
    
    async def close(self):
        """Close mock exchange connection"""
        logger.info("Mock exchange closed")
    
    def set_price(self, symbol: str, price: float):
        """Manually set price for testing"""
        self.market_prices[symbol] = price
        logger.info(f"Mock: Price set for {symbol}: {price}")
    
    def inject_position(self, symbol: str, side: str, size: float, entry_price: float):
        """Inject a position for testing"""
        position_key = f"{symbol}:{side.upper()}"
        self.positions[position_key] = {
            'symbol': symbol,
            'side': side.upper(),
            'contracts': size,
            'entryPrice': entry_price,
            'markPrice': entry_price,
            'unrealizedPnl': 0.0
        }
        self.market_prices[symbol] = entry_price
        logger.info(f"Mock: Position injected - {symbol} {side} {size} @ {entry_price}")
    
    def clear_all(self):
        """Clear all positions and orders"""
        self.positions.clear()
        self.orders.clear()
        logger.info("Mock: All positions and orders cleared")