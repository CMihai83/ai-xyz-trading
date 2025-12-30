#!/usr/bin/env python3
"""
Monitor positions through all state transitions
"""
import ccxt
import json
import time
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

class StateTransitionMonitor:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

        # Track state transitions
        self.state_history = {}
        self.averaging_executed = False
        self.surplus_dump_executed = False
        self.log_file = '/app/state_transitions.log'

    def log(self, message):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}"
        print(log_msg)
        with open(self.log_file, 'a') as f:
            f.write(log_msg + '\n')

    def monitor(self):
        while True:
            try:
                # Get positions and state
                positions = self.exchange.fetch_positions()

                with open('/app/position_state.json', 'r') as f:
                    state = json.load(f)

                # Check each position
                for pos in positions:
                    if pos.get('contracts', 0) > 0:
                        symbol = pos['symbol']
                        upnl_pct = pos.get('percentage', 0)

                        if symbol in state['active_positions']:
                            zone = state.get('position_zones', {}).get(symbol, 'UNKNOWN')
                            steps = state.get('averaging_steps', {}).get(symbol, 0)
                            surplus_stage = state.get('surplus_dump_stage', {}).get(symbol, 0)

                            # Track state changes
                            if symbol not in self.state_history:
                                self.state_history[symbol] = {
                                    'zone': zone,
                                    'steps': steps,
                                    'surplus_stage': surplus_stage
                                }
                                self.log(f"📌 Tracking {symbol}: Zone={zone}, UPNL={upnl_pct:.1f}%")

                            # Check for state transitions
                            prev = self.state_history[symbol]

                            # Zone change
                            if prev['zone'] != zone:
                                self.log(f"🔄 {symbol} ZONE CHANGE: {prev['zone']} → {zone}")
                                self.state_history[symbol]['zone'] = zone

                            # Averaging step executed
                            if steps > prev['steps']:
                                self.log(f"📊 {symbol} AVERAGING EXECUTED: Step {prev['steps']} → {steps}")
                                self.averaging_executed = True
                                self.state_history[symbol]['steps'] = steps

                            # Surplus dump executed
                            if surplus_stage > prev['surplus_stage']:
                                self.log(f"💰 {symbol} SURPLUS DUMP: Stage {prev['surplus_stage']} → {surplus_stage}")
                                self.surplus_dump_executed = True
                                self.state_history[symbol]['surplus_stage'] = surplus_stage

                            # Current status
                            if upnl_pct < -40:
                                self.log(f"⚠️ {symbol}: UPNL={upnl_pct:.1f}% approaching averaging threshold")
                            elif upnl_pct > 20 and zone == 'PROFIT_TAKING':
                                self.log(f"💚 {symbol}: UPNL={upnl_pct:.1f}% in profit taking zone")

                # Check if all states have been tested
                if self.averaging_executed and self.surplus_dump_executed:
                    self.log("✅ ALL STATES TESTED: Averaging and Surplus Dump executed")
                    self.log("System has successfully completed full state transition cycles")
                    break

                time.sleep(10)  # Check every 10 seconds

            except Exception as e:
                self.log(f"Error: {e}")
                time.sleep(30)

    def run(self):
        self.log("="*60)
        self.log("STATE TRANSITION MONITOR STARTED")
        self.log("Monitoring until averaging and surplus dump are executed")
        self.log("="*60)

        try:
            self.monitor()
        except KeyboardInterrupt:
            self.log("Monitor stopped by user")

if __name__ == "__main__":
    monitor = StateTransitionMonitor()
    monitor.run()