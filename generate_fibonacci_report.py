#!/usr/bin/env python3
"""
Generate Fibonacci Report for Current AI-XYZ Positions
Shows stored Fibonacci configurations and current position states
"""

import asyncio
import json
import redis
from datetime import datetime
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv
from fibonacci_results_storage import FibonacciResultsStorage, get_position_fibonacci_report

load_dotenv('/app/.env')

async def get_current_positions():
    """Get current positions from Redis"""
    try:
        r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        positions = []
        
        # Get all position keys
        for key in r.scan_iter("position:*"):
            pos_data = r.hgetall(key)
            if pos_data and pos_data.get('current_quantity', '0') != '0':
                positions.append({
                    'position_id': pos_data.get('position_id'),
                    'symbol': pos_data.get('symbol'),
                    'direction': pos_data.get('direction'),
                    'entry_price': float(pos_data.get('weighted_avg_price', 0)),
                    'current_price': float(pos_data.get('current_price', 0)),
                    'quantity': float(pos_data.get('current_quantity', 0)),
                    'unrealized_pnl': float(pos_data.get('unrealized_pnl', 0)),
                    'zone': pos_data.get('current_zone', 'UNKNOWN'),
                    'averaging_steps_taken': int(pos_data.get('averaging_steps_taken', 0))
                })
        
        return positions
    except Exception as e:
        print(f"Error getting positions: {e}")
        return []

async def get_exchange_positions():
    """Get positions directly from exchange"""
    try:
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
        
        await exchange.load_markets()
        positions = await exchange.fetch_positions()
        await exchange.close()
        
        return positions
        
    except Exception as e:
        print(f"Error fetching from exchange: {e}")
        return []

async def generate_comprehensive_report():
    """Generate comprehensive Fibonacci report for all positions"""
    
    print("="*80)
    print("AI-XYZ FIBONACCI CONFIGURATION REPORT")
    print("="*80)
    print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Get current positions
    print("📊 CURRENT POSITIONS STATUS")
    print("-"*60)
    
    positions = await get_current_positions()
    exchange_positions = await get_exchange_positions()
    
    if positions:
        print(f"Found {len(positions)} active positions in AI-XYZ system")
        print()
        
        for pos in positions:
            print(f"Position: {pos['symbol']}")
            print(f"  ID: {pos['position_id']}")
            print(f"  Direction: {pos['direction'].upper()}")
            print(f"  Entry Price: ${pos['entry_price']:.4f}")
            print(f"  Current Price: ${pos['current_price']:.4f}")
            print(f"  Quantity: {pos['quantity']:.4f}")
            print(f"  Unrealized P&L: ${pos['unrealized_pnl']:.2f}")
            print(f"  Current Zone: {pos['zone']}")
            print(f"  Averaging Steps Taken: {pos['averaging_steps_taken']}")
            print()
    else:
        print("No active positions found in system")
        print()
    
    # Get exchange positions for comparison
    if exchange_positions:
        print("📈 EXCHANGE POSITIONS (Direct from Bitget)")
        print("-"*60)
        
        for ex_pos in exchange_positions:
            if ex_pos['contracts'] > 0:
                print(f"Symbol: {ex_pos['symbol']}")
                print(f"  Side: {ex_pos['side']}")
                print(f"  Contracts: {ex_pos['contracts']}")
                if 'average' in ex_pos and ex_pos['average']:
                    print(f"  Average Price: ${ex_pos['average']:.4f}")
                if 'markPrice' in ex_pos and ex_pos['markPrice']:
                    print(f"  Current Price: ${ex_pos['markPrice']:.4f}")
                if 'unrealizedPnl' in ex_pos:
                    print(f"  Unrealized P&L: ${ex_pos['unrealizedPnl']:.2f}")
                if 'percentage' in ex_pos:
                    print(f"  Percentage: {ex_pos['percentage']:.2f}%")
                print()
    
    # Get Fibonacci configurations
    print("="*80)
    print("FIBONACCI AVERAGING CONFIGURATIONS")
    print("="*80)
    
    storage = FibonacciResultsStorage()
    all_fibonacci_results = storage.get_all_active_results()
    
    if all_fibonacci_results:
        print(f"Found {len(all_fibonacci_results)} stored Fibonacci configurations")
        print()
        
        # Generate detailed report
        full_report = get_position_fibonacci_report()
        print(full_report)
    else:
        print("No Fibonacci configurations found in storage")
        print("(Configurations are stored when new positions are opened)")
        print()
    
    # Summary statistics
    if all_fibonacci_results:
        print("="*80)
        print("SUMMARY STATISTICS")
        print("="*80)
        
        total_positions = len(all_fibonacci_results)
        avg_leverage = sum(r['results']['leverage'] for r in all_fibonacci_results) / total_positions
        avg_steps = sum(len(r['results']['averaging_steps']) for r in all_fibonacci_results) / total_positions
        total_margin = sum(r['results']['total_margin_required'] for r in all_fibonacci_results)
        
        print(f"Total Positions with Fibonacci Config: {total_positions}")
        print(f"Average Leverage: {avg_leverage:.1f}x")
        print(f"Average Averaging Steps: {avg_steps:.1f}")
        print(f"Total Margin Allocated: ${total_margin:.2f}")
        
        # Find position with most aggressive config
        most_steps = max(all_fibonacci_results, key=lambda x: len(x['results']['averaging_steps']))
        print(f"\nMost Aggressive Configuration:")
        print(f"  Position: {most_steps['position_id']}")
        print(f"  Symbol: {most_steps['symbol']}")
        print(f"  Steps: {len(most_steps['results']['averaging_steps'])}")
        print(f"  Leverage: {most_steps['results']['leverage']}x")

async def test_with_sample_data():
    """Test the storage system with sample data for demonstration"""
    
    print("\n" + "="*80)
    print("TESTING WITH SAMPLE DATA")
    print("="*80)
    
    from fibonacci_results_storage import store_position_fibonacci_results
    
    # Create sample Fibonacci results for current positions
    sample_configs = [
        {
            'position_id': 'br_usdt_test_001',
            'symbol': 'BR/USDT:USDT',
            'entry_price': 0.0856,
            'direction': 'long',
            'response': {
                'success': True,
                'leverage': 7,
                'initial_position_size': 6.5,
                'averaging_steps': [
                    {'step_number': 1, 'price': 0.0831, 'margin_allocation': 3.25, 
                     'position_multiplier': 1.0, 'fibonacci_weight': 8, 
                     'distance_from_entry': 0.0025, 'liquidation_safety': True},
                    {'step_number': 2, 'price': 0.0805, 'margin_allocation': 5.20,
                     'position_multiplier': 1.6, 'fibonacci_weight': 5,
                     'distance_from_entry': 0.0051, 'liquidation_safety': True},
                    {'step_number': 3, 'price': 0.0779, 'margin_allocation': 8.45,
                     'position_multiplier': 2.6, 'fibonacci_weight': 3,
                     'distance_from_entry': 0.0077, 'liquidation_safety': True}
                ],
                'total_margin_required': 16.90,
                'liquidation_price': 0.0704,
                'confidence_score': 0.65
            }
        },
        {
            'position_id': 'bake_usdt_test_001',
            'symbol': 'BAKE/USDT:USDT',
            'entry_price': 0.10566,
            'direction': 'short',
            'response': {
                'success': True,
                'leverage': 10,
                'initial_position_size': 6.5,
                'averaging_steps': [
                    {'step_number': 1, 'price': 0.1119, 'margin_allocation': 1.95,
                     'position_multiplier': 0.5, 'fibonacci_weight': 33,
                     'distance_from_entry': 0.0062, 'liquidation_safety': True},
                    {'step_number': 2, 'price': 0.1182, 'margin_allocation': 3.90,
                     'position_multiplier': 1.0, 'fibonacci_weight': 33,
                     'distance_from_entry': 0.0125, 'liquidation_safety': True},
                    {'step_number': 3, 'price': 0.1247, 'margin_allocation': 7.80,
                     'position_multiplier': 2.0, 'fibonacci_weight': 34,
                     'distance_from_entry': 0.0190, 'liquidation_safety': True}
                ],
                'total_margin_required': 13.65,
                'liquidation_price': 0.1268,
                'confidence_score': 0.70
            }
        }
    ]
    
    # Store sample configurations
    for config in sample_configs:
        success = store_position_fibonacci_results(
            position_id=config['position_id'],
            symbol=config['symbol'],
            entry_price=config['entry_price'],
            direction=config['direction'],
            fibonacci_service_response=config['response']
        )
        
        if success:
            print(f"✅ Stored sample config for {config['symbol']}")
        else:
            print(f"❌ Failed to store config for {config['symbol']}")
    
    print("\nSample data stored. Re-running report...\n")
    
    # Generate report with sample data
    await generate_comprehensive_report()

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--test':
        # Run with test data
        asyncio.run(test_with_sample_data())
    else:
        # Run normal report
        asyncio.run(generate_comprehensive_report())