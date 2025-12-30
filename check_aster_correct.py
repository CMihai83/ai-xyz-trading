#!/usr/bin/env python3

# ASTER position details
entry_price = 2.0609
current_price = 2.10  # approximate
amount = 3.0  # current size
leverage = 23.0

# First averaging step - add 1x original size
step_size = 3.0  # adding 3 contracts

# Calculate notional value (after leverage)
notional_value = step_size * current_price
margin_required = notional_value / leverage

print('ASTER Averaging - CORRECTED Analysis:')
print('='*60)
print(f'Current price: ${current_price:.4f}')
print(f'Contracts to add: {step_size}')
print(f'Notional value (after leverage): ${notional_value:.2f}')
print(f'Margin required: ${margin_required:.4f}')
print(f'Leverage: {leverage}x')
print()

# Check against Bitget minimum
bitget_minimum = 5.0  # $5 minimum notional value (after leverage)

if notional_value >= bitget_minimum:
    print(f'✅ Notional value ${notional_value:.2f} MEETS Bitget minimum of ${bitget_minimum}')
    print('   Order should have been accepted!')
else:
    print(f'❌ Notional value ${notional_value:.2f} is BELOW Bitget minimum of ${bitget_minimum}')

print()
print('ACTUAL ISSUE:')
print('-'*60)
print(f'• 3 contracts × ${current_price:.2f} = ${notional_value:.2f} notional')
print(f'• Bitget requires minimum ${bitget_minimum} notional value')
print(f'• Order value ${notional_value:.2f} > ${bitget_minimum} minimum ✅')
print()
print('Since ${:.2f} > $5, the order SHOULD have worked!'.format(notional_value))
print()
print('POSSIBLE REASONS FOR FAILURE:')
print('-'*60)
print('1. Position might be using cross margin instead of isolated')
print('2. Insufficient available balance for the margin')
print('3. Different minimum for this specific pair')
print('4. API configuration or permission issue')
print()

# Check what size would be needed if minimum is actually higher
actual_minimum = 5.0  # If this is per margin, not notional
min_contracts_if_margin = (actual_minimum * leverage) / current_price

print('IF Bitget actually requires $5 MARGIN (not notional):')
print(f'• Would need {min_contracts_if_margin:.1f} contracts minimum')
print(f'• Current attempt: {step_size} contracts')