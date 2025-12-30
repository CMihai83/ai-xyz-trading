#!/usr/bin/env python3
import ccxt
import os
from dotenv import load_dotenv

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

# Get position data from exchange
positions = exchange.fetch_positions()
luna_pos = None
for pos in positions:
    if pos['symbol'] == 'LUNA/USDT:USDT' and pos['contracts'] > 0:
        luna_pos = pos
        break

if not luna_pos:
    print("LUNA position not found")
    exit()

position = {
    'symbol': luna_pos['symbol'],
    'amount': luna_pos['contracts'],
    'side': luna_pos['side'],
    'leverage': luna_pos.get('leverage', 8),
    'pnl_pct': luna_pos['percentage'],
    'upnl': luna_pos['unrealizedPnl']
}

# Get current price

try:
    ticker = exchange.fetch_ticker('LUNA/USDT:USDT')
    current_price = ticker['last']
    amount = position['amount']
    leverage = position['leverage']
    side = position['side']
    pnl_pct = position['pnl_pct']
    upnl = position['upnl']

    # Calculate entry price from P&L
    if side == 'long':
        # For long: pnl_pct = (current - entry)/entry * leverage * 100
        entry_price = current_price / (1 + pnl_pct / (leverage * 100))
    else:
        # For short: pnl_pct = (entry - current)/entry * leverage * 100
        entry_price = current_price / (1 - pnl_pct / (leverage * 100))

    margin = (entry_price * amount) / leverage

    print(f"LUNA Position:")
    print(f"  Entry: ${entry_price:.4f}")
    print(f"  Current: ${current_price:.4f}")
    print(f"  Amount: {amount}")
    print(f"  Leverage: {leverage}x")
    print(f"  UPNL: ${upnl:.2f} ({pnl_pct:.2f}%)")
    print(f"  Margin: ${margin:.2f}")

    # Check averaging trigger
    averaging_pnl_threshold = -15.0
    gate_passed = pnl_pct <= averaging_pnl_threshold
    print(f"\nAveraging Check:")
    print(f"  Gate (-15% P&L): {'✅ PASSED' if gate_passed else '❌ NOT PASSED'}")
    print(f"  Current P&L: {pnl_pct:.2f}% vs Threshold: {averaging_pnl_threshold}%")

    if gate_passed:
        print("  Averaging should trigger!")
    else:
        print(f"  Averaging won't trigger until P&L <= {averaging_pnl_threshold}%")

except Exception as e:
    print(f"Error: {e}")