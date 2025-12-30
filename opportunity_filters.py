#!/usr/bin/env python3
"""
Multi-Indicator Opportunity Filters
Identifies trading opportunities across ALL market coins using various technical signals
Not just volume-based, but momentum, volatility, breakouts, and pattern recognition
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class OpportunityFilter:
    """
    Multi-factor opportunity detection system
    Scans for opportunities using momentum, volatility, volume, technical patterns
    """

    def __init__(self):
        self.filters = {
            'momentum': 0.20,      # 20% weight - strong trends
            'volatility': 0.18,    # 18% weight - potential for large moves
            'volume_spike': 0.15,  # 15% weight - unusual activity
            'rsi_extreme': 0.12,   # 12% weight - oversold/overbought
            'macd_signal': 0.10,   # 10% weight - trend confirmation
            'bb_squeeze': 0.10,    # 10% weight - potential breakout
            'price_action': 0.15   # 15% weight - support/resistance breaks
        }

        print("🔍 Opportunity Filter initialized with 7 multi-factor indicators")

    def calculate_opportunity_score(self, ohlcv_data: pd.DataFrame,
                                    ticker_data: Dict = None) -> Dict:
        """
        Calculate comprehensive opportunity score for a symbol

        Args:
            ohlcv_data: DataFrame with OHLCV data (at least 50 candles for indicators)
            ticker_data: Optional ticker data for additional metrics

        Returns:
            dict: Opportunity score breakdown
        """
        if len(ohlcv_data) < 50:
            return {'total_score': 0, 'reason': 'Insufficient data'}

        df = ohlcv_data.copy()

        # Calculate all indicator scores
        momentum_score = self._calculate_momentum_score(df)
        volatility_score = self._calculate_volatility_score(df)
        volume_score = self._calculate_volume_spike_score(df)
        rsi_score = self._calculate_rsi_extreme_score(df)
        macd_score = self._calculate_macd_signal_score(df)
        bb_score = self._calculate_bb_squeeze_score(df)
        price_action_score = self._calculate_price_action_score(df)

        # Calculate weighted total score
        total_score = (
            momentum_score['score'] * self.filters['momentum'] +
            volatility_score['score'] * self.filters['volatility'] +
            volume_score['score'] * self.filters['volume_spike'] +
            rsi_score['score'] * self.filters['rsi_extreme'] +
            macd_score['score'] * self.filters['macd_signal'] +
            bb_score['score'] * self.filters['bb_squeeze'] +
            price_action_score['score'] * self.filters['price_action']
        )

        # Determine primary opportunity type
        scores_dict = {
            'momentum': momentum_score['score'],
            'volatility': volatility_score['score'],
            'volume_spike': volume_score['score'],
            'rsi_extreme': rsi_score['score'],
            'macd_signal': macd_score['score'],
            'bb_squeeze': bb_score['score'],
            'price_action': price_action_score['score']
        }
        primary_indicator = max(scores_dict, key=scores_dict.get)

        return {
            'total_score': total_score,
            'primary_indicator': primary_indicator,
            'breakdown': {
                'momentum': momentum_score,
                'volatility': volatility_score,
                'volume_spike': volume_score,
                'rsi_extreme': rsi_score,
                'macd_signal': macd_score,
                'bb_squeeze': bb_score,
                'price_action': price_action_score
            },
            'direction': self._determine_direction(
                momentum_score, rsi_score, macd_score, price_action_score
            )
        }

    def _calculate_momentum_score(self, df: pd.DataFrame) -> Dict:
        """
        Score based on price momentum over multiple timeframes
        Strong trends = high score
        """
        # Calculate returns over different periods
        returns_1h = (df['close'].iloc[-1] - df['close'].iloc[-12]) / df['close'].iloc[-12] if len(df) > 12 else 0
        returns_4h = (df['close'].iloc[-1] - df['close'].iloc[-48]) / df['close'].iloc[-48] if len(df) > 48 else 0

        # Check for consistent direction (trend strength)
        recent_closes = df['close'].iloc[-20:].values
        trend_consistency = 0
        if len(recent_closes) >= 20:
            # Calculate how many consecutive moves in same direction
            price_changes = np.diff(recent_closes)
            positive_moves = np.sum(price_changes > 0)
            negative_moves = np.sum(price_changes < 0)
            trend_consistency = max(positive_moves, negative_moves) / len(price_changes)

        # Calculate momentum strength
        momentum_strength = abs(returns_1h) + abs(returns_4h) * 0.5

        # Score: High momentum + high consistency = high score
        score = min(momentum_strength * 10 * (0.5 + trend_consistency * 0.5), 1.0)

        return {
            'score': score,
            'returns_1h': returns_1h,
            'returns_4h': returns_4h,
            'trend_consistency': trend_consistency,
            'signal': 'STRONG_MOMENTUM' if score > 0.7 else ('WEAK_MOMENTUM' if score > 0.3 else 'NO_MOMENTUM')
        }

    def _calculate_volatility_score(self, df: pd.DataFrame) -> Dict:
        """
        Score based on recent volatility increase (potential breakout)
        Rising volatility = opportunity for large moves
        """
        # Calculate recent volatility (last 20 periods)
        recent_returns = df['close'].pct_change().iloc[-20:].std()
        # Calculate historical volatility (20-50 periods ago)
        historical_returns = df['close'].pct_change().iloc[-50:-20].std() if len(df) > 50 else recent_returns

        # Volatility ratio (recent vs historical)
        volatility_ratio = recent_returns / (historical_returns + 1e-6)

        # ATR (Average True Range) for absolute volatility measure
        df['h-l'] = df['high'] - df['low']
        df['h-pc'] = abs(df['high'] - df['close'].shift(1))
        df['l-pc'] = abs(df['low'] - df['close'].shift(1))
        df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)
        atr = df['tr'].iloc[-14:].mean()  # 14-period ATR
        atr_pct = atr / df['close'].iloc[-1]

        # Score: Increasing volatility + high ATR = high opportunity
        score = min((volatility_ratio - 1.0) * 0.5 + atr_pct * 20, 1.0)
        score = max(0, score)  # Ensure non-negative

        return {
            'score': score,
            'volatility_ratio': volatility_ratio,
            'atr_pct': atr_pct,
            'signal': 'HIGH_VOLATILITY' if score > 0.7 else ('MODERATE_VOLATILITY' if score > 0.4 else 'LOW_VOLATILITY')
        }

    def _calculate_volume_spike_score(self, df: pd.DataFrame) -> Dict:
        """
        Score based on volume spikes (unusual trading activity)
        Volume >> average = potential opportunity
        """
        # Calculate average volume
        avg_volume = df['volume'].iloc[-50:-1].mean() if len(df) > 50 else df['volume'].mean()
        current_volume = df['volume'].iloc[-1]

        # Volume ratio (current vs average)
        volume_ratio = current_volume / (avg_volume + 1e-6)

        # Recent volume trend (increasing?)
        recent_volume_trend = df['volume'].iloc[-10:].mean() / (df['volume'].iloc[-30:-10].mean() + 1e-6) if len(df) > 30 else 1.0

        # Score: High volume spike + increasing trend = high score
        spike_score = min((volume_ratio - 1.0) * 0.3, 1.0)
        trend_score = min((recent_volume_trend - 1.0) * 0.5, 0.5)
        score = max(0, spike_score + trend_score)

        return {
            'score': score,
            'volume_ratio': volume_ratio,
            'recent_trend': recent_volume_trend,
            'signal': 'VOLUME_SPIKE' if volume_ratio > 2.0 else ('VOLUME_INCREASE' if volume_ratio > 1.3 else 'NORMAL_VOLUME')
        }

    def _calculate_rsi_extreme_score(self, df: pd.DataFrame) -> Dict:
        """
        Score based on RSI extremes (oversold/overbought conditions)
        RSI < 30 or > 70 = reversal opportunity
        """
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-6)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        # Score based on distance from extreme zones
        if current_rsi < 30:
            # Oversold - potential bullish reversal
            score = (30 - current_rsi) / 30  # Score increases as RSI decreases
            signal = 'OVERSOLD'
            direction = 'BULLISH'
        elif current_rsi > 70:
            # Overbought - potential bearish reversal
            score = (current_rsi - 70) / 30  # Score increases as RSI increases
            signal = 'OVERBOUGHT'
            direction = 'BEARISH'
        else:
            # Neutral zone
            score = 0
            signal = 'NEUTRAL'
            direction = 'NEUTRAL'

        return {
            'score': min(score, 1.0),
            'rsi': current_rsi,
            'signal': signal,
            'direction': direction
        }

    def _calculate_macd_signal_score(self, df: pd.DataFrame) -> Dict:
        """
        Score based on MACD crossovers and momentum
        Recent crossover = trend change opportunity
        """
        # Calculate MACD
        ema_12 = df['close'].ewm(span=12, adjust=False).mean()
        ema_26 = df['close'].ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        histogram = macd_line - signal_line

        current_histogram = histogram.iloc[-1]
        prev_histogram = histogram.iloc[-2] if len(histogram) > 1 else 0

        # Detect crossover
        bullish_cross = current_histogram > 0 and prev_histogram <= 0
        bearish_cross = current_histogram < 0 and prev_histogram >= 0

        # Score based on histogram strength and recent crossover
        histogram_strength = abs(current_histogram) / (df['close'].iloc[-1] + 1e-6)

        if bullish_cross:
            score = min(0.8 + histogram_strength * 100, 1.0)
            signal = 'BULLISH_CROSS'
        elif bearish_cross:
            score = min(0.8 + histogram_strength * 100, 1.0)
            signal = 'BEARISH_CROSS'
        else:
            # No crossover, score based on histogram strength
            score = min(histogram_strength * 100, 0.6)
            signal = 'STRONG_TREND' if abs(current_histogram) > abs(prev_histogram) else 'WEAK_TREND'

        return {
            'score': score,
            'macd': macd_line.iloc[-1],
            'signal_line': signal_line.iloc[-1],
            'histogram': current_histogram,
            'signal': signal,
            'direction': 'BULLISH' if current_histogram > 0 else 'BEARISH'
        }

    def _calculate_bb_squeeze_score(self, df: pd.DataFrame) -> Dict:
        """
        Score based on Bollinger Band squeeze (low volatility before breakout)
        Tight bands = potential explosive move
        """
        # Calculate Bollinger Bands
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        upper_band = sma_20 + (2 * std_20)
        lower_band = sma_20 - (2 * std_20)

        # Band width (normalized)
        band_width = (upper_band - lower_band) / sma_20
        current_width = band_width.iloc[-1]
        avg_width = band_width.iloc[-50:-1].mean() if len(band_width) > 50 else current_width

        # Squeeze ratio (current width vs average)
        squeeze_ratio = current_width / (avg_width + 1e-6)

        # Score: Tighter bands (lower ratio) = higher potential for breakout
        score = max(0, 1.0 - squeeze_ratio) if squeeze_ratio < 1.0 else 0

        # Check if price is near bands (potential breakout direction)
        close_price = df['close'].iloc[-1]
        distance_to_upper = (upper_band.iloc[-1] - close_price) / close_price
        distance_to_lower = (close_price - lower_band.iloc[-1]) / close_price

        if distance_to_upper < 0.01:
            signal = 'NEAR_UPPER_BAND'
            direction = 'BULLISH'
        elif distance_to_lower < 0.01:
            signal = 'NEAR_LOWER_BAND'
            direction = 'BEARISH'
        else:
            signal = 'SQUEEZE' if score > 0.6 else 'NORMAL'
            direction = 'NEUTRAL'

        return {
            'score': score,
            'squeeze_ratio': squeeze_ratio,
            'signal': signal,
            'direction': direction
        }

    def _calculate_price_action_score(self, df: pd.DataFrame) -> Dict:
        """
        Score based on price breaking support/resistance levels
        Recent breakout = momentum opportunity
        """
        # Identify recent high/low (support/resistance)
        recent_high = df['high'].iloc[-50:].max() if len(df) > 50 else df['high'].max()
        recent_low = df['low'].iloc[-50:].min() if len(df) > 50 else df['low'].min()
        current_price = df['close'].iloc[-1]

        # Calculate position within range
        price_range = recent_high - recent_low
        position_in_range = (current_price - recent_low) / (price_range + 1e-6)

        # Detect breakouts
        prev_high = df['high'].iloc[-51:-1].max() if len(df) > 51 else recent_high * 0.99
        prev_low = df['low'].iloc[-51:-1].min() if len(df) > 51 else recent_low * 1.01

        breakout_high = current_price > prev_high
        breakout_low = current_price < prev_low

        # Score based on breakout or position near extremes
        if breakout_high:
            score = 0.9
            signal = 'BREAKOUT_HIGH'
            direction = 'BULLISH'
        elif breakout_low:
            score = 0.9
            signal = 'BREAKOUT_LOW'
            direction = 'BEARISH'
        elif position_in_range > 0.9:
            score = 0.7
            signal = 'NEAR_RESISTANCE'
            direction = 'BEARISH'  # Potential rejection
        elif position_in_range < 0.1:
            score = 0.7
            signal = 'NEAR_SUPPORT'
            direction = 'BULLISH'  # Potential bounce
        else:
            score = 0.3
            signal = 'MID_RANGE'
            direction = 'NEUTRAL'

        return {
            'score': score,
            'position_in_range': position_in_range,
            'signal': signal,
            'direction': direction
        }

    def _determine_direction(self, momentum: Dict, rsi: Dict,
                            macd: Dict, price_action: Dict) -> str:
        """
        Determine overall trade direction based on multiple indicators
        """
        bullish_signals = 0
        bearish_signals = 0

        # Count directional signals
        for indicator in [momentum, rsi, macd, price_action]:
            direction = indicator.get('direction', 'NEUTRAL')
            if direction == 'BULLISH':
                bullish_signals += 1
            elif direction == 'BEARISH':
                bearish_signals += 1

        # Check momentum direction specifically
        if momentum.get('returns_1h', 0) > 0:
            bullish_signals += 0.5
        else:
            bearish_signals += 0.5

        # Determine overall direction
        if bullish_signals > bearish_signals + 1:
            return 'BULLISH'
        elif bearish_signals > bullish_signals + 1:
            return 'BEARISH'
        else:
            return 'NEUTRAL'

    def quick_filter_pass(self, ticker_data: Dict) -> bool:
        """
        Quick first-pass filter to eliminate obviously bad opportunities
        Used in Stage 1 scanning to quickly filter ALL market coins

        Args:
            ticker_data: Ticker data from exchange (must have volume, change, etc.)

        Returns:
            bool: True if passes quick filter (worthy of deep analysis)
        """
        # Minimum liquidity requirement (24h volume)
        min_volume_usd = 100000  # $100k minimum daily volume
        volume = ticker_data.get('quoteVolume', 0) or 0
        if volume < min_volume_usd:
            return False

        # Minimum price change (avoid dead coins)
        price_change_pct = abs(ticker_data.get('percentage', 0) or 0)
        if price_change_pct < 0.5:  # Less than 0.5% change in 24h
            return False

        # Check for extreme moves (potential opportunities)
        # OR moderate moves with high volume
        high_move = price_change_pct > 3.0  # 3%+ move
        high_volume = volume > 1000000  # $1M+ volume
        moderate_move = price_change_pct > 1.5 and high_volume

        return high_move or moderate_move


if __name__ == "__main__":
    # Test opportunity filter
    print("Testing Opportunity Filter...")

    # Create sample OHLCV data for testing
    dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')

    # Simulate momentum opportunity (strong uptrend)
    sample_data = pd.DataFrame({
        'timestamp': dates,
        'open': np.linspace(100, 120, 100) + np.random.randn(100) * 0.5,
        'high': np.linspace(101, 121, 100) + np.random.randn(100) * 0.5,
        'low': np.linspace(99, 119, 100) + np.random.randn(100) * 0.5,
        'close': np.linspace(100, 120, 100) + np.random.randn(100) * 0.5,
        'volume': np.random.randn(100) * 1000 + 5000
    })

    # Add volume spike at end
    sample_data.loc[sample_data.index[-5:], 'volume'] = 15000

    filter_engine = OpportunityFilter()
    result = filter_engine.calculate_opportunity_score(sample_data)

    print(f"\n📊 Opportunity Score: {result['total_score']:.3f}")
    print(f"🎯 Primary Indicator: {result['primary_indicator']}")
    print(f"📈 Direction: {result['direction']}")
    print(f"\n💡 Breakdown:")
    for indicator, data in result['breakdown'].items():
        print(f"  {indicator}: {data['score']:.3f} - {data.get('signal', 'N/A')}")
