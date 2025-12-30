#!/usr/bin/env python3
"""
Averaging Orchestrator - Combines multiple averaging strategies intelligently
Non-breaking integration with current AI-XYZ system
"""

import json
import logging
import os
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path
import importlib
import sys

# Add plugins directory to path
sys.path.insert(0, '/app/averaging_plugins')

from averaging_plugins.plugin_interface import (
    AveragingPlugin,
    PluginManager,
    Signal,
    SignalAction,
    MarketData
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/orchestrator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class AveragingOrchestrator:
    """
    Orchestrates multiple averaging strategies
    Provides weighted decision making and conflict resolution
    """

    def __init__(self, config_path: str = "/app/averaging_config.json"):
        """Initialize orchestrator with configuration"""
        self.config_path = config_path
        self.config = self.load_config()
        self.plugin_manager = PluginManager()
        self.decision_history = []
        self.ab_test_results = []

        # Load and register plugins
        self.load_plugins()

        logger.info(f"Orchestrator initialized with {len(self.plugin_manager.plugins)} plugins")

    def load_config(self) -> Dict:
        """Load orchestrator configuration"""
        default_config = {
            "mode": "hybrid",  # hybrid, fibonacci_only, dynamic_only
            "plugins": {
                "fibonacci": {
                    "enabled": True,
                    "weight": 0.9,  # Start conservative
                    "priority": 100
                },
                "dynamic_pattern": {
                    "enabled": False,  # Start disabled
                    "weight": 0.1,
                    "priority": 90
                }
            },
            "aggregation": {
                "method": "weighted_average",
                "min_combined_confidence": 0.7,
                "conflict_resolution": "highest_priority"
            },
            "testing": {
                "ab_test_mode": False,
                "log_all_signals": True,
                "dry_run": False
            },
            "safety": {
                "max_position_multiplier": 10.0,
                "circuit_breaker_loss_pct": 2.0,
                "enable_rollback": True
            }
        }

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    loaded_config = json.load(f)
                    # Merge with defaults
                    default_config.update(loaded_config)
                    logger.info(f"Loaded configuration from {self.config_path}")
            except Exception as e:
                logger.error(f"Error loading config: {e}, using defaults")

        return default_config

    def save_config(self):
        """Save current configuration"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info("Configuration saved")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def load_plugins(self):
        """Dynamically load and register enabled plugins"""
        # Load Fibonacci plugin (current logic)
        if self.config['plugins'].get('fibonacci', {}).get('enabled', True):
            try:
                from averaging_plugins.fibonacci_plugin import FibonacciAveragingPlugin
                plugin = FibonacciAveragingPlugin(
                    config=self.config['plugins']['fibonacci']
                )
                self.plugin_manager.register_plugin(plugin)
            except ImportError:
                logger.warning("Fibonacci plugin not yet implemented, skipping")

        # Load Dynamic Pattern plugin (new logic)
        if self.config['plugins'].get('dynamic_pattern', {}).get('enabled', False):
            try:
                from averaging_plugins.dynamic_pattern_plugin import DynamicPatternPlugin
                plugin = DynamicPatternPlugin(
                    config=self.config['plugins']['dynamic_pattern']
                )
                self.plugin_manager.register_plugin(plugin)
            except ImportError:
                logger.warning("Dynamic pattern plugin not yet implemented, skipping")

        # Auto-discover additional plugins
        self.auto_discover_plugins()

    def auto_discover_plugins(self):
        """Auto-discover and load plugins from averaging_plugins directory"""
        plugin_dir = Path('/app/averaging_plugins')

        for plugin_file in plugin_dir.glob('*_plugin.py'):
            if plugin_file.stem in ['fibonacci_plugin', 'dynamic_pattern_plugin']:
                continue  # Already handled

            try:
                module_name = plugin_file.stem
                module = importlib.import_module(f'averaging_plugins.{module_name}')

                # Look for plugin classes
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and
                        issubclass(attr, AveragingPlugin) and
                        attr != AveragingPlugin):

                        # Check if enabled in config
                        plugin_config = self.config['plugins'].get(module_name, {})
                        if plugin_config.get('enabled', False):
                            plugin = attr(config=plugin_config)
                            self.plugin_manager.register_plugin(plugin)
                            logger.info(f"Auto-discovered and loaded plugin: {attr.__name__}")

            except Exception as e:
                logger.error(f"Error loading plugin {plugin_file}: {e}")

    def get_market_data(self, symbol: str) -> MarketData:
        """Fetch current market data for symbol"""
        # This would connect to exchange API in production
        # For now, return mock data
        return MarketData(
            symbol=symbol,
            current_price=0.0,  # Will be filled from position_state
            bid=0.0,
            ask=0.0,
            volume_24h=0.0,
            high_24h=0.0,
            low_24h=0.0,
            timestamp=datetime.now()
        )

    def get_averaging_decision(self, position: Dict, market_data: MarketData) -> Signal:
        """
        Main orchestration method - aggregates signals from all plugins

        Args:
            position: Current position data
            market_data: Current market data

        Returns:
            Aggregated Signal with decision
        """
        if not self.plugin_manager.plugins:
            logger.warning("No plugins loaded, returning HOLD signal")
            return Signal(
                action=SignalAction.HOLD,
                confidence=1.0,
                reason="No plugins available"
            )

        # Collect signals from all plugins
        signals = []
        for plugin in self.plugin_manager.get_sorted_plugins():
            try:
                if not plugin.validate_position(position):
                    continue

                signal = plugin.analyze(position, market_data)

                # Convert CamelCase class name to snake_case config key
                # DynamicPatternPlugin -> dynamic_pattern_plugin -> dynamic_pattern
                class_name = plugin.__class__.__name__
                config_key = ''.join(['_' + c.lower() if c.isupper() else c for c in class_name]).lstrip('_')
                # Remove trailing _plugin if present
                if config_key.endswith('_plugin'):
                    config_key = config_key[:-7]

                plugin_config = self.config['plugins'].get(config_key, {})
                logger.info(f"🔑 Plugin {class_name} -> config key '{config_key}' -> weight: {plugin_config.get('weight', 0.5)}")

                signals.append({
                    'plugin': plugin.name,
                    'signal': signal,
                    'priority': plugin.get_priority(),
                    'weight': plugin_config.get('weight', 0.5)
                })

                logger.debug(f"Plugin {plugin.name} signal: {signal.action} "
                           f"(confidence: {signal.confidence:.2f})")

            except Exception as e:
                logger.error(f"Error in plugin {plugin.name}: {e}")
                continue

        # Aggregate signals based on configuration
        aggregated_signal = self.aggregate_signals(signals)

        # Log decision
        self.log_decision(position, signals, aggregated_signal)

        # A/B testing if enabled
        if self.config['testing']['ab_test_mode']:
            self.run_ab_test(signals, aggregated_signal)

        return aggregated_signal

    def aggregate_signals(self, signals: List[Dict]) -> Signal:
        """
        Aggregate multiple signals into final decision

        Args:
            signals: List of signal dictionaries from plugins

        Returns:
            Aggregated Signal
        """
        if not signals:
            return Signal(
                action=SignalAction.HOLD,
                confidence=1.0,
                reason="No valid signals"
            )

        method = self.config['aggregation']['method']

        if method == 'highest_priority':
            # Use highest priority signal above confidence threshold
            min_confidence = self.config['aggregation']['min_combined_confidence']
            for sig_dict in signals:
                if sig_dict['signal'].confidence >= min_confidence:
                    return sig_dict['signal']

        elif method == 'weighted_average':
            # Calculate weighted average of signals
            total_weight = sum(s['weight'] for s in signals)

            if total_weight == 0:
                return signals[0]['signal']  # Fallback to highest priority

            # Group by action
            action_weights = {}
            action_signals = {}

            for sig_dict in signals:
                action = sig_dict['signal'].action
                weight = sig_dict['weight']
                confidence = sig_dict['signal'].confidence

                logger.info(f"📊 Processing signal: action={action}, weight={weight}, confidence={confidence:.2f}")

                if action not in action_weights:
                    action_weights[action] = 0
                    action_signals[action] = []

                action_weights[action] += weight * confidence
                action_signals[action].append(sig_dict)

            # Select action with highest weighted confidence
            best_action = max(action_weights, key=action_weights.get)
            combined_confidence = action_weights[best_action] / total_weight

            logger.info(f"🔍 Action weights: {action_weights}")
            logger.info(f"🎯 Best action: {best_action}, combined_confidence: {combined_confidence:.2f}")

            # Get average size if averaging
            if best_action == SignalAction.AVERAGE:
                sizes = [s['signal'].size for s in action_signals[best_action]
                        if s['signal'].size is not None]
                avg_size = sum(sizes) / len(sizes) if sizes else None
            else:
                avg_size = None

            # Combine reasons
            reasons = [s['signal'].reason for s in action_signals[best_action]]
            combined_reason = f"Weighted consensus: {', '.join(set(reasons))}"

            return Signal(
                action=best_action,
                confidence=combined_confidence,
                size=avg_size,
                reason=combined_reason
            )

        elif method == 'consensus':
            # Require majority agreement
            action_counts = {}
            for sig_dict in signals:
                action = sig_dict['signal'].action
                action_counts[action] = action_counts.get(action, 0) + 1

            # Check if any action has majority
            total_signals = len(signals)
            for action, count in action_counts.items():
                if count > total_signals / 2:
                    # Get highest confidence signal for this action
                    action_signals = [s for s in signals
                                    if s['signal'].action == action]
                    best = max(action_signals,
                             key=lambda s: s['signal'].confidence)
                    return best['signal']

        # Fallback to highest priority
        return signals[0]['signal']

    def log_decision(self, position: Dict, signals: List[Dict],
                     final_signal: Signal):
        """Log decision details for analysis"""
        decision_entry = {
            'timestamp': datetime.now().isoformat(),
            'symbol': position.get('symbol', 'UNKNOWN'),
            'signals': [
                {
                    'plugin': s['plugin'],
                    'action': s['signal'].action.value,
                    'confidence': s['signal'].confidence,
                    'reason': s['signal'].reason
                }
                for s in signals
            ],
            'final_decision': {
                'action': final_signal.action.value,
                'confidence': final_signal.confidence,
                'reason': final_signal.reason
            }
        }

        self.decision_history.append(decision_entry)

        # Save to file if configured
        if self.config['testing']['log_all_signals']:
            self.save_decision_log()

    def save_decision_log(self):
        """Save decision history to file"""
        try:
            log_file = '/app/logs/orchestrator_decisions.json'
            with open(log_file, 'w') as f:
                json.dump(self.decision_history[-1000:], f, indent=2)
        except Exception as e:
            logger.error(f"Error saving decision log: {e}")

    def run_ab_test(self, signals: List[Dict], final_signal: Signal):
        """Run A/B test comparing plugin performance"""
        # Find fibonacci and dynamic signals
        fibonacci_signal = None
        dynamic_signal = None

        for sig_dict in signals:
            if 'Fibonacci' in sig_dict['plugin']:
                fibonacci_signal = sig_dict['signal']
            elif 'Dynamic' in sig_dict['plugin']:
                dynamic_signal = sig_dict['signal']

        if fibonacci_signal and dynamic_signal:
            self.ab_test_results.append({
                'timestamp': datetime.now().isoformat(),
                'fibonacci': {
                    'action': fibonacci_signal.action.value,
                    'confidence': fibonacci_signal.confidence
                },
                'dynamic': {
                    'action': dynamic_signal.action.value,
                    'confidence': dynamic_signal.confidence
                },
                'final': {
                    'action': final_signal.action.value,
                    'confidence': final_signal.confidence
                }
            })

            # Save A/B test results
            if len(self.ab_test_results) % 10 == 0:  # Save every 10 tests
                self.save_ab_test_results()

    def save_ab_test_results(self):
        """Save A/B test results for analysis"""
        try:
            ab_file = '/app/logs/ab_test_results.json'
            with open(ab_file, 'w') as f:
                json.dump(self.ab_test_results[-1000:], f, indent=2)
            logger.info(f"Saved {len(self.ab_test_results)} A/B test results")
        except Exception as e:
            logger.error(f"Error saving A/B test results: {e}")

    def update_plugin_weights(self, performance_data: Dict):
        """
        Dynamically update plugin weights based on performance

        Args:
            performance_data: Dictionary with plugin performance metrics
        """
        for plugin_name, metrics in performance_data.items():
            if plugin_name in self.config['plugins']:
                success_rate = metrics.get('success_rate', 0.5)
                profit_factor = metrics.get('profit_factor', 1.0)

                # Adjust weight based on performance
                current_weight = self.config['plugins'][plugin_name]['weight']

                if success_rate > 0.6 and profit_factor > 1.5:
                    # Increase weight for well-performing plugins
                    new_weight = min(current_weight + 0.05, 0.95)
                elif success_rate < 0.4 or profit_factor < 0.8:
                    # Decrease weight for poor performers
                    new_weight = max(current_weight - 0.05, 0.05)
                else:
                    new_weight = current_weight

                self.config['plugins'][plugin_name]['weight'] = new_weight
                logger.info(f"Updated {plugin_name} weight: {current_weight:.2f} -> {new_weight:.2f}")

        self.save_config()

    def get_stats(self) -> Dict:
        """Get orchestrator and plugin statistics"""
        return {
            'orchestrator': {
                'mode': self.config['mode'],
                'total_decisions': len(self.decision_history),
                'plugins_loaded': len(self.plugin_manager.plugins)
            },
            'plugins': self.plugin_manager.get_plugin_stats(),
            'ab_test': {
                'enabled': self.config['testing']['ab_test_mode'],
                'tests_run': len(self.ab_test_results)
            }
        }

    def emergency_rollback(self):
        """Emergency rollback to fibonacci-only mode"""
        logger.warning("EMERGENCY ROLLBACK INITIATED")

        # Disable all plugins except fibonacci
        for plugin_name in self.config['plugins']:
            if plugin_name != 'fibonacci':
                self.config['plugins'][plugin_name]['enabled'] = False
                self.config['plugins'][plugin_name]['weight'] = 0.0

        # Set fibonacci to full weight
        self.config['plugins']['fibonacci']['weight'] = 1.0
        self.config['mode'] = 'fibonacci_only'

        self.save_config()

        # Reload plugins
        self.plugin_manager.plugins.clear()
        self.load_plugins()

        logger.info("Rollback complete - running fibonacci-only mode")


if __name__ == "__main__":
    # Test orchestrator initialization
    orchestrator = AveragingOrchestrator()
    print(f"Orchestrator initialized with stats: {orchestrator.get_stats()}")