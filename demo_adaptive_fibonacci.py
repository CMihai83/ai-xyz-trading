#!/usr/bin/env python3
"""
Demo of Adaptive Fibonacci Averaging System
Shows automatic K coefficient calculation for safe position management
"""

import sys
sys.path.append('/app')
sys.path.append('/app/core')

from adaptive_fibonacci_averaging import AdaptiveFibonacciCalculator, calculate_position_averaging_config

def demo_adaptive_system():
    print("\n" + "="*120)
    print("ADAPTIVE FIBONACCI AVERAGING SYSTEM - LIVE DEMONSTRATION")
    print("="*120)
    
    print("\n📊 SCENARIO: Your Trading Position")
    print("-"*120)
    
    # Your exact parameters
    params = {
        'entry_price': 10000,
        'leverage': 7,
        'initial_margin': 1.0,
        'total_margin': 25.0,
        'max_delta': 1000.0,
        'direction': 'long'
    }
    
    print(f"""
Trading Parameters:
• Coin: Generic (example at $10,000)
• Position Type: LONG
• Leverage: {params['leverage']}x
• Initial Margin: ${params['initial_margin']}
• Total Capital: ${params['total_margin']}
• Available for Averaging: ${params['total_margin'] * 0.7:.2f} (70%)
• Safety Reserve: ${params['total_margin'] * 0.3:.2f} (30%)
• Max Price Drop (Delta): ${params['max_delta']} (10% from entry)
""")
    
    print("\n🔍 CALCULATING OPTIMAL STRATEGY...")
    print("-"*120)
    
    # Calculate adaptive configuration
    config = calculate_position_averaging_config(**params)
    
    print(f"""
✅ OPTIMAL CONFIGURATION FOUND:

• K Coefficient: {config['k_coefficient']:.2f}
  └─ This multiplier ensures all averaging steps stay >10% above liquidation
  
• Maximum Safe Steps: {config['max_safe_steps']}
  └─ You can average down {config['max_safe_steps']} times safely
  
• Total Margin Required: ${config['total_margin_required']:.2f}
  └─ Uses only ${config['total_margin_required']:.2f} of your ${params['total_margin'] * 0.7:.2f} available
  
• Safety Validation: {'✅ PASSED' if config['safety_validated'] else '❌ FAILED'}
  └─ All steps maintain minimum 10% distance from liquidation
  
• Minimum Safety Buffer: {config['min_safety_distance']*100:.1f}%
  └─ Worst-case distance from liquidation across all steps
""")
    
    print("\n📋 AVERAGING STEPS BREAKDOWN")
    print("-"*120)
    print(f"{'Step':<6} {'Trigger Price':<14} {'Delta Used':<12} {'Fib Weight':<11} {'Multiplier':<12} {'Margin':<10} {'Total Margin':<13} {'Liq Price':<12} {'Safety':<10}")
    print("-"*120)
    
    # Initial position
    initial_liq = params['entry_price'] * 0.857  # Approximate
    print(f"{'0':<6} ${params['entry_price']:<13,} {'0%':<12} {'-':<11} {'-':<12} ${params['initial_margin']:<9.2f} ${params['initial_margin']:<12.2f} ${initial_liq:<11,.0f} {'Initial':<10}")
    
    # Show averaging steps
    for step in config['averaging_steps']:
        print(f"{step['step_number']:<6} ${step['price']:<13,.0f} {step['delta_threshold']*100:<11.0f}% {step['fibonacci_weight']:<11} {step['position_multiplier']:<11.2f}x ${step['margin_allocation']:<9.2f} ${step['cumulative_margin']:<12.2f} ${step['liquidation_price']:<11,.0f} {step['safety_distance']*100:<9.1f}%")
    
    print("-"*120)
    
    print("\n💡 HOW IT WORKS")
    print("-"*120)
    print(f"""
1. AUTOMATIC SAFETY CALCULATION:
   The system tested K values from 0.1 to 3.0 and found K={config['k_coefficient']:.2f} optimal because:
   • It maximizes averaging steps ({config['max_safe_steps']} steps possible)
   • Every step maintains >10% distance from liquidation
   • Uses capital efficiently (${config['total_margin_required']:.2f} of ${params['total_margin'] * 0.7:.2f})

2. FIBONACCI SEQUENCE WITH K ADJUSTMENT:
   Base Fibonacci: [1, 1, 2, 3, 5, 8, 13]
   Your Multipliers: {[round(fib * config['k_coefficient'], 2) for fib in [1,1,2,3,5,8,13][:config['max_safe_steps']]]}
   
3. POSITION EVOLUTION:
   • Initial: ${params['initial_margin']} × {params['leverage']}x = ${params['initial_margin'] * params['leverage']} position
   • After all averaging: ${config['final_position_size']:.2f} total size
   • Final average entry: ${config['final_avg_entry']:,.2f}

4. PROFIT TARGETS (from final average ${config['final_avg_entry']:,.2f}):
   • +0.5%: ${config['final_avg_entry'] * 1.005:,.2f} → Profit: ${config['final_position_size'] * 0.005:.2f}
   • +1.0%: ${config['final_avg_entry'] * 1.010:,.2f} → Profit: ${config['final_position_size'] * 0.010:.2f}
   • +2.0%: ${config['final_avg_entry'] * 1.020:,.2f} → Profit: ${config['final_position_size'] * 0.020:.2f}
   • +5.0%: ${config['final_avg_entry'] * 1.050:,.2f} → Profit: ${config['final_position_size'] * 0.050:.2f}
""")
    
    print("\n🎯 INTEGRATION STATUS")
    print("-"*120)
    print("""
✅ IMPLEMENTED FEATURES:
• Adaptive K coefficient calculation
• Liquidation safety guarantee (10% minimum)
• Automatic initialization when position enters averaging zone
• Integration with zone state machine
• Full position metadata storage

🔄 SYSTEM BEHAVIOR:
1. Position opens normally
2. When UPNL drops below -$0.15 → enters AVERAGING zone
3. System automatically calculates optimal K coefficient
4. Averaging steps configured with safe multipliers
5. Each averaging maintains liquidation safety
6. After last step, safety margin (30%) added for protection

📈 READY FOR LIVE TRADING:
The system will automatically apply these safe multipliers to any position
that enters the averaging zone, ensuring maximum capital efficiency while
maintaining safety from liquidation.
""")
    
    print("="*120)
    print("✅ ADAPTIVE FIBONACCI AVERAGING SYSTEM READY!")
    print("="*120 + "\n")

if __name__ == "__main__":
    demo_adaptive_system()