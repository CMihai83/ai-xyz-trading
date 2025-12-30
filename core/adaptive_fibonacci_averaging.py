"""
Adaptive Fibonacci Averaging Calculator with Dynamic K Coefficient
STATUS: PRODUCTION READY
Cardinal Rules: Rule 4 (Averaging Steps Must Be Tracked), Rule 7 (Position Risk Monitoring)
INTEGRATION: Uses FibonacciDeltaCalculator for optimal delta determination

KEY CONCEPTS:
=============
1. DELTA SOURCE:
   - Delta (max price movement) is PROVIDED by FibonacciDeltaCalculator service
   - This module does NOT calculate delta - it only distributes it
   - Delta comes from: /app/services/api-gateway/src/fibonacci_delta_calculator.py

2. FIBONACCI SEQUENCE GENERATION:
   - For n steps, uses Fibonacci numbers from F(n+3) down to F(4)=3
   - Examples:
     * 3 steps: [8, 5, 3] = [F(6), F(5), F(4)]
     * 4 steps: [13, 8, 5, 3] = [F(7), F(6), F(5), F(4)]
     * 5 steps: [21, 13, 8, 5, 3] = [F(8), F(7), F(6), F(5), F(4)]
   - IMPORTANT: Last number is ALWAYS 3, never 2 or 1

3. DELTA DISTRIBUTION (NOT CALCULATION):
   - Each step's threshold = Fibonacci_number / Sum_of_all_Fibonacci_numbers
   - Example for 5 steps [21, 13, 8, 5, 3]:
     * Sum = 50
     * Step 1: 21/50 = 42% of max delta
     * Step 2: 13/50 = 26% of max delta
     * Step 3: 8/50 = 16% of max delta
     * Step 4: 5/50 = 10% of max delta
     * Step 5: 3/50 = 6% of max delta

3. TRIGGER PRICE CALCULATION:
   - Uses CUMULATIVE thresholds, not individual
   - Cumulative = sum of all thresholds up to that step
   - Example for entry=10000, delta=1000:
     * Step 1: 42% cumulative → trigger at 9580
     * Step 2: 68% cumulative → trigger at 9320
     * Step 3: 84% cumulative → trigger at 9160
     * Step 4: 94% cumulative → trigger at 9060
     * Step 5: 100% cumulative → trigger at 9000

4. BACKTESTING CAPABILITY:
   - Tests 3-7 steps to find optimal configuration
   - Scores based on: steps executed, K coefficient, safety distance, margin efficiency
   - Automatically selects best number of steps for given parameters

5. K COEFFICIENT:
   - Multiplier for position sizing at each step
   - Automatically optimized to maximize steps while maintaining safety
   - Lower K = more conservative, more steps possible
"""

import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
import structlog
import sys
import os

# Add path for imports
sys.path.insert(0, '/app/services/api-gateway/src')

logger = structlog.get_logger(__name__)

@dataclass
class AdaptiveFibonacciConfig:
    """Configuration for adaptive Fibonacci averaging"""
    k_coefficient: float
    multipliers: List[float]
    delta_thresholds: List[float]
    margin_allocations: List[float]
    trigger_prices: List[float]
    liquidation_prices: List[float]
    safety_distances: List[float]
    max_safe_steps: int
    total_margin_required: float
    final_avg_entry: float
    final_position_size: float

class AdaptiveFibonacciCalculator:
    """
    Calculates optimal Fibonacci-based averaging strategy with automatic K coefficient
    that ensures all averaging steps maintain minimum distance from liquidation.
    """
    
    # Constants
    FIBONACCI_BASE = [1, 1, 2, 3, 5, 8, 13]
    # Fibonacci numbers from F(7) onwards in reverse order for delta calculation
    FIBONACCI_DELTA_SEQUENCE = [21, 13, 8, 5, 3]  # F(7), F(6), F(5), F(4), F(3)
    MIN_DISTANCE_FROM_LIQUIDATION = 0.10  # 10% minimum distance
    MAINTENANCE_MARGIN_RATE = 0.005  # 0.5% for Bitget futures
    SAFETY_MARGIN_PERCENT = 0.30  # 30% safety reserve
    
    def __init__(self, num_steps: int = 5):
        """
        Initialize calculator with specified number of averaging steps.
        
        Args:
            num_steps: Number of averaging steps to use (3-7)
        """
        self.logger = structlog.get_logger(self.__class__.__name__)
        self.num_steps = min(max(num_steps, 3), 7)  # Clamp between 3 and 7
        
        # Generate Fibonacci sequence for the number of steps
        self.fibonacci_sequence = self._generate_fibonacci_sequence(self.num_steps)
        
        # Calculate delta thresholds based on Fibonacci sequence
        self.delta_thresholds, self.cumulative_thresholds = self._calculate_delta_thresholds()
    
    def _generate_fibonacci_sequence(self, n: int) -> List[int]:
        """
        Generate Fibonacci sequence for n steps in REVERSE order.
        
        CRITICAL RULE: The last number is ALWAYS 3 (F(4)), never 2 or 1!
        
        Pattern Explanation:
        ====================
        For n steps, we use n consecutive Fibonacci numbers from F(n+3) down to F(4).
        This ensures larger multipliers for earlier steps and always ends with 3.
        
        Examples:
        ---------
        3 steps: [8, 5, 3]           = [F(6), F(5), F(4)]
        4 steps: [13, 8, 5, 3]        = [F(7), F(6), F(5), F(4)]
        5 steps: [21, 13, 8, 5, 3]    = [F(8), F(7), F(6), F(5), F(4)]
        6 steps: [34, 21, 13, 8, 5, 3] = [F(9), F(8), F(7), F(6), F(5), F(4)]
        7 steps: [55, 34, 21, 13, 8, 5, 3] = [F(10), F(9), F(8), F(7), F(6), F(5), F(4)]
        
        Why this pattern?
        -----------------
        1. Larger Fibonacci numbers for initial steps = larger position sizes early
        2. Consistent ending at F(4)=3 ensures predictable final step
        3. Matches proven Excel averaging model with optimal risk distribution
        
        Args:
            n: Number of averaging steps (3-7 typically)
            
        Returns:
            List of Fibonacci numbers in reverse order, ALWAYS ending with 3
        """
        # Complete Fibonacci sequence reference
        # Index: 0    1    2    3    4    5    6     7     8     9     10    11    12
        # F(n):  F(1) F(2) F(3) F(4) F(5) F(6) F(7)  F(8)  F(9)  F(10) F(11) F(12) F(13)
        fib = [1,    1,   2,   3,   5,   8,   13,   21,   34,   55,   89,   144,  233]
        
        # IMPORTANT: We explicitly define each case to ensure correctness
        # The pattern MUST end with 3 (F(4)) for all cases
        
        if n == 3:
            sequence = [8, 5, 3]  # F(6), F(5), F(4)
        elif n == 4:
            sequence = [13, 8, 5, 3]  # F(7), F(6), F(5), F(4)
        elif n == 5:
            # This matches the Excel example exactly
            sequence = [21, 13, 8, 5, 3]  # F(8), F(7), F(6), F(5), F(4)
        elif n == 6:
            sequence = [34, 21, 13, 8, 5, 3]  # F(9), F(8), F(7), F(6), F(5), F(4)
        elif n == 7:
            sequence = [55, 34, 21, 13, 8, 5, 3]  # F(10), F(9), F(8), F(7), F(6), F(5), F(4)
        else:
            # General case for n > 7 or unexpected values
            # Start at F(n+3) and work backwards n times
            start_idx = n + 3  
            sequence = []
            for i in range(n):
                if start_idx - i < len(fib):
                    sequence.append(fib[start_idx - i])
                else:
                    # If we run out of pre-computed values, generate them
                    # This should rarely happen with our typical 3-7 step range
                    sequence.append(3)  # Fallback to 3
            
            # CRITICAL: Ensure the sequence ALWAYS ends with 3
            if len(sequence) > 0 and sequence[-1] != 3:
                sequence[-1] = 3
        
        return sequence
    
    def _calculate_delta_thresholds(self) -> Tuple[List[float], List[float]]:
        """
        Calculate delta thresholds based on Fibonacci numbers.
        
        CRITICAL CONCEPT:
        ================
        1. Individual threshold = Fibonacci_number / Sum_of_all_Fibonacci_numbers
           - This gives the percentage of max delta for each step
        
        2. Cumulative threshold = Sum of all individual thresholds up to that step
           - This is used for trigger price calculation
           - MUST use cumulative, not individual, for correct trigger prices!
        
        Example for [21, 13, 8, 5, 3]:
        - Individual: [0.42, 0.26, 0.16, 0.10, 0.06]
        - Cumulative: [0.42, 0.68, 0.84, 0.94, 1.00]
        
        Returns:
            Tuple of (individual_thresholds, cumulative_thresholds)
        """
        # Calculate sum of all Fibonacci numbers in sequence
        total_sum = sum(self.fibonacci_sequence)
        
        # Individual thresholds: each Fibonacci number as percentage of total
        individual_thresholds = [fib / total_sum for fib in self.fibonacci_sequence]
        
        # IMPORTANT: Calculate cumulative thresholds for trigger prices
        # This is what determines the actual price levels for averaging
        cumulative_thresholds = []
        cumulative_sum = 0
        for threshold in individual_thresholds:
            cumulative_sum += threshold
            cumulative_thresholds.append(cumulative_sum)
        
        self.logger.debug(
            "Calculated delta thresholds",
            num_steps=self.num_steps,
            fibonacci_sequence=self.fibonacci_sequence,
            total_sum=total_sum,
            individual_thresholds=individual_thresholds,
            cumulative_thresholds=cumulative_thresholds
        )
        
        return individual_thresholds, cumulative_thresholds
    
    def calculate_liquidation_price(
        self, 
        avg_entry: float, 
        total_margin: float, 
        total_contracts: float,
        leverage: float,
        is_long: bool = True,
        include_safety: bool = False,
        safety_amount: float = 0
    ) -> float:
        """
        Calculate liquidation price for a futures position
        
        Args:
            avg_entry: Average entry price
            total_margin: Total margin used
            total_contracts: Total position contracts
            leverage: Position leverage
            is_long: True for long position, False for short
            include_safety: Whether to include safety margin
            safety_amount: Amount of safety margin to add
        
        Returns:
            Liquidation price
        """
        margin_to_use = total_margin + (safety_amount if include_safety else 0)
        position_value = avg_entry * total_contracts
        margin_ratio = margin_to_use / position_value if position_value > 0 else 0
        
        if is_long:
            liq_price = avg_entry * (1 - margin_ratio + self.MAINTENANCE_MARGIN_RATE)
        else:
            liq_price = avg_entry * (1 + margin_ratio - self.MAINTENANCE_MARGIN_RATE)
        
        return liq_price
    
    def find_optimal_k(
        self,
        initial_price: float,
        leverage: float,
        initial_margin: float,
        available_margin: float,
        total_delta: float,
        is_long: bool = True,
        k_search_range: Tuple[float, float] = (0.1, 3.0),
        k_step: float = 0.05
    ) -> Tuple[float, int, List[Dict]]:
        """
        Find the optimal K coefficient that maximizes averaging steps while maintaining safety
        
        Args:
            initial_price: Initial entry price
            leverage: Position leverage
            initial_margin: Initial position margin
            available_margin: Total margin available for averaging
            total_delta: Maximum price movement (delta) to cover
            is_long: True for long position, False for short
            k_search_range: Range of K values to test
            k_step: Step size for K search
        
        Returns:
            Tuple of (optimal_k, max_steps, step_details)
        """
        best_k = 0
        best_steps = 0
        best_details = []
        
        # Test different K values
        for k in np.arange(k_search_range[0], k_search_range[1], k_step):
            test_details = []
            cumulative_margin = initial_margin
            cumulative_size = initial_margin * leverage
            cumulative_contracts = cumulative_size / initial_price
            weighted_sum = initial_price * cumulative_contracts
            
            can_continue = True
            steps_executed = 0
            
            for step_num in range(len(self.cumulative_thresholds)):
                if not can_continue or step_num >= len(self.FIBONACCI_BASE):
                    break
                
                # CRITICAL: Use CUMULATIVE threshold for trigger price
                # This ensures each step triggers at the right total delta from entry
                cumulative_threshold = self.cumulative_thresholds[step_num]
                fib = self.FIBONACCI_BASE[step_num]
                
                # Calculate trigger price based on CUMULATIVE delta threshold
                # Example: Step 2 at 68% means price moved 68% of max_delta from entry
                if is_long:
                    trigger_price = initial_price - (total_delta * cumulative_threshold)
                else:
                    trigger_price = initial_price + (total_delta * cumulative_threshold)
                
                # Calculate margin for this step
                step_margin = initial_margin * fib * k
                
                # Check if we exceed available margin
                if cumulative_margin + step_margin > available_margin:
                    remaining = available_margin - cumulative_margin
                    if remaining < 0.1:  # Minimum meaningful margin
                        break
                    step_margin = remaining
                
                # Simulate adding this position
                test_cumul_margin = cumulative_margin + step_margin
                test_step_size = step_margin * leverage
                test_step_contracts = test_step_size / trigger_price
                test_cumul_size = cumulative_size + test_step_size
                test_cumul_contracts = cumulative_contracts + test_step_contracts
                test_weighted_sum = weighted_sum + (trigger_price * test_step_contracts)
                test_avg_entry = test_weighted_sum / test_cumul_contracts
                
                # Calculate liquidation price with new position
                test_liq_price = self.calculate_liquidation_price(
                    test_avg_entry, 
                    test_cumul_margin, 
                    test_cumul_contracts,
                    leverage,
                    is_long
                )
                
                # Check if trigger price is safely above/below liquidation
                if is_long:
                    distance_to_liq = (trigger_price - test_liq_price) / trigger_price
                else:
                    distance_to_liq = (test_liq_price - trigger_price) / trigger_price
                
                if distance_to_liq < self.MIN_DISTANCE_FROM_LIQUIDATION:
                    # This step would be too close to liquidation
                    can_continue = False
                    break
                
                # Step is safe, update values
                cumulative_margin = test_cumul_margin
                cumulative_size = test_cumul_size
                cumulative_contracts = test_cumul_contracts
                weighted_sum = test_weighted_sum
                steps_executed += 1
                
                test_details.append({
                    'step': step_num + 1,
                    'k': k,
                    'margin': cumulative_margin,
                    'liq_price': test_liq_price,
                    'trigger_price': trigger_price,
                    'distance': distance_to_liq,
                    'avg_entry': test_avg_entry
                })
            
            # Check if this K is better (more steps or same steps with lower K)
            if steps_executed > best_steps or (steps_executed == best_steps and k < best_k):
                best_k = k
                best_steps = steps_executed
                best_details = test_details
        
        return best_k, best_steps, best_details
    
    
    def calculate_adaptive_config(
        self,
        position_data: Dict
    ) -> AdaptiveFibonacciConfig:
        """
        Calculate complete adaptive Fibonacci configuration for a position.
        
        IMPORTANT: This method RECEIVES max_delta from FibonacciDeltaCalculator service.
        It does NOT calculate delta itself - only distributes it across Fibonacci steps.
        
        Args:
            position_data: Dictionary containing:
                - entry_price: Initial entry price
                - leverage: Position leverage
                - initial_margin: Initial margin amount
                - total_margin: Total margin available (including safety)
                - max_delta: Maximum price movement (PROVIDED by FibonacciDeltaCalculator)
                - direction: 'long' or 'short'
        
        Returns:
            AdaptiveFibonacciConfig with all calculated parameters
        """
        # Extract parameters
        initial_price = position_data['entry_price']
        leverage = position_data['leverage']
        initial_margin = position_data['initial_margin']
        total_margin = position_data['total_margin']
        max_delta = position_data['max_delta']
        is_long = position_data.get('direction', 'long') == 'long'
        
        # Calculate available margin (excluding safety reserve)
        safety_reserve = total_margin * self.SAFETY_MARGIN_PERCENT
        available_margin = total_margin - safety_reserve
        
        # Find optimal K coefficient
        optimal_k, max_steps, step_details = self.find_optimal_k(
            initial_price,
            leverage,
            initial_margin,
            available_margin,
            max_delta,
            is_long
        )
        
        # Build complete configuration
        multipliers = []
        margin_allocations = []
        trigger_prices = []
        liquidation_prices = []
        safety_distances = []
        
        cumulative_margin = initial_margin
        cumulative_size = initial_margin * leverage
        cumulative_contracts = cumulative_size / initial_price
        weighted_sum = initial_price * cumulative_contracts
        
        for i in range(min(max_steps, len(self.cumulative_thresholds), len(self.FIBONACCI_BASE))):
            # IMPORTANT: Use CUMULATIVE threshold, not individual!
            # This is the key to matching the Excel example
            cumulative_threshold = self.cumulative_thresholds[i]
            fib = self.FIBONACCI_BASE[i]
            
            # Calculate trigger price using CUMULATIVE threshold
            # Each step triggers when total price movement reaches cumulative percentage
            if is_long:
                trigger_price = initial_price - (max_delta * cumulative_threshold)
            else:
                trigger_price = initial_price + (max_delta * cumulative_threshold)
            
            # Calculate multiplier and margin
            multiplier = fib * optimal_k
            step_margin = initial_margin * multiplier
            
            # Check margin limit
            if cumulative_margin + step_margin > available_margin:
                step_margin = available_margin - cumulative_margin
                multiplier = step_margin / initial_margin
            
            # Update cumulative values
            step_size = step_margin * leverage
            step_contracts = step_size / trigger_price
            cumulative_margin += step_margin
            cumulative_size += step_size
            cumulative_contracts += step_contracts
            weighted_sum += trigger_price * step_contracts
            avg_entry = weighted_sum / cumulative_contracts
            
            # Calculate liquidation prices
            liq_price = self.calculate_liquidation_price(
                avg_entry, cumulative_margin, cumulative_contracts, leverage, is_long
            )
            liq_with_safety = self.calculate_liquidation_price(
                avg_entry, cumulative_margin, cumulative_contracts, leverage, is_long,
                include_safety=True, safety_amount=safety_reserve
            )
            
            # Calculate safety distance
            if is_long:
                safety_distance = (trigger_price - liq_price) / trigger_price
            else:
                safety_distance = (liq_price - trigger_price) / trigger_price
            
            # Store configuration
            multipliers.append(multiplier)
            margin_allocations.append(step_margin)
            trigger_prices.append(trigger_price)
            liquidation_prices.append(liq_price)
            safety_distances.append(safety_distance)
        
        # Final values
        final_avg_entry = weighted_sum / cumulative_contracts if cumulative_contracts > 0 else initial_price
        final_position_size = cumulative_size
        
        config = AdaptiveFibonacciConfig(
            k_coefficient=optimal_k,
            multipliers=multipliers,
            delta_thresholds=self.delta_thresholds[:max_steps],
            margin_allocations=margin_allocations,
            trigger_prices=trigger_prices,
            liquidation_prices=liquidation_prices,
            safety_distances=safety_distances,
            max_safe_steps=max_steps,
            total_margin_required=cumulative_margin,
            final_avg_entry=final_avg_entry,
            final_position_size=final_position_size
        )
        
        self.logger.info(
            "Calculated adaptive Fibonacci configuration",
            k_coefficient=optimal_k,
            max_safe_steps=max_steps,
            total_margin=cumulative_margin,
            final_avg_entry=final_avg_entry,
            min_safety_distance=min(safety_distances) if safety_distances else 0
        )
        
        return config
    
    def format_averaging_plan(self, config: AdaptiveFibonacciConfig, position_data: Dict) -> List[Dict]:
        """
        Format the averaging plan for position metadata
        
        CRITICAL: Each step includes BOTH price trigger AND UPNL% trigger.
        Averaging happens at WHICHEVER COMES FIRST to prevent liquidation.
        
        Returns:
            List of averaging step dictionaries for position metadata
        """
        averaging_steps = []
        leverage = position_data.get('leverage', 10)
        
        for i in range(config.max_safe_steps):
            # Calculate UPNL percentage threshold for this step
            # This is based on cumulative margin used vs initial margin
            cumulative_margin = sum(config.margin_allocations[:i+1]) + position_data['initial_margin']
            
            # CORRECT: Convert price delta to UPNL threshold (as in Excel)
            # UPNL = (current_price - entry_price) × quantity
            
            entry_price = position_data['entry_price']
            trigger_price = config.trigger_prices[i]
            initial_margin = position_data['initial_margin']
            
            # Calculate initial position quantity
            initial_quantity = (initial_margin * leverage) / entry_price
            
            # Calculate UPNL in dollars at the trigger price
            # For LONG: UPNL = (trigger_price - entry_price) × quantity
            # For SHORT: UPNL = (entry_price - trigger_price) × quantity
            if position_data.get('direction', 'long') == 'long':
                price_delta = trigger_price - entry_price
            else:
                price_delta = entry_price - trigger_price
            
            # UPNL in dollars for initial position at trigger price
            upnl_dollars_at_trigger = price_delta * initial_quantity
            
            # UPNL% relative to initial margin (for safety check)
            upnl_pct_threshold = upnl_dollars_at_trigger / initial_margin if initial_margin > 0 else 0
            
            # Safety: Cap at -85% of margin to prevent liquidation at -100%
            if upnl_pct_threshold < -0.85:
                self.logger.warning(
                    f"Step {i+1} UPNL capped at -85% (was {upnl_pct_threshold:.1%})",
                    step=i+1,
                    original=upnl_pct_threshold
                )
                upnl_pct_threshold = -0.85
                # Recalculate the dollar threshold based on capped percentage
                upnl_dollars_at_trigger = initial_margin * upnl_pct_threshold
            
            # CRITICAL: Apply -85% UPNL safety limit
            # If calculated threshold would exceed -85%, cap it at -85%
            # This ensures averaging happens BEFORE liquidation at -100%
            # NOTE: This is redundant with the check above but kept for clarity
            if upnl_pct_threshold < -0.85:
                self.logger.warning(
                    f"Step {i+1} UPNL threshold capped at -85% (was {upnl_pct_threshold:.1%})",
                    step=i+1,
                    original_threshold=upnl_pct_threshold,
                    capped_threshold=-0.85
                )
                upnl_pct_threshold = -0.85
                # Recalculate trigger price based on -85% UPNL limit
                if position_data.get('direction', 'long') == 'long':
                    trigger_price = entry_price * (1 + upnl_pct_threshold / leverage)
                else:
                    trigger_price = entry_price * (1 - upnl_pct_threshold / leverage)
            else:
                # upnl_pct_threshold already set above, no need to reassign
                pass
            
            # Store UPNL dollar threshold for this step (as in Excel)
            # This is the UPNL$ that triggers averaging
            upnl_dollar_threshold = upnl_dollars_at_trigger
            
            step = {
                'step_number': i + 1,
                'price': trigger_price,
                'delta_threshold': config.delta_thresholds[i],
                'delta_absolute': config.delta_thresholds[i] * position_data['max_delta'],
                'position_multiplier': config.multipliers[i],
                'margin_allocation': config.margin_allocations[i],
                'fibonacci_weight': self.FIBONACCI_BASE[i] if i < len(self.FIBONACCI_BASE) else self.FIBONACCI_BASE[-1],
                'fibonacci_delta': self.fibonacci_sequence[i] if i < len(self.fibonacci_sequence) else self.fibonacci_sequence[-1],
                'k_coefficient': config.k_coefficient,
                'liquidation_price': config.liquidation_prices[i],
                'safety_distance': config.safety_distances[i],
                'cumulative_margin': cumulative_margin,
                'upnl_dollar_threshold': upnl_dollar_threshold,  # UPNL$ trigger (from Excel)
                'upnl_pct_threshold': upnl_pct_threshold,  # UPNL% relative to margin
                'trigger_condition': 'upnl_dollar OR price',  # Triggers on EITHER
                'liquidation_safety': upnl_pct_threshold > -0.85  # True if safe from liquidation
            }
            averaging_steps.append(step)
        
        return averaging_steps
    
    def validate_safety(self, config: AdaptiveFibonacciConfig) -> bool:
        """
        Validate that all averaging steps maintain minimum safety distance
        
        Returns:
            True if all steps are safe, False otherwise
        """
        for i, distance in enumerate(config.safety_distances):
            if distance < self.MIN_DISTANCE_FROM_LIQUIDATION:
                self.logger.warning(
                    f"Step {i+1} below minimum safety distance",
                    distance=distance,
                    minimum=self.MIN_DISTANCE_FROM_LIQUIDATION
                )
                return False
        
        return True
    
    def backtest_optimal_steps(
        self,
        position_data: Dict,
        min_steps: int = 3,
        max_steps: int = 7
    ) -> Tuple[int, AdaptiveFibonacciConfig, Dict]:
        """
        Backtest to find the optimal number of averaging steps.
        
        Args:
            position_data: Position configuration data
            min_steps: Minimum number of steps to test
            max_steps: Maximum number of steps to test
            
        Returns:
            Tuple of (optimal_steps, best_config, backtest_results)
        """
        best_steps = min_steps
        best_config = None
        best_score = 0
        backtest_results = {}
        
        for num_steps in range(min_steps, max_steps + 1):
            # Reinitialize with different number of steps
            self.__init__(num_steps)
            
            # Calculate configuration for this number of steps
            config = self.calculate_adaptive_config(position_data)
            
            # Score based on multiple factors
            score = self._calculate_backtest_score(config, position_data)
            
            backtest_results[num_steps] = {
                'k_coefficient': config.k_coefficient,
                'max_safe_steps': config.max_safe_steps,
                'total_margin': config.total_margin_required,
                'final_avg_entry': config.final_avg_entry,
                'min_safety_distance': min(config.safety_distances) if config.safety_distances else 0,
                'score': score,
                'fibonacci_sequence': self.fibonacci_sequence.copy(),
                'cumulative_thresholds': self.cumulative_thresholds.copy()
            }
            
            if score > best_score:
                best_score = score
                best_steps = num_steps
                best_config = config
            
            self.logger.info(
                f"Backtested {num_steps} steps",
                score=score,
                k_coefficient=config.k_coefficient,
                max_safe_steps=config.max_safe_steps
            )
        
        # Reinitialize with optimal number of steps
        self.__init__(best_steps)
        
        return best_steps, best_config, backtest_results
    
    def _calculate_backtest_score(
        self,
        config: AdaptiveFibonacciConfig,
        position_data: Dict
    ) -> float:
        """
        Calculate a score for the configuration based on multiple factors.
        
        Higher score is better.
        """
        score = 0
        
        # More steps executed is better (weight: 40%)
        score += config.max_safe_steps * 40
        
        # Lower K coefficient is better (more conservative) (weight: 20%)
        if config.k_coefficient > 0:
            score += (1 / config.k_coefficient) * 2
        
        # Better safety distance (weight: 30%)
        min_safety = min(config.safety_distances) if config.safety_distances else 0
        score += min_safety * 300
        
        # Efficient margin usage (weight: 10%)
        margin_efficiency = config.total_margin_required / position_data['total_margin']
        score += margin_efficiency * 10
        
        return score


# Example usage function for integration
def calculate_position_averaging_config(
    entry_price: float,
    leverage: float = None,  # Will be optimized if not provided
    initial_margin: float = 1.0,
    total_margin: float = 25.0,
    max_delta: float = None,  # MUST be provided by delta calculator
    direction: str = 'long',
    optimize_leverage: bool = True,
    backtest_steps: bool = True
) -> Dict:
    """
    Calculate adaptive Fibonacci averaging configuration for a position.
    
    SYSTEM LOGIC:
    =============
    1. zone_state_machine.py calculates MAX DELTA (maximum expected price deviation)
    2. This function receives that delta and:
       - Backtests to find optimal number of steps (3-7)
       - Optimizes leverage if not provided
       - Calculates optimal K coefficient
       - Distributes steps over the delta using Fibonacci ratios
    
    The delta represents the MAXIMUM price movement expected based on historical data.
    This module's job is to optimally distribute averaging steps across that delta.
    
    Args:
        entry_price: Entry price of position
        leverage: Trading leverage (optimized if None)
        initial_margin: Initial margin for position
        total_margin: Total margin available for averaging
        max_delta: Maximum expected price deviation (from zone_state_machine)
        direction: 'long' or 'short'
        optimize_leverage: Whether to find optimal leverage
        backtest_steps: Whether to backtest for optimal step count
    
    Returns:
        Complete averaging configuration with optimized parameters
    """
    if max_delta is None:
        raise ValueError(
            "max_delta MUST be provided by zone_state_machine._calculate_dynamic_delta(). "
            "This represents the maximum expected price deviation for the coin."
        )
    
    # Optimize leverage if not provided
    if leverage is None and optimize_leverage:
        # Test leverage values from 3x to 10x
        best_leverage = 7  # Default
        best_score = 0
        
        for test_leverage in range(3, 11):
            calculator = AdaptiveFibonacciCalculator()
            test_data = {
                'entry_price': entry_price,
                'leverage': test_leverage,
                'initial_margin': initial_margin,
                'total_margin': total_margin,
                'max_delta': max_delta,
                'direction': direction
            }
            
            config = calculator.calculate_adaptive_config(test_data)
            score = calculator._calculate_backtest_score(config, test_data)
            
            if score > best_score:
                best_score = score
                best_leverage = test_leverage
        
        leverage = best_leverage
        logger.info(f"Optimized leverage: {leverage}x")
    elif leverage is None:
        leverage = 7  # Default if not optimizing
    
    # Initialize calculator
    calculator = AdaptiveFibonacciCalculator()
    
    position_data = {
        'entry_price': entry_price,
        'leverage': leverage,
        'initial_margin': initial_margin,
        'total_margin': total_margin,
        'max_delta': max_delta,  # From zone_state_machine
        'direction': direction
    }
    
    # Backtest to find optimal number of steps
    if backtest_steps:
        optimal_steps, config, backtest_results = calculator.backtest_optimal_steps(
            position_data,
            min_steps=3,
            max_steps=7
        )
        
        logger.info(f"Backtesting complete: optimal steps = {optimal_steps}")
        logger.info(f"Backtest results: {backtest_results}")
    else:
        # Use default 5 steps
        calculator = AdaptiveFibonacciCalculator(5)
        config = calculator.calculate_adaptive_config(position_data)
    
    # Format averaging plan
    averaging_steps = calculator.format_averaging_plan(config, position_data)
    
    # Validate safety
    is_safe = calculator.validate_safety(config)
    
    # Check if all steps are safe from liquidation
    liquidation_safe = all(s.get('liquidation_safety', True) for s in averaging_steps)
    
    # Log critical safety info
    if averaging_steps:
        logger.info(
            "Averaging plan safety check",
            first_step_upnl=f"{averaging_steps[0].get('upnl_pct_threshold', 0):.1%}",
            last_step_upnl=f"{averaging_steps[-1].get('upnl_pct_threshold', 0):.1%}",
            all_safe_from_liquidation=liquidation_safe,
            num_steps=len(averaging_steps)
        )
    
    return {
        'k_coefficient': config.k_coefficient,
        'averaging_steps': averaging_steps,
        'max_safe_steps': config.max_safe_steps,
        'total_margin_required': config.total_margin_required,
        'final_avg_entry': config.final_avg_entry,
        'final_position_size': config.final_position_size,
        'safety_validated': is_safe,
        'min_safety_distance': min(config.safety_distances) if config.safety_distances else 0,
        'optimized_leverage': leverage,
        'max_delta_used': max_delta,
        'backtest_performed': backtest_steps,
        'liquidation_safe': liquidation_safe  # NEW: All steps safe from liquidation
    }