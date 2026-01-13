#!/usr/bin/env python3
"""
Hedge Gateway Backtest - Per Symbol Analysis
Gate opens at averaging step 2/5, tracks peak, surplus dump or reversion close
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
SYMBOLS = [
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT',
    'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'LINK/USDT:USDT',
    'AVAX/USDT:USDT', 'MATIC/USDT:USDT', 'DOT/USDT:USDT',
    'ADA/USDT:USDT'
]
TIMEFRAME = '4h'
CANDLES = 500
LEVERAGE = 10
INITIAL_CAPITAL = 1000

# Averaging thresholds (main position UPNL %)
AVERAGING_STEPS = [-25, -50, -75, -100, -125]

# Gateway configuration
GATE_OPEN_STEPS = [2, 5]  # Gates open at step 2 and 5
GATE_BUFFER_PCT = 2.0     # 2% buffer for reversion detection
SURPLUS_DUMP_PCT = 0.85   # Close at 85% of peak profit
PARTIAL_CLOSE_AT_GATE = 0.30  # Close 30% when gate opens

# Exit rules
PROFIT_TARGET = 0.05  # +5% net P&L
STOP_LOSS = -0.15     # -15% net P&L


def fetch_data(exchange, symbol, timeframe, limit):
    """Fetch historical OHLCV data"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None


def calculate_upnl_pct(entry_price, current_price, direction, leverage):
    """Calculate UPNL percentage"""
    if direction == 'long':
        return ((current_price - entry_price) / entry_price) * leverage * 100
    else:
        return ((entry_price - current_price) / entry_price) * leverage * 100


class HedgeGateway:
    """Gateway mechanism for hedge management"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.is_open = False
        self.gate_level = 0  # Hedge profit when gate opened
        self.peak_profit = 0
        self.opened_at_step = 0
        self.partial_closed = False
        self.total_closed_pct = 0

    def open_gate(self, current_hedge_profit, step):
        """Open gate at averaging step"""
        self.is_open = True
        self.gate_level = current_hedge_profit
        self.peak_profit = current_hedge_profit
        self.opened_at_step = step
        self.partial_closed = False

    def update(self, current_hedge_profit):
        """Update peak tracking"""
        if self.is_open and current_hedge_profit > self.peak_profit:
            self.peak_profit = current_hedge_profit

    def should_surplus_dump(self, current_hedge_profit):
        """Check if should surplus dump (85% of peak)"""
        if not self.is_open or self.peak_profit <= 0:
            return False
        return current_hedge_profit <= self.peak_profit * SURPLUS_DUMP_PCT

    def should_reversion_close(self, current_hedge_profit):
        """Check if reverted back to gate level"""
        if not self.is_open:
            return False
        buffer = self.gate_level * (1 - GATE_BUFFER_PCT / 100)
        return current_hedge_profit <= buffer


def run_gateway_backtest(df, symbol):
    """Run backtest with gateway mechanism"""
    capital = INITIAL_CAPITAL
    position_size = capital * 0.1

    results = {
        'symbol': symbol,
        'trades': [],
        'gate_events': [],
        'final_capital': capital,
        'max_drawdown': 0,
        'peak_capital': capital,
        'total_trades': 0,
        'winning_trades': 0
    }

    # State
    in_position = False
    long_entry = 0
    short_entry = 0
    long_size = 0
    hedge_size = 0
    hedge_remaining = 1.0
    averaging_step = 0
    avg_long_entry = 0
    total_long_invested = 0
    gateway = HedgeGateway()
    trade_pnl = 0

    for i, row in df.iterrows():
        price = row['close']

        if not in_position:
            # Entry: Open LONG + HEDGE SHORT
            long_entry = price
            avg_long_entry = price
            short_entry = price
            long_size = position_size
            hedge_size = position_size
            hedge_remaining = 1.0
            total_long_invested = position_size
            in_position = True
            averaging_step = 0
            gateway.reset()
            continue

        # Calculate UPNL
        long_upnl_pct = calculate_upnl_pct(avg_long_entry, price, 'long', LEVERAGE)
        short_upnl_pct = calculate_upnl_pct(short_entry, price, 'short', LEVERAGE)

        hedge_profit_usd = (hedge_size * hedge_remaining) * (short_upnl_pct / 100)
        long_profit_usd = total_long_invested * (long_upnl_pct / 100)
        net_pnl_usd = long_profit_usd + hedge_profit_usd
        net_pnl_pct = net_pnl_usd / capital

        # Update gateway peak tracking
        gateway.update(hedge_profit_usd)

        # Check averaging triggers
        for step_idx, threshold in enumerate(AVERAGING_STEPS):
            if averaging_step <= step_idx and long_upnl_pct <= threshold:
                averaging_step = step_idx + 1

                # Add to LONG (average down)
                add_size = position_size * (1.0 + step_idx * 0.5)
                total_cost = avg_long_entry * long_size + price * add_size
                long_size += add_size
                total_long_invested += add_size
                avg_long_entry = total_cost / long_size

                # GATEWAY LOGIC: Open gate at step 2 or 5
                if averaging_step in GATE_OPEN_STEPS and not gateway.is_open and hedge_remaining > 0:
                    gateway.open_gate(hedge_profit_usd, averaging_step)
                    results['gate_events'].append({
                        'type': 'gate_open',
                        'step': averaging_step,
                        'hedge_profit': hedge_profit_usd,
                        'price': price
                    })

                    # Partial close at gate open (30%)
                    if PARTIAL_CLOSE_AT_GATE > 0:
                        close_amount = hedge_size * PARTIAL_CLOSE_AT_GATE * hedge_remaining
                        realized = close_amount * (short_upnl_pct / 100)
                        capital += realized
                        hedge_remaining -= PARTIAL_CLOSE_AT_GATE * hedge_remaining
                        gateway.total_closed_pct += PARTIAL_CLOSE_AT_GATE
                        results['trades'].append({
                            'type': 'gate_partial_close',
                            'step': averaging_step,
                            'pnl': realized,
                            'price': price
                        })

        # GATEWAY: Check surplus dump or reversion close
        if gateway.is_open and hedge_remaining > 0:
            current_hedge_profit = (hedge_size * hedge_remaining) * (short_upnl_pct / 100)

            # Check reversion first (immediate close)
            if gateway.should_reversion_close(current_hedge_profit):
                realized = current_hedge_profit
                capital += realized
                hedge_remaining = 0
                gateway.reset()
                results['gate_events'].append({
                    'type': 'reversion_close',
                    'pnl': realized,
                    'price': price
                })
                results['trades'].append({
                    'type': 'hedge_reversion_close',
                    'pnl': realized,
                    'reason': 'reverted_to_gate'
                })

            # Check surplus dump (85% of peak)
            elif gateway.should_surplus_dump(current_hedge_profit):
                realized = current_hedge_profit
                capital += realized
                hedge_remaining = 0
                gateway.reset()
                results['gate_events'].append({
                    'type': 'surplus_dump',
                    'peak': gateway.peak_profit,
                    'closed_at': realized,
                    'price': price
                })
                results['trades'].append({
                    'type': 'hedge_surplus_dump',
                    'pnl': realized,
                    'reason': '85%_of_peak'
                })

        # Exit conditions
        if net_pnl_pct >= PROFIT_TARGET or net_pnl_pct <= STOP_LOSS or i == len(df) - 1:
            # Close all
            final_pnl = net_pnl_usd
            capital += final_pnl
            trade_pnl = final_pnl

            results['total_trades'] += 1
            if final_pnl > 0:
                results['winning_trades'] += 1

            results['trades'].append({
                'type': 'position_exit',
                'reason': 'profit_target' if net_pnl_pct >= PROFIT_TARGET else
                         ('stop_loss' if net_pnl_pct <= STOP_LOSS else 'end'),
                'pnl': final_pnl,
                'avg_step': averaging_step
            })

            in_position = False
            gateway.reset()

        # Track drawdown
        results['peak_capital'] = max(results['peak_capital'], capital)
        drawdown = (results['peak_capital'] - capital) / results['peak_capital']
        results['max_drawdown'] = max(results['max_drawdown'], drawdown)

    results['final_capital'] = capital
    results['total_return'] = (capital - INITIAL_CAPITAL) / INITIAL_CAPITAL * 100
    results['win_rate'] = results['winning_trades'] / max(results['total_trades'], 1) * 100

    return results


def main():
    print("=" * 80)
    print("HEDGE GATEWAY BACKTEST - Per Symbol Analysis")
    print("Gate opens at averaging step 2/5 → Surplus dump (85%) or Reversion close")
    print("=" * 80)

    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })

    all_results = []

    print(f"\n{'Symbol':<18} {'Return':>10} {'MaxDD':>10} {'WinRate':>10} {'Gates':>8} {'Trades':>8}")
    print("-" * 80)

    for symbol in SYMBOLS:
        df = fetch_data(exchange, symbol, TIMEFRAME, CANDLES)
        if df is None or len(df) < 100:
            print(f"{symbol:<18} {'Error':<10}")
            continue

        results = run_gateway_backtest(df, symbol)
        all_results.append(results)

        gate_count = len([e for e in results['gate_events'] if e['type'] == 'gate_open'])

        print(f"{symbol:<18} {results['total_return']:>+9.2f}% {results['max_drawdown']*100:>9.2f}% "
              f"{results['win_rate']:>9.1f}% {gate_count:>8} {results['total_trades']:>8}")

    print("-" * 80)

    # Summary
    if all_results:
        avg_return = np.mean([r['total_return'] for r in all_results])
        avg_dd = np.mean([r['max_drawdown'] for r in all_results])
        avg_wr = np.mean([r['win_rate'] for r in all_results])
        total_gates = sum(len([e for e in r['gate_events'] if e['type'] == 'gate_open']) for r in all_results)

        print(f"{'AVERAGE':<18} {avg_return:>+9.2f}% {avg_dd*100:>9.2f}% {avg_wr:>9.1f}% {total_gates:>8}")
        print("=" * 80)

        # Gate event analysis
        print("\nGATE EVENT ANALYSIS:")
        reversion_closes = sum(len([e for e in r['gate_events'] if e['type'] == 'reversion_close']) for r in all_results)
        surplus_dumps = sum(len([e for e in r['gate_events'] if e['type'] == 'surplus_dump']) for r in all_results)
        print(f"  Reversion closes: {reversion_closes}")
        print(f"  Surplus dumps: {surplus_dumps}")
        print(f"  Total gate opens: {total_gates}")

        # Best/Worst performers
        best = max(all_results, key=lambda x: x['total_return'])
        worst = min(all_results, key=lambda x: x['total_return'])
        print(f"\n  Best:  {best['symbol']:<15} {best['total_return']:>+.2f}%")
        print(f"  Worst: {worst['symbol']:<15} {worst['total_return']:>+.2f}%")

        print("\n" + "=" * 80)

        if avg_return > 0:
            print("✅ GATEWAY STRATEGY PROFITABLE ON AVERAGE")
        else:
            print("⚠️ Strategy needs tuning")


if __name__ == "__main__":
    main()
