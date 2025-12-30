#!/usr/bin/env python3
import ccxt
from datetime import datetime, timedelta

exchange = ccxt.bitget({
    'apiKey': 'bg_1dfc40220e38b5b118c4828b0cbcc2cb',
    'secret': '3cd89a3ceac5330b6a7323c43e91a5e38e0c536678e76a9e36a984966f02951b',
    'password': '83Rule4All',
    'options': {'defaultType': 'swap'}
})

print('=' * 80)
print('CHECKING RECENTLY CLOSED POSITIONS (LAST 48 HOURS)')
print('=' * 80)

# Get all recent trades to find closed positions
symbols_to_check = ['BAKE/USDT:USDT', 'BR/USDT:USDT', 'XAUT/USDT:USDT', 
                    'GLBR/USDT:USDT', 'FIB/USDT:USDT', 'STPT/USDT:USDT',
                    'AVNT/USDT:USDT', 'BSW/USDT:USDT', 'SWTCH/USDT:USDT']

closed_positions = []
total_losses = 0

for symbol in symbols_to_check:
    try:
        # Get trades for this symbol
        trades = exchange.fetch_my_trades(symbol, limit=100)
        
        if not trades:
            continue
            
        # Filter recent trades (last 48 hours)
        cutoff_time = datetime.now().timestamp() * 1000 - (48 * 60 * 60 * 1000)
        recent_trades = [t for t in trades if t['timestamp'] > cutoff_time]
        
        if not recent_trades:
            continue
        
        # Track position to find if it was closed
        position = {'size': 0, 'cost': 0, 'realized_pnl': 0}
        last_trade_time = None
        
        for trade in sorted(recent_trades, key=lambda x: x['timestamp']):
            last_trade_time = trade['datetime']
            
            if trade['side'] == 'buy':
                if position['size'] < 0:  # Closing short
                    closed_size = min(abs(position['size']), trade['amount'])
                    avg_entry = abs(position['cost'] / position['size']) if position['size'] != 0 else 0
                    pnl = (avg_entry - trade['price']) * closed_size
                    position['realized_pnl'] += pnl
                position['size'] += trade['amount']
                position['cost'] += trade['cost']
            else:  # sell
                if position['size'] > 0:  # Closing long
                    closed_size = min(position['size'], trade['amount']) 
                    avg_entry = position['cost'] / position['size'] if position['size'] != 0 else 0
                    pnl = (trade['price'] - avg_entry) * closed_size
                    position['realized_pnl'] += pnl
                position['size'] -= trade['amount']
                position['cost'] -= trade['cost']
        
        # Check if position was closed (size near 0)
        if abs(position['size']) < 1 and position['realized_pnl'] != 0:
            closed_positions.append({
                'symbol': symbol,
                'pnl': position['realized_pnl'],
                'last_trade': last_trade_time,
                'trades': len(recent_trades)
            })
            if position['realized_pnl'] < 0:
                total_losses += position['realized_pnl']
                
    except Exception as e:
        # Symbol might not exist or have trades
        continue

# Sort by P&L (losses first)
closed_positions.sort(key=lambda x: x['pnl'])

print('\nCLOSED POSITIONS WITH LOSSES:')
print('-' * 80)

for pos in closed_positions:
    if pos['pnl'] < 0:
        print(f"\n{pos['symbol']}:")
        print(f"  P&L: ${pos['pnl']:.2f}")
        print(f"  Last trade: {pos['last_trade']}")
        print(f"  Number of trades: {pos['trades']}")

print('\n' + '=' * 80)
print(f'TOTAL LOSSES FROM CLOSED POSITIONS: ${total_losses:.2f}')

# Also check BAKE specifically since you mentioned it
print('\n' + '=' * 80)
print('BAKE POSITION ANALYSIS:')
print('-' * 80)

try:
    bake_trades = exchange.fetch_my_trades('BAKE/USDT:USDT', limit=200)
    
    # Group by day to see pattern
    from collections import defaultdict
    daily_pnl = defaultdict(float)
    
    position = {'size': 0, 'cost': 0}
    
    for trade in sorted(bake_trades, key=lambda x: x['timestamp']):
        date = trade['datetime'].split('T')[0]
        
        if trade['side'] == 'buy':
            if position['size'] < 0:  # Closing short
                closed_size = min(abs(position['size']), trade['amount'])
                avg_entry = abs(position['cost'] / position['size']) if position['size'] != 0 else 0
                pnl = (avg_entry - trade['price']) * closed_size
                daily_pnl[date] += pnl
            position['size'] += trade['amount']
            position['cost'] += trade['cost']
        else:  # sell
            if position['size'] > 0:  # Closing long
                closed_size = min(position['size'], trade['amount'])
                avg_entry = position['cost'] / position['size'] if position['size'] != 0 else 0
                pnl = (trade['price'] - avg_entry) * closed_size
                daily_pnl[date] += pnl
            position['size'] -= trade['amount']
            position['cost'] -= trade['cost']
    
    print('\nBAKE Daily P&L:')
    total_bake_pnl = 0
    for date, pnl in sorted(daily_pnl.items()):
        print(f"  {date}: ${pnl:.2f}")
        total_bake_pnl += pnl
    
    print(f'\nTotal BAKE P&L: ${total_bake_pnl:.2f}')
    print(f'Current BAKE position size: {position["size"]:.0f} contracts')
    
except Exception as e:
    print(f'Could not analyze BAKE: {e}')