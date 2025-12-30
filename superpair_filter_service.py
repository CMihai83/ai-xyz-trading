"""
Superpair Filter Service for Bitget
Filters market data to identify and work with superpair coins
Superpairs have enhanced liquidity and trading features on Bitget
"""

import asyncio
import ccxt.async_support as ccxt
from typing import List, Dict, Any, Optional
import structlog
from datetime import datetime
import os
from dotenv import load_dotenv
import aiohttp
import json

load_dotenv()
logger = structlog.get_logger(__name__)

class SuperpairFilterService:
    """
    Service to filter and identify Bitget superpair coins.
    Superpairs are special trading pairs with:
    - Enhanced liquidity
    - Lower trading fees
    - Better market depth
    - Priority matching
    """
    
    def __init__(self, exchange=None):
        """Initialize the superpair filter service"""
        if exchange:
            self.exchange = exchange
        else:
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
        
        # Cache for superpair data
        self.superpairs_cache = {}
        self.cache_timestamp = None
        self.cache_duration = 3600  # 1 hour cache
        
    async def initialize(self):
        """Initialize the service and exchange connection"""
        try:
            await self.exchange.load_markets()
            logger.info("Superpair filter service initialized")
            # Load initial superpair data
            await self.refresh_superpairs()
            return True
        except Exception as e:
            logger.error(f"Failed to initialize superpair filter: {e}")
            return False
    
    async def get_market_info(self) -> Dict[str, Any]:
        """Get detailed market information from Bitget"""
        try:
            markets = self.exchange.markets
            market_info = {}
            
            for symbol, market in markets.items():
                if market['active'] and market['type'] == 'swap':
                    market_info[symbol] = {
                        'symbol': symbol,
                        'base': market['base'],
                        'quote': market['quote'],
                        'active': market['active'],
                        'type': market['type'],
                        'linear': market.get('linear', True),
                        'inverse': market.get('inverse', False),
                        'contractSize': market.get('contractSize', 1),
                        'info': market.get('info', {})
                    }
            
            return market_info
        except Exception as e:
            logger.error(f"Error getting market info: {e}")
            return {}
    
    async def identify_superpairs(self) -> List[str]:
        """
        Identify superpair symbols from Bitget markets.
        Bitget superpairs are identified by their premium trading characteristics:
        - High maximum leverage (>= 100x)
        - Low maker fees (<= 0.02%)
        - High position limits (>= 150)
        - High daily volume
        """
        try:
            superpairs = []
            markets = self.exchange.markets
            
            for symbol, market in markets.items():
                if not (market['active'] and market['type'] == 'swap' and market['quote'] == 'USDT'):
                    continue
                
                # Get market info from Bitget
                market_info = market.get('info', {})
                
                # Bitget identifies superpairs by these premium characteristics:
                # 1. High maximum leverage (>= 100x)
                max_leverage = float(market_info.get('maxLever', 0))
                
                # 2. Low maker fees (<= 0.02%)
                maker_fee = float(market_info.get('makerFeeRate', 1))
                
                # 3. High position limits (>= 150)
                max_positions = int(market_info.get('maxPositionNum', 0))
                
                # Check if this meets superpair criteria
                is_superpair = (
                    max_leverage >= 100 and
                    maker_fee <= 0.0002 and
                    max_positions >= 150
                )
                
                if is_superpair:
                    superpairs.append(symbol)
                    logger.info(f"Identified superpair: {symbol} (Leverage: {max_leverage}x, Fee: {maker_fee*100:.3f}%, Positions: {max_positions})")
            
            # Additionally, verify with volume for final confirmation
            verified_superpairs = []
            for symbol in superpairs:
                try:
                    ticker = await self.exchange.fetch_ticker(symbol)
                    volume_24h = ticker.get('quoteVolume', 0)
                    
                    # Superpairs should also have significant volume
                    if volume_24h > 5_000_000:  # $5M minimum
                        verified_superpairs.append(symbol)
                        logger.info(f"Verified superpair {symbol}: Volume=${volume_24h:,.0f}")
                except Exception as e:
                    logger.warning(f"Could not verify {symbol}: {e}")
                    # Keep it anyway if it meets the criteria
                    verified_superpairs.append(symbol)
            
            logger.info(f"Identified {len(verified_superpairs)} verified superpair symbols")
            return verified_superpairs
            
        except Exception as e:
            logger.error(f"Error identifying superpairs: {e}")
            return []
    
    async def get_superpair_tickers(self) -> Dict[str, Any]:
        """Get ticker data for all identified superpairs"""
        try:
            superpairs = await self.get_cached_superpairs()
            tickers = {}
            
            # Fetch tickers in batches to avoid rate limits
            batch_size = 10
            for i in range(0, len(superpairs), batch_size):
                batch = superpairs[i:i + batch_size]
                
                for symbol in batch:
                    try:
                        ticker = await self.exchange.fetch_ticker(symbol)
                        tickers[symbol] = {
                            'symbol': symbol,
                            'last': ticker['last'],
                            'bid': ticker['bid'],
                            'ask': ticker['ask'],
                            'volume_24h': ticker['quoteVolume'],
                            'change_24h': ticker['percentage'],
                            'high_24h': ticker['high'],
                            'low_24h': ticker['low'],
                            'timestamp': ticker['timestamp']
                        }
                    except Exception as e:
                        logger.warning(f"Failed to fetch ticker for {symbol}: {e}")
                
                # Small delay between batches
                await asyncio.sleep(0.1)
            
            return tickers
            
        except Exception as e:
            logger.error(f"Error getting superpair tickers: {e}")
            return {}
    
    async def get_cached_superpairs(self) -> List[str]:
        """Get cached superpair list, refreshing if needed"""
        current_time = datetime.now().timestamp()
        
        # Check if cache needs refresh
        if (not self.superpairs_cache or 
            not self.cache_timestamp or 
            current_time - self.cache_timestamp > self.cache_duration):
            await self.refresh_superpairs()
        
        return list(self.superpairs_cache.keys())
    
    async def refresh_superpairs(self):
        """Refresh the superpairs cache"""
        try:
            logger.info("Refreshing superpairs cache...")
            superpairs = await self.identify_superpairs()
            
            self.superpairs_cache = {symbol: True for symbol in superpairs}
            self.cache_timestamp = datetime.now().timestamp()
            
            logger.info(f"Superpairs cache refreshed with {len(superpairs)} symbols")
            
        except Exception as e:
            logger.error(f"Error refreshing superpairs: {e}")
    
    async def is_superpair(self, symbol: str) -> bool:
        """Check if a specific symbol is a superpair"""
        superpairs = await self.get_cached_superpairs()
        return symbol in superpairs
    
    async def get_superpair_opportunities(self, min_volume: float = 1_000_000) -> List[Dict[str, Any]]:
        """
        Get trading opportunities from superpair coins.
        Filters based on volume and technical indicators.
        """
        try:
            opportunities = []
            tickers = await self.get_superpair_tickers()
            
            for symbol, ticker in tickers.items():
                if ticker['volume_24h'] < min_volume:
                    continue
                
                # Calculate simple opportunity score
                opportunity = {
                    'symbol': symbol,
                    'last_price': ticker['last'],
                    'volume_24h': ticker['volume_24h'],
                    'change_24h': ticker['change_24h'],
                    'spread': (ticker['ask'] - ticker['bid']) / ticker['bid'] if ticker['bid'] > 0 else 0,
                    'volatility': (ticker['high_24h'] - ticker['low_24h']) / ticker['low_24h'] if ticker['low_24h'] > 0 else 0,
                    'timestamp': datetime.now().isoformat()
                }
                
                # Calculate opportunity score (0-100)
                score = 0
                
                # Volume score (higher is better)
                if ticker['volume_24h'] > 10_000_000:
                    score += 30
                elif ticker['volume_24h'] > 5_000_000:
                    score += 20
                else:
                    score += 10
                
                # Volatility score (moderate is best)
                if 0.02 < opportunity['volatility'] < 0.10:
                    score += 30
                elif 0.01 < opportunity['volatility'] < 0.15:
                    score += 20
                else:
                    score += 10
                
                # Spread score (tighter is better)
                if opportunity['spread'] < 0.0005:
                    score += 20
                elif opportunity['spread'] < 0.001:
                    score += 10
                
                # Momentum score
                if -5 < ticker['change_24h'] < -2:
                    score += 20  # Potential bounce
                elif 2 < ticker['change_24h'] < 5:
                    score += 15  # Positive momentum
                
                opportunity['score'] = score
                opportunities.append(opportunity)
            
            # Sort by score
            opportunities.sort(key=lambda x: x['score'], reverse=True)
            
            return opportunities
            
        except Exception as e:
            logger.error(f"Error getting superpair opportunities: {e}")
            return []
    
    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()


async def main():
    """Test the superpair filter service"""
    service = SuperpairFilterService()
    
    try:
        # Initialize service
        if await service.initialize():
            logger.info("Service initialized successfully")
            
            # Get superpairs
            superpairs = await service.get_cached_superpairs()
            logger.info(f"Found {len(superpairs)} superpairs:")
            for symbol in superpairs[:10]:  # Show first 10
                logger.info(f"  - {symbol}")
            
            # Get trading opportunities
            opportunities = await service.get_superpair_opportunities()
            logger.info(f"\nTop superpair opportunities:")
            for opp in opportunities[:5]:
                logger.info(f"  {opp['symbol']}: Score={opp['score']}, Volume=${opp['volume_24h']:,.0f}, Change={opp['change_24h']:.2f}%")
        
    finally:
        await service.close()


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())