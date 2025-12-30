#!/usr/bin/env python3
"""
Analyze why positions are hitting stop losses
"""

import json
import ccxt
from datetime import datetime

print("="*70)
print("STOP LOSS ANALYSIS")
print(f"Time: {datetime.now().isoformat()}")
print("="*70)

# Load current positions
with open('/app/position_state.json', 'r') as f:
    state = json.load(f)

print(f"\nActive positions: {len(state['active_positions'])}")
print("\nStop loss configuration:")
print("• Trigger: -10% loss (with leverage)")
print("• This means with 9x leverage:")
print("  - A -1.11% price move against = -10% loss")
print("  - A -2.22% price move against = -20% loss")

print("\n" + "="*70)
print("WHY POSITIONS HIT STOP LOSS")
print("="*70)

print("\n1. HIGH LEVERAGE AMPLIFICATION:")
print("   • System uses 8-9x leverage")
print("   • Small price moves cause large P&L swings")
print("   • -1.11% price move = -10% loss at 9x leverage")

print("\n2. VOLATILE MARKET CONDITIONS:")
print("   • Crypto markets can move 2-5% in minutes")
print("   • Meme coins can move 10-20% rapidly")
print("   • Weekend volatility often higher")

print("\n3. POSITION ENTRY TIMING:")
print("   • Positions may enter at local peaks/troughs")
print("   • No averaging has occurred yet (all at 0 steps)")
print("   • Single entry point vulnerable to reversals")

print("\n4. STOP LOSS CONFIGURATION:")
print("   • Current: -10% loss trigger")
print("   • With 9x leverage: Only -1.11% price buffer")
print("   • May be too tight for volatile assets")

print("\n" + "="*70)
print("RECOMMENDATIONS")
print("="*70)

print("\n1. ADJUST STOP LOSS FOR VOLATILITY:")
print("   • Consider -15% or -20% for high volatility")
print("   • Or use adaptive stop loss based on ATR")
print("   • Different thresholds for different asset classes")

print("\n2. LEVERAGE ADJUSTMENT:")
print("   • Reduce leverage for volatile assets (5-6x)")
print("   • Keep high leverage only for stable assets")
print("   • Dynamic leverage based on volatility")

print("\n3. ENTRY OPTIMIZATION:")
print("   • Wait for better entry signals")
print("   • Use limit orders instead of market")
print("   • Enter positions gradually")

print("\n4. USE AVERAGING BEFORE STOP:")
print("   • Let positions average down first")
print("   • Stop loss only after averaging attempts")
print("   • Give positions room to recover")

print("\n" + "="*70)
print("SUGGESTED CONFIGURATION CHANGES")
print("="*70)

print("\nOption 1: WIDER STOP LOSS")
print("```python")
print("self.zone_thresholds = {")
print("    'averaging': -0.15,")
print("    'profit_taking': 0.15,")
print("    'stop_loss': -3.0  # -300% (was -2.0)")
print("}")
print("")
print("# And in check_stop_loss:")
print("if pct < -20.0:  # -20% loss (was -10%)")
print("```")

print("\nOption 2: VOLATILITY-BASED STOP")
print("```python")
print("def get_adaptive_stop_loss(self, symbol):")
print("    volatility = self.calculate_historical_delta(symbol)")
print("    # More volatile = wider stop")
print("    if volatility > 0.5:  # High volatility")
print("        return -25.0  # -25% stop")
print("    elif volatility > 0.3:  # Medium")
print("        return -15.0  # -15% stop")
print("    else:  # Low volatility")
print("        return -10.0  # -10% stop")
print("```")

print("\nOption 3: AVERAGING PRIORITY")
print("```python")
print("# Only stop loss if averaging failed")
print("if self.averaging_steps[symbol] >= 2 and pct < -20.0:")
print("    # Stop loss only after 2+ averaging attempts")
print("```")

print("\n" + "="*70)
print("CURRENT ISSUE SUMMARY")
print("="*70)

print("\n❌ PROBLEM:")
print("• Stop loss triggers at -10% with 9x leverage")
print("• Only -1.11% price buffer before stop")
print("• Volatile crypto markets easily exceed this")
print("• Positions close at loss before averaging can help")

print("\n✅ SOLUTION:")
print("• Increase stop loss to -15% or -20%")
print("• Make it adaptive based on volatility")
print("• Prioritize averaging over stop loss")
print("• Adjust leverage based on asset volatility")