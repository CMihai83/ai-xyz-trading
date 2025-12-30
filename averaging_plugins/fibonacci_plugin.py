#!/usr/bin/env python3
"""
Fibonacci Averaging Plugin
Wraps the current AI-XYZ Fibonacci-based averaging logic as a plugin
"""

import json
import logging
from typing import Dict, List, Optional
from datetime import datetime

from plugin_interface import (
    AveragingPlugin,
    Signal,
    SignalAction,
    MarketData
)

logger = logging.getLogger(__name__)


class FibonacciAveragingPlugin(AveragingPlugin):
    """
    Current Fibonacci-based averaging strategy from AI-XYZ
    This is the proven logic that's currently in production
    """

    def __init__(self, config: Dict = None):
        """Initialize with Fibonacci thresholds and multipliers"""
        super().__init__(config)

        # Thresholds from AI-XYZ documentation
        # NOTE: -100% would mean liquidation, so we stop at -94% for safety
        self.averaging_thresholds = [-42, -68, -84, -94, -97]  # % of margin (stop before liquidation)
        self.fibonacci_multipliers = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]

        # Gate threshold for allowing averaging
        self.gate_threshold = -42  # Must be at least -42% to start averaging

        # Load position state for context
        self.state_file = '/app/position_state.json'

    def analyze(self, position: Dict, market_data: MarketData) -> Signal:
        """
        Analyze position using Fibonacci logic

        Args:
            position: Current position data
            market_data: Current market data

        Returns:
            Signal with averaging decision
        """
        try:
            # Calculate UPNL percentage
            upnl_pct = self.calculate_upnl_percentage(position, market_data)

            # Check if we should average
            if self.should_average(position, upnl_pct):
                # Get next averaging size
                next_size = self.calculate_next_size(position)

                # Check momentum permission
                if self.check_momentum_permission(position):
                    return Signal(
                        action=SignalAction.AVERAGE,
                        confidence=0.85,  # High confidence for proven logic
                        size=next_size,
                        reason=f"Fibonacci threshold reached at {upnl_pct:.1f}%",
                        metadata={
                            'upnl_pct': upnl_pct,
                            'threshold': self.get_current_threshold(position),
                            'step': self.get_averaging_step(position)
                        }
                    )
                else:
                    return Signal(
                        action=SignalAction.HOLD,
                        confidence=0.9,
                        reason=f"Waiting for momentum reversal at {upnl_pct:.1f}%",
                        metadata={'upnl_pct': upnl_pct}
                    )

            # Check if in profit (for future surplus dump integration)
            if upnl_pct > 0 and self.has_averaging_steps(position):
                # Position recovered - could trigger surplus dump
                return Signal(
                    action=SignalAction.HOLD,  # Let surplus_dump_manager handle this
                    confidence=0.8,
                    reason=f"Position profitable at {upnl_pct:.1f}%, surplus dump zone",
                    metadata={'upnl_pct': upnl_pct, 'suggest': 'surplus_dump'}
                )

            return Signal(
                action=SignalAction.HOLD,
                confidence=1.0,
                reason=f"No action needed at {upnl_pct:.1f}%",
                metadata={'upnl_pct': upnl_pct}
            )

        except Exception as e:
            logger.error(f"Error in Fibonacci analysis: {e}")
            return Signal(
                action=SignalAction.HOLD,
                confidence=1.0,
                reason=f"Analysis error: {str(e)}"
            )

    def calculate_upnl_percentage(self, position: Dict,
                                  market_data: MarketData) -> float:
        """Calculate UPNL as percentage of margin"""
        entry_price = position.get('entry_price', 0)
        amount = position.get('amount', 0)
        leverage = position.get('leverage', 8)
        side = position.get('side', 'buy')

        # Get current price
        current_price = market_data.current_price
        if current_price == 0:
            current_price = position.get('current_price', entry_price)

        # Calculate position value and margin
        position_value = amount * entry_price
        margin = position_value / leverage if leverage > 0 else position_value

        # Calculate UPNL
        if side == 'buy':
            upnl = (current_price - entry_price) * amount
        else:  # sell/short
            upnl = (entry_price - current_price) * amount

        # Calculate as percentage of margin
        upnl_pct = (upnl / margin * 100) if margin > 0 else 0

        return upnl_pct

    def should_average(self, position: Dict, upnl_pct: float) -> bool:
        """Determine if position should be averaged"""
        # Must be in loss and past gate threshold
        if upnl_pct >= self.gate_threshold:
            return False

        # Get current averaging step
        current_step = self.get_averaging_step(position)

        # Check if we've reached max steps
        if current_step >= len(self.averaging_thresholds):
            return False

        # Get threshold for next step
        next_threshold = self.averaging_thresholds[current_step]

        # Check if we've crossed the threshold
        return upnl_pct <= next_threshold

    def get_averaging_step(self, position: Dict) -> int:
        """Get current averaging step from position state"""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            symbol = position.get('symbol', '')
            return state.get('averaging_steps', {}).get(symbol, 0)
        except:
            return 0

    def get_current_threshold(self, position: Dict) -> float:
        """Get current threshold for position"""
        step = self.get_averaging_step(position)
        if step < len(self.averaging_thresholds):
            return self.averaging_thresholds[step]
        return -100  # Max threshold

    def calculate_next_size(self, position: Dict) -> float:
        """Calculate size for next averaging step using Fibonacci"""
        current_step = self.get_averaging_step(position)
        initial_size = position.get('initial_size', position.get('amount', 0))

        # Get Fibonacci multiplier for this step
        if current_step < len(self.fibonacci_multipliers):
            multiplier = self.fibonacci_multipliers[current_step]
        else:
            # Use last multiplier if beyond array
            multiplier = self.fibonacci_multipliers[-1]

        # Calculate next size
        next_size = initial_size * multiplier

        # Apply safety limits
        max_size = initial_size * 20  # Max 20x initial size
        return min(next_size, max_size)

    def check_momentum_permission(self, position: Dict) -> bool:
        """Check if momentum guardian allows averaging"""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            symbol = position.get('symbol', '')
            momentum = state.get('momentum_permission', {}).get(symbol, {})

            return momentum.get('can_average', False)
        except:
            # If can't check, be conservative
            return False

    def has_averaging_steps(self, position: Dict) -> bool:
        """Check if position has taken averaging steps"""
        return self.get_averaging_step(position) > 0

    def get_priority(self) -> int:
        """
        Highest priority - this is the proven production logic

        Returns:
            100 (highest priority)
        """
        return 100

    def get_required_timeframes(self) -> List[str]:
        """
        Required timeframes for delta calculation

        Returns:
            List of timeframe strings
        """
        return ['1m', '5m', '15m', '1h', '4h', '1d']

    def get_required_indicators(self) -> List[str]:
        """
        Required indicators for analysis

        Returns:
            List of indicator names
        """
        return ['momentum', 'volatility', 'volume']

    def validate_position(self, position: Dict) -> bool:
        """
        Validate position has required fields

        Args:
            position: Position data to validate

        Returns:
            True if valid
        """
        required = ['entry_price', 'amount', 'side', 'leverage']
        has_required = all(field in position for field in required)

        if not has_required:
            logger.warning(f"Position missing required fields: {position.keys()}")
            return False

        # Validate values are reasonable
        if position['amount'] <= 0:
            logger.warning(f"Invalid position amount: {position['amount']}")
            return False

        if position['entry_price'] <= 0:
            logger.warning(f"Invalid entry price: {position['entry_price']}")
            return False

        return True

    def __str__(self) -> str:
        """String representation"""
        return f"FibonacciAveragingPlugin(priority=100, thresholds=[-42%, -68%, -84%, -94%, -97%])"


# Test function
if __name__ == "__main__":
    # Test the plugin
    plugin = FibonacciAveragingPlugin()

    # Mock position
    test_position = {
        'symbol': 'TEST/USDT',
        'entry_price': 100.0,
        'amount': 10.0,
        'side': 'buy',
        'leverage': 10,
        'current_price': 90.0  # 10% loss
    }

    # Mock market data
    test_market = MarketData(
        symbol='TEST/USDT',
        current_price=90.0,
        bid=89.9,
        ask=90.1,
        volume_24h=1000000,
        high_24h=105,
        low_24h=88,
        timestamp=datetime.now()
    )

    # Test analysis
    signal = plugin.analyze(test_position, test_market)
    print(f"Test signal: {signal}")
    print(f"Plugin info: {plugin}")