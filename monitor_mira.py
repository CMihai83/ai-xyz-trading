#!/usr/bin/env python3
"""
Monitor MIRA position
"""
import json
import ccxt
import os
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

def monitor_mira():
    # Load state
    with open('/app/position_state.json', 'r') as f:
        state = json.load(f)

    # Initialize exchange
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })

    print('='*60)
    print('🔍 MONITORING MIRA POSITION')
    print('='*60)
    print(f'Time: {datetime.now().strftime("%H:%M:%S")}')

    # Check for MIRA in active positions
    mira_found = False
    for symbol, pos in state['active_positions'].items():
        if 'MIRA' in symbol:
            mira_found = True
            print(f'\n✅ Found MIRA position: {symbol}')

            zone = state['position_zones'].get(symbol, 'NEUTRAL')
            steps = state['averaging_steps'].get(symbol, 0)

            # Get current price
            try:
                ticker = exchange.fetch_ticker(symbol)
                current = ticker['last']
            except:
                current = pos['entry_price']

            # Calculate UPNL
            entry = pos['entry_price']
            amount = pos['amount']
            leverage = pos.get('leverage', 8)
            side = pos['side']

            position_value = amount * entry
            margin = position_value / leverage

            if side == 'buy':
                upnl = (current - entry) * amount
            else:
                upnl = (entry - current) * amount

            upnl_pct = (upnl / margin * 100) if margin > 0 else 0

            print(f'\n📊 MIRA POSITION DETAILS:')
            print(f'  Zone: {zone}')
            print(f'  Side: {side.upper()}')
            print(f'  Entry: {entry:.8f}')
            print(f'  Current: {current:.8f}')
            print(f'  Amount: {amount}')
            print(f'  Leverage: {leverage}x')
            print(f'  UPNL: ${upnl:.2f} ({upnl_pct:.1f}% of margin)')
            print(f'  Averaging Steps: {steps}/5')

            # Check thresholds
            thresholds = [-42, -68, -84, -94, -97]
            if zone == 'AVERAGING' and steps < len(thresholds):
                next_threshold = thresholds[steps]
                if upnl_pct <= next_threshold:
                    print(f'\n  ✅ READY for averaging step {steps+1}')
                    print(f'     Threshold reached: {next_threshold}%')
                else:
                    print(f'\n  ⏳ Next averaging at {next_threshold}%')
                    print(f'     Current: {upnl_pct:.1f}%')
                    print(f'     Need: {next_threshold - upnl_pct:.1f}% more loss')

    if not mira_found:
        print('\n❌ No MIRA position found in active positions')
        print('\n📝 Current active positions:')
        for symbol in state['active_positions'].keys():
            print(f'  - {symbol}')

        # Try to fetch MIRA from exchange
        print('\n🔍 Checking exchange for MIRA positions...')
        try:
            positions = exchange.fetch_positions()
            for pos in positions:
                if 'MIRA' in pos['symbol'] and pos.get('contracts', 0) > 0:
                    print(f'\n✅ Found MIRA on exchange: {pos["symbol"]}')
                    print(f'  Contracts: {pos["contracts"]}')
                    print(f'  Entry: {pos.get("entryPrice", 0)}')
                    print(f'  Mark Price: {pos.get("markPrice", 0)}')
                    print(f'  UPNL: ${pos.get("unrealizedPnl", 0):.2f}')
                    mira_found = True
                    break
        except Exception as e:
            print(f'  Error checking exchange: {e}')

        if not mira_found:
            print('\n❌ No MIRA position found on exchange either')

    return mira_found

# Continuous monitoring
if __name__ == "__main__":
    while True:
        monitor_mira()
        print('\n' + '-'*60)
        print('Refreshing in 10 seconds...')
        time.sleep(10)
        print('\033[2J\033[H')  # Clear screen