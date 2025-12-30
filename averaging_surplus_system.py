#!/usr/bin/env python3
"""
Averaging and Surplus Dump Trading System for AI XYZ
Implements proper DCA and surplus dump mechanics
"""

import ccxt
import asyncio
import os
import json
from dotenv import load_dotenv
from datetime import datetime
import time
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict

load_dotenv('/app/.env')

@dataclass
class AveragingStep:
    """Record of each averaging action"""
    step_number: int
    price: float
    quantity: float
    timestamp: str
    order_id: str

@dataclass
class Position:
    """Enhanced position tracking with averaging data"""
    symbol: str
    side: str
    original_quantity: float
    original_entry: float
    current_quantity: float
    weighted_avg_price: float
    averaging_steps: List[AveragingStep]
    peak_upnl: float = 0
    is_in_surplus_zone: bool = False
    surplus_quantity: float = 0
    
class AveragingSurplusSystem:
    def __init__(self):
        self.exchange = None
        self.positions = {}  # Track our enhanced position data
        
        # Configuration
        self.original_size = 5.0  # $5 base position
        self.leverage = 10
        
        # Averaging thresholds
        self.averaging_levels = [-0.05, -0.15, -0.30]  # -5%, -15%, -30%
        self.averaging_multipliers = [1.5, 2.0, 2.5]  # Size multipliers for each level
        
        # Surplus dump thresholds
        self.surplus_trigger = 0.15  # +15% profit to enter surplus zone
        self.surplus_dump_levels = [0.85, 0.50]  # Dump at 85% and 50% of peak
        
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
        print(f"[{datetime.now()}] ✅ Averaging & Surplus System Initialized")
        
    def calculate_upnl_percentage(self, entry_price, current_price, side):
        """Calculate unrealized P&L percentage"""
        if side == 'buy':
            return (current_price - entry_price) / entry_price
        else:
            return (entry_price - current_price) / entry_price
            
    def should_average(self, position: Position, current_price: float) -> Optional[int]:
        """Check if position should be averaged"""
        upnl_pct = self.calculate_upnl_percentage(
            position.weighted_avg_price, 
            current_price, 
            position.side
        )
        
        steps_taken = len(position.averaging_steps)
        
        # Check each averaging level
        for i, threshold in enumerate(self.averaging_levels):
            if i >= steps_taken and upnl_pct <= threshold:
                return i  # Return which averaging step to take
                
        return None
        
    def execute_averaging(self, position: Position, current_price: float, step_index: int):
        """Execute averaging down on a position"""
        try:
            symbol = position.symbol
            
            # Calculate averaging size
            multiplier = self.averaging_multipliers[step_index]
            avg_size_usd = self.original_size * multiplier
            amount = (avg_size_usd * self.leverage) / current_price
            amount = self.exchange.amount_to_precision(symbol, amount)
            
            print(f"[{datetime.now()}] 📉 AVERAGING DOWN on {symbol}")
            print(f"  Step: {step_index + 1}/3")
            print(f"  Current loss: {self.calculate_upnl_percentage(position.weighted_avg_price, current_price, position.side):.2%}")
            print(f"  Adding: {amount} contracts (${avg_size_usd})")
            
            # Place averaging order
            order = self.exchange.create_market_order(
                symbol=symbol,
                side=position.side,
                amount=amount,
                params={'marginMode': 'isolated'}
            )
            
            # Update position data
            old_total_value = position.current_quantity * position.weighted_avg_price
            new_total_value = old_total_value + (amount * current_price)
            new_total_quantity = position.current_quantity + amount
            
            position.weighted_avg_price = new_total_value / new_total_quantity
            position.current_quantity = new_total_quantity
            position.surplus_quantity += amount  # Track surplus
            
            # Record averaging step
            step = AveragingStep(
                step_number=step_index + 1,
                price=current_price,
                quantity=amount,
                timestamp=datetime.now().isoformat(),
                order_id=order['id']
            )
            position.averaging_steps.append(step)
            
            print(f"  ✅ New avg price: ${position.weighted_avg_price:.6f}")
            print(f"  Total size: {position.current_quantity} contracts")
            
            return True
            
        except Exception as e:
            print(f"Error averaging position: {e}")
            return False
            
    def check_surplus_dump(self, position: Position, current_price: float):
        """Check and execute surplus dump if conditions met"""
        if position.surplus_quantity <= 0:
            return  # No surplus to dump
            
        upnl_pct = self.calculate_upnl_percentage(
            position.weighted_avg_price,
            current_price,
            position.side
        )
        
        # Enter surplus zone if profitable after averaging
        if not position.is_in_surplus_zone and upnl_pct >= self.surplus_trigger:
            position.is_in_surplus_zone = True
            position.peak_upnl = upnl_pct
            print(f"[{datetime.now()}] 🎯 {position.symbol} entered SURPLUS DUMP ZONE")
            print(f"  Peak profit: {upnl_pct:.2%}")
            
        # Update peak if higher
        if position.is_in_surplus_zone and upnl_pct > position.peak_upnl:
            position.peak_upnl = upnl_pct
            
        # Check for surplus dump triggers
        if position.is_in_surplus_zone and position.surplus_quantity > 0:
            peak_ratio = upnl_pct / position.peak_upnl if position.peak_upnl > 0 else 0
            
            # First dump at 85% of peak
            if peak_ratio <= self.surplus_dump_levels[0] and position.surplus_quantity == position.surplus_quantity:
                self.execute_surplus_dump(position, 0.5)  # Dump 50%
                
            # Second dump at 50% of peak
            elif peak_ratio <= self.surplus_dump_levels[1]:
                self.execute_surplus_dump(position, 1.0)  # Dump remaining
                
    def execute_surplus_dump(self, position: Position, dump_ratio: float):
        """Execute surplus dump"""
        try:
            dump_quantity = position.surplus_quantity * dump_ratio
            dump_quantity = self.exchange.amount_to_precision(position.symbol, dump_quantity)
            
            print(f"[{datetime.now()}] 💰 SURPLUS DUMP on {position.symbol}")
            print(f"  Dumping: {dump_quantity} contracts ({dump_ratio*100:.0f}% of surplus)")
            
            # Place sell order
            order = self.exchange.create_market_order(
                symbol=position.symbol,
                side='sell' if position.side == 'buy' else 'buy',
                amount=dump_quantity,
                params={'marginMode': 'isolated'}
            )
            
            # Update position
            position.current_quantity -= dump_quantity
            position.surplus_quantity -= dump_quantity
            
            if position.surplus_quantity <= 0:
                position.is_in_surplus_zone = False
                position.averaging_steps = []
                print(f"  ✅ Surplus fully dumped, returning to original size")
                
        except Exception as e:
            print(f"Error executing surplus dump: {e}")
            
    def sync_positions(self):
        """Sync positions with exchange"""
        try:
            exchange_positions = self.exchange.fetch_positions()
            
            for ex_pos in exchange_positions:
                if ex_pos['contracts'] > 0:
                    symbol = ex_pos['symbol']
                    
                    # Create or update position tracking
                    if symbol not in self.positions:
                        self.positions[symbol] = Position(
                            symbol=symbol,
                            side=ex_pos['side'],
                            original_quantity=ex_pos['contracts'],
                            original_entry=ex_pos['entryPrice'],
                            current_quantity=ex_pos['contracts'],
                            weighted_avg_price=ex_pos['entryPrice'],
                            averaging_steps=[]
                        )
                    
                    # Get current price
                    ticker = self.exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                    
                    position = self.positions[symbol]
                    
                    # Check for averaging
                    avg_step = self.should_average(position, current_price)
                    if avg_step is not None:
                        balance = self.exchange.fetch_balance()
                        free_balance = balance['USDT']['free']
                        
                        required_size = self.original_size * self.averaging_multipliers[avg_step]
                        if free_balance >= required_size:
                            self.execute_averaging(position, current_price, avg_step)
                        else:
                            print(f"[{datetime.now()}] ⚠️ Insufficient balance for averaging")
                            
                    # Check for surplus dump
                    self.check_surplus_dump(position, current_price)
                    
            # Remove closed positions
            current_symbols = {p['symbol'] for p in exchange_positions if p['contracts'] > 0}
            self.positions = {s: p for s, p in self.positions.items() if s in current_symbols}
            
        except Exception as e:
            print(f"Error syncing positions: {e}")
            
    def display_status(self):
        """Display current system status"""
        try:
            balance = self.exchange.fetch_balance()
            print(f"\n{'='*60}")
            print(f"System Status - {datetime.now().strftime('%H:%M:%S')}")
            print(f"Balance: ${balance['USDT']['total']:.2f}")
            
            for symbol, position in self.positions.items():
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                upnl_pct = self.calculate_upnl_percentage(
                    position.weighted_avg_price,
                    current_price,
                    position.side
                )
                
                print(f"\n📊 {symbol}")
                print(f"  Size: {position.current_quantity} contracts")
                print(f"  Avg Entry: ${position.weighted_avg_price:.6f}")
                print(f"  Current: ${current_price:.6f}")
                print(f"  UPNL: {upnl_pct:.2%}")
                print(f"  Averaging Steps: {len(position.averaging_steps)}/3")
                
                if position.is_in_surplus_zone:
                    print(f"  💰 IN SURPLUS ZONE")
                    print(f"  Peak: {position.peak_upnl:.2%}")
                    print(f"  Surplus: {position.surplus_quantity} contracts")
                    
        except Exception as e:
            print(f"Error displaying status: {e}")
            
    def run(self):
        """Main loop"""
        print(f"[{datetime.now()}] Starting Averaging & Surplus System")
        self.initialize()
        
        while True:
            try:
                self.sync_positions()
                self.display_status()
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                print(f"Error in main loop: {e}")
                time.sleep(60)

if __name__ == "__main__":
    system = AveragingSurplusSystem()
    system.run()