#!/usr/bin/env python3
"""
Simple Trading System for AI XYZ
Self-contained system that actually opens positions
"""

import ccxt
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime
import time

# Load environment
load_dotenv('/app/.env')

class SimpleTradingSystem:
    def __init__(self):
        self.exchange = None
        self.position_size = 5.0  # $5 per position
        self.leverage = 10
        self.max_positions = 1
        self.min_volume = 100000  # $100k daily volume
        
    def initialize(self):
        """Initialize exchange connection"""
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'defaultMarginMode': 'isolated'
            }
        })
        self.exchange.load_markets()
        print(f"[{datetime.now()}] ✅ Exchange initialized")
        
    def get_balance(self):
        """Get USDT balance"""
        try:
            balance = self.exchange.fetch_balance()
            return balance['USDT']['free']
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0
            
    def get_positions(self):
        """Get current positions"""
        try:
            positions = self.exchange.fetch_positions()
            return [p for p in positions if p['contracts'] > 0]
        except Exception as e:
            print(f"Error getting positions: {e}")
            return []
            
    def find_opportunity(self):
        """Find a simple trading opportunity"""
        try:
            # Get top volume symbols
            tickers = self.exchange.fetch_tickers()
            
            # Filter USDT perpetuals with good volume
            candidates = []
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT:USDT') and ticker.get('quoteVolume', 0) > self.min_volume:
                    # Simple momentum check
                    if ticker['percentage'] > 2:  # Bullish momentum
                        candidates.append({
                            'symbol': symbol,
                            'side': 'buy',
                            'percentage': ticker['percentage'],
                            'volume': ticker['quoteVolume']
                        })
                    elif ticker['percentage'] < -2:  # Bearish momentum
                        candidates.append({
                            'symbol': symbol,
                            'side': 'sell',
                            'percentage': ticker['percentage'],
                            'volume': ticker['quoteVolume']
                        })
            
            # Sort by absolute percentage change
            candidates.sort(key=lambda x: abs(x['percentage']), reverse=True)
            
            return candidates[0] if candidates else None
            
        except Exception as e:
            print(f"Error finding opportunity: {e}")
            return None
            
    def open_position(self, symbol, side):
        """Open a position"""
        try:
            market = self.exchange.market(symbol)
            ticker = self.exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            # Calculate position size
            amount = (self.position_size * self.leverage) / price
            amount = self.exchange.amount_to_precision(symbol, amount)
            
            # Set leverage
            self.exchange.set_leverage(self.leverage, symbol)
            
            # Place order
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=amount,
                params={'marginMode': 'isolated'}
            )
            
            print(f"[{datetime.now()}] ✅ Opened {side} position on {symbol}")
            print(f"  Amount: {amount}, Price: {price}, Size: ${self.position_size}")
            
            return order
            
        except Exception as e:
            print(f"Error opening position: {e}")
            return None
            
    def run(self):
        """Main trading loop"""
        print(f"[{datetime.now()}] Starting Simple Trading System")
        
        self.initialize()
        
        while True:
            try:
                # Check balance
                balance = self.get_balance()
                print(f"[{datetime.now()}] Balance: ${balance:.2f}")
                
                # Check positions
                positions = self.get_positions()
                print(f"[{datetime.now()}] Active positions: {len(positions)}")
                
                if len(positions) > 0:
                    for pos in positions:
                        pnl = pos.get('unrealizedPnl', 0)
                        print(f"  - {pos['symbol']}: {pos['side']} {pos['contracts']} contracts, PnL: ${pnl:.2f}")
                
                # Only open new position if we have none
                if len(positions) < self.max_positions and balance >= self.position_size:
                    opportunity = self.find_opportunity()
                    
                    if opportunity:
                        print(f"[{datetime.now()}] Found opportunity: {opportunity['symbol']} {opportunity['side']}")
                        self.open_position(opportunity['symbol'], opportunity['side'])
                    else:
                        print(f"[{datetime.now()}] No opportunities found")
                        
                # Wait before next check
                time.sleep(30)
                
            except Exception as e:
                print(f"[{datetime.now()}] Error in main loop: {e}")
                time.sleep(60)

if __name__ == "__main__":
    system = SimpleTradingSystem()
    system.run()