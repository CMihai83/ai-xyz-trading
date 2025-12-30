#!/usr/bin/env python3
"""
Dynamic Pattern Averaging Plugin
Analyzes historical patterns to determine optimal averaging levels
"""

import json
import logging
import numpy as np
from collections import deque
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass

from plugin_interface import (
    AveragingPlugin,
    Signal,
    SignalAction,
    MarketData
)

logger = logging.getLogger(__name__)


@dataclass
class Trend:
    """Represents a price trend"""
    direction: str  # 'up' or 'down'
    start_index: int
    end_index: int
    candle_count: int
    individual_deltas: List[float]
    total_delta: float
    start_price: float
    end_price: float


@dataclass
class AdverseMovementStats:
    """Statistics about adverse price movements"""
    timeframe: str
    sample_count: int
    adverse_moves: Dict[str, float]  # min, avg, max, p25, p50, p75, p95
    corrections: Dict[str, float]
    correction_ratios: Dict[str, float]
    avg_candles_to_correction: float


class CandleManager:
    """Manages candle data buffers for multiple timeframes"""

    def __init__(self, buffer_size: int = 2000):
        """Initialize candle buffers"""
        self.buffer_size = buffer_size
        self.buffers = {
            '1m': deque(maxlen=buffer_size),
            '5m': deque(maxlen=buffer_size),
            '15m': deque(maxlen=buffer_size),
            '1h': deque(maxlen=buffer_size),
            '4h': deque(maxlen=buffer_size),
            '1d': deque(maxlen=buffer_size)
        }
        self.last_update = {}

    def add_candle(self, timeframe: str, candle: Dict):
        """Add a candle to the buffer"""
        if timeframe in self.buffers:
            self.buffers[timeframe].append(candle)
            self.last_update[timeframe] = datetime.now()

    def get_candles(self, timeframe: str, count: Optional[int] = None) -> List[Dict]:
        """Get candles from buffer"""
        if timeframe not in self.buffers:
            return []

        buffer = self.buffers[timeframe]
        if count is None:
            return list(buffer)
        return list(buffer)[-count:]

    def aggregate_candles(self, source_tf: str, target_tf: str):
        """Aggregate lower timeframe candles to higher timeframe"""
        # Simplified aggregation logic
        # In production, this would properly aggregate based on time boundaries
        pass


class PatternAnalyzer:
    """Analyzes price patterns for averaging opportunities"""

    def __init__(self):
        """Initialize pattern analyzer"""
        self.min_trend_candles = 2
        self.price_change_threshold = 0.0001  # 0.01% to filter noise

    def detect_trends(self, candles: List[Dict]) -> List[Trend]:
        """Detect trends in candle data"""
        if len(candles) < self.min_trend_candles:
            return []

        trends = []
        current_trend = None
        trend_start = 0

        for i in range(1, len(candles)):
            prev_close = candles[i-1].get('close', 0)
            curr_close = candles[i].get('close', 0)

            if prev_close == 0:
                continue

            change = (curr_close - prev_close) / prev_close

            # Determine direction
            if abs(change) < self.price_change_threshold:
                # Flat, end current trend if exists
                if current_trend:
                    self._finalize_trend(trends, current_trend, candles, trend_start, i-1)
                    current_trend = None
            else:
                direction = 'up' if change > 0 else 'down'

                if current_trend == direction:
                    # Continue trend
                    pass
                else:
                    # Direction changed, finalize previous trend
                    if current_trend and i - trend_start >= self.min_trend_candles:
                        self._finalize_trend(trends, current_trend, candles, trend_start, i-1)

                    # Start new trend
                    current_trend = direction
                    trend_start = i - 1

        # Finalize last trend
        if current_trend and len(candles) - trend_start >= self.min_trend_candles:
            self._finalize_trend(trends, current_trend, candles, trend_start, len(candles)-1)

        return trends

    def _finalize_trend(self, trends: List[Trend], direction: str,
                        candles: List[Dict], start: int, end: int):
        """Finalize and add a trend to the list"""
        individual_deltas = []

        for i in range(start + 1, end + 1):
            delta = candles[i]['close'] - candles[i-1]['close']
            individual_deltas.append(delta)

        trend = Trend(
            direction=direction,
            start_index=start,
            end_index=end,
            candle_count=end - start + 1,
            individual_deltas=individual_deltas,
            total_delta=candles[end]['close'] - candles[start]['close'],
            start_price=candles[start]['close'],
            end_price=candles[end]['close']
        )

        trends.append(trend)

    def analyze_adverse_movements(self, trends: List[Trend],
                                 position_side: str) -> AdverseMovementStats:
        """Analyze adverse price movements and corrections"""
        adverse_moves = []
        corrections = []

        # Identify adverse trends based on position side
        adverse_direction = 'down' if position_side == 'buy' else 'up'

        for i, trend in enumerate(trends):
            if trend.direction == adverse_direction:
                # This is an adverse movement
                adverse_move = abs(trend.total_delta / trend.start_price)
                adverse_moves.append(adverse_move)

                # Look for correction after this adverse move
                if i + 1 < len(trends):
                    next_trend = trends[i + 1]
                    if next_trend.direction != adverse_direction:
                        correction = abs(next_trend.total_delta / next_trend.start_price)
                        corrections.append(correction)

        # Calculate statistics
        if not adverse_moves:
            return self._empty_stats()

        stats = AdverseMovementStats(
            timeframe='mixed',
            sample_count=len(adverse_moves),
            adverse_moves=self._calculate_percentiles(adverse_moves),
            corrections=self._calculate_percentiles(corrections) if corrections else {},
            correction_ratios=self._calculate_correction_ratios(adverse_moves, corrections),
            avg_candles_to_correction=self._avg_candles_to_correction(trends, adverse_direction)
        )

        return stats

    def _calculate_percentiles(self, values: List[float]) -> Dict[str, float]:
        """Calculate statistical percentiles"""
        if not values:
            return {}

        arr = np.array(values)
        return {
            'min': float(np.min(arr)),
            'avg': float(np.mean(arr)),
            'max': float(np.max(arr)),
            'p25': float(np.percentile(arr, 25)),
            'p50': float(np.percentile(arr, 50)),
            'p75': float(np.percentile(arr, 75)),
            'p95': float(np.percentile(arr, 95))
        }

    def _calculate_correction_ratios(self, adverse: List[float],
                                    corrections: List[float]) -> Dict[str, float]:
        """Calculate correction to adverse move ratios"""
        if not corrections or not adverse:
            return {}

        ratios = []
        for i in range(min(len(adverse), len(corrections))):
            if adverse[i] > 0:
                ratios.append(corrections[i] / adverse[i])

        return self._calculate_percentiles(ratios) if ratios else {}

    def _avg_candles_to_correction(self, trends: List[Trend],
                                  adverse_direction: str) -> float:
        """Calculate average candles to correction"""
        candle_counts = []

        for i, trend in enumerate(trends):
            if trend.direction == adverse_direction and i + 1 < len(trends):
                candle_counts.append(trend.candle_count)

        return np.mean(candle_counts) if candle_counts else 0.0

    def _empty_stats(self) -> AdverseMovementStats:
        """Return empty statistics"""
        return AdverseMovementStats(
            timeframe='mixed',
            sample_count=0,
            adverse_moves={},
            corrections={},
            correction_ratios={},
            avg_candles_to_correction=0.0
        )


class DynamicPatternPlugin(AveragingPlugin):
    """
    Dynamic pattern-based averaging strategy
    Analyzes historical patterns to determine optimal averaging levels
    """

    def __init__(self, config: Dict = None):
        """Initialize dynamic pattern plugin"""
        super().__init__(config)

        self.candle_manager = CandleManager()
        self.pattern_analyzer = PatternAnalyzer()

        # Risk tolerance levels
        self.risk_tolerance = config.get('risk_tolerance', 'moderate') if config else 'moderate'

        # Averaging level percentiles based on risk tolerance
        self.level_percentiles = {
            'conservative': [25, 50, 75],  # Use safer levels
            'moderate': [50, 75, 95],      # Balanced approach
            'aggressive': [75, 95, 99]      # Use extreme levels
        }

        logger.info(f"DynamicPatternPlugin initialized with {self.risk_tolerance} risk tolerance")

    def analyze(self, position: Dict, market_data: MarketData) -> Signal:
        """
        Analyze position using dynamic pattern analysis

        Args:
            position: Current position data
            market_data: Current market data

        Returns:
            Signal with averaging decision
        """
        try:
            # Get candle data (would fetch from exchange in production)
            candles = self._fetch_candles(position.get('symbol', ''))

            if not candles:
                return Signal(
                    action=SignalAction.HOLD,
                    confidence=0.3,
                    reason="Insufficient candle data for pattern analysis"
                )

            # Detect trends
            trends = self.pattern_analyzer.detect_trends(candles)

            if len(trends) < 10:
                return Signal(
                    action=SignalAction.HOLD,
                    confidence=0.4,
                    reason="Insufficient trend history for pattern analysis"
                )

            # Analyze adverse movements
            stats = self.pattern_analyzer.analyze_adverse_movements(
                trends,
                position.get('side', 'buy')
            )

            # Calculate optimal averaging levels
            optimal_levels = self.calculate_optimal_levels(stats)

            # Check if current position matches pattern
            signal = self.evaluate_position(position, market_data, optimal_levels, stats)

            return signal

        except Exception as e:
            logger.error(f"Error in dynamic pattern analysis: {e}")
            return Signal(
                action=SignalAction.HOLD,
                confidence=0.2,
                reason=f"Pattern analysis error: {str(e)}"
            )

    def calculate_optimal_levels(self, stats: AdverseMovementStats) -> List[float]:
        """
        Calculate optimal averaging levels based on historical patterns

        Args:
            stats: Historical adverse movement statistics

        Returns:
            List of price distances (as %) for averaging
        """
        if not stats.adverse_moves:
            # No historical data, use AI-XYZ system defaults (% of margin)
            # These thresholds are from the AI-XYZ documentation
            return [-42, -68, -84, -94, -100]

        percentiles = self.level_percentiles[self.risk_tolerance]
        levels = []

        for p in percentiles:
            key = f'p{p}'
            if key in stats.adverse_moves:
                # Convert to percentage and negate (for loss levels)
                level = -stats.adverse_moves[key] * 100
                levels.append(level)

        # Ensure minimum spacing between levels
        min_spacing = 5.0  # 5% minimum between levels
        for i in range(1, len(levels)):
            if levels[i] > levels[i-1] - min_spacing:
                levels[i] = levels[i-1] - min_spacing

        return levels

    def evaluate_position(self, position: Dict, market_data: MarketData,
                         optimal_levels: List[float],
                         stats: AdverseMovementStats) -> Signal:
        """Evaluate if position should be averaged based on patterns"""
        # Calculate current UPNL%
        upnl_pct = self._calculate_upnl_pct(position, market_data)

        # Check which level we're at
        current_level = self._get_current_level(upnl_pct, optimal_levels)

        if current_level is not None:
            # Calculate size based on expected correction
            size = self._calculate_optimal_size(position, stats, current_level)

            # Calculate confidence based on pattern match
            confidence = self._calculate_confidence(stats, upnl_pct)

            logger.info(f"🎯 DynamicPattern returning AVERAGE: confidence={confidence:.2f}, size={size}, level={current_level}")

            return Signal(
                action=SignalAction.AVERAGE,
                confidence=confidence,
                size=size,
                reason=f"Pattern match at level {current_level+1} ({upnl_pct:.1f}%)",
                metadata={
                    'upnl_pct': upnl_pct,
                    'level': current_level,
                    'expected_correction': stats.corrections.get('p50', 0) * 100,
                    'sample_size': stats.sample_count
                }
            )

        return Signal(
            action=SignalAction.HOLD,
            confidence=0.6,
            reason=f"No pattern trigger at {upnl_pct:.1f}%",
            metadata={'upnl_pct': upnl_pct}
        )

    def _fetch_candles(self, symbol: str) -> List[Dict]:
        """Fetch candle data (simplified for now)"""
        # For now, simulate historical patterns based on asset type
        # In production, this would fetch real historical data

        # Simulate different volatility patterns for different assets
        if 'MIRA' in symbol:
            # High volatility asset - larger moves
            return self._generate_volatile_pattern()
        elif 'HEMI' in symbol:
            # Medium volatility
            return self._generate_medium_pattern()
        else:
            # Default moderate pattern
            return self._generate_default_pattern()

    def _generate_volatile_pattern(self) -> List[Dict]:
        """Generate volatile pattern data for high-risk assets like MIRA"""
        # Simulate historical moves showing 20-60% drops are common
        import random
        candles = []
        price = 100
        for i in range(100):
            change = random.uniform(-0.05, 0.03)  # More downside
            price *= (1 + change)
            candles.append({
                'close': price,
                'open': price * 0.99,
                'high': price * 1.01,
                'low': price * 0.98
            })
        return candles

    def _generate_medium_pattern(self) -> List[Dict]:
        """Generate medium volatility pattern"""
        import random
        candles = []
        price = 100
        for i in range(100):
            change = random.uniform(-0.03, 0.02)
            price *= (1 + change)
            candles.append({
                'close': price,
                'open': price * 0.995,
                'high': price * 1.005,
                'low': price * 0.99
            })
        return candles

    def _generate_default_pattern(self) -> List[Dict]:
        """Generate default pattern data"""
        import random
        candles = []
        price = 100
        for i in range(100):
            change = random.uniform(-0.02, 0.015)
            price *= (1 + change)
            candles.append({
                'close': price,
                'open': price * 0.997,
                'high': price * 1.003,
                'low': price * 0.995
            })
        return candles

    def _calculate_upnl_pct(self, position: Dict, market_data: MarketData) -> float:
        """Calculate UPNL percentage of margin - matches main system logic"""
        # Get position data
        entry = position.get('entry_price', 0)
        current = market_data.current_price or position.get('current_price', entry)
        side = position.get('side', 'buy')
        amount = position.get('amount', 0)
        leverage = position.get('leverage', 8)  # Default leverage from AI-XYZ system

        if entry == 0 or amount == 0:
            return 0.0

        # Calculate UPNL value
        if side == 'buy':
            upnl = (current - entry) * amount
        else:
            upnl = (entry - current) * amount

        # Calculate margin
        position_value = amount * entry
        margin = position_value / leverage

        # Calculate UPNL as percentage of margin (matches autonomous_sync.py)
        if margin > 0:
            return (upnl / margin) * 100
        else:
            return 0.0

    def _get_current_level(self, upnl_pct: float, levels: List[float]) -> Optional[int]:
        """Determine which averaging level we're at"""
        if not levels:
            return None

        # Check if we've passed any threshold (cumulative trigger)
        # Trigger when UPNL is at or below the threshold
        for i, level in enumerate(levels):
            if upnl_pct <= level:
                return i

        return None

    def _calculate_optimal_size(self, position: Dict, stats: AdverseMovementStats,
                               level: int) -> float:
        """Calculate optimal position size for averaging"""
        initial_size = position.get('initial_size', position.get('amount', 0))

        # Progressive sizing based on level
        multipliers = [1.0, 1.5, 2.25, 3.375, 5.0]
        multiplier = multipliers[min(level, len(multipliers)-1)]

        # Adjust based on expected correction
        if stats.corrections:
            expected_correction = stats.corrections.get('p50', 0)
            if expected_correction > 0.01:  # At least 1% expected correction
                # Increase size if good correction expected
                multiplier *= 1.2

        return initial_size * multiplier

    def _calculate_confidence(self, stats: AdverseMovementStats,
                             upnl_pct: float) -> float:
        """Calculate confidence score based on pattern strength"""
        base_confidence = 0.5

        # Increase confidence with more samples
        if stats.sample_count > 100:
            base_confidence += 0.2
        elif stats.sample_count > 50:
            base_confidence += 0.1

        # Increase confidence if corrections are consistent
        if stats.correction_ratios:
            ratio_std = np.std(list(stats.correction_ratios.values()))
            if ratio_std < 0.2:  # Low variance in correction ratios
                base_confidence += 0.15

        return min(base_confidence, 0.85)  # Cap at 85%

    def get_priority(self) -> int:
        """
        Lower priority than Fibonacci (enhancement, not replacement)

        Returns:
            90 (lower than Fibonacci's 100)
        """
        return 90

    def get_required_timeframes(self) -> List[str]:
        """Required timeframes for pattern analysis"""
        return ['1m', '5m', '15m', '1h', '4h']

    def __str__(self) -> str:
        """String representation"""
        return f"DynamicPatternPlugin(priority=90, risk={self.risk_tolerance})"


# Test function
if __name__ == "__main__":
    plugin = DynamicPatternPlugin({'risk_tolerance': 'moderate'})
    print(f"Plugin initialized: {plugin}")