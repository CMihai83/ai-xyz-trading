#!/usr/bin/env python3
"""
Continuous monitor that tracks positions through all state transitions.
Runs until at least one position completes averaging and surplus dump cycles.
"""

import json
import time
import os
from datetime import datetime
from typing import Dict, Set, List

class StateTransitionMonitor:
    def __init__(self):
        self.state_file = '/app/position_state.json'
        self.log_file = '/app/state_transitions.log'

        # Track which states each position has visited
        self.position_history = {}

        # Track averaging and surplus dump completions
        self.averaging_executed = set()  # Positions that have done averaging
        self.surplus_dump_executed = set()  # Positions that have done surplus dumps

        # Target states we want to see
        self.required_transitions = {
            'averaging_steps': False,  # Position must execute averaging
            'surplus_dump': False,  # Position must execute surplus dump
        }

        # Last known state for change detection
        self.last_state = {}

    def log(self, message: str):
        """Log with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"
        print(log_entry)
        with open(self.log_file, 'a') as f:
            f.write(log_entry + '\n')

    def load_state(self) -> Dict:
        """Load current position state"""
        try:
            with open(self.state_file, 'r') as f:
                return json.load(f)
        except:
            return {}

    def detect_changes(self, current_state: Dict) -> List[str]:
        """Detect what changed since last check"""
        changes = []

        if not self.last_state:
            self.last_state = current_state
            return ["Initial state loaded"]

        # Check each position for changes
        for symbol, position in current_state.get('active_positions', {}).items():
            last_pos = self.last_state.get('active_positions', {}).get(symbol, {})

            # Track position in history
            if symbol not in self.position_history:
                self.position_history[symbol] = {
                    'zones_visited': set(),
                    'averaging_steps': [],
                    'surplus_stages': [],
                    'max_averaging_step': 0,
                    'max_surplus_stage': 0
                }

            # Check zone change
            current_zone = current_state.get('position_zones', {}).get(symbol, 'NEUTRAL')
            last_zone = self.last_state.get('position_zones', {}).get(symbol, 'NEUTRAL')

            if current_zone != last_zone:
                changes.append(f"🔄 {symbol}: Zone changed {last_zone} → {current_zone}")
                self.position_history[symbol]['zones_visited'].add(current_zone)

            # Check averaging steps
            current_steps = current_state.get('averaging_steps', {}).get(symbol, 0)
            last_steps = self.last_state.get('averaging_steps', {}).get(symbol, 0)

            if current_steps > last_steps:
                changes.append(f"📊 {symbol}: Averaging step executed! Step {last_steps} → {current_steps}")
                self.averaging_executed.add(symbol)
                self.position_history[symbol]['averaging_steps'].append(current_steps)
                self.position_history[symbol]['max_averaging_step'] = max(
                    self.position_history[symbol]['max_averaging_step'],
                    current_steps
                )

            # Check surplus dump stage
            current_surplus = current_state.get('surplus_dump_stage', {}).get(symbol, 0)
            last_surplus = self.last_state.get('surplus_dump_stage', {}).get(symbol, 0)

            if current_surplus > last_surplus:
                changes.append(f"💰 {symbol}: Surplus dump executed! Stage {last_surplus} → {current_surplus}")
                self.surplus_dump_executed.add(symbol)
                self.position_history[symbol]['surplus_stages'].append(current_surplus)
                self.position_history[symbol]['max_surplus_stage'] = max(
                    self.position_history[symbol]['max_surplus_stage'],
                    current_surplus
                )

            # Check UPNL changes
            current_upnl = position.get('unrealized_pnl', 0)
            last_upnl = last_pos.get('unrealized_pnl', 0) if last_pos else 0

            if abs(current_upnl - last_upnl) > 0.01:  # Significant change
                changes.append(f"💵 {symbol}: UPNL ${last_upnl:.2f} → ${current_upnl:.2f}")

        # Check for new positions
        current_symbols = set(current_state.get('active_positions', {}).keys())
        last_symbols = set(self.last_state.get('active_positions', {}).keys())

        new_positions = current_symbols - last_symbols
        closed_positions = last_symbols - current_symbols

        for symbol in new_positions:
            changes.append(f"✅ New position opened: {symbol}")

        for symbol in closed_positions:
            changes.append(f"❌ Position closed: {symbol}")

        self.last_state = current_state
        return changes

    def check_completion(self) -> bool:
        """Check if we've seen all required state transitions"""
        # Need at least one position to have done averaging
        if self.averaging_executed:
            self.required_transitions['averaging_steps'] = True

        # Need at least one position to have done surplus dump
        if self.surplus_dump_executed:
            self.required_transitions['surplus_dump'] = True

        # Check if all required transitions have been observed
        all_complete = all(self.required_transitions.values())

        if all_complete:
            self.log("🎯 SUCCESS: All required state transitions observed!")
            self.log(f"Averaging executed by: {', '.join(self.averaging_executed)}")
            self.log(f"Surplus dumps executed by: {', '.join(self.surplus_dump_executed)}")
            return True

        return False

    def print_summary(self):
        """Print current monitoring summary"""
        self.log("\n" + "="*60)
        self.log("📊 MONITORING SUMMARY")
        self.log("="*60)

        # Current positions
        state = self.load_state()
        active_positions = state.get('active_positions', {})

        self.log(f"\n🔍 Active Positions: {len(active_positions)}")
        for symbol, pos in active_positions.items():
            zone = state.get('position_zones', {}).get(symbol, 'NEUTRAL')
            avg_steps = state.get('averaging_steps', {}).get(symbol, 0)
            surplus_stage = state.get('surplus_dump_stage', {}).get(symbol, 0)
            upnl = pos.get('unrealized_pnl', 0)

            self.log(f"\n  {symbol}:")
            self.log(f"    Zone: {zone}")
            self.log(f"    UPNL: ${upnl:.2f}")
            self.log(f"    Averaging Steps: {avg_steps}")
            self.log(f"    Surplus Dump Stage: {surplus_stage}")

            if symbol in self.position_history:
                history = self.position_history[symbol]
                self.log(f"    Zones Visited: {', '.join(history['zones_visited'])}")
                self.log(f"    Max Averaging Step: {history['max_averaging_step']}")
                self.log(f"    Max Surplus Stage: {history['max_surplus_stage']}")

        # Progress tracking
        self.log(f"\n✅ Required Transitions Progress:")
        self.log(f"  • Averaging Steps: {'✅ COMPLETE' if self.required_transitions['averaging_steps'] else '⏳ WAITING'}")
        self.log(f"  • Surplus Dump: {'✅ COMPLETE' if self.required_transitions['surplus_dump'] else '⏳ WAITING'}")

        if self.averaging_executed:
            self.log(f"\n  Positions that averaged: {', '.join(self.averaging_executed)}")
        if self.surplus_dump_executed:
            self.log(f"  Positions that dumped surplus: {', '.join(self.surplus_dump_executed)}")

        self.log("="*60 + "\n")

    def run(self):
        """Main monitoring loop"""
        self.log("🚀 Starting continuous state transition monitor")
        self.log("📌 Will run until at least one position completes averaging and surplus dump")

        iteration = 0
        check_interval = 5  # seconds

        try:
            while True:
                iteration += 1

                # Load current state
                state = self.load_state()

                # Detect changes
                changes = self.detect_changes(state)

                # Log any changes
                if changes and iteration > 1:  # Skip initial load
                    self.log(f"\n🔔 Changes detected (iteration {iteration}):")
                    for change in changes:
                        self.log(f"  {change}")

                # Every 12 iterations (1 minute), print summary
                if iteration % 12 == 0:
                    self.print_summary()

                # Check if we've completed all requirements
                if self.check_completion():
                    self.log("\n✨ Monitoring complete! All state transitions have been observed.")
                    self.print_summary()

                    # Save final report
                    report_file = f'/app/transition_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
                    with open(report_file, 'w') as f:
                        json.dump({
                            'completion_time': datetime.now().isoformat(),
                            'position_history': {
                                symbol: {
                                    'zones_visited': list(data['zones_visited']),
                                    'averaging_steps': data['averaging_steps'],
                                    'surplus_stages': data['surplus_stages'],
                                    'max_averaging_step': data['max_averaging_step'],
                                    'max_surplus_stage': data['max_surplus_stage']
                                }
                                for symbol, data in self.position_history.items()
                            },
                            'averaging_executed': list(self.averaging_executed),
                            'surplus_dump_executed': list(self.surplus_dump_executed)
                        }, f, indent=2)

                    self.log(f"📄 Final report saved to: {report_file}")
                    break

                # Sleep before next check
                time.sleep(check_interval)

        except KeyboardInterrupt:
            self.log("\n⚠️ Monitor interrupted by user")
            self.print_summary()

        except Exception as e:
            self.log(f"\n❌ Monitor error: {e}")
            import traceback
            self.log(traceback.format_exc())


if __name__ == "__main__":
    monitor = StateTransitionMonitor()
    monitor.run()