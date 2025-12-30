#!/usr/bin/env python3
"""
Seamless Auto-Syncing Trading System for AI-XYZ
100% Automated - No Manual Intervention Required
"""

import ccxt
import asyncio
import os
import sys
import json
import redis
import logging
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime
import time
from typing import Optional, Dict, Any, List
import signal
import threading

# Load environment
load_dotenv('/app/.env')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/seamless_system.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('SeamlessSystem')

class SeamlessTrading:
    def __init__(self):
        """Initialize the seamless trading system"""
        # Exchange connection
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET') or os.getenv('BITGET_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'defaultMarginMode': 'isolated'
            }
        })
        
        # Redis connection
        self.redis = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        
        # Test thresholds for compliance
        self.averaging_threshold = -0.10  # -10% for testing (was -15%)
        self.profit_threshold = 0.10      # +10% for testing (was +15%)
        self.surplus_threshold = 0.10     # +10% for surplus dump
        self.stop_loss_threshold = -0.50  # -50% stop loss
        
        # Position tracking
        self.positions = {}
        self.running = True
        
        logger.info("="*60)
        logger.info("SEAMLESS AUTO-SYNCING TRADING SYSTEM")
        logger.info("100% Automated - No Manual Intervention")
        logger.info("="*60)
        
    async def initialize(self):
        """Initialize all connections"""
        try:
            await self.exchange.load_markets()
            logger.info("✅ Exchange connected")
            
            # Test Redis
            self.redis.ping()
            logger.info("✅ Redis connected")
            
            logger.info("✅ System initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Initialization failed: {e}")
            return False
    
    def calculate_pnl_pct(self, entry: float, current: float, side: str) -> float:
        """Calculate P&L percentage correctly"""
        if side.lower() in ['short', 'sell']:
            return ((entry - current) / entry) * 100
        else:
            return ((current - entry) / entry) * 100
    
    async def sync_positions(self):
        """Continuously sync positions with exchange"""
        while self.running:
            try:
                # Get live positions from exchange
                positions = await self.exchange.fetch_positions()
                
                for pos in positions:
                    if pos['contracts'] > 0:
                        symbol = pos['symbol']
                        side = pos['side']
                        entry = pos['entryPrice']
                        current = pos['markPrice']
                        size = pos['contracts']
                        upnl = pos['unrealizedPnl']
                        
                        # Calculate real P&L percentage
                        pnl_pct = self.calculate_pnl_pct(entry, current, side)
                        
                        # Store in memory
                        self.positions[symbol] = {
                            'symbol': symbol,
                            'side': side,
                            'entry_price': entry,
                            'current_price': current,
                            'size': size,
                            'upnl': upnl,
                            'pnl_pct': pnl_pct,
                            'averaging_steps': 0,  # Track from Redis
                            'in_surplus': False,
                            'peak_pnl': pnl_pct
                        }
                        
                        # Update Redis
                        self.update_redis(symbol, self.positions[symbol])
                        
                        # Check for actions
                        await self.check_position_actions(symbol)
                
                # Clean up closed positions
                current_symbols = {p['symbol'] for p in positions if p['contracts'] > 0}
                self.positions = {s: p for s, p in self.positions.items() if s in current_symbols}
                
            except Exception as e:
                logger.error(f"Sync error: {e}")
            
            await asyncio.sleep(5)  # Sync every 5 seconds
    
    def update_redis(self, symbol: str, position: Dict):
        """Update position in Redis"""
        key = f'seamless_position:{symbol}'
        self.redis.hset(key, mapping={
            'symbol': position['symbol'],
            'side': position['side'],
            'entry_price': str(position['entry_price']),
            'current_price': str(position['current_price']),
            'size': str(position['size']),
            'upnl': str(position['upnl']),
            'pnl_pct': str(position['pnl_pct']),
            'averaging_steps': str(position.get('averaging_steps', 0)),
            'in_surplus': str(position.get('in_surplus', False)),
            'peak_pnl': str(position.get('peak_pnl', position['pnl_pct'])),
            'last_update': datetime.now().isoformat()
        })
    
    async def check_position_actions(self, symbol: str):
        """Check if any actions needed for position"""
        pos = self.positions.get(symbol)
        if not pos:
            return
        
        pnl_pct = pos['pnl_pct']
        avg_steps = pos.get('averaging_steps', 0)
        
        # Stop Loss Check
        if pnl_pct <= self.stop_loss_threshold * 100:
            logger.warning(f"⛔ STOP LOSS triggered for {symbol} at {pnl_pct:.2f}%")
            await self.close_position(symbol, "STOP_LOSS")
            return
        
        # Averaging Check (only if not averaged yet)
        if pnl_pct <= self.averaging_threshold * 100 and avg_steps < 4:
            logger.info(f"📉 Averaging opportunity for {symbol} at {pnl_pct:.2f}%")
            await self.execute_averaging(symbol)
            return
        
        # Surplus Dump Check (only if has averaged)
        if avg_steps > 0 and pnl_pct >= self.surplus_threshold * 100:
            if not pos.get('in_surplus'):
                logger.info(f"💰 SURPLUS DUMP zone entered for {symbol} at {pnl_pct:.2f}%")
                pos['in_surplus'] = True
                pos['peak_pnl'] = pnl_pct
            
            # Check dump thresholds
            peak_ratio = pnl_pct / pos['peak_pnl'] if pos['peak_pnl'] > 0 else 1
            if peak_ratio <= 0.85:  # 85% of peak
                await self.execute_surplus_dump(symbol, 0.5)
            elif peak_ratio <= 0.50:  # 50% of peak
                await self.execute_surplus_dump(symbol, 0.5)
            return
        
        # Profit Taking Check (only if no averaging)
        if avg_steps == 0 and pnl_pct >= self.profit_threshold * 100:
            logger.info(f"🎯 PROFIT TAKING for {symbol} at {pnl_pct:.2f}%")
            await self.take_profit(symbol)
    
    async def execute_averaging(self, symbol: str):
        """Execute averaging for position"""
        try:
            pos = self.positions[symbol]
            
            # Calculate averaging size (increase by 1.618x golden ratio)
            avg_size = pos['size'] * 1.618
            
            logger.info(f"="*50)
            logger.info(f"📊 EXECUTING AVERAGING - {symbol}")
            logger.info(f"  Current P&L: {pos['pnl_pct']:.2f}%")
            logger.info(f"  Adding: {avg_size:.2f} contracts")
            
            # Place order
            side = 'buy' if pos['side'] == 'long' else 'sell'
            order = await self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=avg_size,
                params={'marginMode': 'isolated'}
            )
            
            # Update position
            pos['averaging_steps'] = pos.get('averaging_steps', 0) + 1
            pos['size'] += avg_size
            
            logger.info(f"✅ Averaging complete - Step {pos['averaging_steps']}")
            logger.info(f"="*50)
            
        except Exception as e:
            logger.error(f"Averaging failed: {e}")
    
    async def execute_surplus_dump(self, symbol: str, ratio: float):
        """Execute surplus dump"""
        try:
            pos = self.positions[symbol]
            dump_size = pos['size'] * ratio
            
            logger.info(f"="*50)
            logger.info(f"💰 SURPLUS DUMP - {symbol}")
            logger.info(f"  Dumping: {dump_size:.2f} contracts ({ratio*100:.0f}%)")
            
            # Place order
            side = 'sell' if pos['side'] == 'long' else 'buy'
            order = await self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=dump_size,
                params={'marginMode': 'isolated'}
            )
            
            pos['size'] -= dump_size
            if pos['size'] <= 0.01:
                pos['averaging_steps'] = 0
                pos['in_surplus'] = False
            
            logger.info(f"✅ Surplus dump complete")
            logger.info(f"="*50)
            
        except Exception as e:
            logger.error(f"Surplus dump failed: {e}")
    
    async def take_profit(self, symbol: str):
        """Take profit on position"""
        try:
            pos = self.positions[symbol]
            
            logger.info(f"="*50)
            logger.info(f"🎯 TAKING PROFIT - {symbol}")
            logger.info(f"  P&L: {pos['pnl_pct']:.2f}%")
            logger.info(f"  Profit: ${pos['upnl']:.2f}")
            
            # Close 50% of position
            close_size = pos['size'] * 0.5
            side = 'sell' if pos['side'] == 'long' else 'buy'
            
            order = await self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=close_size,
                params={'marginMode': 'isolated'}
            )
            
            pos['size'] -= close_size
            logger.info(f"✅ Took 50% profit")
            logger.info(f"="*50)
            
        except Exception as e:
            logger.error(f"Profit taking failed: {e}")
    
    async def close_position(self, symbol: str, reason: str):
        """Close entire position"""
        try:
            pos = self.positions[symbol]
            
            logger.info(f"="*50)
            logger.info(f"🔴 CLOSING POSITION - {symbol}")
            logger.info(f"  Reason: {reason}")
            logger.info(f"  P&L: {pos['pnl_pct']:.2f}%")
            
            side = 'sell' if pos['side'] == 'long' else 'buy'
            order = await self.exchange.create_market_order(
                symbol=symbol,
                side=side,
                amount=pos['size'],
                params={'marginMode': 'isolated'}
            )
            
            logger.info(f"✅ Position closed")
            logger.info(f"="*50)
            
        except Exception as e:
            logger.error(f"Close position failed: {e}")
    
    async def display_status(self):
        """Display current status"""
        while self.running:
            try:
                await asyncio.sleep(30)  # Update every 30 seconds
                
                if self.positions:
                    print("\n" + "="*70)
                    print(f"SEAMLESS TRADING SYSTEM - {datetime.now().strftime('%H:%M:%S')}")
                    
                    # Get balance
                    balance = await self.exchange.fetch_balance()
                    total = balance['USDT']['total']
                    free = balance['USDT']['free']
                    print(f"Balance: ${total:.2f} (Free: ${free:.2f})")
                    print("="*70)
                    
                    for symbol, pos in self.positions.items():
                        status = ""
                        if pos['pnl_pct'] <= self.averaging_threshold * 100:
                            status = "📉 AVERAGING ZONE"
                        elif pos.get('in_surplus'):
                            status = "💰 SURPLUS ZONE"
                        elif pos['pnl_pct'] >= self.profit_threshold * 100:
                            status = "🎯 PROFIT ZONE"
                        
                        print(f"\n📊 {symbol}")
                        print(f"  Position: {pos['side'].upper()} {pos['size']:.1f}")
                        print(f"  Entry: ${pos['entry_price']:.4f} → Current: ${pos['current_price']:.4f}")
                        print(f"  P&L: ${pos['upnl']:.2f} ({pos['pnl_pct']:.2f}%)")
                        if pos.get('averaging_steps', 0) > 0:
                            print(f"  Averaging Steps: {pos['averaging_steps']}/4")
                        if status:
                            print(f"  Status: {status}")
                    
                    print("\n" + "="*70)
                    
            except Exception as e:
                logger.error(f"Display error: {e}")
    
    async def run(self):
        """Main run loop"""
        if not await self.initialize():
            return
        
        # Start tasks
        tasks = [
            asyncio.create_task(self.sync_positions()),
            asyncio.create_task(self.display_status())
        ]
        
        try:
            await asyncio.gather(*tasks)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            self.running = False

async def main():
    """Main entry point"""
    system = SeamlessTrading()
    await system.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n✅ System stopped cleanly")