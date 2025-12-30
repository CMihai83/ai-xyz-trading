#!/usr/bin/env python3
"""
Signal Execution Bridge for AI-XYZ
Connects Market Scanner → Opportunity Discovery → Position Opening
This is the MISSING CRITICAL COMPONENT that prevents autonomous position opening
"""
import ccxt
import json
import os
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any
from dotenv import load_dotenv

load_dotenv('/app/.env')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/signal_execution_bridge.log'),
        logging.StreamHandler()
    ]
)

class SignalExecutionBridge:
    def __init__(self):
        self.api_key = os.getenv('BITGET_API_KEY')
        self.api_secret = os.getenv('BITGET_API_SECRET')
        self.api_passphrase = os.getenv('BITGET_API_PASSPHRASE', '')

        # Initialize exchange
        self.exchange = ccxt.bitget({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'password': self.api_passphrase,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'defaultMarginMode': 'isolated'
            }
        })

        # Load configuration
        with open('/app/runtime_config.json', 'r') as f:
            self.config = json.load(f)

        # Track state
        self.last_opportunity_time = datetime.now()
        self.opportunity_check_interval = 60  # seconds
        self.no_opportunity_duration = 0
        self.relaxation_level = 0  # 0 = strict, increases when no opportunities

        # Signal queue
        self.pending_signals = []

        # Position limits
        self.max_positions = self.config.get('max_positions', 1)
        self.min_position_size = self.config.get('min_position_size', 40.0)

        logging.info("Signal Execution Bridge initialized")
        logging.info(f"Max positions: {self.max_positions}")
        logging.info(f"Min position size: ${self.min_position_size}")

    def check_active_positions(self) -> int:
        """Check how many positions are currently active"""
        try:
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)
            return len(state.get('active_positions', {}))
        except:
            return 0

    def scan_for_opportunities(self) -> List[Dict]:
        """Scan market for trading opportunities"""
        opportunities = []

        try:
            # Get threshold configuration - with relaxation
            base_thresholds = self.config.get('opportunity_thresholds', {})

            # Apply relaxation based on how long we've been without opportunities
            min_confidence = base_thresholds.get('min_confidence', 0.3) * (1 - self.relaxation_level * 0.1)
            min_volatility = base_thresholds.get('min_volatility', 2.0) * (1 - self.relaxation_level * 0.15)
            min_volume = base_thresholds.get('min_volume', 500000) * (1 - self.relaxation_level * 0.2)

            logging.info(f"Scanning with relaxation level {self.relaxation_level}")
            logging.info(f"Thresholds - Confidence: {min_confidence:.2f}, Volatility: {min_volatility:.2f}%, Volume: ${min_volume:,.0f}")

            # Get top volatile coins
            tickers = self.exchange.fetch_tickers()

            # Filter and score opportunities
            for symbol, ticker in tickers.items():
                if not symbol.endswith('/USDT:USDT'):
                    continue

                # Skip if no volume
                if not ticker.get('quoteVolume', 0):
                    continue

                # Calculate metrics
                volume_24h = ticker.get('quoteVolume', 0)
                change_24h = ticker.get('percentage', 0)
                volatility = abs(change_24h)

                # Apply thresholds
                if volume_24h < min_volume:
                    continue

                if volatility < min_volatility:
                    continue

                # Calculate opportunity score
                volume_score = min(volume_24h / 1000000, 1.0) * 0.3
                volatility_score = min(volatility / 10, 1.0) * 0.4
                trend_score = 0.5 if change_24h > 0 else 0.3

                total_score = volume_score + volatility_score + trend_score * 0.3

                if total_score >= min_confidence:
                    opportunities.append({
                        'symbol': symbol,
                        'score': total_score,
                        'volatility': volatility,
                        'volume': volume_24h,
                        'change_24h': change_24h,
                        'price': ticker.get('last', 0),
                        'timestamp': datetime.now().isoformat()
                    })

            # Sort by score
            opportunities.sort(key=lambda x: x['score'], reverse=True)

            # Log findings
            if opportunities:
                logging.info(f"Found {len(opportunities)} opportunities")
                for opp in opportunities[:3]:  # Log top 3
                    logging.info(f"  {opp['symbol']}: Score={opp['score']:.2f}, Vol={opp['volatility']:.1f}%")
            else:
                logging.warning("No opportunities found - will relax criteria")

            return opportunities[:5]  # Return top 5

        except Exception as e:
            logging.error(f"Error scanning for opportunities: {e}")
            return []

    def adjust_opportunity_criteria(self):
        """Auto-adjust criteria if no opportunities found"""
        time_since_last = datetime.now() - self.last_opportunity_time
        minutes_without = time_since_last.total_seconds() / 60

        if minutes_without > 5 and self.relaxation_level < 3:
            self.relaxation_level += 1
            logging.warning(f"No opportunities for {minutes_without:.1f} minutes - relaxing criteria to level {self.relaxation_level}")
        elif minutes_without > 15 and self.relaxation_level < 5:
            self.relaxation_level = 5
            logging.warning(f"No opportunities for {minutes_without:.1f} minutes - maximum relaxation applied")
        elif minutes_without > 60:
            logging.error("No opportunities for over 1 hour - forcing position opening")
            self.force_open_position()

    def force_open_position(self):
        """Force open a position on most liquid coin when no opportunities for too long"""
        try:
            logging.warning("Forcing position opening due to extended inactivity")

            # Get most liquid coins
            tickers = self.exchange.fetch_tickers()

            liquid_coins = []
            for symbol, ticker in tickers.items():
                if not symbol.endswith('/USDT:USDT'):
                    continue

                volume = ticker.get('quoteVolume', 0)
                if volume > 100000:  # Minimum liquidity
                    liquid_coins.append({
                        'symbol': symbol,
                        'volume': volume,
                        'price': ticker.get('last', 0)
                    })

            if liquid_coins:
                # Sort by volume and pick top one
                liquid_coins.sort(key=lambda x: x['volume'], reverse=True)
                target = liquid_coins[0]

                signal = {
                    'symbol': target['symbol'],
                    'action': 'buy',  # Default to long
                    'score': 0.5,  # Moderate confidence
                    'price': target['price'],
                    'forced': True,
                    'reason': 'No opportunities for extended period'
                }

                self.execute_signal(signal)

        except Exception as e:
            logging.error(f"Error forcing position: {e}")

    def execute_signal(self, signal: Dict) -> bool:
        """Execute a trading signal by opening a position"""
        try:
            symbol = signal['symbol']
            action = signal.get('action', 'buy')
            score = signal.get('score', 0.5)
            current_price = signal.get('price', 0)

            logging.info(f"Executing signal for {symbol}")
            logging.info(f"  Action: {action}, Score: {score:.2f}, Price: {current_price}")

            # Check position limit
            active_positions = self.check_active_positions()
            if active_positions >= self.max_positions:
                logging.warning(f"Position limit reached ({active_positions}/{self.max_positions})")
                return False

            # Fixed position size: min_position_size after leverage
            # min_position_size is $40, so we use it directly as target notional after leverage
            target_notional_after_leverage = self.min_position_size  # $40 after leverage

            # Determine leverage based on score
            if score > 0.8:
                leverage = 10
            elif score > 0.6:
                leverage = 8
            else:
                leverage = 5

            # Calculate margin required (position value before leverage)
            margin_required = target_notional_after_leverage / leverage

            # The actual position value (notional) after leverage
            actual_position_value = target_notional_after_leverage
            amount = actual_position_value / current_price

            logging.info(f"  Margin required: ${margin_required:.2f}")
            logging.info(f"  Position size: ${margin_required:.2f} x {leverage} = ${actual_position_value:.2f}")
            logging.info(f"  Amount: {amount:.8f} {symbol.split('/')[0]}")

            # Set leverage
            try:
                self.exchange.set_leverage(leverage, symbol)
            except:
                pass  # Some symbols might not support leverage change

            # Execute order
            side = 'buy' if action == 'buy' else 'sell'
            order = self.exchange.create_order(
                symbol=symbol,
                type='market',
                side=side,
                amount=amount,
                params={'marginMode': 'isolated'}
            )

            logging.info(f"✅ Position opened: {order['id']}")

            # Update position state
            self.update_position_state(symbol, order, leverage)

            # Reset relaxation after successful opening
            self.relaxation_level = 0
            self.last_opportunity_time = datetime.now()

            return True

        except Exception as e:
            logging.error(f"Error executing signal: {e}")
            return False

    def update_position_state(self, symbol: str, order: Dict, leverage: int):
        """Update position_state.json with new position"""
        try:
            # Load current state
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)

            # Add new position
            position = {
                'symbol': symbol,
                'side': order.get('side', 'buy').upper() if order.get('side') else 'BUY',
                'entry_price': order.get('average', order.get('price', 0)),
                'amount': order.get('amount', 0),
                'leverage': leverage,
                'margin': order.get('cost', 0) / leverage if leverage > 0 else 0,
                'upnl': 0,
                'peak_upnl': 0,
                'created_at': datetime.now().isoformat(),
                'order_id': order.get('id', '')
            }

            state['active_positions'][symbol] = position
            state['position_zones'][symbol] = 'NEUTRAL'
            state['averaging_steps'][symbol] = 0

            # Save state
            with open('/app/position_state.json', 'w') as f:
                json.dump(state, f, indent=2)

            logging.info(f"Position state updated for {symbol}")

        except Exception as e:
            logging.error(f"Error updating position state: {e}")

    def process_scanner_output(self):
        """Check if market scanner has produced any signals"""
        try:
            # Check for scanner output files
            scanner_files = [
                '/app/scanner_signals.json',
                '/app/opportunities.json',
                '/tmp/market_opportunities.json'
            ]

            for file_path in scanner_files:
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        data = json.load(f)

                    if data and isinstance(data, list):
                        logging.info(f"Found {len(data)} signals in {file_path}")

                        for signal in data[:1]:  # Process first signal only
                            if self.execute_signal(signal):
                                # Remove processed signal
                                os.remove(file_path)
                                break

        except Exception as e:
            logging.error(f"Error processing scanner output: {e}")

    def run(self):
        """Main execution loop"""
        logging.info("=" * 60)
        logging.info("SIGNAL EXECUTION BRIDGE STARTED")
        logging.info("=" * 60)

        while True:
            try:
                # Check active positions
                active_positions = self.check_active_positions()
                logging.info(f"Active positions: {active_positions}/{self.max_positions}")

                if active_positions < self.max_positions:
                    # Look for scanner signals first
                    self.process_scanner_output()

                    # If still room, scan for opportunities
                    if self.check_active_positions() < self.max_positions:
                        opportunities = self.scan_for_opportunities()

                        if opportunities:
                            # Execute best opportunity
                            best = opportunities[0]
                            signal = {
                                'symbol': best['symbol'],
                                'action': 'buy' if best['change_24h'] > 0 else 'sell',
                                'score': best['score'],
                                'price': best['price']
                            }
                            self.execute_signal(signal)
                        else:
                            # No opportunities - adjust criteria
                            self.adjust_opportunity_criteria()
                else:
                    logging.info("Position limit reached - waiting for closures")

                # Sleep before next cycle
                time.sleep(self.opportunity_check_interval)

            except KeyboardInterrupt:
                logging.info("Signal Execution Bridge stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                time.sleep(10)

if __name__ == "__main__":
    bridge = SignalExecutionBridge()
    bridge.run()