#!/usr/bin/env python3
# Open 3 high volatility positions with SAFE sizing and Fibonacci config

import ccxt
import sys
sys.path.append('/root/ai_xyz')

from dotenv import load_dotenv
import os
from backtesting_service import BacktestingService, FibonacciAveragingOptimizer
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
backtesting = BacktestingService()
optimizer = FibonacciAveragingOptimizer(backtesting)

volatile_coins = [
    'FOLKS/USDT:USDT',
    'LAB/USDT:USDT',
    'NIGHT/USDT:USDT'
]

def open_safe_position(symbol):
    try:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']

        # Get safe sizing
        safe_sizing = margin_sizer.get_backtested_optimal_size(
            symbol=symbol,
            volatility_pct=50.0,
            account_balance=93.44
        )

        amount = safe_sizing['position_value'] / current_price
        amount = float(exchange.amount_to_precision(symbol, amount))

        side = 'buy'

        order = exchange.create_market_order(
            symbol=symbol,
            side=side,
            amount=amount
        )

        print(f"✅ SAFE POSITION OPENED:")
        print(f"  Symbol: {symbol}")
        print(f"  Amount: {amount}")
        print(f"  Value: ${safe_sizing['position_value']:.2f}")
        print(f"  Safe Steps: {safe_sizing['max_averaging_steps']}")

        # Generate Fibonacci config
        fib_config = optimizer.generate_optimal_averaging_plan(symbol, {}, {'volatility': 1.0})
        print(f"  Fibonacci Steps: {fib_config['max_averaging_steps']}")

        return True

    except Exception as e:
        print(f"❌ Failed {symbol}: {e}")
        return False

if __name__ == '__main__':
    print("🔥 OPENING SAFE HIGH-VOLATILITY POSITIONS")
    count = 0
    for symbol in volatile_coins:
        if open_safe_position(symbol):
            count += 1
        if count >= 3:
            break
    print(f"✅ Opened {count} safe positions!")