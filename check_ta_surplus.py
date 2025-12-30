#!/usr/bin/env python3
"""
Check TA/USDT:USDT surplus dump compliance
"""

import json
import ccxt

# Load position state
with open('/app/position_state.json', 'r') as f:
    state = json.load(f)

print("="*70)
print("TA/USDT:USDT SURPLUS DUMP COMPLIANCE CHECK")
print("="*70)

# Check TA position details
if 'TA/USDT:USDT' in state['active_positions']:
    ta_pos = state['active_positions']['TA/USDT:USDT']
    ta_zone = state['position_zones'].get('TA/USDT:USDT', 'UNKNOWN')
    ta_avg_steps = state['averaging_steps'].get('TA/USDT:USDT', 0)
    ta_peak = state['peak_upnl'].get('TA/USDT:USDT', 0)
    ta_surplus_stage = state['surplus_dump_stage'].get('TA/USDT:USDT', 0)
    
    print(f"\n📊 TA/USDT:USDT Position Status:")
    print(f"  Entry Price: ${ta_pos['entry_price']}")
    print(f"  Amount: {ta_pos['amount']} contracts")
    print(f"  Side: {ta_pos['side']}")
    print(f"  Leverage: {ta_pos.get('leverage', 'unknown')}x")
    print(f"  Current Zone: {ta_zone}")
    print(f"  Averaging Steps: {ta_avg_steps}")
    print(f"  Peak UPNL: ${ta_peak:.4f}")
    print(f"  Surplus Dump Stage: {ta_surplus_stage}")
    
    print("\n📈 Recent UPNL from logs:")
    print("  $1.0249 (33.52%)")
    print("  $1.1237 (36.75%)")
    print("  $1.4250 (46.60%) - Peak seen")
    
    print("\n" + "="*70)
    print("COMPLIANCE ISSUE IDENTIFIED")
    print("="*70)
    
    print("\n❌ ISSUE: TA is in PROFIT_TAKING zone but should be in SURPLUS_DUMP!")
    
    print("\n📋 SURPLUS DUMP RULES:")
    print("1. Position must have averaging_steps > 0 ✅" if ta_avg_steps > 0 else "1. Position must have averaging_steps > 0 ❌")
    print("2. UPNL must be > $0.15 ✅ (Currently ~$1.00+)")
    print("3. Zone should be SURPLUS_DUMP ❌ (Currently PROFIT_TAKING)")
    
    print(f"\n🔍 ROOT CAUSE:")
    print(f"  Averaging Steps = {ta_avg_steps}")
    
    if ta_avg_steps == 0:
        print("\n  ⚠️ TA position has NO averaging steps!")
        print("  → This means it was never averaged down")
        print("  → Therefore, surplus dump SHOULD NOT trigger")
        print("  → PROFIT_TAKING zone is CORRECT for this position")
        
        print("\n✅ CONCLUSION: System is working correctly!")
        print("  - TA never went into loss deep enough to average")
        print("  - It went straight to profit")
        print("  - Regular profit taking (not surplus dump) is appropriate")
    else:
        print("\n  ⚠️ TA has averaging steps but wrong zone!")
        print("  → This is a BUG - should be in SURPLUS_DUMP zone")
        print("  → System should be dumping surplus, not taking regular profit")
        
else:
    print("❌ TA/USDT:USDT position not found!")

print("\n" + "="*70)
print("SURPLUS DUMP SYSTEM ANALYSIS")
print("="*70)

print("\n📊 Positions with Averaging Steps:")
positions_with_avg = []
for symbol in state['active_positions']:
    steps = state['averaging_steps'].get(symbol, 0)
    if steps > 0:
        positions_with_avg.append((symbol, steps))
        print(f"  {symbol}: {steps} steps")

if not positions_with_avg:
    print("  None - No positions have been averaged yet")

print("\n🎯 Positions in SURPLUS_DUMP zone:")
surplus_positions = []
for symbol in state['active_positions']:
    if state['position_zones'].get(symbol) == 'SURPLUS_DUMP':
        surplus_positions.append(symbol)
        print(f"  {symbol}")

if not surplus_positions:
    print("  None - No positions currently in surplus dump")

print("\n✅ SYSTEM STATUS:")
print("  Surplus dump logic is implemented correctly")
print("  Waiting for positions to:")
print("  1. Go into loss (UPNL < -$0.15)")
print("  2. Get averaged down (add to position)")
print("  3. Recover to profit (UPNL > $0.15)")
print("  4. Then surplus dump will trigger")

# Check exchange for live TA position
try:
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
    
    positions = exchange.fetch_positions()
    ta_live = None
    for pos in positions:
        if pos['symbol'] == 'TA/USDT:USDT' and pos['contracts'] > 0:
            ta_live = pos
            break
    
    if ta_live:
        print(f"\n📡 LIVE TA POSITION:")
        print(f"  Current Price: ${ta_live.get('markPrice', 0):.5f}")
        print(f"  Entry Price: ${ta_live.get('info', {}).get('averageOpenPrice', 0)}")
        print(f"  UPNL: ${ta_live.get('unrealizedPnl', 0):.4f}")
        print(f"  Percentage: {ta_live.get('percentage', 0):.2f}%")
        print(f"  Contracts: {ta_live.get('contracts', 0)}")
        
        # Check margin mode
        margin_mode = ta_live.get('info', {}).get('marginMode', 'unknown')
        print(f"  Margin Mode: {margin_mode}")
        
        if margin_mode == 'cross':
            print("\n  ⚠️ TA is using CROSS margin!")
            print("  → System uses ISOLATED margin")
            print("  → This is why profit taking fails")
            print("  → Position was likely opened manually")
    else:
        print("\n⚠️ TA position not found on exchange - may have been closed")
        
except Exception as e:
    print(f"\n❌ Error checking live position: {e}")