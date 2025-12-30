#!/usr/bin/env python3
"""
V3: Adaptive Averaging Engine with Dynamic Phasing
Intelligent averaging step management with market-aware progression
"""

import numpy as np
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional

class AdaptiveAveragingEngine:
    """
    Dynamic averaging step phasing with market-aware progression
    """

    def __init__(self):
        self.averaging_history = self.load_averaging_history()
        self.market_phasing_model = self.load_phasing_model()

    def load_averaging_history(self):
        """Load historical averaging performance data"""
        try:
            with open('/root/ai_xyz/averaging_performance_history.json', 'r') as f:
                return json.load(f)
        except:
            return {}

    def load_phasing_model(self):
        """Load phasing optimization model"""
        # Simple rule-based model for now
        # Could be upgraded to ML model
        return {
            'bull_market': {'progression': 'conservative', 'max_steps': 4},
            'bear_market': {'progression': 'aggressive', 'max_steps': 6},
            'volatile_market': {'progression': 'moderate', 'max_steps': 5},
            'neutral_market': {'progression': 'balanced', 'max_steps': 4}
        }

    def calculate_adaptive_averaging_plan(self, symbol, delta_analysis, market_context, position_data):
        """
        Calculate adaptive averaging plan based on delta and market conditions

        Args:
            symbol: Trading symbol
            delta_analysis: Delta calculation results
            market_context: Current market analysis
            position_data: Current position information

        Returns:
            dict: Complete averaging plan
        """
        # Determine market regime and optimal progression
        regime = market_context.get('regime', 'neutral')
        regime_config = self.market_phasing_model.get(regime, self.market_phasing_model['neutral_market'])

        # Calculate optimal number of steps
        optimal_steps = self.calculate_optimal_steps(symbol, delta_analysis, market_context, position_data)

        # Generate step sizes using adaptive algorithm
        step_sizes = self.generate_adaptive_step_sizes(optimal_steps, delta_analysis, market_context)

        # Calculate trigger prices for each step
        trigger_prices = self.calculate_step_triggers(symbol, step_sizes, position_data)

        # Optimize phasing timing
        phasing_schedule = self.optimize_phasing_schedule(step_sizes, market_context)

        # Calculate risk management per step
        risk_management = self.calculate_step_risk_management(step_sizes, position_data)

        plan = {
            'symbol': symbol,
            'total_steps': optimal_steps,
            'step_sizes': step_sizes,
            'trigger_prices': trigger_prices,
            'phasing_schedule': phasing_schedule,
            'risk_management': risk_management,
            'progression_type': regime_config['progression'],
            'market_regime': regime,
            'confidence_score': self.calculate_plan_confidence(delta_analysis, market_context),
            'expected_completion_time': self.estimate_completion_time(phasing_schedule, market_context)
        }

        return plan

    def calculate_optimal_steps(self, symbol, delta_analysis, market_context, position_data):
        """
        Calculate optimal number of averaging steps
        """
        # Base calculation from delta
        delta = delta_analysis.get('final_delta', 0.03)
        base_steps = max(3, min(8, int(10 / delta)))  # Inverse relationship with delta

        # Adjust for market conditions
        volatility = market_context.get('volatility', 0.5)
        trend_strength = market_context.get('trend_strength', 0.5)

        # Higher volatility suggests more steps for better averaging
        volatility_adjustment = int(volatility * 2)

        # Stronger trends suggest fewer steps (let it run)
        trend_adjustment = -int(trend_strength * 1.5)

        # Position size consideration
        position_size = position_data.get('amount', 1) * position_data.get('entry_price', 1)
        size_adjustment = 0
        if position_size < 10:  # Small position
            size_adjustment = 1  # Allow more steps
        elif position_size > 100:  # Large position
            size_adjustment = -1  # Fewer steps

        # Historical performance adjustment
        historical_adjustment = self.get_historical_step_adjustment(symbol)

        optimal_steps = base_steps + volatility_adjustment + trend_adjustment + size_adjustment + historical_adjustment
        optimal_steps = max(3, min(8, optimal_steps))  # Constrain to 3-8 steps

        return optimal_steps

    def generate_adaptive_step_sizes(self, num_steps, delta_analysis, market_context):
        """
        Generate adaptive step sizes based on market conditions
        """
        # Start with base Fibonacci progression
        base_multipliers = [1.0, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0]

        # Adjust based on market regime
        regime = market_context.get('regime', 'neutral')

        if regime == 'bull':
            # Conservative sizing in bull markets
            multipliers = [m * 0.8 for m in base_multipliers]
        elif regime == 'bear':
            # Aggressive sizing in bear markets
            multipliers = [m * 1.2 for m in base_multipliers]
        elif regime == 'volatile':
            # Moderate sizing in volatile markets
            multipliers = [m * 1.0 for m in base_multipliers]
        else:
            # Balanced sizing in neutral markets
            multipliers = base_multipliers.copy()

        # Adjust for delta size
        delta = delta_analysis.get('final_delta', 0.03)
        delta_adjustment = 1 + (delta - 0.03) * 5  # Smaller delta = smaller steps

        multipliers = [m * delta_adjustment for m in multipliers]

        # Normalize to ensure total allocation makes sense
        total_allocation = sum(multipliers[:num_steps])
        if total_allocation > 50:  # Too much total allocation
            scale_factor = 50 / total_allocation
            multipliers = [m * scale_factor for m in multipliers]

        return multipliers[:num_steps]

    def calculate_step_triggers(self, symbol, step_sizes, position_data):
        """
        Calculate price trigger levels for each averaging step
        """
        entry_price = position_data.get('entry_price', 1.0)
        current_price = position_data.get('current_price', entry_price)
        position_side = position_data.get('side', 'long')

        trigger_prices = []
        cumulative_size = position_data.get('amount', 1.0)

        for i, step_size in enumerate(step_sizes):
            # Calculate new weighted average price after this step
            step_amount = step_size  # Amount to add (in base units)

            if position_side == 'long':
                # For long positions, averaging happens when price drops
                # Calculate price level that would bring weighted average to target
                target_avg_drop = (i + 1) * 0.02  # Progressive target drops
                trigger_price = entry_price * (1 - target_avg_drop)
            else:
                # For short positions, averaging happens when price rises
                target_avg_rise = (i + 1) * 0.02  # Progressive target rises
                trigger_price = entry_price * (1 + target_avg_rise)

            # Adjust for current market conditions
            market_adjustment = self.calculate_market_trigger_adjustment(i, position_data)
            trigger_price *= (1 + market_adjustment)

            trigger_prices.append(trigger_price)

        return trigger_prices

    def optimize_phasing_schedule(self, step_sizes, market_context):
        """
        Optimize timing between averaging steps
        """
        schedule = []
        base_delay = 300  # 5 minutes base delay

        volatility = market_context.get('volatility', 0.5)
        volume = market_context.get('volume_profile', 1.0)

        for i, step_size in enumerate(step_sizes):
            # Adjust delay based on step size and market conditions
            size_factor = step_size / step_sizes[0]  # Relative to first step
            volatility_factor = 1 + volatility * 0.5  # Higher volatility = longer delays
            volume_factor = 1 / (1 + volume * 0.3)  # Higher volume = shorter delays

            step_delay = base_delay * size_factor * volatility_factor * volume_factor

            # Progressive delays (later steps take longer)
            step_delay *= (1 + i * 0.2)

            schedule.append({
                'step': i + 1,
                'delay_seconds': max(60, min(step_delay, 3600)),  # 1min to 1hour
                'size_factor': size_factor,
                'market_conditions': {
                    'volatility': volatility,
                    'volume': volume
                }
            })

        return schedule

    def calculate_step_risk_management(self, step_sizes, position_data):
        """
        Calculate risk management parameters for each step
        """
        risk_management = []

        for i, step_size in enumerate(step_sizes):
            # Calculate position size after this step
            cumulative_size = sum(step_sizes[:i+1])
            total_position_value = cumulative_size * position_data.get('entry_price', 1)

            # Calculate liquidation distance
            leverage = position_data.get('leverage', 8)
            liquidation_buffer = 0.02  # 2% buffer from liquidation

            # Maximum safe drawdown for this step
            max_drawdown = (1 / leverage) - liquidation_buffer

            # Step-specific stop loss
            step_stop_loss = max_drawdown * (1 - i * 0.1)  # Tighter stops for later steps

            risk_management.append({
                'step': i + 1,
                'cumulative_position_value': total_position_value,
                'max_safe_drawdown': max_drawdown,
                'step_stop_loss': step_stop_loss,
                'recommended_leverage': leverage,
                'risk_multiplier': step_size / step_sizes[0]
            })

        return risk_management

    def calculate_market_trigger_adjustment(self, step_number, position_data):
        """
        Calculate market-based adjustment for trigger prices
        """
        # Adjust based on position holding time
        holding_time = position_data.get('holding_time_hours', 0)

        # Longer holding = more aggressive triggers (closer to current price)
        time_adjustment = min(holding_time / 24, 0.1)  # Max 10% adjustment

        # Adjust based on recent volatility
        recent_volatility = position_data.get('recent_volatility', 0.5)
        volatility_adjustment = (recent_volatility - 0.5) * 0.05  # ±5% based on volatility

        # Step number adjustment (later steps are more aggressive)
        step_adjustment = step_number * 0.02  # 2% more aggressive per step

        total_adjustment = time_adjustment + volatility_adjustment + step_adjustment

        return total_adjustment

    def calculate_plan_confidence(self, delta_analysis, market_context):
        """
        Calculate overall confidence in the averaging plan
        """
        delta_confidence = delta_analysis.get('confidence', 0.5)
        regime_strength = market_context.get('regime_strength', 0.5)
        data_quality = market_context.get('data_quality', 0.8)

        confidence = (delta_confidence * 0.4 + regime_strength * 0.3 + data_quality * 0.3)

        return min(confidence, 1.0)

    def estimate_completion_time(self, phasing_schedule, market_context):
        """
        Estimate total time to complete all averaging steps
        """
        if not phasing_schedule:
            return 0

        total_delay = sum(step['delay_seconds'] for step in phasing_schedule)

        # Adjust for market conditions
        volatility = market_context.get('volatility', 0.5)
        speed_multiplier = 1 + volatility * 0.5  # Volatile markets move faster

        estimated_time = total_delay / speed_multiplier

        return estimated_time

    def get_historical_step_adjustment(self, symbol):
        """
        Get historical adjustment for optimal step count
        """
        symbol_history = self.averaging_history.get(symbol, [])

        if len(symbol_history) < 3:
            return 0

        # Find average optimal steps from successful trades
        successful_trades = [h for h in symbol_history if h.get('final_pnl', 0) > 0]

        if successful_trades:
            avg_steps = np.mean([h.get('total_steps', 4) for h in successful_trades])
            current_avg = 4.5  # System default
            adjustment = int((avg_steps - current_avg) * 0.5)  # Conservative adjustment
            return adjustment

        return 0

    def execute_averaging_step(self, symbol, step_number, averaging_plan, market_context):
        """
        Execute a specific averaging step with dynamic adjustments
        """
        if step_number >= len(averaging_plan['step_sizes']):
            return {'success': False, 'reason': 'Step number exceeds plan'}

        step_info = averaging_plan['phasing_schedule'][step_number]
        risk_info = averaging_plan['risk_management'][step_number]

        # Check if market conditions are favorable
        market_check = self.validate_market_conditions_for_step(step_number, market_context)

        if not market_check['favorable']:
            return {
                'success': False,
                'reason': f'Unfavorable market conditions: {market_check["reason"]}',
                'delay_suggested': market_check.get('suggested_delay', 300)
            }

        # Calculate optimal execution parameters
        execution_params = self.calculate_step_execution_parameters(
            symbol, step_number, averaging_plan, market_context
        )

        return {
            'success': True,
            'step_number': step_number,
            'execution_params': execution_params,
            'risk_assessment': risk_info,
            'market_validation': market_check
        }

    def validate_market_conditions_for_step(self, step_number, market_context):
        """
        Validate if market conditions are suitable for executing this step
        """
        volatility = market_context.get('volatility', 0.5)
        trend_strength = market_context.get('trend_strength', 0.5)
        momentum = market_context.get('momentum', 0)

        # Early steps prefer moderate volatility
        if step_number < 2:
            if volatility > 0.8:
                return {'favorable': False, 'reason': 'Too volatile for early step', 'suggested_delay': 600}
        # Later steps can handle higher volatility
        else:
            if volatility < 0.2:
                return {'favorable': False, 'reason': 'Insufficient volatility for averaging', 'suggested_delay': 300}

        # Check momentum alignment
        if step_number > 0 and abs(momentum) < 0.1:
            return {'favorable': False, 'reason': 'Insufficient momentum', 'suggested_delay': 180}

        return {'favorable': True, 'reason': 'Conditions favorable'}

    def calculate_step_execution_parameters(self, symbol, step_number, averaging_plan, market_context):
        """
        Calculate optimal execution parameters for this step
        """
        step_size = averaging_plan['step_sizes'][step_number]
        trigger_price = averaging_plan['trigger_prices'][step_number]

        # Adjust execution based on current market
        slippage_tolerance = self.calculate_slippage_tolerance(market_context)
        execution_speed = self.determine_execution_speed(market_context)

        # Iceberg orders for large steps
        use_iceberg = step_size > averaging_plan['step_sizes'][0] * 2

        return {
            'step_size': step_size,
            'target_price': trigger_price,
            'slippage_tolerance': slippage_tolerance,
            'execution_speed': execution_speed,
            'use_iceberg': use_iceberg,
            'max_holding_time': averaging_plan['phasing_schedule'][step_number]['delay_seconds'] * 2
        }

    def calculate_slippage_tolerance(self, market_context):
        """Calculate acceptable slippage for current market"""
        volatility = market_context.get('volatility', 0.5)
        volume = market_context.get('volume_profile', 1.0)

        base_tolerance = 0.002  # 0.2% base

        # Higher volatility allows more slippage
        volatility_adjustment = volatility * 0.005

        # Higher volume allows less slippage
        volume_adjustment = - (volume - 1) * 0.001

        tolerance = base_tolerance + volatility_adjustment + volume_adjustment

        return max(0.001, min(tolerance, 0.01))  # 0.1% to 1%

    def determine_execution_speed(self, market_context):
        """Determine optimal execution speed"""
        volatility = market_context.get('volatility', 0.5)
        trend_strength = market_context.get('trend_strength', 0.5)

        if volatility > 0.7:
            return 'fast'  # Execute quickly in volatile markets
        elif trend_strength > 0.7:
            return 'moderate'  # Steady execution in trending markets
        else:
            return 'slow'  # Careful execution in ranging markets

    def update_averaging_performance(self, symbol, averaging_plan, final_results):
        """Update historical performance data"""
        if symbol not in self.averaging_history:
            self.averaging_history[symbol] = []

        performance_record = {
            'timestamp': datetime.now().isoformat(),
            'total_steps': averaging_plan['total_steps'],
            'final_pnl': final_results.get('final_pnl', 0),
            'completion_time': final_results.get('completion_time', 0),
            'market_regime': averaging_plan['market_regime'],
            'success_rate': final_results.get('success_rate', 0),
            'sharpe_ratio': final_results.get('sharpe_ratio', 0)
        }

        self.averaging_history[symbol].append(performance_record)

        # Keep last 50 records
        self.averaging_history[symbol] = self.averaging_history[symbol][-50:]

        # Save to disk
        try:
            with open('/root/ai_xyz/averaging_performance_history.json', 'w') as f:
                json.dump(self.averaging_history, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save averaging history: {e}")