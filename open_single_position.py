#!/usr/bin/env python3
"""Open a single volatile position"""
import ccxt
import os
from dotenv import load_dotenv

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def check_positions():
    try:
        positions = exchange.fetch_positions()
        print("Current positions:")
        for pos in positions:
            if pos['contracts'] > 0:
                symbol = pos['symbol']
                side = 'LONG' if pos['side'] == 'long' else 'SHORT'
                pnl_pct = pos['percentage']
                pnl = pos['unrealizedPnl']
                amount = pos['contracts']
                print(f"  {symbol}: {side} | ${pnl:.2f} ({pnl_pct:.2f}%) | Amount: {amount}")
    except Exception as e:
        print(f"Error checking positions: {e}")

def open_position(symbol, leverage=8):
    try:
        exchange.set_leverage(leverage, symbol)
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # Ensure minimum 5 USDT
        min_value = 5.0
        amount = max(1.0, min_value / current_price)
        amount = float(exchange.amount_to_precision(symbol, amount))

        side = 'buy'  # Let's try buy for this one

        order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        print(f"✅ Opened {symbol} {side.upper()} position")
        return True
    except Exception as e:
        print(f"❌ Error opening {symbol}: {e}")
        return False

if __name__ == "__main__":
    print("Checking current positions...")
    check_positions()

    print("\nTrying to open LAB/USDT position...")
    if open_position('LAB/USDT:USDT'):
        print("\nChecking positions after opening...")
        check_positions()
    else:
        print("Failed to open position")