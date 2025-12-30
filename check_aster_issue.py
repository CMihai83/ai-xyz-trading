#!/usr/bin/env python3

# ASTER position details
entry_price = 2.0609
current_price = 2.10  # approximate
amount = 3.0  # current size
leverage = 23.0

# First averaging step - add 1x original size
step_size = 3.0  # adding 3 contracts

# Calculate notional value and margin required
notional_value = step_size * current_price
margin_required = notional_value / leverage

print('ASTER Averaging Failure Analysis:')
print('='*60)
print(f'Current price: ${current_price:.4f}')
print(f'Contracts to add: {step_size}')
print(f'Notional value: ${notional_value:.2f}')
print(f'Leverage: {leverage}x')
print(f'Margin required: ${margin_required:.4f}')
print()
print(f'❌ PROBLEM: Margin required (${margin_required:.4f}) is less than')
print('   Bitget minimum order size of $5 USDT')
print()
print('WHY AVERAGING FAILED:')
print('-'*60)
print(f'• Bitget requires minimum $5 margin per order')
print(f'• ASTER averaging step needs only ${margin_required:.2f} margin')
print(f'• Order was rejected with error code 45110')
print()
print('SOLUTION:')
print('-'*60)
print('The initial ASTER position size is too small for averaging.')
print('With only 3 contracts at ~$2.10 each:')

# Calculate minimum contracts needed
min_margin = 5.0
min_notional = min_margin * leverage
min_contracts = min_notional / current_price

print(f'• Minimum contracts needed: {min_contracts:.1f}')
print(f'• Minimum notional value: ${min_notional:.2f}')
print(f'• Current position has only 3 contracts')
print()
print('RECOMMENDATION:')
print('-'*60)
print('1. Close ASTER position (too small for proper averaging)')
print('2. Open positions with initial size of at least:')
print(f'   ${min_notional:.2f} notional / {leverage}x leverage = ${min_margin:.2f} margin')
print('3. Or use the system scanner to find appropriate pairs')
print('   that meet the $6.50 minimum position size after leverage')