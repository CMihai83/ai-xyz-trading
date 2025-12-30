#!/usr/bin/env python3
"""Continuous monitoring until all positions are closed"""
import json
import ccxt
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

def monitor_until_all_closed():
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    print("🔄 MONITORING POSITIONS UNTIL ALL CLOSED")
    print("=" * 80)

    check_count = 0
    initial_positions = None
    closed_positions = []

    while True:
        try:
            check_count += 1

            # Read position state
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)

            if not state['active_positions']:
                print(f"\n✅ ALL POSITIONS CLOSED!")
                print(f"Total monitoring time: {check_count * 10} seconds")
                print(f"Positions closed: {', '.join(closed_positions)}")
                break

            # Track initial positions
            if initial_positions is None:
                initial_positions = set(state['active_positions'].keys())

            # Check for closed positions
            current_positions = set(state['active_positions'].keys())
            newly_closed = initial_positions - current_positions - set(closed_positions)
            if newly_closed:
                for symbol in newly_closed:
                    closed_positions.append(symbol)
                    print(f"\n🔒 POSITION CLOSED: {symbol}")

            # Show status every 30 seconds
            if check_count % 3 == 1:
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Status Check #{check_count}")
                print("-" * 80)

                total_upnl = 0
                for symbol in state['active_positions']:
                    pos = state['active_positions'][symbol]
                    zone = state['position_zones'].get(symbol, 'UNKNOWN')
                    steps = state['averaging_steps'].get(symbol, 0)

                    try:
                        ticker = exchange.fetch_ticker(symbol)
                        current_price = ticker['last']

                        # Calculate UPNL
                        entry = pos['entry_price']
                        amount = pos['amount']
                        leverage = pos.get('leverage', 10)
                        side = pos['side']

                        if side == 'buy':
                            price_change = current_price - entry
                        else:
                            price_change = entry - current_price

                        upnl = price_change * amount
                        position_value = entry * amount
                        margin = position_value / leverage
                        margin_pct = (upnl / margin) * 100
                        total_upnl += upnl

                        # Status
                        zone_emoji = {
                            'NEUTRAL': '⚪',
                            'AVERAGING': '🔴',
                            'SURPLUS_DUMP': '🟡',
                            'PROFIT_TAKING': '🟢',
                            'STOP_LOSS': '⛔'
                        }.get(zone, '❓')

                        status = f"{zone_emoji} {symbol}: ${upnl:+.2f} ({margin_pct:+.1f}%)"
                        if steps > 0:
                            status += f" | Steps: {steps}"
                        print(status)

                    except Exception as e:
                        print(f"❌ Error checking {symbol}: {e}")

                print(f"\n💰 Total UPNL: ${total_upnl:+.2f}")
                print(f"📊 Active: {len(state['active_positions'])} | Closed: {len(closed_positions)}")

            time.sleep(10)

        except KeyboardInterrupt:
            print("\n⏹️ Monitoring stopped by user")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)

    print("\n" + "=" * 80)
    print("📊 FINAL SUMMARY:")
    print(f"Started with: {len(initial_positions)} positions")
    print(f"All positions have been closed")
    print(f"Total monitoring duration: {check_count * 10} seconds")

if __name__ == "__main__":
    monitor_until_all_closed()