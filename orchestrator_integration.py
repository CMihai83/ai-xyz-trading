#!/usr/bin/env python3
"""
Integration hook for Averaging Orchestrator with autonomous_sync
This module can be imported by autonomous_sync to use orchestrated decisions
"""

import json
import logging
from typing import Dict, Optional
from datetime import datetime

from averaging_orchestrator import AveragingOrchestrator
from averaging_plugins.plugin_interface import MarketData, SignalAction

logger = logging.getLogger(__name__)


class OrchestratorIntegration:
    """
    Integration layer between orchestrator and autonomous_sync
    Provides backward-compatible interface for averaging decisions
    """

    def __init__(self, enabled: bool = False):
        """
        Initialize integration

        Args:
            enabled: Whether to use orchestrator or fall back to original logic
        """
        self.enabled = enabled
        self.orchestrator = None
        self.config_file = '/app/averaging_config.json'

        # Check if integration is enabled in config
        self.check_config()

        if self.enabled:
            try:
                self.orchestrator = AveragingOrchestrator()
                logger.info("Orchestrator integration initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize orchestrator: {e}")
                self.enabled = False

    def check_config(self):
        """Check configuration to see if integration is enabled"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
                self.enabled = config.get('integration', {}).get('enabled', False)
        except Exception as e:
            logger.warning(f"Could not load config, defaulting to disabled: {e}")
            self.enabled = False

    def should_average(self, symbol: str, position: Dict,
                      current_price: float) -> Dict:
        """
        Check if position should be averaged using orchestrator

        Args:
            symbol: Trading symbol
            position: Position data from position_state
            current_price: Current market price

        Returns:
            Dictionary with decision details:
            {
                'should_average': bool,
                'size': float or None,
                'reason': str,
                'confidence': float,
                'source': 'orchestrator' or 'original'
            }
        """
        if not self.enabled or not self.orchestrator:
            # Fall back to original logic (return None to use original)
            return {
                'should_average': None,
                'size': None,
                'reason': 'Orchestrator disabled, using original logic',
                'confidence': 0.0,
                'source': 'original'
            }

        try:
            # Prepare position data
            position_data = position.copy()
            position_data['symbol'] = symbol

            # Create market data
            market_data = MarketData(
                symbol=symbol,
                current_price=current_price,
                bid=current_price * 0.999,  # Approximate
                ask=current_price * 1.001,  # Approximate
                volume_24h=0,
                high_24h=0,
                low_24h=0,
                timestamp=datetime.now()
            )

            # Get decision from orchestrator
            signal = self.orchestrator.get_averaging_decision(
                position_data,
                market_data
            )

            # Convert to response format
            should_average = signal.action == SignalAction.AVERAGE

            return {
                'should_average': should_average,
                'size': signal.size if should_average else None,
                'reason': signal.reason,
                'confidence': signal.confidence,
                'source': 'orchestrator',
                'metadata': signal.metadata
            }

        except Exception as e:
            logger.error(f"Orchestrator decision failed: {e}")
            # Fall back to original logic
            return {
                'should_average': None,
                'size': None,
                'reason': f'Orchestrator error: {str(e)}',
                'confidence': 0.0,
                'source': 'original'
            }

    def update_performance(self, symbol: str, decision: Dict, result: Dict):
        """
        Update plugin performance based on trade results

        Args:
            symbol: Trading symbol
            decision: The decision that was made
            result: Trade execution result
        """
        if not self.enabled or not self.orchestrator:
            return

        try:
            # Update plugin performance stats
            if decision.get('source') == 'orchestrator':
                # Find which plugin made the decision
                # This would be tracked in the orchestrator
                pass  # Implementation for performance tracking

        except Exception as e:
            logger.error(f"Failed to update performance: {e}")

    def get_stats(self) -> Dict:
        """Get orchestrator statistics"""
        if self.orchestrator:
            return self.orchestrator.get_stats()
        return {'status': 'disabled'}


# Example integration in autonomous_sync.py:
"""
# Add this import at the top of autonomous_sync.py:
from orchestrator_integration import OrchestratorIntegration

# In the __init__ method:
self.orchestrator_integration = OrchestratorIntegration()

# In the averaging decision logic, replace or augment with:
if self.orchestrator_integration.enabled:
    decision = self.orchestrator_integration.should_average(
        symbol, position, current_price
    )

    if decision['should_average'] is not None:
        # Use orchestrator decision
        if decision['should_average']:
            print(f"Orchestrator says average: {decision['reason']}")
            # Execute averaging with decision['size']
        else:
            print(f"Orchestrator says hold: {decision['reason']}")
    else:
        # Fall back to original logic
        # ... original fibonacci logic here ...
"""

if __name__ == "__main__":
    # Test integration
    integration = OrchestratorIntegration()
    print(f"Integration enabled: {integration.enabled}")
    print(f"Stats: {integration.get_stats()}")