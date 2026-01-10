#!/usr/bin/env python3
"""
Dynamic Position Sizer - Grok AI Optimized Formulas
Based on Grok API consultation (January 2026)

Dynamically calculates optimal position sizing based on:
- Delta (worst-case price movement)
- Volatility multiplier
- Market regime (LOW/NORMAL/HIGH volatility)

Goal: After all averaging steps, weighted average entry should be in
the 50% Fibonacci retracement zone for breakeven/profit on correction.
"""

from typing import List, Dict, Tuple
from dataclasses import dataclass
from position_sizing_config import PositionSizingConfig


@dataclass
class DynamicSizingResult:
    """Result of dynamic position sizing calculation"""
    initial_margin: float          # Initial margin before leverage
    num_steps: int                 # Number of averaging steps
    multipliers: List[int]         # Fibonacci multipliers for each step
    step_margins: List[float]      # Actual margin for each averaging step
    total_margin: float            # Total margin (initial + all steps)
    delta: float                   # Delta used for calculation
    regime: str                    # Market regime
    vol_mult: float                # Volatility multiplier used


class DynamicPositionSizer:
    """
    Adaptive position sizing based on market conditions.

    Core Formulas (from Grok AI):
    1. Initial Margin = base × (1/vol_mult) × regime_factor
    2. Num Steps = 3 + (delta - 1.5%) / 0.5% + regime_adjust
    3. Multipliers = Fibonacci sequence [1, 1, 2, 3, 5, 8, 13][:num_steps]

    Constraints:
    - Total margin <= TOTAL_CAPITAL ($25)
    - Last step is always largest (liquidation protection)
    - Weighted average positioned for 50% retracement recovery
    """

    # Regime adjustment factors
    REGIME_INITIAL_FACTORS = {
        'LOW_VOLATILITY': 1.2,      # Larger initial in calm markets
        'NORMAL_VOLATILITY': 1.0,   # Standard sizing
        'HIGH_VOLATILITY': 0.8      # Smaller initial, save for averaging
    }

    REGIME_STEP_ADJUST = {
        'LOW_VOLATILITY': -1,       # Fewer steps needed
        'NORMAL_VOLATILITY': 0,     # Standard steps
        'HIGH_VOLATILITY': 1        # More steps for protection
    }

    def __init__(self, total_capital: float = None):
        """
        Initialize dynamic position sizer.

        Args:
            total_capital: Total capital per position (default from config)
        """
        if total_capital is None:
            total_capital = PositionSizingConfig.TOTAL_CAPITAL

        self.total_capital = total_capital
        self.trading_capital = total_capital * PositionSizingConfig.TRADING_CAPITAL_PERCENT
        self.safety_reserve = total_capital * PositionSizingConfig.SAFETY_MARGIN_PERCENT

        print(f"📊 DynamicPositionSizer initialized")
        print(f"   Total Capital: ${total_capital:.2f}")
        print(f"   Trading Capital: ${self.trading_capital:.2f} (70%)")
        print(f"   Safety Reserve: ${self.safety_reserve:.2f} (30%)")

    def calc_initial_margin(self, delta: float, vol_mult: float, regime: str) -> float:
        """
        Calculate optimal initial margin based on delta and market conditions.

        Formula: base_margin × (1/vol_mult) × regime_factor

        Args:
            delta: Price movement percentage as decimal (e.g., 0.021 for 2.1%)
            vol_mult: Volatility multiplier (0.5 to 2.0)
            regime: Market regime (LOW_VOLATILITY, NORMAL_VOLATILITY, HIGH_VOLATILITY)

        Returns:
            Initial margin in dollars
        """
        # Base margin scales with delta - larger delta = need more for averaging
        # Use 20% of total capital as base, scaled by delta
        base_margin = self.total_capital * delta * 0.2

        # Volatility adjustment - higher volatility = smaller initial
        vol_adjust = 1 / max(vol_mult, 0.5)  # Prevent division issues

        # Regime adjustment
        regime_factor = self.REGIME_INITIAL_FACTORS.get(regime, 1.0)

        # Calculate initial margin
        initial_margin = base_margin * vol_adjust * regime_factor

        # Ensure minimum viable margin ($1) and maximum (50% of trading capital)
        min_margin = 1.0
        max_margin = self.trading_capital * 0.5
        initial_margin = max(min_margin, min(initial_margin, max_margin))

        return round(initial_margin, 2)

    def calc_num_steps(self, delta: float, regime: str) -> int:
        """
        Calculate optimal number of averaging steps.

        Formula: 3 + (delta - 0.015) / 0.005 + regime_adjust

        Args:
            delta: Price movement percentage as decimal
            regime: Market regime

        Returns:
            Number of steps (3-7)
        """
        # Base steps scale with delta
        # 1.5% delta = 3 steps, each 0.5% adds 1 step
        delta_pct = delta * 100  # Convert to percentage
        base_steps = 3 + int((delta_pct - 1.5) / 0.5)

        # Regime adjustment
        regime_adjust = self.REGIME_STEP_ADJUST.get(regime, 0)

        # Calculate total steps
        num_steps = base_steps + regime_adjust

        # Clamp to 3-7 range
        return max(3, min(7, num_steps))

    def calc_multipliers(self, num_steps: int) -> List[int]:
        """
        Generate Fibonacci multipliers for position sizing.

        Last multiplier is always largest for liquidation protection.

        Args:
            num_steps: Number of averaging steps

        Returns:
            List of Fibonacci multipliers
        """
        if num_steps <= 1:
            return [1]

        # Generate Fibonacci sequence
        multipliers = [1, 1]
        for i in range(2, num_steps):
            multipliers.append(multipliers[-1] + multipliers[-2])

        return multipliers

    def calc_step_margins(self, initial_margin: float, multipliers: List[int]) -> List[float]:
        """
        Calculate actual margin for each averaging step.

        Distributes remaining capital after initial margin across steps
        using Fibonacci multipliers.

        Args:
            initial_margin: Initial position margin
            multipliers: Fibonacci multipliers for each step

        Returns:
            List of margins for each averaging step
        """
        # Available capital for averaging (total - initial - safety reserve)
        available_for_averaging = self.trading_capital - initial_margin

        if available_for_averaging <= 0:
            return [0] * len(multipliers)

        # Sum of multipliers for proportional allocation
        total_mult = sum(multipliers)

        # Calculate margin for each step
        step_margins = []
        for mult in multipliers:
            step_margin = (mult / total_mult) * available_for_averaging
            step_margins.append(round(step_margin, 2))

        return step_margins

    def calculate_sizing(self, delta: float, vol_mult: float = 1.0,
                         regime: str = 'NORMAL_VOLATILITY') -> DynamicSizingResult:
        """
        Calculate complete dynamic position sizing.

        Main entry point - calculates all sizing parameters based on
        current market conditions.

        Args:
            delta: Price movement percentage as decimal (e.g., 0.021)
            vol_mult: Volatility multiplier (0.5-2.0)
            regime: Market regime

        Returns:
            DynamicSizingResult with all sizing parameters
        """
        # Normalize regime string
        regime = regime.upper().replace(' ', '_')
        if regime not in self.REGIME_INITIAL_FACTORS:
            regime = 'NORMAL_VOLATILITY'

        # Calculate each component
        initial_margin = self.calc_initial_margin(delta, vol_mult, regime)
        num_steps = self.calc_num_steps(delta, regime)
        multipliers = self.calc_multipliers(num_steps)
        step_margins = self.calc_step_margins(initial_margin, multipliers)

        # Total margin used
        total_margin = initial_margin + sum(step_margins)

        # Validate total doesn't exceed capital
        if total_margin > self.trading_capital:
            # Scale down step margins proportionally
            scale_factor = (self.trading_capital - initial_margin) / sum(step_margins)
            step_margins = [round(m * scale_factor, 2) for m in step_margins]
            total_margin = initial_margin + sum(step_margins)

        return DynamicSizingResult(
            initial_margin=initial_margin,
            num_steps=num_steps,
            multipliers=multipliers,
            step_margins=step_margins,
            total_margin=round(total_margin, 2),
            delta=delta,
            regime=regime,
            vol_mult=vol_mult
        )

    def get_sizing_for_symbol(self, delta: float, vol_mult: float,
                               regime: str, leverage: int = 10) -> Dict:
        """
        Get complete sizing information for a symbol.

        Convenience method that returns a dictionary with all sizing
        info including position values after leverage.

        Args:
            delta: Price movement percentage as decimal
            vol_mult: Volatility multiplier
            regime: Market regime
            leverage: Trading leverage

        Returns:
            Dictionary with sizing details
        """
        result = self.calculate_sizing(delta, vol_mult, regime)

        return {
            'initial_margin': result.initial_margin,
            'initial_position_value': result.initial_margin * leverage,
            'num_steps': result.num_steps,
            'multipliers': result.multipliers,
            'step_margins': result.step_margins,
            'step_position_values': [m * leverage for m in result.step_margins],
            'total_margin': result.total_margin,
            'total_position_value': result.total_margin * leverage,
            'safety_reserve': self.safety_reserve,
            'delta_percent': result.delta * 100,
            'regime': result.regime,
            'vol_mult': result.vol_mult,
            'leverage': leverage
        }


# Singleton instance for use across the system
_sizer_instance = None

def get_dynamic_sizer() -> DynamicPositionSizer:
    """Get or create singleton DynamicPositionSizer instance."""
    global _sizer_instance
    if _sizer_instance is None:
        _sizer_instance = DynamicPositionSizer()
    return _sizer_instance


# Example usage and testing
if __name__ == "__main__":
    print("=" * 60)
    print("DYNAMIC POSITION SIZER - GROK AI OPTIMIZED")
    print("=" * 60)

    sizer = DynamicPositionSizer(total_capital=25.0)

    # Test scenarios
    test_cases = [
        {'delta': 0.015, 'vol_mult': 0.8, 'regime': 'LOW_VOLATILITY', 'desc': 'Stable BTC'},
        {'delta': 0.021, 'vol_mult': 1.0, 'regime': 'NORMAL_VOLATILITY', 'desc': 'Normal SOL'},
        {'delta': 0.030, 'vol_mult': 1.2, 'regime': 'NORMAL_VOLATILITY', 'desc': 'Mid volatile'},
        {'delta': 0.040, 'vol_mult': 1.8, 'regime': 'HIGH_VOLATILITY', 'desc': 'Volatile DOGE'},
        {'delta': 0.050, 'vol_mult': 2.0, 'regime': 'HIGH_VOLATILITY', 'desc': 'Extreme meme'},
    ]

    for test in test_cases:
        print(f"\n{'-' * 60}")
        print(f"Scenario: {test['desc']}")
        print(f"Delta: {test['delta']*100:.1f}% | Vol Mult: {test['vol_mult']} | Regime: {test['regime']}")

        sizing = sizer.get_sizing_for_symbol(
            delta=test['delta'],
            vol_mult=test['vol_mult'],
            regime=test['regime'],
            leverage=10
        )

        print(f"\nResults:")
        print(f"  Initial Margin: ${sizing['initial_margin']:.2f}")
        print(f"  Initial Position: ${sizing['initial_position_value']:.2f} (10x)")
        print(f"  Num Steps: {sizing['num_steps']}")
        print(f"  Multipliers: {sizing['multipliers']}")
        print(f"  Step Margins: ${sizing['step_margins']}")
        print(f"  Total Margin: ${sizing['total_margin']:.2f}")
        print(f"  Safety Reserve: ${sizing['safety_reserve']:.2f}")
