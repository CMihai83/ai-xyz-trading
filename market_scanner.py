#!/usr/bin/env python3
"""
Market Scanner - Finds new trading opportunities
Scans all USDT perpetual futures for signals
"""

import asyncio
import ccxt.async_support as ccxt
from typing import List, Dict, Any
import structlog
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()
logger = structlog.get_logger(__name__)

class MarketScanner:
    """Scans market for trading opportunities using technical indicators"""
    
    def __init__(self, exchange=None):
        if exchange:
            self.exchange = exchange
        else:
            self.exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_API_SECRET'),
                'password': os.getenv('BITGET_API_PASSPHRASE'),  # CCXT uses 'password' not 'passphrase'
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'defaultMarginMode': 'isolated'
                }
            })
        self.min_volume_24h = 100000  # Lowered to $100K for more opportunities
        self.rsi_oversold = 35  # Less strict
        self.rsi_overbought = 65  # Less strict
        
    async def initialize(self):
        """Initialize exchange connection"""
        try:
            await self.exchange.load_markets()
            logger.info("Market scanner initialized")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize scanner: {e}")
            return False
            
    async def get_active_symbols(self) -> List[str]:
        """Get list of active USDT perpetual symbols with good volume"""
        try:
            markets = self.exchange.markets
            active_symbols = []
            
            for symbol, market in markets.items():
                if (market['active'] and 
                    market['quote'] == 'USDT' and 
                    market['type'] == 'swap' and
                    ':' in symbol):  # Perpetual format
                    
                    # Check 24h volume
                    ticker = await self.exchange.fetch_ticker(symbol)
                    volume_usd = ticker.get('quoteVolume', 0)
                    
                    if volume_usd >= self.min_volume_24h:
                        active_symbols.append(symbol)
                        
            logger.info(f"Found {len(active_symbols)} active symbols with good volume")
            return active_symbols[:50]  # Limit to top 50 for performance
            
        except Exception as e:
            logger.error(f"Error getting active symbols: {e}")
            return []
            
    async def calculate_rsi(self, symbol: str, period: int = 14) -> float:
        """Calculate RSI for a symbol"""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, '1h', limit=period + 1)
            if len(ohlcv) < period + 1:
                return 50  # Neutral if not enough data
                
            closes = [candle[4] for candle in ohlcv]
            
            # Calculate RSI
            gains = []
            losses = []
            
            for i in range(1, len(closes)):
                diff = closes[i] - closes[i-1]
                if diff > 0:
                    gains.append(diff)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(diff))
                    
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            
            if avg_loss == 0:
                return 100
                
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
            
        except Exception as e:
            logger.error(f"Error calculating RSI for {symbol}: {e}")
            return 50
            
    async def check_fibonacci_retracement(self, symbol: str) -> Dict[str, Any]:
        """Check if price is at Fibonacci retracement level"""
        try:
            # Get daily candles for trend
            daily = await self.exchange.fetch_ohlcv(symbol, '1d', limit=30)
            if len(daily) < 10:
                return {'signal': None}
                
            # Find recent high and low
            highs = [c[2] for c in daily]
            lows = [c[3] for c in daily]
            
            recent_high = max(highs[-20:])
            recent_low = min(lows[-20:])
            current_price = daily[-1][4]
            
            # Calculate Fibonacci levels
            diff = recent_high - recent_low
            fib_levels = {
                '0.236': recent_high - (diff * 0.236),
                '0.382': recent_high - (diff * 0.382),
                '0.500': recent_high - (diff * 0.500),
                '0.618': recent_high - (diff * 0.618),
                '0.786': recent_high - (diff * 0.786)
            }
            
            # Check if price is near a Fibonacci level (within 0.5%)
            for level_name, level_price in fib_levels.items():
                if abs(current_price - level_price) / level_price < 0.005:
                    # Determine direction based on trend
                    trend = 'up' if current_price > (recent_high + recent_low) / 2 else 'down'
                    
                    return {
                        'signal': 'long' if trend == 'up' else 'short',
                        'fibonacci_level': level_name,
                        'level_price': level_price,
                        'current_price': current_price,
                        'confidence': float(level_name)  # Higher fib levels = higher confidence
                    }
                    
            return {'signal': None}
            
        except Exception as e:
            logger.error(f"Error checking Fibonacci for {symbol}: {e}")
            return {'signal': None}
            
    async def scan_symbol(self, symbol: str) -> Dict[str, Any]:
        """Scan a single symbol for trading signals"""
        try:
            # Get RSI
            rsi = await self.calculate_rsi(symbol)
            
            # Check Fibonacci levels
            fib_signal = await self.check_fibonacci_retracement(symbol)
            
            # Get current price
            ticker = await self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            
            signal = None
            confidence = 0
            reason = []
            
            # RSI signals
            if rsi < self.rsi_oversold:
                signal = 'long'
                confidence += 0.3
                reason.append(f"RSI oversold ({rsi:.1f})")
            elif rsi > self.rsi_overbought:
                signal = 'short'
                confidence += 0.3
                reason.append(f"RSI overbought ({rsi:.1f})")
                
            # Fibonacci signals
            if fib_signal['signal']:
                if signal == fib_signal['signal']:
                    confidence += fib_signal['confidence']
                    reason.append(f"Fibonacci {fib_signal['fibonacci_level']} retracement")
                elif signal is None:
                    signal = fib_signal['signal']
                    confidence = fib_signal['confidence'] * 0.7
                    reason.append(f"Fibonacci {fib_signal['fibonacci_level']} bounce")
                    
            if signal and confidence >= 0.5:
                return {
                    'symbol': symbol,
                    'signal': signal,
                    'confidence': confidence,
                    'price': current_price,
                    'rsi': rsi,
                    'reasons': reason,
                    'timestamp': datetime.now()
                }
                
            return None
            
        except Exception as e:
            logger.error(f"Error scanning {symbol}: {e}")
            return None
            
    async def scan_market(self) -> List[Dict[str, Any]]:
        """Scan entire market for opportunities"""
        logger.info("Starting market scan...")
        
        # Get active symbols
        symbols = await self.get_active_symbols()
        
        # Scan each symbol
        signals = []
        for symbol in symbols:
            signal = await self.scan_symbol(symbol)
            if signal:
                signals.append(signal)
                logger.info(f"Signal found: {signal['symbol']} {signal['signal']} "
                          f"(confidence: {signal['confidence']:.2f})")
            
            # Rate limiting
            await asyncio.sleep(0.1)
            
        # Sort by confidence
        signals.sort(key=lambda x: x['confidence'], reverse=True)
        
        logger.info(f"Market scan complete. Found {len(signals)} signals")
        return signals
        
    async def close(self):
        """Close exchange connection"""
        await self.exchange.close()

async def main():
    """Test market scanner"""
    scanner = MarketScanner()
    
    if await scanner.initialize():
        signals = await scanner.scan_market()
        
        print("\n" + "="*60)
        print("TOP TRADING SIGNALS")
        print("="*60)
        
        for signal in signals[:5]:  # Top 5 signals
            print(f"\n{signal['symbol']}:")
            print(f"  Direction: {signal['signal'].upper()}")
            print(f"  Confidence: {signal['confidence']:.2f}")
            print(f"  Price: ${signal['price']:.4f}")
            print(f"  RSI: {signal['rsi']:.1f}")
            print(f"  Reasons: {', '.join(signal['reasons'])}")
            
        await scanner.close()

if __name__ == "__main__":
    asyncio.run(main())