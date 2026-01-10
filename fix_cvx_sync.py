#!/usr/bin/env python3
"""
Emergency fix: Manually sync CVX position from exchange to update peak_upnl
and enable profit-taking
"""
import json
import ccxt
import os
from datetime import datetime

def sync_cvx_position():
    """Fetch live CVX data and update position_state.json"""

    # Load API credentials
    api_key = os.getenv('BITGET_API_KEY', 'bg_51d0d52cc6ec6d13ae8e6c5f8f6c0633')
    api_secret = os.getenv('BITGET_SECRET', '88e3e2e5e5f6a8b7dbb47e21dc3f94cc51e90fcd8d71eae5e9e0799c9e21ad4b')
    api_passphrase = os.getenv('BITGET_PASSPHRASE', 'FLorin123!@#')

    # Initialize exchange
    exchange = ccxt.bitget({
        'apiKey': api_key,
        'secret': api_secret,
        'password': api_passphrase,
        'options': {'defaultType': 'swap'}
    })

    print("🔍 Fetching live CVX position from exchange...")

    try:
        # Fetch CVX position
        positions = exchange.fetch_positions(['CVX/USDT:USDT'])

        cvx_pos = None
        for pos in positions:
            if pos['contracts'] > 0 and pos['symbol'] == 'CVX/USDT:USDT':
                cvx_pos = pos
                break

        if not cvx_pos:
            print("❌ No CVX position found on exchange")
            return

        # Extract data
        symbol = 'CVX/USDT:USDT'
        contracts = cvx_pos['contracts']
        entry_price = cvx_pos['entryPrice']
        mark_price = cvx_pos['markPrice']
        upnl = cvx_pos.get('unrealizedPnl', 0)
        percentage = cvx_pos.get('percentage', 0)
        side = cvx_pos['side']

        print(f"\n=== LIVE CVX DATA ===")
        print(f"Contracts: {contracts}")
        print(f"Entry: ${entry_price:.4f}")
        print(f"Mark: ${mark_price:.4f}")
        print(f"UPNL: ${upnl:.4f}")
        print(f"P&L%: {percentage:.2f}%")
        print(f"Side: {side}")

        # Load position_state.json
        with open('position_state.json', 'r') as f:
            state = json.load(f)

        # Update CVX position data
        if symbol in state['active_positions']:
            print(f"\n🔧 Updating CVX in position_state.json...")

            # Update entry price (weighted average from exchange)
            old_entry = state['active_positions'][symbol]['entry_price']
            state['active_positions'][symbol]['entry_price'] = entry_price
            state['active_positions'][symbol]['amount'] = contracts

            print(f"  Entry: ${old_entry:.4f} → ${entry_price:.4f}")
            print(f"  Amount: {state['active_positions'][symbol]['amount']} contracts")

            # Update peak UPNL if current UPNL is higher
            old_peak = state['peak_upnl'].get(symbol, 0)
            if upnl > old_peak:
                state['peak_upnl'][symbol] = upnl
                state['peak_upnl_timestamps'][symbol] = datetime.now().isoformat()
                print(f"  Peak UPNL: ${old_peak:.4f} → ${upnl:.4f} ✅")
            else:
                print(f"  Peak UPNL: ${old_peak:.4f} (current ${upnl:.4f})")

            # Calculate averaging steps from size increase
            original_size = state['original_sizes'].get(symbol, contracts)
            if original_size == 0:
                original_size = contracts / 5  # Estimate from 5x increase
                state['original_sizes'][symbol] = original_size

            size_multiplier = contracts / original_size
            estimated_steps = max(0, int(size_multiplier - 1))

            old_steps = state['averaging_steps'].get(symbol, 0)
            if estimated_steps > old_steps:
                state['averaging_steps'][symbol] = estimated_steps
                print(f"  Averaging steps: {old_steps} → {estimated_steps} (estimated from {size_multiplier:.1f}x size)")

            # Update zone based on profit
            old_zone = state['position_zones'].get(symbol, 'NEUTRAL')
            if upnl > 0 and estimated_steps > 0:
                state['position_zones'][symbol] = 'SURPLUS_DUMP'
                print(f"  Zone: {old_zone} → SURPLUS_DUMP (averaged position in profit)")
            elif upnl > 0:
                state['position_zones'][symbol] = 'PROFIT_TAKING'
                print(f"  Zone: {old_zone} → PROFIT_TAKING (profit detected)")

            # Update timestamp
            state['timestamp'] = datetime.now().isoformat()

            # Save updated state
            with open('position_state.json', 'w') as f:
                json.dump(state, f, indent=2)

            print(f"\n✅ CVX position synchronized!")
            print(f"   The system should now monitor and take profit on CVX")

            # Show profit-taking threshold
            peak = state['peak_upnl'][symbol]
            if peak >= 0.50:
                threshold_70 = peak * 0.70
                print(f"\n💰 PROFIT-TAKING INFO:")
                print(f"   Peak: ${peak:.4f}")
                print(f"   Current: ${upnl:.4f} ({(upnl/peak*100):.1f}% of peak)")
                print(f"   Will exit at: ${threshold_70:.4f} (70% of peak)")
                if upnl <= threshold_70:
                    print(f"   ⚠️  SHOULD TAKE PROFIT NOW!")
            else:
                print(f"\n⏳ Peak UPNL ${peak:.4f} < $0.50 minimum threshold")
                print(f"   Need ${0.50 - peak:.4f} more profit to enable profit-taking")

        else:
            print(f"\n❌ CVX not found in active_positions")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    sync_cvx_position()
