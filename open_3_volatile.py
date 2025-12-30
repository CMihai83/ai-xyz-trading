#!/usr/bin/env python3
"""Open 3 high volatility positions manually"""
import ccxt
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# Top 3 volatile coins from recent scan
volatile_coins = [
    {'symbol': 'FOLKS/USDT:USDT', 'price': 7.22, 'volatility': 72.75},
    {'symbol': 'LIGHT/USDT:USDT', 'price': 3.66, 'volatility': 47.14},
    {'symbol': 'NIGHT/USDT:USDT', 'price': 0.08878, 'volatility': 34.86}
]

def open_position(symbol, target_value=3.0, leverage=8):
    """Open a position with proper amount calculation"""
    try:
        # Set leverage
        exchange.set_leverage(leverage, symbol)

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # Calculate amount (ensure minimum 5 USDT value)
        min_value = 5.0  # Minimum 5 USDT
        amount = max(1.0, min_value / current_price)

        # Get market info for precision
        market = exchange.market(symbol)
        amount = float(exchange.amount_to_precision(symbol, amount))

        # Calculate actual position value
        position_value = amount * current_price

        print(f"\n🎯 Opening position:")
        print(f"  Symbol: {symbol}")
        print(f"  Leverage: {leverage}x")
        print(f"  Price: ${current_price}")
        print(f"  Amount: {amount}")
        print(f"  Position Value: ${position_value:.2f}")

        # Determine side (alternate between buy/sell for diversification)
        side = 'buy' if hash(symbol) % 2 == 0 else 'sell'

        # Place market order
        order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        print(f"✅ Position opened successfully!")
        return order

    except Exception as e:
        print(f"❌ Error opening position for {symbol}: {e}")
        return None

def main():
    print("🔥 Opening 3 High Volatility Positions\n")

    opened_positions = 0
    for coin in volatile_coins:
        if opened_positions >= 3:
            break

        print(f"📈 Opening position {opened_positions + 1}/3: {coin['symbol']} ({coin['volatility']:.1f}% volatility)")
        order = open_position(coin['symbol'])

        if order:
            opened_positions += 1
            print(f"✅ Successfully opened position {opened_positions}")
        else:
            print(f"❌ Failed to open position for {coin['symbol']}")

    print(f"\n🎉 Opened {opened_positions} volatile positions!")

if __name__ == "__main__":
    main()