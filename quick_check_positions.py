#!/usr/bin/env python3
"""
Quick check of current positions and system status
"""

import ccxt
import time
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
print("AI-XYZ POSITION STATUS CHECK")
print("="*70)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Get current positions
positions = exchange.fetch_positions()
active = [p for p in positions if p['contracts'] > 0]

print(f"\n📊 Active Positions: {len(active)}/10")

if active:
    longs = sum(1 for p in active if p['side'] == 'long')
    shorts = len(active) - longs
    
    print(f"⚖️ Balance: {longs} LONG / {shorts} SHORT")
    print(f"   Long:  {'█' * int((longs/len(active))*10):10s} {longs/len(active):.0%}")
    print(f"   Short: {'█' * int((shorts/len(active))*10):10s} {shorts/len(active):.0%}")
    
    if shorts == len(active):
        print("\n❌ ALL POSITIONS ARE SHORT - HEAVILY IMBALANCED")
        print("   System should prioritize LONG positions")
    elif longs == len(active):
        print("\n❌ ALL POSITIONS ARE LONG - HEAVILY IMBALANCED")
        print("   System should prioritize SHORT positions")
    
    print("\nPosition Details:")
    total_upnl = 0
    for p in active:
        upnl = p.get('unrealizedPnl', 0)
        pct = p.get('percentage', 0)
        total_upnl += upnl
        status = "🟢" if upnl > 0 else "🔴"
        print(f"  {p['symbol']:15s} {p['side']:5s} | {status} ${upnl:8.4f} ({pct:6.2f}%)")
    
    print(f"\nTotal UPNL: ${total_upnl:.4f}")
else:
    print("No active positions")

# Get balance
balance = exchange.fetch_balance()
usdt_balance = balance.get('USDT', {})
print(f"\n💰 Balance:")
print(f"  Total: ${usdt_balance.get('total', 0):.2f}")
print(f"  Free:  ${usdt_balance.get('free', 0):.2f}")
print(f"  Used:  ${usdt_balance.get('used', 0):.2f}")

print("\n" + "="*70)
print("SYSTEM STATUS")
print("="*70)

# Check if continuous system is running
import subprocess
result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
if 'aixyz_continuous' in result.stdout:
    print("✅ AI-XYZ Continuous System: RUNNING")
else:
    print("❌ AI-XYZ Continuous System: NOT RUNNING")
    print("\nTo start the system:")
    print("  python3 aixyz_continuous_profit_system.py")
    print("\nThe system will:")
    print("  • Scan every 30 seconds for opportunities")
    print("  • Open positions when < 10 active")
    print("  • Prioritize LONG positions (since all current are SHORT)")
    print("  • Manage averaging, surplus dump, profit taking")

print("\n" + "="*70)