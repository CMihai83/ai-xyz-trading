#!/usr/bin/env python3
"""
Trailing Surplus Dumps System
Sprint 4: Advanced profit-taking with trailing mechanisms
Maximizes profit capture while protecting gains
"""

import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional, List
import logging


class TrailingSurplusDumps:
    """
    Intelligent trailing mechanism for surplus dumps
    Dynamically adjusts dump levels based on momentum
    """

    def __init__(self):
        # Trailing parameters
        self.trailing_config = {
            'activation_profit': 0.10,  # $0.10 minimum to activate
            'trail_distance': 0.15,  # 15% trailing distance
            'step_size': 0.05,  # 5% step increments
            'momentum_factor': 0.2,  # Momentum adjustment
            'volatility_factor': 0.3,  # Volatility adjustment
            'max_trail': 0.30,  # Maximum 30% trail
            'min_trail': 0.10,  # Minimum 10% trail
        }

        # Dump stages with trailing
        self.dump_stages = [
            {
                'name': 'Stage 1',
                'trigger_pct': 0.85,  # 85% of peak
                'dump_ratio': 0.5,  # Dump 50%
                'trail_enabled': True,
                'trail_tightening': 0.02  # Tighten by 2% each update
            },
            {
                'name': 'Stage 2',
                'trigger_pct': 0.50,  # 50% of peak
                'dump_ratio': 0.5,  # Dump remaining 50%
                'trail_enabled': True,
                'trail_tightening': 0.03  # Tighten by 3%
            }
        ]

        # Position tracking
        self.position_trails = {}
        self.peak_values = {}
        self.trailing_stops = {}

        # Performance metrics
        self.metrics = {
            'total_dumps': 0,
            'successful_trails': 0,
            'premature_exits': 0,
            'avg_trail_improvement': 0,
            'total_profit_captured': 0
        }

        # Logging
        self._setup_logging()

        # State persistence
        self.state_file = '/app/trailing_state.json'
        self._load_state()

    def _setup_logging(self):
        """Configure logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('TrailingSurplus')

    def update_position(
        self,
        symbol: str,
        current_upnl: float,
        position_data: Dict,
        market_data: Dict
    ) -> Tuple[bool, Optional[Dict]]:
        """
        Update trailing surplus for position

        Args:
            symbol: Trading symbol
            current_upnl: Current unrealized PnL
            position_data: Position information
            market_data: Market conditions

        Returns:
            (should_dump, dump_params)
        """
        averaging_steps = position_data.get('averaging_steps', 0)

        # Only trail positions that have averaged
        if averaging_steps == 0:
            return False, None

        # Check minimum profit threshold
        if current_upnl < self.trailing_config['activation_profit']:
            return False, None

        # Initialize or update peak
        if symbol not in self.peak_values:
            self.peak_values[symbol] = current_upnl
            self.position_trails[symbol] = {
                'stage': 0,
                'trail_distance': self.trailing_config['trail_distance'],
                'last_update': datetime.now(),
                'momentum': 0
            }
            self.logger.info(f"{symbol}: Trailing activated at ${current_upnl:.2f}")

        # Update peak if new high
        if current_upnl > self.peak_values[symbol]:
            old_peak = self.peak_values[symbol]
            self.peak_values[symbol] = current_upnl

            # Tighten trail on new peak
            self._tighten_trail(symbol, current_upnl, old_peak)

            self.logger.info(
                f"{symbol}: New peak ${current_upnl:.2f} "
                f"(+${current_upnl - old_peak:.2f})"
            )

        # Calculate trailing stop
        trailing_stop = self._calculate_trailing_stop(
            symbol,
            self.peak_values[symbol],
            market_data
        )

        # Check if trailing stop hit
        if current_upnl <= trailing_stop:
            dump_params = self._prepare_dump(
                symbol,
                current_upnl,
                position_data
            )

            if dump_params:
                self.logger.info(
                    f"{symbol}: Trailing stop hit at ${current_upnl:.2f} "
                    f"(peak: ${self.peak_values[symbol]:.2f})"
                )
                return True, dump_params

        # Update trailing information
        self._update_trail_metrics(symbol, current_upnl, market_data)

        return False, None

    def _calculate_trailing_stop(
        self,
        symbol: str,
        peak: float,
        market_data: Dict
    ) -> float:
        """
        Calculate dynamic trailing stop level

        Args:
            symbol: Trading symbol
            peak: Peak UPNL value
            market_data: Market conditions

        Returns:
            Trailing stop level
        """
        trail_info = self.position_trails[symbol]
        base_distance = trail_info['trail_distance']

        # Adjust for volatility
        volatility = market_data.get('volatility', 0.02)
        vol_adjustment = volatility * self.trailing_config['volatility_factor']

        # Adjust for momentum
        momentum = market_data.get('momentum', 0)
        mom_adjustment = momentum * self.trailing_config['momentum_factor']

        # Calculate adjusted trail distance
        adjusted_distance = base_distance + vol_adjustment - mom_adjustment

        # Apply limits
        adjusted_distance = max(
            self.trailing_config['min_trail'],
            min(self.trailing_config['max_trail'], adjusted_distance)
        )

        # Calculate stop level
        trailing_stop = peak * (1 - adjusted_distance)

        # Store for monitoring
        self.trailing_stops[symbol] = {
            'stop_level': trailing_stop,
            'distance': adjusted_distance,
            'peak': peak,
            'timestamp': datetime.now().isoformat()
        }

        return trailing_stop

    def _tighten_trail(
        self,
        symbol: str,
        new_peak: float,
        old_peak: float
    ):
        """
        Tighten trailing distance on new peaks

        Args:
            symbol: Trading symbol
            new_peak: New peak value
            old_peak: Previous peak value
        """
        trail_info = self.position_trails[symbol]

        # Calculate momentum
        peak_increase = (new_peak - old_peak) / old_peak if old_peak > 0 else 0
        trail_info['momentum'] = peak_increase

        # Get current stage
        stage = trail_info['stage']

        if stage < len(self.dump_stages):
            stage_config = self.dump_stages[stage]

            if stage_config['trail_enabled']:
                # Tighten trail
                tightening = stage_config['trail_tightening']

                # Extra tightening for strong momentum
                if peak_increase > 0.05:  # 5% jump
                    tightening *= 1.5

                # Apply tightening
                old_distance = trail_info['trail_distance']
                new_distance = max(
                    self.trailing_config['min_trail'],
                    old_distance - tightening
                )

                trail_info['trail_distance'] = new_distance

                self.logger.info(
                    f"{symbol}: Trail tightened {old_distance:.1%} → {new_distance:.1%}"
                )

    def _prepare_dump(
        self,
        symbol: str,
        current_upnl: float,
        position_data: Dict
    ) -> Optional[Dict]:
        """
        Prepare dump parameters

        Args:
            symbol: Trading symbol
            current_upnl: Current UPNL
            position_data: Position information

        Returns:
            Dump parameters or None
        """
        trail_info = self.position_trails[symbol]
        stage = trail_info['stage']

        if stage >= len(self.dump_stages):
            return None

        stage_config = self.dump_stages[stage]

        # Calculate dump size
        position_size = position_data.get('amount', 0)
        averaging_steps = position_data.get('averaging_steps', 0)

        # Calculate surplus (size from averaging)
        base_size = position_size / sum([1] + [1, 2, 3, 5, 8][:averaging_steps])
        surplus_size = position_size - base_size

        # Dump portion of surplus
        dump_size = surplus_size * stage_config['dump_ratio']

        dump_params = {
            'symbol': symbol,
            'stage': stage_config['name'],
            'dump_size': dump_size,
            'dump_ratio': stage_config['dump_ratio'],
            'current_upnl': current_upnl,
            'peak_upnl': self.peak_values[symbol],
            'capture_ratio': current_upnl / self.peak_values[symbol],
            'reason': 'Trailing stop triggered',
            'timestamp': datetime.now().isoformat()
        }

        # Update metrics
        self.metrics['total_dumps'] += 1
        self.metrics['total_profit_captured'] += current_upnl * stage_config['dump_ratio']

        # Move to next stage
        trail_info['stage'] += 1

        return dump_params

    def _update_trail_metrics(
        self,
        symbol: str,
        current_upnl: float,
        market_data: Dict
    ):
        """
        Update trailing metrics and analytics

        Args:
            symbol: Trading symbol
            current_upnl: Current UPNL
            market_data: Market conditions
        """
        trail_info = self.position_trails[symbol]

        # Calculate time in trail
        time_in_trail = (datetime.now() - trail_info['last_update']).total_seconds()

        # Update trail info
        trail_info['last_update'] = datetime.now()
        trail_info['current_distance'] = (
            self.peak_values[symbol] - current_upnl
        ) / self.peak_values[symbol]

        # Check if trail is working well
        if trail_info['current_distance'] < trail_info['trail_distance'] * 0.5:
            # Position is strong, trail is protecting profits well
            self.metrics['successful_trails'] += 1

    def get_trail_status(self, symbol: str) -> Optional[Dict]:
        """
        Get current trailing status for position

        Args:
            symbol: Trading symbol

        Returns:
            Trail status dictionary
        """
        if symbol not in self.position_trails:
            return None

        trail_info = self.position_trails[symbol]
        peak = self.peak_values.get(symbol, 0)
        stop = self.trailing_stops.get(symbol, {})

        return {
            'symbol': symbol,
            'stage': trail_info['stage'],
            'peak_upnl': peak,
            'trail_distance': trail_info['trail_distance'],
            'trailing_stop': stop.get('stop_level', 0),
            'momentum': trail_info['momentum'],
            'stage_name': self.dump_stages[trail_info['stage']]['name']
                         if trail_info['stage'] < len(self.dump_stages) else 'Complete'
        }

    def optimize_trailing_parameters(self, performance_data: List[Dict]):
        """
        Optimize trailing parameters based on performance

        Args:
            performance_data: Historical performance records
        """
        if len(performance_data) < 20:
            return

        try:
            # Analyze performance
            successful = [p for p in performance_data if p.get('success', False)]
            failed = [p for p in performance_data if not p.get('success', False)]

            if successful:
                # Calculate optimal trail distance
                avg_drawdown = np.mean([
                    p.get('max_drawdown', 0.15) for p in successful
                ])

                # Adjust trail distance
                old_distance = self.trailing_config['trail_distance']
                new_distance = min(
                    self.trailing_config['max_trail'],
                    max(self.trailing_config['min_trail'], avg_drawdown * 1.2)
                )

                if abs(new_distance - old_distance) > 0.02:
                    self.trailing_config['trail_distance'] = new_distance
                    self.logger.info(
                        f"Optimized trail distance: {old_distance:.1%} → {new_distance:.1%}"
                    )

            # Analyze premature exits
            if failed:
                premature_rate = len(failed) / len(performance_data)

                if premature_rate > 0.3:  # Too many premature exits
                    # Loosen trail
                    self.trailing_config['trail_distance'] = min(
                        self.trailing_config['max_trail'],
                        self.trailing_config['trail_distance'] * 1.1
                    )
                    self.logger.info("Loosened trail due to premature exits")

            self._save_state()

        except Exception as e:
            self.logger.error(f"Optimization error: {e}")

    def reset_position_trail(self, symbol: str):
        """
        Reset trailing for position

        Args:
            symbol: Trading symbol
        """
        if symbol in self.position_trails:
            del self.position_trails[symbol]
        if symbol in self.peak_values:
            del self.peak_values[symbol]
        if symbol in self.trailing_stops:
            del self.trailing_stops[symbol]

        self.logger.info(f"{symbol}: Trail reset")

    def get_metrics(self) -> Dict:
        """Get performance metrics"""
        return {
            'total_dumps': self.metrics['total_dumps'],
            'successful_trails': self.metrics['successful_trails'],
            'premature_exits': self.metrics['premature_exits'],
            'avg_capture_ratio': (
                self.metrics['successful_trails'] / self.metrics['total_dumps']
                if self.metrics['total_dumps'] > 0 else 0
            ),
            'total_profit_captured': self.metrics['total_profit_captured'],
            'active_trails': len(self.position_trails)
        }

    def _load_state(self):
        """Load saved state"""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                self.position_trails = state.get('trails', {})
                self.peak_values = state.get('peaks', {})
                self.metrics = state.get('metrics', self.metrics)
                self.trailing_config.update(state.get('config', {}))
        except:
            pass

    def _save_state(self):
        """Save current state"""
        try:
            state = {
                'trails': self.position_trails,
                'peaks': self.peak_values,
                'metrics': self.metrics,
                'config': self.trailing_config,
                'timestamp': datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            self.logger.error(f"Save state error: {e}")


def main():
    """Test trailing surplus dumps"""
    trailing = TrailingSurplusDumps()

    print("\n" + "="*70)
    print("📈 TRAILING SURPLUS DUMPS TEST")
    print("="*70)

    # Test position updates
    test_positions = [
        {
            'symbol': 'BTC/USDT',
            'upnl_sequence': [0.05, 0.10, 0.15, 0.25, 0.20, 0.18, 0.12],
            'averaging_steps': 2
        },
        {
            'symbol': 'ETH/USDT',
            'upnl_sequence': [0.08, 0.12, 0.30, 0.35, 0.28],
            'averaging_steps': 3
        }
    ]

    market_data = {
        'volatility': 0.02,
        'momentum': 0.01
    }

    print("\n📊 Testing Trailing Updates:")
    for pos in test_positions:
        print(f"\n{pos['symbol']}:")

        for i, upnl in enumerate(pos['upnl_sequence']):
            should_dump, params = trailing.update_position(
                pos['symbol'],
                upnl,
                {'averaging_steps': pos['averaging_steps'], 'amount': 100},
                market_data
            )

            status = trailing.get_trail_status(pos['symbol'])

            if status:
                print(f"  Step {i+1}: UPNL=${upnl:.2f}, Peak=${status['peak_upnl']:.2f}, "
                      f"Stop=${status['trailing_stop']:.2f}")

                if should_dump:
                    print(f"  🔔 DUMP TRIGGERED: {params['reason']}")

    # Display metrics
    metrics = trailing.get_metrics()
    print("\n📈 Performance Metrics:")
    for key, value in metrics.items():
        if isinstance(value, float):
            print(f"  {key}: {value:.2f}")
        else:
            print(f"  {key}: {value}")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()