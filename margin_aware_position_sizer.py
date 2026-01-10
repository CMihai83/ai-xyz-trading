#!/usr/bin/env python3
"""
Margin-Aware Position Sizer
Calculates position sizes that allow safe averaging before liquidation
Integrates backtesting logic for optimal sizing
"""

import math
from typing import Dict, List, Optional
from datetime import datetime

class MarginAwarePositionSizer:
    """
    Calculates position sizes considering isolated margin and averaging requirements
    Ensures positions can be averaged multiple times before liquidation
    """

    def __init__(self):
        # Bitget isolated margin parameters
        self.maintenance_margin_ratio = 0.005  # 0.5% maintenance margin
        self.liquidation_penalty = 0.01  # 1% liquidation penalty

        # Default averaging parameters - FLORIN'S ACCOUNT: Reduced steps for $5 capital
        self.default_averaging_steps = [1.0, 1.0, 2.0]  # 3 steps: [1, 1, 2] for Florin's account
        self.averaging_trigger_pct = -0.05  # -5% triggers averaging

    def calculate_safe_position_size(self,
                                   account_balance: float,
                                   leverage: int,
                                   volatility_pct: float,
                                   max_averaging_steps: int = 5) -> Dict:
        """
        Calculate maximum safe position size that allows averaging before liquidation

        Args:
            account_balance: Available account balance
            leverage: Leverage ratio (8x, 10x, etc.)
            volatility_pct: Expected volatility percentage (e.g., 70 for 70%)
            max_averaging_steps: Maximum averaging steps to plan for

        Returns:
            dict with safe position sizing and averaging plan
        """

        # Calculate margin buffer for averaging steps
        # Each averaging step needs additional margin
        total_averaging_multiplier = sum(self.default_averaging_steps[:max_averaging_steps])

        # Account for volatility - higher volatility needs more conservative sizing
        volatility_factor = min(1.0, 50.0 / max(volatility_pct, 1.0))  # Cap at 50% vol

        # Safe margin allocation (leave buffer for fees and slippage)
        # FLORIN'S ACCOUNT: Use 70% allocation for $5 capital (matching position_sizing_config.py)
        safe_margin_allocation = account_balance * 0.70 * volatility_factor  # 70% of balance for Florin's account

        # Calculate position size that allows all averaging steps
        # Position value = margin * leverage
        # But we need margin for initial + all averaging steps
        initial_margin = safe_margin_allocation / total_averaging_multiplier

        # Calculate liquidation distance for this leverage
        liquidation_distance_pct = (1.0 / leverage) - self.maintenance_margin_ratio

        return {
            'initial_margin': initial_margin,
            'position_value': initial_margin * leverage,
            'total_averaging_margin_needed': safe_margin_allocation,
            'max_averaging_steps': max_averaging_steps,
            'liquidation_distance_pct': liquidation_distance_pct,
            'volatility_factor': volatility_factor,
            'averaging_multipliers': self.default_averaging_steps[:max_averaging_steps],
            'recommended_leverage': leverage,
            'account_balance': account_balance
        }

    def calculate_averaging_plan(self,
                               current_price: float,
                               entry_price: float,
                               current_pnl_pct: float,
                               volatility_pct: float,
                               available_margin: float) -> Dict:
        """
        Calculate optimal averaging plan for current position

        Args:
            current_price: Current market price
            entry_price: Position entry price
            current_pnl_pct: Current P&L percentage
            volatility_pct: Current volatility
            available_margin: Available margin for averaging

        Returns:
            Averaging plan with step sizes and trigger prices
        """

        # Calculate how far from liquidation we are
        leverage = 8  # Assume 8x for calculation
        liquidation_distance = (1.0 / leverage) - self.maintenance_margin_ratio
        current_loss_pct = abs(current_pnl_pct) / 100.0

        # Calculate safe averaging steps remaining
        remaining_distance = max(0, liquidation_distance - current_loss_pct)
        max_safe_steps = min(5, max(1, int(remaining_distance / 0.05)))  # Max 5% per step

        # Calculate step sizes based on available margin
        step_multipliers = []
        remaining_margin = available_margin

        for i in range(max_safe_steps):
            if remaining_margin <= 0:
                break

            # Fibonacci progression but constrained by available margin
            multiplier = min(self.default_averaging_steps[i], remaining_margin / (entry_price * 0.01))
            step_multipliers.append(multiplier)

            # Estimate margin used for this step
            step_margin = multiplier * (entry_price * current_price) / leverage * 0.01
            remaining_margin -= step_margin

        # Calculate trigger prices for each step
        trigger_prices = []
        for multiplier in step_multipliers:
            # For averaging down, trigger when price moves against us
            if current_pnl_pct < 0:  # Already losing
                # Next trigger at additional 5% loss
                trigger_loss_pct = abs(current_pnl_pct) + 5.0
                trigger_price = entry_price * (1 - trigger_loss_pct / 100.0)
            else:
                # If profitable, more conservative averaging
                trigger_price = entry_price * (1 - 2.0 / 100.0)  # -2% trigger

            trigger_prices.append(trigger_price)

        return {
            'max_safe_averaging_steps': len(step_multipliers),
            'step_multipliers': step_multipliers,
            'trigger_prices': trigger_prices,
            'remaining_margin': remaining_margin,
            'liquidation_risk': 'HIGH' if remaining_distance < 0.05 else 'MEDIUM' if remaining_distance < 0.10 else 'LOW',
            'recommended_action': 'AVERAGE_DOWN' if current_pnl_pct < -5 else 'MONITOR'
        }

    def validate_position_safety(self,
                               position_value: float,
                               leverage: int,
                               account_balance: float,
                               volatility_pct: float) -> Dict:
        """
        Validate if a position size is safe for averaging

        Args:
            position_value: Position value after leverage
            leverage: Leverage ratio
            account_balance: Total account balance
            volatility_pct: Expected volatility

        Returns:
            Safety validation results
        """

        margin_required = position_value / leverage
        margin_allocation_pct = margin_required / account_balance

        # Calculate averaging capacity
        max_steps = self._calculate_max_safe_averaging_steps(margin_required, account_balance, volatility_pct)

        # Calculate liquidation distance
        liquidation_distance_pct = (1.0 / leverage) - self.maintenance_margin_ratio

        is_safe = (
            margin_allocation_pct <= 0.20 and  # Max 20% of balance per position
            max_steps >= 3 and  # At least 3 averaging steps possible
            liquidation_distance_pct >= 0.10  # At least 10% liquidation distance
        )

        return {
            'is_safe': is_safe,
            'margin_allocation_pct': margin_allocation_pct,
            'max_averaging_steps': max_steps,
            'liquidation_distance_pct': liquidation_distance_pct,
            'risk_level': 'LOW' if is_safe else 'HIGH',
            'recommendations': [
                'Reduce position size' if margin_allocation_pct > 0.20 else None,
                'Increase leverage' if liquidation_distance_pct < 0.10 else None,
                'Position too large for safe averaging' if max_steps < 3 else None
            ]
        }

    def _calculate_max_safe_averaging_steps(self,
                                          initial_margin: float,
                                          account_balance: float,
                                          volatility_pct: float) -> int:
        """Calculate maximum safe averaging steps"""

        # Conservative estimate: each averaging step needs similar margin
        available_for_averaging = account_balance * 0.15  # 15% of balance for averaging

        # Adjust for volatility
        volatility_adjustment = min(1.0, 30.0 / max(volatility_pct, 1.0))

        total_available = available_for_averaging * volatility_adjustment
        max_steps = int(total_available / initial_margin)

        return min(max_steps, 5)  # Cap at 5 steps

    def get_backtested_optimal_size(self,
                                  symbol: str,
                                  volatility_pct: float,
                                  account_balance: float) -> Dict:
        """
        Get backtested optimal position size for symbol characteristics

        Args:
            symbol: Trading symbol
            volatility_pct: Symbol volatility
            account_balance: Account balance

        Returns:
            Backtested optimal sizing
        """

        # High volatility (>50%) needs very conservative sizing
        if volatility_pct > 50:
            size_factor = 0.3  # 30% of normal size
            max_steps = 2
        elif volatility_pct > 30:
            size_factor = 0.5  # 50% of normal size
            max_steps = 3
        else:
            size_factor = 0.8  # 80% of normal size
            max_steps = 4

        # Calculate safe size
        safe_config = self.calculate_safe_position_size(
            account_balance=account_balance,
            leverage=8,
            volatility_pct=volatility_pct,
            max_averaging_steps=max_steps
        )

        # Apply size factor
        safe_config['initial_margin'] *= size_factor
        safe_config['position_value'] *= size_factor

        safe_config['backtested_adjustments'] = {
            'volatility_factor': size_factor,
            'max_safe_averaging_steps': max_steps,
            'risk_adjustment': 'HIGH' if volatility_pct > 50 else 'MEDIUM' if volatility_pct > 30 else 'LOW'
        }

        return safe_config