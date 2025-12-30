#!/usr/bin/env python3
"""Check current balance and position limits"""

import ccxt

# Setup exchange
exchange = ccxt.bitget({
    'apiKey': 'bg_2a2a7096f3f092a5c088171d1fa76421',
    'secret': '2f3acb91c8b5ddb3cf6b7e09ad99c7e4b802e3f1c3e2e7af8ab06de50a4e07be',
    'password': 'N8P4tgZd'
})
exchange.set_sandbox_mode(True)

# Get balance
balance = exchange.fetch_balance()
print(f'Total USDT: ${balance["USDT"]["total"]:.2f}')
print(f'Free USDT: ${balance["USDT"]["free"]:.2f}')
print(f'Used USDT: ${balance["USDT"]["used"]:.2f}')

# Get positions
positions = exchange.fetch_positions()
active_positions = [p for p in positions if p['contracts'] > 0]
print(f'\nActive positions: {len(active_positions)}')

total_margin = 0
for pos in active_positions:
    margin = pos['notional'] / (pos['leverage'] or 10)
    total_margin += margin
    print(f'  {pos["symbol"]}: Margin ${margin:.2f}, Notional ${pos["notional"]:.2f}')

print(f'\nTotal margin in use: ${total_margin:.2f}')
print(f'Free capital: ${balance["USDT"]["free"]:.2f}')

# Calculate requirements
margin_per_position = 10.83 / 9  # ~$1.20
print(f'\nMargin per new position: ${margin_per_position:.2f}')

# Calculate how much we need for averaging existing positions
# Fibonacci: 1x + 2x + 3x + 5x + 8x = 19x additional margin needed
total_averaging_needed = total_margin * 19
print(f'\nCapital needed for full averaging of {len(active_positions)} positions: ${total_averaging_needed:.2f}')
print(f'Current free capital: ${balance["USDT"]["free"]:.2f}')

if balance["USDT"]["free"] < total_averaging_needed:
    print(f'\n⚠️ INSUFFICIENT CAPITAL for averaging!')
    print(f'   Short by ${total_averaging_needed - balance["USDT"]["free"]:.2f}')
    print(f'   System should NOT open new positions!')
else:
    available_after_reserve = balance["USDT"]["free"] - total_averaging_needed
    print(f'\n✅ Capital after averaging reserve: ${available_after_reserve:.2f}')
    
    # How many new positions can we open?
    new_position_capital_needed = margin_per_position * 20  # Need 20x for full averaging
    max_new = int(available_after_reserve / new_position_capital_needed)
    print(f'   Can open {max_new} new positions with full averaging capability')

# Recommendations
print('\n' + '='*60)
print('RECOMMENDATIONS:')
print('='*60)

if len(active_positions) > 3:
    print('⚠️ Too many positions open! Should limit to 2-3 maximum.')
    print('   Current system cannot properly average all positions.')

if balance["USDT"]["total"] < 20:
    print('📊 Small account detected (<$20)')
    print('   Should limit to MAX 2 positions')
    print(f'   Current: {len(active_positions)} positions')
elif balance["USDT"]["total"] < 50:
    print('📊 Medium account detected (<$50)')
    print('   Should limit to MAX 3 positions')
    print(f'   Current: {len(active_positions)} positions')
else:
    print('📊 Larger account detected')
    print('   Could support up to 4 positions')
    print(f'   Current: {len(active_positions)} positions')

print('\nPosition sizing should be:')
print(f'  Base size: $10.83 (after leverage)')
print(f'  Margin needed: ${margin_per_position:.2f}')
print(f'  For full averaging: ${margin_per_position * 20:.2f} per position')