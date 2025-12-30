#!/usr/bin/env python3
"""
Check Bitget symbols with direct API call to get detailed symbol information
Superpairs might be identified through a different field or endpoint
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

class BitgetAPIChecker:
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
    
    def check_symbols(self):
        """Check symbol information from Bitget API"""
        
        # Try different endpoints that might have superpair information
        endpoints = [
            "/api/v2/mix/market/contracts",  # Contract information
            "/api/v2/mix/market/symbols",     # Symbol information
            "/api/v2/mix/market/tickers",     # Ticker information with all symbols
        ]
        
        for endpoint in endpoints:
            print(f"\n{'='*70}")
            print(f"Checking endpoint: {endpoint}")
            print('='*70)
            
            try:
                headers = self._get_headers('GET', endpoint)
                response = requests.get(f"{self.base_url}{endpoint}?productType=USDT-FUTURES", headers=headers)
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get('code') == '00000':
                        items = data.get('data', [])
                        
                        if items and len(items) > 0:
                            # Check first item structure
                            print(f"First item structure:")
                            print(json.dumps(items[0] if isinstance(items, list) else items, indent=2))
                            
                            # Look for superpair indicators
                            if isinstance(items, list):
                                print(f"\nTotal items: {len(items)}")
                                
                                # Check for superpair fields
                                superpair_symbols = []
                                for item in items[:50]:  # Check first 50
                                    # Check various possible fields
                                    symbol = item.get('symbol', '')
                                    
                                    # Check for superpair indicators
                                    if any([
                                        item.get('superpair'),
                                        item.get('isSuperPair'),
                                        item.get('superPair'),
                                        item.get('isPremium'),
                                        item.get('isSuper'),
                                        'SP' in item.get('tags', []),
                                        'super' in str(item.get('label', '')).lower(),
                                        'premium' in str(item.get('label', '')).lower(),
                                    ]):
                                        superpair_symbols.append(symbol)
                                        print(f"  Found superpair: {symbol}")
                                
                                if superpair_symbols:
                                    print(f"\nSuperpairs found: {superpair_symbols}")
                                else:
                                    print("\nNo explicit superpair flags found in this endpoint")
                    else:
                        print(f"API Error: {data.get('msg', 'Unknown error')}")
                else:
                    print(f"HTTP Error: {response.status_code}")
                    
            except Exception as e:
                print(f"Error checking endpoint: {e}")
        
        # Also check if superpairs are identified by trading rules
        print(f"\n{'='*70}")
        print("Checking if superpairs are identified by trading characteristics")
        print('='*70)
        
        # Get contracts endpoint which has more detailed info
        endpoint = "/api/v2/mix/market/contracts"
        headers = self._get_headers('GET', endpoint)
        response = requests.get(f"{self.base_url}{endpoint}?productType=USDT-FUTURES", headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if data.get('code') == '00000':
                contracts = data.get('data', [])
                
                # Analyze characteristics that might indicate superpairs
                print("\nAnalyzing contract characteristics for superpair patterns:")
                
                high_leverage_symbols = []
                low_fee_symbols = []
                high_limit_symbols = []
                
                for contract in contracts[:30]:  # Analyze first 30
                    symbol = contract.get('symbol', '')
                    max_lever = int(contract.get('maxLever', 0))
                    maker_fee = float(contract.get('makerFeeRate', 1))
                    max_position = int(contract.get('maxPositionNum', 0))
                    
                    # Superpairs might have:
                    # - Higher max leverage (>= 100)
                    # - Lower fees (<= 0.0002)
                    # - Higher position limits (>= 150)
                    
                    if max_lever >= 100:
                        high_leverage_symbols.append((symbol, max_lever))
                    
                    if maker_fee <= 0.0002:
                        low_fee_symbols.append((symbol, maker_fee))
                    
                    if max_position >= 150:
                        high_limit_symbols.append((symbol, max_position))
                
                print(f"\nHigh leverage symbols (>= 100x): {len(high_leverage_symbols)}")
                for sym, lev in high_leverage_symbols[:5]:
                    print(f"  {sym}: {lev}x")
                
                print(f"\nLow fee symbols (<= 0.02%): {len(low_fee_symbols)}")
                for sym, fee in low_fee_symbols[:5]:
                    print(f"  {sym}: {fee*100:.3f}%")
                
                print(f"\nHigh position limit symbols (>= 150): {len(high_limit_symbols)}")
                for sym, limit in high_limit_symbols[:5]:
                    print(f"  {sym}: {limit} positions")
                
                # Find symbols that meet all criteria (likely superpairs)
                likely_superpairs = set()
                for sym, _ in high_leverage_symbols:
                    if any(s[0] == sym for s in low_fee_symbols) and any(s[0] == sym for s in high_limit_symbols):
                        likely_superpairs.add(sym)
                
                if likely_superpairs:
                    print(f"\n🎯 LIKELY SUPERPAIRS (meet all premium criteria):")
                    for sym in list(likely_superpairs)[:20]:
                        print(f"  - {sym}")

if __name__ == "__main__":
    checker = BitgetAPIChecker()
    checker.check_symbols()