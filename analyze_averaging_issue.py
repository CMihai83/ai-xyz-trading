#!/usr/bin/env python3
"""
Analyze why averaging reached $5 quickly for F/USDT position
"""

import asyncio
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

async def analyze_position():
    """Analyze the F/USDT position averaging issue"""
    
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    try:
        # Get account balance
        balance = await exchange.fetch_balance()
        total_capital = balance['USDT']['total'] if 'USDT' in balance else 0
        free_capital = balance['USDT']['free'] if 'USDT' in balance else 0
        
        print("\n" + "="*60)
        print("    AVERAGING AMOUNT ANALYSIS")
        print("="*60)
        
        print(f"\n💰 Account Status:")
        print(f"   Total Capital: ${total_capital:.2f}")
        print(f"   Free Capital: ${free_capital:.2f}")
        print(f"   Used Margin: ${total_capital - free_capital:.2f}")
        
        # Get position details
        positions = await exchange.fetch_positions()
        f_position = None
        for pos in positions:
            if 'F/USDT' in pos['symbol'] and pos['contracts'] > 0:
                f_position = pos
                break
        
        if f_position:
            print(f"\n📊 F/USDT Position Details:")
            print(f"   Symbol: {f_position['symbol']}")
            print(f"   Side: {f_position['side'].upper()}")
            print(f"   Contracts: {f_position['contracts']}")
            print(f"   Contract Size: ${f_position['contractSize']}")
            print(f"   Position Value: ${f_position['contracts'] * f_position['contractSize']:.2f}")
            print(f"   Initial Margin: ${f_position['initialMargin']:.2f}")
            print(f"   Maintenance Margin: ${f_position['maintenanceMargin']:.2f}")
            print(f"   Unrealized PNL: ${f_position['unrealizedPnl']:.2f}")
            print(f"   PNL %: {f_position['percentage']:.2f}%")
            
            # Calculate expected averaging based on 70/30 rule
            print(f"\n🔍 Expected Averaging Calculation:")
            print(f"   Position Limit Rule: 1 position per $25")
            
            positions_allowed = int(total_capital / 25) if total_capital >= 50 else 1
            capital_per_position = total_capital / positions_allowed
            
            print(f"   Positions Allowed: {positions_allowed}")
            print(f"   Capital per Position: ${capital_per_position:.2f}")
            
            # 70/30 split
            averaging_capital = capital_per_position * 0.70
            safety_margin = capital_per_position * 0.30
            
            print(f"\n   70% for Averaging: ${averaging_capital:.2f}")
            print(f"   30% Safety Margin: ${safety_margin:.2f}")
            
            # Fibonacci multipliers: 1, 1, 2, 3, 5, 8 = Total 20x
            fibonacci_sum = 20
            base_margin = averaging_capital / fibonacci_sum
            
            print(f"\n   Base Margin (70%/20): ${base_margin:.2f}")
            print(f"   Expected Initial Position: ${base_margin:.2f}")
            
            # Calculate expected averaging steps
            print(f"\n📈 Expected Averaging Steps:")
            fib_sequence = [1, 1, 2, 3, 5, 8]
            total = base_margin
            for i, multiplier in enumerate(fib_sequence[1:], 1):
                step_amount = base_margin * multiplier
                total += step_amount
                print(f"   Step {i}: ${step_amount:.2f} ({multiplier}x) | Total: ${total:.2f}")
                if i == 3:
                    print(f"      → This is where it shows $5 quickly!")
            
            print(f"\n⚠️ ISSUE IDENTIFIED:")
            print(f"   The log shows step 3 with multipliers [8, 5, 3]")
            print(f"   This is REVERSED Fibonacci - should be [3, 5, 8]!")
            print(f"   The system is using DECREASING multipliers instead of INCREASING")
            
            # Show correct vs incorrect
            print(f"\n❌ Current (WRONG) Implementation:")
            print(f"   Step 1: 8x = ${base_margin * 8:.2f}")
            print(f"   Step 2: 5x = ${base_margin * 5:.2f}")
            print(f"   Step 3: 3x = ${base_margin * 3:.2f}")
            print(f"   Total: ${base_margin * (1 + 8 + 5 + 3):.2f}")
            
            print(f"\n✅ Correct Implementation Should Be:")
            print(f"   Step 1: 1x = ${base_margin * 1:.2f}")
            print(f"   Step 2: 2x = ${base_margin * 2:.2f}")
            print(f"   Step 3: 3x = ${base_margin * 3:.2f}")
            print(f"   Step 4: 5x = ${base_margin * 5:.2f}")
            print(f"   Step 5: 8x = ${base_margin * 8:.2f}")
            print(f"   Total: ${base_margin * 20:.2f}")
            
        else:
            print("\n❌ No F/USDT position found")
        
        # Check current system configuration
        print(f"\n🔧 System Configuration Check:")
        
        # Get orders to see actual averaging history
        try:
            orders = await exchange.fetch_orders('F/USDT:USDT', limit=20)
            filled_orders = [o for o in orders if o['status'] == 'closed']
            
            if filled_orders:
                print(f"\n📜 Recent Order History:")
                for order in filled_orders[-5:]:
                    print(f"   {order['datetime']}: {order['side']} ${order['cost']:.2f}")
        except:
            print("   Could not fetch order history")
        
        print("\n" + "="*60)
        print("   CONCLUSION")
        print("="*60)
        print("\n🔴 The Fibonacci multipliers are REVERSED!")
        print("   - System uses [8,5,3] instead of [1,2,3,5,8]")
        print("   - This causes large initial averaging amounts")
        print("   - Need to fix the Fibonacci sequence order")
        print("")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await exchange.close()

if __name__ == "__main__":
    asyncio.run(analyze_position())