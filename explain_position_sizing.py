#!/usr/bin/env python3
"""
Explain the correct position sizing with [8,5,3] multipliers
and 70/30 capital split with safety margin on last step only
"""

def explain_sizing():
    print("\n" + "="*60)
    print("    POSITION SIZING EXPLANATION")
    print("="*60)
    
    # Current account balance
    total_capital = 17.47
    
    print(f"\n💰 Account Balance: ${total_capital:.2f}")
    print(f"   Position Limit: 1 position (below $50)")
    print(f"   Capital per Position: ${total_capital:.2f}")
    
    # 70/30 split
    averaging_capital = total_capital * 0.70  # $12.23
    safety_margin = total_capital * 0.30      # $5.24
    
    print(f"\n📊 Capital Allocation (70/30 Rule):")
    print(f"   70% for averaging: ${averaging_capital:.2f}")
    print(f"   30% safety margin: ${safety_margin:.2f} (reserved for last step)")
    
    # Fibonacci multipliers [8,5,3] - DECREASING intentionally
    multipliers = [8, 5, 3]
    total_multiplier = 1 + sum(multipliers)  # 1 + 8 + 5 + 3 = 17
    
    print(f"\n🔢 Fibonacci Multipliers: {multipliers}")
    print(f"   Total multiplier: 1 (initial) + {' + '.join(map(str, multipliers))} = {total_multiplier}")
    
    # Calculate base amount
    base_amount = averaging_capital / total_multiplier
    
    print(f"\n📈 Position Sizing Breakdown:")
    print(f"   Base amount: ${averaging_capital:.2f} ÷ {total_multiplier} = ${base_amount:.2f}")
    
    # Show each step
    print(f"\n   Step 0 (Initial): ${base_amount:.2f} × 1 = ${base_amount:.2f}")
    
    total = base_amount
    for i, mult in enumerate(multipliers, 1):
        step_amount = base_amount * mult
        total += step_amount
        
        if i == len(multipliers):
            # Last step gets safety margin
            step_amount += safety_margin
            print(f"   Step {i} (Averaging): ${base_amount:.2f} × {mult} = ${base_amount * mult:.2f}")
            print(f"                      + ${safety_margin:.2f} safety = ${step_amount:.2f} ⬅️ FINAL STEP")
            total += safety_margin
        else:
            print(f"   Step {i} (Averaging): ${base_amount:.2f} × {mult} = ${step_amount:.2f}")
    
    print(f"\n   Total capital used: ${total:.2f}")
    
    print(f"\n💡 Why the first averaging is ~$5:")
    print(f"   Base amount: ${base_amount:.2f}")
    print(f"   First averaging: ${base_amount:.2f} × 8 = ${base_amount * 8:.2f}")
    print(f"   This is CORRECT - we want larger steps early!")
    
    print(f"\n✅ Benefits of [8,5,3] decreasing multipliers:")
    print(f"   1. More capital deployed early when price moves against us")
    print(f"   2. Improves average price faster")
    print(f"   3. Reduces risk of deep drawdown")
    print(f"   4. Safety margin only on last step protects from liquidation")
    
    print("\n" + "="*60)
    print("")

if __name__ == "__main__":
    explain_sizing()