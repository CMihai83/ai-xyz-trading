#!/usr/bin/env python3
"""
Timeframe Speed Tracker
Tracks the average speed of price movement for each timeframe and dynamically
adjusts averaging thresholds based on actual price velocity.
"""

import time
import numpy as np
from typing import Dict, List, Tuple, Optional
from collections import deque
from datetime import datetime, timedelta
import structlog

logger = structlog.get_logger(__name__)

class TimeframeSpeedTracker:
    """
    Tracks price movement speed across different timeframes and determines
    when to switch to higher timeframe deltas based on price velocity.
    """
    
    # Timeframe durations in seconds
    TIMEFRAME_SECONDS = {
        '1m': 60,
        '5m': 300,
        '15m': 900,
        '1h': 3600,
        '4h': 14400,
        '1d': 86400
    }
    
    # Expected average movement per timeframe (% per period)
    # These will be calibrated from historical data
    DEFAULT_SPEEDS = {
        '1m': 0.5,   # 0.5% per minute
        '5m': 1.0,   # 1.0% per 5 minutes
        '15m': 1.5,  # 1.5% per 15 minutes
        '1h': 2.5,   # 2.5% per hour
        '4h': 5.0,   # 5.0% per 4 hours
        '1d': 10.0   # 10.0% per day
    }
    
    def __init__(self, window_size: int = 100):
        """
        Initialize the speed tracker
        
        Args:
            window_size: Number of price points to keep for each timeframe
        """
        self.window_size = window_size
        self.price_history = {}  # symbol -> deque of (timestamp, price)
        self.speed_history = {}  # symbol -> timeframe -> deque of speeds
        self.average_speeds = {}  # symbol -> timeframe -> average speed
        self.current_timeframe = {}  # symbol -> current active timeframe
        self.last_averaging_time = {}  # symbol -> timestamp of last averaging
        self.position_start_time = {}  # symbol -> position opening time
        self.position_start_price = {}  # symbol -> position entry price
        
        logger.info(
            "TimeframeSpeedTracker initialized",
            window_size=window_size
        )
    
    def update_price(self, symbol: str, price: float, timestamp: Optional[float] = None):
        """
        Update price data and calculate speeds for all timeframes
        
        Args:
            symbol: Trading symbol
            price: Current price
            timestamp: Unix timestamp (uses current time if not provided)
        """
        if timestamp is None:
            timestamp = time.time()
        
        # Initialize if needed
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.window_size)
            self.speed_history[symbol] = {tf: deque(maxlen=20) for tf in self.TIMEFRAME_SECONDS}
            self.average_speeds[symbol] = {}
            self.current_timeframe[symbol] = '1m'
        
        # Add price point
        self.price_history[symbol].append((timestamp, price))
        
        # Calculate speeds for each timeframe
        self._calculate_speeds(symbol)
    
    def _calculate_speeds(self, symbol: str):
        """
        Calculate price movement speeds for all timeframes
        """
        if len(self.price_history[symbol]) < 2:
            return
        
        current_time, current_price = self.price_history[symbol][-1]
        
        for timeframe, seconds in self.TIMEFRAME_SECONDS.items():
            # Find price from timeframe seconds ago
            target_time = current_time - seconds
            
            # Find closest historical price
            historical_price = None
            for ts, price in self.price_history[symbol]:
                if ts <= target_time:
                    historical_price = price
                else:
                    break
            
            if historical_price:
                # Calculate speed (% change per timeframe period)
                price_change_pct = abs((current_price - historical_price) / historical_price * 100)
                time_elapsed = current_time - ts
                
                if time_elapsed > 0:
                    # Normalize to speed per timeframe period
                    speed = price_change_pct * (seconds / time_elapsed)
                    self.speed_history[symbol][timeframe].append(speed)
                    
                    # Update average speed
                    if len(self.speed_history[symbol][timeframe]) > 0:
                        self.average_speeds[symbol][timeframe] = np.mean(
                            list(self.speed_history[symbol][timeframe])
                        )
    
    def get_current_speed(self, symbol: str, timeframe: str) -> float:
        """
        Get current price movement speed for a timeframe
        
        Returns:
            Speed in % per timeframe period
        """
        if symbol not in self.speed_history:
            return self.DEFAULT_SPEEDS.get(timeframe, 1.0)
        
        speeds = self.speed_history[symbol].get(timeframe, [])
        if speeds:
            return speeds[-1]
        return self.DEFAULT_SPEEDS.get(timeframe, 1.0)
    
    def get_average_speed(self, symbol: str, timeframe: str) -> float:
        """
        Get average price movement speed for a timeframe
        
        Returns:
            Average speed in % per timeframe period
        """
        if symbol in self.average_speeds and timeframe in self.average_speeds[symbol]:
            return self.average_speeds[symbol][timeframe]
        return self.DEFAULT_SPEEDS.get(timeframe, 1.0)
    
    def should_switch_timeframe(
        self,
        symbol: str,
        current_upnl_pct: float,
        current_timeframe: str,
        position_entry_price: float
    ) -> Tuple[bool, str, Dict]:
        """
        Determine if we should switch to a higher timeframe based on price speed
        
        Args:
            symbol: Trading symbol
            current_upnl_pct: Current unrealized P&L percentage
            current_timeframe: Current active timeframe
            position_entry_price: Position entry price
            
        Returns:
            Tuple of (should_switch, new_timeframe, speed_info)
        """
        if symbol not in self.price_history or len(self.price_history[symbol]) < 2:
            return False, current_timeframe, {}
        
        # Track position start if not already
        if symbol not in self.position_start_time:
            self.position_start_time[symbol] = time.time()
            self.position_start_price[symbol] = position_entry_price
        
        current_time = time.time()
        position_duration = current_time - self.position_start_time[symbol]
        
        # Calculate actual price movement speed
        current_price = self.price_history[symbol][-1][1]
        total_movement_pct = abs((current_price - position_entry_price) / position_entry_price * 100)
        
        speed_info = {
            'position_duration_seconds': position_duration,
            'total_movement_pct': total_movement_pct,
            'current_timeframe': current_timeframe,
            'timeframe_speeds': {}
        }
        
        # Get list of timeframes in order
        timeframe_list = list(self.TIMEFRAME_SECONDS.keys())
        current_tf_index = timeframe_list.index(current_timeframe)
        
        # Check if price is moving faster than expected for current timeframe
        current_tf_seconds = self.TIMEFRAME_SECONDS[current_timeframe]
        expected_movement = self.get_average_speed(symbol, current_timeframe)
        
        # Calculate how many timeframe periods have passed
        periods_passed = position_duration / current_tf_seconds
        expected_total_movement = expected_movement * periods_passed
        
        speed_info['expected_movement'] = expected_total_movement
        speed_info['actual_vs_expected_ratio'] = total_movement_pct / expected_total_movement if expected_total_movement > 0 else 1.0
        
        # If price is moving faster than expected, switch to next timeframe
        if total_movement_pct > expected_total_movement * 1.2:  # 20% faster than expected
            if current_tf_index < len(timeframe_list) - 1:
                new_timeframe = timeframe_list[current_tf_index + 1]
                
                logger.info(
                    "Switching to higher timeframe due to fast price movement",
                    symbol=symbol,
                    current_timeframe=current_timeframe,
                    new_timeframe=new_timeframe,
                    actual_movement=f"{total_movement_pct:.2f}%",
                    expected_movement=f"{expected_total_movement:.2f}%",
                    duration_minutes=position_duration/60
                )
                
                self.current_timeframe[symbol] = new_timeframe
                return True, new_timeframe, speed_info
        
        # Also check if we've been in this timeframe too long
        # (price moving too slowly for current timeframe)
        if periods_passed > 2 and total_movement_pct < expected_total_movement * 0.5:
            # Price moving too slowly, stay in current timeframe longer
            speed_info['recommendation'] = 'stay_current_timeframe'
        
        return False, current_timeframe, speed_info
    
    def get_dynamic_threshold(
        self,
        symbol: str,
        step: int,
        base_allocations: Dict,
        current_upnl_pct: float
    ) -> float:
        """
        Get dynamic averaging threshold based on current timeframe and speed
        
        Args:
            symbol: Trading symbol
            step: Averaging step number (0-based)
            base_allocations: Base allocations from TimeframeCapitalAllocator
            current_upnl_pct: Current unrealized P&L percentage
            
        Returns:
            Threshold percentage for this averaging step
        """
        # Map steps to timeframes based on allocations
        step_to_timeframe = []
        step_counter = 0
        
        for timeframe in self.TIMEFRAME_SECONDS.keys():
            if timeframe in base_allocations:
                steps_in_tf = base_allocations[timeframe].get('steps', 0)
                for _ in range(steps_in_tf):
                    step_to_timeframe.append(timeframe)
                    step_counter += 1
        
        if step >= len(step_to_timeframe):
            # Beyond configured steps, use largest timeframe
            target_timeframe = '1d'
        else:
            target_timeframe = step_to_timeframe[step]
        
        # Get the appropriate delta for this timeframe
        timeframe_deltas = {
            '1m': 4.4,    # From your logs
            '5m': 8.3,    # From your logs
            '15m': 15.3,  # From your logs
            '1h': 40.7,   # From your logs
            '4h': 84.7,   # From your logs
            '1d': 108.9   # From your logs
        }
        
        base_delta = timeframe_deltas.get(target_timeframe, 10.0)
        
        # Adjust based on current speed
        current_speed = self.get_current_speed(symbol, target_timeframe)
        average_speed = self.get_average_speed(symbol, target_timeframe)
        
        if average_speed > 0:
            speed_ratio = current_speed / average_speed
            # If price moving faster, reduce threshold (average sooner)
            # If price moving slower, increase threshold (wait longer)
            # FIX: Changed from 0.1 to 0.5 to prevent 10x explosion on new positions
            # When current_speed=0, this now creates 2x max instead of 10x
            adjusted_delta = base_delta / max(speed_ratio, 0.5)  # Prevent division by very small numbers
        else:
            adjusted_delta = base_delta

        # Ensure reasonable bounds
        # FIX: Reduced cap from base_delta * 5 to base_delta * 2 for safer thresholds
        # This prevents thresholds from exceeding liquidation point when multiplied by leverage
        adjusted_delta = max(0.001, min(adjusted_delta, base_delta * 2))
        
        # Apply step multiplier for progressive thresholds
        if step == 0:
            threshold = adjusted_delta * 0.5  # First step at 50% of delta
        elif step % 2 == 1:
            threshold = adjusted_delta * 0.75  # Odd steps at 75% of delta
        else:
            threshold = adjusted_delta  # Even steps at full delta
        
        logger.info(
            "Calculated dynamic threshold",
            symbol=symbol,
            step=step,
            timeframe=target_timeframe,
            base_delta=base_delta,
            adjusted_delta=adjusted_delta,
            threshold=threshold,
            current_speed=current_speed,
            average_speed=average_speed
        )
        
        return threshold
    
    def reset_position(self, symbol: str):
        """
        Reset tracking for a position (called when position is closed)
        
        Args:
            symbol: Trading symbol
        """
        if symbol in self.position_start_time:
            del self.position_start_time[symbol]
        if symbol in self.position_start_price:
            del self.position_start_price[symbol]
        if symbol in self.last_averaging_time:
            del self.last_averaging_time[symbol]
        if symbol in self.current_timeframe:
            self.current_timeframe[symbol] = '1m'
        
        logger.info("Reset position tracking", symbol=symbol)


# Example usage
if __name__ == "__main__":
    tracker = TimeframeSpeedTracker()
    
    # Simulate price updates
    symbol = "AVNT/USDT:USDT"
    entry_price = 0.7779
    
    # Initial price
    tracker.update_price(symbol, entry_price)
    
    # Simulate price drops over time
    import time
    prices = [
        (60, 0.7700),   # 1 minute: -1.0%
        (120, 0.7650),  # 2 minutes: -1.7%
        (180, 0.7600),  # 3 minutes: -2.3%
        (300, 0.7500),  # 5 minutes: -3.6%
        (600, 0.7400),  # 10 minutes: -4.9%
    ]
    
    start_time = time.time()
    for seconds, price in prices:
        tracker.update_price(symbol, price, start_time + seconds)
        
        # Check if should switch timeframe
        upnl_pct = (price - entry_price) / entry_price * 100
        should_switch, new_tf, info = tracker.should_switch_timeframe(
            symbol, upnl_pct, '1m', entry_price
        )
        
        print(f"\nTime: {seconds}s, Price: {price}, UPNL: {upnl_pct:.2f}%")
        print(f"Should switch: {should_switch}, New TF: {new_tf}")
        print(f"Speed info: {info}")