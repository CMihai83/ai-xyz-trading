#!/usr/bin/env python3
"""Force test averaging by creating positions that will quickly hit -42%"""
import ccxt
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv('/app/.env')

def create_aggressive_position():
    """Create a position with maximum leverage on most volatile coin"""
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    # Find the most volatile small-cap coins
    print("🔍 Finding extremely volatile coins...")
    tickers = exchange.fetch_tickers()

    volatile_coins = []
    for symbol, ticker in tickers.items():
        if symbol.endswith('/USDT:USDT'):
            if ticker.get('quoteVolume', 0) > 100000:  # Lower volume for more volatility
                if ticker.get('percentage'):
                    # Get coins with massive moves
                    volatility = abs(ticker['percentage'])
                    if volatility > 20 and ticker['last'] < 10:  # Small price coins move more
                        volatile_coins.append({
                            'symbol': symbol,
                            'volatility': volatility,
                            'price': ticker['last'],
                            'volume': ticker['quoteVolume']
                        })

    volatile_coins.sort(key=lambda x: x['volatility'], reverse=True)

    if not volatile_coins:
        print("❌ No volatile coins found")
        return None

    # Pick the most volatile one not already in positions
    with open('/app/position_state.json', 'r') as f:
        state = json.load(f)

    for coin in volatile_coins[:10]:
        if coin['symbol'] not in state['active_positions']:
            symbol = coin['symbol']
            print(f"\n✅ Selected: {symbol}")
            print(f"   Volatility: {coin['volatility']:.1f}%")
            print(f"   Price: ${coin['price']}")

            try:
                # Try maximum leverage
                for leverage in [75, 50, 30, 20]:
                    try:
                        exchange.set_leverage(leverage, symbol)
                        print(f"   Set leverage: {leverage}x")
                        break
                    except:
                        continue

                # Open position against the trend for faster losses
                # If coin is up, short it; if down, long it
                side = 'sell' if coin['volatility'] > 0 else 'buy'

                # Small position size for safety
                position_value = 6.50
                amount = position_value / coin['price']

                # Get precision
                market = exchange.market(symbol)
                amount = exchange.amount_to_precision(symbol, amount)

                print(f"   Opening {side.upper()} position")
                print(f"   Amount: {amount}")

                # Place order
                order = exchange.create_market_order(
                    symbol=symbol,
                    side=side,
                    amount=amount
                )

                print(f"   ✅ Order placed: {order['id']}")

                # Add to state
                state['active_positions'][symbol] = {
                    'entry_price': coin['price'],
                    'amount': float(amount),
                    'side': side,
                    'leverage': leverage,
                    'confidence': 0.99,
                    'opened_at': datetime.now().isoformat(),
                    'order_id': order['id'],
                    'initial_margin': position_value / leverage,
                    'safety_margin': 7.50
                }
                state['position_zones'][symbol] = 'NEUTRAL'
                state['averaging_steps'][symbol] = 0
                state['timestamp'] = datetime.now().isoformat()

                with open('/app/position_state.json', 'w') as f:
                    json.dump(state, f, indent=2)

                return symbol

            except Exception as e:
                print(f"   ❌ Failed: {e}")
                continue

    return None

def main():
    print("🚀 FORCING AVERAGING TEST")
    print("=" * 60)

    # Create 2 aggressive positions
    for i in range(2):
        result = create_aggressive_position()
        if result:
            print(f"\n✅ Created position {i+1}: {result}")
        else:
            print(f"\n❌ Failed to create position {i+1}")

    print("\n" + "=" * 60)
    print("Positions created. Monitor them for averaging triggers!")

if __name__ == "__main__":
    main()