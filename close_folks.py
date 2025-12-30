#!/usr/bin/env python3
import ccxt
from dotenv import load_dotenv
import os

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

try:
    positions = exchange.fetch_positions(['FOLKS/USDT:USDT'])
    for pos in positions:
        if pos['symbol'] == 'FOLKS/USDT:USDT' and pos['contracts'] > 0:
            side = 'sell' if pos['side'] == 'long' else 'buy'
            amount = pos['contracts']
            print(f"Closing {pos['symbol']} {pos['side']} {amount} contracts")
            order = exchange.create_market_order(pos['symbol'], side, amount)
            print(f"Closed: {order}")
            break
    else:
        print("No FOLKS position found")
except Exception as e:
    print(f"Error: {e}")