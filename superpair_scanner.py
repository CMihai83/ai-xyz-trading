#!/usr/bin/env python3
"""
Optimized Superpair Scanner for AI XYZ Trading System
Efficiently identifies and monitors Bitget superpair symbols
"""

import asyncio
import ccxt.async_support as ccxt
from typing import List, Dict, Any, Set
import structlog
from datetime import datetime
import os
import json
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger(__name__)

class SuperpairScanner:
    """
    Optimized scanner specifically for Bitget superpairs
    Superpairs are identified by:
    - High volume (>$10M daily)
    - Tight spreads (<0.05%)
    - High liquidity depth
    - Special market tags
    """
    
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'defaultMarginMode': 'isolated'
            }
        })
        
        # Superpair identification criteria
        self.min_volume_threshold = 10_000_000  # $10M daily volume
        self.max_spread_threshold = 0.0005      # 0.05% max spread
        self.min_liquidity_score = 0.8          # High liquidity score
        
        # Known superpair patterns (based on Bitget's common superpairs)
        self.known_superpair_bases = {
            'BTC', 'ETH', 'SOL', 'DOGE', 'PEPE', 'WIF', 
            'ARB', 'OP', 'INJ', 'AVAX', 'MATIC', 'LINK',
            'ADA', 'DOT', 'UNI', 'BNB', 'XRP', 'SUI',
            'WLD', 'TIA', 'SEI', 'JUP', 'BONK', 'FLOKI'
        }
        
        self.superpairs_cache = {}
        self.last_scan_time = None
        
    async def initialize(self):
        """Initialize exchange connection"""
        try:
            await self.exchange.load_markets()
            logger.info("Superpair scanner initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize scanner: {e}")
            return False
    
    async def quick_identify_superpairs(self) -> Set[str]:
        """
        Quick identification of superpairs using market structure
        and known patterns
        """
        superpairs = set()
        
        try:
            markets = self.exchange.markets
            
            # First pass: identify by market structure
            for symbol, market in markets.items():
                if not (market['active'] and 
                       market['type'] == 'swap' and
                       market['quote'] == 'USDT'):
                    continue
                
                # Check if base is in known superpair bases
                if market['base'] in self.known_superpair_bases:
                    superpairs.add(symbol)
                
                # Check market info for superpair indicators
                info = market.get('info', {})
                
                # Check for explicit superpair tags
                if any(tag in str(info).lower() for tag in ['super', 'premium', 'sp']):
                    superpairs.add(symbol)
                
                # Check contract specifications that indicate superpair
                if info.get('contractType') == 'perpetual':
                    # Check for favorable contract specs
                    min_leverage = info.get('minLeverage', 1)
                    max_leverage = info.get('maxLeverage', 1)
                    
                    # Superpairs typically have higher max leverage
                    if max_leverage >= 50:
                        superpairs.add(symbol)
            
            logger.info(f"Quick scan identified {len(superpairs)} potential superpairs")
            return superpairs
            
        except Exception as e:
            logger.error(f"Error in quick identification: {e}")
            return set()
    
    async def validate_superpair(self, symbol: str) -> Dict[str, Any]:
        """
        Validate if a symbol meets superpair criteria
        Returns validation data
        """
        try:
            # Fetch ticker for volume data
            ticker = await self.exchange.fetch_ticker(symbol)
            volume_24h = ticker.get('quoteVolume', 0)
            
            # Fetch orderbook for spread calculation
            orderbook = await self.exchange.fetch_order_book(symbol, limit=5)
            
            if orderbook['bids'] and orderbook['asks']:
                best_bid = orderbook['bids'][0][0]
                best_ask = orderbook['asks'][0][0]
                spread = (best_ask - best_bid) / best_bid if best_bid > 0 else 1
                
                # Calculate liquidity depth
                bid_depth = sum(bid[1] * bid[0] for bid in orderbook['bids'][:5])
                ask_depth = sum(ask[1] * ask[0] for ask in orderbook['asks'][:5])
                liquidity_depth = bid_depth + ask_depth
            else:
                spread = 1
                liquidity_depth = 0
            
            # Calculate superpair score
            is_superpair = (
                volume_24h >= self.min_volume_threshold and
                spread <= self.max_spread_threshold
            )
            
            # Calculate quality score (0-100)
            score = 0
            
            # Volume score (max 40 points)
            if volume_24h > 100_000_000:
                score += 40
            elif volume_24h > 50_000_000:
                score += 30
            elif volume_24h > 10_000_000:
                score += 20
            else:
                score += min(10, volume_24h / 1_000_000)
            
            # Spread score (max 30 points)
            if spread < 0.0001:
                score += 30
            elif spread < 0.0005:
                score += 20
            elif spread < 0.001:
                score += 10
            
            # Liquidity score (max 30 points)
            if liquidity_depth > 1_000_000:
                score += 30
            elif liquidity_depth > 500_000:
                score += 20
            elif liquidity_depth > 100_000:
                score += 10
            
            return {
                'symbol': symbol,
                'is_superpair': is_superpair,
                'score': min(100, score),
                'volume_24h': volume_24h,
                'spread': spread,
                'liquidity_depth': liquidity_depth,
                'last_price': ticker['last'],
                'change_24h': ticker['percentage'],
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.warning(f"Failed to validate {symbol}: {e}")
            return {
                'symbol': symbol,
                'is_superpair': False,
                'score': 0,
                'error': str(e)
            }
    
    async def scan_superpairs(self, quick_mode: bool = True) -> List[Dict[str, Any]]:
        """
        Scan and validate superpairs
        quick_mode: Use quick identification without full validation
        """
        results = []
        
        try:
            # Quick identification
            potential_superpairs = await self.quick_identify_superpairs()
            
            if quick_mode:
                # Return quick results without validation
                for symbol in potential_superpairs:
                    results.append({
                        'symbol': symbol,
                        'is_superpair': True,
                        'quick_scan': True,
                        'timestamp': datetime.now().isoformat()
                    })
            else:
                # Full validation (slower but more accurate)
                logger.info(f"Validating {len(potential_superpairs)} potential superpairs...")
                
                # Process in batches to avoid rate limits
                batch_size = 5
                for i in range(0, len(potential_superpairs), batch_size):
                    batch = list(potential_superpairs)[i:i + batch_size]
                    
                    # Validate each symbol in batch
                    validation_tasks = [self.validate_superpair(symbol) for symbol in batch]
                    batch_results = await asyncio.gather(*validation_tasks)
                    
                    # Filter confirmed superpairs
                    for result in batch_results:
                        if result.get('is_superpair') or result.get('score', 0) > 50:
                            results.append(result)
                    
                    # Small delay between batches
                    await asyncio.sleep(0.5)
            
            # Sort by score
            results.sort(key=lambda x: x.get('score', 0), reverse=True)
            
            # Cache results
            self.superpairs_cache = {r['symbol']: r for r in results}
            self.last_scan_time = datetime.now()
            
            logger.info(f"Found {len(results)} confirmed superpairs")
            return results
            
        except Exception as e:
            logger.error(f"Error scanning superpairs: {e}")
            return []
    
    async def get_top_superpair_opportunities(self, count: int = 10) -> List[Dict[str, Any]]:
        """
        Get top trading opportunities from superpairs
        """
        if not self.superpairs_cache:
            await self.scan_superpairs(quick_mode=False)
        
        # Get fresh ticker data for cached superpairs
        opportunities = []
        
        for symbol, cached_data in list(self.superpairs_cache.items())[:count * 2]:
            try:
                ticker = await self.exchange.fetch_ticker(symbol)
                
                opportunity = {
                    'symbol': symbol,
                    'score': cached_data.get('score', 0),
                    'last_price': ticker['last'],
                    'volume_24h': ticker['quoteVolume'],
                    'change_24h': ticker['percentage'],
                    'volatility': (ticker['high'] - ticker['low']) / ticker['low'] if ticker['low'] > 0 else 0,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Boost score based on current conditions
                if -5 < ticker['percentage'] < -2:
                    opportunity['score'] += 10  # Oversold bounce potential
                elif 0.02 < opportunity['volatility'] < 0.10:
                    opportunity['score'] += 5   # Good volatility
                
                opportunities.append(opportunity)
                
            except Exception as e:
                logger.warning(f"Failed to get opportunity data for {symbol}: {e}")
        
        # Sort by score and return top N
        opportunities.sort(key=lambda x: x['score'], reverse=True)
        return opportunities[:count]
    
    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()


async def main():
    """Test the superpair scanner"""
    scanner = SuperpairScanner()
    
    try:
        # Initialize
        if await scanner.initialize():
            print("✅ Scanner initialized")
            
            # Quick scan
            print("\n🔍 Running quick superpair scan...")
            quick_results = await scanner.scan_superpairs(quick_mode=True)
            print(f"✅ Quick scan found {len(quick_results)} superpairs")
            
            if quick_results:
                print("\nSample superpairs (first 10):")
                for result in quick_results[:10]:
                    print(f"  - {result['symbol']}")
            
            # Full scan (limited for testing)
            print("\n🔍 Running full validation on top symbols...")
            full_results = await scanner.scan_superpairs(quick_mode=False)
            print(f"✅ Full scan confirmed {len(full_results)} superpairs")
            
            if full_results:
                print("\nTop 5 Confirmed Superpairs:")
                for i, result in enumerate(full_results[:5], 1):
                    print(f"\n{i}. {result['symbol']}:")
                    print(f"   Score: {result.get('score', 0)}/100")
                    print(f"   Volume: ${result.get('volume_24h', 0):,.0f}")
                    print(f"   Spread: {result.get('spread', 0):.4%}")
            
            # Get opportunities
            print("\n💰 Getting top superpair opportunities...")
            opportunities = await scanner.get_top_superpair_opportunities(count=5)
            
            if opportunities:
                print("\nTop Trading Opportunities:")
                for i, opp in enumerate(opportunities, 1):
                    print(f"\n{i}. {opp['symbol']}:")
                    print(f"   Score: {opp['score']:.0f}")
                    print(f"   Price: ${opp['last_price']:.4f}")
                    print(f"   24h Change: {opp['change_24h']:.2f}%")
                    print(f"   Volatility: {opp['volatility']:.2%}")
            
            # Save results
            results_data = {
                'timestamp': datetime.now().isoformat(),
                'quick_scan_count': len(quick_results),
                'confirmed_count': len(full_results),
                'top_superpairs': full_results[:10],
                'opportunities': opportunities
            }
            
            with open('/app/superpair_scan_results.json', 'w') as f:
                json.dump(results_data, f, indent=2)
            print("\n✅ Results saved to superpair_scan_results.json")
            
    finally:
        await scanner.close()
        print("\n✅ Scanner closed")


if __name__ == "__main__":
    asyncio.run(main())