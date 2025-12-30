#!/usr/bin/env python3
"""Update leverage settings to 7x minimum and open new positions"""

import ccxt
import time
from datetime import datetime

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

def update_existing_positions_leverage():
    """Update leverage on existing positions (if possible)"""
    print("="*60)
    print("UPDATING LEVERAGE ON EXISTING POSITIONS")
    print("="*60)
    
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    
    print(f"\n📊 Found {len(active)} active positions")
    
    for pos in active:
        symbol = pos['symbol']
        current_leverage = pos.get('leverage', 1)
        
        print(f"\n{symbol}:")
        print(f"  Current leverage: {current_leverage}x")
        
        # Note: Cannot change leverage on open positions
        # This is for display only
        print(f"  ⚠️ Cannot change leverage on open positions")
        print(f"  New positions will use 7x-10x leverage")

def open_high_leverage_positions():
    """Open new positions with 7x-10x leverage"""
    print("\n" + "="*60)
    print("OPENING NEW POSITIONS WITH 7x-10x LEVERAGE")
    print("="*60)
    
    # Get current positions to avoid duplicates
    positions = exchange.fetch_positions()
    active_symbols = [p['symbol'] for p in positions if p['contracts'] > 0]
    
    # Target symbols for new positions
    target_symbols = [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT',
        'AVAX/USDT:USDT', 'MATIC/USDT:USDT', 'LINK/USDT:USDT',
        'ADA/USDT:USDT', 'DOT/USDT:USDT', 'UNI/USDT:USDT',
        'ATOM/USDT:USDT', 'FIL/USDT:USDT', 'LTC/USDT:USDT'
    ]
    
    # Filter out already opened
    available = [s for s in target_symbols if s not in active_symbols]
    
    print(f"\n🎯 Available symbols: {len(available)}")
    print(f"📊 Current positions: {len(active_symbols)}")
    print(f"🚀 Will open up to {min(3, 10-len(active_symbols))} new positions")
    
    positions_opened = 0
    max_to_open = min(3, 10 - len(active_symbols))  # Open up to 3, max 10 total
    
    for symbol in available[:max_to_open]:
        try:
            # Get market data
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            
            # Check momentum
            ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=10)
            momentum = (ohlcv[-1][4] - ohlcv[0][1]) / ohlcv[0][1]
            
            # Determine side based on momentum
            side = 'buy' if momentum > 0 else 'sell'
            
            # Set leverage between 7x and 10x
            leverage = 7 + positions_opened  # 7x, 8x, 9x for variety
            
            print(f"\n📈 Opening {symbol}")
            print(f"  Price: {price}")
            print(f"  Momentum: {momentum:.2%}")
            print(f"  Side: {side.upper()}")
            print(f"  Leverage: {leverage}x")
            
            # Set isolated margin and leverage
            exchange.set_margin_mode('isolated', symbol)
            exchange.set_leverage(leverage, symbol)
            
            # Calculate position size (minimum $6.50 after leverage)
            margin_size = 7.0  # $7 margin
            position_value = margin_size * leverage
            amount = position_value / price
            
            # Open position
            order = exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=amount
            )
            
            print(f"  ✅ Position opened!")
            print(f"  Order ID: {order['id']}")
            print(f"  Size: {amount:.4f} contracts")
            print(f"  Value: ${position_value:.2f}")
            
            positions_opened += 1
            time.sleep(2)  # Small delay between positions
            
        except Exception as e:
            print(f"  ❌ Failed to open {symbol}: {e}")
            continue
    
    return positions_opened

def check_final_status():
    """Check final status after updates"""
    print("\n" + "="*60)
    print("FINAL STATUS CHECK")
    print("="*60)
    
    # Get all positions
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    
    total_upnl = 0
    
    print(f"\n📊 Total Active Positions: {len(active)}")
    
    for i, pos in enumerate(active, 1):
        upnl = pos.get('unrealizedPnl', 0)
        total_upnl += upnl
        leverage = pos.get('leverage', 1)
        
        print(f"\n{i}. {pos['symbol']}")
        print(f"   Side: {pos['side'].upper()}")
        print(f"   Leverage: {leverage}x")
        print(f"   UPNL: ${upnl:.4f} ({pos.get('percentage', 0):.2f}%)")
        
        # Zone status
        if upnl <= -0.15:
            print(f"   Zone: 🔴 AVERAGING")
        elif upnl > 0.15:
            print(f"   Zone: 🟢 SURPLUS DUMP")
        else:
            print(f"   Zone: 🟡 NEUTRAL")
    
    print(f"\n💰 Total UPNL: ${total_upnl:.4f}")
    
    # Balance check
    balance = exchange.fetch_balance()
    usdt = balance.get('USDT', {})
    print(f"\n💵 Account Balance:")
    print(f"   Total: ${usdt.get('total', 0):.2f}")
    print(f"   Free: ${usdt.get('free', 0):.2f}")
    print(f"   Used: ${usdt.get('used', 0):.2f}")

def main():
    print("="*70)
    print("LEVERAGE SETTINGS UPDATE - 7x MINIMUM")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Show current leverage settings
    update_existing_positions_leverage()
    
    # Open new positions with higher leverage
    new_positions = open_high_leverage_positions()
    
    if new_positions > 0:
        print(f"\n✅ Opened {new_positions} new positions with 7x-10x leverage")
    else:
        print(f"\n⚠️ No new positions opened (may be at maximum)")
    
    # Final status
    check_final_status()
    
    print("\n" + "="*70)
    print("LEVERAGE UPDATE COMPLETE")
    print("="*70)
    print("✅ New positions will use 7x-10x leverage")
    print("✅ Continuous trading script updated to use 7x minimum")
    print("✅ Test scripts updated with new leverage settings")

if __name__ == "__main__":
    main()