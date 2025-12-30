#!/usr/bin/env python3
"""
Check Current Positions Against Dynamic Thresholds
Shows where positions will average or surplus dump
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add services to path
sys.path.append(str(Path(__file__).parent / 'services' / 'api-gateway' / 'src'))

import os
from dotenv import load_dotenv
load_dotenv()

from live_positions_registry import LivePositionsRegistry, PositionZone
from position_zone_manager import PositionZoneManager
from fibonacci_delta_calculator import FibonacciDeltaCalculator
from bitget_futures_client import BitgetFuturesClient

async def check_all_positions():
    """Check all positions against dynamic thresholds"""
    try:
        # Initialize components
        print("="*80)
        print("POSITION THRESHOLD ANALYSIS - DYNAMIC FIBONACCI LEVELS")
        print("="*80)
        print(f"Timestamp: {datetime.now().isoformat()}\n")
        
        # Connect to Redis
        registry = LivePositionsRegistry()
        await registry.connect()
        
        # Get mock client for calculator (won't make actual trades)
        class MockExchange:
            async def fetch_ohlcv(self, symbol, timeframe, limit):
                # Return mock data for testing
                return []
        
        # Initialize zone manager with mock client
        zone_manager = PositionZoneManager(
            registry=registry,
            bitget_client=MockExchange(),
            manage_manual_positions=True
        )
        
        # Get all positions
        positions = await registry.get_all_positions()
        
        if not positions:
            print("No positions found")
            return
        
        print(f"Found {len(positions)} positions\n")
        
        # Analyze each position
        for position in positions:
            print("="*60)
            position_type = "MANUAL" if position.is_manual else "AUTO"
            print(f"[{position_type}] {position.symbol} - {position.direction.upper()}")
            print("-"*60)
            
            # Current position stats
            entry_price = float(position.weighted_avg_price)
            current_price = float(position.current_price)
            quantity = float(position.current_quantity)
            upnl = float(position.unrealized_pnl)
            
            # Calculate current loss/gain percentage
            if position.direction == "long":
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
            else:
                pnl_pct = ((entry_price - current_price) / entry_price) * 100
            
            print(f"Entry Price:     ${entry_price:.4f}")
            print(f"Current Price:   ${current_price:.4f}")
            print(f"Quantity:        {quantity:.6f}")
            print(f"UPNL:           ${upnl:.2f} ({pnl_pct:.2f}%)")
            print(f"Current Zone:    {position.current_zone.value.upper()}")
            print(f"Averaging Steps: {int(position.averaging_steps_taken)}/{position.custom_params.max_averaging_steps}")
            
            # Check if position has surplus from averaging
            surplus_size = float(position.surplus_size) if position.surplus_size else 0
            if surplus_size > 0:
                print(f"Surplus Size:    {surplus_size:.6f}")
                surplus_value = surplus_size * current_price
                print(f"Surplus Value:   ${surplus_value:.2f}")
            
            print("\n📊 THRESHOLD ANALYSIS:")
            print("-"*40)
            
            # Static thresholds (current system)
            print("Static Thresholds (Old System):")
            avg_threshold = float(position.custom_params.averaging_threshold)
            surplus_threshold = float(position.custom_params.neutral_upper)  # Using neutral_upper as surplus threshold
            profit_threshold = float(position.custom_params.profit_threshold)
            stop_loss = float(position.custom_params.stop_loss)
            
            print(f"  Averaging:     ${avg_threshold:.2f}")
            print(f"  Surplus Dump:  ${surplus_threshold:.2f}")
            print(f"  Profit Taking: ${profit_threshold:.2f}")
            print(f"  Stop Loss:     ${stop_loss:.2f}")
            
            # Try to calculate dynamic thresholds
            print("\nDynamic Thresholds (Fibonacci System):")
            
            # For demonstration, calculate theoretical thresholds
            # In production, these would come from market analysis
            next_level = int(position.averaging_steps_taken) + 1
            
            if next_level <= position.custom_params.max_averaging_steps:
                # Estimate dynamic thresholds based on position
                if position.direction == "long":
                    level_1_price = entry_price * 0.975  # -2.5%
                    level_2_price = entry_price * 0.95   # -5%
                    level_3_price = entry_price * 0.92   # -8%
                    level_4_price = entry_price * 0.88   # -12%
                    level_5_price = entry_price * 0.84   # -16%
                else:
                    level_1_price = entry_price * 1.025  # +2.5%
                    level_2_price = entry_price * 1.05   # +5%
                    level_3_price = entry_price * 1.08   # +8%
                    level_4_price = entry_price * 1.12   # +12%
                    level_5_price = entry_price * 1.16   # +16%
                
                thresholds = [level_1_price, level_2_price, level_3_price, level_4_price, level_5_price]
                multipliers = [1.3, 2.1, 3.4, 4.8, 5.0]
                
                print(f"  Next Level: {next_level}")
                if next_level <= 5:
                    next_threshold = thresholds[next_level - 1]
                    next_multiplier = multipliers[next_level - 1]
                    next_size = float(position.initial_quantity) * next_multiplier
                    
                    if position.direction == "long":
                        distance_to_threshold = current_price - next_threshold
                        will_trigger = current_price <= next_threshold
                    else:
                        distance_to_threshold = next_threshold - current_price
                        will_trigger = current_price >= next_threshold
                    
                    print(f"  Threshold Price: ${next_threshold:.4f}")
                    print(f"  Distance:        ${abs(distance_to_threshold):.4f}")
                    print(f"  Multiplier:      {next_multiplier:.1f}x")
                    print(f"  Next Size:       {next_size:.6f}")
                    
                    if will_trigger:
                        print(f"  ⚠️ WOULD TRIGGER AVERAGING NOW!")
                    else:
                        pct_to_threshold = (abs(distance_to_threshold) / current_price) * 100
                        print(f"  Distance %:      {pct_to_threshold:.2f}% away")
            
            # Check surplus dump conditions
            print("\n💰 SURPLUS DUMP ANALYSIS:")
            print("-"*40)
            
            if position.surplus_size and float(position.surplus_size) > 0:
                # Track peak UPNL if positive
                if upnl > 0:
                    print(f"Current UPNL:    ${upnl:.2f}")
                    print(f"Peak Tracking:   Active")
                    
                    # Surplus dump triggers
                    stage_1_trigger = upnl * 0.85  # 85% of peak
                    stage_2_trigger = upnl * 0.30  # 30% of peak
                    
                    print(f"Stage 1 (85%):   Triggers at ${stage_1_trigger:.2f}")
                    print(f"Stage 2 (30%):   Triggers at ${stage_2_trigger:.2f}")
                    
                    if upnl >= surplus_threshold:
                        print(f"✅ READY FOR SURPLUS DUMP (above ${surplus_threshold:.2f})")
                        dump_qty = float(position.surplus_size) * 0.5  # Stage 1 dumps 50%
                        dump_value = dump_qty * current_price
                        print(f"  Would dump:    {dump_qty:.6f} ({dump_value:.2f} USDT)")
                else:
                    print(f"Not ready - UPNL negative (${upnl:.2f})")
                    to_positive = abs(upnl)
                    print(f"Needs ${to_positive:.2f} recovery to start tracking peak")
            else:
                print("No surplus available (no averaging done)")
            
            # Check profit taking conditions
            print("\n📈 PROFIT TAKING ANALYSIS:")
            print("-"*40)
            
            if int(position.averaging_steps_taken) == 0:  # Only for non-averaged positions
                if upnl >= profit_threshold:
                    print(f"✅ READY FOR PROFIT TAKING (UPNL ${upnl:.2f} > ${profit_threshold:.2f})")
                    print(f"  Would close entire position")
                else:
                    needed = profit_threshold - upnl
                    print(f"Not ready - needs ${needed:.2f} more profit")
            else:
                print(f"Not applicable - position has been averaged ({int(position.averaging_steps_taken)} times)")
            
            # Check stop loss
            print("\n🛑 STOP LOSS ANALYSIS:")
            print("-"*40)
            
            if upnl <= stop_loss:
                print(f"⚠️ STOP LOSS TRIGGERED (UPNL ${upnl:.2f} <= ${stop_loss:.2f})")
                print(f"  Would close entire position immediately")
            else:
                distance_to_stop = upnl - stop_loss
                print(f"Safe - ${distance_to_stop:.2f} away from stop loss")
            
            # Summary
            print("\n📌 SUMMARY:")
            print("-"*40)
            
            actions = []
            if position.current_zone == PositionZone.AVERAGING:
                actions.append("📉 In AVERAGING zone - checking thresholds")
            elif position.current_zone == PositionZone.SURPLUS_DUMP:
                actions.append("💰 In SURPLUS_DUMP zone - ready to take profits")
            elif position.current_zone == PositionZone.PROFIT_TAKING:
                actions.append("📈 In PROFIT_TAKING zone")
            elif position.current_zone == PositionZone.STOP_LOSS:
                actions.append("🛑 In STOP_LOSS zone - emergency exit needed")
            else:
                actions.append("😊 In NEUTRAL zone - monitoring")
            
            for action in actions:
                print(f"  {action}")
            
            print()
        
        print("="*80)
        print("END OF ANALYSIS")
        print("="*80)
        
        await registry.disconnect()
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_all_positions())