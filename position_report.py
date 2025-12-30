#!/usr/bin/env python3
"""Comprehensive position status report"""

import json
import ccxt
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'productType': 'USDT-FUTURES'
    }
})

# Load position state
with open('/app/position_state.json', 'r') as f:
    state = json.load(f)

print("\n" + "="*80)
print("🎯 AI-XYZ POSITION MANAGEMENT REPORT")
print("="*80)
print(f"Timestamp: {datetime.now()}")
print("="*80)

total_upnl = 0
positions_in_profit = 0
positions_in_loss = 0
positions_ready_for_action = []

for symbol, position in state['active_positions'].items():
    try:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        entry_price = position['entry_price']
        amount = position['amount']
        side = position.get('side', 'buy')
        leverage = position.get('leverage', 1)
        zone = state['position_zones'].get(symbol, 'UNKNOWN')

        # Calculate UPNL
        if side == 'buy':
            upnl = (current_price - entry_price) * amount
        else:  # sell
            upnl = (entry_price - current_price) * amount

        position_value = entry_price * amount
        upnl_pct = (upnl / position_value) * 100 if position_value > 0 else 0
        margin = position_value / leverage if leverage > 0 else position_value
        upnl_on_margin = (upnl / margin) * 100 if margin > 0 else 0

        total_upnl += upnl
        if upnl > 0:
            positions_in_profit += 1
        else:
            positions_in_loss += 1

        print(f"\n📊 {symbol}")
        print(f"  Side: {side.upper()} | Leverage: {leverage}x | Zone: {zone}")
        print(f"  Entry: ${entry_price:.8f} | Current: ${current_price:.8f}")
        print(f"  UPNL: ${upnl:.4f} ({upnl_pct:.1f}% of position, {upnl_on_margin:.1f}% of margin)")

        # Check for actions
        peak_upnl = state['peak_upnl'].get(symbol, 0)
        steps = state['averaging_steps'].get(symbol, 0)
        surplus_stage = state['surplus_dump_stage'].get(symbol, 0)

        # AVERAGING CHECK
        if zone == 'AVERAGING' and upnl_pct <= -42 and steps == 0:
            print(f"  🔴 READY FOR AVERAGING! First step triggered at {upnl_pct:.1f}%")
            positions_ready_for_action.append(f"{symbol}: AVERAGING")
        elif zone == 'AVERAGING':
            print(f"  ⏳ Waiting for -42% (current: {upnl_pct:.1f}%)")

        # SURPLUS DUMP CHECK
        if peak_upnl > 0.10 and upnl > 0:
            stage1_trigger = peak_upnl * 0.85
            stage2_trigger = peak_upnl * 0.50
            print(f"  Peak UPNL: ${peak_upnl:.4f}")

            if surplus_stage == 0 and upnl <= stage1_trigger:
                print(f"  💰 READY FOR SURPLUS DUMP STAGE 1! (${upnl:.4f} <= ${stage1_trigger:.4f})")
                positions_ready_for_action.append(f"{symbol}: SURPLUS_DUMP_1")
            elif surplus_stage == 1 and upnl <= stage2_trigger:
                print(f"  💰 READY FOR SURPLUS DUMP STAGE 2! (${upnl:.4f} <= ${stage2_trigger:.4f})")
                positions_ready_for_action.append(f"{symbol}: SURPLUS_DUMP_2")
            else:
                print(f"  Surplus triggers: Stage1=${stage1_trigger:.4f}, Stage2=${stage2_trigger:.4f}")

        # STOP LOSS CHECK
        if upnl_pct <= -70:
            print(f"  ⛔ STOP LOSS TERRITORY! ({upnl_pct:.1f}%)")
            positions_ready_for_action.append(f"{symbol}: STOP_LOSS")

    except Exception as e:
        print(f"\n{symbol}: Error - {e}")

print("\n" + "="*80)
print("📈 SUMMARY")
print("="*80)
print(f"Total Positions: {len(state['active_positions'])}")
print(f"In Profit: {positions_in_profit} | In Loss: {positions_in_loss}")
print(f"Total UPNL: ${total_upnl:.4f}")

if positions_ready_for_action:
    print(f"\n⚠️ POSITIONS READY FOR ACTION:")
    for action in positions_ready_for_action:
        print(f"  - {action}")
else:
    print(f"\n✅ No positions require immediate action")

# Check if autonomous_sync is running
import subprocess
result = subprocess.run(['pgrep', '-f', 'autonomous_sync'], capture_output=True, text=True)
if result.returncode == 0:
    print(f"\n✅ Autonomous sync is running (PID: {result.stdout.strip()})")
else:
    print(f"\n⚠️ Autonomous sync is NOT running")

print("\n" + "="*80)