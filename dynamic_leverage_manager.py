#!/usr/bin/env python3
"""
Dynamic Leverage Manager for AI-XYZ Trading System
V2.1.0 - January 14, 2026

Adjusts leverage dynamically based on:
- Market regime (from Dynamic Parameter Manager)
- Account balance and margin utilization
- Position risk profile
- Recent performance (win rate, drawdown)
- EDGE CASES: Extreme volatility, liquidity constraints, regime transitions

Grok Sprint 5 Enhancement: Added edge case handling for:
- Flash crashes and liquidation cascades
- Low liquidity / wide spread conditions
- Rapid regime transitions
- Circuit breaker mechanisms
- Correlation-based portfolio stress

Sprint 9 Enhancement (Claude + Grok Consensus):
- Reduced MAX_LEVERAGE from 20x to 10x (conservative default)
- Added STRICT_MODE flag for 5x leverage cap
- Tightened regime-based leverage multipliers
- 22.5% leverage aggressiveness identified as profit leak

Author: Claude + Grok Consortium
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from collections import deque
import json
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DynamicLeverageManager:
    """
    Manages dynamic leverage adjustment based on market conditions and account state.

    Integrates with DynamicParameterManager for regime-aware leverage scaling.
    """

    # =========================================================================
    # SPRINT 9 LEVERAGE GUARDRAILS (Claude + Grok Consensus)
    # =========================================================================
    # Issue: 22.5% of leverage decisions were "too aggressive"
    # Solution: Cap leverage at 5x default, 10x max for high-confidence signals
    #
    # STRICT_MODE = True: Max 5x leverage (conservative, recommended for recovery)
    # STRICT_MODE = False: Max 10x leverage (moderate risk)
    # =========================================================================

    STRICT_MODE = True  # Enable strict 5x leverage cap (Sprint 9)

    # Base leverage settings - Sprint 9 tightened
    BASE_LEVERAGE = 5 if STRICT_MODE else 10
    MIN_LEVERAGE = 3
    MAX_LEVERAGE = 5 if STRICT_MODE else 10  # Reduced from 20x to prevent over-leverage

    # Absolute cap (never exceed regardless of any calculation)
    ABSOLUTE_MAX_LEVERAGE = 10  # Hard cap, even in non-strict mode

    # Regime-based leverage multipliers - Sprint 9 conservative
    REGIME_LEVERAGE = {
        'HIGH_VOLATILITY': {
            'max_leverage': 3,      # Reduced from 5x - extra conservative
            'recommended': 3,       # Conservative recommendation
            'description': 'High volatility - minimum leverage for safety'
        },
        'EXTREME_VOLATILITY': {  # New regime for Sprint 9
            'max_leverage': 2,      # Near-minimum leverage
            'recommended': 2,       # Only hold existing positions
            'description': 'Extreme volatility - do not open new positions'
        },
        'TRENDING': {
            'max_leverage': 7 if not STRICT_MODE else 5,
            'recommended': 5,       # Reduced from 8x
            'description': 'Trending market - moderate leverage to capture moves'
        },
        'RANGING': {
            'max_leverage': 7 if not STRICT_MODE else 5,
            'recommended': 5,       # Reduced from 10x
            'description': 'Ranging market - leverage OK for mean reversion'
        },
        'NORMAL': {
            'max_leverage': 7 if not STRICT_MODE else 5,
            'recommended': 5,       # Reduced from 10x
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

    # ==========================================================================
    # EDGE CASE THRESHOLDS (V2.0.0 - Sprint 5)
    # ==========================================================================

    # Extreme volatility detection (flash crash protection)
    EXTREME_VOLATILITY_THRESHOLDS = {
        'flash_crash': 3.0,      # ATR ratio > 3.0 = flash crash territory
        'high_stress': 2.5,      # ATR ratio > 2.5 = high stress
        'elevated': 2.0,         # ATR ratio > 2.0 = elevated volatility
        'price_drop_1m': -0.03,  # -3% in 1 minute = potential flash crash
        'price_drop_5m': -0.05,  # -5% in 5 minutes = confirmed crash
    }

    # Liquidity constraint thresholds
    LIQUIDITY_THRESHOLDS = {
        'spread_critical': 0.005,   # Spread > 0.5% = critical, minimum leverage
        'spread_high': 0.003,       # Spread > 0.3% = reduce leverage
        'spread_moderate': 0.001,   # Spread > 0.1% = slight reduction
        'volume_critical': 0.1,     # Volume < 10% of avg = illiquid
        'volume_low': 0.3,          # Volume < 30% of avg = low liquidity
    }

    # Regime transition settings
    REGIME_TRANSITION_SETTINGS = {
        'rapid_change_window': 5,       # Minutes to detect rapid changes
        'max_transitions': 3,           # Max transitions before circuit breaker
        'cooldown_minutes': 15,         # Cooldown after circuit breaker
        'transition_leverage_cap': 5,   # Max leverage during rapid transitions
    }

    # Circuit breaker settings - Sprint 9 improved for 80% effectiveness
    # Previous: 61.5% effectiveness (triggered but didn't prevent losses)
    # Target: 80% effectiveness via earlier, more sensitive triggers
    CIRCUIT_BREAKER = {
        'consecutive_losses': 3,        # Reduced from 5 - trigger earlier
        'loss_threshold': -0.10,        # Reduced from -15% - more sensitive
        'max_averaging_positions': 5,   # Reduced from 8 - prevent over-accumulation
        'leverage_floor': 3,            # Minimum leverage during breaker
        'cooldown_minutes': 20,         # Reduced from 30 - faster recovery testing
        # Sprint 9 additional triggers
        'margin_utilization_trigger': 0.80,  # NEW: Trigger at 80% margin used
        'portfolio_upnl_trigger': -0.15,     # NEW: Trigger at -15% portfolio UPNL
        'rapid_decline_trigger': -0.05,      # NEW: -5% decline in 5 min triggers
    }

    # Portfolio stress thresholds
    PORTFOLIO_STRESS = {
        'correlation_threshold': 0.7,   # High correlation warning
        'concentrated_positions': 5,    # Positions in same sector
        'total_upnl_critical': -0.20,   # -20% total UPNL = critical
        'total_upnl_high': -0.10,       # -10% total UPNL = high stress
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

        # V2.0.0 - Edge case tracking
        self.regime_history = deque(maxlen=20)  # Track regime transitions
        self.price_history = {}  # symbol -> deque of recent prices
        self.circuit_breaker_active = False
        self.circuit_breaker_until = None
        self.consecutive_losses = 0
        self.last_regime = 'NORMAL'
        self.regime_transition_count = 0
        self.last_transition_time = None
        self.edge_case_alerts = []

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

    # ==========================================================================
    # EDGE CASE DETECTION METHODS (V2.0.0)
    # ==========================================================================

    def detect_flash_crash(self, symbol: str, current_price: float,
                          price_1m_ago: float = None, price_5m_ago: float = None) -> Dict:
        """
        Detect flash crash conditions based on rapid price movements.

        Returns:
            Dict with is_flash_crash, severity, and recommended action
        """
        result = {
            'is_flash_crash': False,
            'severity': 'none',
            'price_change_1m': 0,
            'price_change_5m': 0,
            'leverage_multiplier': 1.0,
            'action': 'none'
        }

        # Calculate price changes
        if price_1m_ago and price_1m_ago > 0:
            result['price_change_1m'] = (current_price - price_1m_ago) / price_1m_ago

        if price_5m_ago and price_5m_ago > 0:
            result['price_change_5m'] = (current_price - price_5m_ago) / price_5m_ago

        # Check for flash crash (rapid drop)
        thresholds = self.EXTREME_VOLATILITY_THRESHOLDS

        if result['price_change_5m'] <= thresholds['price_drop_5m']:
            result['is_flash_crash'] = True
            result['severity'] = 'critical'
            result['leverage_multiplier'] = 0.3  # Reduce to 30% of normal
            result['action'] = 'EMERGENCY_REDUCE'
            self._add_edge_case_alert('FLASH_CRASH', f"{symbol}: {result['price_change_5m']*100:.1f}% in 5m")

        elif result['price_change_1m'] <= thresholds['price_drop_1m']:
            result['is_flash_crash'] = True
            result['severity'] = 'high'
            result['leverage_multiplier'] = 0.5  # Reduce to 50% of normal
            result['action'] = 'REDUCE_LEVERAGE'
            self._add_edge_case_alert('POTENTIAL_CRASH', f"{symbol}: {result['price_change_1m']*100:.1f}% in 1m")

        return result

    def detect_extreme_volatility(self, atr_ratio: float) -> Dict:
        """
        Detect extreme volatility conditions from ATR ratio.

        Returns:
            Dict with volatility level and leverage adjustment
        """
        thresholds = self.EXTREME_VOLATILITY_THRESHOLDS

        result = {
            'is_extreme': False,
            'level': 'normal',
            'atr_ratio': atr_ratio,
            'leverage_multiplier': 1.0
        }

        if atr_ratio >= thresholds['flash_crash']:
            result['is_extreme'] = True
            result['level'] = 'flash_crash'
            result['leverage_multiplier'] = 0.3
            self._add_edge_case_alert('EXTREME_VOL', f"ATR ratio {atr_ratio:.2f} = flash crash territory")

        elif atr_ratio >= thresholds['high_stress']:
            result['is_extreme'] = True
            result['level'] = 'high_stress'
            result['leverage_multiplier'] = 0.5

        elif atr_ratio >= thresholds['elevated']:
            result['level'] = 'elevated'
            result['leverage_multiplier'] = 0.7

        return result

    def check_liquidity_constraints(self, symbol: str, spread: float = None,
                                   volume_ratio: float = None) -> Dict:
        """
        Check for liquidity constraints that affect leverage safety.

        Args:
            symbol: Trading symbol
            spread: Current bid-ask spread as decimal (e.g., 0.001 = 0.1%)
            volume_ratio: Current volume / average volume

        Returns:
            Dict with liquidity assessment and leverage adjustment
        """
        thresholds = self.LIQUIDITY_THRESHOLDS

        result = {
            'is_constrained': False,
            'spread_level': 'normal',
            'volume_level': 'normal',
            'leverage_multiplier': 1.0,
            'reason': ''
        }

        # Check spread
        if spread is not None:
            if spread >= thresholds['spread_critical']:
                result['is_constrained'] = True
                result['spread_level'] = 'critical'
                result['leverage_multiplier'] = min(result['leverage_multiplier'], 0.4)
                result['reason'] = f"Spread {spread*100:.2f}% too wide"
                self._add_edge_case_alert('LIQUIDITY', f"{symbol}: spread {spread*100:.2f}%")

            elif spread >= thresholds['spread_high']:
                result['spread_level'] = 'high'
                result['leverage_multiplier'] = min(result['leverage_multiplier'], 0.6)

            elif spread >= thresholds['spread_moderate']:
                result['spread_level'] = 'moderate'
                result['leverage_multiplier'] = min(result['leverage_multiplier'], 0.8)

        # Check volume
        if volume_ratio is not None:
            if volume_ratio <= thresholds['volume_critical']:
                result['is_constrained'] = True
                result['volume_level'] = 'critical'
                result['leverage_multiplier'] = min(result['leverage_multiplier'], 0.4)
                result['reason'] += f" Low volume ({volume_ratio*100:.0f}% of avg)"

            elif volume_ratio <= thresholds['volume_low']:
                result['volume_level'] = 'low'
                result['leverage_multiplier'] = min(result['leverage_multiplier'], 0.7)

        return result

    def check_regime_transitions(self, current_regime: str) -> Dict:
        """
        Track regime transitions and detect rapid changes.

        Returns:
            Dict with transition status and leverage cap
        """
        now = datetime.now()
        settings = self.REGIME_TRANSITION_SETTINGS

        result = {
            'is_rapid_transition': False,
            'transition_count': 0,
            'leverage_cap': None,
            'in_cooldown': False
        }

        # Check if regime changed
        if current_regime != self.last_regime:
            self.regime_history.append({
                'from': self.last_regime,
                'to': current_regime,
                'timestamp': now
            })

            # Count recent transitions
            window = timedelta(minutes=settings['rapid_change_window'])
            recent_transitions = [
                t for t in self.regime_history
                if now - t['timestamp'] <= window
            ]

            self.regime_transition_count = len(recent_transitions)
            self.last_transition_time = now
            self.last_regime = current_regime

            # Check for rapid transitions
            if self.regime_transition_count >= settings['max_transitions']:
                result['is_rapid_transition'] = True
                result['transition_count'] = self.regime_transition_count
                result['leverage_cap'] = settings['transition_leverage_cap']
                self._add_edge_case_alert('RAPID_TRANSITION',
                    f"{self.regime_transition_count} regime changes in {settings['rapid_change_window']}min")

        return result

    def check_circuit_breaker(self, account_data: Dict = None,
                             position_data: Dict = None) -> Dict:
        """
        Check if circuit breaker should be activated.

        Returns:
            Dict with circuit breaker status
        """
        now = datetime.now()
        settings = self.CIRCUIT_BREAKER

        result = {
            'is_active': self.circuit_breaker_active,
            'reason': '',
            'leverage_floor': settings['leverage_floor'],
            'cooldown_remaining': 0
        }

        # Check if in cooldown
        if self.circuit_breaker_until and now < self.circuit_breaker_until:
            remaining = (self.circuit_breaker_until - now).total_seconds() / 60
            result['is_active'] = True
            result['cooldown_remaining'] = remaining
            result['reason'] = f"Cooldown: {remaining:.0f}min remaining"
            return result

        # Reset if cooldown expired
        if self.circuit_breaker_until and now >= self.circuit_breaker_until:
            self.circuit_breaker_active = False
            self.circuit_breaker_until = None
            self.consecutive_losses = 0

        account_data = account_data or {}
        position_data = position_data or {}

        # Check consecutive losses
        if self.consecutive_losses >= settings['consecutive_losses']:
            self._activate_circuit_breaker(f"Consecutive losses: {self.consecutive_losses}")
            result['is_active'] = True
            result['reason'] = f"Consecutive losses ({self.consecutive_losses})"

        # Check session loss threshold
        session_pnl = account_data.get('session_pnl_pct', 0)
        if session_pnl <= settings['loss_threshold']:
            self._activate_circuit_breaker(f"Session loss: {session_pnl*100:.1f}%")
            result['is_active'] = True
            result['reason'] = f"Session loss ({session_pnl*100:.1f}%)"

        # Check averaging positions count
        averaging_count = position_data.get('averaging_positions', 0)
        if averaging_count >= settings['max_averaging_positions']:
            self._activate_circuit_breaker(f"Averaging positions: {averaging_count}")
            result['is_active'] = True
            result['reason'] = f"Too many averaging ({averaging_count})"

        # =================================================================
        # Sprint 9 Additional Triggers for 80% Effectiveness
        # =================================================================

        # Check margin utilization (NEW)
        margin_used = account_data.get('margin_utilization', 0)
        margin_trigger = settings.get('margin_utilization_trigger', 0.80)
        if margin_used >= margin_trigger:
            self._activate_circuit_breaker(f"High margin utilization: {margin_used*100:.1f}%")
            result['is_active'] = True
            result['reason'] = f"High margin ({margin_used*100:.0f}%)"

        # Check portfolio UPNL (NEW)
        portfolio_upnl = position_data.get('total_upnl_pct', 0)
        upnl_trigger = settings.get('portfolio_upnl_trigger', -0.15)
        if portfolio_upnl <= upnl_trigger:
            self._activate_circuit_breaker(f"Portfolio UPNL critical: {portfolio_upnl*100:.1f}%")
            result['is_active'] = True
            result['reason'] = f"Portfolio UPNL ({portfolio_upnl*100:.0f}%)"

        # Check rapid decline (NEW) - requires historical tracking
        rapid_trigger = settings.get('rapid_decline_trigger', -0.05)
        recent_decline = account_data.get('pnl_change_5min', 0)
        if recent_decline <= rapid_trigger:
            self._activate_circuit_breaker(f"Rapid decline: {recent_decline*100:.1f}% in 5min")
            result['is_active'] = True
            result['reason'] = f"Rapid decline ({recent_decline*100:.1f}%/5min)"

        return result

    def _activate_circuit_breaker(self, reason: str):
        """Activate the circuit breaker."""
        self.circuit_breaker_active = True
        self.circuit_breaker_until = datetime.now() + timedelta(
            minutes=self.CIRCUIT_BREAKER['cooldown_minutes']
        )
        logger.warning(f"CIRCUIT BREAKER ACTIVATED: {reason}")
        self._add_edge_case_alert('CIRCUIT_BREAKER', reason)

    def check_portfolio_stress(self, positions: Dict = None) -> Dict:
        """
        Check for portfolio-level stress indicators.

        Returns:
            Dict with stress level and leverage adjustment
        """
        positions = positions or {}
        thresholds = self.PORTFOLIO_STRESS

        result = {
            'stress_level': 'normal',
            'leverage_multiplier': 1.0,
            'warnings': []
        }

        if not positions:
            return result

        # Calculate total UPNL percentage
        total_value = sum(p.get('value', 0) for p in positions.values())
        total_upnl = sum(p.get('unrealized_pnl', 0) for p in positions.values())

        if total_value > 0:
            total_upnl_pct = total_upnl / total_value

            if total_upnl_pct <= thresholds['total_upnl_critical']:
                result['stress_level'] = 'critical'
                result['leverage_multiplier'] = 0.4
                result['warnings'].append(f"Critical UPNL: {total_upnl_pct*100:.1f}%")

            elif total_upnl_pct <= thresholds['total_upnl_high']:
                result['stress_level'] = 'high'
                result['leverage_multiplier'] = 0.6
                result['warnings'].append(f"High stress UPNL: {total_upnl_pct*100:.1f}%")

        # Check sector concentration
        sector_counts = {}
        for pos in positions.values():
            sector = pos.get('sector', 'other')
            sector_counts[sector] = sector_counts.get(sector, 0) + 1

        max_sector_count = max(sector_counts.values()) if sector_counts else 0
        if max_sector_count >= thresholds['concentrated_positions']:
            result['leverage_multiplier'] *= 0.8
            result['warnings'].append(f"Concentrated: {max_sector_count} positions in one sector")

        return result

    def _add_edge_case_alert(self, alert_type: str, message: str):
        """Add an edge case alert to the history."""
        alert = {
            'type': alert_type,
            'message': message,
            'timestamp': datetime.now().isoformat()
        }
        self.edge_case_alerts.append(alert)
        if len(self.edge_case_alerts) > 100:
            self.edge_case_alerts = self.edge_case_alerts[-50:]
        logger.warning(f"[EDGE CASE] {alert_type}: {message}")

    def record_trade_result(self, is_win: bool):
        """Record a trade result for consecutive loss tracking."""
        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1

    def calculate_edge_case_factor(self, symbol: str, atr_ratio: float = 1.0,
                                   spread: float = None, volume_ratio: float = None,
                                   current_price: float = None, price_1m_ago: float = None,
                                   price_5m_ago: float = None, account_data: Dict = None,
                                   position_data: Dict = None, regime: str = 'NORMAL') -> Dict:
        """
        Calculate combined edge case adjustment factor.

        Returns:
            Dict with overall edge case assessment and leverage multiplier
        """
        # Check all edge cases
        volatility = self.detect_extreme_volatility(atr_ratio)
        flash_crash = self.detect_flash_crash(symbol, current_price or 0, price_1m_ago, price_5m_ago)
        liquidity = self.check_liquidity_constraints(symbol, spread, volume_ratio)
        transitions = self.check_regime_transitions(regime)
        circuit = self.check_circuit_breaker(account_data, position_data)

        # Combine multipliers (use minimum - most conservative)
        combined_multiplier = 1.0
        active_edge_cases = []

        if volatility['is_extreme']:
            combined_multiplier = min(combined_multiplier, volatility['leverage_multiplier'])
            active_edge_cases.append(f"volatility:{volatility['level']}")

        if flash_crash['is_flash_crash']:
            combined_multiplier = min(combined_multiplier, flash_crash['leverage_multiplier'])
            active_edge_cases.append(f"flash_crash:{flash_crash['severity']}")

        if liquidity['is_constrained']:
            combined_multiplier = min(combined_multiplier, liquidity['leverage_multiplier'])
            active_edge_cases.append(f"liquidity:{liquidity['spread_level']}")

        if transitions['is_rapid_transition']:
            # Apply leverage cap if in rapid transition
            combined_multiplier = min(combined_multiplier, 0.5)
            active_edge_cases.append(f"transitions:{transitions['transition_count']}")

        if circuit['is_active']:
            combined_multiplier = min(combined_multiplier, 0.3)
            active_edge_cases.append(f"circuit_breaker")

        return {
            'combined_multiplier': combined_multiplier,
            'active_edge_cases': active_edge_cases,
            'volatility': volatility,
            'flash_crash': flash_crash,
            'liquidity': liquidity,
            'transitions': transitions,
            'circuit_breaker': circuit,
            'has_edge_cases': len(active_edge_cases) > 0
        }

    def calculate_optimal_leverage(self, symbol: str, account_data: Dict = None,
                                   position_data: Dict = None,
                                   market_data: Dict = None) -> Dict:
        """
        Calculate optimal leverage for a symbol based on all factors.

        Args:
            symbol: Trading symbol
            account_data: Account metrics (margin utilization, drawdown, win rate)
            position_data: Position metrics (averaging steps, holding time)
            market_data: Market metrics (spread, volume_ratio, prices for edge cases)

        Returns:
            Dict with leverage recommendation and reasoning
        """
        account_data = account_data or {}
        position_data = position_data or {}
        market_data = market_data or {}

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

        # V2.0.0 - Calculate edge case factor
        edge_case_result = self.calculate_edge_case_factor(
            symbol=symbol,
            atr_ratio=atr_ratio,
            spread=market_data.get('spread'),
            volume_ratio=market_data.get('volume_ratio'),
            current_price=market_data.get('current_price'),
            price_1m_ago=market_data.get('price_1m_ago'),
            price_5m_ago=market_data.get('price_5m_ago'),
            account_data=account_data,
            position_data=position_data,
            regime=regime
        )
        edge_case_factor = edge_case_result['combined_multiplier']

        # Calculate optimal leverage
        base_leverage = regime_settings['recommended']
        max_leverage = regime_settings['max_leverage']

        # Apply all factors including edge cases
        adjusted_leverage = base_leverage * health_factor * risk_factor * edge_case_factor

        # Ensure within bounds
        optimal_leverage = max(self.MIN_LEVERAGE, min(max_leverage, int(adjusted_leverage)))

        # Additional cap if circuit breaker is active
        if edge_case_result['circuit_breaker']['is_active']:
            optimal_leverage = min(optimal_leverage, self.CIRCUIT_BREAKER['leverage_floor'])

        # Build result
        result = {
            'symbol': symbol,
            'regime': regime,
            'atr_ratio': atr_ratio,
            'base_leverage': base_leverage,
            'max_leverage': max_leverage,
            'health_factor': health_factor,
            'risk_factor': risk_factor,
            'edge_case_factor': edge_case_factor,
            'optimal_leverage': optimal_leverage,
            'description': regime_settings['description'],
            'timestamp': datetime.now().isoformat(),
            # V2.0.0 - Edge case details
            'edge_cases': {
                'has_edge_cases': edge_case_result['has_edge_cases'],
                'active': edge_case_result['active_edge_cases'],
                'circuit_breaker_active': edge_case_result['circuit_breaker']['is_active']
            }
        }

        # Log significant changes
        prev_leverage = self.current_leverage.get(symbol, base_leverage)
        if abs(optimal_leverage - prev_leverage) >= 2:
            edge_info = f", edge_cases={edge_case_result['active_edge_cases']}" if edge_case_result['has_edge_cases'] else ""
            logger.info(f"[{symbol}] Leverage adjusted: {prev_leverage}x -> {optimal_leverage}x ({regime}{edge_info})")

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
            'recent_changes': self.leverage_history[-5:] if self.leverage_history else [],
            # V2.0.0 - Edge case status
            'circuit_breaker_active': self.circuit_breaker_active,
            'circuit_breaker_until': self.circuit_breaker_until.isoformat() if self.circuit_breaker_until else None,
            'consecutive_losses': self.consecutive_losses,
            'regime_transition_count': self.regime_transition_count,
            'recent_edge_case_alerts': self.edge_case_alerts[-10:] if self.edge_case_alerts else []
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

    # ==========================================================================
    # V2.0.0 - EDGE CASE TESTS
    # ==========================================================================
    print("\n" + "=" * 60)
    print("EDGE CASE TESTS (V2.0.0)")
    print("=" * 60)

    # Test 1: Flash Crash Detection
    print("\n1. Flash Crash Detection:")
    flash_tests = [
        {'current': 100, 'price_1m': 100, 'price_5m': 100, 'expected': False},      # Normal
        {'current': 97, 'price_1m': 100, 'price_5m': 100, 'expected': True},        # -3% in 1m
        {'current': 94, 'price_1m': 98, 'price_5m': 100, 'expected': True},         # -6% in 5m
    ]
    for i, test in enumerate(flash_tests):
        result = manager.detect_flash_crash(
            'TEST/USDT', test['current'], test['price_1m'], test['price_5m']
        )
        status = "PASS" if result['is_flash_crash'] == test['expected'] else "FAIL"
        print(f"  Test {i+1}: {status} - crash={result['is_flash_crash']}, "
              f"severity={result['severity']}, mult={result['leverage_multiplier']:.2f}")

    # Test 2: Extreme Volatility Detection
    print("\n2. Extreme Volatility Detection:")
    vol_tests = [
        {'atr_ratio': 1.0, 'expected_level': 'normal'},
        {'atr_ratio': 2.0, 'expected_level': 'elevated'},
        {'atr_ratio': 2.5, 'expected_level': 'high_stress'},
        {'atr_ratio': 3.5, 'expected_level': 'flash_crash'},
    ]
    for i, test in enumerate(vol_tests):
        result = manager.detect_extreme_volatility(test['atr_ratio'])
        status = "PASS" if result['level'] == test['expected_level'] else "FAIL"
        print(f"  Test {i+1}: {status} - ATR {test['atr_ratio']:.1f}x -> {result['level']}, "
              f"mult={result['leverage_multiplier']:.2f}")

    # Test 3: Liquidity Constraints
    print("\n3. Liquidity Constraints:")
    liq_tests = [
        {'spread': 0.0005, 'volume_ratio': 1.0, 'expected_constrained': False},
        {'spread': 0.003, 'volume_ratio': 0.5, 'expected_constrained': False},
        {'spread': 0.006, 'volume_ratio': 0.5, 'expected_constrained': True},
        {'spread': 0.001, 'volume_ratio': 0.05, 'expected_constrained': True},
    ]
    for i, test in enumerate(liq_tests):
        result = manager.check_liquidity_constraints(
            'TEST/USDT', test['spread'], test['volume_ratio']
        )
        status = "PASS" if result['is_constrained'] == test['expected_constrained'] else "FAIL"
        print(f"  Test {i+1}: {status} - spread={test['spread']*100:.2f}%, "
              f"vol={test['volume_ratio']*100:.0f}% -> constrained={result['is_constrained']}")

    # Test 4: Circuit Breaker
    print("\n4. Circuit Breaker Tests:")
    # Simulate consecutive losses
    manager2 = DynamicLeverageManager()
    for _ in range(5):
        manager2.record_trade_result(is_win=False)
    cb_result = manager2.check_circuit_breaker()
    print(f"  After 5 losses: breaker_active={cb_result['is_active']}, "
          f"floor={cb_result['leverage_floor']}x")

    # Test session loss trigger
    manager3 = DynamicLeverageManager()
    cb_result = manager3.check_circuit_breaker({'session_pnl_pct': -0.20})
    print(f"  Session -20% loss: breaker_active={cb_result['is_active']}")

    # Test 5: Combined Edge Case Factor
    print("\n5. Combined Edge Case Factor:")
    edge_result = manager.calculate_edge_case_factor(
        symbol='BTC/USDT',
        atr_ratio=2.8,  # High stress
        spread=0.004,   # High spread
        volume_ratio=0.2,  # Low volume
        current_price=50000,
        price_1m_ago=51000,  # -2% drop
        price_5m_ago=52000,  # -4% drop
        regime='HIGH_VOLATILITY'
    )
    print(f"  Combined multiplier: {edge_result['combined_multiplier']:.2f}")
    print(f"  Active edge cases: {edge_result['active_edge_cases']}")
    print(f"  Has edge cases: {edge_result['has_edge_cases']}")

    # Test 6: Optimal Leverage with Edge Cases
    print("\n6. Optimal Leverage with Edge Cases:")
    lev_result = manager.calculate_optimal_leverage(
        symbol='ETH/USDT',
        account_data={'margin_utilization': 0.80, 'current_drawdown': 0.12},
        position_data={'averaging_steps': 3, 'holding_hours': 20},
        market_data={
            'spread': 0.003,
            'volume_ratio': 0.4,
            'current_price': 3000,
            'price_1m_ago': 3020,
            'price_5m_ago': 3050
        }
    )
    print(f"  Optimal leverage: {lev_result['optimal_leverage']}x")
    print(f"  Health factor: {lev_result['health_factor']:.2f}")
    print(f"  Risk factor: {lev_result['risk_factor']:.2f}")
    print(f"  Edge case factor: {lev_result['edge_case_factor']:.2f}")
    print(f"  Edge cases active: {lev_result['edge_cases']['active']}")

    print("\n" + "=" * 60)
    print("All edge case tests completed!")
    print("=" * 60)
