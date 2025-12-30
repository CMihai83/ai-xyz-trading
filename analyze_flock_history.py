#!/usr/bin/env python3
"""Analyze FLOCK position history with 1-minute candles"""

import ccxt
import pandas as pd
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv('/app/.env')

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
    }
})

def analyze_position_history():
    """Analyze FLOCK position with historical data"""
    
    print("=== FLOCK/USDT POSITION ANALYSIS ===")
    print(f"Analysis Time: {datetime.now()}")
    
    # Position details from the state
    symbol = 'FLOCK/USDT:USDT'
    entry_price = 0.461
    position_size = 63.0  # Current size after averaging
    original_size = 23.5  # Original size from state
    side = 'sell'  # Short position
    opened_at = datetime.fromisoformat("2025-09-09T09:19:38.966320")
    averaging_steps = 2
    
    print(f"\nPosition Details:")
    print(f"  Symbol: {symbol}")
    print(f"  Side: SHORT")
    print(f"  Entry Price: ${entry_price}")
    print(f"  Original Size: {original_size:.1f} contracts")
    print(f"  Current Size: {position_size} contracts (after {averaging_steps} averaging steps)")
    print(f"  Opened: {opened_at}")
    
    # Calculate averaging details
    # With Fibonacci multipliers: 1x, 2x, 3x for first 2 steps
    # Original: 23.5, Step 1: +23.5, Step 2: +16 = Total 63
    step1_size = original_size * 1.0  # 23.5
    step2_size = 16.0  # Remaining to reach 63
    
    print(f"\nAveraging History (estimated):")
    print(f"  Initial: {original_size:.1f} contracts @ ${entry_price}")
    print(f"  Step 1: +{step1_size:.1f} contracts")
    print(f"  Step 2: +{step2_size:.1f} contracts")
    
    try:
        # Fetch 1-minute candles since position opened
        since = int(opened_at.timestamp() * 1000)
        ohlcv = exchange.fetch_ohlcv(symbol, '1m', since=since, limit=500)
        
        if not ohlcv:
            print("No candle data available")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        print(f"\nCandle Data: {len(df)} 1-minute candles")
        print(f"  Time Range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        print(f"  Price Range: ${df['low'].min():.4f} - ${df['high'].max():.4f}")
        
        # Calculate UPNL for each candle (SHORT position)
        # For SHORT: UPNL = (entry_price - current_price) * position_size
        df['upnl_per_contract'] = entry_price - df['close']
        df['upnl_total'] = df['upnl_per_contract'] * position_size
        
        # Find peaks in UPNL (when position was in profit)
        profit_candles = df[df['upnl_total'] > 0.15]  # Above surplus threshold
        
        print(f"\n=== SURPLUS DUMP ANALYSIS ===")
        print(f"Threshold for SURPLUS_DUMP zone: UPNL > $0.15")
        print(f"Position has {averaging_steps} averaging steps (eligible for surplus)")
        
        if len(profit_candles) > 0:
            print(f"\n🔴 FOUND {len(profit_candles)} CANDLES WHERE SURPLUS SHOULD HAVE TRIGGERED!")
            
            # Find the peak UPNL
            peak_idx = df['upnl_total'].idxmax()
            peak_row = df.loc[peak_idx]
            
            print(f"\nPeak UPNL:")
            print(f"  Time: {peak_row['timestamp']}")
            print(f"  Price: ${peak_row['close']:.4f}")
            print(f"  UPNL: ${peak_row['upnl_total']:.2f}")
            print(f"  Per Contract: ${peak_row['upnl_per_contract']:.4f}")
            
            # Show first time it crossed surplus threshold
            first_profit = profit_candles.iloc[0]
            print(f"\nFirst Surplus Trigger Point:")
            print(f"  Time: {first_profit['timestamp']}")
            print(f"  Price: ${first_profit['close']:.4f}")
            print(f"  UPNL: ${first_profit['upnl_total']:.2f}")
            
            # Calculate what should have happened
            print(f"\n📊 SURPLUS DUMP SHOULD HAVE:")
            print(f"  1. Transitioned to SURPLUS_DUMP zone at ${first_profit['close']:.4f}")
            print(f"  2. Tracked peak UPNL of ${peak_row['upnl_total']:.2f}")
            print(f"  3. Dumped 50% at 85% of peak (${peak_row['upnl_total']*0.85:.2f})")
            print(f"  4. Dumped remaining at 50% of peak (${peak_row['upnl_total']*0.50:.2f})")
            
            # Show recent UPNL values
            recent = df.tail(10)
            print(f"\nRecent UPNL (last 10 minutes):")
            for _, row in recent.iterrows():
                status = "✅ SURPLUS" if row['upnl_total'] > 0.15 else "❌ LOSS"
                print(f"  {row['timestamp'].strftime('%H:%M:%S')}: ${row['close']:.4f} -> UPNL: ${row['upnl_total']:.2f} {status}")
                
        else:
            print(f"\n✅ Position has NOT reached profit threshold yet")
            print(f"  Current UPNL range: ${df['upnl_total'].min():.2f} to ${df['upnl_total'].max():.2f}")
            print(f"  Needs to reach: > $0.15 to trigger SURPLUS_DUMP")
            
            # Show if it ever got close
            best_upnl = df['upnl_total'].max()
            best_idx = df['upnl_total'].idxmax()
            best_row = df.loc[best_idx]
            
            print(f"\nBest UPNL so far:")
            print(f"  Time: {best_row['timestamp']}")
            print(f"  Price: ${best_row['close']:.4f}")
            print(f"  UPNL: ${best_row['upnl_total']:.2f}")
            print(f"  Distance to threshold: ${0.15 - best_row['upnl_total']:.2f}")
        
    except Exception as e:
        print(f"Error fetching candle data: {e}")

if __name__ == "__main__":
    analyze_position_history()