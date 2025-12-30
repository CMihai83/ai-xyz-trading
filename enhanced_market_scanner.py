#!/usr/bin/env python3
"""
Enhanced Market Scanner with Multi-Criteria Opportunity Detection
Priority: Volatility + VSA (Volume Spread Analysis) + Multi-Timeframe Validation
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import json
from typing import Dict, List, Tuple, Optional
import asyncio
import sys
import os
sys.path.append('/root/ai_xyz/services/api-gateway/src')
from superpair_filter_service import SuperpairFilterService

class EnhancedMarketScanner:
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
        
        # Initialize superpair filter service
        self.superpair_filter = None
        self.use_superpairs_only = False  # Flag to enable superpair-only scanning
        
        # Timeframes for analysis (4H is mandatory)
        self.timeframes = ['5m', '15m', '1h', '4h']  # 4H is mandatory
        self.primary_timeframe = '15m'
        self.mandatory_timeframe = '4h'
        
        # Super Pairs - frequently featured in Bitget competitions
        self.super_pairs = [
            # Major (always featured)
            'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
            # Popular memes
            'DOGE/USDT:USDT', 'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'SHIB/USDT:USDT',
            # Layer 1/2
            'ARB/USDT:USDT', 'OP/USDT:USDT', 'INJ/USDT:USDT', 'SUI/USDT:USDT',
            # DeFi & Infrastructure
            'AVAX/USDT:USDT', 'MATIC/USDT:USDT', 'LINK/USDT:USDT', 'UNI/USDT:USDT',
            # Others
            'ADA/USDT:USDT', 'DOT/USDT:USDT', 'ATOM/USDT:USDT', 'FIL/USDT:USDT',
            'LTC/USDT:USDT', 'APT/USDT:USDT', 'CRV/USDT:USDT', 'MANA/USDT:USDT',
            # AI tokens
            'FET/USDT:USDT', 'WLD/USDT:USDT', 'TAO/USDT:USDT',
            # Hot new tokens
            'TIA/USDT:USDT', 'SEI/USDT:USDT', 'JUP/USDT:USDT'
        ]
        
        # Use super pairs by default
        self.symbols = self.super_pairs.copy()
        self.use_super_pairs_only = True
    
    async def initialize_superpair_filter(self):
        """Initialize the superpair filter service"""
        try:
            self.superpair_filter = SuperpairFilterService(self.exchange)
            await self.superpair_filter.initialize()
            print(f"Superpair filter initialized successfully")
            return True
        except Exception as e:
            print(f"Failed to initialize superpair filter: {e}")
            return False
    
    async def update_symbols_with_superpairs(self):
        """Update scanning symbols with superpairs"""
        if not self.superpair_filter:
            return
        
        try:
            superpairs = await self.superpair_filter.get_cached_superpairs()
            
            if self.use_superpairs_only:
                # Use only superpairs
                self.symbols = superpairs[:30]  # Limit to top 30 for performance
                print(f"Updated scanner with {len(self.symbols)} superpair symbols")
            else:
                # Merge superpairs with default symbols
                # Prioritize superpairs
                combined = list(set(superpairs[:20] + self.default_symbols))
                self.symbols = combined[:30]  # Keep total under 30
                print(f"Updated scanner with {len(self.symbols)} combined symbols (superpairs + defaults)")
            
            print(f"Active symbols: {', '.join(self.symbols[:10])}...")
            
        except Exception as e:
            print(f"Error updating symbols with superpairs: {e}")
            self.symbols = self.default_symbols
    
    def calculate_volatility(self, ohlcv: List) -> float:
        """Calculate price volatility using ATR (Average True Range)"""
        if len(ohlcv) < 14:
            return 0
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate True Range
        df['hl'] = df['high'] - df['low']
        df['hc'] = abs(df['high'] - df['close'].shift(1))
        df['lc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['hl', 'hc', 'lc']].max(axis=1)
        
        # ATR
        atr = df['tr'].rolling(14).mean().iloc[-1]
        price = df['close'].iloc[-1]
        
        # Volatility as percentage of price
        volatility = (atr / price) * 100 if price > 0 else 0
        return volatility
    
    def analyze_vsa(self, ohlcv: List) -> Dict:
        """
        Volume Spread Analysis (VSA)
        Analyzes relationship between volume, spread, and close position
        """
        if len(ohlcv) < 20:
            return {'signal': 'neutral', 'strength': 0}
        
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Calculate spread and volume metrics
        df['spread'] = df['high'] - df['low']
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'] + 0.0001)
        df['volume_ma'] = df['volume'].rolling(20).mean()
        df['spread_ma'] = df['spread'].rolling(20).mean()
        
        # Get latest values
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        signal = 'neutral'
        strength = 0
        
        # VSA Patterns
        
        # 1. High Volume, Narrow Spread, High Close = Accumulation (Bullish)
        if (latest['volume'] > latest['volume_ma'] * 1.5 and 
            latest['spread'] < latest['spread_ma'] * 0.7 and 
            latest['close_position'] > 0.7):
            signal = 'bullish'
            strength = 0.8
        
        # 2. High Volume, Wide Spread, Low Close = Distribution (Bearish)
        elif (latest['volume'] > latest['volume_ma'] * 1.5 and 
              latest['spread'] > latest['spread_ma'] * 1.3 and 
              latest['close_position'] < 0.3):
            signal = 'bearish'
            strength = 0.8
        
        # 3. Low Volume, Test of support/resistance
        elif latest['volume'] < latest['volume_ma'] * 0.5:
            if latest['close'] > prev['close'] and latest['close_position'] > 0.7:
                signal = 'bullish'
                strength = 0.6
            elif latest['close'] < prev['close'] and latest['close_position'] < 0.3:
                signal = 'bearish'
                strength = 0.6
        
        # 4. Climax Volume
        elif latest['volume'] > latest['volume_ma'] * 2.5:
            if latest['close'] > prev['close']:
                signal = 'bearish'  # Buying climax, potential reversal
                strength = 0.7
            else:
                signal = 'bullish'  # Selling climax, potential reversal
                strength = 0.7
        
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
        
        # Calculate MACD
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
    
    def calculate_bollinger_bands(self, prices: List[float], period: int = 20) -> Dict:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return {'upper': 0, 'middle': 0, 'lower': 0, 'position': 0.5}
        
        df = pd.DataFrame({'close': prices})
        
        middle = df['close'].rolling(period).mean().iloc[-1]
        std = df['close'].rolling(period).std().iloc[-1]
        upper = middle + (2 * std)
        lower = middle - (2 * std)
        
        current_price = prices[-1]
        position = (current_price - lower) / (upper - lower) if upper != lower else 0.5
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'position': position,
            'squeeze': std / middle if middle > 0 else 0
        }
    
    def multi_timeframe_validation(self, symbol: str) -> Dict:
        """
        Validate signals across multiple timeframes
        4H timeframe is MANDATORY for signal confirmation
        """
        mtf_signals = {}
        
        for tf in self.timeframes:
            try:
                ohlcv = self.exchange.fetch_ohlcv(symbol, tf, limit=100)
                
                if len(ohlcv) < 50:
                    continue
                
                # Extract price data
                closes = [c[4] for c in ohlcv]
                
                # Calculate indicators for each timeframe
                rsi = self.calculate_rsi(closes)
                macd = self.calculate_macd(closes)
                bb = self.calculate_bollinger_bands(closes)
                vsa = self.analyze_vsa(ohlcv)
                volatility = self.calculate_volatility(ohlcv)
                
                # Determine signal for this timeframe
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
                if macd['histogram'] > 0 and macd['macd'] > macd['signal']:
                    signal_strength += 0.2
                    if signal_direction == 'neutral':
                        signal_direction = 'bullish'
                elif macd['histogram'] < 0 and macd['macd'] < macd['signal']:
                    signal_strength += 0.2
                    if signal_direction == 'neutral':
                        signal_direction = 'bearish'
                
                # Bollinger Band signals
                if bb['position'] < 0.2:
                    signal_strength += 0.2
                    if signal_direction == 'neutral':
                        signal_direction = 'bullish'
                elif bb['position'] > 0.8:
                    signal_strength += 0.2
                    if signal_direction == 'neutral':
                        signal_direction = 'bearish'
                
                # VSA signals (highest weight)
                if vsa['signal'] != 'neutral':
                    signal_strength += vsa['strength'] * 0.5
                    if signal_direction == 'neutral':
                        signal_direction = vsa['signal']
                
                mtf_signals[tf] = {
                    'direction': signal_direction,
                    'strength': min(signal_strength, 1.0),
                    'rsi': rsi,
                    'macd_histogram': macd['histogram'],
                    'bb_position': bb['position'],
                    'vsa_signal': vsa['signal'],
                    'vsa_strength': vsa['strength'],
                    'volatility': volatility
                }
                
            except Exception as e:
                print(f"Error analyzing {symbol} on {tf}: {e}")
                continue
        
        return mtf_signals
    
    def calculate_signal_score(self, mtf_signals: Dict) -> Tuple[str, float, Dict]:
        """
        Calculate final signal score based on signal quality, not volatility
        UPDATED: Volatility weight reduced to minimum (2% only)
        """
        # Check if 4H timeframe is present and valid
        if '4h' not in mtf_signals:
            return 'neutral', 0, {'reason': 'Missing mandatory 4H timeframe'}
        
        four_hour_signal = mtf_signals['4h']
        
        # 4H must confirm direction
        if four_hour_signal['direction'] == 'neutral':
            return 'neutral', 0, {'reason': '4H timeframe is neutral'}
        
        # Calculate signal quality components (volatility weight MINIMIZED)
        final_direction = four_hour_signal['direction']
        
        # Component 1: Technical indicator strength (30% weight - REDUCED)
        technical_scores = []
        for tf, signal in mtf_signals.items():
            if signal['direction'] == final_direction:
                technical_scores.append(signal['strength'])
        technical_score = np.mean(technical_scores) if technical_scores else 0
        
        # Component 2: Timeframe alignment (25% weight - REDUCED)
        alignment_score = sum(1 for s in mtf_signals.values() if s['direction'] == final_direction) / len(mtf_signals)
        
        # Component 3: VSA confirmation (43% weight - SIGNIFICANTLY INCREASED)
        # VSA (Volume Spread Analysis) is now the PRIMARY factor
        vsa_score = sum(1 for s in mtf_signals.values() if s['vsa_signal'] == final_direction) / len(mtf_signals)
        
        # Component 4: Volatility (2% weight - MINIMIZED from implicit to explicit minimal)
        # Only use as a tiny tiebreaker, not a primary factor
        avg_volatility = np.mean([s['volatility'] for s in mtf_signals.values()])
        # Normalize volatility to 0-1 range (cap at 5% daily volatility as max)
        volatility_score = min(avg_volatility / 5.0, 1.0)
        
        # Calculate final composite score (VSA weight MAXIMIZED to 43%)
        composite_score = (
            technical_score * 0.30 +  # Reduced from 45%
            alignment_score * 0.25 +  # Reduced from 35%
            vsa_score * 0.43 +        # SIGNIFICANTLY INCREASED from 18%
            volatility_score * 0.02    # MINIMIZED to 2% (was implicit before)
        )
        
        # Minimum threshold for quality signals (reduced further for VSA-based signals)
        if composite_score < 0.15:
            return 'neutral', 0, {'reason': 'Insufficient signal quality'}
        
        # Calculate quality metrics for reporting
        quality_metrics = {
            'volatility_avg': np.mean([s['volatility'] for s in mtf_signals.values()]),
            'volatility_weight': 0.02,  # Show the minimal weight used
            'vsa_confirmation': sum(1 for s in mtf_signals.values() if s['vsa_signal'] == final_direction),
            'timeframe_alignment': sum(1 for s in mtf_signals.values() if s['direction'] == final_direction),
            '4h_strength': four_hour_signal['strength'],
            'total_strength': composite_score,
            'technical_score': technical_score,
            'alignment_score': alignment_score,
            'vsa_score': vsa_score,
            'volatility_score': volatility_score,
            'weights': {
                'technical': 0.30,
                'alignment': 0.25,
                'vsa': 0.43,  # VSA is now PRIMARY
                'volatility': 0.02  # MINIMIZED
            }
        }
        
        return final_direction, composite_score, quality_metrics
    
    async def scan_superpairs(self) -> List[Dict]:
        """
        Scan specifically superpair symbols for trading opportunities
        """
        if not self.superpair_filter:
            await self.initialize_superpair_filter()
        
        # Update symbols with superpairs
        self.use_superpairs_only = True
        await self.update_symbols_with_superpairs()
        
        # Get superpair-specific opportunities
        superpair_opportunities = await self.superpair_filter.get_superpair_opportunities()
        
        # Run regular scan on superpair symbols
        regular_opportunities = self.scan_market()
        
        # Merge and enhance opportunities
        enhanced_opportunities = []
        for opp in regular_opportunities:
            # Check if this symbol is in superpair opportunities
            sp_data = next((sp for sp in superpair_opportunities if sp['symbol'] == opp['symbol']), None)
            if sp_data:
                opp['is_superpair'] = True
                opp['superpair_score'] = sp_data['score']
                opp['spread'] = sp_data['spread']
                # Boost composite score for superpairs
                opp['composite_score'] = opp['composite_score'] * 1.2  # 20% boost for superpairs
            enhanced_opportunities.append(opp)
        
        return enhanced_opportunities
    
    def scan_market(self) -> List[Dict]:
        """
        Scan market for opportunities based on multi-criteria analysis
        NOTE: This scanner makes ~120 API calls (30 symbols × 4 timeframes)
        Expected completion time: 60-90 seconds with rate limiting
        """
        opportunities = []

        import time
        start_time = time.time()

        print("="*70)
        print("ENHANCED MARKET SCANNER - SIGNAL QUALITY ANALYSIS")
        print("="*70)
        print(f"Scanning {len(self.symbols)} symbols across {len(self.timeframes)} timeframes")
        print(f"Expected API calls: {len(self.symbols)} × {len(self.timeframes)} = {len(self.symbols) * len(self.timeframes)}")
        print(f"Estimated time: 60-90 seconds (NOT hanging, please wait...)")
        print("Priority: Signal Quality (Technical + VSA + Multi-Timeframe with 4H Mandatory)")
        print("Volatility is considered but not prioritized")
        print("-"*70)

        for idx, symbol in enumerate(self.symbols, 1):
            try:
                print(f"\n[{idx}/{len(self.symbols)}] 📊 Analyzing {symbol}...")
                
                # Get multi-timeframe signals
                mtf_signals = self.multi_timeframe_validation(symbol)
                
                if not mtf_signals:
                    print(f"  ⚠️ Insufficient data for {symbol}")
                    continue
                
                # Calculate final score
                direction, score, metrics = self.calculate_signal_score(mtf_signals)
                
                if direction == 'neutral' or score < 0.5:
                    print(f"  ❌ No signal: {metrics.get('reason', 'Score too low')}")
                    continue
                
                # Create opportunity object
                opportunity = {
                    'symbol': symbol,
                    'direction': direction,
                    'score': score,
                    'volatility': metrics['volatility_avg'],
                    'vsa_confirmation': metrics['vsa_confirmation'],
                    'timeframe_alignment': metrics['timeframe_alignment'],
                    '4h_strength': metrics['4h_strength'],
                    'timestamp': datetime.now().isoformat(),
                    'timeframe_signals': mtf_signals
                }
                
                opportunities.append(opportunity)
                
                print(f"  ✅ OPPORTUNITY FOUND!")
                print(f"     Direction: {direction.upper()}")
                print(f"     Score: {score:.2f}")
                print(f"     Volatility: {metrics['volatility_avg']:.2f}%")
                print(f"     VSA Confirmations: {metrics['vsa_confirmation']}/4")
                print(f"     Timeframe Alignment: {metrics['timeframe_alignment']}/4")
                print(f"     4H Strength: {metrics['4h_strength']:.2f}")
                
            except Exception as e:
                print(f"  ❌ Error scanning {symbol}: {e}")
                continue
        
        # Sort opportunities by signal quality score only (not volatility)
        # Volatility should be a factor in scoring, not sorting
        opportunities.sort(key=lambda x: x['score'], reverse=True)

        elapsed = time.time() - start_time
        print(f"\n⏱️ Scan completed in {elapsed:.1f} seconds")
        print(f"📊 Found {len(opportunities)} opportunities")

        return opportunities
    
    def scan_for_opportunities(self) -> List[Dict]:
        """
        Compatibility method for main trading system
        Returns list of opportunities in the same format as SimpleVSAScanner
        """
        opportunities = self.scan_market()

        # Convert to format expected by main system
        formatted_opportunities = []
        for opp in opportunities:
            formatted_opportunities.append({
                'symbol': opp['symbol'],
                'direction': opp['direction'],
                'score': opp['score'],
                'confidence': opp['4h_strength'],
                'volatility': opp['volatility'],
                'reasoning': {
                    'vsa_confirmations': opp['vsa_confirmation'],
                    'timeframe_alignment': opp['timeframe_alignment'],
                    'details': f"VSA: {opp['vsa_confirmation']}/4, Alignment: {opp['timeframe_alignment']}/4, 4H: {opp['4h_strength']:.2f}"
                }
            })

        return formatted_opportunities

    def generate_trading_signals(self, max_signals: int = 5) -> List[Dict]:
        """
        Generate trading signals from scanned opportunities
        """
        opportunities = self.scan_market()
        
        print("\n" + "="*70)
        print("TRADING SIGNAL GENERATION")
        print("="*70)
        
        if not opportunities:
            print("❌ No valid opportunities found")
            return []
        
        # Take top opportunities
        top_opportunities = opportunities[:max_signals]
        
        trading_signals = []
        
        for opp in top_opportunities:
            # Get current price for position sizing
            ticker = self.exchange.fetch_ticker(opp['symbol'])
            current_price = ticker['last']
            
            # Determine leverage based primarily on signal quality, not volatility
            base_leverage = 5  # Base leverage
            
            # Signal quality determines leverage (stronger signals = higher leverage)
            score_bonus = opp['score'] * 4  # 0.5-1.0 score = 2-4 leverage bonus
            
            # Volatility is a minor adjustment factor (not primary)
            # Low volatility gets slight boost, high volatility gets slight reduction
            volatility_adjustment = 0
            if opp['volatility'] < 1.0:  # Low volatility
                volatility_adjustment = 0.5  # Small bonus for stable coins
            elif opp['volatility'] > 2.0:  # High volatility  
                volatility_adjustment = -0.5  # Small penalty for very volatile coins
            
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
                    '4h_validation': 'CONFIRMED',
                    'multi_criteria_score': opp['score']
                }
            }
            
            trading_signals.append(signal)
            
            print(f"\n🎯 Signal #{len(trading_signals)}: {signal['symbol']}")
            print(f"   Action: {signal['action']}")
            print(f"   Leverage: {signal['leverage']}x")
            print(f"   Confidence: {signal['confidence']:.2f}")
            print(f"   Score: {signal['score']:.2f}")
        
        # Save signals to file
        with open('trading_signals.json', 'w') as f:
            json.dump(trading_signals, f, indent=2)
        
        print(f"\n✅ Generated {len(trading_signals)} trading signals")
        print("📄 Signals saved to: trading_signals.json")
        
        return trading_signals

def main():
    scanner = EnhancedMarketScanner()
    
    print("Starting Enhanced Market Scanner...")
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Generate trading signals
    signals = scanner.generate_trading_signals(max_signals=5)
    
    if signals:
        print("\n" + "="*70)
        print("SIGNAL SUMMARY")
        print("="*70)
        
        for i, signal in enumerate(signals, 1):
            print(f"{i}. {signal['symbol']}: {signal['action']} @ {signal['leverage']}x (Score: {signal['score']:.2f})")
    
    print("\n✅ Scan complete!")

if __name__ == "__main__":
    main()