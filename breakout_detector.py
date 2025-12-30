#!/usr/bin/env python3
"""
Breakout/Breakdown Detector - Catch the Exact Moment of Breakout
Identifies when price breaks out of consolidation with volume confirmation
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional


class BreakoutDetector:
    """
    Detects genuine breakouts/breakdowns with volume confirmation
    - Consolidation identification (range-bound price action)
    - Breakout detection (price breaks range)
    - Volume confirmation (breakout volume > average)
    - False breakout filtering (reject weak breakouts)
    """

    def __init__(self):
        self.consolidation_lookback = 30  # Periods to analyze for consolidation
        self.breakout_threshold = 0.02   # 2% beyond range = breakout
        self.volume_multiplier = 1.5     # Breakout volume must be 1.5x average
        print("🚀 Breakout Detector initialized - catching breakouts in real-time")

    def detect_breakout(self, df: pd.DataFrame) -> Dict:
        """
        Main detection function - finds active breakouts/breakdowns
        Returns breakout score, direction, and confidence
        """
        if len(df) < self.consolidation_lookback + 10:
            return {'score': 0, 'reason': 'Insufficient data', 'is_breakout': False}

        # Step 1: Identify if we're in consolidation
        consolidation_result = self._identify_consolidation(df)
        if not consolidation_result['is_consolidating']:
            return {
                'score': 0,
                'reason': 'Not in consolidation',
                'is_breakout': False,
                'consolidation': consolidation_result
            }

        # Step 2: Check if price is breaking out
        breakout_result = self._detect_range_break(df, consolidation_result)
        if not breakout_result['is_breaking']:
            return {
                'score': 0,
                'reason': 'No breakout detected',
                'is_breakout': False,
                'consolidation': consolidation_result,
                'breakout': breakout_result
            }

        # Step 3: Validate with volume confirmation
        volume_result = self._validate_volume(df)
        if not volume_result['is_confirmed']:
            return {
                'score': 0,
                'reason': 'Insufficient volume confirmation',
                'is_breakout': False,
                'consolidation': consolidation_result,
                'breakout': breakout_result,
                'volume': volume_result
            }

        # Step 4: Calculate breakout score
        # Score = consolidation quality * breakout strength * volume confirmation
        breakout_score = (
            consolidation_result['quality'] * 0.3 +
            breakout_result['strength'] * 0.4 +
            volume_result['confirmation_strength'] * 0.3
        )

        return {
            'score': breakout_score,
            'is_breakout': True,
            'direction': breakout_result['direction'],
            'breakout_type': breakout_result['type'],
            'confidence': breakout_score,
            'consolidation': consolidation_result,
            'breakout': breakout_result,
            'volume': volume_result,
            'reason': f"{breakout_result['type']} with {volume_result['volume_ratio']:.1f}x volume"
        }

    def _identify_consolidation(self, df: pd.DataFrame) -> Dict:
        """
        Identify if price is consolidating (range-bound)
        Consolidation = low volatility + horizontal price action
        """
        lookback = self.consolidation_lookback
        recent_data = df.iloc[-lookback:]

        # Calculate range
        high = recent_data['high'].max()
        low = recent_data['low'].min()
        range_size = (high - low) / low

        # Calculate volatility (standard deviation)
        price_std = recent_data['close'].std()
        price_mean = recent_data['close'].mean()
        volatility = price_std / price_mean

        # Consolidation criteria:
        # 1. Range < 8% (tight range)
        # 2. Volatility < 3%
        # 3. Price staying within range (80%+ of candles)
        candles_in_range = 0
        for _, candle in recent_data.iterrows():
            if low * 1.05 <= candle['close'] <= high * 0.95:
                candles_in_range += 1

        range_containment = candles_in_range / len(recent_data)

        # Quality score
        is_consolidating = (
            range_size < 0.08 and           # Range < 8%
            volatility < 0.03 and           # Volatility < 3%
            range_containment > 0.7         # 70%+ candles in range
        )

        # Calculate consolidation quality (0-1)
        quality = min(
            (0.08 - range_size) / 0.08 * 0.4 +
            (0.03 - volatility) / 0.03 * 0.3 +
            range_containment * 0.3,
            1.0
        )

        return {
            'is_consolidating': is_consolidating,
            'quality': quality if is_consolidating else 0,
            'range_high': high,
            'range_low': low,
            'range_size_pct': range_size * 100,
            'volatility_pct': volatility * 100,
            'range_containment_pct': range_containment * 100,
            'consolidation_periods': lookback
        }

    def _detect_range_break(self, df: pd.DataFrame, consolidation: Dict) -> Dict:
        """
        Detect if current price is breaking out of consolidation range
        """
        current_price = df['close'].iloc[-1]
        range_high = consolidation['range_high']
        range_low = consolidation['range_low']

        # Calculate breakout distance
        breakout_threshold_price_high = range_high * (1 + self.breakout_threshold)
        breakout_threshold_price_low = range_low * (1 - self.breakout_threshold)

        # Check for bullish breakout
        if current_price > breakout_threshold_price_high:
            distance_beyond = (current_price - range_high) / range_high
            strength = min(distance_beyond / self.breakout_threshold, 1.0)
            return {
                'is_breaking': True,
                'direction': 'BULLISH',
                'type': 'BREAKOUT',
                'strength': strength,
                'target_price': range_high + (range_high - range_low),  # Measured move
                'distance_beyond_pct': distance_beyond * 100
            }

        # Check for bearish breakdown
        elif current_price < breakout_threshold_price_low:
            distance_beyond = (range_low - current_price) / range_low
            strength = min(distance_beyond / self.breakout_threshold, 1.0)
            return {
                'is_breaking': True,
                'direction': 'BEARISH',
                'type': 'BREAKDOWN',
                'strength': strength,
                'target_price': range_low - (range_high - range_low),  # Measured move
                'distance_beyond_pct': distance_beyond * 100
            }

        else:
            return {
                'is_breaking': False,
                'direction': 'NEUTRAL',
                'type': 'NO_BREAK',
                'strength': 0
            }

    def _validate_volume(self, df: pd.DataFrame) -> Dict:
        """
        Validate breakout with volume confirmation
        Real breakouts have higher volume than consolidation average
        """
        # Current volume
        current_volume = df['volume'].iloc[-1]

        # Average volume during consolidation
        consolidation_volume = df['volume'].iloc[-self.consolidation_lookback:-1].mean()

        # Volume ratio
        volume_ratio = current_volume / (consolidation_volume + 1e-10)

        # Volume confirmation: current volume > 1.5x average
        is_confirmed = volume_ratio >= self.volume_multiplier

        # Confirmation strength (0-1)
        confirmation_strength = min(volume_ratio / (self.volume_multiplier * 2), 1.0)

        return {
            'is_confirmed': is_confirmed,
            'volume_ratio': volume_ratio,
            'confirmation_strength': confirmation_strength,
            'current_volume': current_volume,
            'average_volume': consolidation_volume,
            'required_multiplier': self.volume_multiplier
        }

    def detect_false_breakout(self, df: pd.DataFrame, breakout_candle_index: int = -1) -> bool:
        """
        Detect if a breakout is false (price returns to range quickly)
        Call this 2-3 candles after initial breakout detection
        """
        if len(df) < abs(breakout_candle_index) + 5:
            return False

        breakout_price = df['close'].iloc[breakout_candle_index]
        current_price = df['close'].iloc[-1]

        # If price has retraced 50%+ of breakout move, it's likely false
        recent_high = df['high'].iloc[breakout_candle_index:].max()
        recent_low = df['low'].iloc[breakout_candle_index:].min()

        if breakout_price > df['close'].mean():  # Was bullish breakout
            move_size = recent_high - breakout_price
            retracement = (recent_high - current_price) / move_size if move_size > 0 else 0
            return retracement > 0.5  # Retraced 50%+
        else:  # Was bearish breakdown
            move_size = breakout_price - recent_low
            retracement = (current_price - recent_low) / move_size if move_size > 0 else 0
            return retracement > 0.5  # Retraced 50%+
