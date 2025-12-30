#!/usr/bin/env python3
"""
Anticipatory Signal Detector - Catch Moves BEFORE They Happen
Focuses on accumulation, coiling, and setup patterns rather than momentum that already happened
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
from datetime import datetime


class AnticipatorySignalDetector:
    """
    Detects trading opportunities BEFORE the big move happens
    - Accumulation patterns (volume building, price consolidating)
    - Volatility coiling (BB squeeze, low ATR)
    - Hidden divergences (price vs indicator disagreement)
    - Support/resistance positioning (near bounce zones)
    - Early breakout confirmation (1-3% moves, not 10%+)
    """

    def __init__(self):
        print("🔮 Anticipatory Signal Detector initialized - catching moves BEFORE they happen")

    def detect_pre_breakout_setup(self, df: pd.DataFrame) -> Dict:
        """
        Main detection function - finds setups BEFORE the breakout
        Returns signal strength and direction
        """
        if len(df) < 100:
            return {'score': 0, 'reason': 'Insufficient data'}

        # Run all anticipatory detectors
        accumulation = self._detect_accumulation(df)
        coiling = self._detect_volatility_coiling(df)
        divergence = self._detect_hidden_divergence(df)
        support_resistance = self._detect_support_resistance_proximity(df)
        early_momentum = self._detect_early_momentum(df)

        # Weight anticipatory signals (favor early setups over late momentum)
        total_score = (
            accumulation['score'] * 0.30 +      # Accumulation: 30% (highest)
            coiling['score'] * 0.25 +           # Coiling: 25%
            divergence['score'] * 0.20 +        # Divergence: 20%
            support_resistance['score'] * 0.15 + # S/R proximity: 15%
            early_momentum['score'] * 0.10      # Early momentum: 10% (lowest)
        )

        # Determine direction from components
        bullish_signals = sum([
            1 for x in [accumulation, coiling, divergence, support_resistance, early_momentum]
            if x.get('direction') == 'BULLISH'
        ])
        bearish_signals = sum([
            1 for x in [accumulation, coiling, divergence, support_resistance, early_momentum]
            if x.get('direction') == 'BEARISH'
        ])

        if bullish_signals >= 3:
            direction = 'BULLISH'
        elif bearish_signals >= 3:
            direction = 'BEARISH'
        else:
            direction = 'NEUTRAL'

        # Get primary signal
        signal_scores = {
            'accumulation': accumulation['score'],
            'coiling': coiling['score'],
            'divergence': divergence['score'],
            'support_resistance': support_resistance['score'],
            'early_momentum': early_momentum['score']
        }
        primary_signal = max(signal_scores, key=signal_scores.get)

        return {
            'total_score': total_score,
            'direction': direction,
            'primary_signal': primary_signal,
            'confidence': total_score,
            'breakdown': {
                'accumulation': accumulation,
                'coiling': coiling,
                'divergence': divergence,
                'support_resistance': support_resistance,
                'early_momentum': early_momentum
            },
            'anticipatory': True,  # Flag this as anticipatory (not reactive)
            'reason': f"{primary_signal} setup detected ({direction})"
        }

    def _detect_accumulation(self, df: pd.DataFrame) -> Dict:
        """
        Detect accumulation phase: Volume increasing while price consolidates
        This is the "spring loading" before a move
        """
        # Calculate volume trend (last 20 vs previous 20)
        recent_volume = df['volume'].iloc[-20:].mean()
        previous_volume = df['volume'].iloc[-40:-20].mean()
        volume_increase_ratio = recent_volume / (previous_volume + 1e-6)

        # Calculate price consolidation (low volatility)
        recent_price_std = df['close'].iloc[-20:].std()
        price_mean = df['close'].iloc[-20:].mean()
        consolidation_ratio = recent_price_std / (price_mean + 1e-6)

        # Accumulation = rising volume + flat price
        # High score when volume up 30%+ but price volatility < 2%
        volume_score = min((volume_increase_ratio - 1.0) / 0.5, 1.0)  # Normalize 1.3x = score 0.6
        consolidation_score = max(0, 1.0 - (consolidation_ratio / 0.02))  # < 2% volatility = high score

        # Combined accumulation score
        accumulation_score = (volume_score * 0.6 + consolidation_score * 0.4)

        # Determine direction from price position in consolidation
        sma_20 = df['close'].rolling(window=20).mean().iloc[-1]
        current_price = df['close'].iloc[-1]
        if current_price > sma_20:
            direction = 'BULLISH'
        else:
            direction = 'BEARISH'

        return {
            'score': max(0, accumulation_score),
            'volume_increase': volume_increase_ratio,
            'consolidation_level': consolidation_ratio,
            'direction': direction,
            'signal': 'ACCUMULATION' if accumulation_score > 0.6 else 'WEAK'
        }

    def _detect_volatility_coiling(self, df: pd.DataFrame) -> Dict:
        """
        Detect volatility compression (coiling spring)
        Low ATR + tight BB = explosive move imminent
        """
        # Calculate ATR (Average True Range)
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = ranges.max(axis=1)
        atr = true_range.rolling(14).mean()

        # Current ATR vs historical ATR
        current_atr = atr.iloc[-1]
        avg_atr = atr.iloc[-50:-1].mean() if len(atr) > 50 else current_atr
        atr_ratio = current_atr / (avg_atr + 1e-6)

        # Bollinger Band width
        sma_20 = df['close'].rolling(window=20).mean()
        std_20 = df['close'].rolling(window=20).std()
        bb_width = (std_20.iloc[-1] * 4) / (sma_20.iloc[-1] + 1e-6)
        avg_bb_width = ((std_20.iloc[-50:-1] * 4) / (sma_20.iloc[-50:-1] + 1e-6)).mean()
        bb_ratio = bb_width / (avg_bb_width + 1e-6)

        # Coiling score: Low ATR + tight BB = high score
        coiling_score = (1.0 - atr_ratio) * 0.5 + (1.0 - bb_ratio) * 0.5
        coiling_score = max(0, min(coiling_score, 1.0))

        # Direction from price position in BB
        upper_band = sma_20.iloc[-1] + (2 * std_20.iloc[-1])
        lower_band = sma_20.iloc[-1] - (2 * std_20.iloc[-1])
        current_price = df['close'].iloc[-1]

        if current_price > sma_20.iloc[-1]:
            direction = 'BULLISH'
        else:
            direction = 'BEARISH'

        return {
            'score': coiling_score,
            'atr_ratio': atr_ratio,
            'bb_ratio': bb_ratio,
            'direction': direction,
            'signal': 'COILING' if coiling_score > 0.7 else 'NORMAL'
        }

    def _detect_hidden_divergence(self, df: pd.DataFrame) -> Dict:
        """
        Detect hidden bullish/bearish divergence
        Bullish: Price makes higher low, RSI makes lower low (continuation)
        Bearish: Price makes lower high, RSI makes higher high (continuation)
        """
        # Calculate RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=14).mean()
        loss = -delta.where(delta < 0, 0).rolling(window=14).mean()
        rs = gain / (loss + 1e-6)
        rsi = 100 - (100 / (1 + rs))

        # Find recent swing points (last 30 periods)
        recent_df = df.iloc[-30:].copy()
        recent_rsi = rsi.iloc[-30:]

        # Find local lows and highs
        price_lows = recent_df['close'].rolling(5, center=True).min() == recent_df['close']
        price_highs = recent_df['close'].rolling(5, center=True).max() == recent_df['close']

        # Get last 2 swing lows/highs
        low_indices = np.where(price_lows)[0]
        high_indices = np.where(price_highs)[0]

        divergence_score = 0
        direction = 'NEUTRAL'
        signal = 'NO_DIVERGENCE'

        # Hidden bullish divergence (price higher low, RSI lower low)
        if len(low_indices) >= 2:
            last_low_idx = low_indices[-1]
            prev_low_idx = low_indices[-2]

            price_last_low = recent_df['close'].iloc[last_low_idx]
            price_prev_low = recent_df['close'].iloc[prev_low_idx]
            rsi_last_low = recent_rsi.iloc[last_low_idx]
            rsi_prev_low = recent_rsi.iloc[prev_low_idx]

            if price_last_low > price_prev_low and rsi_last_low < rsi_prev_low:
                divergence_score = 0.8
                direction = 'BULLISH'
                signal = 'HIDDEN_BULLISH_DIVERGENCE'

        # Hidden bearish divergence (price lower high, RSI higher high)
        if len(high_indices) >= 2:
            last_high_idx = high_indices[-1]
            prev_high_idx = high_indices[-2]

            price_last_high = recent_df['close'].iloc[last_high_idx]
            price_prev_high = recent_df['close'].iloc[prev_high_idx]
            rsi_last_high = recent_rsi.iloc[last_high_idx]
            rsi_prev_high = recent_rsi.iloc[prev_high_idx]

            if price_last_high < price_prev_high and rsi_last_high > rsi_prev_high:
                divergence_score = 0.8
                direction = 'BEARISH'
                signal = 'HIDDEN_BEARISH_DIVERGENCE'

        return {
            'score': divergence_score,
            'direction': direction,
            'signal': signal
        }

    def _detect_support_resistance_proximity(self, df: pd.DataFrame) -> Dict:
        """
        Detect if price is near support (bullish) or resistance (bearish)
        Near = within 2% of level
        """
        # Identify key levels from recent history (50 periods)
        recent_highs = df['high'].iloc[-50:]
        recent_lows = df['low'].iloc[-50:]

        # Find major resistance (most touched high level)
        resistance_level = recent_highs.quantile(0.95)

        # Find major support (most touched low level)
        support_level = recent_lows.quantile(0.05)

        current_price = df['close'].iloc[-1]

        # Calculate distance to levels
        dist_to_support = abs(current_price - support_level) / support_level
        dist_to_resistance = abs(current_price - resistance_level) / resistance_level

        # Score based on proximity (< 2% = high score)
        if dist_to_support < 0.02:
            score = 1.0 - (dist_to_support / 0.02)
            direction = 'BULLISH'
            signal = 'NEAR_SUPPORT'
        elif dist_to_resistance < 0.02:
            score = 1.0 - (dist_to_resistance / 0.02)
            direction = 'BEARISH'
            signal = 'NEAR_RESISTANCE'
        else:
            score = 0
            direction = 'NEUTRAL'
            signal = 'MID_RANGE'

        return {
            'score': score,
            'support_level': support_level,
            'resistance_level': resistance_level,
            'distance_to_support': dist_to_support,
            'distance_to_resistance': dist_to_resistance,
            'direction': direction,
            'signal': signal
        }

    def _detect_early_momentum(self, df: pd.DataFrame) -> Dict:
        """
        Detect EARLY momentum (1-3% moves) not late momentum (10%+ moves)
        This catches the start of the move, not the end
        """
        # Calculate recent price change
        price_1h = df['close'].iloc[-12] if len(df) > 12 else df['close'].iloc[0]
        price_4h = df['close'].iloc[-48] if len(df) > 48 else df['close'].iloc[0]
        current_price = df['close'].iloc[-1]

        change_1h = ((current_price - price_1h) / price_1h) * 100
        change_4h = ((current_price - price_4h) / price_4h) * 100

        # Score: HIGH for 1-5% moves, LOW for 0% or 10%+ moves
        # This is the OPPOSITE of traditional momentum
        abs_change = abs(change_1h)

        if 1.0 <= abs_change <= 5.0:
            # Sweet spot - early move
            score = min((abs_change - 1.0) / 4.0 + 0.5, 1.0)
            signal = 'EARLY_MOMENTUM'
        elif abs_change < 1.0:
            # Too early, no confirmation
            score = abs_change / 2.0
            signal = 'NO_MOMENTUM'
        else:
            # Too late, move already happened
            score = max(0, 1.0 - (abs_change - 5.0) / 10.0)
            signal = 'LATE_MOMENTUM'

        direction = 'BULLISH' if change_1h > 0 else 'BEARISH'

        return {
            'score': score,
            'change_1h': change_1h,
            'change_4h': change_4h,
            'direction': direction,
            'signal': signal
        }
