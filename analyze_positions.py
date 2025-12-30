#!/usr/bin/env python3
import json
from datetime import datetime

with open('position_state.json', 'r') as f:
    data = json.load(f)
    
print('=== POSITION HISTORY ANALYSIS - SURPLUS DUMP VERIFICATION ===')
print(f'Report generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')

print('=== POSITIONS WITH AVERAGING HISTORY ===')
print('These positions had multipliers > 1.0, indicating averaging occurred:\n')

positions_with_averaging = []
for symbol, multipliers in data['position_multipliers'].items():
    max_mult = max(multipliers)
    if max_mult > 1.0:
        positions_with_averaging.append(symbol)
        print(f'📊 {symbol}:')
        print(f'  Multipliers: {[f"{m:.2f}x" for m in multipliers]}')
        print(f'  Max multiplier: {max_mult:.2f}x')
        averaging_steps = len([m for m in multipliers if m > 1.0])
        print(f'  Averaging steps taken: {averaging_steps}')
        
        # Check if this position is still active
        if symbol in data['active_positions']:
            print(f'  ✅ STILL ACTIVE - Position not closed yet')
        else:
            print(f'  ❌ CLOSED - Position no longer active')
            print(f'  ⚠️ REVIEW NEEDED: Position with averaging was closed')
            print(f'     Need to verify if surplus dump was triggered properly')
        print()

print(f'\nTotal positions with averaging history: {len(positions_with_averaging)}')

print('\n=== CURRENT ACTIVE POSITIONS ===')
for symbol, pos in data['active_positions'].items():
    zone = data['position_zones'].get(symbol, 'NEUTRAL')
    steps = data['averaging_steps'].get(symbol, 0)
    peak = data['peak_upnl'].get(symbol, 0)
    peak_timestamp = data['peak_upnl_timestamps'].get(symbol)
    surplus_stage = data['surplus_dump_stage'].get(symbol, 0)
    
    print(f'📈 {symbol}:')
    print(f'  Current Zone: {zone}')
    print(f'  Averaging steps taken: {steps}')
    print(f'  Peak UPNL: ${peak:.4f}')
    if peak_timestamp:
        print(f'  Peak timestamp: {peak_timestamp}')
    print(f'  Surplus dump stage: {surplus_stage}')
    print(f'  Entry price: ${pos["entry_price"]}')
    print(f'  Side: {pos["side"]}')
    print(f'  Amount: {pos["amount"]}')
    print()

print('\n=== SURPLUS DUMP COMPLIANCE CHECK ===')
print('According to system rules:')
print('1. When position recovers from averaging zone to profit')
print('2. System should dump 50% at 85% of peak UPNL')
print('3. System should dump remaining 50% at 50% of peak UPNL')
print()

# Check for positions that were closed with averaging
closed_with_averaging = []
for symbol in positions_with_averaging:
    if symbol not in data['active_positions']:
        closed_with_averaging.append(symbol)

if closed_with_averaging:
    print(f'⚠️ ALERT: {len(closed_with_averaging)} positions with averaging were closed:')
    for symbol in closed_with_averaging:
        print(f'  - {symbol}')
    print('\nThese positions need review to verify surplus dump was executed properly.')
    print('Check exchange trade history for partial sells at profit levels.')
else:
    print('✅ All positions with averaging history are still active.')

print('\n=== RECOMMENDATIONS ===')
if closed_with_averaging:
    print('1. Check exchange trade history for the closed positions')
    print('2. Verify if partial sells occurred at profit recovery')
    print('3. Review peak UPNL timestamps vs closure times')
    print('4. Ensure surplus dump logic is properly implemented')
else:
    print('1. Continue monitoring active positions')
    print('2. Watch for zone transitions from AVERAGING to SURPLUS_DUMP')
    print('3. Verify surplus dump triggers when positions recover')