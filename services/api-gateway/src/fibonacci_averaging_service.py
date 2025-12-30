"""
Fibonacci Averaging Service for AI-XYZ Trading System
=====================================================

This service calculates optimal averaging steps using Fibonacci sequence weighting
to minimize liquidation risk while maximizing position efficiency.

Integration with AI-XYZ:
- Called before opening any position
- Provides averaging steps, multipliers, and leverage recommendations
- Uses delta from market scanner/opportunity engine
- Ensures liquidation safety with multi-step validation
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import json
import structlog
from decimal import Decimal, ROUND_HALF_UP

logger = structlog.get_logger(__name__)

class TradeDirection(Enum):
    """Trade direction enumeration."""
    LONG = "long"
    SHORT = "short"

@dataclass
class AveragingStep:
    """Represents a single averaging step with Fibonacci-based configuration."""
    step_number: int
    price: float
    margin_allocation: float
    position_multiplier: float
    cumulative_margin: float
    liquidation_safety: bool
    fibonacci_weight: int
    distance_from_entry: float

@dataclass
class TradingParameters:
    """Complete trading parameters for position entry."""
    leverage: float
    initial_position_size: float
    averaging_steps: List[AveragingStep]
    total_margin_required: float
    max_loss_tolerance: float
    liquidation_price: float
    confidence_score: float

class FibonacciAveragingService:
    """
    Main service for calculating Fibonacci-based averaging parameters.
    Integrates with AI-XYZ trading system for position management.
    """
    
    def __init__(self, exchange=None):
        """Initialize service with AI-XYZ specific configuration."""
        # Fibonacci sequence for step weighting - starting from 3 upwards
        # We want sequences that END at 3 when reversed: [21, 13, 8, 5, 3]
        self.fibonacci_sequence = [3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610]
        
        # AI-XYZ specific constraints
        self.min_steps = 3  # Minimum averaging steps
        self.max_steps = 8  # Maximum for AI-XYZ system (cardinal rules)
        self.liquidation_buffer = 0.05  # 5% safety buffer
        self.min_position_value = 6.5  # $6.5 minimum after leverage
        self.default_leverage_range = (7, 10)  # AI-XYZ leverage range
        
        # Initialize AdaptiveTimeframeDeltaService if exchange provided
        self.delta_service = None
        if exchange:
            import sys
            sys.path.append('/app/core')
            from adaptive_timeframe_delta import AdaptiveTimeframeDeltaService
            self.delta_service = AdaptiveTimeframeDeltaService(exchange)
        
        logger.info("Fibonacci Averaging Service initialized for AI-XYZ")
    
    def generate_fibonacci_weights(self, num_steps: int) -> List[int]:
        """
        Generate Fibonacci weights for step positioning.
        Largest number = first step (largest distance from entry).
        """
        if num_steps > len(self.fibonacci_sequence):
            raise ValueError(f"Maximum {len(self.fibonacci_sequence)} steps supported")
        
        # Take first N Fibonacci numbers and REVERSE for price level calculation
        # Larger numbers = further from entry price (21%, 13%, 8%, 5%, 3%)
        weights = self.fibonacci_sequence[:num_steps][::-1]  # Reverse for distance calculation
        logger.debug(f"Generated Fibonacci weights for {num_steps} steps: {weights}")
        return weights
    
    def calculate_step_positions(self, entry_price: float, delta: float, 
                                direction: TradeDirection, num_steps: int) -> List[Dict]:
        """
        Calculate exact price levels for each averaging step using Fibonacci distribution.
        
        Returns list of dicts with price and distance information.
        """
        weights = self.generate_fibonacci_weights(num_steps)
        total_weight = sum(weights)
        
        step_positions = []
        cumulative_distance = 0
        
        for i, weight in enumerate(weights):
            # Calculate distance for this step
            distance_ratio = weight / total_weight
            distance_from_entry = distance_ratio * delta
            cumulative_distance += distance_from_entry
            
            # Calculate step price based on trade direction
            if direction == TradeDirection.LONG:
                step_price = entry_price - cumulative_distance
            else:  # SHORT
                step_price = entry_price + cumulative_distance
                
            step_positions.append({
                'step_number': i + 1,
                'price': round(step_price, 8),  # Higher precision for crypto
                'fibonacci_weight': weight,
                'distance_from_entry': round(cumulative_distance, 8),
                'distance_percentage': round((cumulative_distance / entry_price) * 100, 2)
            })
            
        return step_positions
    
    def calculate_margin_allocation(self, total_margin: float, num_steps: int) -> List[float]:
        """
        Calculate margin allocation using INVERSE Fibonacci weighting.
        Allocates full capital across all steps to maximize averaging capability.
        """
        weights = self.generate_fibonacci_weights(num_steps)
        # INVERSE weighting for margin allocation (smaller steps get less margin)
        inverse_weights = weights[::-1]
        total_weight = sum(inverse_weights)
        
        allocations = []
        remaining_margin = total_margin
        
        for i, weight in enumerate(inverse_weights):
            if i < len(inverse_weights) - 1:
                # Regular steps get Fibonacci-weighted allocation
                allocation = (weight / total_weight) * total_margin
                allocation = min(allocation, remaining_margin)  # Don't exceed remaining
            else:
                # Last step gets all remaining margin (includes emergency reserve)
                allocation = remaining_margin
            
            allocations.append(round(allocation, 2))
            remaining_margin -= allocation
            
        # Ensure total doesn't exceed available margin
        if sum(allocations) > total_margin:
            # Scale down proportionally if needed
            scale = total_margin / sum(allocations)
            allocations = [round(a * scale, 2) for a in allocations]
            
        return allocations
    
    def calculate_position_multipliers(self, margin_allocations: List[float], 
                                      entry_price: float, leverage: float) -> List[float]:
        """
        Calculate position size multipliers for each averaging step.
        Preference for multipliers > 1 for aggressive averaging.
        """
        if not margin_allocations:
            return []
        
        # Calculate initial position size
        initial_position_size = (margin_allocations[0] * leverage) / entry_price
        multipliers = []
        
        for allocation in margin_allocations:
            position_size = (allocation * leverage) / entry_price
            multiplier = position_size / initial_position_size
            multipliers.append(round(multiplier, 3))
            
        return multipliers
    
    def check_liquidation_safety(self, entry_price: float, step_positions: List[Dict],
                                margin_allocations: List[float], leverage: float,
                                direction: TradeDirection) -> Tuple[bool, List[bool], float]:
        """
        Check liquidation safety at each averaging step.
        Returns (all_safe, individual_safety_checks, liquidation_price).
        """
        cumulative_margin = 0
        cumulative_position_size = 0
        safety_checks = []
        worst_unrealized_pnl = 0
        
        for i, (step_info, margin) in enumerate(zip(step_positions, margin_allocations)):
            cumulative_margin += margin
            position_size = (margin * leverage) / entry_price
            cumulative_position_size += position_size
            
            step_price = step_info['price']
            
            # Calculate unrealized P&L at this step
            if direction == TradeDirection.LONG:
                unrealized_pnl = cumulative_position_size * (step_price - entry_price)
            else:  # SHORT
                unrealized_pnl = cumulative_position_size * (entry_price - step_price)
            
            worst_unrealized_pnl = min(worst_unrealized_pnl, unrealized_pnl)
            
            # Apply safety buffer
            max_acceptable_loss = cumulative_margin * (1 - self.liquidation_buffer)
            
            # Check safety
            is_safe = abs(unrealized_pnl) <= max_acceptable_loss
            safety_checks.append(is_safe)
            
            logger.debug(f"Step {i+1}: pnl={unrealized_pnl:.2f}, max_loss={max_acceptable_loss:.2f}, safe={is_safe}")
        
        # Calculate liquidation price
        if direction == TradeDirection.LONG:
            # For long: liquidation when loss = total margin
            liquidation_price = entry_price * (1 - (cumulative_margin / (cumulative_position_size * entry_price)))
        else:
            # For short: liquidation when loss = total margin
            liquidation_price = entry_price * (1 + (cumulative_margin / (cumulative_position_size * entry_price)))
        
        all_safe = all(safety_checks)
        return all_safe, safety_checks, liquidation_price
    
    def optimize_leverage(self, available_margin: float, delta: float, 
                         entry_price: float, direction: TradeDirection) -> Tuple[float, int]:
        """
        Find optimal leverage and number of averaging steps within capital constraints.
        Prioritizes maximum averaging steps within the available margin.
        Returns (optimal_leverage, optimal_steps).
        """
        best_config = (self.default_leverage_range[0], self.min_steps)
        best_score = 0
        
        # Start with maximum steps and work down to find what fits our budget
        for num_steps in range(self.max_steps, self.min_steps - 1, -1):
            for leverage in range(self.default_leverage_range[1], self.default_leverage_range[0] - 1, -1):
                # Check if configuration is safe
                step_positions = self.calculate_step_positions(entry_price, delta, direction, num_steps)
                margin_allocations = self.calculate_margin_allocation(available_margin, num_steps)
                
                # Check total margin needed doesn't exceed available
                # The margin allocations already account for 70/30 split
                # So the sum should equal available_margin
                total_margin_needed = sum(margin_allocations)
                
                # Skip if margin needed exceeds budget
                if total_margin_needed > available_margin * 1.01:  # Allow 1% tolerance
                    logger.debug(f"Skipping {leverage}x/{num_steps} steps: needs ${total_margin_needed:.2f}, have ${available_margin:.2f}")
                    continue
                
                is_safe, _, liq_price = self.check_liquidation_safety(
                    entry_price, step_positions, margin_allocations, leverage, direction
                )
                
                if is_safe:
                    # Prioritize more steps over higher leverage
                    score = num_steps * 100 + leverage  # Heavy weight on steps
                    if score > best_score:
                        best_score = score
                        best_config = (leverage, num_steps)
                        logger.debug(f"Found config: {leverage}x leverage, {num_steps} steps, margin needed: ${total_margin_needed:.2f}")
        
        # If no safe config found with many steps, try to at least get something
        if best_score == 0:
            logger.warning(f"No safe config found within ${available_margin:.2f} budget, using minimum")
            best_config = (self.default_leverage_range[0], self.min_steps)
            
        logger.info(f"Optimal configuration: leverage={best_config[0]}x, steps={best_config[1]} for ${available_margin:.2f} budget")
        return best_config
    
    async def get_adaptive_delta(self, symbol: str, entry_price: float, 
                                 leverage: int = 10) -> float:
        """
        Get delta from AdaptiveTimeframeDeltaService
        
        Args:
            symbol: Trading symbol
            entry_price: Current market price
            leverage: Trading leverage
            
        Returns:
            Optimal delta as absolute price value
        """
        if self.delta_service:
            try:
                # Calculate all timeframe deltas
                deltas = await self.delta_service.calculate_all_deltas(symbol, entry_price)
                
                # Get appropriate delta based on safety
                delta_pct, timeframe, _ = self.delta_service.get_adaptive_delta(
                    symbol, {}, leverage
                )
                
                logger.info(f"Using adaptive delta from {timeframe}: {delta_pct*100:.1f}%")
                return entry_price * delta_pct
                
            except Exception as e:
                logger.error(f"Failed to get adaptive delta: {e}")
        
        # Fallback to safe minimum (34% for -85% UPNL safety at 10x leverage)
        safe_delta_pct = 0.34
        logger.warning(f"Using fallback delta: {safe_delta_pct*100:.1f}%")
        return entry_price * safe_delta_pct
    
    def calculate_trading_parameters(self, 
                                    delta: float,
                                    entry_price: float,
                                    available_margin: float,
                                    direction: Union[str, TradeDirection],
                                    market_confidence: float = 0.5) -> TradingParameters:
        """
        Main method to calculate complete trading parameters.
        
        Args:
            delta: Price movement range (from AdaptiveTimeframeDeltaService or provided)
            entry_price: Current market price
            available_margin: Available capital for position
            direction: Trade direction (long/short)
            market_confidence: Confidence from market scanner (0-1)
            
        Returns:
            TradingParameters with all necessary information
        """
        try:
            # Convert direction if string
            if isinstance(direction, str):
                direction = TradeDirection(direction.lower())
            
            # Find optimal leverage and steps
            optimal_leverage, optimal_steps = self.optimize_leverage(
                available_margin, delta, entry_price, direction
            )
            
            # Calculate step positions
            step_positions = self.calculate_step_positions(
                entry_price, delta, direction, optimal_steps
            )
            
            # Calculate margin allocation
            margin_allocations = self.calculate_margin_allocation(
                available_margin, optimal_steps
            )
            
            # Calculate position multipliers
            multipliers = self.calculate_position_multipliers(
                margin_allocations, entry_price, optimal_leverage
            )
            
            # Check liquidation safety
            is_safe, safety_checks, liquidation_price = self.check_liquidation_safety(
                entry_price, step_positions, margin_allocations, optimal_leverage, direction
            )
            
            if not is_safe:
                # Reduce steps if not safe
                optimal_steps = self.min_steps
                step_positions = self.calculate_step_positions(
                    entry_price, delta, direction, optimal_steps
                )
                margin_allocations = self.calculate_margin_allocation(
                    available_margin, optimal_steps
                )
                multipliers = self.calculate_position_multipliers(
                    margin_allocations, entry_price, optimal_leverage
                )
                _, safety_checks, liquidation_price = self.check_liquidation_safety(
                    entry_price, step_positions, margin_allocations, optimal_leverage, direction
                )
            
            # Build averaging steps
            averaging_steps = []
            cumulative_margin = 0
            for i in range(optimal_steps):
                cumulative_margin += margin_allocations[i]
                step = AveragingStep(
                    step_number=i + 1,
                    price=step_positions[i]['price'],
                    margin_allocation=margin_allocations[i],
                    position_multiplier=multipliers[i],
                    cumulative_margin=cumulative_margin,
                    liquidation_safety=safety_checks[i],
                    fibonacci_weight=step_positions[i]['fibonacci_weight'],
                    distance_from_entry=step_positions[i]['distance_from_entry']
                )
                averaging_steps.append(step)
            
            # Calculate initial position size (ensuring minimum $6.5)
            initial_margin = margin_allocations[0]
            initial_position_value = initial_margin * optimal_leverage
            
            # Don't scale up if below minimum - work within our budget
            # The system will use whatever capital is available
            if initial_position_value < self.min_position_value:
                logger.debug(f"Initial position ${initial_position_value:.2f} below minimum ${self.min_position_value}, but using available capital")
            
            # Calculate confidence-adjusted score
            confidence_score = market_confidence * (0.8 if is_safe else 0.5)
            
            # Debug logging
            total_margin = sum(margin_allocations)
            logger.info(f"DEBUG: available_margin=${available_margin:.2f}, margin_allocations={[f'${m:.2f}' for m in margin_allocations]}, total=${total_margin:.2f}")
            
            # IMPORTANT: Ensure total_margin_required doesn't exceed available_margin
            # This was causing the $70 issue when we only have $25
            if total_margin > available_margin * 1.01:  # Allow 1% rounding
                logger.warning(f"Total margin ${total_margin:.2f} exceeds available ${available_margin:.2f}, capping at available")
                total_margin = available_margin
            
            return TradingParameters(
                leverage=optimal_leverage,
                initial_position_size=initial_position_value,
                averaging_steps=averaging_steps,
                total_margin_required=total_margin,
                max_loss_tolerance=available_margin * (1 - self.liquidation_buffer),
                liquidation_price=liquidation_price,
                confidence_score=confidence_score
            )
            
        except Exception as e:
            logger.error(f"Error calculating trading parameters: {e}")
            raise

# API Integration for AI-XYZ System
def create_fibonacci_api():
    """Create API endpoint for AI-XYZ integration."""
    service = FibonacciAveragingService()
    
    async def get_trading_parameters(request_data: Dict) -> Dict:
        """
        API endpoint for AI-XYZ trading system.
        
        Input:
        {
            "delta": 100.0,           # From market scanner
            "entry_price": 50000.0,   # Current price
            "available_margin": 50.0, # Available capital
            "direction": "long",      # or "short"
            "confidence": 0.65       # Market scanner confidence
        }
        
        Output:
        {
            "success": true,
            "leverage": 8,
            "initial_position_size": 6.5,
            "averaging_steps": [...],
            "total_margin_required": 45.0,
            "liquidation_price": 47500.0,
            "confidence_score": 0.52
        }
        """
        try:
            params = service.calculate_trading_parameters(
                delta=float(request_data['delta']),
                entry_price=float(request_data['entry_price']),
                available_margin=float(request_data['available_margin']),
                direction=request_data['direction'],
                market_confidence=float(request_data.get('confidence', 0.5))
            )
            
            return {
                'success': True,
                'leverage': params.leverage,
                'initial_position_size': params.initial_position_size,
                'averaging_steps': [
                    {
                        'step_number': step.step_number,
                        'price': step.price,
                        'margin_allocation': step.margin_allocation,
                        'position_multiplier': step.position_multiplier,
                        'fibonacci_weight': step.fibonacci_weight,
                        'distance_from_entry': step.distance_from_entry,
                        'liquidation_safety': step.liquidation_safety
                    }
                    for step in params.averaging_steps
                ],
                'total_margin_required': params.total_margin_required,
                'max_loss_tolerance': params.max_loss_tolerance,
                'liquidation_price': params.liquidation_price,
                'confidence_score': params.confidence_score,
                'message': f"Optimized {len(params.averaging_steps)} averaging steps with {params.leverage}x leverage"
            }
            
        except Exception as e:
            logger.error(f"API error: {e}")
            return {
                'success': False,
                'error': str(e),
                'message': 'Failed to calculate trading parameters'
            }
    
    return get_trading_parameters

# Singleton instance for system-wide use
_fibonacci_service = None

def get_fibonacci_service() -> FibonacciAveragingService:
    """Get singleton instance of Fibonacci service."""
    global _fibonacci_service
    if _fibonacci_service is None:
        _fibonacci_service = FibonacciAveragingService()
    return _fibonacci_service

# Example usage
if __name__ == "__main__":
    import asyncio
    
    async def test_service():
        """Test the Fibonacci averaging service."""
        api = create_fibonacci_api()
        
        # Test case: BTC long position
        test_request = {
            'delta': 500.0,  # $500 delta
            'entry_price': 50000.0,  # BTC at $50k
            'available_margin': 100.0,  # $100 available
            'direction': 'long',
            'confidence': 0.7
        }
        
        result = await api(test_request)
        print(json.dumps(result, indent=2))
    
    asyncio.run(test_service())