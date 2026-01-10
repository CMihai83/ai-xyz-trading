#!/usr/bin/env python3
"""
Add Fibonacci configurations for existing positions
"""

import ccxt
import os
import sys
import json
import redis
from dotenv import load_dotenv

# Load environment
load_dotenv('/app/.env')

# Add path for Fibonacci service
sys.path.append('/app/services/api-gateway/src')
from fibonacci_averaging_service import FibonacciAveragingService

def main():
    print("="*60)
    print("ADDING FIBONACCI CONFIGS FOR EXISTING POSITIONS")
    print("="*60)
    
    # Initialize exchange
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
    
    # Initialize Fibonacci service
    fib_service = FibonacciAveragingService()
    
    # Get current positions
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    
    print(f"\nFound {len(active)} active positions")
    
    # Calculate Fibonacci configs for each
    configs = {}
    
    for pos in active:
        symbol = pos['symbol']
        side = pos['side']
        entry_price = pos['entryPrice']
        mark_price = pos['markPrice']
        
        print(f"\n📊 {symbol}:")
        print(f"  Side: {side}")
        print(f"  Entry: ${entry_price:.5f}")
        print(f"  Current: ${mark_price:.5f}")
        
        # Calculate volatility estimate
        price_change = abs((mark_price - entry_price) / entry_price)
        volatility = price_change * 2  # Rough estimate
        
        # Calculate delta
        delta = entry_price * volatility
        
        # Calculate Fibonacci parameters
        print(f"  Calculating Fibonacci parameters...")
        
        fib_params_raw = fib_service.calculate_trading_parameters(
            delta=delta,
            entry_price=entry_price,
            available_margin=10.0,  # Standard margin
            direction='long' if side == 'long' else 'short',
            market_confidence=0.5
        )
        
        # Convert to expected format
        fib_config = {
            'safe_to_trade': True,
            'leverage': fib_params_raw.leverage,
            'max_averaging_steps': len(fib_params_raw.averaging_steps),
            'total_capital_needed': fib_params_raw.total_margin_required,
            'max_drawdown_pct': (fib_params_raw.max_loss_tolerance / 10.0) * 100,
            'position_multipliers': [step.position_multiplier for step in fib_params_raw.averaging_steps],
            'averaging_thresholds': [(step.price - entry_price) / entry_price for step in fib_params_raw.averaging_steps]
        }
        
        configs[symbol] = fib_config
        
        print(f"  ✅ Fibonacci config calculated:")
        print(f"     Leverage: {fib_config['leverage']}x")
        print(f"     Max steps: {fib_config['max_averaging_steps']}")
        print(f"     Multipliers: {fib_config['position_multipliers']}")
    
    # Save configs to Redis for the system to pick up
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = int(os.getenv('REDIS_PORT', 6379))
    r = redis.Redis(host=redis_host, port=redis_port, db=0, decode_responses=True)
    
    # Store in a key the system can read
    for symbol, config in configs.items():
        key = f'fibonacci_config:{symbol}'
        r.set(key, json.dumps(config))
        print(f"\n✅ Saved Fibonacci config for {symbol} to Redis")
    
    print("\n" + "="*60)
    print("FIBONACCI CONFIGS ADDED SUCCESSFULLY")
    print("Restart the trading system to apply these configs")
    print("="*60)

if __name__ == "__main__":
    main()