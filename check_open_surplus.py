#!/usr/bin/env python3
"""Check OPEN position surplus dump status with peak timestamps"""

import ccxt
import json
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

def check_open_position():
    """Analyze OPEN position for surplus dump status"""
    
    print("=== OPEN/USDT SURPLUS DUMP ANALYSIS ===")
    print(f"Analysis Time: {datetime.now()}")
    
    # Load position state
    with open('/app/position_state.json', 'r') as f:
        state = json.load(f)
    
    if 'OPEN/USDT:USDT' not in state['active_positions']:
        print("OPEN position not found in active positions")
        return
    
    # Position details
    pos = state['active_positions']['OPEN/USDT:USDT']
    symbol = 'OPEN/USDT:USDT'
    entry_price = pos['entry_price']
    amount = pos['amount']
    side = pos['side']
    opened_at = datetime.fromisoformat(pos['opened_at'])
    
    # Zone and surplus status
    zone = state['position_zones'].get(symbol, 'UNKNOWN')
    averaging_steps = state['averaging_steps'].get(symbol, 0)
    peak_upnl = state['peak_upnl'].get(symbol, 0)
    peak_timestamp = state['peak_upnl_timestamps'].get(symbol)
    surplus_stage = state['surplus_dump_stage'].get(symbol, 0)
    original_size = state['original_sizes'].get(symbol, amount)
    
    print(f"\n📊 Position Details:")
    print(f"  Symbol: {symbol}")
    print(f"  Side: {side.upper()}")
    print(f"  Entry Price: ${entry_price}")
    print(f"  Current Amount: {amount} contracts")
    print(f"  Original Size: {original_size:.2f} contracts")
    print(f"  Opened: {opened_at}")
    
    print(f"\n🎯 Zone & Status:")
    print(f"  Current Zone: {zone}")
    print(f"  Averaging Steps: {averaging_steps}")
    print(f"  Surplus Dump Stage: {surplus_stage}")
    
    print(f"\n📈 Peak UPNL Tracking:")
    print(f"  Peak UPNL: ${peak_upnl:.4f}")
    print(f"  Peak Timestamp: {peak_timestamp if peak_timestamp else 'Never reached peak'}")
    
    # Fetch current price
    try:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        
        # Calculate current UPNL
        if side == 'sell':
            upnl_per_contract = entry_price - current_price
        else:
            upnl_per_contract = current_price - entry_price
        
        upnl_total = upnl_per_contract * amount
        upnl_pct = (upnl_per_contract / entry_price) * 100
        
        print(f"\n💰 Current Status:")
        print(f"  Current Price: ${current_price:.4f}")
        print(f"  UPNL: ${upnl_total:.4f} ({upnl_pct:.2f}%)")
        print(f"  Per Contract: ${upnl_per_contract:.4f}")
        
        # Check surplus dump conditions
        print(f"\n🔍 Surplus Dump Analysis:")
        print(f"  Threshold for SURPLUS_DUMP zone: UPNL > $0.15")
        print(f"  Averaging steps completed: {averaging_steps}")
        
        if averaging_steps > 0:
            print(f"  ✅ Has averaging history - eligible for surplus dump")
            
            if upnl_total > 0.15:
                print(f"  ✅ UPNL above threshold - should be in SURPLUS_DUMP zone")
                
                if peak_upnl > 0:
                    # Calculate dump thresholds
                    first_threshold = peak_upnl * 0.85
                    second_threshold = peak_upnl * 0.50
                    
                    print(f"\n  📊 Surplus Dump Thresholds:")
                    print(f"    Stage 1 trigger: ${first_threshold:.4f} (85% of peak)")
                    print(f"    Stage 2 trigger: ${second_threshold:.4f} (50% of peak)")
                    print(f"    Current UPNL: ${upnl_total:.4f}")
                    
                    if surplus_stage == 0 and upnl_total <= first_threshold:
                        print(f"  🔴 STAGE 1 SHOULD TRIGGER!")
                    elif surplus_stage == 1 and upnl_total <= second_threshold:
                        print(f"  🔴 STAGE 2 SHOULD TRIGGER!")
                    else:
                        pct_of_peak = (upnl_total / peak_upnl * 100) if peak_upnl > 0 else 0
                        print(f"  ⏳ Waiting: Currently at {pct_of_peak:.1f}% of peak")
            else:
                print(f"  ❌ UPNL below threshold ({upnl_total:.4f} < 0.15)")
                print(f"  💡 Needs ${0.15 - upnl_total:.4f} more profit to enter SURPLUS_DUMP zone")
        else:
            print(f"  ❌ No averaging steps - not eligible for surplus dump")
            print(f"  💡 Would go to PROFIT_TAKING zone if UPNL > $0.15")
        
        # Fetch historical data if peak timestamp exists
        if peak_timestamp:
            print(f"\n📅 Historical Analysis at Peak:")
            peak_dt = datetime.fromisoformat(peak_timestamp)
            
            # Fetch 1-minute candles around peak time
            since = int((peak_dt - timedelta(minutes=5)).timestamp() * 1000)
            until = int((peak_dt + timedelta(minutes=5)).timestamp() * 1000)
            
            ohlcv = exchange.fetch_ohlcv(symbol, '1m', since=since, limit=11)
            
            if ohlcv:
                print(f"  Peak occurred at: {peak_timestamp}")
                print(f"  Candles around peak time:")
                
                for candle in ohlcv:
                    candle_time = datetime.fromtimestamp(candle[0]/1000)
                    candle_price = candle[4]  # Close price
                    
                    if side == 'sell':
                        candle_upnl = (entry_price - candle_price) * amount
                    else:
                        candle_upnl = (candle_price - entry_price) * amount
                    
                    is_peak = abs((candle_time - peak_dt).total_seconds()) < 60
                    marker = " 📍 PEAK" if is_peak else ""
                    
                    print(f"    {candle_time.strftime('%H:%M')}: ${candle_price:.4f} -> UPNL: ${candle_upnl:.4f}{marker}")
        
    except Exception as e:
        print(f"Error fetching market data: {e}")

if __name__ == "__main__":
    check_open_position()