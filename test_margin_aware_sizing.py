#!/usr/bin/env python3
"""Test the margin-aware position sizing system"""

import sys
sys.path.append('/root/ai_xyz')

from margin_aware_position_sizer import MarginAwarePositionSizer

def test_current_positions():
    """Test sizing for current live positions"""

    sizer = MarginAwarePositionSizer()

    # Current account balance (estimated from previous logs)
    account_balance = 93.44

    # Test cases for current positions
    test_cases = [
        {'symbol': 'FOLKS/USDT', 'volatility': 72.8, 'current_price': 7.20},
        {'symbol': 'XPIN/USDT', 'volatility': 38.8, 'current_price': 0.0073},
        {'symbol': 'ANIME/USDT', 'volatility': 10.0, 'current_price': 0.0073},
        {'symbol': 'PIPPIN/USDT', 'volatility': 15.0, 'current_price': 0.4384},
        {'symbol': 'ICP/USDT', 'volatility': 8.0, 'current_price': 3.1780}
    ]

    print("🧮 MARGIN-AWARE POSITION SIZING ANALYSIS")
    print("=" * 50)

    for test_case in test_cases:
        print(f"\n📊 {test_case['symbol']} (Volatility: {test_case['volatility']}%)")
        print("-" * 40)

        # Get backtested optimal size
        optimal_size = sizer.get_backtested_optimal_size(
            symbol=test_case['symbol'],
            volatility_pct=test_case['volatility'],
            account_balance=account_balance
        )

        print(f"Initial Margin: ${optimal_size['initial_margin']:.4f}")
        print(f"Position Value: ${optimal_size['position_value']:.4f}")
        print(f"Max Safe Averaging Steps: {optimal_size['max_averaging_steps']}")
        print(f"Averaging Multipliers: {optimal_size['averaging_multipliers']}")
        print(f"Total Averaging Margin Needed: ${optimal_size['total_averaging_margin_needed']:.4f}")
        print(f"Volatility Factor: {optimal_size['volatility_factor']:.2f}")
        print(f"Risk Adjustment: {optimal_size['backtested_adjustments']['risk_adjustment']}")

        # Validate what would be safe for current position sizes
        # Estimate current position sizes
        current_size_estimate = 6.5  # Approximate current position value
        validation = sizer.validate_position_safety(
            position_value=current_size_estimate,
            leverage=8,
            account_balance=account_balance,
            volatility_pct=test_case['volatility']
        )

        print("\n🔍 SAFETY VALIDATION:")
        print(f"Safe Position: {'✅' if validation['is_safe'] else '❌'}")
        print(f"Margin Allocation: {validation['margin_allocation_pct']:.1%}")
        print(f"Max Averaging Steps: {validation['max_averaging_steps']}")
        print(f"Liquidation Distance: {validation['liquidation_distance_pct']:.1%}")
        print(f"Risk Level: {validation['risk_level']}")

        if validation['recommendations']:
            print("Recommendations:")
            for rec in validation['recommendations']:
                if rec:
                    print(f"  • {rec}")

def test_averaging_plan():
    """Test averaging plan calculation"""

    sizer = MarginAwarePositionSizer()

    print("\n🎯 AVERAGING PLAN EXAMPLES")
    print("=" * 50)

    # Test scenarios
    scenarios = [
        {
            'name': 'FOLKS High Volatility Loss',
            'entry_price': 7.20,
            'current_price': 6.77,  # -6% loss
            'current_pnl_pct': -6.0,
            'volatility_pct': 72.8,
            'available_margin': 5.0
        },
        {
            'name': 'XPIN Extreme Loss',
            'entry_price': 0.0073,
            'current_price': 0.0038,  # -48% loss
            'current_pnl_pct': -48.0,
            'volatility_pct': 38.8,
            'available_margin': 2.0
        },
        {
            'name': 'ICP Small Loss',
            'entry_price': 3.1780,
            'current_price': 3.1620,  # -0.5% loss
            'current_pnl_pct': -0.5,
            'volatility_pct': 8.0,
            'available_margin': 8.0
        }
    ]

    for scenario in scenarios:
        print(f"\n📈 {scenario['name']}")
        print("-" * 30)

        plan = sizer.calculate_averaging_plan(
            current_price=scenario['current_price'],
            entry_price=scenario['entry_price'],
            current_pnl_pct=scenario['current_pnl_pct'],
            volatility_pct=scenario['volatility_pct'],
            available_margin=scenario['available_margin']
        )

        print(f"Max Safe Averaging Steps: {plan['max_safe_averaging_steps']}")
        print(f"Step Multipliers: {plan['step_multipliers']}")
        print("Trigger Prices:")
        for i, price in enumerate(plan['trigger_prices'][:3]):  # Show first 3
            print(f"  Step {i+1}: ${price:.6f}")
        print(f"Remaining Margin: ${plan['remaining_margin']:.2f}")
        print(f"Liquidation Risk: {plan['liquidation_risk']}")
        print(f"Recommended Action: {plan['recommended_action']}")

if __name__ == "__main__":
    test_current_positions()
    test_averaging_plan()