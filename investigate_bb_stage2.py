#!/usr/bin/env python3
"""Deep investigation of BB position and Stage 2 surplus dump"""

import ccxt
import json
from datetime import datetime

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
    'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
    'password': '2609Luiza',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

print("="*70)
print("BB POSITION STAGE 2 SURPLUS DUMP INVESTIGATION")
print("="*70)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Get current positions
positions = exchange.fetch_positions()
bb_position = None

for pos in positions:
    if 'BB' in pos['symbol']:
        bb_position = pos
        break

if not bb_position:
    print("❌ No BB position found!")
    exit()

print("📊 CURRENT BB POSITION:")
print("-"*40)
print(f"Symbol:        {bb_position['symbol']}")
print(f"Side:          {bb_position['side']}")
print(f"Contracts:     {bb_position['contracts']}")
print(f"Entry Price:   ${bb_position['entryPrice']:.4f}")
print(f"Mark Price:    ${bb_position['markPrice']:.4f}")
print(f"UPNL:          ${bb_position['unrealizedPnl']:.2f} ({bb_position['percentage']:.1f}%)")
print()

# Check for historical data
try:
    # Look for position state file
    with open('/app/position_state.json', 'r') as f:
        position_states = json.load(f)
        
    if 'BB/USDT:USDT' in position_states:
        bb_state = position_states['BB/USDT:USDT']
        print("📁 STORED POSITION STATE:")
        print("-"*40)
        for key, value in bb_state.items():
            print(f"{key:20}: {value}")
        print()
except:
    print("⚠️ No stored position state found")
    bb_state = {}

# Calculate Stage 2 requirements
print("🎯 STAGE 2 SURPLUS DUMP ANALYSIS:")
print("-"*40)

# Check if position has averaged (need historical trades)
try:
    trades = exchange.fetch_my_trades(bb_position['symbol'], limit=50)
    
    # Analyze trades for averaging pattern
    buy_trades = []
    sell_trades = []
    
    for trade in trades:
        if trade['side'] == 'buy':
            buy_trades.append(trade)
        else:
            sell_trades.append(trade)
    
    print(f"Trade History: {len(buy_trades)} buys, {len(sell_trades)} sells")
    
    # For short position, buy trades during loss = averaging
    if bb_position['side'] == 'short':
        averaging_trades = [t for t in buy_trades if t['price'] > bb_position['entryPrice']]
        if averaging_trades:
            print(f"✅ Averaging detected: {len(averaging_trades)} cover trades above entry")
    else:
        averaging_trades = [t for t in sell_trades if t['price'] < bb_position['entryPrice']]
        if averaging_trades:
            print(f"✅ Averaging detected: {len(averaging_trades)} sell trades below entry")
    
except Exception as e:
    print(f"⚠️ Could not fetch trade history: {e}")
    averaging_trades = []

print()
print("🔍 SURPLUS DUMP TRIGGER CONDITIONS:")
print("-"*40)

# Determine peak UPNL (would need historical monitoring)
current_upnl = bb_position['unrealizedPnl']

# Simulate different peak scenarios
peak_scenarios = [
    current_upnl * 1.5,  # Peak was 50% higher
    current_upnl * 2.0,  # Peak was 2x current
    current_upnl * 3.0,  # Peak was 3x current
]

print("For current UPNL of ${:.2f}:".format(current_upnl))
print()

for i, peak in enumerate(peak_scenarios, 1):
    if peak > 0.15:  # Must be profitable after averaging
        stage1_trigger = peak * 0.85
        stage2_trigger = peak * 0.30
        
        print(f"Scenario {i}: Peak UPNL = ${peak:.2f}")
        print(f"  Stage 1 (85%): Triggers at ${stage1_trigger:.2f}")
        if current_upnl <= stage1_trigger:
            print(f"    ✅ WOULD TRIGGER NOW (current ${current_upnl:.2f} <= ${stage1_trigger:.2f})")
        else:
            print(f"    ❌ Not ready (need to drop ${current_upnl - stage1_trigger:.2f})")
        
        print(f"  Stage 2 (30%): Triggers at ${stage2_trigger:.2f}")
        if current_upnl <= stage2_trigger:
            print(f"    ✅ WOULD TRIGGER NOW (current ${current_upnl:.2f} <= ${stage2_trigger:.2f})")
        else:
            distance = current_upnl - stage2_trigger
            price_move = (distance / current_upnl) * 100 if current_upnl > 0 else 0
            print(f"    ❌ Not ready (need to drop ${distance:.2f} or {price_move:.1f}%)")
        print()

print("📋 KEY FINDINGS:")
print("-"*40)

# Check actual conditions
if current_upnl > 0.15:
    print("✅ Position is profitable (>${:.2f})".format(0.15))
else:
    print("❌ Position needs to be >${:.2f} profit for surplus zone".format(0.15))

if averaging_trades:
    print("✅ Averaging has occurred")
else:
    print("⚠️ No clear averaging pattern found")

print()
print("🚨 STAGE 2 REQUIREMENTS:")
print("-"*40)
print("1. Position must have averaged during drawdown")
print("2. Position must recover to profit (>$0.15 UPNL)")
print("3. Peak UPNL must be recorded while in profit")
print("4. Stage 1 executes at 85% of peak (50% dump)")
print("5. Stage 2 executes at 30% of peak (remaining 50% dump)")
print()

# Final recommendation
if current_upnl > 0.15:
    estimated_peak = current_upnl * 1.2  # Conservative estimate
    stage2_trigger = estimated_peak * 0.30
    
    print("💡 RECOMMENDATION:")
    print(f"  BB position UPNL: ${current_upnl:.2f}")
    print(f"  If peak was ~${estimated_peak:.2f}:")
    print(f"  Stage 2 would trigger at ${stage2_trigger:.2f}")
    print(f"  Current distance: ${current_upnl - stage2_trigger:.2f}")
    print()
    print("  Position needs continuous monitoring to track peak UPNL")
    print("  and execute Stage 2 automatically when UPNL drops to 30% of peak")