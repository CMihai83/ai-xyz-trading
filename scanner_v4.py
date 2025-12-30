#!/usr/bin/env python3
"""
Scanner v4.0: Intelligent All-Market Scanner
Scans ALL available coins (not just top 30 or 100) using multi-indicator opportunity detection
Two-stage approach: Quick filter → Deep analysis
"""

import ccxt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import json
import os
from collections import defaultdict

# Import components
from opportunity_filters import OpportunityFilter
from anticipatory_signals import AnticipatorySignalDetector
from breakout_detector import BreakoutDetector

# Import AI components from opportunity cost engine
try:
    from v3_opportunity_cost_engine import OpportunityCostEngine
    from dynamic_threshold_engine import DynamicThresholdEngine
    from opportunity_cost_predictor import OpportunityCostPredictor
    from correlation_matrix_analyzer import CorrelationMatrixAnalyzer
    AI_COMPONENTS_AVAILABLE = True
except ImportError:
    AI_COMPONENTS_AVAILABLE = False
    print("⚠️ Some AI components not available, using fallback methods")


class ScannerV4:
    """
    Advanced All-Market Scanner with Two-Stage Filtering

    Stage 1 (Quick Filter): Scan ALL available USDT futures
        - Uses lightweight indicators (volume, price change, momentum)
        - Filters out low-opportunity coins quickly
        - Target: Process 200-500 coins in 10-15 seconds

    Stage 2 (Deep Analysis): Multi-timeframe VSA + ML + Risk Metrics
        - Full technical analysis on filtered opportunities (30-50 coins)
        - VSA, ML prediction, Sharpe/Sortino, correlation analysis
        - Target: Complete in 15-20 seconds

    Total scan time: 25-35 seconds for ALL market opportunities
    """

    def __init__(self, exchange=None):
        self.exchange = exchange
        if not self.exchange:
            self.exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_SECRET'),
                'password': os.getenv('BITGET_PASSWORD'),
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'}
            })

        # Initialize opportunity filter
        self.opportunity_filter = OpportunityFilter()

        # Initialize anticipatory signal detector (catch moves BEFORE they happen)
        self.anticipatory_detector = AnticipatorySignalDetector()

        # Initialize breakout detector (catch moves AS they happen)
        self.breakout_detector = BreakoutDetector()

        # Initialize AI components if available
        if AI_COMPONENTS_AVAILABLE:
            self.opp_cost_engine = OpportunityCostEngine(self.exchange)
            self.dynamic_thresholds = DynamicThresholdEngine()
            self.ml_predictor = OpportunityCostPredictor()
            self.correlation_analyzer = CorrelationMatrixAnalyzer(self.exchange)
            print("✅ AI components loaded successfully")
        else:
            self.opp_cost_engine = None
            self.dynamic_thresholds = None
            self.ml_predictor = None
            self.correlation_analyzer = None

        # Timeframes for deep analysis
        self.timeframes = ['5m', '15m', '1h', '4h']

        # Cache for market data (reduce API calls)
        self.cache = {
            'all_markets': {'data': None, 'timestamp': None, 'ttl': 600},  # 10 min
            'tickers': {'data': None, 'timestamp': None, 'ttl': 60},  # 1 min
            'ohlcv': defaultdict(lambda: {'data': None, 'timestamp': None, 'ttl': 120})  # 2 min
        }

        # Performance tracking
        self.stats = {
            'total_markets': 0,
            'stage1_filtered': 0,
            'stage2_analyzed': 0,
            'opportunities_found': 0,
            'scan_time': 0,
            'api_calls': 0
        }

        print("🚀 Scanner v4.0 Initialized - All-Market Multi-Indicator Scanner")
        print("   📊 Two-stage filtering: Quick scan → Deep analysis")
        print("   🎯 Opportunity detection: 7 multi-factor indicators")
        print("   ⚡ Optimized for scanning ALL available markets")

    def scan_market(self, max_deep_analysis: int = 40) -> List[Dict]:
        """
        Main scanning method: Two-stage approach

        Args:
            max_deep_analysis: Maximum number of coins to analyze deeply (Stage 2)

        Returns:
            List of trading opportunities ranked by quality
        """
        start_time = time.time()
        print("\n" + "="*80)
        print("🔍 SCANNER V4.0 - ALL MARKET OPPORTUNITY SCAN")
        print("="*80)

        # STAGE 1: Quick Filter - Scan ALL markets
        print("\n📋 STAGE 1: Quick Filter (ALL Markets)")
        stage1_candidates = self._stage1_quick_filter()
        self.stats['stage1_filtered'] = len(stage1_candidates)
        print(f"   ✅ Filtered to {len(stage1_candidates)} candidates from {self.stats['total_markets']} total markets")

        # STAGE 2: Deep Analysis - Multi-timeframe + ML + Risk metrics
        print(f"\n🔬 STAGE 2: Deep Analysis (Top {max_deep_analysis} Candidates)")
        opportunities = self._stage2_deep_analysis(stage1_candidates[:max_deep_analysis])
        self.stats['stage2_analyzed'] = len(stage1_candidates[:max_deep_analysis])
        self.stats['opportunities_found'] = len(opportunities)

        # Calculate final statistics
        elapsed = time.time() - start_time
        self.stats['scan_time'] = elapsed

        # Print summary
        print("\n" + "="*80)
        print("📊 SCAN COMPLETE")
        print("="*80)
        print(f"⏱️  Scan Time: {elapsed:.1f}s")
        print(f"🌍 Total Markets Scanned: {self.stats['total_markets']}")
        print(f"🔍 Stage 1 Candidates: {self.stats['stage1_filtered']}")
        print(f"🔬 Stage 2 Analyzed: {self.stats['stage2_analyzed']}")
        print(f"✨ Opportunities Found: {self.stats['opportunities_found']}")
        print(f"📞 API Calls Made: {self.stats['api_calls']}")
        print("="*80)

        return opportunities

    def _stage1_quick_filter(self) -> List[Dict]:
        """
        Stage 1: Quick filter using lightweight indicators
        Scan ALL USDT perpetual futures and filter based on:
        - Volume threshold ($100k+ daily volume)
        - Price movement (>0.5% change in 24h)
        - Momentum signals

        Returns:
            List of candidate symbols with basic metrics
        """
        # Get ALL USDT perpetual futures
        all_markets = self._get_all_usdt_futures()
        self.stats['total_markets'] = len(all_markets)
        print(f"   📈 Scanning {len(all_markets)} USDT perpetual futures...")

        # Fetch tickers for all markets (batch call)
        tickers = self._get_cached_tickers(all_markets)
        self.stats['api_calls'] += 1  # Batch ticker fetch

        # Quick filter each market
        candidates = []
        passed = 0

        for symbol in all_markets:
            ticker = tickers.get(symbol, {})
            if not ticker:
                continue

            # Apply quick filter
            if self.opportunity_filter.quick_filter_pass(ticker):
                # Calculate basic opportunity metrics
                price_change_pct = abs(ticker.get('percentage', 0) or 0)
                volume_usd = ticker.get('quoteVolume', 0) or 0

                # Classify opportunity type
                opportunity_type = self._classify_quick_opportunity(ticker)

                candidates.append({
                    'symbol': symbol,
                    'price_change_24h': price_change_pct,
                    'volume_usd_24h': volume_usd,
                    'current_price': ticker.get('last', 0),
                    'opportunity_type': opportunity_type,
                    'quick_score': self._calculate_quick_score(ticker)
                })
                passed += 1

            # Progress indicator (every 50 symbols)
            if len(all_markets) > 100 and (all_markets.index(symbol) + 1) % 50 == 0:
                print(f"   ... Processed {all_markets.index(symbol) + 1}/{len(all_markets)} ({passed} candidates)")

        # Sort by quick_score
        candidates = sorted(candidates, key=lambda x: x['quick_score'], reverse=True)

        return candidates

    def _stage2_deep_analysis(self, candidates: List[Dict]) -> List[Dict]:
        """
        Stage 2: Deep multi-timeframe analysis with ML and risk metrics

        For each candidate:
        1. Fetch OHLCV data for all timeframes
        2. Calculate comprehensive opportunity score (7 indicators)
        3. Apply VSA analysis
        4. ML signal quality prediction
        5. Sharpe/Sortino risk-adjusted metrics
        6. Correlation filtering
        7. Dynamic threshold application

        Returns:
            List of high-quality opportunities
        """
        opportunities = []

        for i, candidate in enumerate(candidates, 1):
            symbol = candidate['symbol']
            print(f"   [{i}/{len(candidates)}] Analyzing {symbol}...", end=' ')

            try:
                # Fetch multi-timeframe data (with caching)
                tf_data = self._fetch_multi_timeframe_data(symbol)
                if not tf_data:
                    print("❌ No data")
                    continue

                # Calculate comprehensive opportunity score
                opp_score_data = self._calculate_comprehensive_score(symbol, tf_data, candidate)

                # ENHANCED RISK FILTERS (Based on ONT failure analysis)
                final_score = opp_score_data['final_score']
                price_change = abs(candidate.get('price_change_24h', 0))

                # Filter 1: Minimum score threshold (raised from 0.6 to 0.7)
                if final_score < 0.7:
                    print(f"⚠️  Score: {final_score:.3f} (below 0.7 threshold)")
                    continue

                # Filter 2: EARLY MOMENTUM - Prefer 1-8% moves (catch early), reject late moves (>12%)
                if price_change < 1.0:
                    print(f"⚠️  Score: {final_score:.3f} but no momentum confirmation ({price_change:.1f}% < 1%)")
                    continue
                if price_change > 12.0:
                    print(f"⚠️  Score: {final_score:.3f} but move already exhausted ({price_change:.1f}% > 12%) - too late")
                    continue

                # Filter 3: Volume quality check
                if candidate.get('volume_usd_24h', 0) < 1_000_000:
                    print(f"⚠️  Score: {final_score:.3f} but low volume")
                    continue

                # Filter 4: MEAN REVERSION - Prevent buying tops/selling bottoms
                primary_df = tf_data.get('5m', tf_data.get('15m'))
                if primary_df is not None and len(primary_df) >= 50:
                    # Calculate RSI
                    delta = primary_df['close'].diff()
                    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
                    loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
                    rs = gain / (loss + 1e-6)
                    rsi = 100 - (100 / (1 + rs))
                    current_rsi = rsi.iloc[-1]

                    # Calculate distance from 20-period MA
                    ma_20 = primary_df['close'].rolling(window=20).mean().iloc[-1]
                    current_price = primary_df['close'].iloc[-1]
                    distance_from_ma = ((current_price - ma_20) / ma_20) * 100

                    direction = opp_score_data['direction']

                    # Reject LONG positions in overbought/extended conditions
                    if direction == 'BULLISH':
                        if current_rsi > 70:
                            print(f"⚠️  Score: {final_score:.3f} but OVERBOUGHT (RSI: {current_rsi:.1f}) - buying top rejected")
                            continue
                        if distance_from_ma > 10:
                            print(f"⚠️  Score: {final_score:.3f} but {distance_from_ma:.1f}% above MA20 - extended rejected")
                            continue

                    # Reject SHORT positions in oversold/oversold conditions
                    elif direction == 'BEARISH':
                        if current_rsi < 30:
                            print(f"⚠️  Score: {final_score:.3f} but OVERSOLD (RSI: {current_rsi:.1f}) - selling bottom rejected")
                            continue
                        if distance_from_ma < -10:
                            print(f"⚠️  Score: {final_score:.3f} but {distance_from_ma:.1f}% below MA20 - oversold rejected")
                            continue

                # Passed all filters
                opportunities.append(opp_score_data)
                print(f"✅ Score: {final_score:.3f} ({opp_score_data['direction']}) | Momentum: {price_change:.1f}%")

            except Exception as e:
                print(f"❌ Error: {str(e)[:50]}")
                continue

        # Apply correlation filter to diversify opportunities
        if self.correlation_analyzer and len(opportunities) > 10:
            print("\n   🔗 Applying correlation filter for diversification...")
            opportunities = self._apply_correlation_filter(opportunities)

        # Sort by final score
        opportunities = sorted(opportunities, key=lambda x: x['final_score'], reverse=True)

        return opportunities

    def _get_all_usdt_futures(self) -> List[str]:
        """Get ALL USDT-margined perpetual futures (cached)"""
        cache_entry = self.cache['all_markets']

        # Check cache
        if cache_entry['data'] and cache_entry['timestamp']:
            age = time.time() - cache_entry['timestamp']
            if age < cache_entry['ttl']:
                return cache_entry['data']

        # Fetch from exchange
        try:
            if not self.exchange.markets:
                self.exchange.load_markets()

            all_futures = [
                symbol for symbol, market in self.exchange.markets.items()
                if market.get('swap', False)
                and market.get('linear', False)
                and market.get('settle') == 'USDT'
                and market.get('active', True)
            ]

            # Update cache
            cache_entry['data'] = all_futures
            cache_entry['timestamp'] = time.time()

            return all_futures

        except Exception as e:
            print(f"   ⚠️ Error loading markets: {e}")
            return []

    def _get_cached_tickers(self, symbols: List[str]) -> Dict:
        """Fetch tickers with caching"""
        cache_entry = self.cache['tickers']

        # Check cache
        if cache_entry['data'] and cache_entry['timestamp']:
            age = time.time() - cache_entry['timestamp']
            if age < cache_entry['ttl']:
                return cache_entry['data']

        # Fetch from exchange
        try:
            tickers = self.exchange.fetch_tickers(symbols)

            # Update cache
            cache_entry['data'] = tickers
            cache_entry['timestamp'] = time.time()

            return tickers

        except Exception as e:
            print(f"   ⚠️ Error fetching tickers: {e}")
            return {}

    def _classify_quick_opportunity(self, ticker: Dict) -> str:
        """Classify opportunity type based on ticker data"""
        price_change = ticker.get('percentage', 0) or 0
        volume = ticker.get('quoteVolume', 0) or 0

        if abs(price_change) > 5.0:
            return 'HIGH_MOMENTUM'
        elif volume > 5000000:  # $5M+
            return 'HIGH_VOLUME'
        elif abs(price_change) > 3.0 and volume > 1000000:
            return 'MOMENTUM_VOLUME'
        else:
            return 'MODERATE_OPPORTUNITY'

    def _calculate_quick_score(self, ticker: Dict) -> float:
        """Calculate quick opportunity score from ticker data"""
        price_change = abs(ticker.get('percentage', 0) or 0)
        volume = ticker.get('quoteVolume', 0) or 0

        # Normalize components
        price_score = min(price_change / 10.0, 1.0)  # 10% = max score
        volume_score = min(volume / 10000000.0, 1.0)  # $10M = max score

        # Weighted combination
        return price_score * 0.6 + volume_score * 0.4

    def _fetch_multi_timeframe_data(self, symbol: str) -> Dict[str, pd.DataFrame]:
        """
        Fetch OHLCV data for all timeframes (with aggressive caching)

        Returns:
            Dict mapping timeframe to DataFrame
        """
        tf_data = {}

        for timeframe in self.timeframes:
            # Check cache first
            cache_key = f"{symbol}_{timeframe}"
            cache_entry = self.cache['ohlcv'][cache_key]

            if cache_entry['data'] is not None and cache_entry['timestamp']:
                age = time.time() - cache_entry['timestamp']
                if age < cache_entry['ttl']:
                    tf_data[timeframe] = cache_entry['data']
                    continue  # Use cached data

            # Fetch from exchange
            try:
                limit = 100 if timeframe in ['5m', '15m'] else 50
                ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

                # Update cache
                cache_entry['data'] = df
                cache_entry['timestamp'] = time.time()

                tf_data[timeframe] = df
                self.stats['api_calls'] += 1

                # Rate limiting
                time.sleep(0.1)

            except Exception as e:
                print(f"Error fetching {symbol} {timeframe}: {e}")
                continue

        return tf_data

    def _calculate_comprehensive_score(self, symbol: str, tf_data: Dict[str, pd.DataFrame],
                                       candidate: Dict) -> Dict:
        """
        Calculate comprehensive opportunity score using:
        1. Multi-indicator opportunity filter (7 factors)
        2. VSA analysis
        3. ML signal quality prediction (if available)
        4. Sharpe/Sortino risk metrics
        5. Multi-timeframe confirmation
        """
        # Use primary timeframe (5m) for detailed analysis
        primary_tf = '5m'
        if primary_tf not in tf_data or len(tf_data[primary_tf]) < 50:
            return {'final_score': 0, 'symbol': symbol}

        primary_data = tf_data[primary_tf]

        # 1. Calculate multi-indicator opportunity score
        opp_score_result = self.opportunity_filter.calculate_opportunity_score(primary_data)

        # 2. Calculate VSA score (Volume Spread Analysis)
        vsa_score = self._calculate_vsa_score(primary_data)

        # 3. Calculate multi-timeframe confirmation
        mtf_confirmation = self._calculate_mtf_confirmation(tf_data, opp_score_result['direction'])

        # 4. Calculate Sharpe/Sortino ratios
        sharpe_score, sortino_score = self._calculate_risk_metrics(primary_data)

        # 5. ML prediction (if available)
        ml_score = self._get_ml_prediction(symbol, primary_data, opp_score_result) if self.ml_predictor else 0.5

        # 6. ANTICIPATORY SIGNALS (catch moves BEFORE they happen)
        anticipatory_result = self.anticipatory_detector.detect_pre_breakout_setup(primary_data)
        anticipatory_score = anticipatory_result['total_score']

        # 7. BREAKOUT DETECTION (catch moves AS they happen)
        breakout_result = self.breakout_detector.detect_breakout(primary_data)
        breakout_score = breakout_result['score']

        # Weighted final score (THREE-STAGE TIMING: Anticipatory > Breakout > Reactive)
        final_score = (
            anticipatory_score * 0.25 +      # Anticipatory: 25% (early setups)
            breakout_score * 0.25 +         # Breakout: 25% (real-time breakouts)
            vsa_score * 0.20 +              # VSA: 20%
            ml_score * 0.12 +               # ML: 12%
            opp_score_result['total_score'] * 0.08 +  # Multi-indicator: 8%
            sharpe_score * 0.05 +           # Sharpe: 5%
            sortino_score * 0.03 +          # Sortino: 3%
            mtf_confirmation * 0.02         # Multi-timeframe: 2%
        )

        # Apply dynamic threshold adjustment (if available)
        if self.dynamic_thresholds:
            min_threshold = self._get_dynamic_threshold(primary_data)
        else:
            min_threshold = 0.6

        # Calculate dynamic leverage based on confidence (prevent high leverage on weak signals)
        if final_score >= 0.85:
            recommended_leverage = 10  # Very high confidence
        elif final_score >= 0.75:
            recommended_leverage = 7   # High confidence
        elif final_score >= 0.70:
            recommended_leverage = 5   # Moderate confidence (minimum threshold)
        else:
            recommended_leverage = 3   # Low confidence (shouldn't reach here due to filters)

        # Determine direction priority: Breakout > Anticipatory > Reactive
        if breakout_result['is_breakout'] and breakout_score > 0.6:
            final_direction = breakout_result['direction']
            primary_indicator = f"breakout_{breakout_result['breakout_type'].lower()}"
        elif anticipatory_score > 0.6:
            final_direction = anticipatory_result['direction']
            primary_indicator = f"anticipatory_{anticipatory_result['primary_signal']}"
        else:
            final_direction = opp_score_result['direction']
            primary_indicator = opp_score_result['primary_indicator']

        return {
            'symbol': symbol,
            'final_score': final_score,
            'direction': final_direction,
            'recommended_leverage': recommended_leverage,
            'primary_indicator': primary_indicator,
            'min_threshold': min_threshold,
            'breakdown': {
                'anticipatory': anticipatory_score,   # 25% - early setups
                'breakout': breakout_score,          # 25% - real-time breakouts
                'vsa': vsa_score,                    # 20%
                'ml_prediction': ml_score,           # 12%
                'opportunity_indicators': opp_score_result['total_score'],  # 8%
                'sharpe': sharpe_score,              # 5%
                'sortino': sortino_score,            # 3%
                'mtf_confirmation': mtf_confirmation # 2%
            },
            'anticipatory_details': anticipatory_result['breakdown'],
            'breakout_details': breakout_result,     # NEW
            'opportunity_details': opp_score_result['breakdown'],
            'current_price': candidate.get('current_price', 0),
            'volume_24h': candidate.get('volume_usd_24h', 0),
            'price_change_24h': candidate.get('price_change_24h', 0),
            'timeframe_data': {tf: len(df) for tf, df in tf_data.items()}
        }

    def _calculate_vsa_score(self, df: pd.DataFrame) -> float:
        """Calculate Volume Spread Analysis score"""
        if len(df) < 20:
            return 0

        # Calculate spread (high - low) and volume metrics
        df['spread'] = df['high'] - df['low']
        df['spread_pct'] = df['spread'] / df['close']

        # VSA signals
        recent_volume = df['volume'].iloc[-5:].mean()
        avg_volume = df['volume'].iloc[-20:-5].mean()
        volume_ratio = recent_volume / (avg_volume + 1e-6)

        recent_spread = df['spread_pct'].iloc[-5:].mean()
        avg_spread = df['spread_pct'].iloc[-20:-5].mean()
        spread_ratio = recent_spread / (avg_spread + 1e-6)

        # High volume + wide spread = strong signal
        # High volume + narrow spread = potential reversal
        if volume_ratio > 1.5 and spread_ratio > 1.2:
            vsa_score = 0.9  # Strong trending move
        elif volume_ratio > 2.0 and spread_ratio < 0.8:
            vsa_score = 0.85  # Potential reversal (high volume, low spread)
        elif volume_ratio > 1.2:
            vsa_score = 0.7  # Moderate signal
        else:
            vsa_score = 0.5  # Weak signal

        return vsa_score

    def _calculate_mtf_confirmation(self, tf_data: Dict[str, pd.DataFrame],
                                    direction: str) -> float:
        """
        Calculate multi-timeframe confirmation score
        Higher score if all timeframes agree on direction
        """
        if direction == 'NEUTRAL':
            return 0.5

        confirmations = 0
        total_timeframes = 0

        for tf, df in tf_data.items():
            if len(df) < 10:
                continue

            # Check if this timeframe confirms the direction
            recent_return = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]

            if direction == 'BULLISH' and recent_return > 0.01:
                confirmations += 1
            elif direction == 'BEARISH' and recent_return < -0.01:
                confirmations += 1

            total_timeframes += 1

        return confirmations / total_timeframes if total_timeframes > 0 else 0.5

    def _calculate_risk_metrics(self, df: pd.DataFrame) -> tuple:
        """Calculate Sharpe and Sortino ratios"""
        if len(df) < 24:
            return 0.5, 0.5

        # Calculate returns
        returns = df['close'].pct_change().dropna()

        # Sharpe ratio (simplified, annualized)
        mean_return = returns.mean()
        std_return = returns.std()
        sharpe = mean_return / (std_return + 1e-6)
        sharpe_normalized = min(max((sharpe + 2) / 4, 0), 1)  # Normalize to 0-1

        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_std = downside_returns.std() if len(downside_returns) > 0 else std_return
        sortino = mean_return / (downside_std + 1e-6)
        sortino_normalized = min(max((sortino + 2) / 4, 0), 1)  # Normalize to 0-1

        return sharpe_normalized, sortino_normalized

    def _get_ml_prediction(self, symbol: str, df: pd.DataFrame, opp_data: Dict) -> float:
        """Get ML-based signal quality prediction (placeholder for future ML integration)"""
        # TODO: Integrate trained ML model
        # For now, use a heuristic based on opportunity score consistency

        # If opportunity score is high across multiple indicators, return higher ML score
        high_scores = sum(1 for ind_data in opp_data['breakdown'].values()
                         if ind_data.get('score', 0) > 0.7)

        ml_score = 0.5 + (high_scores / len(opp_data['breakdown'])) * 0.3
        return min(ml_score, 1.0)

    def _get_dynamic_threshold(self, df: pd.DataFrame) -> float:
        """Calculate dynamic threshold based on market volatility"""
        # Calculate recent market volatility
        returns = df['close'].pct_change().dropna()
        volatility = returns.std()

        # Higher volatility = require higher signal quality
        if volatility > 0.03:  # High volatility (3%+ std)
            return 0.7
        elif volatility > 0.02:  # Moderate volatility
            return 0.65
        else:  # Low volatility
            return 0.6

    def _apply_correlation_filter(self, opportunities: List[Dict]) -> List[Dict]:
        """
        Filter opportunities to reduce correlation (improve diversification)
        Keep top opportunities but ensure they're not highly correlated
        """
        if not opportunities:
            return []

        filtered = [opportunities[0]]  # Always keep the top opportunity

        for opp in opportunities[1:]:
            # Check correlation with already selected opportunities
            is_correlated = False

            for selected in filtered:
                # Simple heuristic: Same sector/type coins (e.g., DeFi, L1, Meme)
                # In production, would use actual correlation matrix

                # For now, ensure we don't select too many similar coins
                # This is a placeholder - correlation_analyzer would provide better filtering
                pass

            if not is_correlated:
                filtered.append(opp)

            # Limit to reasonable number of diversified opportunities
            if len(filtered) >= 15:
                break

        return filtered

    def scan_for_opportunities(self) -> List[Dict]:
        """
        Main entry point for trading system compatibility
        Matches interface of SimpleVSAScanner and EnhancedMarketScanner
        """
        opportunities = self.scan_market(max_deep_analysis=40)

        # Convert to expected format for main trading system
        formatted_opportunities = []
        for opp in opportunities:
            formatted_opportunities.append({
                'symbol': opp['symbol'],
                'direction': opp['direction'],
                'score': opp['final_score'],  # Main system expects 'score' not 'signal_quality'
                'confidence': opp['final_score'],  # Use same as score for confidence
                'leverage': opp.get('recommended_leverage', 10),
                'volatility': opp.get('price_change_24h', 0),
                'size_multiplier': 1.0,
                'price_change_24h': opp.get('price_change_24h', 0),
                'volume': opp.get('volume_24h', 0),
                'reasoning': {
                    'primary_indicator': opp.get('primary_indicator', 'unknown'),
                    'vsa': opp.get('breakdown', {}).get('vsa', 0),
                    'ml': opp.get('breakdown', {}).get('ml_prediction', 0),
                    'technical': opp.get('breakdown', {}).get('technical', 0),
                    'details': f"{opp.get('primary_indicator', 'Multi-factor')} signal: Score {opp['final_score']:.3f}"
                }
            })

        return formatted_opportunities


if __name__ == "__main__":
    # Test Scanner v4.0
    print("🚀 Testing Scanner v4.0...")

    scanner = ScannerV4()
    opportunities = scanner.scan_market(max_deep_analysis=30)

    print(f"\n✨ Found {len(opportunities)} opportunities:")
    for i, opp in enumerate(opportunities[:10], 1):
        print(f"\n{i}. {opp['symbol']} - {opp['direction']}")
        print(f"   Score: {opp['final_score']:.3f}")
        print(f"   Primary: {opp['primary_indicator']}")
        print(f"   Price: ${opp['current_price']:.4f}")
        print(f"   Volume 24h: ${opp['volume_24h']:,.0f}")
        print(f"   Breakdown: VSA={opp['breakdown']['vsa']:.2f}, "
              f"ML={opp['breakdown']['ml_prediction']:.2f}, "
              f"Sharpe={opp['breakdown']['sharpe']:.2f}")
