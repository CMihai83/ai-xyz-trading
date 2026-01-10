#!/usr/bin/env python3
"""
Position Sizing Configuration
- Full capital utilization (no safety reserve)
- Safety replaced by limit orders before liquidation
- FIFO margin allocation for capital increases
"""

class PositionSizingConfig:
    # Total capital available for allocation (can be dynamically updated)
    TOTAL_CAPITAL = 25.0  # $25 total capital per position (default)

    # Capital allocation strategy - USE FULL CAPITAL
    # Safety is now handled by limit orders before liquidation price
    SAFETY_MARGIN_PERCENT = 0.0   # NO safety reserve - full capital for trading
    TRADING_CAPITAL_PERCENT = 1.0  # 100% for initial + averaging

    # Base position margin - $5.00 initial margin (before leverage)
    BASE_MARGIN_SIZE = 5.00  # $5.00 initial margin (FIXED)

    # Base position value after leverage (assuming ~6.5x average leverage)
    BASE_POSITION_VALUE = 32.50  # $32.50 position value after leverage ($5 margin * 6.5x leverage)

    # Capital breakdown - FULL UTILIZATION
    SAFETY_MARGIN = 0.0  # No safety margin - replaced by limit orders
    TRADING_CAPITAL = TOTAL_CAPITAL  # Full $25 for trading
    AVERAGING_CAPITAL = TOTAL_CAPITAL - BASE_MARGIN_SIZE  # $20 for averaging steps

    # Liquidation Protection (replaces safety margin)
    LIQUIDATION_PROTECTION_ENABLED = True
    LIQUIDATION_ORDER_UPNL_PERCENT = -82.5  # Place limit order at -82.5% UPNL
    LIQUIDATION_ORDER_MARGIN_MULTIPLIER = 1.0  # Match margin used so far

    # FIFO Margin Allocation
    FIFO_ENABLED = True  # First positions get priority for extra margin
    MIN_CAPITAL_PER_POSITION = 25.0  # Minimum capital allocation
    MAX_CAPITAL_PER_POSITION = 50.0  # Maximum capital allocation

    # Confidence threshold for larger positions
    HIGH_CONFIDENCE_THRESHOLD = 0.7

    # Maximum position size multiplier when high confidence
    MAX_SIZE_MULTIPLIER = 2.0  # Can go up to 2x base size

    @classmethod
    def update_total_capital(cls, new_capital: float):
        """
        Dynamically update total capital per position.
        Used for FIFO margin allocation.

        Args:
            new_capital: New capital amount (e.g., $40 instead of $25)
        """
        cls.TOTAL_CAPITAL = new_capital
        cls.TRADING_CAPITAL = new_capital  # Full capital for trading
        cls.AVERAGING_CAPITAL = new_capital - cls.BASE_MARGIN_SIZE
        print(f"📊 Updated Position Sizing: Total=${new_capital:.2f}, Averaging=${cls.AVERAGING_CAPITAL:.2f}")

    @staticmethod
    def calculate_position_size(leverage: float, confidence: float = 0.5) -> dict:
        """
        Calculate position size based on confidence level

        Args:
            leverage: Leverage to use (7x-10x)
            confidence: Signal confidence (0-1)

        Returns:
            dict with margin_size and position_value
        """
        # Default position value after leverage
        position_value = PositionSizingConfig.BASE_MARGIN_SIZE * leverage

        # Only increase size if confidence > 0.7
        if confidence > PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD:
            # Scale size based on confidence above threshold
            confidence_factor = (confidence - PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD) / 0.3
            size_multiplier = 1.0 + (confidence_factor * (PositionSizingConfig.MAX_SIZE_MULTIPLIER - 1.0))
            base_position_value = PositionSizingConfig.BASE_MARGIN_SIZE * leverage
            position_value = base_position_value * size_multiplier

        # Calculate margin required
        margin_size = position_value / leverage

        return {
            'margin_size': margin_size,
            'position_value': position_value,
            'confidence': confidence,
            'size_multiplier': position_value / (PositionSizingConfig.BASE_MARGIN_SIZE * leverage)
        }

    @staticmethod
    def get_position_size_for_signal(signal: dict) -> dict:
        """
        Get position size for a trading signal

        Args:
            signal: Trading signal with confidence and leverage

        Returns:
            dict with sizing information
        """
        confidence = signal.get('confidence', 0.5)
        leverage = signal.get('leverage', 7)

        sizing = PositionSizingConfig.calculate_position_size(leverage, confidence)

        # Add explanation
        if confidence > PositionSizingConfig.HIGH_CONFIDENCE_THRESHOLD:
            sizing['reason'] = f"High confidence ({confidence:.2f}) - using {sizing['size_multiplier']:.1f}x base size"
        else:
            sizing['reason'] = f"Standard confidence ({confidence:.2f}) - using base size ${PositionSizingConfig.BASE_MARGIN_SIZE:.2f}"

        return sizing


# Example usage
if __name__ == "__main__":
    print("="*60)
    print("POSITION SIZING CONFIGURATION (FULL CAPITAL)")
    print("="*60)
    print(f"Total Capital: ${PositionSizingConfig.TOTAL_CAPITAL:.2f}")
    print(f"Trading Capital: ${PositionSizingConfig.TRADING_CAPITAL:.2f} (100%)")
    print(f"Base Margin: ${PositionSizingConfig.BASE_MARGIN_SIZE:.2f}")
    print(f"Averaging Capital: ${PositionSizingConfig.AVERAGING_CAPITAL:.2f}")
    print(f"Safety Margin: ${PositionSizingConfig.SAFETY_MARGIN:.2f} (replaced by limit orders)")
    print(f"\nLiquidation Protection: {PositionSizingConfig.LIQUIDATION_PROTECTION_ENABLED}")
    print(f"Limit Order Trigger: {PositionSizingConfig.LIQUIDATION_ORDER_UPNL_PERCENT}% UPNL")
    print(f"FIFO Allocation: {PositionSizingConfig.FIFO_ENABLED}")
