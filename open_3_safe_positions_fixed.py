#!/usr/bin/env python3
# Open 3 high volatility positions with minimum amount compliance

import ccxt
import sys
sys.path.append('/root/ai_xyz')

from dotenv import load_dotenv
import os
from margin_aware_position_sizer import MarginAwarePositionSizer

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

margin_sizer = MarginAwarePositionSizer()

# Coins with low minimum requirements
volatile_coins = [
    {'symbol': 'LAB/USDT:USDT', 'volatility': 36.37},
    {'symbol': 'VTHO/USDT:USDT', 'volatility': 32.97},
    {'symbol': 'NIGHT/USDT:USDT', 'volatility': 34.86}
]

def open_safe_position(symbol, volatility):
    try:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # Ensure minimum $5 value
        min_value = 5.5
        safe_value = min_value  # Use minimum to test
        
        amount = safe_value / current_price
        amount = float(exchange.amount_to_precision(symbol, amount))

        side = 'buy'

        order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        print(f"✅ POSITION OPENED:")
        print(f"  Symbol: {symbol}")
        print(f"  Volatility: {volatility}%")
        print(f"  Amount: {amount}")
        print(f"  Value: ${safe_value:.2f}")
        print(f"  Side: {side}")

        return True

    except Exception as e:
        print(f"❌ Failed {symbol}: {e}")
        return False

if __name__ == '__main__':
    print("🔥 OPENING 3 SAFE HIGH-VOLATILITY POSITIONS")
    count = 0
    for coin in volatile_coins:
        if open_safe_position(coin['symbol'], coin['volatility']):
            count += 1
        if count >= 3:
            break
    print(f"✅ Opened {count} safe positions!")