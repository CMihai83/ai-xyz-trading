#!/usr/bin/env python3
"""
Hedge Strategy Backtest - Averaging Step Triggered Closes
Tests: Close hedge at averaging step 2 (30%) and step 5 (70%)
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
SYMBOL = "BTC/USDT:USDT"
TIMEFRAME = "1h"
CANDLES = 720  # 30 days of hourly data
LEVERAGE = 10
INITIAL_CAPITAL = 1000  # USD

# Averaging thresholds (UPNL % triggers)
AVERAGING_STEPS = [-25, -50, -75, -100, -125]  # Steps 1-5

# Hedge close rules (Grok recommended)
HEDGE_CLOSE_STEP_2 = 0.30  # Close 30% at step 2 (-50% UPNL)
HEDGE_CLOSE_STEP_5 = 0.70  # Close remaining 70% at step 5 (-125% UPNL)

# Exit rules
PROFIT_TARGET = 0.05  # +5% net P&L
STOP_LOSS = -0.10     # -10% net P&L


def fetch_data(symbol, timeframe, limit):
    """Fetch historical OHLCV data"""
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })

    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    return df


def calculate_upnl_pct(entry_price, current_price, direction, leverage):
    """Calculate UPNL percentage"""
    if direction == 'long':
        return ((current_price - entry_price) / entry_price) * leverage * 100
    else:  # short
        return ((entry_price - current_price) / entry_price) * leverage * 100


def run_backtest(df, with_hedge=True):
    """Run backtest with or without hedge"""
    capital = INITIAL_CAPITAL
    position_size = capital * 0.1  # 10% per position

    results = {
        'trades': [],
        'final_capital': capital,
        'max_drawdown': 0,
        'peak_capital': capital
    }

    # State tracking
    in_position = False
    long_entry = 0
    short_entry = 0
    long_size = 0
    short_size = 0
    hedge_remaining = 1.0  # 100% of hedge
    averaging_step = 0
    avg_long_entry = 0
    total_long_invested = 0

    for i, row in df.iterrows():
        price = row['close']

        if not in_position:
            # Entry: Open LONG + HEDGE SHORT
            long_entry = price
            avg_long_entry = price
            long_size = position_size
            total_long_invested = position_size

            if with_hedge:
                short_entry = price
                short_size = position_size
                hedge_remaining = 1.0

            in_position = True
            averaging_step = 0
            continue

        # Calculate current UPNL
        long_upnl_pct = calculate_upnl_pct(avg_long_entry, price, 'long', LEVERAGE)

        if with_hedge and hedge_remaining > 0:
            short_upnl_pct = calculate_upnl_pct(short_entry, price, 'short', LEVERAGE)
            short_upnl_usd = (short_size * hedge_remaining) * (short_upnl_pct / 100)
        else:
            short_upnl_usd = 0

        long_upnl_usd = total_long_invested * (long_upnl_pct / 100)
        net_upnl_usd = long_upnl_usd + short_upnl_usd
        net_pnl_pct = net_upnl_usd / capital

        # Check averaging triggers
        for step_idx, threshold in enumerate(AVERAGING_STEPS):
            if averaging_step <= step_idx and long_upnl_pct <= threshold:
                averaging_step = step_idx + 1

                # Add to LONG position (average down)
                add_size = position_size * (1.0 + step_idx * 0.5)  # Fibonacci-like sizing
                total_long_invested += add_size

                # Update average entry
                total_cost = avg_long_entry * long_size + price * add_size
                long_size += add_size
                avg_long_entry = total_cost / long_size

                # HEDGE CLOSE LOGIC
                if with_hedge and hedge_remaining > 0:
                    if averaging_step == 2:  # Step 2: Close 30%
                        close_pct = HEDGE_CLOSE_STEP_2
                        realized_pnl = (short_size * close_pct) * (short_upnl_pct / 100)
                        capital += realized_pnl
                        hedge_remaining -= close_pct
                        results['trades'].append({
                            'type': 'hedge_partial_close',
                            'step': 2,
                            'pnl': realized_pnl,
                            'price': price
                        })

                    elif averaging_step == 5:  # Step 5: Close remaining
                        realized_pnl = (short_size * hedge_remaining) * (short_upnl_pct / 100)
                        capital += realized_pnl
                        hedge_remaining = 0
                        results['trades'].append({
                            'type': 'hedge_full_close',
                            'step': 5,
                            'pnl': realized_pnl,
                            'price': price
                        })

        # Check exit conditions
        if net_pnl_pct >= PROFIT_TARGET or net_pnl_pct <= STOP_LOSS or i == len(df) - 1:
            # Close all positions
            final_pnl = net_upnl_usd
            capital += final_pnl

            results['trades'].append({
                'type': 'exit',
                'reason': 'profit_target' if net_pnl_pct >= PROFIT_TARGET else ('stop_loss' if net_pnl_pct <= STOP_LOSS else 'end_of_data'),
                'pnl': final_pnl,
                'averaging_step': averaging_step
            })

            in_position = False

        # Track drawdown
        results['peak_capital'] = max(results['peak_capital'], capital)
        drawdown = (results['peak_capital'] - capital) / results['peak_capital']
        results['max_drawdown'] = max(results['max_drawdown'], drawdown)

    results['final_capital'] = capital
    results['total_return'] = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100

    return results


def main():
    print("=" * 60)
    print("HEDGE STRATEGY BACKTEST")
    print("Averaging Step Triggered Closes")
    print("=" * 60)

    print(f"\nFetching {CANDLES} candles of {SYMBOL} {TIMEFRAME} data...")
    df = fetch_data(SYMBOL, TIMEFRAME, CANDLES)
    print(f"Data range: {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")

    # Run with hedge
    print("\n--- WITH HEDGE (Step 2: 30%, Step 5: 70% close) ---")
    results_hedge = run_backtest(df, with_hedge=True)
    print(f"Final Capital: ${results_hedge['final_capital']:.2f}")
    print(f"Total Return: {results_hedge['total_return']:.2f}%")
    print(f"Max Drawdown: {results_hedge['max_drawdown']*100:.2f}%")
    print(f"Trades: {len(results_hedge['trades'])}")

    # Run without hedge
    print("\n--- WITHOUT HEDGE (baseline) ---")
    results_no_hedge = run_backtest(df, with_hedge=False)
    print(f"Final Capital: ${results_no_hedge['final_capital']:.2f}")
    print(f"Total Return: {results_no_hedge['total_return']:.2f}%")
    print(f"Max Drawdown: {results_no_hedge['max_drawdown']*100:.2f}%")
    print(f"Trades: {len(results_no_hedge['trades'])}")

    # Comparison
    print("\n--- COMPARISON ---")
    hedge_improvement = results_hedge['total_return'] - results_no_hedge['total_return']
    dd_improvement = results_no_hedge['max_drawdown'] - results_hedge['max_drawdown']
    print(f"Hedge vs No-Hedge Return: {hedge_improvement:+.2f}%")
    print(f"Drawdown Reduction: {dd_improvement*100:+.2f}%")

    if hedge_improvement > 0 and dd_improvement > 0:
        print("\n✅ HEDGE STRATEGY IMPROVES BOTH RETURN AND RISK")
    elif hedge_improvement > 0:
        print("\n⚠️ Hedge improves return but increases drawdown")
    elif dd_improvement > 0:
        print("\n⚠️ Hedge reduces risk but lowers return")
    else:
        print("\n❌ Hedge strategy underperforms baseline")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
