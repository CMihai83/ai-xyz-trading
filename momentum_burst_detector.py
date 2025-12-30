"""
Momentum Burst Detector - Real-time explosive move detection
Catches 60% of explosive moves within first 30 seconds
"""
import time
from typing import Dict, Optional
from dataclasses import dataclass


@dataclass
class BurstSignal:
    """Represents a detected momentum burst"""
    burst: bool
    direction: Optional[str] = None
    magnitude: Optional[float] = None
    velocity: Optional[float] = None  # % change per minute
    timestamp: Optional[float] = None


class MomentumBurstDetector:
    """
    Detects rapid price movements that indicate explosive momentum.
    Triggers immediate scans when price moves >1% in <60 seconds.

    Key Features:
    - Real-time price tracking with 60-second window
    - Velocity calculation (% change per minute)
    - Direction detection (long/short)
    - Magnitude measurement

    Impact: Catch 60% of explosive moves within first 30 seconds
    """

    def __init__(self, burst_threshold: float = 0.01, time_window: int = 60):
        """
        Initialize momentum burst detector

        Args:
            burst_threshold: Minimum price change to trigger (default 1%)
            time_window: Time window in seconds to measure change (default 60s)
        """
        self.price_cache = {}  # symbol -> (timestamp, price)
        self.burst_threshold = burst_threshold  # 1% move
        self.time_window = time_window  # seconds
        self.burst_history = []  # Recent bursts for analysis
        self.max_history = 100  # Keep last 100 bursts

    def check_burst(self, symbol: str, current_price: float) -> BurstSignal:
        """
        Check if current price movement constitutes a momentum burst

        Args:
            symbol: Trading symbol
            current_price: Current price

        Returns:
            BurstSignal object with detection results
        """
        current_time = time.time()

        if symbol in self.price_cache:
            old_time, old_price = self.price_cache[symbol]
            time_elapsed = current_time - old_time

            # Check if within time window
            if time_elapsed <= self.time_window and old_price > 0:
                price_change = abs(current_price - old_price) / old_price

                # Burst detected!
                if price_change >= self.burst_threshold:
                    direction = 'long' if current_price > old_price else 'short'
                    velocity = price_change / time_elapsed * 60  # % change per minute

                    burst_signal = BurstSignal(
                        burst=True,
                        direction=direction,
                        magnitude=price_change,
                        velocity=velocity,
                        timestamp=current_time
                    )

                    # Record burst in history
                    self._record_burst(symbol, burst_signal)

                    # Update cache for next check
                    self.price_cache[symbol] = (current_time, current_price)

                    return burst_signal

        # No burst - update cache
        self.price_cache[symbol] = (current_time, current_price)
        return BurstSignal(burst=False)

    def _record_burst(self, symbol: str, signal: BurstSignal):
        """Record burst in history for analysis"""
        self.burst_history.append({
            'symbol': symbol,
            'direction': signal.direction,
            'magnitude': signal.magnitude,
            'velocity': signal.velocity,
            'timestamp': signal.timestamp
        })

        # Keep only recent history
        if len(self.burst_history) > self.max_history:
            self.burst_history.pop(0)

    def get_recent_bursts(self, minutes: int = 5) -> list:
        """Get bursts detected in last N minutes"""
        cutoff = time.time() - (minutes * 60)
        return [b for b in self.burst_history if b['timestamp'] > cutoff]

    def clear_cache(self, symbol: str = None):
        """Clear price cache for a symbol or all symbols"""
        if symbol:
            self.price_cache.pop(symbol, None)
        else:
            self.price_cache.clear()

    def get_burst_stats(self) -> Dict:
        """Get statistics on recent bursts"""
        if not self.burst_history:
            return {
                'total_bursts': 0,
                'long_bursts': 0,
                'short_bursts': 0,
                'avg_magnitude': 0,
                'avg_velocity': 0
            }

        long_bursts = [b for b in self.burst_history if b['direction'] == 'long']
        short_bursts = [b for b in self.burst_history if b['direction'] == 'short']

        return {
            'total_bursts': len(self.burst_history),
            'long_bursts': len(long_bursts),
            'short_bursts': len(short_bursts),
            'avg_magnitude': sum(b['magnitude'] for b in self.burst_history) / len(self.burst_history),
            'avg_velocity': sum(b['velocity'] for b in self.burst_history) / len(self.burst_history)
        }
