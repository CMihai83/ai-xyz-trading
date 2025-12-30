#!/usr/bin/env python3
"""
Analyze the SPBL flag in Bitget spot trading
SPBL appears to be the spot trading designation
"""

import requests
import json
import os
from dotenv import load_dotenv
import hmac
import hashlib
import base64
import time

load_dotenv()

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

print("=" * 80)
print("ANALYZING SPBL FLAG IN BITGET SPOT API")
print("=" * 80)

# Check the V1 spot products endpoint
endpoint = "/api/spot/v1/public/products"
url = f"https://api.bitget.com{endpoint}"

response = requests.get(url, timeout=10)

if response.status_code == 200:
    data = response.json()
    
    if data.get('code') == '00000':
        products = data.get('data', [])
        
        print(f"\nTotal products: {len(products)}")
        
        # Analyze the symbol patterns
        spbl_products = []
        non_spbl_products = []
        
        for product in products:
            symbol = product.get('symbol', '')
            if '_SPBL' in symbol:
                spbl_products.append(product)
            else:
                non_spbl_products.append(product)
        
        print(f"Products with _SPBL suffix: {len(spbl_products)}")
        print(f"Products without _SPBL suffix: {len(non_spbl_products)}")
        
        # Check if all products have SPBL
        if len(non_spbl_products) == 0:
            print("\n✅ ALL spot products have _SPBL suffix - this is the standard spot designation")
        
        # Analyze specific high-volume pairs
        print("\n" + "=" * 80)
        print("CHECKING SPECIFIC PAIRS:")
        print("=" * 80)
        
        target_pairs = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'DOGEUSDT', 'PEPEUSDT']
        
        for target in target_pairs:
            found = False
            for product in products:
                if product.get('symbolName') == target:
                    symbol = product.get('symbol')
                    status = product.get('status')
                    
                    # Check if this has any special designation
                    print(f"\n{target}:")
                    print(f"  Symbol ID: {symbol}")
                    print(f"  Status: {status}")
                    
                    # Check for SP in the symbol
                    if 'SP' in symbol and '_SPBL' not in symbol:
                        print(f"  ✅ FOUND SP FLAG! Symbol contains 'SP' without being just SPBL")
                    
                    found = True
                    break
            
            if not found:
                print(f"\n{target}: Not found in spot products")
        
        # Look for any products with SP (not SPBL) designation
        print("\n" + "=" * 80)
        print("SEARCHING FOR SP (SUPERPAIR) DESIGNATION:")
        print("=" * 80)
        
        sp_products = []
        for product in products:
            symbol = product.get('symbol', '')
            symbol_name = product.get('symbolName', '')
            
            # Look for SP that's not part of SPBL
            if 'SP' in symbol.replace('_SPBL', ''):
                sp_products.append({
                    'symbol': symbol,
                    'name': symbol_name,
                    'status': product.get('status')
                })
        
        if sp_products:
            print(f"\n✅ Found {len(sp_products)} products with potential SP designation:")
            for sp in sp_products[:20]:
                print(f"  {sp['name']}: {sp['symbol']} (Status: {sp['status']})")
        else:
            print("\n❌ No products found with SP designation (other than SPBL suffix)")
            print("SPBL appears to be the standard spot designation, not a superpair flag")

# Now check if there's a different endpoint for superpairs
print("\n" + "=" * 80)
print("CHECKING OTHER ENDPOINTS FOR SUPERPAIR INFO:")
print("=" * 80)

other_endpoints = [
    "/api/v2/spot/public/coins",
    "/api/v2/spot/public/symbols", 
    "/api/spot/v1/market/tickers",
]

for endpoint in other_endpoints:
    print(f"\nChecking: {endpoint}")
    
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
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            data_str = json.dumps(data).upper()
            
            # Look for superpair indicators
            if 'SUPERPAIR' in data_str:
                print("  ✅ Found 'SUPERPAIR' in response!")
            if '"SP":TRUE' in data_str or '"SP":"TRUE"' in data_str:
                print("  ✅ Found SP flag set to true!")
            if 'ISPREMIUM' in data_str:
                print("  ✅ Found 'ISPREMIUM' flag!")
            
            # Check if BTC has any special field
            if 'BTCUSDT' in data_str:
                # Try to find BTC's data
                if 'data' in data:
                    items = data['data']
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict):
                                if 'BTC' in str(item.get('symbol', '')).upper() or 'BTC' in str(item.get('coin', '')).upper():
                                    # Check all fields for special values
                                    for key, value in item.items():
                                        if isinstance(value, bool) and value:
                                            print(f"    BTC has {key}=True")
                                        elif isinstance(value, str) and value.upper() in ['PREMIUM', 'SUPER', 'SP', 'VIP']:
                                            print(f"    BTC has {key}={value}")
                                    break
        else:
            print(f"  Response: {response.status_code}")
            
    except Exception as e:
        print(f"  Error: {e}")

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("SPBL = Spot Bitget Listing (standard spot designation)")
print("Looking for actual SP (superpair) flag...")