#!/usr/bin/env python3
import ccxt

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

print("Fetching live positions from Bitget...")
positions = exchange.fetch_positions()

found = False
for pos in positions:
    if pos['symbol'] == 'CUDIS/USDT:USDT' and pos['contracts'] > 0:
        found = True
        print(f'\nCUDIS/USDT:USDT Position:')
        print(f'  Side: {pos["side"]}')
        print(f'  Contracts: {pos["contracts"]}')
        print(f'  Mark Price: ${pos["markPrice"]}')
        print(f'  Entry Price: ${pos["entryPrice"]}')
        print(f'  Unrealized PNL: ${pos["unrealizedPnl"]}')
        print(f'  Percentage: {pos["percentage"]:.2f}%')
        
        # Check if in profit
        if pos["unrealizedPnl"] > 0:
            print(f'\n✅ POSITION IS IN PROFIT: ${pos["unrealizedPnl"]:.4f}')
        else:
            print(f'\n❌ POSITION IS IN LOSS: ${pos["unrealizedPnl"]:.4f}')
        break

if not found:
    print('No CUDIS position found on exchange')