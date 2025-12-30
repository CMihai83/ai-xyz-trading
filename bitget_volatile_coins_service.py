#!/usr/bin/env python3
"""
Bitget Top Volatile Coins Service
Fetches and maintains a list of the most volatile coins from Bitget
"""

import ccxt
import time
import json
from datetime import datetime
from typing import List, Dict, Optional
import os
import sys
import threading

class BitgetVolatileCoinsService:
    """Service to fetch and cache top volatile coins from Bitget"""
    
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
            'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
            'password': '2609Luiza',
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'defaultMarginMode': 'isolated'
            }
        })
        
        self.cache_file = '/app/top_volatile_coins.json'
        self.top_volatile_coins = []
        self.last_update = None
        self.update_interval = 300  # Update every 5 minutes
        self.running = False
        
    def fetch_top_volatile_coins(self, limit: int = 20) -> List[Dict]:
        """Fetch top volatile coins from Bitget"""
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching top volatile coins from Bitget...")
            
            # Get all USDT perpetual tickers
            tickers = self.exchange.fetch_tickers()
            
            # Filter for USDT perpetuals and calculate volatility metrics
            volatile_coins = []
            
            for symbol, ticker in tickers.items():
                if ':USDT' in symbol and ticker.get('percentage'):
                    # Calculate volatility score based on 24h change and volume
                    change_24h = abs(ticker.get('percentage', 0))
                    volume_24h = ticker.get('quoteVolume', 0)
                    
                    # Volatility score: weighted combination of price change and volume
                    volatility_score = change_24h * (1 + min(volume_24h / 1000000, 10))
                    
                    volatile_coins.append({
                        'symbol': symbol,
                        'base': symbol.split('/')[0] if '/' in symbol else symbol.replace(':USDT', ''),
                        'change_24h': ticker.get('percentage', 0),
                        'abs_change_24h': change_24h,
                        'volume_24h': volume_24h,
                        'volatility_score': volatility_score,
                        'price': ticker.get('last', 0),
                        'timestamp': datetime.now().isoformat()
                    })
            
            # Sort by volatility score
            volatile_coins.sort(key=lambda x: x['volatility_score'], reverse=True)
            
            # Take top coins
            top_coins = volatile_coins[:limit]
            
            print(f"✅ Found {len(top_coins)} top volatile coins")
            print(f"   Top 5 volatile coins:")
            for i, coin in enumerate(top_coins[:5], 1):
                print(f"   {i}. {coin['base']}: {coin['change_24h']:.2f}% change, score: {coin['volatility_score']:.2f}")
            
            return top_coins
            
        except Exception as e:
            print(f"❌ Error fetching volatile coins: {e}")
            return []
    
    def update_cache(self):
        """Update the cached list of top volatile coins"""
        try:
            top_coins = self.fetch_top_volatile_coins()
            
            if top_coins:
                self.top_volatile_coins = top_coins
                self.last_update = datetime.now()
                
                # Save to file
                cache_data = {
                    'last_update': self.last_update.isoformat(),
                    'coins': top_coins
                }
                
                with open(self.cache_file, 'w') as f:
                    json.dump(cache_data, f, indent=2)
                
                print(f"✅ Cache updated with {len(top_coins)} volatile coins")
                return True
            
        except Exception as e:
            print(f"❌ Error updating cache: {e}")
        
        return False
    
    def load_cache(self) -> bool:
        """Load cached volatile coins from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                
                self.top_volatile_coins = cache_data.get('coins', [])
                self.last_update = datetime.fromisoformat(cache_data.get('last_update'))
                
                # Check if cache is stale (older than 10 minutes)
                age = (datetime.now() - self.last_update).total_seconds()
                if age > 600:
                    print(f"⚠️ Cache is {age/60:.1f} minutes old, updating...")
                    return self.update_cache()
                
                print(f"✅ Loaded {len(self.top_volatile_coins)} coins from cache (age: {age/60:.1f} min)")
                return True
                
        except Exception as e:
            print(f"⚠️ Could not load cache: {e}")
        
        return False
    
    def get_top_volatile_symbols(self, limit: int = 2) -> List[str]:
        """Get the top N most volatile symbols"""
        # Load cache if not loaded or stale
        if not self.top_volatile_coins or not self.last_update:
            if not self.load_cache():
                self.update_cache()
        else:
            # Check if cache needs refresh
            age = (datetime.now() - self.last_update).total_seconds()
            if age > self.update_interval:
                self.update_cache()
        
        # Return top symbols
        symbols = []
        for coin in self.top_volatile_coins[:limit]:
            symbol = coin['symbol']
            if symbol and ':' in symbol:
                symbols.append(symbol)
        
        return symbols
    
    def get_top_volatile_coins(self, limit: int = 10) -> List[Dict]:
        """Get top volatile coins with their details"""
        # Ensure cache is fresh
        if not self.top_volatile_coins or not self.last_update:
            if not self.load_cache():
                self.update_cache()
        else:
            age = (datetime.now() - self.last_update).total_seconds()
            if age > self.update_interval:
                self.update_cache()
        
        return self.top_volatile_coins[:limit]
    
    def start_background_updates(self):
        """Start background thread to update volatile coins periodically"""
        if self.running:
            print("⚠️ Background updates already running")
            return
        
        self.running = True
        
        def update_loop():
            print(f"🚀 Starting volatile coins background updater...")
            while self.running:
                try:
                    self.update_cache()
                    time.sleep(self.update_interval)
                except Exception as e:
                    print(f"❌ Error in update loop: {e}")
                    time.sleep(60)  # Wait a minute on error
        
        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()
        print(f"✅ Background updater started (updates every {self.update_interval/60:.1f} minutes)")
    
    def stop(self):
        """Stop the background updates"""
        self.running = False
        print("⏹️ Stopping volatile coins service...")

# Global instance
volatile_coins_service = None

def get_volatile_coins_service():
    """Get or create the global volatile coins service instance"""
    global volatile_coins_service
    if volatile_coins_service is None:
        volatile_coins_service = BitgetVolatileCoinsService()
    return volatile_coins_service

if __name__ == "__main__":
    # Test the service
    service = get_volatile_coins_service()
    
    print("\n=== Bitget Volatile Coins Service Test ===\n")
    
    # Update cache
    service.update_cache()
    
    # Get top 2 symbols
    print(f"\nTop 2 volatile symbols: {service.get_top_volatile_symbols(2)}")
    
    # Show top 5 volatile coins
    print("\nTop 5 volatile coins:")
    for coin in service.get_top_volatile_coins(5):
        print(f"  {coin['base']}: {coin['change_24h']:.2f}% ({coin['volatility_score']:.2f} score)")