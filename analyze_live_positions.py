#!/usr/bin/env python3
"""Analyze live positions and determine their lifecycle stage"""
import ccxt
import os
from dotenv import load_dotenv

load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

def analyze_live_positions():
    try:
        positions = exchange.fetch_positions()
        print("🔍 LIVE POSITION ANALYSIS - LIFECYCLE STAGES\n")

        losing_positions = []
        profitable_positions = []

        for pos in positions:
            if pos['contracts'] > 0:
                symbol = pos['symbol']
                side = 'LONG' if pos['side'] == 'long' else 'SHORT'
                pnl_pct = pos['percentage']
                pnl = pos['unrealizedPnl']
                amount = pos['contracts']
                entry_price = pos.get('averagePrice', 'N/A')

                print(f"📊 {symbol}:")
                print(f"   Side: {side}")
                print(f"   P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
                print(f"   Amount: {amount}")
                print(f"   Entry: ${entry_price}")

                # Determine lifecycle stage based on P&L
                if pnl_pct < -0.05:  # Losing >5%
                    stage = "🔴 AVERAGING ZONE - Should trigger averaging down"
                    losing_positions.append((symbol, pnl_pct))
                elif pnl_pct > 0.15:  # Profitable >15%
                    stage = "🟢 SURPLUS DUMP ZONE - Should trigger profit taking"
                    profitable_positions.append((symbol, pnl_pct))
                elif pnl_pct > 0:  # Slightly profitable
                    stage = "🟡 PROFIT TAKING ZONE - Monitor for surplus dump"
                else:  # Neutral
                    stage = "⚪ NEUTRAL ZONE - Stable position"

                print(f"   Stage: {stage}")
                print()

        print("🎯 SYSTEM RECOMMENDATIONS:")
        print(f"   Positions needing averaging: {len(losing_positions)}")
        for symbol, pnl in losing_positions:
            print(f"     - {symbol}: {pnl:.1f}% loss → Fibonacci averaging")

        print(f"   Positions ready for surplus dump: {len(profitable_positions)}")
        for symbol, pnl in profitable_positions:
            print(f"     - {symbol}: {pnl:.1f}% profit → Profit taking")

        if not losing_positions and not profitable_positions:
            print("   📈 All positions in neutral zone - system monitoring")

    except Exception as e:
        print(f"❌ Error analyzing positions: {e}")

if __name__ == "__main__":
    analyze_live_positions()