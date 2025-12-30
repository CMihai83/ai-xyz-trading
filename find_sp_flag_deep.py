#!/usr/bin/env python3
"""
Deep search for Bitget's actual SP/Superpair flag
Check all available fields and endpoints
"""

import ccxt
import json
import requests
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 80)
print("DEEP SEARCH FOR BITGET SP/SUPERPAIR FLAG")
print("=" * 80)

# Method 1: Check using CCXT with raw response
print("\n1. CHECKING RAW CCXT RESPONSES")
print("-" * 50)

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

# Enable verbose mode to see raw responses
exchange.verbose = True

# Load markets and check raw response
try:
    markets = exchange.load_markets()
    
    # Check if exchange has raw response
    if hasattr(exchange, 'last_response_headers'):
        print("Raw response headers available")
    
    # Check a specific symbol's full structure
    test_symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']
    
    for symbol in test_symbols:
        if symbol in markets:
            market = markets[symbol]
            print(f"\n{symbol} Full Market Structure:")
            
            # Print ALL fields
            for key, value in market.items():
                print(f"  {key}: {value}")
            
            # Check info dict completely
            info = market.get('info', {})
            print(f"\n{symbol} Info Dict (ALL FIELDS):")
            for key, value in info.items():
                print(f"  {key}: {value}")
                
                # If value is a string, check if it contains SP
                if isinstance(value, str) and ('SP' in value.upper() or 'SUPER' in value.upper()):
                    print(f"    ^^^ FOUND SP/SUPER INDICATOR IN {key}!")
            
            break  # Just check first symbol in detail

except Exception as e:
    print(f"Error: {e}")

# Method 2: Direct API call to check response structure
print("\n\n2. CHECKING DIRECT API RESPONSES")
print("-" * 50)

import hmac
import hashlib
import base64
import time

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

# Try V2 Mix endpoint
endpoint = "/api/v2/mix/market/contracts"
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

url = f"https://api.bitget.com{endpoint}?productType=USDT-FUTURES"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    if data.get('code') == '00000':
        contracts = data.get('data', [])
        
        # Check all unique fields across all contracts
        all_fields = set()
        sp_contracts = []
        
        for contract in contracts:
            all_fields.update(contract.keys())
            
            # Check each field for SP/super indicators
            for key, value in contract.items():
                if isinstance(value, str):
                    if 'SP' in value or 'SUPER' in value.upper():
                        sp_contracts.append({
                            'symbol': contract.get('symbol'),
                            'field': key,
                            'value': value
                        })
        
        print(f"All available fields in contracts: {sorted(all_fields)}")
        
        if sp_contracts:
            print(f"\n✅ FOUND CONTRACTS WITH SP/SUPER INDICATORS:")
            for sp in sp_contracts[:10]:
                print(f"  {sp['symbol']}: {sp['field']}={sp['value']}")
        
        # Check if there's a specific pattern for known superpairs
        print("\n3. ANALYZING KNOWN SUPERPAIRS FOR PATTERNS")
        print("-" * 50)
        
        # These are likely superpairs based on trading characteristics
        likely_superpairs = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT']
        
        for sp_symbol in likely_superpairs:
            for contract in contracts:
                if contract.get('symbol') == sp_symbol:
                    print(f"\n{sp_symbol} Contract Details:")
                    # Print every field to look for patterns
                    for key, value in contract.items():
                        print(f"  {key}: {value}")
                    break

# Method 3: Check ticker endpoint for additional fields
print("\n\n4. CHECKING TICKER ENDPOINT FOR SP FLAGS")
print("-" * 50)

endpoint = "/api/v2/mix/market/tickers"
timestamp = str(int(time.time() * 1000))
signature = generate_signature(timestamp, 'GET', endpoint)

headers['ACCESS-TIMESTAMP'] = timestamp
headers['ACCESS-SIGN'] = signature

url = f"https://api.bitget.com{endpoint}?productType=USDT-FUTURES"
response = requests.get(url, headers=headers)

if response.status_code == 200:
    data = response.json()
    if data.get('code') == '00000':
        tickers = data.get('data', [])
        
        if tickers:
            print(f"First ticker structure:")
            first_ticker = tickers[0]
            for key, value in first_ticker.items():
                print(f"  {key}: {value}")
            
            # Check for SP in any ticker
            sp_tickers = []
            for ticker in tickers:
                ticker_str = json.dumps(ticker).upper()
                if 'SP' in ticker_str or 'SUPER' in ticker_str:
                    # Find which field contains it
                    for key, value in ticker.items():
                        if isinstance(value, str) and ('SP' in value.upper() or 'SUPER' in value.upper()):
                            sp_tickers.append({
                                'symbol': ticker.get('symbol'),
                                'field': key,
                                'value': value
                            })
            
            if sp_tickers:
                print(f"\n✅ FOUND TICKERS WITH SP/SUPER INDICATORS:")
                for sp in sp_tickers[:10]:
                    print(f"  {sp['symbol']}: {sp['field']}={sp['value']}")

print("\n" + "=" * 80)
print("SEARCH COMPLETE")
print("=" * 80)