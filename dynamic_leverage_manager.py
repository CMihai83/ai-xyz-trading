#!/usr/bin/env python3
"""
Dynamic Leverage Manager for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Adjusts leverage dynamically based on:
- Market regime (from Dynamic Parameter Manager)
- Account balance and margin utilization
- Position risk profile
- Recent performance (win rate, drawdown)

Grok recommendation: Scale down leverage during high-volatility periods
to reduce liquidation risk while maximizing capital efficiency in calm markets.

Author: Claude + Grok Consortium
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DynamicLeverageManager:
    """
    Manages dynamic leverage adjustment based on market conditions and account state.

    Integrates with DynamicParameterManager for regime-aware leverage scaling.
    """

    # Base leverage settings
    BASE_LEVERAGE = 10
    MIN_LEVERAGE = 3
    MAX_LEVERAGE = 20

    # Regime-based leverage multipliers
    REGIME_LEVERAGE = {
        'HIGH_VOLATILITY': {
            'max_leverage': 5,      # Reduce max leverage in high vol
            'recommended': 4,       # Conservative recommendation
            'description': 'High volatility - reduced leverage for safety'
        },
        'TRENDING': {
            'max_leverage': 12,     # Allow moderate leverage in trends
            'recommended': 8,       # Follow the trend with reasonable leverage
            'description': 'Trending market - moderate leverage to capture moves'
        },
        'RANGING': {
            'max_leverage': 15,     # Higher leverage OK in ranging markets
            'recommended': 10,      # Mean reversion benefits from leverage
            'description': 'Ranging market - leverage OK for mean reversion'
        },
        'NORMAL': {
            'max_leverage': 12,     # Standard operations
            'recommended': 10,      # Default leverage
            'description': 'Normal conditions - standard leverage'
        }
    }

    # Account health thresholds
    MARGIN_UTILIZATION_THRESHOLDS = {
        'critical': 0.90,    # >90% margin used - reduce leverage immediately
        'high': 0.75,        # >75% margin used - reduce leverage
        'moderate': 0.50,    # >50% margin used - slight reduction
        'healthy': 0.30      # <30% margin used - full leverage OK
    }

    # Drawdown-based adjustments
    DRAWDOWN_THRESHOLDS = {
        'severe': 0.20,      # >20% drawdown - minimum leverage
        'moderate': 0.10,    # >10% drawdown - reduced leverage
        'mild': 0.05         # >5% drawdown - slightly reduced
    }

    def __init__(self, exchange=None, dynamic_param_manager=None):
        """
        Initialize the Dynamic Leverage Manager.

        Args:
            exchange: CCXT exchange instance
            dynamic_param_manager: DynamicParameterManager instance for regime detection
        """
        self.exchange = exchange
        self.dynamic_param_manager = dynamic_param_manager
        self.leverage_history = []
        self.current_leverage = {}  # symbol -> leverage

    def set_exchange(self, exchange):
        """Set the exchange instance."""
        self.exchange = exchange

    def set_param_manager(self, param_manager):
        """Set the Dynamic Parameter Manager instance."""
        self.dynamic_param_manager = param_manager

    def calculate_regime_leverage(self, regime: str) -> Dict:
        """Get leverage settings based on market regime."""
        return self.REGIME_LEVERAGE.get(regime, self.REGIME_LEVERAGE['NORMAL'])

    def calculate_account_health_factor(self, account_data: Dict) -> float:
        """
        Calculate leverage adjustment factor based on account health.

        Returns:
            Factor between 0.5 and 1.0 (lower = reduce leverage more)
        """
        margin_utilization = account_data.get('margin_utilization', 0.5)
        current_drawdown = account_data.get('current_drawdown', 0)
        win_rate = account_data.get('recent_win_rate', 0.5)

        # Start with full factor
        health_factor = 1.0

        # Margin utilization adjustment
        if margin_utilization > self.MARGIN_UTILIZATION_THRESHOLDS['critical']:
            health_factor *= 0.5  # Severe reduction
        elif margin_utilization > self.MARGIN_UTILIZATION_THRESHOLDS['high']:
            health_factor *= 0.7
        elif margin_utilization > self.MARGIN_UTILIZATION_THRESHOLDS['moderate']:
            health_factor *= 0.85

        # Drawdown adjustment
        if current_drawdown > self.DRAWDOWN_THRESHOLDS['severe']:
            health_factor *= 0.5
        elif current_drawdown > self.DRAWDOWN_THRESHOLDS['moderate']:
            health_factor *= 0.7
        elif current_drawdown > self.DRAWDOWN_THRESHOLDS['mild']:
            health_factor *= 0.85

        # Win rate adjustment (poor performance = reduce leverage)
        if win_rate < 0.3:
            health_factor *= 0.7
        elif win_rate < 0.4:
            health_factor *= 0.85

        return max(0.5, health_factor)

    def calculate_position_risk_factor(self, position_data: Dict) -> float:
        """
        Calculate leverage adjustment based on position characteristics.

        Returns:
            Factor between 0.5 and 1.0
        """
        avg_steps = position_data.get('averaging_steps', 0)
        holding_hours = position_data.get('holding_hours', 0)
        unrealized_pnl_pct = position_data.get('unrealized_pnl_pct', 0)

        risk_factor = 1.0

        # More averaging steps = higher risk, reduce leverage
        if avg_steps >= 4:
            risk_factor *= 0.6
        elif avg_steps >= 3:
            risk_factor *= 0.75
        elif avg_steps >= 2:
            risk_factor *= 0.85

        # Long holding time with losses = reduce leverage
        if holding_hours > 24 and unrealized_pnl_pct < -0.10:
            risk_factor *= 0.7
        elif holding_hours > 12 and unrealized_pnl_pct < -0.05:
            risk_factor *= 0.85

        return max(0.5, risk_factor)

    def calculate_optimal_leverage(self, symbol: str, account_data: Dict = None,
                                   position_data: Dict = None) -> Dict:
        """
        Calculate optimal leverage for a symbol based on all factors.

        Args:
            symbol: Trading symbol
            account_data: Account metrics (margin utilization, drawdown, win rate)
            position_data: Position metrics (averaging steps, holding time)

        Returns:
            Dict with leverage recommendation and reasoning
        """
        account_data = account_data or {}
        position_data = position_data or {}

        # Get market regime from Dynamic Parameter Manager
        regime = 'NORMAL'
        atr_ratio = 1.0

        if self.dynamic_param_manager:
            try:
                params = self.dynamic_param_manager.calculate_dynamic_params(symbol)
                regime = params.get('regime', 'NORMAL')
                atr_ratio = params.get('atr_ratio', 1.0)
            except Exception as e:
                logger.warning(f"Could not get regime for {symbol}: {e}")

        # Get regime-based leverage limits
        regime_settings = self.calculate_regime_leverage(regime)

        # Calculate adjustment factors
        health_factor = self.calculate_account_health_factor(account_data)
        risk_factor = self.calculate_position_risk_factor(position_data)

        # Calculate optimal leverage
        base_leverage = regime_settings['recommended']
        max_leverage = regime_settings['max_leverage']

        # Apply factors
        adjusted_leverage = base_leverage * health_factor * risk_factor

        # Ensure within bounds
        optimal_leverage = max(self.MIN_LEVERAGE, min(max_leverage, int(adjusted_leverage)))

        # Build result
        result = {
            'symbol': symbol,
            'regime': regime,
            'atr_ratio': atr_ratio,
            'base_leverage': base_leverage,
            'max_leverage': max_leverage,
            'health_factor': health_factor,
            'risk_factor': risk_factor,
            'optimal_leverage': optimal_leverage,
            'description': regime_settings['description'],
            'timestamp': datetime.now().isoformat()
        }

        # Log significant changes
        prev_leverage = self.current_leverage.get(symbol, base_leverage)
        if abs(optimal_leverage - prev_leverage) >= 2:
            logger.info(f"[{symbol}] Leverage adjusted: {prev_leverage}x -> {optimal_leverage}x ({regime})")

        self.current_leverage[symbol] = optimal_leverage
        self.leverage_history.append(result)

        # Keep history bounded
        if len(self.leverage_history) > 1000:
            self.leverage_history = self.leverage_history[-500:]

        return result

    def get_leverage_for_new_position(self, symbol: str, signal_confidence: float = 0.5,
                                      account_data: Dict = None) -> int:
        """
        Get recommended leverage for opening a new position.

        Args:
            symbol: Trading symbol
            signal_confidence: Signal confidence score (0-1)
            account_data: Account metrics

        Returns:
            Recommended leverage as integer
        """
        account_data = account_data or {}

        # Get base optimal leverage
        leverage_data = self.calculate_optimal_leverage(symbol, account_data)
        base_leverage = leverage_data['optimal_leverage']

        # Adjust based on signal confidence
        if signal_confidence >= 0.85:
            confidence_mult = 1.2  # High confidence = allow more leverage
        elif signal_confidence >= 0.70:
            confidence_mult = 1.0
        elif signal_confidence >= 0.55:
            confidence_mult = 0.85
        else:
            confidence_mult = 0.7  # Low confidence = reduce leverage

        final_leverage = int(base_leverage * confidence_mult)
        final_leverage = max(self.MIN_LEVERAGE, min(leverage_data['max_leverage'], final_leverage))

        return final_leverage

    def should_reduce_leverage(self, symbol: str, current_leverage: int,
                               account_data: Dict = None, position_data: Dict = None) -> Tuple[bool, int, str]:
        """
        Check if leverage should be reduced for an existing position.

        Returns:
            Tuple of (should_reduce, new_leverage, reason)
        """
        leverage_data = self.calculate_optimal_leverage(symbol, account_data, position_data)
        optimal = leverage_data['optimal_leverage']

        if current_leverage > optimal + 2:
            return True, optimal, f"Regime: {leverage_data['regime']}, recommended: {optimal}x"

        return False, current_leverage, "Leverage OK"

    def get_status_summary(self) -> Dict:
        """Get summary of current leverage state."""
        return {
            'current_leverages': self.current_leverage.copy(),
            'history_length': len(self.leverage_history),
            'recent_changes': self.leverage_history[-5:] if self.leverage_history else []
        }

    def format_leverage_log(self, leverage_data: Dict) -> str:
        """Format leverage data for logging."""
        return (
            f"[{leverage_data.get('regime', 'N/A')}] "
            f"Leverage: {leverage_data.get('optimal_leverage', 0)}x "
            f"(base:{leverage_data.get('base_leverage', 0)}x "
            f"health:{leverage_data.get('health_factor', 0):.2f} "
            f"risk:{leverage_data.get('risk_factor', 0):.2f})"
        )


# Singleton instance
_leverage_manager_instance = None

def get_dynamic_leverage_manager(exchange=None, param_manager=None) -> DynamicLeverageManager:
    """Get or create the singleton DynamicLeverageManager instance."""
    global _leverage_manager_instance
    if _leverage_manager_instance is None:
        _leverage_manager_instance = DynamicLeverageManager(exchange, param_manager)
    else:
        if exchange:
            _leverage_manager_instance.set_exchange(exchange)
        if param_manager:
            _leverage_manager_instance.set_param_manager(param_manager)
    return _leverage_manager_instance


if __name__ == "__main__":
    # Test the dynamic leverage manager
    print("=" * 60)
    print("DYNAMIC LEVERAGE MANAGER TEST")
    print("=" * 60)

    manager = DynamicLeverageManager()

    # Test regime-based leverage
    print("\nRegime-Based Leverage Settings:")
    for regime, settings in manager.REGIME_LEVERAGE.items():
        print(f"  {regime}: max={settings['max_leverage']}x, recommended={settings['recommended']}x")

    # Test with different account health scenarios
    print("\nAccount Health Factor Tests:")
    scenarios = [
        {'margin_utilization': 0.20, 'current_drawdown': 0.02, 'recent_win_rate': 0.60},
        {'margin_utilization': 0.60, 'current_drawdown': 0.08, 'recent_win_rate': 0.45},
        {'margin_utilization': 0.85, 'current_drawdown': 0.15, 'recent_win_rate': 0.35},
        {'margin_utilization': 0.95, 'current_drawdown': 0.25, 'recent_win_rate': 0.25},
    ]

    for i, scenario in enumerate(scenarios):
        factor = manager.calculate_account_health_factor(scenario)
        print(f"  Scenario {i+1}: margin={scenario['margin_utilization']*100:.0f}%, "
              f"dd={scenario['current_drawdown']*100:.0f}%, "
              f"wr={scenario['recent_win_rate']*100:.0f}% -> factor={factor:.2f}")

    # Test position risk factor
    print("\nPosition Risk Factor Tests:")
    position_scenarios = [
        {'averaging_steps': 0, 'holding_hours': 1, 'unrealized_pnl_pct': 0.02},
        {'averaging_steps': 2, 'holding_hours': 6, 'unrealized_pnl_pct': -0.03},
        {'averaging_steps': 4, 'holding_hours': 24, 'unrealized_pnl_pct': -0.12},
    ]

    for i, pos in enumerate(position_scenarios):
        factor = manager.calculate_position_risk_factor(pos)
        print(f"  Position {i+1}: steps={pos['averaging_steps']}, "
              f"hours={pos['holding_hours']}, "
              f"pnl={pos['unrealized_pnl_pct']*100:.0f}% -> factor={factor:.2f}")
