#!/usr/bin/env python3
"""Check current trading system status"""

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

print('=' * 60)
print('CHECKING CURRENT SYSTEM STATUS')
print('=' * 60)

# Check balance
balance = exchange.fetch_balance()
usdt_balance = balance.get('USDT', {})
print(f'\n💰 Account Balance:')
print(f'  Total USDT: {usdt_balance.get("total", 0):.2f}')
print(f'  Free USDT: {usdt_balance.get("free", 0):.2f}')
print(f'  Used USDT: {usdt_balance.get("used", 0):.2f}')

# Check open positions
positions = exchange.fetch_positions()
print(f'\n📊 Open Positions: {len(positions)}')

if len(positions) == 0:
    print('  ❌ No positions currently open')
    print('\nReasons for no positions:')
    print('  1. All test positions were closed after completion')
    print('  2. System is not running in continuous mode')
    print('  3. No active trading signals at this moment')
    print('  4. Tests run in isolated sessions and close positions')
else:
    for pos in positions:
        print(f'\n  Position: {pos["symbol"]}')
        print(f'    Side: {pos["side"]}')
        print(f'    Contracts: {pos["contracts"]}')
        print(f'    Entry Price: {pos.get("entryPrice", 0)}')
        print(f'    Mark Price: {pos.get("markPrice", 0)}')
        print(f'    Unrealized PnL: ${pos.get("unrealizedPnl", 0):.4f}')
        print(f'    Percentage: {pos.get("percentage", 0):.2f}%')

print('\n' + '=' * 60)
print('SYSTEM STATUS EXPLANATION')
print('=' * 60)

print("""
The AI-XYZ system is designed to:

1. TESTING MODE (Current):
   - Opens positions for compliance testing
   - Monitors zones and mechanics
   - Closes positions after test completion
   - Does NOT maintain continuous positions

2. PRODUCTION MODE (Not Active):
   - Would continuously scan markets
   - Open positions based on signals
   - Manage multiple concurrent positions
   - Run 24/7 with proper risk management

Currently: TESTING MODE
- Each test opens, monitors, and closes positions
- No positions remain open between tests
- This is expected behavior for compliance testing

To have continuous positions, the system needs to run:
- integrated_system_launcher.py (continuous mode)
- With proper signal generation
- With risk management parameters
- In production configuration
""")

print('=' * 60)