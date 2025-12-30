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
print('CLOSED POSITIONS WITH LOSSES (Last 7 days)')
print('=' * 80)

# Get trades from last 7 days
since = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)

# Check multiple symbols that might have been traded
symbols_to_check = [
    'BAKE/USDT:USDT', 'BR/USDT:USDT', 'XAUT/USDT:USDT', 
    'NAORIS/USDT:USDT', 'PTB/USDT:USDT', 'AVNT/USDT:USDT',
    'HIFI/USDT:USDT', 'MANA/USDT:USDT', 'ENJ/USDT:USDT',
    'ADA/USDT:USDT', 'DOGE/USDT:USDT', 'TRX/USDT:USDT'
]

all_closed_positions = {}
total_losses = 0

print("\nChecking trades around 4:35 AM...")
print("-" * 40)

for symbol in symbols_to_check:
    try:
        trades = exchange.fetch_my_trades(symbol, since=since, limit=100)
        
        if trades:
            # Look for trades around 4:35
            for trade in trades:
                trade_time = trade['datetime']
                if '04:3' in trade_time or '04:4' in trade_time:
                    print(f"{trade_time}: {symbol} {trade['side'].upper()} {trade['amount']:.1f} @ ${trade['price']:.5f} (Cost: ${trade['cost']:.2f})")
            
            # Calculate P&L for this symbol
            buy_cost = 0
            sell_cost = 0
            buy_amount = 0
            sell_amount = 0
            fees = 0
            
            for trade in trades:
                if trade['side'] == 'buy':
                    buy_cost += trade['cost']
                    buy_amount += trade['amount']
                else:
                    sell_cost += trade['cost']
                    sell_amount += trade['amount']
                
                if trade['fee']:
                    fees += trade['fee']['cost'] if trade['fee']['cost'] else 0
            
            # Check if position is closed (buy and sell amounts roughly match)
            if abs(buy_amount - sell_amount) < (buy_amount * 0.1) if buy_amount > 0 else 1:
                # Position is mostly or fully closed
                realized_pnl = sell_cost - buy_cost - fees
                
                if realized_pnl < -0.01:  # Only show losses
                    all_closed_positions[symbol] = {
                        'pnl': realized_pnl,
                        'buy_cost': buy_cost,
                        'sell_cost': sell_cost,
                        'fees': fees,
                        'trades': len(trades),
                        'last_trade': trades[-1]['datetime'] if trades else 'Unknown'
                    }
                    total_losses += realized_pnl
                    
    except Exception as e:
        pass  # Skip symbols that don't have trades

# Sort by loss amount (most negative first)
sorted_losses = sorted(all_closed_positions.items(), key=lambda x: x[1]['pnl'])

print("\n" + "=" * 80)
print("POSITIONS CLOSED WITH LOSSES:")
print("=" * 80)

if sorted_losses:
    for symbol, data in sorted_losses:
        print(f'\n{symbol}:')
        print(f'  Realized Loss: ${data["pnl"]:.2f}')
        print(f'  Buy Cost: ${data["buy_cost"]:.2f}')
        print(f'  Sell Cost: ${data["sell_cost"]:.2f}')
        print(f'  Fees Paid: ${data["fees"]:.2f}')
        print(f'  Number of Trades: {data["trades"]}')
        print(f'  Last Trade: {data["last_trade"]}')
    
    print('\n' + '=' * 80)
    print(f'TOTAL LOSSES FROM CLOSED POSITIONS: ${total_losses:.2f}')
    print('=' * 80)
else:
    print('\n✅ No closed positions with losses found in the last 7 days')

# Also check current open positions with unrealized losses
print('\n' + '=' * 80)
print('CURRENT OPEN POSITIONS WITH UNREALIZED LOSSES')
print('=' * 80)

positions = exchange.fetch_positions()
open_losses = 0

for pos in positions:
    if pos['contracts'] > 0 and pos.get('unrealizedPnl') and pos['unrealizedPnl'] < -0.01:
        print(f'\n{pos["symbol"]} ({pos["side"].upper()}):')
        print(f'  Unrealized Loss: ${pos["unrealizedPnl"]:.2f}')
        print(f'  Percentage: {pos["percentage"]:.2f}%')
        print(f'  Contracts: {pos["contracts"]}')
        print(f'  Entry Price: ${pos.get("markPrice", 0):.5f}')
        open_losses += pos['unrealizedPnl']

if open_losses < 0:
    print(f'\nTOTAL UNREALIZED LOSSES: ${open_losses:.2f}')