#!/usr/bin/env python3
"""Averaging Executor - Execute safe averaging steps"""

import ccxt
import os
from dotenv import load_dotenv

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

class AveragingExecutor:
    def __init__(self):
        self.fib_multipliers = [1.0, 2.0, 3.0, 5.0, 8.0]
    
    def get_position_data(self, symbol):
        """Get current position data"""
        try:
            positions = exchange.fetch_positions([symbol])
            for pos in positions:
                if pos['symbol'] == symbol and pos['contracts'] > 0:
                    return {
                        'amount': pos['contracts'],
                        'side': pos['side'],
                        'entry_price': pos.get('entryPrice', 0),
                        'leverage': pos.get('leverage', 8),
                        'pnl_pct': pos['percentage']
                    }
        except Exception as e:
            print(f"Error fetching position: {e}")
        return None
    
    def execute_averaging_step(self, symbol, current_step):
        """Execute averaging step for position"""
        position = self.get_position_data(symbol)
        if not position:
            print(f"❌ No position found for {symbol}")
            return False
        
        multiplier = self.fib_multipliers[current_step]
        amount_to_add = position['amount'] * multiplier * 0.5  # Conservative sizing
        
        print(f"📊 {symbol} Averaging Step {current_step + 1}:")
        print(f"   Current P&L: {position['pnl_pct']:.1f}%")
        print(f"   Adding {amount_to_add:.2f} contracts (x{multiplier})")
        
        # Check margin
        balance = exchange.fetch_balance()
        available_margin = balance['USDT']['free']
        required_margin = amount_to_add * position['entry_price'] / position['leverage']
        print(f"   Available Margin: ${available_margin:.2f}")
        print(f"   Required Margin: ${required_margin:.2f}")
        
        if available_margin < required_margin * 1.1:  # 10% buffer
            print("❌ Insufficient margin for averaging")
            return False
        
        # Execute averaging
        try:
            order = exchange.create_market_order(
                symbol=symbol,
                side=position['side'],
                amount=amount_to_add
            )
            print(f"✅ Averaging executed: {order['id']}")
            return True
        except Exception as e:
            print(f"❌ Averaging failed: {e}")
            return False

if __name__ == '__main__':
    executor = AveragingExecutor()
    print("🔍 Checking PIPPIN status...")
    executor.execute_averaging_step('PIPPIN/USDT:USDT', 0)