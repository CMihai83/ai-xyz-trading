#!/usr/bin/env python3
"""
Check Bitget SPOT trading API for superpair/SP flag
"""

import ccxt
import json
import requests
import hmac
import hashlib
import base64
import time
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("CHECKING BITGET SPOT TRADING API FOR SUPERPAIR FLAG")
print("=" * 80)

# Method 1: Check using CCXT with spot market type
print("\n1. CHECKING SPOT MARKETS WITH CCXT")
print("-" * 50)

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'spot',  # Change to spot
    }
})

# Load spot markets
markets = exchange.load_markets()

print(f"Total spot markets loaded: {len([m for m in markets.values() if m['spot']])}")

# Check for SP/superpair in spot markets
sp_markets = []
for symbol, market in markets.items():
    if market['spot']:
        # Check the full market structure for SP indicators
        market_str = json.dumps(market).upper()
        info_str = json.dumps(market.get('info', {})).upper()
        
        # Look for various SP indicators
        if ('SUPERPAIR' in market_str or 'SUPER_PAIR' in market_str or 
            'ISPREMIUM' in market_str or 'ISSUPER' in market_str or
            '"SP"' in info_str or 'SYMBOLTYPE":"SP' in info_str):
            sp_markets.append((symbol, market))
            print(f"  Found potential SP indicator in: {symbol}")

# Check first spot market structure in detail
spot_symbols = [s for s, m in markets.items() if m['spot']]
if spot_symbols:
    first_spot = spot_symbols[0]
    market = markets[first_spot]
    print(f"\n{first_spot} Spot Market Full Structure:")
    print("-" * 50)
    
    # Print all fields
    for key, value in market.items():
        if key != 'info':  # Skip info for now
            print(f"  {key}: {value}")
    
    # Print info dict
    info = market.get('info', {})
    print(f"\n{first_spot} Info Dict Fields:")
    for key, value in info.items():
        print(f"  {key}: {value}")
        # Check if any field contains SP/super
        if isinstance(value, str) and ('SP' in value.upper() or 'SUPER' in value.upper()):
            print(f"    ^^^ FOUND SP/SUPER INDICATOR!")

# Method 2: Direct API call to spot endpoints
print("\n\n2. CHECKING DIRECT SPOT API ENDPOINTS")
print("-" * 50)

api_key = os.getenv('BITGET_API_KEY')
api_secret = os.getenv('BITGET_API_SECRET')
passphrase = os.getenv('BITGET_API_PASSPHRASE')

def generate_signature(timestamp: str, method: str, request_path: str, body: str = "") -> str:
    message = timestamp + method.upper() + request_path + body
    signature = base64.b64encode(
        hmac.new(
            api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).digest()
    ).decode('utf-8')
    return signature

# Check spot symbols endpoint
endpoints = [
    "/api/v2/spot/public/symbols",
    "/api/v2/spot/market/tickers",
    "/api/spot/v1/public/products",  # V1 endpoint
]

for endpoint in endpoints:
    print(f"\nChecking endpoint: {endpoint}")
    print("-" * 40)
    
    try:
        timestamp = str(int(time.time() * 1000))
        signature = generate_signature(timestamp, 'GET', endpoint)
        
        headers = {
            'ACCESS-KEY': api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': passphrase,
            'Content-Type': 'application/json',
            'locale': 'en-US'
        }
        
        url = f"https://api.bitget.com{endpoint}"
        
        # Try with auth first, then without if it fails
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            response = requests.get(url, timeout=10)  # Try public
        
        if response.status_code == 200:
            data = response.json()
            
            # Convert to string to search
            data_str = json.dumps(data).upper()
            
            # Search for SP/superpair indicators
            if 'SUPERPAIR' in data_str or 'SUPER_PAIR' in data_str:
                print("  ✅ FOUND 'SUPERPAIR' in response!")
            if '"SP"' in data_str or '"SP":' in data_str:
                print("  ✅ FOUND 'SP' flag in response!")
            if 'ISPREMIUM' in data_str:
                print("  ✅ FOUND 'ISPREMIUM' in response!")
            if 'SYMBOLTYPE' in data_str:
                print("  ✅ FOUND 'SYMBOLTYPE' field in response!")
                
            # Check structure of first item
            if 'data' in data and isinstance(data['data'], list) and len(data['data']) > 0:
                first_item = data['data'][0]
                print(f"\n  First item structure:")
                for key, value in first_item.items():
                    print(f"    {key}: {value}")
                    if isinstance(value, str) and ('SP' in value.upper() or 'SUPER' in value.upper()):
                        print(f"      ^^^ CONTAINS SP/SUPER!")
        else:
            print(f"  Response code: {response.status_code}")
            
    except Exception as e:
        print(f"  Error: {e}")

# Method 3: Check if certain spot pairs have special designation
print("\n\n3. COMPARING SPOT PAIRS FOR PATTERNS")
print("-" * 50)

# Known high-volume spot pairs
test_pairs = ['BTC/USDT', 'ETH/USDT', 'DOGE/USDT', 'PEPE/USDT']

for pair in test_pairs:
    if pair in markets:
        market = markets[pair]
        info = market.get('info', {})
        print(f"\n{pair} Spot Info:")
        
        # Check all fields for special values
        special_fields = {}
        for key, value in info.items():
            # Look for fields that might indicate premium status
            if key.lower() in ['status', 'type', 'tag', 'label', 'tier', 'grade', 'class', 'symboltype', 'category']:
                special_fields[key] = value
        
        if special_fields:
            for key, value in special_fields.items():
                print(f"  {key}: {value}")

print("\n" + "=" * 80)
print("SEARCH COMPLETE")
print("=" * 80)