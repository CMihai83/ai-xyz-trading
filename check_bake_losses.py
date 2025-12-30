#!/usr/bin/env python3
import ccxt
from datetime import datetime

exchange = ccxt.bitget({
    'apiKey': 'bg_1dfc40220e38b5b118c4828b0cbcc2cb',
    'secret': '3cd89a3ceac5330b6a7323c43e91a5e38e0c536678e76a9e36a984966f02951b',
    'password': '83Rule4All',
    'options': {'defaultType': 'swap'}
})

print('=' * 80)
print('BAKE POSITION - LAST 10 LOSING TRADES')
print('=' * 80)

# Get BAKE trades
trades = exchange.fetch_my_trades('BAKE/USDT:USDT', limit=500)
trades.sort(key=lambda x: x['timestamp'])

print(f'Total BAKE trades fetched: {len(trades)}')

# Since BAKE is a SHORT position, track it properly
losing_trades = []
for i in range(len(trades)):
    trade = trades[i]
    
    # For shorts: SELL opens position, BUY closes it
    # Loss occurs when BUY price > SELL price
    if trade['side'] == 'buy':  # Closing short
        # Look back for the corresponding sell
        entry_price = None
        for j in range(i-1, -1, -1):
            if trades[j]['side'] == 'sell' and trades[j]['amount'] >= trade['amount']:
                entry_price = trades[j]['price']
                break
        
        if entry_price:
            # For short: loss = (exit_price - entry_price) * amount
            loss = (trade['price'] - entry_price) * trade['amount']
            if loss > 0:  # This is a loss for short position
                losing_trades.append({
                    'date': trade['datetime'],
                    'contracts': trade['amount'],
                    'entry_price': entry_price,
                    'exit_price': trade['price'],
                    'loss_usd': loss,
                    'fee': trade['fee']['cost'] if trade['fee'] else 0
                })

# Show last 10 losses
print(f'\nFound {len(losing_trades)} losing trades')
print('\nLAST 10 LOSING TRADES FOR BAKE SHORT POSITION:')
print('-' * 80)

for i, t in enumerate(losing_trades[-10:], 1):
    print(f'\n{i}. {t["date"]}')
    print(f'   Closed {t["contracts"]:.0f} contracts')
    print(f'   Entry (SELL): ${t["entry_price"]:.5f}')
    print(f'   Exit (BUY):  ${t["exit_price"]:.5f}')
    print(f'   Loss: ${t["loss_usd"]:.2f}')
    print(f'   Fee: ${t["fee"]:.4f}')

total_losses = sum(t['loss_usd'] for t in losing_trades)
total_fees = sum(t['fee'] for t in losing_trades)

print('\n' + '=' * 80)
print(f'TOTAL LOSSES from BAKE losing trades: ${total_losses:.2f}')
print(f'TOTAL FEES from losing trades: ${total_fees:.2f}')
print(f'COMBINED LOSS + FEES: ${(total_losses + total_fees):.2f}')
print('=' * 80)

# Check current position
positions = exchange.fetch_positions(['BAKE/USDT:USDT'])
if positions:
    pos = positions[0]
    print(f'\nCURRENT BAKE POSITION:')
    print(f'  Side: {pos["side"].upper()}')
    print(f'  Contracts: {pos["contracts"]}')
    print(f'  Avg Entry: ${pos["markPrice"]:.5f}')
    print(f'  Unrealized P&L: ${pos["unrealizedPnl"]:.2f}')