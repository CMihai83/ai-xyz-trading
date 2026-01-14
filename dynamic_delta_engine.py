#!/usr/bin/env python3
"""
Dynamic Delta Engine - Multi-Timeframe S/R & Regime-Aware Delta Calculation
===========================================================================

Sprint 14: Replaces fixed delta with dynamic calculation based on:
1. Multi-timeframe Support/Resistance levels (1h, 4h, 1d)
2. Market regime detection (trending/ranging/volatile/extreme)
3. Consecutive candle analysis for correction probability
4. Historical correction depth per symbol
5. Extreme market expansion (instead of stop-loss)

Core Philosophy (User Vision):
- "Stop loss is final, positions can recover"
- "In extreme markets, EXPAND delta to give room for market to calm"
- "Delta should represent the EXPECTED REVERSAL ZONE"

Author: Claude + Grok Consortium
Version: 1.0.0 (Sprint 14)
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import time


@dataclass
class MarketRegime:
    """Market regime classification"""
    regime: str  # 'trending', 'ranging', 'volatile', 'extreme'
    adx_value: float
    rsi_value: float
    consecutive_candles: int  # Negative for bearish, positive for bullish
    atr_ratio: float  # Current ATR / Average ATR
    confidence: float  # 0-1 confidence in regime classification


@dataclass
class SupportResistance:
    """Support/Resistance level"""
    price: float
    strength: float  # 0-1 based on touch count and timeframe
    timeframe: str
    level_type: str  # 'support' or 'resistance'
    touches: int


@dataclass
class DynamicDeltaResult:
    """Result of dynamic delta calculation"""
    delta_pct: float  # Percentage delta from entry
    delta_price: float  # Absolute price delta
    regime: MarketRegime
    nearest_support: Optional[SupportResistance]
    nearest_resistance: Optional[SupportResistance]
    averaging_levels: List[float]  # Price levels for each averaging step
    expansion_multiplier: float  # 1.0 normal, >1.0 in extreme markets
    correction_probability: float  # Estimated probability of reversal
    reasoning: str


class DynamicDeltaEngine:
    """
    Calculates dynamic delta for Fibonacci averaging based on market conditions.

    Key Features:
    - Multi-timeframe S/R analysis (1h, 4h, 1d)
    - Market regime detection (ADX, RSI, consecutive candles)
    - Extreme market expansion (no stop-loss, expand delta instead)
    - Correction probability estimation
    """

    # Base delta parameters
    BASE_DELTA_PCT = 0.05  # 5% base delta
    MIN_DELTA_PCT = 0.02   # 2% minimum delta
    MAX_DELTA_PCT = 0.25   # 25% maximum delta (extreme expansion)

    # Market regime thresholds
    ADX_TRENDING_THRESHOLD = 25  # ADX > 25 = trending
    ADX_RANGING_THRESHOLD = 20   # ADX < 20 = ranging
    RSI_OVERSOLD = 25            # Grok V2: Tightened from 30
    RSI_OVERBOUGHT = 75          # Grok V2: Tightened from 70
    RSI_EXTREME_OVERSOLD = 15
    RSI_EXTREME_OVERBOUGHT = 85

    # Consecutive candle thresholds
    CONSECUTIVE_MODERATE = 3     # 3+ candles = moderate trend
    CONSECUTIVE_STRONG = 5       # 5+ candles = strong trend
    CONSECUTIVE_EXTREME = 7      # 7+ candles = extreme, expect reversal

    # ATR ratio thresholds for volatility
    ATR_NORMAL = 1.0
    ATR_ELEVATED = 1.5
    ATR_HIGH = 2.0
    ATR_EXTREME = 3.0

    # Delta multipliers by regime
    REGIME_MULTIPLIERS = {
        'ranging': 0.8,      # Tighter delta in ranging markets
        'trending': 1.0,     # Normal delta in trends
        'volatile': 1.5,     # Wider delta in volatile markets
        'extreme': 2.5       # Much wider delta in extreme conditions
    }

    # Timeframe weights for S/R
    TIMEFRAME_WEIGHTS = {
        '1h': 0.2,
        '4h': 0.3,
        '1d': 0.5
    }

    def __init__(self, exchange):
        """
        Initialize DynamicDeltaEngine.

        Args:
            exchange: CCXT exchange instance
        """
        self.exchange = exchange
        self.sr_cache = {}  # Cache S/R levels
        self.regime_cache = {}  # Cache regime detection
        self.cache_ttl = 300  # 5 minute cache

        # Historical correction data per symbol
        self.correction_history = {}

    def calculate_dynamic_delta(
        self,
        symbol: str,
        entry_price: float,
        direction: str,  # 'long' or 'short'
        num_steps: int = 5
    ) -> DynamicDeltaResult:
        """
        Calculate dynamic delta based on current market conditions.

        Args:
            symbol: Trading symbol
            entry_price: Position entry price
            direction: 'long' or 'short'
            num_steps: Number of averaging steps (default 5)

        Returns:
            DynamicDeltaResult with delta and averaging levels
        """
        # 1. Detect market regime
        regime = self.detect_market_regime(symbol)

        # 2. Find S/R levels
        supports, resistances = self.find_sr_levels(symbol, entry_price)

        # 3. Find nearest relevant S/R
        if direction == 'long':
            # For longs, we care about support below entry
            nearest_support = self._find_nearest_level(supports, entry_price, 'below')
            nearest_resistance = self._find_nearest_level(resistances, entry_price, 'above')
        else:
            # For shorts, we care about resistance above entry
            nearest_support = self._find_nearest_level(supports, entry_price, 'below')
            nearest_resistance = self._find_nearest_level(resistances, entry_price, 'above')

        # 4. Calculate base delta from S/R distance
        sr_delta = self._calculate_sr_based_delta(
            entry_price, direction, nearest_support, nearest_resistance
        )

        # 5. Apply regime multiplier
        regime_multiplier = self.REGIME_MULTIPLIERS.get(regime.regime, 1.0)

        # 6. Apply ATR-based volatility adjustment
        atr_multiplier = min(regime.atr_ratio, self.ATR_EXTREME) / self.ATR_NORMAL

        # 7. Apply consecutive candle adjustment
        candle_multiplier = self._get_candle_multiplier(regime.consecutive_candles, direction)

        # 8. Calculate expansion multiplier for extreme markets
        expansion_multiplier = self._calculate_expansion_multiplier(regime)

        # 9. Calculate final delta
        final_delta_pct = (
            sr_delta *
            regime_multiplier *
            atr_multiplier *
            candle_multiplier *
            expansion_multiplier
        )

        # Clamp to min/max
        final_delta_pct = max(self.MIN_DELTA_PCT, min(final_delta_pct, self.MAX_DELTA_PCT))

        # 10. Calculate averaging levels using Fibonacci distribution
        averaging_levels = self._calculate_averaging_levels(
            entry_price, final_delta_pct, direction, num_steps
        )

        # 11. Estimate correction probability
        correction_prob = self._estimate_correction_probability(regime, direction)

        # Build reasoning string
        reasoning = self._build_reasoning(
            regime, sr_delta, regime_multiplier, atr_multiplier,
            candle_multiplier, expansion_multiplier, final_delta_pct
        )

        return DynamicDeltaResult(
            delta_pct=final_delta_pct,
            delta_price=entry_price * final_delta_pct,
            regime=regime,
            nearest_support=nearest_support,
            nearest_resistance=nearest_resistance,
            averaging_levels=averaging_levels,
            expansion_multiplier=expansion_multiplier,
            correction_probability=correction_prob,
            reasoning=reasoning
        )

    def detect_market_regime(self, symbol: str) -> MarketRegime:
        """
        Detect current market regime using multiple indicators.

        Returns:
            MarketRegime with classification and metrics
        """
        cache_key = f"{symbol}_regime"
        if cache_key in self.regime_cache:
            cached = self.regime_cache[cache_key]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                return cached['regime']

        try:
            # Fetch OHLCV data (1h for indicators)
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=50)
            if len(ohlcv) < 30:
                return MarketRegime('ranging', 0, 50, 0, 1.0, 0.5)

            closes = [c[4] for c in ohlcv]
            highs = [c[2] for c in ohlcv]
            lows = [c[3] for c in ohlcv]

            # Calculate ADX
            adx = self._calculate_adx(highs, lows, closes, 14)

            # Calculate RSI
            rsi = self._calculate_rsi(closes, 14)

            # Count consecutive candles
            consecutive = self._count_consecutive_candles(closes)

            # Calculate ATR ratio
            atr_14 = self._calculate_atr(highs, lows, closes, 14)
            atr_50 = self._calculate_atr(highs, lows, closes, min(50, len(closes)-1))
            atr_ratio = atr_14 / atr_50 if atr_50 > 0 else 1.0

            # Classify regime
            regime, confidence = self._classify_regime(adx, rsi, consecutive, atr_ratio)

            result = MarketRegime(
                regime=regime,
                adx_value=adx,
                rsi_value=rsi,
                consecutive_candles=consecutive,
                atr_ratio=atr_ratio,
                confidence=confidence
            )

            # Cache result
            self.regime_cache[cache_key] = {
                'regime': result,
                'timestamp': time.time()
            }

            return result

        except Exception as e:
            print(f"  Error detecting regime for {symbol}: {e}")
            return MarketRegime('ranging', 0, 50, 0, 1.0, 0.5)

    def find_sr_levels(
        self,
        symbol: str,
        current_price: float
    ) -> Tuple[List[SupportResistance], List[SupportResistance]]:
        """
        Find support and resistance levels across multiple timeframes.

        Returns:
            Tuple of (supports, resistances) lists
        """
        cache_key = f"{symbol}_sr"
        if cache_key in self.sr_cache:
            cached = self.sr_cache[cache_key]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                return cached['supports'], cached['resistances']

        supports = []
        resistances = []

        for timeframe, weight in self.TIMEFRAME_WEIGHTS.items():
            try:
                tf_supports, tf_resistances = self._find_sr_for_timeframe(
                    symbol, timeframe, current_price, weight
                )
                supports.extend(tf_supports)
                resistances.extend(tf_resistances)
            except Exception as e:
                print(f"  Error finding S/R for {symbol} {timeframe}: {e}")

        # Sort by strength (strongest first)
        supports.sort(key=lambda x: x.strength, reverse=True)
        resistances.sort(key=lambda x: x.strength, reverse=True)

        # Cache results
        self.sr_cache[cache_key] = {
            'supports': supports,
            'resistances': resistances,
            'timestamp': time.time()
        }

        return supports, resistances

    def _find_sr_for_timeframe(
        self,
        symbol: str,
        timeframe: str,
        current_price: float,
        weight: float
    ) -> Tuple[List[SupportResistance], List[SupportResistance]]:
        """Find S/R levels for a specific timeframe using pivot points and swing highs/lows."""
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        if len(ohlcv) < 20:
            return [], []

        highs = [c[2] for c in ohlcv]
        lows = [c[3] for c in ohlcv]
        closes = [c[4] for c in ohlcv]

        supports = []
        resistances = []

        # Find swing lows (supports)
        for i in range(2, len(lows) - 2):
            if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
               lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                # Count how many times price touched this level
                touches = sum(1 for low in lows if abs(low - lows[i]) / lows[i] < 0.01)
                supports.append(SupportResistance(
                    price=lows[i],
                    strength=min(touches / 5, 1.0) * weight,
                    timeframe=timeframe,
                    level_type='support',
                    touches=touches
                ))

        # Find swing highs (resistances)
        for i in range(2, len(highs) - 2):
            if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
               highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                touches = sum(1 for high in highs if abs(high - highs[i]) / highs[i] < 0.01)
                resistances.append(SupportResistance(
                    price=highs[i],
                    strength=min(touches / 5, 1.0) * weight,
                    timeframe=timeframe,
                    level_type='resistance',
                    touches=touches
                ))

        # Add recent significant lows/highs
        recent_low = min(lows[-20:])
        recent_high = max(highs[-20:])

        supports.append(SupportResistance(
            price=recent_low,
            strength=0.5 * weight,
            timeframe=timeframe,
            level_type='support',
            touches=1
        ))

        resistances.append(SupportResistance(
            price=recent_high,
            strength=0.5 * weight,
            timeframe=timeframe,
            level_type='resistance',
            touches=1
        ))

        return supports, resistances

    def _find_nearest_level(
        self,
        levels: List[SupportResistance],
        price: float,
        direction: str  # 'above' or 'below'
    ) -> Optional[SupportResistance]:
        """Find the nearest S/R level in the specified direction."""
        if not levels:
            return None

        if direction == 'below':
            below_levels = [l for l in levels if l.price < price]
            if not below_levels:
                return None
            return max(below_levels, key=lambda x: x.price)
        else:
            above_levels = [l for l in levels if l.price > price]
            if not above_levels:
                return None
            return min(above_levels, key=lambda x: x.price)

    def _calculate_sr_based_delta(
        self,
        entry_price: float,
        direction: str,
        nearest_support: Optional[SupportResistance],
        nearest_resistance: Optional[SupportResistance]
    ) -> float:
        """Calculate base delta based on distance to nearest S/R."""
        if direction == 'long' and nearest_support:
            # For longs, delta should cover the distance to support
            distance = (entry_price - nearest_support.price) / entry_price
            # Add 20% buffer beyond support
            return max(distance * 1.2, self.BASE_DELTA_PCT)
        elif direction == 'short' and nearest_resistance:
            # For shorts, delta should cover distance to resistance
            distance = (nearest_resistance.price - entry_price) / entry_price
            return max(distance * 1.2, self.BASE_DELTA_PCT)
        else:
            return self.BASE_DELTA_PCT

    def _calculate_expansion_multiplier(self, regime: MarketRegime) -> float:
        """
        Calculate delta expansion multiplier for extreme markets.

        Instead of stop-loss, we EXPAND delta to give room for market to calm.
        """
        multiplier = 1.0

        # Extreme RSI conditions
        if regime.rsi_value < self.RSI_EXTREME_OVERSOLD or regime.rsi_value > self.RSI_EXTREME_OVERBOUGHT:
            multiplier *= 1.5

        # Extreme consecutive candles (7+)
        if abs(regime.consecutive_candles) >= self.CONSECUTIVE_EXTREME:
            multiplier *= 1.5

        # Extreme ATR ratio
        if regime.atr_ratio >= self.ATR_EXTREME:
            multiplier *= 1.5

        # Cap at 2.5x expansion
        return min(multiplier, 2.5)

    def _get_candle_multiplier(self, consecutive: int, direction: str) -> float:
        """
        Get delta multiplier based on consecutive candles.

        If price has moved many candles against position, expect reversal soon
        -> can use tighter delta. If moving WITH position, use wider delta.
        """
        is_bearish = consecutive < 0
        abs_consecutive = abs(consecutive)

        # Position is long
        if direction == 'long':
            if is_bearish:  # Bearish candles against long position
                if abs_consecutive >= self.CONSECUTIVE_EXTREME:
                    return 0.8  # Tighter delta - reversal expected
                elif abs_consecutive >= self.CONSECUTIVE_STRONG:
                    return 0.9
                else:
                    return 1.0
            else:  # Bullish candles with long position
                return 1.0  # Normal delta
        else:  # Position is short
            if not is_bearish:  # Bullish candles against short position
                if abs_consecutive >= self.CONSECUTIVE_EXTREME:
                    return 0.8  # Tighter delta - reversal expected
                elif abs_consecutive >= self.CONSECUTIVE_STRONG:
                    return 0.9
                else:
                    return 1.0
            else:  # Bearish candles with short position
                return 1.0

    def _calculate_averaging_levels(
        self,
        entry_price: float,
        delta_pct: float,
        direction: str,
        num_steps: int
    ) -> List[float]:
        """
        Calculate price levels for each averaging step using Fibonacci distribution.

        Uses golden ratio to distribute steps across the delta range.
        """
        # Fibonacci percentages for step distribution
        fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0][:num_steps]

        levels = []
        for ratio in fib_ratios:
            if direction == 'long':
                # For longs, averaging levels are below entry
                level = entry_price * (1 - delta_pct * ratio)
            else:
                # For shorts, averaging levels are above entry
                level = entry_price * (1 + delta_pct * ratio)
            levels.append(level)

        return levels

    def _estimate_correction_probability(
        self,
        regime: MarketRegime,
        direction: str
    ) -> float:
        """
        Estimate probability of price correcting favorably.

        Higher probability in extreme conditions (mean reversion).
        """
        prob = 0.5  # Base probability

        # Extreme RSI increases reversal probability
        if direction == 'long' and regime.rsi_value < self.RSI_EXTREME_OVERSOLD:
            prob += 0.25
        elif direction == 'short' and regime.rsi_value > self.RSI_EXTREME_OVERBOUGHT:
            prob += 0.25
        elif direction == 'long' and regime.rsi_value < self.RSI_OVERSOLD:
            prob += 0.15
        elif direction == 'short' and regime.rsi_value > self.RSI_OVERBOUGHT:
            prob += 0.15

        # Extreme consecutive candles increase reversal probability
        is_bearish = regime.consecutive_candles < 0
        abs_consecutive = abs(regime.consecutive_candles)

        if direction == 'long' and is_bearish:
            if abs_consecutive >= self.CONSECUTIVE_EXTREME:
                prob += 0.20
            elif abs_consecutive >= self.CONSECUTIVE_STRONG:
                prob += 0.10
        elif direction == 'short' and not is_bearish:
            if abs_consecutive >= self.CONSECUTIVE_EXTREME:
                prob += 0.20
            elif abs_consecutive >= self.CONSECUTIVE_STRONG:
                prob += 0.10

        return min(prob, 0.95)

    def _classify_regime(
        self,
        adx: float,
        rsi: float,
        consecutive: int,
        atr_ratio: float
    ) -> Tuple[str, float]:
        """Classify market regime based on indicators."""
        # Check for extreme conditions first
        extreme_count = 0
        if rsi < self.RSI_EXTREME_OVERSOLD or rsi > self.RSI_EXTREME_OVERBOUGHT:
            extreme_count += 1
        if abs(consecutive) >= self.CONSECUTIVE_EXTREME:
            extreme_count += 1
        if atr_ratio >= self.ATR_EXTREME:
            extreme_count += 1

        if extreme_count >= 2:
            return 'extreme', 0.9

        # Check for high volatility
        if atr_ratio >= self.ATR_HIGH:
            return 'volatile', 0.8

        # Check for trending
        if adx > self.ADX_TRENDING_THRESHOLD:
            return 'trending', 0.85

        # Default to ranging
        if adx < self.ADX_RANGING_THRESHOLD:
            return 'ranging', 0.75

        return 'trending', 0.6

    def _calculate_adx(self, highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
        """Calculate Average Directional Index."""
        if len(closes) < period + 1:
            return 0

        plus_dm = []
        minus_dm = []
        tr = []

        for i in range(1, len(closes)):
            high_diff = highs[i] - highs[i-1]
            low_diff = lows[i-1] - lows[i]

            plus_dm.append(high_diff if high_diff > low_diff and high_diff > 0 else 0)
            minus_dm.append(low_diff if low_diff > high_diff and low_diff > 0 else 0)

            tr_val = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            tr.append(tr_val)

        if len(tr) < period:
            return 0

        # Smoothed averages
        atr = sum(tr[-period:]) / period
        plus_di = (sum(plus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0
        minus_di = (sum(minus_dm[-period:]) / period) / atr * 100 if atr > 0 else 0

        dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) > 0 else 0

        return dx

    def _calculate_rsi(self, closes: List[float], period: int) -> float:
        """Calculate Relative Strength Index."""
        if len(closes) < period + 1:
            return 50

        gains = []
        losses = []

        for i in range(1, len(closes)):
            change = closes[i] - closes[i-1]
            gains.append(change if change > 0 else 0)
            losses.append(abs(change) if change < 0 else 0)

        if len(gains) < period:
            return 50

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_atr(self, highs: List[float], lows: List[float], closes: List[float], period: int) -> float:
        """Calculate Average True Range."""
        if len(closes) < period + 1:
            return 0

        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)

        return sum(trs[-period:]) / period if len(trs) >= period else 0

    def _count_consecutive_candles(self, closes: List[float]) -> int:
        """
        Count consecutive candles in same direction.

        Returns negative for bearish, positive for bullish.
        """
        if len(closes) < 2:
            return 0

        count = 0
        direction = None

        for i in range(len(closes) - 1, 0, -1):
            change = closes[i] - closes[i-1]
            current_dir = 'up' if change > 0 else 'down'

            if direction is None:
                direction = current_dir
                count = 1 if current_dir == 'up' else -1
            elif current_dir == direction:
                count += 1 if direction == 'up' else -1
            else:
                break

        return count

    def _build_reasoning(
        self,
        regime: MarketRegime,
        sr_delta: float,
        regime_mult: float,
        atr_mult: float,
        candle_mult: float,
        expansion_mult: float,
        final_delta: float
    ) -> str:
        """Build human-readable reasoning string."""
        parts = [
            f"Regime: {regime.regime} (ADX={regime.adx_value:.1f}, RSI={regime.rsi_value:.1f})",
            f"Consecutive candles: {regime.consecutive_candles}",
            f"ATR ratio: {regime.atr_ratio:.2f}x",
            f"S/R delta: {sr_delta*100:.1f}%",
            f"Multipliers: regime={regime_mult:.2f}x, ATR={atr_mult:.2f}x, candle={candle_mult:.2f}x",
        ]

        if expansion_mult > 1.0:
            parts.append(f"EXTREME EXPANSION: {expansion_mult:.2f}x")

        parts.append(f"Final delta: {final_delta*100:.1f}%")

        return " | ".join(parts)


# Module test
if __name__ == "__main__":
    print("DynamicDeltaEngine V1.0.0 - Multi-TF S/R & Regime-Aware Delta")
    print("Features:")
    print("  - Multi-timeframe S/R analysis (1h, 4h, 1d)")
    print("  - Market regime detection (trending/ranging/volatile/extreme)")
    print("  - Consecutive candle analysis")
    print("  - Extreme market expansion (no stop-loss)")
    print("  - Correction probability estimation")
