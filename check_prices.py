#!/usr/bin/env python3
"""Check current market prices for active positions"""

import ccxt
import os
import json
from dotenv import load_dotenv

load_dotenv('/app/.env')

# Initialize exchange
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

# Load position state
with open('/app/position_state.json', 'r') as f:
    state = json.load(f)

positions = state.get('active_positions', {})

print("\n" + "="*60)
print("📊 CURRENT MARKET PRICES & UPNL")
print("="*60)

for symbol, position in positions.items():
    try:
        ticker = exchange.fetch_ticker(symbol)
        current_price = ticker['last']
        entry_price = position['entry_price']
        amount = position['amount']
        side = position.get('side', 'buy')
        leverage = position.get('leverage', 1)

        # Calculate UPNL
        if side == 'buy':
            upnl = (current_price - entry_price) * amount
        else:  # sell
            upnl = (entry_price - current_price) * amount

        # Calculate position value and UPNL%
        position_value = entry_price * amount
        upnl_pct = (upnl / position_value) * 100 if position_value > 0 else 0

        print(f"\n{symbol}")
        print(f"  Entry: ${entry_price:.6f}")
        print(f"  Current: ${current_price:.6f}")
        print(f"  Change: {((current_price/entry_price - 1) * 100):.2f}%")
        print(f"  UPNL: ${upnl:.4f} ({upnl_pct:.1f}%)")
        print(f"  Zone: {state['position_zones'].get(symbol, 'UNKNOWN')}")

        # Check thresholds
        if upnl_pct <= -42:
            print(f"  ⚠️ Ready for averaging (threshold -42%)")
        elif upnl_pct <= -70:
            print(f"  🔴 Stop loss territory (threshold -70%)")

        # Check surplus dump for positions with peak UPNL
        peak_upnl = state['peak_upnl'].get(symbol, 0)
        if peak_upnl > 0.10 and upnl > 0:
            dump_85 = peak_upnl * 0.85
            dump_50 = peak_upnl * 0.50
            print(f"  Peak UPNL: ${peak_upnl:.4f}")
            print(f"  Stage 1 trigger (85%): ${dump_85:.4f}")
            print(f"  Stage 2 trigger (50%): ${dump_50:.4f}")
            if upnl <= dump_85:
                print(f"  💰 Ready for surplus dump stage 1")

    except Exception as e:
        print(f"\n{symbol}: Error fetching price - {e}")

print("\n" + "="*60)