#!/usr/bin/env python3
import ccxt
import os
from dotenv import load_dotenv

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

try:
    positions = exchange.fetch_positions()
    print("Current positions to close:")
    closed_count = 0

    for pos in positions:
        if pos['contracts'] > 0:
            symbol = pos['symbol']
            side = 'LONG' if pos['side'] == 'long' else 'SHORT'
            pnl_pct = pos['percentage']
            pnl = pos['unrealizedPnl']
            amount = pos['contracts']

            print(f"  Closing {symbol}: {side} | ${pnl:.2f} ({pnl_pct:.2f}%) | Amount: {amount}")

            try:
                # Close position by placing opposite order
                close_side = 'sell' if pos['side'] == 'long' else 'buy'
                order = exchange.create_market_order(
                    symbol=symbol,
                    side=close_side,
                    amount=amount
                )
                print(f"✅ Successfully closed {symbol}")
                closed_count += 1
            except Exception as e:
                print(f"❌ Error closing {symbol}: {e}")

    print(f"\nClosed {closed_count} positions")

except Exception as e:
    print(f"Error: {e}")