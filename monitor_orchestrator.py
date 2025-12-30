#!/usr/bin/env python3
"""
Real-time monitoring of orchestrator decisions
"""
import json
import time
import sys
from datetime import datetime
from orchestrator_integration import OrchestratorIntegration

def monitor_orchestrator():
    """Monitor orchestrator decisions and position states"""

    print("\n" + "="*80)
    print("🤖 ORCHESTRATOR MONITORING DASHBOARD")
    print("="*80)

    integration = OrchestratorIntegration()

    if not integration.enabled:
        print("❌ Orchestrator is DISABLED in config")
        return

    print(f"✅ Orchestrator ENABLED - Mode: {integration.orchestrator.config.get('mode', 'unknown')}")
    print(f"📊 Monitoring positions for orchestrator decisions...")
    print("-"*80)

    last_state = {}
    decision_count = 0

    while True:
        try:
            # Load position state
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)

            # Check each position in averaging zone
            for symbol, position in state['active_positions'].items():
                zone = state['position_zones'].get(symbol, 'NEUTRAL')

                # Only check positions in averaging zone
                if zone == 'AVERAGING':
                    # Calculate current UPNL%
                    entry = position['entry_price']
                    amount = position['amount']
                    leverage = position.get('leverage', 8)
                    side = position['side']

                    # Get current price (from position or use entry as fallback)
                    current_price = position.get('current_price', entry)

                    # Calculate UPNL%
                    position_value = amount * entry
                    margin = position_value / leverage

                    if side == 'buy':
                        upnl = (current_price - entry) * amount
                    else:
                        upnl = (entry - current_price) * amount

                    upnl_pct = (upnl / margin * 100) if margin > 0 else 0

                    # Get orchestrator decision
                    decision = integration.should_average(symbol, position, current_price)

                    # Check if this is a new decision
                    decision_key = f"{symbol}_{state['timestamp']}"
                    if decision_key not in last_state:
                        last_state[decision_key] = True
                        decision_count += 1

                        # Print decision details
                        timestamp = datetime.now().strftime("%H:%M:%S")
                        print(f"\n[{timestamp}] 📍 {symbol} in AVERAGING zone")
                        print(f"  UPNL: {upnl_pct:.2f}%")
                        print(f"  Steps taken: {state['averaging_steps'].get(symbol, 0)}")

                        if decision['source'] == 'orchestrator':
                            print(f"  🤖 Orchestrator Decision:")
                            print(f"     Action: {'AVERAGE' if decision['should_average'] else 'HOLD'}")
                            print(f"     Confidence: {decision.get('confidence', 0):.1%}")
                            print(f"     Reason: {decision['reason']}")
                            if decision.get('size'):
                                print(f"     Size: {decision['size']:.4f}")
                            if decision.get('metadata'):
                                print(f"     Metadata: {decision['metadata']}")
                        else:
                            print(f"  📌 Using original logic (orchestrator returned None)")

            # Print stats every 10 decisions
            if decision_count > 0 and decision_count % 10 == 0:
                stats = integration.get_stats()
                print(f"\n📊 Stats after {decision_count} decisions:")
                print(f"   {stats}")

            time.sleep(10)  # Check every 10 seconds

        except KeyboardInterrupt:
            print("\n\nMonitoring stopped.")
            break
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_orchestrator()