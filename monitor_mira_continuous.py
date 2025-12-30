#!/usr/bin/env python3
"""
Continuous MIRA position monitor - tracks through averaging and surplus dump
"""
import json
import ccxt
import os
import time
from datetime import datetime
from dotenv import load_dotenv
from orchestrator_integration import OrchestratorIntegration

load_dotenv('/app/.env')

class MiraMonitor:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        self.symbol = 'MIRA/USDT:USDT'
        self.orchestrator = OrchestratorIntegration()
        self.events_log = []

    def monitor_position(self):
        """Main monitoring loop"""
        # Load state
        with open('/app/position_state.json', 'r') as f:
            state = json.load(f)

        if self.symbol not in state['active_positions']:
            print(f"❌ {self.symbol} not found in positions")
            return None

        pos = state['active_positions'][self.symbol]
        zone = state['position_zones'].get(self.symbol, 'NEUTRAL')
        steps = state['averaging_steps'].get(self.symbol, 0)
        peak_upnl = state['peak_upnl'].get(self.symbol, 0)
        surplus_stage = state['surplus_dump_stage'].get(self.symbol, 0)

        # Get current market data
        ticker = self.exchange.fetch_ticker(self.symbol)
        current = ticker['last']

        # Calculate UPNL
        entry = pos['entry_price']
        amount = pos['amount']
        leverage = pos['leverage']
        side = pos['side']

        position_value = amount * entry
        margin = position_value / leverage

        if side in ['short', 'sell']:
            upnl = (entry - current) * amount
        else:
            upnl = (current - entry) * amount

        upnl_pct = (upnl / margin * 100) if margin > 0 else 0

        # Clear screen for clean display
        print('\033[2J\033[H')

        # Display header
        print('='*80)
        print('🎯 MIRA/USDT:USDT CONTINUOUS MONITOR')
        print('='*80)
        print(f'Time: {datetime.now().strftime("%H:%M:%S")}')

        # Position details
        print(f'\n📊 POSITION:')
        print(f'  Side: {side.upper()} | Leverage: {leverage}x')
        print(f'  Entry: ${entry:.4f} | Current: ${current:.4f}')
        print(f'  Price Move: {((current - entry) / entry * 100):.2f}%')
        print(f'  UPNL: ${upnl:.2f} ({upnl_pct:.1f}% of margin)')

        # Zone and status
        print(f'\n🎯 ZONE: {zone}')

        # Zone-specific monitoring
        if zone == 'AVERAGING':
            print(f'  📉 Averaging Steps: {steps}/5')
            thresholds = [-42, -68, -84, -94, -97]
            if steps < len(thresholds):
                next_threshold = thresholds[steps]
                if upnl_pct <= next_threshold:
                    print(f'  ✅ READY FOR AVERAGING STEP {steps+1}!')
                    self.log_event(f'AVERAGING THRESHOLD {next_threshold}% REACHED')
                else:
                    print(f'  ⏳ Next threshold: {next_threshold}% (need {next_threshold - upnl_pct:.1f}% more)')

        elif zone == 'SURPLUS_DUMP':
            print(f'  📈 Surplus Dump Stage: {surplus_stage}/2')
            print(f'  Peak UPNL: ${peak_upnl:.2f}')
            if surplus_stage == 0:
                trigger = peak_upnl * 0.85
                print(f'  Stage 1 trigger: ${trigger:.2f} (85% of peak)')
            elif surplus_stage == 1:
                trigger = peak_upnl * 0.50
                print(f'  Stage 2 trigger: ${trigger:.2f} (50% of peak)')
            else:
                print(f'  ✅ Surplus dump complete!')
                self.log_event('SURPLUS DUMP COMPLETED')

        elif zone == 'NEUTRAL':
            if upnl_pct < -15:
                print(f'  ⚠️ Approaching averaging zone (starts at -15%)')
            elif upnl_pct > 15:
                print(f'  💰 Profitable - may enter profit taking zone')

        # Orchestrator decision
        if self.orchestrator.enabled:
            decision = self.orchestrator.should_average(self.symbol, pos, current)
            print(f'\n🤖 ORCHESTRATOR:')
            print(f'  Decision: {"AVERAGE" if decision["should_average"] else "HOLD"}')
            print(f'  Confidence: {decision.get("confidence", 0):.1%}')
            print(f'  Reason: {decision["reason"]}')

        # Risk metrics
        if side in ['short', 'sell']:
            liquidation_price = entry * (1 + 1/leverage)
        else:
            liquidation_price = entry * (1 - 1/leverage)
        distance_to_liq = abs((current - liquidation_price) / liquidation_price * 100)

        print(f'\n⚠️ RISK:')
        print(f'  Liquidation: ${liquidation_price:.4f} ({distance_to_liq:.1f}% away)')

        if upnl_pct < -85:
            print(f'  🚨 CRITICAL: Near liquidation zone!')
        elif upnl_pct < -70:
            print(f'  ⚠️ WARNING: High risk territory')

        # Events log
        if self.events_log:
            print(f'\n📜 RECENT EVENTS:')
            for event in self.events_log[-5:]:
                print(f'  {event}')

        print('\n' + '='*80)
        print('Monitoring... (Updates every 5 seconds, Ctrl+C to stop)')

        return {
            'zone': zone,
            'steps': steps,
            'upnl_pct': upnl_pct,
            'surplus_stage': surplus_stage
        }

    def log_event(self, message):
        """Log important events"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events_log.append(f"[{timestamp}] {message}")

    def run(self):
        """Run continuous monitoring"""
        print("Starting MIRA position monitor...")
        print("Will track through averaging and surplus dump stages")
        print("Press Ctrl+C to stop\n")

        last_zone = None
        last_steps = 0
        last_surplus_stage = 0

        try:
            while True:
                result = self.monitor_position()

                if result:
                    # Detect zone changes
                    if result['zone'] != last_zone:
                        self.log_event(f"ZONE CHANGE: {last_zone} → {result['zone']}")
                        last_zone = result['zone']

                    # Detect averaging steps
                    if result['steps'] > last_steps:
                        self.log_event(f"AVERAGING STEP {result['steps']} EXECUTED")
                        last_steps = result['steps']

                    # Detect surplus dump stages
                    if result['surplus_stage'] > last_surplus_stage:
                        self.log_event(f"SURPLUS DUMP STAGE {result['surplus_stage']} EXECUTED")
                        last_surplus_stage = result['surplus_stage']

                    # Check if we've completed the cycle
                    if result['zone'] == 'NEUTRAL' and result['steps'] > 0 and result['surplus_stage'] >= 2:
                        print("\n✅ COMPLETE CYCLE: Position has gone through averaging and surplus dump!")
                        self.log_event("FULL CYCLE COMPLETED")

                time.sleep(5)

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped by user")
            print(f"Total events logged: {len(self.events_log)}")

if __name__ == "__main__":
    monitor = MiraMonitor()
    monitor.run()