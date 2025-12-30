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
    print("Current positions:")
    positions_to_close = []
    for pos in positions:
        if pos['contracts'] > 0:
            symbol = pos['symbol']
            side = 'LONG' if pos['side'] == 'long' else 'SHORT'
            pnl_pct = pos['percentage']
            pnl = pos['unrealizedPnl']
            entry = pos.get('averagePrice', 'N/A')
            amount = pos['contracts']
            leverage = pos.get('leverage', 'N/A')
            print(f"  {symbol}: {side} | ${pnl:.2f} ({pnl_pct:.2f}%) | Entry: {entry} | Amount: {amount} | Lev: {leverage}")
            positions_to_close.append(pos)

    if positions_to_close:
        print(f"\nFound {len(positions_to_close)} positions to close...")
        confirm = input("Close all positions? (yes/no): ")
        if confirm.lower() == 'yes':
            for pos in positions_to_close:
                try:
                    side = 'sell' if pos['side'] == 'long' else 'buy'
                    order = exchange.create_market_order(
                        symbol=pos['symbol'],
                        side=side,
                        amount=pos['contracts']
                    )
                    print(f"✅ Closed {pos['symbol']} {pos['side'].upper()}")
                except Exception as e:
                    print(f"❌ Error closing {pos['symbol']}: {e}")
        else:
            print("Cancelled closing positions")
    else:
        print("No positions to close")
except Exception as e:
    print(f"Error: {e}")