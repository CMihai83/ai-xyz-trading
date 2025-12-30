#!/usr/bin/env python3
"""Open extremely volatile positions for rapid testing"""
import ccxt
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv('/app/.env')

def open_extreme_positions():
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    # Target volatile coins with high leverage
    targets = [
        {'symbol': 'NEIROETH/USDT:USDT', 'leverage': 50, 'side': 'buy'},  # 45% volatility
        {'symbol': 'SQD/USDT:USDT', 'leverage': 50, 'side': 'sell'},      # 41% volatility
        {'symbol': 'IP/USDT:USDT', 'leverage': 20, 'side': 'buy'},        # 29% volatility
    ]

    position_state_file = '/app/position_state.json'
    with open(position_state_file, 'r') as f:
        state = json.load(f)

    opened_positions = []

    for target in targets:
        try:
            symbol = target['symbol']

            # Skip if already have position
            if symbol in state['active_positions']:
                print(f"⏭️ Skipping {symbol} - position already exists")
                continue

            # Set leverage
            exchange.set_leverage(target['leverage'], symbol)

            # Get current price
            ticker = exchange.fetch_ticker(symbol)
            current_price = ticker['last']

            # Calculate position size ($6.50 after leverage)
            position_value = 6.50
            amount = position_value / current_price

            # Get market info for precision
            market = exchange.market(symbol)
            amount = exchange.amount_to_precision(symbol, amount)

            print(f"\n🎯 Opening {target['side'].upper()} position:")
            print(f"  Symbol: {symbol}")
            print(f"  Leverage: {target['leverage']}x")
            print(f"  Price: ${current_price}")
            print(f"  Amount: {amount}")
            print(f"  Value: ${float(amount) * current_price:.2f}")

            # Place market order
            order = exchange.create_market_order(
                symbol=symbol,
                side=target['side'],
                amount=amount
            )

            print(f"✅ Order placed: {order['id']}")

            # Add to state
            state['active_positions'][symbol] = {
                'entry_price': current_price,
                'amount': float(amount),
                'side': target['side'],
                'leverage': target['leverage'],
                'confidence': 0.9,  # High confidence for test
                'opened_at': datetime.now().isoformat(),
                'order_id': order['id'],
                'initial_margin': position_value / target['leverage'],
                'safety_margin': 7.50
            }
            state['position_zones'][symbol] = 'NEUTRAL'
            state['averaging_steps'][symbol] = 0

            opened_positions.append(symbol)

        except Exception as e:
            print(f"❌ Error opening {symbol}: {e}")
            continue

    # Save updated state
    if opened_positions:
        state['timestamp'] = datetime.now().isoformat()
        with open(position_state_file, 'w') as f:
            json.dump(state, f, indent=2)
        print(f"\n✅ Opened {len(opened_positions)} positions")

    return opened_positions

if __name__ == "__main__":
    print("🚀 Opening extreme volatility positions for rapid testing...")
    positions = open_extreme_positions()
    print(f"\n📊 Total positions opened: {len(positions)}")
    for pos in positions:
        print(f"  - {pos}")