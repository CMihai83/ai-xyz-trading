#!/usr/bin/env python3
"""
Check Bitget market data structure to find the superpair flag
"""

import ccxt
import json
import os
from dotenv import load_dotenv

load_dotenv()

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

# Load markets
markets = exchange.load_markets()

print("=" * 70)
print("CHECKING BITGET MARKET DATA STRUCTURE FOR SUPERPAIR FLAG")
print("=" * 70)

# Check a few known symbols to see their market info structure
test_symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']

for symbol in test_symbols:
    if symbol in markets:
        market = markets[symbol]
        print(f"\n{symbol} Market Info:")
        print("-" * 50)
        
        # Print the raw info dict to see all fields
        info = market.get('info', {})
        
        # Pretty print the info dict
        print(json.dumps(info, indent=2))
        
        # Check for specific superpair-related fields
        print("\nChecking for superpair indicators:")
        print(f"  - 'superpair' field: {info.get('superpair', 'NOT FOUND')}")
        print(f"  - 'isSuperPair' field: {info.get('isSuperPair', 'NOT FOUND')}")
        print(f"  - 'superPair' field: {info.get('superPair', 'NOT FOUND')}")
        print(f"  - 'tags' field: {info.get('tags', 'NOT FOUND')}")
        print(f"  - 'label' field: {info.get('label', 'NOT FOUND')}")
        print(f"  - 'symbolType' field: {info.get('symbolType', 'NOT FOUND')}")
        
        print("\n" + "=" * 70)
        
        # Only check first symbol in detail to avoid too much output
        break

# Now check all markets to find any with superpair indicators
print("\nScanning all markets for superpair flags...")
superpair_count = 0
superpair_symbols = []

for symbol, market in markets.items():
    if market['type'] != 'swap' or market['quote'] != 'USDT':
        continue
    
    info = market.get('info', {})
    
    # Check various possible superpair indicators
    is_superpair = False
    
    # Check different possible field names
    if info.get('superpair') or info.get('isSuperPair') or info.get('superPair'):
        is_superpair = True
    
    # Check if symbolType indicates superpair
    if info.get('symbolType') == 'superpair':
        is_superpair = True
    
    # Check tags
    tags = info.get('tags', [])
    if isinstance(tags, list) and any('super' in str(tag).lower() for tag in tags):
        is_superpair = True
    
    # Check label
    label = info.get('label', '')
    if 'super' in str(label).lower():
        is_superpair = True
    
    if is_superpair:
        superpair_count += 1
        superpair_symbols.append(symbol)
        print(f"  Found superpair: {symbol}")

print(f"\nTotal superpairs found: {superpair_count}")
if superpair_symbols:
    print("Superpair symbols:", superpair_symbols[:10])  # Show first 10