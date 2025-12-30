#!/usr/bin/env python3
"""Execute trades based on enhanced market scanner signals"""

import ccxt
import json
from datetime import datetime
from position_sizing_config import PositionSizingConfig

# Initialize exchange
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

def execute_signal(signal):
    """Execute a trading signal"""
    try:
        symbol = signal['symbol']
        action = signal['action'].lower()
        leverage = signal['leverage']
        price = signal['price']
        score = signal['score']
        
        print(f"\n🔄 Executing signal for {symbol}")
        print(f"   Action: {action.upper()}")
        print(f"   Leverage: {leverage}x")
        print(f"   Score: {score:.2f}")
        print(f"   Current Price: {price}")
        
        # Set isolated margin and leverage
        exchange.set_margin_mode('isolated', symbol)
        exchange.set_leverage(leverage, symbol)
        
        # Calculate position size based on confidence
        sizing = PositionSizingConfig.get_position_size_for_signal(signal)
        margin_size = sizing['margin_size']
        position_value = sizing['position_value']
        amount = position_value / price
        
        print(f"   Position Sizing: {sizing['reason']}")
        print(f"   Position Value: ${position_value:.2f} (Margin: ${margin_size:.2f})")
        
        # Execute trade
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=action,
            amount=amount
        )
        
        print(f"   ✅ Position opened!")
        print(f"   Order ID: {order['id']}")
        print(f"   Size: {amount:.4f} contracts")
        print(f"   Value: ${position_value:.2f}")
        
        return {
            'success': True,
            'symbol': symbol,
            'order_id': order['id'],
            'amount': amount,
            'leverage': leverage,
            'action': action
        }
        
    except Exception as e:
        print(f"   ❌ Failed to execute: {e}")
        return {
            'success': False,
            'symbol': signal['symbol'],
            'error': str(e)
        }

def main():
    print("="*70)
    print("EXECUTING SCANNER SIGNALS")
    print("="*70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load signals
    try:
        with open('trading_signals.json', 'r') as f:
            signals = json.load(f)
    except:
        print("❌ No trading signals found. Run enhanced_market_scanner.py first.")
        return
    
    print(f"\n📊 Found {len(signals)} signals to execute")
    
    # Check current positions
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    print(f"📈 Current active positions: {len(active)}")
    
    # Check balance
    balance = exchange.fetch_balance()
    usdt = balance.get('USDT', {})
    print(f"💰 Available balance: ${usdt.get('free', 0):.2f} USDT")
    
    if usdt.get('free', 0) < 20:
        print("⚠️ Insufficient balance. Need at least $20 free USDT")
        return
    
    # Execute signals
    execution_results = []
    
    for signal in signals:
        # Check if already have position in this symbol
        existing = [p for p in active if p['symbol'] == signal['symbol']]
        if existing:
            print(f"\n⚠️ Skipping {signal['symbol']} - already have position")
            continue
        
        result = execute_signal(signal)
        execution_results.append(result)
    
    # Summary
    print("\n" + "="*70)
    print("EXECUTION SUMMARY")
    print("="*70)
    
    successful = [r for r in execution_results if r.get('success')]
    failed = [r for r in execution_results if not r.get('success')]
    
    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")
    
    if successful:
        print("\nPositions Opened:")
        for r in successful:
            print(f"  • {r['symbol']}: {r['action'].upper()} @ {r['leverage']}x")
    
    # Check final status
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    
    print(f"\n📊 Total active positions now: {len(active)}")
    
    # Update balance
    balance = exchange.fetch_balance()
    usdt = balance.get('USDT', {})
    print(f"💰 Remaining balance: ${usdt.get('free', 0):.2f} USDT")
    
    # Save execution results
    with open('execution_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'signals_processed': len(signals),
            'successful': len(successful),
            'failed': len(failed),
            'results': execution_results
        }, f, indent=2)
    
    print("\n📄 Results saved to: execution_results.json")

if __name__ == "__main__":
    main()