#!/usr/bin/env python3
"""
AI-XYZ Manual Position Field Fixer
Automatically adds missing initial_margin and safety_margin fields to any manual position
"""

import json
import logging
import time
from datetime import datetime
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('manual_position_fixer.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ManualPositionFixer:
    def __init__(self):
        self.state_file = 'position_state.json'
        self.safety_margin = 3.0  # Standard safety margin for all positions
        self.check_interval = 30  # Check every 30 seconds

    def fix_manual_positions(self):
        """Check and fix any manual positions missing required fields"""
        try:
            # Load position state
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            modified = False

            for symbol, position in state.get('active_positions', {}).items():
                # Check if it's a manual position without required fields
                if position.get('opened_at') == 'manual':
                    needs_fix = False

                    # Check for missing fields
                    if 'initial_margin' not in position:
                        # Calculate initial margin
                        amount = position.get('amount', 0)
                        entry_price = position.get('entry_price', 0)
                        leverage = position.get('leverage', 1)

                        if amount and entry_price and leverage:
                            position_value = amount * entry_price
                            initial_margin = position_value / leverage
                            position['initial_margin'] = initial_margin
                            needs_fix = True
                            logger.info(f"Added initial_margin to {symbol}: ${initial_margin:.4f}")

                    if 'safety_margin' not in position:
                        position['safety_margin'] = self.safety_margin
                        needs_fix = True
                        logger.info(f"Added safety_margin to {symbol}: ${self.safety_margin:.2f}")

                    if needs_fix:
                        modified = True
                        logger.info(f"✅ Fixed manual position {symbol}:")
                        logger.info(f"   Entry: ${position.get('entry_price', 0):.6f}")
                        logger.info(f"   Amount: {position.get('amount', 0)}")
                        logger.info(f"   Leverage: {position.get('leverage', 1)}x")
                        logger.info(f"   Initial Margin: ${position.get('initial_margin', 0):.4f}")
                        logger.info(f"   Safety Margin: ${position.get('safety_margin', 0):.2f}")

            # Save if modified
            if modified:
                with open(self.state_file, 'w') as f:
                    json.dump(state, f, indent=2)
                logger.info(f"💾 Saved updated position state with fixed manual positions")
                return True

            return False

        except FileNotFoundError:
            logger.warning(f"Position state file not found: {self.state_file}")
            return False
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error fixing positions: {e}")
            return False

    def run_continuous(self):
        """Continuously monitor and fix manual positions"""
        logger.info("🔧 AI-XYZ Manual Position Fixer started")
        logger.info(f"   Checking every {self.check_interval} seconds")
        logger.info(f"   Safety margin: ${self.safety_margin:.2f}")

        while True:
            try:
                # Check and fix positions
                fixed = self.fix_manual_positions()

                if not fixed:
                    # No fixes needed
                    logger.debug("No manual positions need fixing")

                # Wait before next check
                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                logger.info("Manual position fixer stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(self.check_interval)

    def fix_once(self):
        """Run a single fix check"""
        logger.info("Running single manual position check...")
        fixed = self.fix_manual_positions()
        if fixed:
            logger.info("✅ Manual positions fixed successfully")
        else:
            logger.info("No manual positions needed fixing")
        return fixed

if __name__ == "__main__":
    import sys

    fixer = ManualPositionFixer()

    if len(sys.argv) > 1 and sys.argv[1] == "--once":
        # Run once and exit
        fixer.fix_once()
    else:
        # Run continuously
        fixer.run_continuous()