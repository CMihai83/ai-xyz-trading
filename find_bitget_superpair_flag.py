#!/usr/bin/env python3
"""
Deep search for Bitget superpair flag in all available data
"""

import requests
import json
import hmac
import hashlib
import base64
import time
import os
from dotenv import load_dotenv

load_dotenv()

class BitgetSuperpairFinder:
    def __init__(self):
        self.api_key = os.getenv('BITGET_API_KEY')
        self.api_secret = os.getenv('BITGET_API_SECRET')
        self.passphrase = os.getenv('BITGET_API_PASSPHRASE')
        self.base_url = "https://api.bitget.com"
        
    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Generate signature for API authentication."""
        message = timestamp + method.upper() + request_path + body
        signature = base64.b64encode(
            hmac.new(
                self.api_secret.encode('utf-8'),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
        ).decode('utf-8')
        return signature
    
    def _get_headers(self, method: str, request_path: str, body: str = "") -> dict:
        """Get headers for API request."""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, request_path, body)
        
        return {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json',
            'locale': 'en-US'
        }
    
    def search_all_endpoints(self):
        """Search all possible endpoints for superpair information"""
        
        # List of all possible Bitget endpoints that might contain superpair info
        endpoints = [
            # Market data endpoints
            ("/api/v2/mix/market/contracts", "USDT-FUTURES"),
            ("/api/v2/mix/market/tickers", "USDT-FUTURES"),
            ("/api/v2/mix/market/ticker", None),  # Might need symbol param
            ("/api/v2/mix/market/fills", None),
            ("/api/v2/mix/market/candles", None),
            
            # Spot market endpoints (might have different structure)
            ("/api/v2/spot/public/symbols", None),
            ("/api/v2/spot/market/tickers", None),
            
            # Public endpoints (no auth needed)
            ("/api/v2/public/mix/market/contracts", "USDT-FUTURES"),
            ("/api/v2/public/products", None),
            
            # V1 endpoints (older API)
            ("/api/mix/v1/market/contracts", "umcbl"),
            ("/api/mix/v1/market/tickers", "umcbl"),
        ]
        
        superpair_indicators = [
            'superpair', 'superPair', 'isSuperPair', 'super_pair',
            'isPremium', 'premium', 'isSuper', 'super',
            'SP', 'sp', 'elite', 'vip', 'pro',
            'tag', 'tags', 'label', 'labels', 'type',
            'category', 'tier', 'grade', 'class'
        ]
        
        found_indicators = {}
        
        for endpoint, product_type in endpoints:
            print(f"\n{'='*70}")
            print(f"Checking: {endpoint}")
            print('='*70)
            
            try:
                # Build URL with parameters
                url = f"{self.base_url}{endpoint}"
                if product_type:
                    url += f"?productType={product_type}"
                
                # Try with authentication
                headers = self._get_headers('GET', endpoint.split('?')[0])
                response = requests.get(url, headers=headers, timeout=5)
                
                if response.status_code != 200:
                    # Try without authentication (public endpoint)
                    response = requests.get(url, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Convert to string for deep search
                    data_str = json.dumps(data).lower()
                    
                    # Search for any superpair indicators
                    for indicator in superpair_indicators:
                        if indicator.lower() in data_str:
                            print(f"  ✅ Found '{indicator}' in response!")
                            found_indicators[endpoint] = indicator
                            
                            # Try to find the exact location
                            if isinstance(data, dict) and 'data' in data:
                                items = data['data']
                                if isinstance(items, list) and len(items) > 0:
                                    # Check first item
                                    first_item = items[0]
                                    for key in first_item.keys():
                                        if indicator.lower() in key.lower():
                                            print(f"    Found in field: {key} = {first_item[key]}")
                                            
                                            # Check a few more items to see the pattern
                                            print(f"\n    Checking multiple items for '{key}':")
                                            for i, item in enumerate(items[:10]):
                                                value = item.get(key, 'N/A')
                                                symbol = item.get('symbol', item.get('instId', 'unknown'))
                                                print(f"      {symbol}: {key}={value}")
                    
                    # Also print first item structure if we haven't found indicators
                    if endpoint not in found_indicators and isinstance(data, dict) and 'data' in data:
                        items = data.get('data', [])
                        if items and isinstance(items, list) and len(items) > 0:
                            print("\n  First item structure (searching for hidden flags):")
                            first_item = items[0]
                            for key, value in first_item.items():
                                # Print all fields to manually inspect
                                if isinstance(value, (str, int, float, bool)):
                                    print(f"    {key}: {value}")
                                elif isinstance(value, list) and len(value) > 0:
                                    print(f"    {key}: {value[:3]}...")  # Show first 3 items
                                    
                else:
                    print(f"  Response code: {response.status_code}")
                    
            except Exception as e:
                print(f"  Error: {e}")
        
        print(f"\n{'='*70}")
        print("SUMMARY")
        print('='*70)
        
        if found_indicators:
            print("\n✅ Found superpair indicators in these endpoints:")
            for endpoint, indicator in found_indicators.items():
                print(f"  {endpoint}: '{indicator}'")
        else:
            print("\n❌ No explicit superpair flags found in Bitget API")
            print("\nBitget appears to identify premium pairs by characteristics:")
            print("  - High leverage (>= 100x)")
            print("  - Low fees (<= 0.02%)")
            print("  - High position limits (>= 150)")
            print("\nThese pairs are effectively 'superpairs' with premium features.")

if __name__ == "__main__":
    finder = BitgetSuperpairFinder()
    finder.search_all_endpoints()