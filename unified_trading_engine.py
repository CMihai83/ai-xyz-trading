#!/usr/bin/env python3
"""
AI-XYZ Unified Trading Engine v3.0
Consolidates all trading functionality into a single, efficient service
Implements Sprint 2 architecture consolidation
"""

import os
import sys
import json
import time
import threading
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import ccxt
from dotenv import load_dotenv

# Import all core components
from autonomous_sync import AutonomousSync
from surplus_dump_manager import SurplusDumpManager
from momentum_guardian import EnhancedMomentumGuardian as MomentumGuardian
from kelly_criterion_sizer import KellyCriterionSizer
from smart_leverage_manager import SmartLeverageManager


class UnifiedTradingEngine:
    """
    Single consolidated trading engine for AI-XYZ
    Manages all trading operations through one interface
    """

    def __init__(self):
        # Load environment
        load_dotenv('/app/.env')

        # Initialize logging
        self._setup_logging()

        # Core components
        self.config_file = '/app/runtime_config.json'
        self.state_file = '/app/position_state.json'

        # Load configuration
        self.config = self._load_config()

        # Initialize exchange
        self.exchange = self._init_exchange()

        # Initialize managers (single instance of each)
        self.autonomous_sync = None
        self.surplus_manager = SurplusDumpManager()
        self.momentum_guardian = MomentumGuardian()
        self.kelly_sizer = KellyCriterionSizer()
        self.leverage_manager = SmartLeverageManager()

        # Thread management
        self.running = False
        self.threads = {}

        # Performance metrics
        self.metrics = {
            'start_time': None,
            'positions_opened': 0,
            'positions_closed': 0,
            'total_pnl': 0,
            'averaging_events': 0,
            'surplus_dumps': 0
        }

    def _setup_logging(self):
        """Configure unified logging"""
        log_dir = '/app/logs'
        os.makedirs(log_dir, exist_ok=True)

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(f'{log_dir}/unified_engine.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger('UnifiedEngine')

    def _load_config(self) -> Dict:
        """Load runtime configuration"""
        try:
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            self.logger.info("Configuration loaded successfully")
            return config
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {}

    def _init_exchange(self):
        """Initialize Bitget exchange connection"""
        try:
            exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_SECRET_KEY'),
                'password': os.getenv('BITGET_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'productType': 'USDT-FUTURES',
                    'positionMode': 'hedge'
                }
            })

            # Test connection
            exchange.fetch_balance()
            self.logger.info("Exchange connection established")
            return exchange

        except Exception as e:
            self.logger.error(f"Exchange initialization failed: {e}")
            return None

    def start(self):
        """Start the unified trading engine"""
        self.logger.info("="*60)
        self.logger.info("🚀 AI-XYZ UNIFIED TRADING ENGINE STARTING")
        self.logger.info("="*60)

        self.running = True
        self.metrics['start_time'] = datetime.now()

        # Start core services in separate threads
        self._start_service_threads()

        # Main loop
        self._run_main_loop()

    def _start_service_threads(self):
        """Start all service threads"""

        # 1. Position Sync Thread (replaces autonomous_sync)
        self.threads['position_sync'] = threading.Thread(
            target=self._position_sync_loop,
            daemon=True
        )
        self.threads['position_sync'].start()

        # 2. Market Scanner Thread
        self.threads['market_scanner'] = threading.Thread(
            target=self._market_scanner_loop,
            daemon=True
        )
        self.threads['market_scanner'].start()

        # 3. Risk Monitor Thread
        self.threads['risk_monitor'] = threading.Thread(
            target=self._risk_monitor_loop,
            daemon=True
        )
        self.threads['risk_monitor'].start()

        self.logger.info(f"Started {len(self.threads)} service threads")

    def _position_sync_loop(self):
        """Main position synchronization loop"""
        while self.running:
            try:
                # Sync with exchange
                self._sync_positions()

                # Check for averaging opportunities
                self._check_averaging()

                # Check for surplus dumps
                self._check_surplus_dumps()

                # Update metrics
                self._update_metrics()

                time.sleep(5)  # 5-second sync interval

            except Exception as e:
                self.logger.error(f"Position sync error: {e}")
                time.sleep(10)

    def _sync_positions(self):
        """Synchronize positions with exchange"""
        try:
            # Fetch positions from exchange
            positions = self.exchange.fetch_positions()

            # Load local state
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            # Update state with exchange data
            for position in positions:
                if position['contracts'] > 0:
                    symbol = position['symbol']

                    # Update or add position
                    if symbol not in state.get('positions', {}):
                        state['positions'] = state.get('positions', {})
                        state['positions'][symbol] = {
                            'entry_price': position['markPrice'],
                            'amount': position['contracts'],
                            'leverage': self.config['leverage'],
                            'timestamp': datetime.now().isoformat()
                        }
                        self.metrics['positions_opened'] += 1
                        self.logger.info(f"New position detected: {symbol}")

                    # Update UPNL
                    state['positions'][symbol]['unrealized_pnl'] = position['unrealizedPnl']
                    state['positions'][symbol]['current_price'] = position['markPrice']

            # Remove closed positions
            exchange_symbols = {p['symbol'] for p in positions if p['contracts'] > 0}
            closed = []

            for symbol in list(state.get('positions', {}).keys()):
                if symbol not in exchange_symbols:
                    closed.append(symbol)
                    self.metrics['positions_closed'] += 1

            for symbol in closed:
                if 'positions' in state:
                    state['positions'].pop(symbol, None)
                self.logger.info(f"Position closed: {symbol}")

            # Save updated state
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            self.logger.error(f"Sync error: {e}")

    def _check_averaging(self):
        """Check and execute averaging opportunities"""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            for symbol, position in state.get('positions', {}).items():
                upnl = position.get('unrealized_pnl', 0)
                entry = position.get('entry_price', 0)
                amount = position.get('amount', 0)
                leverage = position.get('leverage', 8)

                if entry > 0 and amount > 0:
                    # Calculate UPNL percentage (fixed calculation)
                    position_value = entry * amount
                    upnl_pct = (upnl / position_value) * 100

                    # Check averaging thresholds
                    thresholds = [-42, -68, -84, -94, -100]
                    steps_taken = state.get('averaging_steps', {}).get(symbol, 0)

                    if steps_taken < len(thresholds) and upnl_pct <= thresholds[steps_taken]:
                        # Check momentum permission
                        if self.momentum_guardian.check_averaging_permission(symbol):
                            self._execute_averaging(symbol, steps_taken)
                            self.metrics['averaging_events'] += 1
                        else:
                            self.logger.info(f"{symbol}: Averaging blocked by momentum guardian")

        except Exception as e:
            self.logger.error(f"Averaging check error: {e}")

    def _execute_averaging(self, symbol: str, step: int):
        """Execute averaging for a position"""
        try:
            # Get Fibonacci multiplier
            fibonacci = self.config['fibonacci_multipliers']
            multiplier = fibonacci[step] if step < len(fibonacci) else fibonacci[-1]

            # Calculate size using Kelly criterion
            base_size = self.kelly_sizer.calculate_position_size(
                win_rate=0.5,  # Would use historical data
                avg_win=1.5,
                avg_loss=1.0
            )

            size = base_size * multiplier

            self.logger.info(f"Executing averaging for {symbol}: Step {step+1}, Size: {size}")

            # Execute order (simplified for now)
            # In production, would place actual order through exchange

        except Exception as e:
            self.logger.error(f"Averaging execution error: {e}")

    def _check_surplus_dumps(self):
        """Check and execute surplus dumps"""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            for symbol, position in state.get('positions', {}).items():
                upnl = position.get('unrealized_pnl', 0)

                # Check if in surplus dump zone
                if symbol in state.get('averaging_steps', {}):
                    steps = state['averaging_steps'][symbol]
                    if steps > 0 and upnl > 0.10:  # Min profit threshold

                        # Track peak UPNL
                        peak = state.get('peak_upnl', {}).get(symbol, upnl)
                        if upnl > peak:
                            state['peak_upnl'] = state.get('peak_upnl', {})
                            state['peak_upnl'][symbol] = upnl
                            peak = upnl

                        # Check surplus dump triggers
                        should_dump, ratio = self.surplus_manager.check_surplus_dump_trigger(
                            symbol, upnl, peak
                        )

                        if should_dump:
                            self._execute_surplus_dump(symbol, ratio)
                            self.metrics['surplus_dumps'] += 1

            # Save state if updated
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            self.logger.error(f"Surplus dump check error: {e}")

    def _execute_surplus_dump(self, symbol: str, ratio: float):
        """Execute surplus dump"""
        try:
            self.logger.info(f"Executing surplus dump for {symbol}: {ratio*100}%")
            # In production, would execute actual trade

        except Exception as e:
            self.logger.error(f"Surplus dump execution error: {e}")

    def _market_scanner_loop(self):
        """Market scanning loop for opportunities"""
        while self.running:
            try:
                # Scan for opportunities
                symbols = self.config.get('opportunity_symbols', [])

                for symbol in symbols:
                    # Check if we should open position
                    # Simplified - would use actual market analysis
                    pass

                time.sleep(30)  # 30-second scan interval

            except Exception as e:
                self.logger.error(f"Market scanner error: {e}")
                time.sleep(60)

    def _risk_monitor_loop(self):
        """Risk monitoring loop"""
        while self.running:
            try:
                # Monitor portfolio risk
                self._check_portfolio_risk()

                # Adjust leverage if needed
                self._adjust_leverage()

                time.sleep(60)  # 1-minute risk check

            except Exception as e:
                self.logger.error(f"Risk monitor error: {e}")
                time.sleep(60)

    def _check_portfolio_risk(self):
        """Check overall portfolio risk"""
        try:
            balance = self.exchange.fetch_balance()
            total_balance = balance['USDT']['total']

            # Calculate portfolio metrics
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            total_exposure = 0
            total_upnl = 0

            for symbol, position in state.get('positions', {}).items():
                exposure = position['entry_price'] * position['amount']
                total_exposure += exposure
                total_upnl += position.get('unrealized_pnl', 0)

            # Log risk metrics
            if total_balance > 0:
                risk_ratio = total_exposure / total_balance
                self.logger.info(f"Portfolio Risk - Exposure: ${total_exposure:.2f}, "
                               f"UPNL: ${total_upnl:.2f}, Risk Ratio: {risk_ratio:.2f}")

        except Exception as e:
            self.logger.error(f"Risk check error: {e}")

    def _adjust_leverage(self):
        """Dynamically adjust leverage based on conditions"""
        try:
            # Get volatility estimate
            volatility = 0.2  # Would calculate from market data

            # Calculate safe leverage
            safe_leverage = self.leverage_manager.calculate_safe_leverage(
                symbol='PORTFOLIO',
                volatility=volatility,
                win_rate=0.5
            )

            # Update if significantly different
            current_leverage = self.config.get('leverage', 8)
            if abs(safe_leverage - current_leverage) >= 2:
                self.config['leverage'] = safe_leverage
                with open(self.config_file, 'w') as f:
                    json.dump(self.config, f, indent=2)
                self.logger.info(f"Leverage adjusted: {current_leverage}x → {safe_leverage}x")

        except Exception as e:
            self.logger.error(f"Leverage adjustment error: {e}")

    def _update_metrics(self):
        """Update performance metrics"""
        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            # Calculate total PnL
            total_pnl = sum(p.get('unrealized_pnl', 0)
                          for p in state.get('positions', {}).values())
            self.metrics['total_pnl'] = total_pnl

        except Exception as e:
            self.logger.error(f"Metrics update error: {e}")

    def _run_main_loop(self):
        """Main engine loop"""
        try:
            while self.running:
                # Display status every 30 seconds
                self._display_status()
                time.sleep(30)

        except KeyboardInterrupt:
            self.logger.info("Shutdown requested")
            self.stop()

    def _display_status(self):
        """Display current engine status"""
        runtime = datetime.now() - self.metrics['start_time'] if self.metrics['start_time'] else timedelta(0)

        self.logger.info("="*60)
        self.logger.info("📊 UNIFIED ENGINE STATUS")
        self.logger.info(f"Runtime: {runtime}")
        self.logger.info(f"Positions: Opened={self.metrics['positions_opened']}, "
                        f"Closed={self.metrics['positions_closed']}")
        self.logger.info(f"Total PnL: ${self.metrics['total_pnl']:.2f}")
        self.logger.info(f"Events: Averaging={self.metrics['averaging_events']}, "
                        f"Surplus={self.metrics['surplus_dumps']}")
        self.logger.info("="*60)

    def stop(self):
        """Stop the trading engine"""
        self.logger.info("Shutting down unified engine...")
        self.running = False

        # Wait for threads to complete
        for name, thread in self.threads.items():
            if thread.is_alive():
                thread.join(timeout=5)

        self.logger.info("Unified engine stopped")


def main():
    """Main entry point"""
    engine = UnifiedTradingEngine()

    try:
        engine.start()
    except Exception as e:
        logging.error(f"Engine error: {e}")
        engine.stop()


if __name__ == "__main__":
    main()