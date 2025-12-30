#!/usr/bin/env python3
import ccxt
from datetime import datetime
import json

exchange = ccxt.bitget({
    'apiKey': 'bg_1dfc40220e38b5b118c4828b0cbcc2cb',
    'secret': '3cd89a3ceac5330b6a7323c43e91a5e38e0c536678e76a9e36a984966f02951b',
    'password': '83Rule4All',
    'options': {'defaultType': 'swap'}
})

print('=' * 80)
print('EXCHANGE SYNC CHECK - COMPARING ACTUAL VS SYSTEM')
print('=' * 80)

# Get all open positions from exchange
positions = exchange.fetch_positions()
total_upnl = 0

print(f'\nOPEN POSITIONS ON EXCHANGE:')
print('-' * 40)

active_positions = []
for pos in positions:
    if pos['contracts'] and pos['contracts'] > 0:
        active_positions.append(pos)
        symbol = pos['symbol']
        side = pos['side']
        contracts = pos['contracts']
        mark_price = pos['markPrice'] if pos['markPrice'] else 0
        upnl = pos['unrealizedPnl'] if pos['unrealizedPnl'] else 0
        percentage = pos['percentage'] if pos['percentage'] else 0
        
        print(f'\n{symbol}:')
        print(f'  Side: {side.upper()}')
        print(f'  Contracts: {contracts}')
        print(f'  Mark Price: ${mark_price:.5f}')
        print(f'  Unrealized P&L: ${upnl:.2f} ({percentage:.2f}%)')
        
        total_upnl += upnl

print(f'\n{"-" * 40}')
print(f'TOTAL POSITIONS: {len(active_positions)}')
print(f'TOTAL UNREALIZED P&L: ${total_upnl:.2f}')

# Get account balance
balance = exchange.fetch_balance()
usdt_balance = balance['USDT']
print(f'\nACCOUNT BALANCE:')
print(f'  Free: ${usdt_balance["free"]:.2f}')
print(f'  Used: ${usdt_balance["used"]:.2f}')
print(f'  Total: ${usdt_balance["total"]:.2f}')

# Now check what the AI-XYZ system thinks it has
print('\n' + '=' * 80)
print('AI-XYZ SYSTEM STATUS:')
print('-' * 40)

try:
    with open('/app/data/positions.json', 'r') as f:
        system_positions = json.load(f)
        print(f'\nSystem thinks it has {len(system_positions)} positions:')
        for symbol, pos_data in system_positions.items():
            print(f'  - {symbol}: {pos_data.get("side", "?")} {pos_data.get("amount", 0)} contracts')
except Exception as e:
    print(f'Could not read system positions: {e}')

print('\n' + '=' * 80)
print('DISCREPANCIES:')
print('-' * 40)

exchange_symbols = {pos['symbol'] for pos in active_positions}
print(f'\nPositions on exchange: {exchange_symbols}')

if total_upnl < -1:
    print(f'\n⚠️  WARNING: Total unrealized P&L is ${total_upnl:.2f}')
    print('This indicates losses that may not be tracked by the system!')