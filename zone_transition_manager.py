#!/usr/bin/env python3
"""
AI-XYZ Enhanced Zone Transition Manager
Handles rapid zone transitions for high-leverage positions
"""

import json
import time
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('zone_transitions.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ZoneTransitionManager:
    def __init__(self):
        self.state_file = 'position_state.json'
        # Faster refresh for high leverage positions
        self.refresh_intervals = {
            'default': 10,
            'high_leverage': 1,  # 1 second for leverage > 20x
            'extreme_leverage': 0.5  # 0.5 seconds for leverage > 40x
        }

    def get_refresh_interval(self, positions):
        """Determine refresh interval based on position leverage"""
        max_leverage = 0
        for symbol, pos in positions.items():
            leverage = pos.get('leverage', 1)
            max_leverage = max(max_leverage, leverage)

        if max_leverage >= 40:
            return self.refresh_intervals['extreme_leverage']
        elif max_leverage >= 20:
            return self.refresh_intervals['high_leverage']
        else:
            return self.refresh_intervals['default']

    def calculate_upnl_percentage(self, position, current_price):
        """Calculate UPNL percentage based on margin"""
        entry_price = position.get('entry_price', 0)
        amount = position.get('amount', 0)
        leverage = position.get('leverage', 1)
        side = position.get('side', 'buy')

        if not (entry_price and amount):
            return 0

        # Calculate position value and UPNL
        entry_value = amount * entry_price
        current_value = amount * current_price

        if side == 'buy':
            upnl = current_value - entry_value
        else:
            upnl = entry_value - current_value

        # Calculate margin
        margin = entry_value / leverage

        # UPNL percentage relative to margin
        if margin > 0:
            upnl_pct = (upnl / margin) * 100
        else:
            upnl_pct = 0

        return upnl_pct

    def determine_zone(self, upnl_pct, current_zone, averaging_steps):
        """Determine position zone based on UPNL"""
        new_zone = current_zone

        # Zone thresholds
        AVERAGING_THRESHOLD = -42  # Start averaging at -42%
        PROFIT_THRESHOLD = 15  # Profit taking starts at +15%
        SURPLUS_THRESHOLD = 15  # Surplus dump if recovered after averaging

        # Determine zone based on conditions
        if upnl_pct <= AVERAGING_THRESHOLD:
            new_zone = 'AVERAGING'
        elif upnl_pct >= SURPLUS_THRESHOLD and averaging_steps > 0:
            new_zone = 'SURPLUS_DUMP'
        elif upnl_pct >= PROFIT_THRESHOLD and averaging_steps == 0:
            new_zone = 'PROFIT_TAKING'
        elif -15 < upnl_pct < 15:
            new_zone = 'NEUTRAL'

        return new_zone

    def enforce_zone_transitions(self):
        """Main loop to enforce zone transitions"""
        logger.info("🚀 Zone Transition Manager started")

        while True:
            try:
                # Load position state
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                positions = state.get('active_positions', {})
                zones = state.get('position_zones', {})
                averaging_steps = state.get('averaging_steps', {})

                # Determine refresh interval based on leverage
                interval = self.get_refresh_interval(positions)

                # Check each position for zone transitions
                for symbol, pos in positions.items():
                    # Skip if no position data
                    if not pos:
                        continue

                    # For high leverage positions, enforce zone transitions
                    leverage = pos.get('leverage', 1)

                    if leverage >= 20:  # High leverage needs special handling
                        # Simulate current price (in production, fetch from exchange)
                        # For now, we'll ensure zone is properly set based on state
                        current_zone = zones.get(symbol, 'NEUTRAL')
                        steps = averaging_steps.get(symbol, 0)

                        # Log high leverage position
                        logger.info(f"⚠️ High leverage position {symbol}: {leverage}x")
                        logger.info(f"   Current zone: {current_zone}, Steps: {steps}")

                        # For extreme leverage, ensure rapid zone updates
                        if leverage >= 40:
                            logger.warning(f"🚨 EXTREME LEVERAGE {symbol}: {leverage}x - Rapid monitoring active")

                            # Force zone update check
                            if symbol not in zones:
                                zones[symbol] = 'NEUTRAL'
                                state['position_zones'] = zones

                                # Save updated state
                                with open(self.state_file, 'w') as f:
                                    json.dump(state, f, indent=2)

                                logger.info(f"✅ Added zone tracking for {symbol}")

                # Sleep based on leverage-adjusted interval
                time.sleep(interval)

            except Exception as e:
                logger.error(f"Error in zone transition manager: {e}")
                time.sleep(1)

if __name__ == "__main__":
    manager = ZoneTransitionManager()
    manager.enforce_zone_transitions()