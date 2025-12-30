#!/usr/bin/env python3
"""Create a test position with high leverage for testing all stages"""

import json
import os
import ccxt
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'productType': 'USDT-FUTURES'
    }
})

# High volatility coins for testing
test_symbols = ['PEPE/USDT:USDT', 'DOGS/USDT:USDT', 'SHIB/USDT:USDT', 'FLOKI/USDT:USDT']

print("\n" + "="*60)
print("🧪 CREATING HIGH VOLATILITY TEST POSITION")
print("="*60)

# Find the most volatile coin
best_symbol = None
best_volatility = 0

for symbol in test_symbols:
    try:
        ticker = exchange.fetch_ticker(symbol)
        volatility = abs(ticker['percentage'])
        print(f"{symbol}: 24h change = {ticker['percentage']:.2f}%, Volume = ${ticker['quoteVolume']:,.0f}")

        if volatility > best_volatility:
            best_volatility = volatility
            best_symbol = symbol
            best_price = ticker['last']
    except:
        pass

if best_symbol:
    print(f"\n✅ Selected {best_symbol} with {best_volatility:.2f}% volatility")

    # Load current state
    with open('/app/position_state.json', 'r') as f:
        state = json.load(f)

    # Create test position
    leverage = 50  # High leverage for faster testing
    notional = 6.5  # Minimum size
    amount = notional / best_price

    position = {
        'entry_price': best_price,
        'amount': amount,
        'side': 'buy',
        'leverage': leverage,
        'opened_at': datetime.now().isoformat(),
        'test_position': True
    }

    # Add to state
    state['active_positions'][best_symbol] = position
    state['position_zones'][best_symbol] = 'NEUTRAL'
    state['averaging_steps'][best_symbol] = 0
    state['peak_upnl'][best_symbol] = 0
    state['peak_upnl_timestamps'][best_symbol] = None
    state['surplus_dump_stage'][best_symbol] = 0
    state['original_sizes'][best_symbol] = amount

    # Save state
    with open('/app/position_state.json', 'w') as f:
        json.dump(state, f, indent=2)

    print(f"\n📊 Test Position Created:")
    print(f"  Symbol: {best_symbol}")
    print(f"  Entry: ${best_price:.8f}")
    print(f"  Amount: {amount:.2f}")
    print(f"  Leverage: {leverage}x")
    print(f"  Notional: ${notional:.2f}")
    print(f"  Margin Required: ${notional/leverage:.2f}")
    print(f"  Zone: NEUTRAL")
    print(f"\n✅ Position added to position_state.json")
    print(f"   Autonomous sync will manage this position")
    print(f"   With {leverage}x leverage, a -0.84% move = -42% UPNL")
    print(f"   This should trigger averaging quickly")
else:
    print("❌ No suitable volatile symbol found")