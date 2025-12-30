#!/usr/bin/env python3
import ccxt
from datetime import datetime, timedelta
import pandas as pd

exchange = ccxt.bitget({
    'apiKey': 'bg_1dfc40220e38b5b118c4828b0cbcc2cb',
    'secret': '3cd89a3ceac5330b6a7323c43e91a5e38e0c536678e76a9e36a984966f02951b',
    'password': '83Rule4All',
    'options': {'defaultType': 'swap'}
})

print('=' * 80)
print('ANALYZING ALL CLOSED POSITIONS WITH LOSSES')
print('=' * 80)

# Get closed orders from the last 7 days
since = exchange.milliseconds() - (7 * 24 * 60 * 60 * 1000)
closed_orders = exchange.fetch_closed_orders(since=since, params={'productType': 'umcbl'})

print(f'\nFetched {len(closed_orders)} closed orders from last 7 days')

# Group by symbol and calculate P&L
position_pnl = {}

for order in closed_orders:
    if order['status'] == 'closed' and order['filled'] > 0:
        symbol = order['symbol']
        if symbol not in position_pnl:
            position_pnl[symbol] = {
                'buys': [],
                'sells': [],
                'total_bought': 0,
                'total_sold': 0,
                'buy_cost': 0,
                'sell_revenue': 0
            }
        
        if order['side'] == 'buy':
            position_pnl[symbol]['buys'].append(order)
            position_pnl[symbol]['total_bought'] += order['filled']
            position_pnl[symbol]['buy_cost'] += order['cost']
        else:
            position_pnl[symbol]['sells'].append(order)
            position_pnl[symbol]['total_sold'] += order['filled']
            position_pnl[symbol]['sell_revenue'] += order['cost']

# Calculate P&L for each closed position
losses = []
profits = []

for symbol, data in position_pnl.items():
    # For futures/perps: 
    # LONG: profit = sell_revenue - buy_cost
    # SHORT: profit = sell_revenue - buy_cost (but sells open, buys close)
    
    # Check if position is closed (roughly equal buys and sells)
    if abs(data['total_bought'] - data['total_sold']) < min(data['total_bought'], data['total_sold']) * 0.1:
        # Position is mostly closed
        net_pnl = data['sell_revenue'] - data['buy_cost']
        
        result = {
            'symbol': symbol,
            'pnl': net_pnl,
            'buy_volume': data['total_bought'],
            'sell_volume': data['total_sold'],
            'trades': len(data['buys']) + len(data['sells'])
        }
        
        if net_pnl < 0:
            losses.append(result)
        else:
            profits.append(result)

# Sort losses by magnitude
losses.sort(key=lambda x: x['pnl'])

print('\n' + '=' * 80)
print('CLOSED POSITIONS WITH LOSSES:')
print('-' * 80)

total_losses = 0
for i, loss in enumerate(losses, 1):
    print(f"\n{i}. {loss['symbol']}")
    print(f"   Loss: ${loss['pnl']:.2f}")
    print(f"   Trades: {loss['trades']}")
    print(f"   Volume: {loss['buy_volume']:.0f} contracts")
    total_losses += loss['pnl']

print('\n' + '=' * 80)
print(f'TOTAL LOSSES FROM CLOSED POSITIONS: ${total_losses:.2f}')
print(f'Number of losing positions: {len(losses)}')
print('=' * 80)

# Also check order history for more details
print('\nDETAILED LOSS BREAKDOWN BY SYMBOL:')
print('-' * 80)

# Get my trades for more accurate P&L
for symbol_data in losses[:5]:  # Top 5 losses
    symbol = symbol_data['symbol']
    print(f'\n{symbol}:')
    
    trades = exchange.fetch_my_trades(symbol, limit=100)
    trades = [t for t in trades if t['timestamp'] > since]
    
    # Calculate actual P&L from trades
    position = {'size': 0, 'cost': 0, 'realized_pnl': 0}
    
    for trade in sorted(trades, key=lambda x: x['timestamp']):
        if trade['side'] == 'buy':
            # Closing short or opening long
            if position['size'] < 0:  # Closing short
                closed_size = min(abs(position['size']), trade['amount'])
                avg_entry = abs(position['cost'] / position['size']) if position['size'] != 0 else 0
                pnl = (avg_entry - trade['price']) * closed_size
                position['realized_pnl'] += pnl
                position['size'] += trade['amount']
                position['cost'] += trade['cost']
            else:  # Opening long
                position['size'] += trade['amount']
                position['cost'] += trade['cost']
        else:  # sell
            # Closing long or opening short  
            if position['size'] > 0:  # Closing long
                closed_size = min(position['size'], trade['amount'])
                avg_entry = position['cost'] / position['size'] if position['size'] != 0 else 0
                pnl = (trade['price'] - avg_entry) * closed_size
                position['realized_pnl'] += pnl
                position['size'] -= trade['amount']
                position['cost'] -= trade['cost']
            else:  # Opening short
                position['size'] -= trade['amount']
                position['cost'] -= trade['cost']
    
    print(f'  Realized P&L: ${position["realized_pnl"]:.2f}')
    print(f'  Final position: {position["size"]:.0f} contracts')
    print(f'  Number of trades: {len(trades)}')