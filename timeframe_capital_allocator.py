#!/usr/bin/env python3
"""
Timeframe-based Capital Allocation System
Distributes the full 70% capital ($17.50) across averaging steps based on timeframe expansion
"""

import numpy as np
from typing import Dict, List, Tuple
import structlog
from position_sizing_config import PositionSizingConfig

logger = structlog.get_logger(__name__)

class TimeframeCapitalAllocator:
    """
    Allocates capital based on timeframe expansion strategy
    Early timeframes (1m, 5m) get smaller allocations
    Later timeframes (1h, 4h, 1d) get larger allocations
    """
    
    # Timeframe hierarchy with relative capital weights
    # FLORIN'S ACCOUNT: 100% weight on single timeframe
    TIMEFRAME_WEIGHTS = {
        '1m': 1.00,   # 100% weight - all capital in initial position
        '5m': 0.00,   # Disabled
        '15m': 0.00,  # Disabled
        '1h': 0.00,   # Disabled
        '4h': 0.00,   # Disabled
        '1d': 0.00,   # Disabled
    }
    
    # Steps per timeframe (how many averaging steps in each timeframe)
    # 4 steps total (initial + 3 averaging) in single timeframe
    STEPS_PER_TIMEFRAME = {
        '1m': 4,   # 4 steps: Initial ($5.00) + 3 averaging steps
        '5m': 0,   # Disabled
        '15m': 0,  # Disabled
        '1h': 0,   # Disabled
        '4h': 0,   # Disabled
        '1d': 0,   # Disabled
    }
    
    def __init__(self, total_capital: float = None, allocation_percent: float = None, min_initial_position: float = None):
        """
        Initialize the capital allocator

        Args:
            total_capital: Total capital available (default from PositionSizingConfig)
            allocation_percent: Percent to allocate for trading (default 70%)
            min_initial_position: Minimum initial position size after leverage (default BASE_POSITION_VALUE)
        """
        # Use config values as defaults
        if total_capital is None:
            total_capital = PositionSizingConfig.TOTAL_CAPITAL  # $25
        if allocation_percent is None:
            allocation_percent = PositionSizingConfig.TRADING_CAPITAL_PERCENT  # 0.70
        if min_initial_position is None:
            min_initial_position = PositionSizingConfig.BASE_POSITION_VALUE  # $32.50 ($5 × 6.5x)
        self.total_capital = total_capital
        self.allocation_percent = allocation_percent
        self.trading_capital = total_capital * allocation_percent
        self.safety_reserve = total_capital * (1 - allocation_percent)
        self.min_initial_position = min_initial_position
        
        logger.info(
            "Initialized TimeframeCapitalAllocator",
            total_capital=total_capital,
            trading_capital=self.trading_capital,
            safety_reserve=self.safety_reserve
        )
    
    def calculate_timeframe_allocations(
        self,
        current_delta: float,
        leverage: int = 10,
        min_notional: float = None  # Will use PositionSizingConfig.BASE_MARGIN_SIZE * leverage if not provided
    ) -> Dict[str, Dict]:
        """
        Calculate capital allocation for each timeframe

        Args:
            current_delta: Current price delta percentage
            leverage: Trading leverage
            min_notional: Minimum notional position size after leverage (default: BASE_MARGIN_SIZE * leverage)

        Returns:
            Dictionary with allocations per timeframe
        """
        # Set default min_notional based on config if not provided
        if min_notional is None:
            min_notional = PositionSizingConfig.BASE_MARGIN_SIZE * leverage  # $5 × 10 = $50 notional

        allocations = {}
        remaining_capital = self.trading_capital

        # Determine which timeframes to use based on delta size
        active_timeframes = self._get_active_timeframes(current_delta)

        # Calculate minimum margin needed for initial position
        # Use configured base margin size from PositionSizingConfig
        min_initial_margin = PositionSizingConfig.BASE_MARGIN_SIZE  # $5.00 initial margin before leverage

        # Ensure first timeframe gets enough capital for min_initial_position
        # Reserve capital for initial position first
        reserved_for_initial = min_initial_margin * 2  # 2 steps in first timeframe
        remaining_for_other = max(0, self.trading_capital - reserved_for_initial)

        # Recalculate weights for active timeframes only
        active_weights = {tf: self.TIMEFRAME_WEIGHTS[tf] for tf in active_timeframes}
        total_weight = sum(active_weights.values())
        normalized_weights = {tf: w/total_weight for tf, w in active_weights.items()}

        # Calculate minimum position size
        min_position_margin = min_notional / leverage
        
        # Allocate capital per timeframe
        is_first_timeframe = True
        for timeframe in active_timeframes:
            steps = self.STEPS_PER_TIMEFRAME.get(timeframe, 1)

            if steps > 0:
                # First timeframe gets reserved capital to ensure min_initial_position
                if is_first_timeframe:
                    capital_per_step = min_initial_margin
                    tf_capital = capital_per_step * steps
                    is_first_timeframe = False
                else:
                    # Other timeframes share remaining capital proportionally
                    tf_capital = remaining_for_other * normalized_weights[timeframe]
                    capital_per_step = tf_capital / steps

                # Ensure minimum position size
                if capital_per_step < min_position_margin:
                    capital_per_step = min_position_margin
                    tf_capital = capital_per_step * steps

                allocations[timeframe] = {
                    'total_capital': tf_capital,
                    'steps': steps,
                    'capital_per_step': capital_per_step,
                    'weight': normalized_weights[timeframe],
                    'leverage': self._get_optimal_leverage(timeframe, capital_per_step, min_notional)
                }

                remaining_capital -= tf_capital
        
        # If we have remaining capital, distribute it to later timeframes
        if remaining_capital > 0:
            self._redistribute_remaining(allocations, remaining_capital, min_position_margin)
        
        # Calculate total utilization
        total_used = sum(a['total_capital'] for a in allocations.values())
        
        logger.info(
            "Calculated timeframe allocations",
            total_trading_capital=self.trading_capital,
            total_used=total_used,
            utilization_percent=total_used/self.trading_capital*100,
            allocations=allocations
        )
        
        return allocations
    
    def _get_active_timeframes(self, delta: float) -> List[str]:
        """
        Determine which timeframes to activate based on delta size
        Larger deltas activate more timeframes
        """
        if delta < 0.01:  # < 1% delta
            return ['1m', '5m']
        elif delta < 0.02:  # < 2% delta
            return ['1m', '5m', '15m']
        elif delta < 0.03:  # < 3% delta
            return ['1m', '5m', '15m', '1h']
        elif delta < 0.05:  # < 5% delta
            return ['1m', '5m', '15m', '1h', '4h']
        else:  # >= 5% delta
            return ['1m', '5m', '15m', '1h', '4h', '1d']
    
    def _get_optimal_leverage(self, timeframe: str, capital: float, min_notional: float) -> int:
        """
        Calculate optimal leverage for a timeframe
        Early timeframes use higher leverage (smaller position, more risk)
        Later timeframes use lower leverage (larger position, less risk)
        """
        leverage_map = {
            '1m': 10,  # Maximum leverage for smallest positions
            '5m': 8,   # High leverage
            '15m': 6,  # Medium leverage
            '1h': 5,   # Lower leverage
            '4h': 4,   # Conservative leverage
            '1d': 3,   # Minimum leverage for largest positions
        }
        
        base_leverage = leverage_map.get(timeframe, 5)
        
        # Ensure minimum notional is met
        required_leverage = min_notional / capital
        if required_leverage > base_leverage:
            return min(10, int(np.ceil(required_leverage)))
        
        return base_leverage
    
    def _redistribute_remaining(
        self,
        allocations: Dict,
        remaining: float,
        min_margin: float
    ):
        """
        Redistribute remaining capital to later timeframes
        Priority: 1d > 4h > 1h > 15m > 5m > 1m
        """
        priority_order = ['1d', '4h', '1h', '15m', '5m', '1m']
        
        for timeframe in priority_order:
            if remaining <= 0:
                break
                
            if timeframe in allocations:
                # Add remaining to this timeframe
                additional = min(remaining, allocations[timeframe]['total_capital'] * 0.5)
                allocations[timeframe]['total_capital'] += additional
                allocations[timeframe]['capital_per_step'] = (
                    allocations[timeframe]['total_capital'] / 
                    allocations[timeframe]['steps']
                )
                remaining -= additional
    
    def calculate_dynamic_multipliers(
        self,
        allocations: Dict[str, Dict],
        current_timeframe: str
    ) -> List[float]:
        """
        Calculate position multipliers based on current timeframe and allocations
        
        Returns:
            List of multipliers for each averaging step
        """
        multipliers = []
        
        # Get all timeframes from current onwards
        all_timeframes = list(self.TIMEFRAME_WEIGHTS.keys())
        start_idx = all_timeframes.index(current_timeframe)
        active_timeframes = all_timeframes[start_idx:]
        
        for tf in active_timeframes:
            if tf in allocations:
                steps = allocations[tf]['steps']
                capital_per_step = allocations[tf]['capital_per_step']
                
                # Calculate multiplier relative to initial position
                # Assuming initial position uses minimum allocation
                initial_capital = min(a['capital_per_step'] for a in allocations.values())
                multiplier = capital_per_step / initial_capital
                
                # Add multiplier for each step in this timeframe
                for _ in range(steps):
                    multipliers.append(multiplier)
        
        return multipliers
    
    def get_averaging_plan(
        self,
        entry_price: float,
        delta: float,
        direction: str = 'long',
        current_balance: float = None
    ) -> Dict:
        """
        Get complete averaging plan with full capital utilization
        
        Returns:
            Dictionary with complete averaging configuration
        """
        # Use actual balance if provided and less than max
        if current_balance and current_balance < self.total_capital:
            self.total_capital = current_balance
            self.trading_capital = current_balance * self.allocation_percent
            self.safety_reserve = current_balance * (1 - self.allocation_percent)
        
        # Get allocations
        allocations = self.calculate_timeframe_allocations(delta)
        
        # Build averaging steps
        averaging_steps = []
        cumulative_margin = 0
        step_number = 0
        
        for timeframe, allocation in allocations.items():
            steps_in_tf = allocation['steps']
            capital_per_step = allocation['capital_per_step']
            leverage = allocation['leverage']
            
            # Calculate delta for this timeframe (scales with timeframe)
            tf_delta_multiplier = {
                '1m': 1.0,
                '5m': 1.5,
                '15m': 2.0,
                '1h': 3.0,
                '4h': 5.0,
                '1d': 8.0
            }.get(timeframe, 1.0)
            
            tf_delta = delta * tf_delta_multiplier
            
            for step_in_timeframe in range(steps_in_tf):
                step_number += 1
                cumulative_margin += capital_per_step
                
                # Calculate trigger price for this step
                price_movement = tf_delta * (step_in_timeframe + 1) / steps_in_tf
                if direction == 'long':
                    trigger_price = entry_price * (1 - price_movement)
                else:
                    trigger_price = entry_price * (1 + price_movement)
                
                averaging_steps.append({
                    'step': step_number,
                    'timeframe': timeframe,
                    'margin': capital_per_step,
                    'cumulative_margin': cumulative_margin,
                    'leverage': leverage,
                    'trigger_price': trigger_price,
                    'delta_from_entry': price_movement,
                    'notional_size': capital_per_step * leverage
                })
        
        # Calculate final statistics
        total_steps = len(averaging_steps)
        total_margin_used = sum(s['margin'] for s in averaging_steps)
        utilization = total_margin_used / self.trading_capital * 100
        
        return {
            'total_capital': self.total_capital,
            'trading_capital': self.trading_capital,
            'safety_reserve': self.safety_reserve,
            'total_margin_used': total_margin_used,
            'utilization_percent': utilization,
            'total_steps': total_steps,
            'allocations_by_timeframe': allocations,
            'averaging_steps': averaging_steps,
            'initial_margin': averaging_steps[0]['margin'] if averaging_steps else 0,
            'max_leverage': max(s['leverage'] for s in averaging_steps) if averaging_steps else 10
        }


# Example usage and testing
if __name__ == "__main__":
    # Test the allocator
    allocator = TimeframeCapitalAllocator(total_capital=25.0, allocation_percent=0.70)
    
    # Test with different delta sizes
    test_deltas = [0.01, 0.025, 0.05]
    
    for delta in test_deltas:
        print(f"\n{'='*60}")
        print(f"Testing with delta: {delta*100:.1f}%")
        print('='*60)
        
        plan = allocator.get_averaging_plan(
            entry_price=100.0,
            delta=delta,
            direction='long'
        )
        
        print(f"\nCapital Distribution:")
        print(f"  Total Capital: ${plan['total_capital']:.2f}")
        print(f"  Trading Capital: ${plan['trading_capital']:.2f}")
        print(f"  Safety Reserve: ${plan['safety_reserve']:.2f}")
        print(f"  Total Used: ${plan['total_margin_used']:.2f}")
        print(f"  Utilization: {plan['utilization_percent']:.1f}%")
        print(f"  Total Steps: {plan['total_steps']}")
        
        print(f"\nTimeframe Allocations:")
        for tf, alloc in plan['allocations_by_timeframe'].items():
            print(f"  {tf:3s}: ${alloc['total_capital']:6.2f} ({alloc['steps']} steps @ ${alloc['capital_per_step']:.2f}/step, {alloc['leverage']}x leverage)")
        
        print(f"\nAveraging Steps:")
        for step in plan['averaging_steps']:
            print(f"  Step {step['step']}: {step['timeframe']:3s} - ${step['margin']:.2f} @ {step['leverage']}x = ${step['notional_size']:.2f} notional (trigger: ${step['trigger_price']:.2f})")