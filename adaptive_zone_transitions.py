#!/usr/bin/env python3
"""
Adaptive Zone Transitions System
Sprint 3: Dynamic zone management that adapts to market conditions
Automatically adjusts thresholds based on volatility and performance
"""

import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
import logging


class AdaptiveZoneTransitions:
    """
    Dynamic zone transition system that adapts to market conditions
    Manages: Neutral, Averaging, Surplus Dump, Profit Taking, Stop Loss zones
    """

    def __init__(self):
        # Zone definitions (adaptive)
        self.zones = {
            'NEUTRAL': {
                'min_upnl': -0.15,
                'max_upnl': 0.15,
                'color': '⚪'
            },
            'AVERAGING': {
                'entry_threshold': -0.42,  # Base threshold
                'steps': [-0.42, -0.68, -0.84, -0.94, -1.00],
                'adaptive': True,
                'color': '🔴'
            },
            'SURPLUS_DUMP': {
                'trigger_upnl': 0.10,  # Min profit to enter
                'stage_1': 0.85,  # 85% of peak
                'stage_2': 0.50,  # 50% of peak
                'color': '🟡'
            },
            'PROFIT_TAKING': {
                'threshold': 5.00,  # $5 profit
                'partial_takes': [0.25, 0.50, 0.75],  # Partial profit %
                'color': '🟢'
            },
            'STOP_LOSS': {
                'threshold': -0.70,  # -70% of margin
                'adaptive': True,
                'color': '⛔'
            }
        }

        # Adaptation parameters
        self.adaptation_params = {
            'volatility_weight': 0.3,
            'momentum_weight': 0.2,
            'volume_weight': 0.15,
            'success_weight': 0.35,
            'learning_rate': 0.05
        }

        # Performance tracking
        self.zone_performance = {
            zone: {
                'entries': 0,
                'successful_exits': 0,
                'avg_duration': 0,
                'total_pnl': 0
            }
            for zone in self.zones
        }

        # Market condition memory
        self.market_conditions = {}

        # Configuration
        self.config_file = '/app/adaptive_zones_config.json'
        self.state_file = '/app/position_state.json'

        # Initialize
        self._setup_logging()
        self._load_configuration()

    def _setup_logging(self):
        """Configure logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('AdaptiveZones')

    def _load_configuration(self):
        """Load saved configuration"""
        try:
            with open(self.config_file, 'r') as f:
                saved = json.load(f)
                self.zones.update(saved.get('zones', {}))
                self.zone_performance.update(saved.get('performance', {}))
                self.logger.info("Loaded adaptive zone configuration")
        except:
            self.logger.info("Using default zone configuration")

    def determine_zone(
        self,
        symbol: str,
        upnl_pct: float,
        position_data: Dict
    ) -> Tuple[str, Dict]:
        """
        Determine current zone for position

        Args:
            symbol: Trading symbol
            upnl_pct: Current UPNL percentage
            position_data: Position information

        Returns:
            (zone_name, zone_params)
        """
        averaging_steps = position_data.get('averaging_steps', 0)
        peak_upnl = position_data.get('peak_upnl', 0)

        # Stop Loss check (highest priority)
        if self._check_stop_loss(symbol, upnl_pct):
            return 'STOP_LOSS', self.zones['STOP_LOSS']

        # Profit Taking check
        if upnl_pct >= self.zones['PROFIT_TAKING']['threshold']:
            return 'PROFIT_TAKING', self.zones['PROFIT_TAKING']

        # Surplus Dump check (positions that averaged and recovered)
        if averaging_steps > 0 and upnl_pct > self.zones['SURPLUS_DUMP']['trigger_upnl']:
            return 'SURPLUS_DUMP', self.zones['SURPLUS_DUMP']

        # Averaging check
        if self._check_averaging_zone(symbol, upnl_pct, averaging_steps):
            return 'AVERAGING', self.zones['AVERAGING']

        # Default to Neutral
        return 'NEUTRAL', self.zones['NEUTRAL']

    def should_transition(
        self,
        symbol: str,
        current_zone: str,
        new_zone: str,
        market_data: Dict
    ) -> Tuple[bool, str]:
        """
        Determine if zone transition should occur

        Args:
            symbol: Trading symbol
            current_zone: Current zone
            new_zone: Proposed new zone
            market_data: Current market data

        Returns:
            (should_transition, reason)
        """
        # No transition needed
        if current_zone == new_zone:
            return False, "Same zone"

        # Validate transition rules
        valid, reason = self._validate_transition(current_zone, new_zone, market_data)

        if valid:
            # Record zone entry
            self.zone_performance[new_zone]['entries'] += 1
            self.logger.info(
                f"{symbol}: Zone transition {current_zone} → {new_zone} "
                f"({self.zones[new_zone]['color']})"
            )

        return valid, reason

    def _validate_transition(
        self,
        from_zone: str,
        to_zone: str,
        market_data: Dict
    ) -> Tuple[bool, str]:
        """
        Validate zone transition rules

        Args:
            from_zone: Current zone
            to_zone: Target zone
            market_data: Market data

        Returns:
            (is_valid, reason)
        """
        # Define valid transitions
        valid_transitions = {
            'NEUTRAL': ['AVERAGING', 'PROFIT_TAKING', 'STOP_LOSS'],
            'AVERAGING': ['NEUTRAL', 'SURPLUS_DUMP', 'STOP_LOSS'],
            'SURPLUS_DUMP': ['NEUTRAL', 'PROFIT_TAKING', 'AVERAGING'],
            'PROFIT_TAKING': ['NEUTRAL'],
            'STOP_LOSS': []  # Terminal state
        }

        if to_zone not in valid_transitions.get(from_zone, []):
            return False, f"Invalid transition: {from_zone} → {to_zone}"

        # Additional validation based on market conditions
        volatility = market_data.get('volatility', 0.02)

        # High volatility: be more conservative
        if volatility > 0.05:
            if to_zone == 'AVERAGING':
                return False, "Volatility too high for averaging"

        return True, "Transition valid"

    def adapt_thresholds(
        self,
        symbol: str,
        market_data: Dict,
        performance_data: Dict
    ):
        """
        Dynamically adapt zone thresholds based on conditions

        Args:
            symbol: Trading symbol
            market_data: Current market conditions
            performance_data: Historical performance
        """
        try:
            # Extract metrics
            volatility = market_data.get('volatility', 0.02)
            volume_ratio = market_data.get('volume_ratio', 1.0)
            momentum = market_data.get('momentum', 0)
            success_rate = performance_data.get('success_rate', 0.5)

            # Calculate adjustment factors
            vol_factor = 1 + (volatility - 0.02) * self.adaptation_params['volatility_weight']
            mom_factor = 1 + momentum * self.adaptation_params['momentum_weight']
            vol_ratio_factor = 1 + (volume_ratio - 1) * self.adaptation_params['volume_weight']
            success_factor = 1 + (success_rate - 0.5) * self.adaptation_params['success_weight']

            # Combined adjustment
            adjustment = (vol_factor * mom_factor * vol_ratio_factor * success_factor - 1) * \
                        self.adaptation_params['learning_rate']

            # Adapt Averaging thresholds
            if self.zones['AVERAGING']['adaptive']:
                old_threshold = self.zones['AVERAGING']['entry_threshold']
                new_threshold = old_threshold * (1 + adjustment)

                # Constrain to reasonable range
                new_threshold = max(-0.60, min(-0.30, new_threshold))

                if abs(new_threshold - old_threshold) > 0.01:
                    self.zones['AVERAGING']['entry_threshold'] = new_threshold

                    # Adjust all steps proportionally
                    ratio = new_threshold / -0.42
                    self.zones['AVERAGING']['steps'] = [
                        -0.42 * ratio,
                        -0.68 * ratio,
                        -0.84 * ratio,
                        -0.94 * ratio,
                        -1.00 * ratio
                    ]

                    self.logger.info(
                        f"Adapted averaging threshold: {old_threshold:.2%} → {new_threshold:.2%}"
                    )

            # Adapt Stop Loss threshold
            if self.zones['STOP_LOSS']['adaptive']:
                old_sl = self.zones['STOP_LOSS']['threshold']
                new_sl = old_sl * (1 - adjustment)  # Inverse adjustment for stop loss

                # Constrain to reasonable range
                new_sl = max(-0.90, min(-0.50, new_sl))

                if abs(new_sl - old_sl) > 0.01:
                    self.zones['STOP_LOSS']['threshold'] = new_sl
                    self.logger.info(
                        f"Adapted stop loss: {old_sl:.2%} → {new_sl:.2%}"
                    )

            # Save configuration
            self._save_configuration()

        except Exception as e:
            self.logger.error(f"Threshold adaptation error: {e}")

    def get_zone_action(
        self,
        zone: str,
        position_data: Dict
    ) -> Dict:
        """
        Get recommended action for zone

        Args:
            zone: Current zone
            position_data: Position information

        Returns:
            Action dictionary
        """
        actions = {
            'NEUTRAL': {
                'action': 'monitor',
                'description': 'Monitor position',
                'params': {}
            },
            'AVERAGING': {
                'action': 'average_down',
                'description': 'Execute averaging step',
                'params': {
                    'step': position_data.get('averaging_steps', 0),
                    'multiplier': self._get_fibonacci_multiplier(
                        position_data.get('averaging_steps', 0)
                    )
                }
            },
            'SURPLUS_DUMP': {
                'action': 'dump_surplus',
                'description': 'Execute surplus dump',
                'params': {
                    'stage': position_data.get('surplus_stage', 0),
                    'percentage': 0.5  # Dump 50% each stage
                }
            },
            'PROFIT_TAKING': {
                'action': 'take_profit',
                'description': 'Take profits',
                'params': {
                    'percentage': 0.25  # Take 25% at a time
                }
            },
            'STOP_LOSS': {
                'action': 'close_position',
                'description': 'Emergency close',
                'params': {
                    'urgency': 'immediate'
                }
            }
        }

        return actions.get(zone, actions['NEUTRAL'])

    def _check_stop_loss(self, symbol: str, upnl_pct: float) -> bool:
        """Check if stop loss should trigger"""
        threshold = self.zones['STOP_LOSS']['threshold']

        # Additional safety for high-risk positions
        if symbol in self.market_conditions:
            risk_level = self.market_conditions[symbol].get('risk_level', 'medium')
            if risk_level == 'high':
                threshold *= 0.8  # Tighter stop for high risk

        return upnl_pct <= threshold

    def _check_averaging_zone(
        self,
        symbol: str,
        upnl_pct: float,
        steps_taken: int
    ) -> bool:
        """Check if position should enter/remain in averaging zone"""
        # Check if we've hit the next averaging threshold
        thresholds = self.zones['AVERAGING']['steps']

        if steps_taken < len(thresholds):
            next_threshold = thresholds[steps_taken]

            # Apply market condition adjustments
            if symbol in self.market_conditions:
                volatility = self.market_conditions[symbol].get('volatility', 0.02)
                # Wider threshold in high volatility
                next_threshold *= (1 + volatility)

            return upnl_pct <= next_threshold

        return False

    def _get_fibonacci_multiplier(self, step: int) -> float:
        """Get Fibonacci multiplier for averaging step"""
        fibonacci = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]
        return fibonacci[step] if step < len(fibonacci) else fibonacci[-1]

    def record_zone_exit(
        self,
        zone: str,
        duration: float,
        pnl: float,
        success: bool
    ):
        """
        Record zone exit for performance tracking

        Args:
            zone: Zone being exited
            duration: Time in zone (seconds)
            pnl: PnL from zone
            success: Whether exit was successful
        """
        perf = self.zone_performance[zone]

        if success:
            perf['successful_exits'] += 1

        # Update moving averages
        alpha = 0.1  # Exponential smoothing factor
        perf['avg_duration'] = (1 - alpha) * perf['avg_duration'] + alpha * duration
        perf['total_pnl'] += pnl

        # Calculate zone effectiveness
        if perf['entries'] > 0:
            effectiveness = perf['successful_exits'] / perf['entries']
            self.logger.info(
                f"Zone {zone} effectiveness: {effectiveness:.2%} "
                f"(PnL: ${perf['total_pnl']:.2f})"
            )

    def get_zone_statistics(self) -> Dict:
        """Get zone performance statistics"""
        stats = {}

        for zone, perf in self.zone_performance.items():
            if perf['entries'] > 0:
                stats[zone] = {
                    'success_rate': perf['successful_exits'] / perf['entries'],
                    'avg_duration': perf['avg_duration'],
                    'total_pnl': perf['total_pnl'],
                    'entries': perf['entries']
                }

        return stats

    def update_market_conditions(self, symbol: str, conditions: Dict):
        """
        Update market conditions for symbol

        Args:
            symbol: Trading symbol
            conditions: Market condition data
        """
        self.market_conditions[symbol] = {
            'volatility': conditions.get('volatility', 0.02),
            'volume_ratio': conditions.get('volume_ratio', 1.0),
            'momentum': conditions.get('momentum', 0),
            'trend': conditions.get('trend', 0),
            'risk_level': self._assess_risk_level(conditions),
            'timestamp': datetime.now().isoformat()
        }

    def _assess_risk_level(self, conditions: Dict) -> str:
        """Assess risk level from conditions"""
        volatility = conditions.get('volatility', 0.02)
        volume = conditions.get('volume_ratio', 1.0)

        if volatility > 0.05 or volume < 0.5:
            return 'high'
        elif volatility > 0.03 or volume < 0.8:
            return 'medium'
        else:
            return 'low'

    def _save_configuration(self):
        """Save adaptive configuration"""
        try:
            config = {
                'zones': self.zones,
                'performance': self.zone_performance,
                'adaptation_params': self.adaptation_params,
                'timestamp': datetime.now().isoformat()
            }

            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

        except Exception as e:
            self.logger.error(f"Save config error: {e}")


def main():
    """Test adaptive zone transitions"""
    zones = AdaptiveZoneTransitions()

    print("\n" + "="*70)
    print("🎯 ADAPTIVE ZONE TRANSITIONS TEST")
    print("="*70)

    # Test zone determination
    test_positions = [
        {'symbol': 'BTC/USDT', 'upnl_pct': -5, 'averaging_steps': 0},
        {'symbol': 'ETH/USDT', 'upnl_pct': -45, 'averaging_steps': 0},
        {'symbol': 'SOL/USDT', 'upnl_pct': 12, 'averaging_steps': 2},
        {'symbol': 'DOGE/USDT', 'upnl_pct': -75, 'averaging_steps': 3},
    ]

    print("\n📊 Zone Determination:")
    for pos in test_positions:
        zone, params = zones.determine_zone(
            pos['symbol'],
            pos['upnl_pct'],
            pos
        )
        print(f"  {pos['symbol']}: UPNL={pos['upnl_pct']}% → {zone} {params['color']}")

    # Test adaptation
    print("\n🔄 Testing Threshold Adaptation...")
    market_data = {
        'volatility': 0.04,
        'volume_ratio': 1.5,
        'momentum': -0.02
    }
    performance_data = {
        'success_rate': 0.65
    }

    zones.adapt_thresholds('BTC/USDT', market_data, performance_data)

    # Get zone actions
    print("\n⚡ Recommended Actions:")
    for zone_name in ['NEUTRAL', 'AVERAGING', 'SURPLUS_DUMP']:
        action = zones.get_zone_action(zone_name, {'averaging_steps': 1})
        print(f"  {zone_name}: {action['description']}")

    # Display statistics
    stats = zones.get_zone_statistics()
    if stats:
        print("\n📈 Zone Statistics:")
        for zone, data in stats.items():
            print(f"  {zone}: Success={data['success_rate']:.1%}")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()