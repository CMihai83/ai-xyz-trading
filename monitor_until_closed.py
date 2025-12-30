#!/usr/bin/env python3
"""Monitor positions until all are closed"""
import json
import ccxt
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

def monitor_until_closed():
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    print("🔄 Monitoring positions until closure...")
    print("=" * 80)

    initial_positions = {}
    check_count = 0

    while True:
        try:
            check_count += 1

            # Read position state
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)

            if not state['active_positions']:
                print(f"\n✅ ALL POSITIONS CLOSED!")
                print(f"Total checks performed: {check_count}")
                break

            current_time = datetime.now().strftime('%H:%M:%S')
            print(f"\n[{current_time}] Check #{check_count}")
            print("-" * 80)

            # Track initial positions
            if not initial_positions:
                initial_positions = {k: v['entry_price'] for k, v in state['active_positions'].items()}

            positions_summary = []
            total_upnl = 0

            for symbol in state['active_positions']:
                position = state['active_positions'][symbol]
                zone = state['position_zones'].get(symbol, 'UNKNOWN')
                steps = state['averaging_steps'].get(symbol, 0)
                peak = state.get('peak_upnl', {}).get(symbol, 0)
                dump_stage = state.get('surplus_dump_stage', {}).get(symbol, 0)

                # Get current price
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                except Exception as e:
                    print(f"❌ Error fetching {symbol}: {e}")
                    continue

                # Calculate UPNL
                entry_price = position['entry_price']
                amount = position['amount']
                leverage = position.get('leverage', 10)
                side = position['side']

                if side == 'buy':
                    price_change = current_price - entry_price
                else:  # sell
                    price_change = entry_price - current_price

                upnl = price_change * amount
                position_value = entry_price * amount
                margin = position_value / leverage
                upnl_pct = (upnl / position_value) * 100
                margin_pct = (upnl / margin) * 100
                total_upnl += upnl

                # Zone emojis
                zone_emoji = {
                    'NEUTRAL': '⚪',
                    'AVERAGING': '🔴',
                    'SURPLUS_DUMP': '🟡',
                    'PROFIT_TAKING': '🟢',
                    'STOP_LOSS': '⛔'
                }.get(zone, '❓')

                # Build summary line
                status_line = f"{zone_emoji} {symbol}: "
                status_line += f"${upnl:+.2f} ({margin_pct:+.1f}% margin) "
                status_line += f"Zone: {zone}"

                if steps > 0:
                    status_line += f" | Steps: {steps}"

                if dump_stage > 0:
                    status_line += f" | Dump Stage: {dump_stage}"

                # Check for important events
                events = []

                if margin_pct <= -42 and steps == 0:
                    events.append("🚨 READY FOR FIRST AVERAGING!")

                if margin_pct <= -68 and steps == 1:
                    events.append("🚨 READY FOR SECOND AVERAGING!")

                if peak > 0 and upnl > 0:
                    if upnl <= peak * 0.85 and dump_stage == 0:
                        events.append(f"🚨 READY FOR SURPLUS DUMP STAGE 1!")
                    elif upnl <= peak * 0.50 and dump_stage == 1:
                        events.append(f"🚨 READY FOR SURPLUS DUMP STAGE 2!")

                if margin_pct <= -70:
                    events.append("⛔ APPROACHING STOP LOSS!")

                print(status_line)
                for event in events:
                    print(f"  → {event}")

            print(f"\n💰 Total UPNL: ${total_upnl:+.2f}")
            print(f"📊 Active Positions: {len(state['active_positions'])}")

            # Check if any positions were closed
            current_positions = set(state['active_positions'].keys())
            initial_set = set(initial_positions.keys())
            closed = initial_set - current_positions

            if closed:
                print(f"\n🔒 CLOSED POSITIONS: {', '.join(closed)}")

            print("=" * 80)
            time.sleep(10)  # Check every 10 seconds

        except KeyboardInterrupt:
            print("\n⏹️ Monitoring stopped by user")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            time.sleep(5)

    print("\n📊 Final Summary:")
    print(f"Started with {len(initial_positions)} positions")
    print(f"Monitoring duration: {check_count * 10} seconds")
    print("All positions have been closed!")

if __name__ == "__main__":
    monitor_until_closed()