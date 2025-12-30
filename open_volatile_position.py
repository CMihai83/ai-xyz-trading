#!/usr/bin/env python3
"""Open a high-leverage volatile position for testing all position management stages"""
import ccxt
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv('/app/.env')

def find_volatile_coin():
    """Find a highly volatile coin for testing"""
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    # Get 24hr tickers for volatility analysis
    tickers = exchange.fetch_tickers()

    # Filter for USDT pairs with good volume and volatility
    volatile_coins = []
    for symbol, ticker in tickers.items():
        if symbol.endswith('/USDT:USDT') and ticker['quoteVolume']:
            if ticker['quoteVolume'] > 1000000:  # $1M+ volume
                if ticker['percentage']:
                    volatility = abs(ticker['percentage'])
                    volatile_coins.append({
                        'symbol': symbol,
                        'volatility': volatility,
                        'volume': ticker['quoteVolume'],
                        'price': ticker['last']
                    })

    # Sort by volatility
    volatile_coins.sort(key=lambda x: x['volatility'], reverse=True)

    # Return top 5 for selection
    return volatile_coins[:5]

def open_position(symbol, side='buy', leverage=50):
    """Open a high-leverage position"""
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    try:
        # Set leverage
        exchange.set_leverage(leverage, symbol)

        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # Calculate position size ($3.00 after leverage for testing)
        position_value = 3.00
        amount = position_value / current_price

        # Get market info for precision
        market = exchange.market(symbol)
        amount = exchange.amount_to_precision(symbol, amount)

        print(f"\n🎯 Opening {side.upper()} position:")
        print(f"  Symbol: {symbol}")
        print(f"  Leverage: {leverage}x")
        print(f"  Price: ${current_price}")
        print(f"  Amount: {amount}")
        print(f"  Position Value: ${float(amount) * current_price:.2f}")

        # Place market order
        order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        print(f"✅ Order placed: {order['id']}")

        # Update position_state.json
        position_state_file = '/app/position_state.json'
        with open(position_state_file, 'r') as f:
            state = json.load(f)

        # Add new position
        state['active_positions'][symbol] = {
            'entry_price': current_price,
            'amount': float(amount),
            'side': side,
            'leverage': leverage,
            'confidence': 0.85,  # High confidence for test
            'opened_at': datetime.now().isoformat(),
            'order_id': order['id'],
            'initial_margin': position_value / leverage,
            'safety_margin': 7.50  # Safety margin
        }
        state['position_zones'][symbol] = 'NEUTRAL'
        state['averaging_steps'][symbol] = 0
        state['timestamp'] = datetime.now().isoformat()

        with open(position_state_file, 'w') as f:
            json.dump(state, f, indent=2)

        print(f"✅ Position added to state file")
        return order

    except Exception as e:
        print(f"❌ Error opening position: {e}")
        return None

def main():
    print("🔍 Finding volatile coins...")
    volatile_coins = find_volatile_coin()

    print("\n📊 Top 5 Most Volatile Coins (24hr):")
    for i, coin in enumerate(volatile_coins, 1):
        print(f"{i}. {coin['symbol']}: {coin['volatility']:.2f}% | Volume: ${coin['volume']:,.0f} | Price: ${coin['price']}")

    # Select the most volatile one that's not already in position_state
    with open('/app/position_state.json', 'r') as f:
        state = json.load(f)

    selected = None
    for coin in volatile_coins:
        if coin['symbol'] not in state['active_positions']:
            selected = coin
            break

    if selected:
        print(f"\n✅ Selected: {selected['symbol']} with {selected['volatility']:.2f}% volatility")

        # Determine side based on recent movement (counter-trade for volatility)
        side = 'sell' if selected['volatility'] > 0 else 'buy'

        # Open position with 50x leverage for maximum sensitivity
        open_position(selected['symbol'], side=side, leverage=50)
    else:
        print("\n⚠️ All volatile coins already have positions")

if __name__ == "__main__":
    main()