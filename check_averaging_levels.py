#!/usr/bin/env python3
import json

# Read current position state
with open('/app/position_state.json', 'r') as f:
    state = json.load(f)

# Get BARD position details
bard = state['active_positions'].get('BARD/USDT:USDT', {})
entry_price = bard.get('entry_price', 1.4176)
side = bard.get('side', 'sell')
amount = bard.get('amount', 4.0)
leverage = bard.get('leverage', 32)

print('BARD/USDT:USDT Position & Averaging Levels:')
print('='*70)
print(f'Position Type: SHORT')
print(f'Entry Price: ${entry_price:.4f}')
print(f'Current Size: {amount} contracts')
print(f'Leverage: {leverage}x')
print(f'Initial Margin: ${(entry_price * amount) / leverage:.4f}')
print()

# Based on the system configuration, averaging steps are typically:
# Using fibonacci-based percentages with adaptive thresholds
# For high volatility pairs like BARD, typical thresholds are:
averaging_thresholds = [1.34, 2.67, 4.01, 5.35, 8.02, 12.03]

print('Averaging Step Levels (SHORT - triggers when price rises):')
print('-'*70)
print('Step | Trigger Price | Distance from Entry | Size Multiplier')
print('-'*70)

# Fibonacci multipliers for position sizing
fib_multipliers = [1, 1, 2, 3, 5, 8]

total_contracts = amount
for i, (threshold_pct, multiplier) in enumerate(zip(averaging_thresholds, fib_multipliers), 1):
    trigger_price = entry_price * (1 + threshold_pct/100)
    distance = trigger_price - entry_price
    step_size = amount * multiplier
    total_contracts += step_size
    print(f'{i:4d} | ${trigger_price:11.4f} | +${distance:8.4f} (+{threshold_pct:5.2f}%) | {multiplier:2d}x ({step_size:.0f} contracts)')

print()
print('Position Management Summary:')
print('-'*70)
print(f'• Total capital allocated: $25.00 per position')
print(f'• Trading capital: $17.50 (for initial + averaging)')
print(f'• Safety margin: $7.50 (added after final averaging step)')
print(f'• Surplus dump trigger: 70% of peak profit (100% dump)')
print(f'• Take profit minimum: $5.00')
print()
print(f'Maximum position size after all averaging: {total_contracts:.0f} contracts')
print(f'Required margin for full averaging: ~${(entry_price * total_contracts) / leverage:.2f}')