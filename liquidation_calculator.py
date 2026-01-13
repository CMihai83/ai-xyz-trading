#!/usr/bin/env python3
"""
Unified Liquidation Calculator
==============================
Single source of truth for liquidation price calculations across all modules.

This eliminates calculation inconsistencies that were causing ~50 USD errors
per $10k position due to different formulas in different modules.

Usage:
    from liquidation_calculator import get_liquidation_calculator, LiquidationCalculator

    calc = get_liquidation_calculator()
    liq_price = calc.calculate_liquidation_price(
        entry_price=50000,
        side='buy',  # or 'long'
        leverage=10
    )
"""

import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Singleton instance
_calculator_instance: Optional['LiquidationCalculator'] = None


@dataclass
class LiquidationResult:
    """Result of liquidation calculation with metadata"""
    liquidation_price: float
    entry_price: float
    side: str
    leverage: float
    margin_ratio: float
    maintenance_margin_rate: float
    price_distance_pct: float  # How far from entry to liquidation
    upnl_at_liquidation: float  # -100% for long, +100% for short (theoretical)


class LiquidationCalculator:
    """
    Unified liquidation price calculator.

    Formula (consistent across all modules):
    - LONG:  liq_price = entry * (1 - margin_ratio + maintenance_margin_rate)
    - SHORT: liq_price = entry * (1 + margin_ratio - maintenance_margin_rate)

    Where:
    - margin_ratio = 1 / leverage
    - maintenance_margin_rate = 0.5% (Bitget standard for USDT-M futures)

    Example (10x leverage LONG at $50,000):
    - margin_ratio = 1/10 = 0.10 (10%)
    - maintenance = 0.005 (0.5%)
    - liq_price = 50000 * (1 - 0.10 + 0.005) = 50000 * 0.905 = $45,250
    - Price must drop 9.5% to liquidate (not 10% due to maintenance margin)
    """

    # Bitget USDT-M Futures maintenance margin rate
    # This is the critical value that was missing in some calculations
    MAINTENANCE_MARGIN_RATE = 0.005  # 0.5%

    # Safety buffer for protection orders (place order before actual liquidation)
    PROTECTION_BUFFER = 0.025  # 2.5% buffer before liquidation

    def __init__(self, maintenance_margin_rate: float = None):
        """
        Initialize calculator with optional custom maintenance margin rate.

        Args:
            maintenance_margin_rate: Override default 0.5% if needed
        """
        self.maintenance_margin_rate = maintenance_margin_rate or self.MAINTENANCE_MARGIN_RATE
        logger.info(f"LiquidationCalculator initialized (maintenance_margin={self.maintenance_margin_rate*100:.2f}%)")

    def normalize_side(self, side: str) -> str:
        """Normalize side to 'long' or 'short'"""
        side_lower = side.lower()
        if side_lower in ['buy', 'long']:
            return 'long'
        elif side_lower in ['sell', 'short']:
            return 'short'
        else:
            raise ValueError(f"Invalid side: {side}. Must be 'buy'/'long' or 'sell'/'short'")

    def calculate_margin_ratio(self, leverage: float) -> float:
        """Calculate margin ratio from leverage"""
        if leverage <= 0:
            raise ValueError(f"Leverage must be positive, got {leverage}")
        return 1.0 / leverage

    def calculate_liquidation_price(
        self,
        entry_price: float,
        side: str,
        leverage: float
    ) -> float:
        """
        Calculate liquidation price for a position.

        Args:
            entry_price: Position entry price
            side: 'buy'/'long' or 'sell'/'short'
            leverage: Position leverage (e.g., 10 for 10x)

        Returns:
            Liquidation price

        Example:
            >>> calc = LiquidationCalculator()
            >>> calc.calculate_liquidation_price(50000, 'long', 10)
            45250.0  # Price drops 9.5% to liquidate
        """
        if entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got {entry_price}")

        normalized_side = self.normalize_side(side)
        margin_ratio = self.calculate_margin_ratio(leverage)

        if normalized_side == 'long':
            # LONG: liquidation when price drops
            # liq_price = entry * (1 - margin_ratio + maintenance)
            liquidation_price = entry_price * (1 - margin_ratio + self.maintenance_margin_rate)
        else:
            # SHORT: liquidation when price rises
            # liq_price = entry * (1 + margin_ratio - maintenance)
            liquidation_price = entry_price * (1 + margin_ratio - self.maintenance_margin_rate)

        return liquidation_price

    def calculate_liquidation_details(
        self,
        entry_price: float,
        side: str,
        leverage: float
    ) -> LiquidationResult:
        """
        Calculate liquidation price with full details.

        Returns LiquidationResult with all calculation metadata.
        """
        normalized_side = self.normalize_side(side)
        margin_ratio = self.calculate_margin_ratio(leverage)
        liq_price = self.calculate_liquidation_price(entry_price, side, leverage)

        # Calculate price distance
        if normalized_side == 'long':
            price_distance_pct = (entry_price - liq_price) / entry_price * 100
        else:
            price_distance_pct = (liq_price - entry_price) / entry_price * 100

        return LiquidationResult(
            liquidation_price=liq_price,
            entry_price=entry_price,
            side=normalized_side,
            leverage=leverage,
            margin_ratio=margin_ratio,
            maintenance_margin_rate=self.maintenance_margin_rate,
            price_distance_pct=price_distance_pct,
            upnl_at_liquidation=-100.0 if normalized_side == 'long' else 100.0
        )

    def calculate_protection_price(
        self,
        entry_price: float,
        side: str,
        leverage: float,
        buffer_pct: float = None
    ) -> float:
        """
        Calculate price for liquidation protection order.

        Places order BEFORE liquidation with a safety buffer.

        Args:
            entry_price: Position entry price
            side: 'buy'/'long' or 'sell'/'short'
            leverage: Position leverage
            buffer_pct: Buffer before liquidation (default 2.5%)

        Returns:
            Protection order price
        """
        buffer = buffer_pct if buffer_pct is not None else self.PROTECTION_BUFFER
        liq_price = self.calculate_liquidation_price(entry_price, side, leverage)
        normalized_side = self.normalize_side(side)

        if normalized_side == 'long':
            # Protection price above liquidation price
            protection_price = liq_price * (1 + buffer)
        else:
            # Protection price below liquidation price
            protection_price = liq_price * (1 - buffer)

        return protection_price

    def calculate_upnl_at_price(
        self,
        entry_price: float,
        current_price: float,
        side: str,
        leverage: float,
        position_size: float = 1.0
    ) -> tuple[float, float]:
        """
        Calculate UPNL and UPNL% at a given price.

        Args:
            entry_price: Position entry price
            current_price: Current market price
            side: 'buy'/'long' or 'sell'/'short'
            leverage: Position leverage
            position_size: Position size in contracts

        Returns:
            Tuple of (upnl_amount, upnl_percentage)
        """
        normalized_side = self.normalize_side(side)
        margin = (entry_price * position_size) / leverage

        if normalized_side == 'long':
            price_diff = current_price - entry_price
        else:
            price_diff = entry_price - current_price

        upnl = price_diff * position_size
        upnl_pct = (upnl / margin) * 100 if margin > 0 else 0

        return upnl, upnl_pct

    def calculate_price_at_upnl(
        self,
        entry_price: float,
        target_upnl_pct: float,
        side: str,
        leverage: float
    ) -> float:
        """
        Calculate price at which a target UPNL% is reached.

        Args:
            entry_price: Position entry price
            target_upnl_pct: Target UPNL percentage (e.g., -82.5 for -82.5%)
            side: 'buy'/'long' or 'sell'/'short'
            leverage: Position leverage

        Returns:
            Price at which target UPNL% is reached

        Example:
            >>> calc.calculate_price_at_upnl(50000, -82.5, 'long', 10)
            45875.0  # Price at which UPNL = -82.5%
        """
        normalized_side = self.normalize_side(side)

        # UPNL% = ((current - entry) / entry) * leverage * 100 for long
        # target_upnl_pct = ((price - entry) / entry) * leverage * 100
        # price = entry * (1 + target_upnl_pct / (leverage * 100))

        price_change_pct = target_upnl_pct / (leverage * 100)

        if normalized_side == 'long':
            target_price = entry_price * (1 + price_change_pct)
        else:
            target_price = entry_price * (1 - price_change_pct)

        return target_price

    def is_safe_from_liquidation(
        self,
        entry_price: float,
        current_price: float,
        side: str,
        leverage: float,
        safety_buffer_pct: float = 5.0
    ) -> tuple[bool, float]:
        """
        Check if position is safe from liquidation.

        Args:
            entry_price: Position entry price
            current_price: Current market price
            side: 'buy'/'long' or 'sell'/'short'
            leverage: Position leverage
            safety_buffer_pct: Required buffer from liquidation (default 5%)

        Returns:
            Tuple of (is_safe, distance_to_liquidation_pct)
        """
        liq_price = self.calculate_liquidation_price(entry_price, side, leverage)
        normalized_side = self.normalize_side(side)

        if normalized_side == 'long':
            distance_pct = (current_price - liq_price) / liq_price * 100
        else:
            distance_pct = (liq_price - current_price) / liq_price * 100

        is_safe = distance_pct >= safety_buffer_pct

        return is_safe, distance_pct


def get_liquidation_calculator() -> LiquidationCalculator:
    """Get singleton instance of LiquidationCalculator"""
    global _calculator_instance
    if _calculator_instance is None:
        _calculator_instance = LiquidationCalculator()
    return _calculator_instance


# Quick access functions for common operations
def calc_liq_price(entry: float, side: str, leverage: float) -> float:
    """Quick function to calculate liquidation price"""
    return get_liquidation_calculator().calculate_liquidation_price(entry, side, leverage)


def calc_upnl_price(entry: float, upnl_pct: float, side: str, leverage: float) -> float:
    """Quick function to calculate price at target UPNL%"""
    return get_liquidation_calculator().calculate_price_at_upnl(entry, upnl_pct, side, leverage)


if __name__ == "__main__":
    # Test the calculator
    calc = LiquidationCalculator()

    print("=" * 60)
    print("LIQUIDATION CALCULATOR TEST")
    print("=" * 60)

    # Test LONG position
    entry = 50000
    leverage = 10

    result = calc.calculate_liquidation_details(entry, 'long', leverage)
    print(f"\nLONG Position @ ${entry:,.0f} with {leverage}x leverage:")
    print(f"  Liquidation price: ${result.liquidation_price:,.2f}")
    print(f"  Price distance: {result.price_distance_pct:.2f}%")
    print(f"  Margin ratio: {result.margin_ratio*100:.1f}%")
    print(f"  Maintenance margin: {result.maintenance_margin_rate*100:.2f}%")

    # Test protection price
    prot_price = calc.calculate_protection_price(entry, 'long', leverage)
    print(f"  Protection price (2.5% buffer): ${prot_price:,.2f}")

    # Test UPNL at -82.5%
    upnl_price = calc.calculate_price_at_upnl(entry, -82.5, 'long', leverage)
    print(f"  Price at -82.5% UPNL: ${upnl_price:,.2f}")

    # Test SHORT position
    result_short = calc.calculate_liquidation_details(entry, 'short', leverage)
    print(f"\nSHORT Position @ ${entry:,.0f} with {leverage}x leverage:")
    print(f"  Liquidation price: ${result_short.liquidation_price:,.2f}")
    print(f"  Price distance: {result_short.price_distance_pct:.2f}%")
