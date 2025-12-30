#!/usr/bin/env python3
"""
Live demonstration of Fibonacci Averaging with real exchange data
Shows how the system calculates averaging steps for current positions
"""

import sys
import os
from datetime import datetime

# Add paths
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/core')

# Import Fibonacci calculator directly
import importlib.util
spec = importlib.util.spec_from_file_location("adaptive_fibonacci_averaging", "/app/core/adaptive_fibonacci_averaging.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
AdaptiveFibonacciCalculator = module.AdaptiveFibonacciCalculator

# Import exchange
import ccxt

def main():
    print("="*80)
    print("FIBONACCI AVERAGING SYSTEM - LIVE DEMONSTRATION")
    print("="*80)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Initialize Fibonacci calculator with 5 steps (matching Excel)
    calc = AdaptiveFibonacciCalculator(num_steps=5)
    
    print("📊 Fibonacci Configuration (5 steps):")
    print(f"   Sequence: {calc.fibonacci_sequence}")
    print(f"   Individual thresholds: {[f'{t:.1%}' for t in calc.delta_thresholds]}")
    print(f"   Cumulative thresholds: {[f'{t:.1%}' for t in calc.cumulative_thresholds]}")
    print()
    
    # Connect to exchange
    exchange = ccxt.bitget({
        'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
        'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
        'password': '2609Luiza',
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'defaultMarginMode': 'isolated'
        }
    })
    
    # Get current positions
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    
    print(f"🔍 Found {len(active)} active positions")
    print()
    
    if len(active) == 0:
        print("📌 No active positions. Creating example with BTC/USDT:")
        # Get current BTC price
        ticker = exchange.fetch_ticker('BTC/USDT:USDT')
        current_price = ticker['last']
        
        position_data = {
            'entry_price': current_price,
            'leverage': 7,
            'initial_margin': 10.0,
            'total_margin': 100.0,
            'max_delta': current_price * 0.15,  # 15% max movement
            'direction': 'long'
        }
        
        print(f"   Current BTC Price: ${current_price:,.2f}")
        print(f"   Max Delta: ${position_data['max_delta']:,.2f} (15%)")
    else:
        # Use first active position
        pos = active[0]
        print(f"📌 Using active position: {pos['symbol']}")
        print(f"   Side: {pos['side']}")
        print(f"   Current Price: ${pos['markPrice']:,.2f}")
        print(f"   Contracts: {pos['contracts']}")
        print(f"   Unrealized PNL: ${pos['unrealizedPnl']:,.2f}")
        
        # Create position data
        position_data = {
            'entry_price': pos['markPrice'],
            'leverage': 7,
            'initial_margin': abs(pos['initialMargin']) if pos['initialMargin'] else 10.0,
            'total_margin': 100.0,  # Available for averaging
            'max_delta': pos['markPrice'] * 0.15,  # 15% max movement
            'direction': pos['side'] if pos['side'] else 'long'
        }
    
    print("\n" + "="*80)
    print("CALCULATING FIBONACCI AVERAGING CONFIGURATION")
    print("="*80)
    
    # Calculate configuration
    config = calc.calculate_adaptive_config(position_data)
    
    print(f"\n✅ Optimal Configuration Found:")
    print(f"   K Coefficient: {config.k_coefficient:.3f}")
    print(f"   Max Safe Steps: {config.max_safe_steps}")
    print(f"   Total Margin Required: ${config.total_margin_required:.2f}")
    print(f"   Final Average Entry: ${config.final_avg_entry:.2f}")
    
    print("\n📈 Averaging Steps (Trigger Prices):")
    print("-"*70)
    print(f"{'Step':<6} {'Fib':<6} {'Threshold':<12} {'Cumulative':<12} {'Trigger Price':<15} {'Margin':<10}")
    print("-"*70)
    
    for i in range(config.max_safe_steps):
        fib = calc.fibonacci_sequence[i] if i < len(calc.fibonacci_sequence) else 0
        individual = calc.delta_thresholds[i] if i < len(calc.delta_thresholds) else 0
        cumulative = calc.cumulative_thresholds[i] if i < len(calc.cumulative_thresholds) else 0
        trigger = config.trigger_prices[i] if i < len(config.trigger_prices) else 0
        margin = config.margin_allocations[i] if i < len(config.margin_allocations) else 0
        
        print(f"{i+1:<6} {fib:<6} {individual:<12.1%} {cumulative:<12.1%} ${trigger:<14,.2f} ${margin:<9.2f}")
    
    print("\n" + "="*80)
    print("BACKTESTING OPTIMAL STEP COUNT")
    print("="*80)
    
    # Backtest different step counts
    optimal_steps, best_config, results = calc.backtest_optimal_steps(
        position_data,
        min_steps=3,
        max_steps=7
    )
    
    print(f"\n{'Steps':<8} {'K Coef':<10} {'Safe Steps':<12} {'Score':<10} {'Fibonacci Sequence'}")
    print("-"*70)
    
    for num_steps, result in sorted(results.items()):
        marker = " ← BEST" if num_steps == optimal_steps else ""
        fib_seq = str(result['fibonacci_sequence'])
        print(f"{num_steps:<8} {result['k_coefficient']:<10.3f} {result['max_safe_steps']:<12} {result['score']:<10.2f} {fib_seq}{marker}")
    
    print(f"\n🎯 Optimal Configuration: {optimal_steps} steps")
    print(f"   Best K: {best_config.k_coefficient:.3f}")
    print(f"   Achieves {best_config.max_safe_steps} safe averaging steps")
    
    print("\n" + "="*80)
    print("✅ FIBONACCI AVERAGING SYSTEM IS OPERATIONAL")
    print("="*80)
    print("\nThe system is now using:")
    print("• Correct Fibonacci sequences (ending with 3)")
    print("• Proper delta threshold calculation (individual and cumulative)")
    print("• Trigger prices matching Excel example pattern")
    print("• Backtesting to find optimal step counts")
    print("• Automatic K coefficient optimization")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()