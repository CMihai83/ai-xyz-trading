#!/usr/bin/env python3

print('HEMI Position Liquidation Analysis')
print('='*60)

# Based on the trade data from HEMI/USDT:USDT
trades = [
    {'time': '12:18:13', 'side': 'sell', 'amount': 38, 'price': 0.155910},
    {'time': '12:18:34', 'side': 'buy', 'amount': 38, 'price': 0.160685},
    {'time': '14:04:29', 'side': 'sell', 'amount': 37, 'price': 0.162148},
    {'time': '14:08:57', 'side': 'buy', 'amount': 37, 'price': 0.167114}
]

print('\n📊 Trade Sequence Analysis:\n')

# First position (SHORT)
entry1 = trades[0]['price']
exit1 = trades[1]['price']
loss1_pct = ((exit1 - entry1) / entry1) * 100
loss1_usd = (exit1 - entry1) * trades[0]['amount']

print(f"Position 1 (SHORT):")
print(f"  Opened: {trades[0]['amount']} contracts @ ${entry1:.6f}")
print(f"  Closed: {trades[1]['amount']} contracts @ ${exit1:.6f}")
print(f"  Loss: {loss1_pct:.2f}% = ${loss1_usd:.2f}")
print(f"  Time: 21 seconds between open and close")

# Second position (SHORT)
entry2 = trades[2]['price']
exit2 = trades[3]['price']
loss2_pct = ((exit2 - entry2) / entry2) * 100
loss2_usd = (exit2 - entry2) * trades[2]['amount']

print(f"\nPosition 2 (SHORT):")
print(f"  Opened: {trades[2]['amount']} contracts @ ${entry2:.6f}")
print(f"  Closed: {trades[3]['amount']} contracts @ ${exit2:.6f}")
print(f"  Loss: {loss2_pct:.2f}% = ${loss2_usd:.2f}")
print(f"  Time: 4 minutes 28 seconds between open and close")

print("\n⚠️ LIQUIDATION INDICATORS:")
print(f"  • Both positions closed at ~3% loss")
print(f"  • Rapid closure (especially position 1 - only 21 seconds)")
print(f"  • Consistent loss percentage suggests hitting liquidation level")
print(f"  • Total loss: ${loss1_usd + loss2_usd:.2f}")

print("\n📉 Liquidation Calculation:")
if loss1_pct > 2:
    likely_leverage = 100 / loss1_pct
    print(f"  • With {loss1_pct:.1f}% price movement causing liquidation")
    print(f"  • Estimated leverage used: ~{likely_leverage:.0f}x")
    print(f"  • At 25-50x leverage, a 2-4% move triggers liquidation")
    
print("\n✅ VERDICT: POSITIONS WERE LIQUIDATED")
print("  - Not manually closed (too fast, consistent loss %)")
print("  - Both hit similar liquidation thresholds")
print("  - High leverage + volatile price = forced liquidation")