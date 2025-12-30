#!/usr/bin/env python3
import ccxt
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv('.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap'
    }
})

print("Checking for HEMI position/liquidation...")
print("="*60)

try:
    # Check all positions
    positions = exchange.fetch_positions()
    
    hemi_found = False
    for pos in positions:
        if 'HEMI' in pos['symbol']:
            print(f"Found HEMI position: {pos['symbol']}")
            print(f"  Side: {pos['side']}")
            print(f"  Contracts: {pos['contracts']}")
            print(f"  Entry Price: ${pos.get('entryPrice', 'N/A')}")
            print(f"  Mark Price: ${pos.get('markPrice', 'N/A')}")
            print(f"  UPNL: ${pos.get('unrealizedPnl', 0):.4f}")
            print(f"  Percentage: {pos.get('percentage', 0):.2f}%")
            hemi_found = True
    
    if not hemi_found:
        print("No active HEMI position found")
        
    # Try to check recent trades for liquidation info
    print("\nChecking recent account activity...")
    try:
        # Fetch account balance history to check for liquidation events
        balance = exchange.fetch_balance()
        print(f"Current USDT balance: ${balance['USDT']['total']:.2f}")
        
        # Check for HEMI trades in last 24 hours
        since = exchange.milliseconds() - 24*60*60*1000
        all_trades = []
        
        # Try different HEMI symbols
        hemi_symbols = ['HEMI/USDT:USDT', 'HEMI/USDT', 'HEMISOL/USDT:USDT']
        
        for symbol in hemi_symbols:
            try:
                trades = exchange.fetch_my_trades(symbol, since=since, limit=20)
                if trades:
                    all_trades.extend(trades)
                    print(f"\nFound trades for {symbol}:")
                    for trade in trades[:5]:
                        print(f"  {trade['datetime']}: {trade['side']} {trade['amount']} @ ${trade['price']:.6f}")
                        if trade.get('info', {}).get('orderType') == 'liquidation':
                            print(f"  ⚠️ LIQUIDATION DETECTED!")
            except:
                pass
        
        if not all_trades:
            print("No HEMI trades found in last 24 hours")
            
    except Exception as e:
        print(f"Could not fetch trade history: {e}")
        
except Exception as e:
    print(f"Error: {e}")