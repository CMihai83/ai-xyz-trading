#!/usr/bin/env python3
"""
Fix averaging_steps counter based on actual position size growth

The counter shows 0 despite positions growing 6x-19x through averaging.
This script calculates the correct step count from size ratio.

Fibonacci multipliers: 1, 1, 2, 3, 5, 8, 13, 21
Growth pattern:
- Start: 1x (original)
- Step 1: 2x (1 + 1)
- Step 2: 3x (1 + 1 + 1)
- Step 3: 5x (1 + 1 + 2)
- Step 4: 8x (1 + 1 + 2 + 3)
- Step 5: 13x (1 + 1 + 2 + 3 + 5)
- Step 6: 21x (1 + 1 + 2 + 3 + 5 + 8)
"""

import json
import math

def infer_averaging_steps(size_ratio):
    """
    Infer averaging steps from size ratio using Fibonacci growth pattern

    Fibonacci position growth:
    1.0x = 0 steps (original)
    2.0x = 1 step
    3.0x = 2 steps
    5.0x = 3 steps
    8.0x = 4 steps
    13.0x = 5 steps
    21.0x = 6 steps
    """
    if size_ratio < 1.5:
        return 0
    elif size_ratio < 2.5:
        return 1
    elif size_ratio < 4.0:
        return 2
    elif size_ratio < 6.5:
        return 3
    elif size_ratio < 10.5:
        return 4
    elif size_ratio < 17.0:
        return 5
    else:
        return 6


def fix_averaging_steps():
    """Fix averaging_steps counter for all positions"""

    print("=" * 80)
    print("FIXING AVERAGING STEPS COUNTER")
    print("=" * 80)
    print()

    # Load current state
    with open('/root/ai_xyz/position_state.json', 'r') as f:
        state = json.load(f)

    positions = state['active_positions']
    original_sizes = state['original_sizes']
    averaging_steps = state['averaging_steps']

    print("Current State:")
    print("-" * 80)

    fixes_made = 0

    for symbol, pos in positions.items():
        current_size = pos['amount']
        original_size = original_sizes.get(symbol, current_size)
        current_step = averaging_steps.get(symbol, 0)

        # Calculate size ratio
        if original_size > 0:
            size_ratio = current_size / original_size
        else:
            size_ratio = 1.0

        # Infer correct step count
        inferred_steps = infer_averaging_steps(size_ratio)

        print(f"\n{symbol}:")
        print(f"  Original size: {original_size:,.0f}")
        print(f"  Current size:  {current_size:,.0f}")
        print(f"  Growth ratio:  {size_ratio:.2f}x")
        print(f"  Current step:  {current_step}")
        print(f"  Inferred step: {inferred_steps}")

        if inferred_steps != current_step:
            print(f"  🔧 FIX: Updating {current_step} → {inferred_steps}")
            averaging_steps[symbol] = inferred_steps
            fixes_made += 1
        else:
            print(f"  ✅ Correct (no change needed)")

    # Update state
    state['averaging_steps'] = averaging_steps

    # Save updated state
    with open('/root/ai_xyz/position_state.json', 'w') as f:
        json.dump(state, f, indent=2)

    print()
    print("=" * 80)
    print(f"COMPLETE: Fixed {fixes_made} positions")
    print("=" * 80)
    print()

    # Summary
    print("Updated averaging_steps:")
    for symbol, steps in averaging_steps.items():
        if steps > 0:
            print(f"  {symbol}: {steps} steps")


if __name__ == '__main__':
    fix_averaging_steps()
