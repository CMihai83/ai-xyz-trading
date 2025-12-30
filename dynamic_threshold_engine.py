#!/usr/bin/env python3
"""
Dynamic Threshold Engine for Opportunity Cost Service
Adapts closing thresholds based on real-time market conditions, position metrics, and risk profile
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os

class DynamicThresholdEngine:
    """
    Dynamically adjusts opportunity cost thresholds based on:
    - Market volatility
    - Position size relative to portfolio
    - Account risk profile
    - Market regime (bull/bear/sideways)
    - Holding time patterns
    """

    def __init__(self):
        self.market_regime = 'neutral'
        self.volatility_regime = 'normal'
        self.base_thresholds = {
            'high_cost': 0.05,
            'moderate_cost': 0.03,
            'acceptable_cost': 0.02
        }
        self.threshold_history = []
        self.performance_metrics = {}

    def calculate_dynamic_thresholds(self, market_data: Dict, position_data: Dict, portfolio_data: Dict) -> Dict:
        """
        Calculate adaptive thresholds based on current market and position conditions

        Args:
            market_data: Current market conditions (volatility, returns, correlations)
            position_data: Individual position metrics
            portfolio_data: Overall portfolio state

        Returns:
            dict: Adjusted thresholds for this context
        """
        # Calculate market regime
        market_regime_multiplier = self._calculate_market_regime_multiplier(market_data)

        # Calculate volatility adjustment
        volatility_multiplier = self._calculate_volatility_multiplier(market_data)

        # Calculate position size adjustment
        position_size_multiplier = self._calculate_position_size_multiplier(position_data, portfolio_data)

        # Calculate risk profile adjustment
        risk_multiplier = self._calculate_risk_profile_multiplier(portfolio_data)

        # Calculate holding time adjustment
        time_multiplier = self._calculate_holding_time_multiplier(position_data)

        # Apply all adjustments
        dynamic_thresholds = {}
        for threshold_name, base_value in self.base_thresholds.items():
            total_multiplier = (
                market_regime_multiplier *
                volatility_multiplier *
                position_size_multiplier *
                risk_multiplier *
                time_multiplier
            )

            # Adjust threshold (higher thresholds = less aggressive)
            dynamic_thresholds[threshold_name] = base_value * total_multiplier

            # Ensure reasonable bounds
            dynamic_thresholds[threshold_name] = np.clip(dynamic_thresholds[threshold_name], 0.005, 0.15)

        # Store for learning
        self.threshold_history.append({
            'timestamp': datetime.now(),
            'market_data': market_data,
            'position_data': position_data,
            'portfolio_data': portfolio_data,
            'dynamic_thresholds': dynamic_thresholds,
            'multipliers': {
                'market_regime': market_regime_multiplier,
                'volatility': volatility_multiplier,
                'position_size': position_size_multiplier,
                'risk': risk_multiplier,
                'time': time_multiplier
            }
        })

        return dynamic_thresholds

    def _calculate_market_regime_multiplier(self, market_data: Dict) -> float:
        """Calculate multiplier based on market regime (bull/bear/sideways)"""
        # Simple regime detection based on recent returns and volatility
        recent_returns = market_data.get('avg_market_return_24h', 0)
        volatility = market_data.get('market_volatility_24h', 0.05)

        if recent_returns > 0.05 and volatility < 0.08:  # Strong bull market
            return 1.5  # More patient, higher thresholds
        elif recent_returns < -0.05:  # Bear market
            return 0.7  # More aggressive, lower thresholds
        elif volatility > 0.12:  # High volatility regardless of direction
            return 0.8  # Slightly more aggressive
        else:  # Neutral/sideways
            return 1.0

    def _calculate_volatility_multiplier(self, market_data: Dict) -> float:
        """Calculate multiplier based on volatility regime"""
        volatility = market_data.get('market_volatility_24h', 0.05)

        if volatility > 0.15:  # Extreme volatility
            return 0.6  # Much more aggressive
        elif volatility > 0.10:  # High volatility
            return 0.8  # More aggressive
        elif volatility < 0.03:  # Low volatility
            return 1.4  # More patient
        else:  # Normal volatility
            return 1.0

    def _calculate_position_size_multiplier(self, position_data: Dict, portfolio_data: Dict) -> float:
        """Calculate multiplier based on position size relative to portfolio"""
        position_value = position_data.get('position_value_usd', 0)
        total_portfolio = portfolio_data.get('total_portfolio_value', 1000)

        position_ratio = position_value / total_portfolio

        if position_ratio > 0.2:  # Large position (>20% of portfolio)
            return 0.8  # More aggressive closing
        elif position_ratio > 0.1:  # Medium position (10-20%)
            return 0.9
        elif position_ratio < 0.02:  # Small position (<2%)
            return 1.3  # More patient
        else:
            return 1.0

    def _calculate_risk_profile_multiplier(self, portfolio_data: Dict) -> float:
        """Calculate multiplier based on account risk profile"""
        drawdown_pct = portfolio_data.get('current_drawdown_pct', 0)
        win_rate = portfolio_data.get('recent_win_rate', 0.5)
        margin_utilization = portfolio_data.get('margin_utilization', 0.5)

        risk_score = 0

        if drawdown_pct > 0.15:  # High drawdown
            risk_score += 2
        elif drawdown_pct > 0.08:
            risk_score += 1

        if win_rate < 0.4:  # Poor win rate
            risk_score += 1
        elif win_rate > 0.7:  # Good win rate
            risk_score -= 1

        if margin_utilization > 0.8:  # High leverage
            risk_score += 1

        # Convert risk score to multiplier
        if risk_score >= 3:  # High risk
            return 0.7
        elif risk_score >= 1:  # Medium risk
            return 0.85
        elif risk_score <= -1:  # Low risk
            return 1.2
        else:
            return 1.0

    def _calculate_holding_time_multiplier(self, position_data: Dict) -> float:
        """Calculate multiplier based on holding time patterns"""
        holding_hours = position_data.get('holding_time_hours', 0)

        if holding_hours > 24:  # Very long hold
            return 0.8  # More aggressive
        elif holding_hours > 8:  # Long hold
            return 0.9
        elif holding_hours < 1:  # Very short hold
            return 1.2  # More patient
        else:
            return 1.0

    def get_threshold_explanation(self, dynamic_thresholds: Dict) -> str:
        """Generate human-readable explanation of threshold adjustments"""
        explanations = []

        for name, value in dynamic_thresholds.items():
            base = self.base_thresholds[name]
            change_pct = ((value - base) / base) * 100

            if abs(change_pct) > 10:
                direction = "increased" if change_pct > 0 else "decreased"
                explanations.append(f"{name}: {direction} by {abs(change_pct):.1f}% to {value:.3f}")

        if explanations:
            return "Dynamic adjustments: " + "; ".join(explanations)
        else:
            return "Using base thresholds (no significant adjustments needed)"

    def update_performance_feedback(self, threshold_decision: Dict, outcome: Dict):
        """Update performance metrics for learning"""
        # Store decision outcomes for future threshold optimization
        self.performance_metrics[datetime.now().isoformat()] = {
            'decision': threshold_decision,
            'outcome': outcome
        }

        # Keep only recent performance data
        if len(self.performance_metrics) > 1000:
            oldest_key = min(self.performance_metrics.keys())
            del self.performance_metrics[oldest_key]