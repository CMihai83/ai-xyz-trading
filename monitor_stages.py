#!/usr/bin/env python3
"""Monitor positions for stage triggers continuously"""
import json
import ccxt
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

def monitor_positions():
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    print("🔄 Starting continuous position monitoring...")
    print("=" * 60)

    while True:
        try:
            # Read position state
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)

            print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Position Status:")
            print("-" * 60)

            for symbol in state['active_positions']:
                position = state['active_positions'][symbol]
                zone = state['position_zones'].get(symbol, 'UNKNOWN')
                steps = state['averaging_steps'].get(symbol, 0)
                peak = state.get('peak_upnl', {}).get(symbol, 0)

                # Get current price
                try:
                    ticker = exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                except:
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

                # Zone emojis
                zone_emoji = {
                    'NEUTRAL': '⚪',
                    'AVERAGING': '🔴',
                    'SURPLUS_DUMP': '🟡',
                    'PROFIT_TAKING': '🟢',
                    'STOP_LOSS': '⛔'
                }.get(zone, '❓')

                print(f"\n{zone_emoji} {symbol}:")
                print(f"  Zone: {zone} | Steps: {steps}")
                print(f"  Entry: ${entry_price:.5f} | Current: ${current_price:.5f}")
                print(f"  UPNL: ${upnl:.2f} ({upnl_pct:.1f}% pos, {margin_pct:.1f}% margin)")

                # Check for triggers
                if margin_pct <= -42 and zone != 'AVERAGING':
                    print(f"  🚨 READY FOR AVERAGING! ({margin_pct:.1f}% <= -42%)")

                if peak > 0 and upnl > 0:
                    if upnl <= peak * 0.85:
                        print(f"  🚨 READY FOR SURPLUS DUMP STAGE 1! (${upnl:.2f} <= ${peak*0.85:.2f})")
                    elif upnl <= peak * 0.50:
                        print(f"  🚨 READY FOR SURPLUS DUMP STAGE 2! (${upnl:.2f} <= ${peak*0.50:.2f})")

            print("\n" + "=" * 60)
            time.sleep(10)  # Check every 10 seconds

        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    monitor_positions()