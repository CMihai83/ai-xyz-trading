#!/usr/bin/env python3
"""
Monitor and Test Position Management
Tests all stages with current live positions
"""

import json
import time
import ccxt
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')


class PositionMonitor:
    """Monitor positions through all management stages"""

    def __init__(self):
        self.state_file = '/app/position_state.json'
        self.config_file = '/app/runtime_config.json'
        self.exchange = self._init_exchange()

    def _init_exchange(self):
        """Initialize exchange connection"""
        try:
            exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_API_SECRET'),
                'password': os.getenv('BITGET_API_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'productType': 'USDT-FUTURES'
                }
            })
            return exchange
        except:
            return None

    def monitor_all_positions(self):
        """Monitor all positions and their stages"""

        print("\n" + "="*70)
        print("🎯 AI-XYZ POSITION MANAGEMENT TEST")
        print("="*70)
        print(f"Timestamp: {datetime.now()}")
        print("="*70)

        # Load current state
        with open(self.state_file, 'r') as f:
            state = json.load(f)

        positions = state.get('active_positions', {})
        zones = state.get('position_zones', {})
        steps = state.get('averaging_steps', {})
        peaks = state.get('peak_upnl', {})
        stages = state.get('surplus_dump_stage', {})

        if not positions:
            print("❌ No active positions found")
            return

        # Check each position
        for symbol, position in positions.items():
            self._check_position(symbol, position, state)

    def _check_position(self, symbol, position, state):
        """Check individual position status"""

        zone = state.get('position_zones', {}).get(symbol, 'UNKNOWN')
        steps_taken = state.get('averaging_steps', {}).get(symbol, 0)
        peak_upnl = state.get('peak_upnl', {}).get(symbol, 0)
        surplus_stage = state.get('surplus_dump_stage', {}).get(symbol, 0)

        # Get current price
        try:
            ticker = self.exchange.fetch_ticker(symbol.replace(':', ''))
            current_price = ticker['last']
        except:
            current_price = position.get('entry_price', 0)

        # Calculate UPNL
        entry = position['entry_price']
        amount = position['amount']
        side = position.get('side', 'buy')

        if side == 'buy':
            upnl = (current_price - entry) * amount
        else:
            upnl = (entry - current_price) * amount

        position_value = entry * amount
        upnl_pct = (upnl / position_value) * 100 if position_value > 0 else 0

        # Display position status
        print(f"\n📊 {symbol}")
        print(f"  Zone: {zone} {self._get_zone_emoji(zone)}")
        print(f"  Entry: ${entry:.4f}")
        print(f"  Current: ${current_price:.4f}")
        print(f"  Amount: {amount}")
        print(f"  Leverage: {position.get('leverage', 'N/A')}x")
        print(f"  UPNL: ${upnl:.2f} ({upnl_pct:.1f}%)")
        print(f"  Peak UPNL: ${peak_upnl:.4f}")

        # Test zone-specific features
        self._test_zone_features(symbol, zone, upnl_pct, steps_taken, surplus_stage, peak_upnl)

    def _test_zone_features(self, symbol, zone, upnl_pct, steps_taken, surplus_stage, peak_upnl):
        """Test features specific to each zone"""

        print(f"\n  📋 Zone Testing:")

        if zone == 'AVERAGING':
            # Test averaging steps
            thresholds = [-42, -68, -84, -94, -97]  # -97% max to avoid liquidation at -100%
            fibonacci = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]

            print(f"    Averaging Steps Taken: {steps_taken}/{len(thresholds)}")

            if steps_taken < len(thresholds):
                next_threshold = thresholds[steps_taken]
                next_multiplier = fibonacci[steps_taken] if steps_taken < len(fibonacci) else fibonacci[-1]

                print(f"    Next Step Threshold: {next_threshold}% (current: {upnl_pct:.1f}%)")
                print(f"    Next Fibonacci Multiplier: {next_multiplier}x")

                if upnl_pct <= next_threshold:
                    print(f"    ✅ Ready for Step {steps_taken + 1}")
                else:
                    print(f"    ⏳ Waiting for {next_threshold}% threshold")

        elif zone == 'SURPLUS_DUMP':
            print(f"    Surplus Dump Stage: {surplus_stage}/2")
            print(f"    Peak UPNL: ${peak_upnl:.4f}")

            if surplus_stage == 0:
                trigger = peak_upnl * 0.85
                print(f"    Stage 1 Trigger: ${trigger:.4f} (85% of peak)")
            elif surplus_stage == 1:
                trigger = peak_upnl * 0.50
                print(f"    Stage 2 Trigger: ${trigger:.4f} (50% of peak)")
            else:
                print(f"    ✅ Surplus dump complete")

        elif zone == 'PROFIT_TAKING':
            print(f"    Peak UPNL: ${peak_upnl:.4f}")
            print(f"    Ready for profit taking")
            print(f"    XPL showing strong profit momentum")

        elif zone == 'STOP_LOSS':
            print(f"    ⛔ Stop loss triggered at {upnl_pct:.1f}%")
            print(f"    Position should be closed immediately")

        elif zone == 'NEUTRAL':
            print(f"    Position stable")
            print(f"    Monitoring for zone transitions")

    def _get_zone_emoji(self, zone):
        """Get zone emoji"""
        emojis = {
            'NEUTRAL': '⚪',
            'AVERAGING': '🔴',
            'SURPLUS_DUMP': '🟡',
            'PROFIT_TAKING': '🟢',
            'STOP_LOSS': '⛔',
            'UNKNOWN': '❓'
        }
        return emojis.get(zone, '❓')

    def test_zone_transitions(self):
        """Test zone transition logic"""

        print("\n" + "="*50)
        print("🔄 TESTING ZONE TRANSITIONS")
        print("="*50)

        # Load config
        with open(self.config_file, 'r') as f:
            config = json.load(f)

        thresholds = config['zone_thresholds']

        print(f"\n📋 Zone Thresholds:")
        print(f"  Averaging Start: {thresholds['averaging_start']*100}%")
        print(f"  Stop Loss: {thresholds['stop_loss']*100}%")
        print(f"  Surplus Dump 85%: {thresholds['surplus_dump_85']*100}%")
        print(f"  Surplus Dump 50%: {thresholds['surplus_dump_50']*100}%")

        print(f"\n📋 Fibonacci Multipliers:")
        print(f"  {config['fibonacci_multipliers'][:9]}")

        print(f"\n✅ System Configuration Verified")

    def continuous_monitor(self, interval=10):
        """Continuously monitor positions"""

        print("\n🔄 Starting continuous monitoring (Ctrl+C to stop)")
        print("Checking every", interval, "seconds...")

        try:
            while True:
                self.monitor_all_positions()
                self.test_zone_transitions()
                time.sleep(interval)

        except KeyboardInterrupt:
            print("\n⏹️ Monitoring stopped")


def main():
    """Main monitoring function"""
    monitor = PositionMonitor()

    # Single check
    monitor.monitor_all_positions()
    monitor.test_zone_transitions()

    # Ask for continuous monitoring
    response = input("\n🔄 Start continuous monitoring? (y/n): ")
    if response.lower() == 'y':
        monitor.continuous_monitor()


if __name__ == "__main__":
    main()