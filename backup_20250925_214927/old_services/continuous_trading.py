#!/usr/bin/env python3
"""Continuous trading mode - opens and maintains positions"""

import ccxt
import time
import json
from datetime import datetime
import sys
from position_sizing_config import PositionSizingConfig

# Initialize exchange with isolated margin
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

def find_volatile_opportunity(exclude_symbols=None):
    """Find most volatile coins for trading"""
    symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'DOGE/USDT:USDT', 
               'SOL/USDT:USDT', 'PEPE/USDT:USDT', 'WIF/USDT:USDT',
               'ARB/USDT:USDT', 'OP/USDT:USDT', 'INJ/USDT:USDT',
               'TRX/USDT:USDT', 'APT/USDT:USDT', 'CRV/USDT:USDT',
               'MANA/USDT:USDT', 'SAND/USDT:USDT', 'AXS/USDT:USDT',
               'AVAX/USDT:USDT', 'MATIC/USDT:USDT', 'DOT/USDT:USDT',
               'ADA/USDT:USDT', 'LINK/USDT:USDT', 'UNI/USDT:USDT']
    
    # Exclude already opened symbols
    if exclude_symbols:
        symbols = [s for s in symbols if s not in exclude_symbols]
    
    best_opportunity = None
    best_volatility = 0
    
    import random
    random.shuffle(symbols)  # Randomize order for variety
    
    for symbol in symbols[:10]:  # Check only 10 random symbols for speed
        try:
            # Get recent candles
            ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=20)
            
            # Calculate volatility
            high_prices = [c[2] for c in ohlcv]
            low_prices = [c[3] for c in ohlcv]
            avg_range = sum((h-l)/l*100 for h,l in zip(high_prices, low_prices)) / len(ohlcv)
            
            print(f"  {symbol}: Volatility {avg_range:.2f}%")
            
            if avg_range > best_volatility:
                best_volatility = avg_range
                best_opportunity = symbol
                
        except Exception as e:
            print(f"  Error checking {symbol}: {e}")
            continue
    
    return best_opportunity, best_volatility

def open_position(symbol, leverage=7):
    """Open a position with isolated margin"""
    try:
        # Set isolated margin mode
        exchange.set_margin_mode('isolated', symbol)
        exchange.set_leverage(leverage, symbol)
        
        # Get current price
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # Calculate position size (default $6.50 after leverage)
        # Use confidence 0.5 for continuous trading (standard size)
        sizing = PositionSizingConfig.calculate_position_size(leverage, confidence=0.5)
        amount = sizing['position_value'] / current_price
        
        # Determine side based on simple momentum
        ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=5)
        momentum = (ohlcv[-1][4] - ohlcv[0][1]) / ohlcv[0][1]
        side = 'buy' if momentum < 0 else 'sell'  # Counter-trend
        
        # Open position
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=side,
            amount=amount
        )
        
        print(f"\n✅ POSITION OPENED:")
        print(f"  Symbol: {symbol}")
        print(f"  Side: {side}")
        print(f"  Amount: {amount:.4f}")
        print(f"  Leverage: {leverage}x")
        print(f"  Entry Price: {current_price}")
        print(f"  Order ID: {order['id']}")
        
        return {
            'symbol': symbol,
            'side': side,
            'amount': amount,
            'entry_price': current_price,
            'leverage': leverage,
            'order_id': order['id'],
            'opened_at': datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"❌ Failed to open position: {e}")
        return None

def monitor_positions():
    """Monitor and display current positions"""
    positions = exchange.fetch_positions()
    
    if not positions:
        return []
    
    active_positions = []
    for pos in positions:
        if pos['contracts'] > 0:
            active_positions.append({
                'symbol': pos['symbol'],
                'side': pos['side'],
                'contracts': pos['contracts'],
                'entry_price': pos.get('entryPrice', 0),
                'mark_price': pos.get('markPrice', 0),
                'upnl': pos.get('unrealizedPnl', 0),
                'percentage': pos.get('percentage', 0)
            })
    
    return active_positions

def main():
    print("=" * 60)
    print("AI-XYZ CONTINUOUS TRADING MODE")
    print("=" * 60)
    print("\nThis will open and maintain positions continuously.")
    print("Press Ctrl+C to stop.\n")
    
    # Check balance
    balance = exchange.fetch_balance()
    usdt_balance = balance.get('USDT', {})
    print(f"💰 Starting Balance: ${usdt_balance.get('total', 0):.2f} USDT")
    print(f"   Free: ${usdt_balance.get('free', 0):.2f}")
    
    positions_opened = []
    max_positions = 10  # Increased limit to 10 concurrent positions
    
    try:
        while True:
            print("\n" + "=" * 40)
            print(f"Cycle at {datetime.now().strftime('%H:%M:%S')}")
            
            # Check current positions
            active_positions = monitor_positions()
            print(f"\n📊 Active Positions: {len(active_positions)}")
            
            for pos in active_positions:
                print(f"  {pos['symbol']}: {pos['side']} | UPNL: ${pos['upnl']:.4f} ({pos['percentage']:.2f}%)")
            
            # Open new positions if below limit (aggressive mode)
            positions_needed = max_positions - len(active_positions)
            if positions_needed > 0:
                print(f"\n🔍 Need to open {positions_needed} more positions...")
                
                # Get list of already opened symbols
                opened_symbols = [pos['symbol'] for pos in active_positions]
                
                # Try to open multiple positions in one cycle
                for i in range(min(3, positions_needed)):  # Open up to 3 per cycle
                    symbol, volatility = find_volatile_opportunity(exclude_symbols=opened_symbols)
                    
                    if symbol and volatility > 0.2:  # Lowered threshold to 0.2% for more opportunities
                        print(f"\n🎯 Opportunity #{i+1}: {symbol} (volatility: {volatility:.2f}%)")
                        
                        # Vary leverage based on volatility (7x minimum, 10x maximum)
                        leverage = min(10, max(7, int(volatility * 5)))  # 7x-10x leverage range
                        
                        position = open_position(symbol, leverage)
                        if position:
                            positions_opened.append(position)
                            time.sleep(2)  # Small delay between positions
                    else:
                        print(f"  No opportunity found in cycle {i+1}")
            else:
                print(f"\n✅ Maximum {max_positions} positions reached!")
            
            # Update balance
            balance = exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {})
            print(f"\n💰 Current Balance: ${usdt_balance.get('total', 0):.2f} USDT")
            print(f"   Free: ${usdt_balance.get('free', 0):.2f}")
            print(f"   Used: ${usdt_balance.get('used', 0):.2f}")
            
            # Save state
            with open('continuous_trading_state.json', 'w') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(),
                    'positions_opened': positions_opened,
                    'active_positions': active_positions,
                    'balance': {
                        'total': usdt_balance.get('total', 0),
                        'free': usdt_balance.get('free', 0),
                        'used': usdt_balance.get('used', 0)
                    }
                }, f, indent=2)
            
            # Wait before next cycle
            print("\n⏳ Waiting 30 seconds for next cycle...")
            time.sleep(30)
            
    except KeyboardInterrupt:
        print("\n\n⛔ Stopping continuous trading...")
        print(f"Total positions opened: {len(positions_opened)}")
        
        # Final status
        active_positions = monitor_positions()
        print(f"\n📊 Final Active Positions: {len(active_positions)}")
        for pos in active_positions:
            print(f"  {pos['symbol']}: {pos['side']} | UPNL: ${pos['upnl']:.4f}")
        
        print("\n✅ Continuous trading stopped")
        print("Note: Positions remain open for further management")

if __name__ == "__main__":
    main()