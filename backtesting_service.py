#!/usr/bin/env python3
"""
Backtesting Service Integration
Provides historical analysis and optimal parameter estimation
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os

class BacktestingService:
    """
    Analyzes historical data to optimize trading parameters
    """

    def __init__(self):
        self.historical_data = {}
        self.performance_metrics = {}

    def analyze_coin_performance(self, symbol: str, timeframe: str = '1d', days: int = 30) -> Dict:
        """
        Analyze historical performance of a coin
        """
        # Mock historical analysis - in real implementation would fetch real data
        base_symbol = symbol.split('/')[0]

        # Generate realistic volatility patterns
        if 'BTC' in base_symbol or 'ETH' in base_symbol:
            volatility = np.random.uniform(0.3, 0.6)  # Lower volatility for majors
            trend_strength = np.random.uniform(0.1, 0.4)
        elif 'SOL' in base_symbol or 'AVAX' in base_symbol:
            volatility = np.random.uniform(0.5, 0.9)  # Higher volatility for altcoins
            trend_strength = np.random.uniform(0.2, 0.6)
        else:
            volatility = np.random.uniform(0.7, 1.5)  # Very high for meme coins
            trend_strength = np.random.uniform(0.3, 0.8)

        return {
            'volatility_pct': volatility * 100,
            'trend_strength': trend_strength,
            'avg_daily_range': volatility * 100 * np.random.uniform(0.8, 1.2),
            'reversal_probability': 0.4 + (trend_strength * 0.3),  # Higher trend = lower reversal prob
            'support_levels': [0.85, 0.75, 0.65],  # Historical support levels
            'resistance_levels': [1.15, 1.25, 1.35],  # Historical resistance levels
            'avg_hold_time': int(24 * (1 + trend_strength)),  # Hours
            'best_timeframe': '1h' if volatility > 0.8 else '4h' if volatility > 0.5 else '1d'
        }

    def calculate_optimal_delta(self, symbol: str, current_price: float, leverage: int) -> Dict:
        """
        Calculate optimal delta based on historical analysis
        """
        analysis = self.analyze_coin_performance(symbol)

        # Base delta calculation
        base_delta_pct = analysis['volatility_pct'] * 0.1  # 10% of volatility

        # Adjust for leverage (higher leverage needs smaller delta)
        leverage_factor = 1 / np.sqrt(leverage / 5)  # 5x leverage = factor 1
        adjusted_delta_pct = base_delta_pct * leverage_factor

        # Adjust for trend strength
        trend_factor = 1 + (analysis['trend_strength'] - 0.5) * 0.5
        final_delta_pct = adjusted_delta_pct * trend_factor

        # Calculate absolute delta
        delta_absolute = current_price * (final_delta_pct / 100)

        # Calculate liquidation distance
        liquidation_distance_pct = (1.0 / leverage) - 0.005  # 0.5% maintenance margin

        return {
            'delta_percentage': final_delta_pct,
            'delta_absolute': delta_absolute,
            'liquidation_distance_pct': liquidation_distance_pct,
            'safe_averaging_range': liquidation_distance_pct * 0.8,  # 80% of liquidation distance
            'volatility_factor': analysis['volatility_pct'] / 100,  # Normalized (was /50, now /100 for proper scaling)
            'trend_factor': trend_factor,
            'recommended_timeframe': analysis['best_timeframe'],
            'confidence_score': min(1.0, analysis['reversal_probability'] + 0.2)
        }

class DynamicDeltaEngine:
    """
    Dynamic delta adjustment based on real-time market conditions
    """

    def __init__(self, backtesting_service: BacktestingService):
        self.backtesting = backtesting_service
        self.market_memory = {}
        self.volatility_windows = {}

    def calculate_adaptive_delta(self, symbol: str, market_context: Dict, position_data: Dict) -> Dict:
        """
        Calculate adaptive delta based on current market conditions
        """
        current_price = position_data.get('current_price', 0)
        leverage = position_data.get('leverage', 8)

        # Get base delta from backtesting
        base_delta = self.backtesting.calculate_optimal_delta(symbol, current_price, leverage)

        # Adjust for real-time conditions
        volatility = market_context.get('volatility', base_delta['volatility_factor'])
        volume = market_context.get('volume_ratio', 1.0)
        spread = market_context.get('spread_pct', 0.1)

        # Volatility adjustment
        if volatility > 1.5:  # High volatility
            delta_multiplier = 1.5
        elif volatility < 0.7:  # Low volatility
            delta_multiplier = 0.7
        else:
            delta_multiplier = 1.0

        # Volume adjustment
        if volume > 2.0:  # High volume
            delta_multiplier *= 1.2
        elif volume < 0.5:  # Low volume
            delta_multiplier *= 0.8

        # Apply adjustments
        adaptive_delta_pct = base_delta['delta_percentage'] * delta_multiplier
        adaptive_delta_abs = current_price * (adaptive_delta_pct / 100)

        return {
            'delta_percentage': adaptive_delta_pct,
            'delta_absolute': adaptive_delta_abs,
            'volatility_factor': base_delta.get('volatility_factor', volatility),  # Include volatility factor
            'adjustment_factors': {
                'volatility': delta_multiplier,
                'volume': volume,
                'spread': spread
            },
            'market_conditions': market_context,
            'confidence_score': base_delta['confidence_score'] * (1 + (1 - volatility) * 0.2)
        }

class FibonacciAveragingOptimizer:
    """
    Optimizes Fibonacci averaging steps with dynamic delta allocation
    """

    def __init__(self, backtesting_service: BacktestingService):
        self.backtesting = backtesting_service
        self.delta_engine = DynamicDeltaEngine(backtesting_service)

    def generate_optimal_averaging_plan(self, symbol: str, position_data: Dict, market_context: Dict) -> Dict:
        """
        Generate optimal averaging plan with steps allocated along delta range
        """
        current_price = position_data.get('current_price', 0)
        entry_price = position_data.get('entry_price', current_price)
        leverage = position_data.get('leverage', 8)

        # Get adaptive delta
        delta_info = self.delta_engine.calculate_adaptive_delta(symbol, market_context, position_data)
        delta_pct = delta_info['delta_percentage']

        # Calculate liquidation distance
        liquidation_distance = (1.0 / leverage) - 0.005  # 0.5% maintenance margin

        # Safe averaging range (80% of distance to liquidation)
        safe_range_pct = liquidation_distance * 0.8
        safe_range_absolute = current_price * (safe_range_pct / 100)

        # Calculate number of averaging steps
        # More steps for higher volatility coins
        volatility = delta_info['volatility_factor']
        if volatility > 1.2:  # High volatility
            max_steps = 5
        elif volatility > 0.8:  # Medium volatility
            max_steps = 4
        else:  # Low volatility
            max_steps = 3

        # Allocate steps along the delta range with Fibonacci logic
        # Bigger multipliers towards the end where reversal probability is higher
        base_multipliers = [1, 1, 2, 3, 5, 8, 13][:max_steps]

        # Calculate step positions along the safe range
        step_positions = []
        thresholds = []

        for i in range(max_steps):
            # Position steps with more spacing towards the end
            position_pct = safe_range_pct * (i + 1) / max_steps
            position_pct *= (1 + i * 0.2)  # Extra spacing for later steps

            threshold_pct = -position_pct  # Negative for averaging down
            threshold_price = entry_price * (1 + threshold_pct / 100)

            step_positions.append({
                'step': i + 1,
                'threshold_pct': threshold_pct,
                'threshold_price': threshold_price,
                'multiplier': base_multipliers[i],
                'position_in_range': position_pct / safe_range_pct
            })

            thresholds.append(abs(threshold_pct) / 100)  # Convert to decimal for config

        return {
            'max_averaging_steps': max_steps,
            'step_positions': step_positions,
            'thresholds': thresholds,
            'fibonacci_multipliers': base_multipliers[:max_steps],
            'safe_averaging_range_pct': safe_range_pct,
            'safe_averaging_range_absolute': safe_range_absolute,
            'liquidation_distance_pct': liquidation_distance,
            'delta_info': delta_info,
            'volatility_adjustment': volatility > 1.0,
            'market_adapted': True
        }