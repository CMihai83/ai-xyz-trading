#!/usr/bin/env python3
"""
Enhanced Market Scanner - OPTIMIZED VERSION
Fixes hanging issues with async execution, timeout handling, and concurrent API calls
"""

import ccxt.async_support as ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
from typing import Dict, List, Tuple, Optional
import asyncio
import sys
import os

class EnhancedMarketScannerOptimized:
    def __init__(self, max_symbols=15, max_concurrent=5, timeout_per_symbol=10):
        """
        Initialize optimized scanner with concurrency controls

        Args:
            max_symbols: Maximum symbols to scan (default: 15, reduced from 30)
            max_concurrent: Max concurrent API requests (default: 5)
            timeout_per_symbol: Timeout in seconds per symbol (default: 10)
        """
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY', 'bg_f483546274ffb2bfa567328e98dba6c0'),
            'secret': os.getenv('BITGET_API_SECRET', '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0'),
            'password': os.getenv('BITGET_API_PASSPHRASE', '2609Luiza'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'defaultMarginMode': 'isolated'
            }
        })

        # Performance settings
        self.max_symbols = max_symbols
        self.max_concurrent = max_concurrent
        self.timeout_per_symbol = timeout_per_symbol
        self.semaphore = asyncio.Semaphore(max_concurrent)

        # Timeframes for analysis (4H is mandatory)
        self.timeframes = ['15m', '1h', '4h']  # Reduced from 4 to 3 timeframes
        self.primary_timeframe = '15m'
        self.mandatory_timeframe = '4h'

        # Top tier super pairs only (reduced to 15 for performance)
        self.super_pairs = [
            # Tier 1 - Always liquid
            'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
            # Tier 2 - High volume memes
            'DOGE/USDT:USDT', 'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'SHIB/USDT:USDT',
            # Tier 3 - Popular L1/L2
            'ARB/USDT:USDT', 'OP/USDT:USDT', 'INJ/USDT:USDT', 'SUI/USDT:USDT',
            # Tier 4 - DeFi/Infrastructure
            'AVAX/USDT:USDT', 'LINK/USDT:USDT', 'UNI/USDT:USDT'
        ]

        self.symbols = self.super_pairs[:max_symbols]

        # Cache for OHLCV data
        self.ohlcv_cache = {}
        self.cache_ttl = 60  # Cache for 60 seconds

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close exchange"""
        await self.exchange.close()

    def calculate_volatility(self, ohlcv: List) -> float:
        """Calculate price volatility using ATR"""
        if len(ohlcv) < 14:
            return 0

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['hl'] = df['high'] - df['low']
        df['hc'] = abs(df['high'] - df['close'].shift(1))
        df['lc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['hl', 'hc', 'lc']].max(axis=1)
        atr = df['tr'].rolling(14).mean().iloc[-1]
        price = df['close'].iloc[-1]
        return (atr / price) * 100 if price > 0 else 0

    def analyze_vsa(self, ohlcv: List) -> Dict:
        """Volume Spread Analysis"""
        if len(ohlcv) < 20:
            return {'signal': 'neutral', 'strength': 0}

        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['spread'] = df['high'] - df['low']
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 0.0001)
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['spread_ma'] = df['spread'].rolling(20).mean()

        latest = df.iloc[-1]
        signal = 'neutral'
        strength = 0

        # VSA Patterns
        if (latest['volume'] > latest['volume_ma'] * 1.5 and
            latest['spread'] < latest['spread_ma'] * 0.7 and
            latest['close_position'] > 0.7):
            signal = 'bullish'
            strength = 0.8
        elif (latest['volume'] > latest['volume_ma'] * 1.5 and
              latest['spread'] > latest['spread_ma'] * 1.3 and
              latest['close_position'] < 0.3):
            signal = 'bearish'
            strength = 0.8
        elif latest['volume'] < latest['volume_ma'] * 0.5:
            if latest['close_position'] > 0.7:
                signal = 'bullish'
                strength = 0.6
            elif latest['close_position'] < 0.3:
                signal = 'bearish'
                strength = 0.6

        return {
            'signal': signal,
            'strength': strength,
            'volume_ratio': latest['volume'] / latest['volume_ma'] if latest['volume_ma'] > 0 else 1,
            'spread_ratio': latest['spread'] / latest['spread_ma'] if latest['spread_ma'] > 0 else 1,
            'close_position': latest['close_position']
        }

    def calculate_rsi(self, prices: List[float], period: int = 14) -> float:
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50

        df = pd.DataFrame({'close': prices})
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / (loss + 0.0001)
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]

    def calculate_macd(self, prices: List[float]) -> Dict:
        """Calculate MACD"""
        if len(prices) < 26:
            return {'macd': 0, 'signal': 0, 'histogram': 0}

        df = pd.DataFrame({'close': prices})
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        histogram = macd - signal

        return {
            'macd': macd.iloc[-1],
            'signal': signal.iloc[-1],
            'histogram': histogram.iloc[-1]
        }

    async def fetch_ohlcv_cached(self, symbol: str, timeframe: str, limit: int = 100) -> Optional[List]:
        """Fetch OHLCV with caching"""
        cache_key = f"{symbol}_{timeframe}"
        now = time.time()

        # Check cache
        if cache_key in self.ohlcv_cache:
            cached_data, cached_time = self.ohlcv_cache[cache_key]
            if now - cached_time < self.cache_ttl:
                return cached_data

        # Fetch with semaphore to limit concurrency
        async with self.semaphore:
            try:
                ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                self.ohlcv_cache[cache_key] = (ohlcv, now)
                return ohlcv
            except Exception as e:
                print(f"    ⚠️ Error fetching {symbol} {timeframe}: {e}")
                return None

    async def analyze_symbol_timeframe(self, symbol: str, timeframe: str) -> Optional[Dict]:
        """Analyze a single symbol on a single timeframe with timeout"""
        try:
            ohlcv = await asyncio.wait_for(
                self.fetch_ohlcv_cached(symbol, timeframe, limit=100),
                timeout=5.0  # 5 second timeout per timeframe
            )

            if not ohlcv or len(ohlcv) < 50:
                return None

            closes = [c[4] for c in ohlcv]
            rsi = self.calculate_rsi(closes)
            macd = self.calculate_macd(closes)
            vsa = self.analyze_vsa(ohlcv)
            volatility = self.calculate_volatility(ohlcv)

            # Determine signal
            signal_strength = 0
            signal_direction = 'neutral'

            # RSI signals
            if rsi < 30:
                signal_strength += 0.3
                signal_direction = 'bullish'
            elif rsi > 70:
                signal_strength += 0.3
                signal_direction = 'bearish'

            # MACD signals
            if macd['histogram'] > 0:
                signal_strength += 0.2
                if signal_direction == 'neutral':
                    signal_direction = 'bullish'
            elif macd['histogram'] < 0:
                signal_strength += 0.2
                if signal_direction == 'neutral':
                    signal_direction = 'bearish'

            # VSA signals (highest weight)
            if vsa['signal'] != 'neutral':
                signal_strength += vsa['strength'] * 0.5
                if signal_direction == 'neutral':
                    signal_direction = vsa['signal']

            return {
                'direction': signal_direction,
                'strength': min(signal_strength, 1.0),
                'rsi': rsi,
                'macd_histogram': macd['histogram'],
                'vsa_signal': vsa['signal'],
                'vsa_strength': vsa['strength'],
                'volatility': volatility
            }

        except asyncio.TimeoutError:
            print(f"    ⏱️ Timeout analyzing {symbol} on {timeframe}")
            return None
        except Exception as e:
            print(f"    ❌ Error analyzing {symbol} on {timeframe}: {e}")
            return None

    async def analyze_symbol(self, symbol: str) -> Optional[Dict]:
        """Analyze a symbol across all timeframes with timeout"""
        try:
            # Analyze all timeframes concurrently
            tasks = [
                self.analyze_symbol_timeframe(symbol, tf)
                for tf in self.timeframes
            ]

            # Wait for all with timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.timeout_per_symbol
            )

            # Build mtf_signals dict
            mtf_signals = {}
            for tf, result in zip(self.timeframes, results):
                if result and not isinstance(result, Exception):
                    mtf_signals[tf] = result

            if not mtf_signals or '4h' not in mtf_signals:
                return None

            return mtf_signals

        except asyncio.TimeoutError:
            print(f"  ⏱️ Timeout analyzing {symbol}")
            return None
        except Exception as e:
            print(f"  ❌ Error analyzing {symbol}: {e}")
            return None

    def calculate_signal_score(self, mtf_signals: Dict) -> Tuple[str, float, Dict]:
        """Calculate final signal score"""
        if '4h' not in mtf_signals:
            return 'neutral', 0, {'reason': 'Missing 4H timeframe'}

        four_hour_signal = mtf_signals['4h']

        if four_hour_signal['direction'] == 'neutral':
            return 'neutral', 0, {'reason': '4H neutral'}

        final_direction = four_hour_signal['direction']

        # Calculate components
        technical_scores = [s['strength'] for s in mtf_signals.values() if s['direction'] == final_direction]
        technical_score = np.mean(technical_scores) if technical_scores else 0

        alignment_score = sum(1 for s in mtf_signals.values() if s['direction'] == final_direction) / len(mtf_signals)
        vsa_score = sum(1 for s in mtf_signals.values() if s['vsa_signal'] == final_direction) / len(mtf_signals)
        avg_volatility = np.mean([s['volatility'] for s in mtf_signals.values()])
        volatility_score = min(avg_volatility / 5.0, 1.0)

        # Composite score (VSA-weighted)
        composite_score = (
            technical_score * 0.30 +
            alignment_score * 0.25 +
            vsa_score * 0.43 +
            volatility_score * 0.02
        )

        if composite_score < 0.15:
            return 'neutral', 0, {'reason': 'Low quality'}

        quality_metrics = {
            'volatility_avg': avg_volatility,
            'vsa_confirmation': sum(1 for s in mtf_signals.values() if s['vsa_signal'] == final_direction),
            'timeframe_alignment': sum(1 for s in mtf_signals.values() if s['direction'] == final_direction),
            '4h_strength': four_hour_signal['strength'],
            'total_strength': composite_score
        }

        return final_direction, composite_score, quality_metrics

    async def scan_market(self) -> List[Dict]:
        """Scan market asynchronously with progress tracking"""
        opportunities = []

        print("="*70)
        print("ENHANCED MARKET SCANNER - OPTIMIZED ASYNC VERSION")
        print("="*70)
        print(f"Scanning {len(self.symbols)} symbols with {self.max_concurrent} concurrent requests")
        print(f"Timeout: {self.timeout_per_symbol}s per symbol")
        print(f"Timeframes: {', '.join(self.timeframes)} (4H mandatory)")
        print("-"*70)

        start_time = time.time()

        # Analyze all symbols concurrently
        tasks = []
        for symbol in self.symbols:
            tasks.append(self.analyze_symbol(symbol))

        # Process with progress tracking
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            symbol = self.symbols[i-1]
            print(f"\n[{i}/{len(self.symbols)}] 📊 Analyzing {symbol}...")

            mtf_signals = await coro

            if not mtf_signals:
                print(f"  ❌ Insufficient data")
                continue

            direction, score, metrics = self.calculate_signal_score(mtf_signals)

            if direction == 'neutral' or score < 0.5:
                print(f"  ❌ No signal: {metrics.get('reason', 'Score too low')}")
                continue

            opportunity = {
                'symbol': symbol,
                'direction': direction,
                'score': score,
                'volatility': metrics['volatility_avg'],
                'vsa_confirmation': metrics['vsa_confirmation'],
                'timeframe_alignment': metrics['timeframe_alignment'],
                '4h_strength': metrics['4h_strength'],
                'timestamp': datetime.now().isoformat()
            }

            opportunities.append(opportunity)

            print(f"  ✅ SIGNAL: {direction.upper()} | Score: {score:.2f} | VSA: {metrics['vsa_confirmation']}/3")

        elapsed = time.time() - start_time
        print(f"\n⏱️ Scan completed in {elapsed:.1f}s")
        print(f"📊 Found {len(opportunities)} opportunities")

        opportunities.sort(key=lambda x: x['score'], reverse=True)
        return opportunities

    async def generate_trading_signals(self, max_signals: int = 5) -> List[Dict]:
        """Generate trading signals asynchronously"""
        opportunities = await self.scan_market()

        if not opportunities:
            print("❌ No valid opportunities found")
            return []

        top_opportunities = opportunities[:max_signals]
        trading_signals = []

        print("\n" + "="*70)
        print("TRADING SIGNAL GENERATION")
        print("="*70)

        for opp in top_opportunities:
            try:
                ticker = await self.exchange.fetch_ticker(opp['symbol'])
                current_price = ticker['last']

                base_leverage = 5
                score_bonus = opp['score'] * 4
                volatility_adjustment = 0
                if opp['volatility'] < 1.0:
                    volatility_adjustment = 0.5
                elif opp['volatility'] > 2.0:
                    volatility_adjustment = -0.5

                leverage = min(10, max(3, int(base_leverage + score_bonus + volatility_adjustment)))

                signal = {
                    'symbol': opp['symbol'],
                    'action': 'BUY' if opp['direction'] == 'bullish' else 'SELL',
                    'price': current_price,
                    'leverage': leverage,
                    'score': opp['score'],
                    'volatility': opp['volatility'],
                    'confidence': opp['4h_strength'],
                    'timestamp': datetime.now().isoformat(),
                    'reasoning': {
                        'vsa_confirmations': opp['vsa_confirmation'],
                        'timeframe_alignment': opp['timeframe_alignment'],
                        '4h_validation': 'CONFIRMED'
                    }
                }

                trading_signals.append(signal)
                print(f"\n🎯 {signal['symbol']}: {signal['action']} @ {signal['leverage']}x (Score: {signal['score']:.2f})")

            except Exception as e:
                print(f"Error generating signal for {opp['symbol']}: {e}")
                continue

        # Save signals
        with open('/root/ai_xyz/trading_signals.json', 'w') as f:
            json.dump(trading_signals, f, indent=2)

        print(f"\n✅ Generated {len(trading_signals)} signals")
        print("📄 Saved to: /root/ai_xyz/trading_signals.json")

        return trading_signals

async def main():
    """Main async function"""
    async with EnhancedMarketScannerOptimized(
        max_symbols=15,
        max_concurrent=5,
        timeout_per_symbol=10
    ) as scanner:
        print(f"⏰ Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        signals = await scanner.generate_trading_signals(max_signals=5)

        if signals:
            print("\n" + "="*70)
            print("SIGNAL SUMMARY")
            print("="*70)
            for i, signal in enumerate(signals, 1):
                print(f"{i}. {signal['symbol']}: {signal['action']} @ {signal['leverage']}x (Score: {signal['score']:.2f})")

        print("\n✅ Scan complete!")

if __name__ == "__main__":
    asyncio.run(main())
