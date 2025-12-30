#!/usr/bin/env python3

print('AVERAGING COMPARISON: BEFORE vs AFTER FIX')
print('='*60)
print()

# Position details
position_value = 10.77
leverage = 15
original_margin = position_value / leverage

print(f'Position: ${position_value:.2f} at {leverage}x leverage')
print(f'Original margin: ${original_margin:.2f}')
print()

# Multipliers
multipliers = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]

print('OLD METHOD (Multiplier on Position Value):')
total_old = original_margin
for i, mult in enumerate(multipliers):
    margin_needed = (position_value * mult) / leverage
    total_old += margin_needed
    print(f'  Step {i+1}: Add ${margin_needed:.2f} margin (Total: ${total_old:.2f})')

print()
print('NEW METHOD (Multiplier on Margin):')
total_new = original_margin
for i, mult in enumerate(multipliers):
    margin_needed = original_margin * mult
    total_new += margin_needed
    print(f'  Step {i+1}: Add ${margin_needed:.2f} margin (Total: ${total_new:.2f})')

print()
print('SUMMARY:')
print(f'  Old method total margin: ${total_old:.2f}')
print(f'  New method total margin: ${total_new:.2f}')
print(f'  Savings: ${total_old - total_new:.2f} ({((total_old - total_new)/total_old)*100:.1f}%)')
print()
print('With $41 balance:')
print(f'  Old: Can handle {41/total_old:.1f} fully averaged positions')
print(f'  New: Can handle {41/total_new:.1f} fully averaged positions')