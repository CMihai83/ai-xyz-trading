#!/usr/bin/env python3
"""
Test script for liquidation protection price calculations

Demonstrates liquidation price calculation for current positions
Shows where limit orders would be placed to prevent liquidation

Author: AI-XYZ Trading System
Date: 2026-01-03
"""

import json
from liquidation_protection_service import LiquidationProtectionService


def test_liquidation_calculations():
    """
    Test liquidation price calculations with current positions
    """
    print("=" * 80)
    print("LIQUIDATION PROTECTION - PRICE CALCULATION TEST")
    print("=" * 80)
    print()

    # Load current positions from state file
    with open('/root/ai_xyz/position_state.json', 'r') as f:
        state = json.load(f)

    positions = state['active_positions']
    averaging_steps = state['averaging_steps']

    # Initialize service (without exchange for testing)
    service = LiquidationProtectionService(exchange=None)

    print("📊 CURRENT POSITIONS:")
    print("-" * 80)

    for symbol, pos in positions.items():
        entry_price = pos['entry_price']
        amount = pos['amount']
        side = pos['side']
        leverage = pos.get('leverage', 10.0)
        avg_step = averaging_steps.get(symbol, 0)

        print(f"\n{symbol}:")
        print(f"  Entry Price (weighted avg): ${entry_price:.6f}")
        print(f"  Position Size: {amount:,.0f} contracts")
        print(f"  Side: {side.upper()}")
        print(f"  Leverage: {leverage}x")
        print(f"  Averaging Step: {avg_step}")

        # Calculate liquidation prices at different UPNL levels
        upnl_levels = [-75.0, -80.0, -82.5, -85.0, -90.0]

        print(f"\n  📊 Liquidation Prices at Different UPNL Levels:")
        print(f"  {'UPNL %':<10} {'Price':<12} {'Change from Entry':<20} {'Notes':<30}")
        print(f"  {'-'*10} {'-'*12} {'-'*20} {'-'*30}")

        for upnl_pct in upnl_levels:
            liq_price = service.calculate_liquidation_price(
                entry_price, side, leverage, upnl_pct
            )

            if side == 'buy':
                price_change_pct = ((liq_price - entry_price) / entry_price) * 100
            else:
                price_change_pct = ((entry_price - liq_price) / entry_price) * 100

            # Add notes based on UPNL level
            if upnl_pct == -82.5:
                notes = "← PROTECTION ORDER HERE"
            elif upnl_pct == -90.0:
                notes = "Exchange liquidation zone"
            elif upnl_pct == -75.0:
                notes = "Last averaging step cap"
            else:
                notes = ""

            print(f"  {upnl_pct:>6.1f}%   ${liq_price:<10.6f}  {price_change_pct:>6.2f}%             {notes}")

        # Calculate contracts and new position after protection
        protection_margin = 25.0
        protection_price = service.calculate_liquidation_price(
            entry_price, side, leverage, -82.5
        )
        protection_contracts = (protection_margin * leverage) / protection_price

        # Calculate new weighted average after protection fills
        total_contracts = amount + protection_contracts
        new_weighted_avg = (
            (entry_price * amount + protection_price * protection_contracts)
            / total_contracts
        )

        if side == 'buy':
            improvement_pct = ((entry_price - new_weighted_avg) / entry_price) * 100
        else:
            improvement_pct = ((new_weighted_avg - entry_price) / entry_price) * 100

        print(f"\n  💰 Protection Order Impact:")
        print(f"     Additional margin: ${protection_margin:.2f}")
        print(f"     Contracts to add: {protection_contracts:,.0f}")
        print(f"     New total size: {total_contracts:,.0f} contracts")
        print(f"     New weighted avg (after fill): ${new_weighted_avg:.6f}")
        print(f"     Entry improvement: {improvement_pct:.2f}%")

        # Calculate UPNL at new weighted average if price stays at protection level
        if side == 'buy':
            new_upnl_pct = ((protection_price - new_weighted_avg) / new_weighted_avg) * leverage * 100
        else:
            new_upnl_pct = ((new_weighted_avg - protection_price) / new_weighted_avg) * leverage * 100

        print(f"     UPNL after protection fills: {new_upnl_pct:.1f}%")
        print(f"     Margin at that point: ${protection_price * total_contracts / leverage:.2f}")

        # Determine if this position would qualify for protection
        if avg_step >= 5:
            print(f"\n  ✅ Position qualifies for liquidation protection (step {avg_step} >= 5)")
        else:
            print(f"\n  ⏳ Not ready yet (step {avg_step} < 5, needs {5 - avg_step} more steps)")

        print(f"\n  {'-'*80}")

    print("\n" + "=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


def test_edge_cases():
    """
    Test edge cases and different leverage levels
    """
    print("\n\n" + "=" * 80)
    print("EDGE CASE TESTING")
    print("=" * 80)

    service = LiquidationProtectionService(exchange=None)

    test_cases = [
        {
            'name': 'BTC at 5x leverage',
            'entry': 50000.0,
            'side': 'buy',
            'leverage': 5.0
        },
        {
            'name': 'ETH SHORT at 10x leverage',
            'entry': 3000.0,
            'side': 'sell',
            'leverage': 10.0
        },
        {
            'name': 'Altcoin at 20x leverage (risky)',
            'entry': 1.0,
            'side': 'buy',
            'leverage': 20.0
        }
    ]

    for case in test_cases:
        print(f"\n{case['name']}:")
        print(f"  Entry: ${case['entry']:.2f}")
        print(f"  Side: {case['side'].upper()}")
        print(f"  Leverage: {case['leverage']}x")

        liq_price = service.calculate_liquidation_price(
            case['entry'], case['side'], case['leverage'], -82.5
        )

        if case['side'] == 'buy':
            price_change_pct = ((liq_price - case['entry']) / case['entry']) * 100
        else:
            price_change_pct = ((case['entry'] - liq_price) / case['entry']) * 100

        print(f"  Liquidation protection price: ${liq_price:.6f}")
        print(f"  Price change required: {price_change_pct:.2f}%")
        print(f"  UPNL at that price: -82.5%")


if __name__ == '__main__':
    test_liquidation_calculations()
    test_edge_cases()

    print("\n\n💡 KEY INSIGHTS:")
    print("=" * 80)
    print("1. Protection orders placed at -82.5% UPNL (before exchange liquidation ~-90%)")
    print("2. Uses additional $25 margin per position (limit orders, not market)")
    print("3. Improves weighted average entry when filled")
    print("4. Only triggers after averaging step 5+ (last steps)")
    print("5. Provides final safety net before liquidation")
    print("=" * 80)
