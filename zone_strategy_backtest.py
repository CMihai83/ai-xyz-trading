#!/usr/bin/env python3
"""
Zone-Based Trading Strategy Backtest
=====================================
Tests the current AI-XYZ zone-based position management:
- Neutral zone (-$0.15 to +$0.15)
- Averaging zone (<-25% UPNL)
- Profit taking zone (>+5% UPNL)
- Stop loss zone (<-90% UPNL)

With Fibonacci averaging simulation.

Created: January 15, 2026
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List
import ccxt
from dotenv import load_dotenv
import warnings
warnings.filterwarnings('ignore')

load_dotenv('/root/ai_xyz/.env')

from market_shift_predictor import MarketShiftPredictor, ShiftDirection


# Zone thresholds (from main system)
ZONE_THRESHOLDS = {
    'averaging': -0.25,      # -25% UPNL triggers averaging
    'profit_taking': 0.05,   # +5% UPNL enters surplus dump zone
    'stop_loss': -0.90       # -90% UPNL (safe for 15x leverage)
}

NEUTRAL_ZONE_USD = 0.15  # $0.15 minimum UPNL to exit neutral

# Fibonacci multipliers for averaging
FIBONACCI_MULTIPLIERS = [1.0, 1.618, 2.618, 4.236, 6.854]

# Position sizing
BASE_MARGIN = 0.70  # $0.70 initial position
TOTAL_CAPITAL_PER_POSITION = 5.00  # $5.00 total
LEVERAGE = 5


def get_exchange():
    """Initialize exchange connection"""
    return ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })


def fetch_ohlcv(exchange, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """Fetch historical OHLCV data"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None


class ZoneBasedPosition:
    """Simulates a zone-based position with Fibonacci averaging"""

    def __init__(self, symbol: str, side: str, entry_price: float):
        self.symbol = symbol
        self.side = side  # 'long' or 'short'
        self.entry_price = entry_price
        self.current_price = entry_price

        # Averaging state
        self.averaging_steps = 0
        self.max_steps = 5
        self.entries = [(entry_price, BASE_MARGIN)]  # [(price, margin)]
        self.total_margin = BASE_MARGIN

        # Peak tracking for profit taking
        self.peak_upnl = 0
        self.peak_upnl_pct = 0

        # State
        self.closed = False
        self.close_price = 0
        self.close_reason = ""

    @property
    def avg_entry(self) -> float:
        """Calculate weighted average entry price"""
        total_value = sum(price * margin for price, margin in self.entries)
        total_margin = sum(margin for _, margin in self.entries)
        return total_value / total_margin if total_margin > 0 else self.entry_price

    @property
    def position_size(self) -> float:
        """Position size in contracts (margin * leverage)"""
        return self.total_margin * LEVERAGE

    def calculate_upnl(self, current_price: float) -> float:
        """Calculate unrealized P&L in USD"""
        if self.side == 'long':
            pnl_pct = (current_price - self.avg_entry) / self.avg_entry
        else:
            pnl_pct = (self.avg_entry - current_price) / self.avg_entry

        return pnl_pct * self.position_size

    def calculate_upnl_pct(self, current_price: float) -> float:
        """Calculate unrealized P&L as percentage"""
        if self.side == 'long':
            return (current_price - self.avg_entry) / self.avg_entry * LEVERAGE
        else:
            return (self.avg_entry - current_price) / self.avg_entry * LEVERAGE

    def get_zone(self, current_price: float) -> str:
        """Determine current zone based on UPNL"""
        upnl = self.calculate_upnl(current_price)
        upnl_pct = self.calculate_upnl_pct(current_price)

        if upnl_pct <= ZONE_THRESHOLDS['stop_loss']:
            return 'STOP_LOSS'
        elif upnl_pct <= ZONE_THRESHOLDS['averaging']:
            return 'AVERAGING'
        elif abs(upnl) < NEUTRAL_ZONE_USD:
            return 'NEUTRAL'
        elif upnl_pct >= ZONE_THRESHOLDS['profit_taking']:
            return 'PROFIT_TAKING'
        else:
            return 'NEUTRAL'

    def add_averaging(self, current_price: float) -> bool:
        """Add averaging step if possible"""
        if self.averaging_steps >= self.max_steps:
            return False

        self.averaging_steps += 1
        fib_mult = FIBONACCI_MULTIPLIERS[min(self.averaging_steps, len(FIBONACCI_MULTIPLIERS) - 1)]

        # Simplified: add proportional margin
        add_margin = BASE_MARGIN * fib_mult * 0.2  # 20% of fib multiplier
        self.entries.append((current_price, add_margin))
        self.total_margin += add_margin

        return True

    def update(self, current_price: float) -> str:
        """Update position and return action taken"""
        self.current_price = current_price
        upnl = self.calculate_upnl(current_price)
        upnl_pct = self.calculate_upnl_pct(current_price)

        # Track peak
        if upnl > self.peak_upnl:
            self.peak_upnl = upnl
            self.peak_upnl_pct = upnl_pct

        zone = self.get_zone(current_price)

        if zone == 'STOP_LOSS':
            self.close(current_price, 'stop_loss')
            return 'CLOSED_STOP_LOSS'

        elif zone == 'AVERAGING':
            if self.add_averaging(current_price):
                return f'AVERAGED_STEP_{self.averaging_steps}'
            return 'HOLD_MAX_AVERAGED'

        elif zone == 'PROFIT_TAKING':
            # Surplus dump logic
            if self.peak_upnl > 0 and upnl < self.peak_upnl * 0.85:
                self.close(current_price, 'surplus_dump')
                return 'CLOSED_SURPLUS_DUMP'
            return 'HOLD_PROFIT'

        return 'HOLD_NEUTRAL'

    def close(self, price: float, reason: str):
        """Close position"""
        self.closed = True
        self.close_price = price
        self.close_reason = reason

    def get_final_pnl(self) -> float:
        """Get final P&L for closed position"""
        if not self.closed:
            return self.calculate_upnl(self.current_price)
        return self.calculate_upnl(self.close_price)


def run_zone_strategy_backtest(symbol: str, ohlcv: pd.DataFrame, predictor: MarketShiftPredictor) -> Dict:
    """Run zone-based strategy backtest on single asset"""

    positions = []
    active_position = None
    lookback = 100

    for i in range(lookback, len(ohlcv)):
        current_bar = ohlcv.iloc[i]
        current_price = current_bar['close']
        low = current_bar['low']
        high = current_bar['high']

        # Manage active position
        if active_position:
            # Check stop loss on low/high
            if active_position.side == 'long':
                action = active_position.update(low)  # Check worst case
            else:
                action = active_position.update(high)

            if active_position.closed:
                positions.append(active_position)
                active_position = None

        # Entry logic using market shift predictor
        if active_position is None:
            window = ohlcv.iloc[i-lookback:i].copy()
            prediction = predictor.predict(window)

            if prediction.direction != ShiftDirection.NEUTRAL and prediction.confidence > 0.5:
                side = 'long' if prediction.direction == ShiftDirection.BULLISH else 'short'
                active_position = ZoneBasedPosition(symbol, side, current_price)

    # Close any remaining position
    if active_position:
        active_position.close(ohlcv.iloc[-1]['close'], 'end_of_backtest')
        positions.append(active_position)

    # Calculate statistics
    if not positions:
        return {'total_trades': 0, 'message': 'No trades'}

    total_pnl = sum(p.get_final_pnl() for p in positions)
    wins = [p for p in positions if p.get_final_pnl() > 0]
    losses = [p for p in positions if p.get_final_pnl() <= 0]

    # Analyze close reasons
    close_reasons = {}
    for p in positions:
        r = p.close_reason
        close_reasons[r] = close_reasons.get(r, 0) + 1

    # Analyze averaging effectiveness
    avg_steps_on_wins = np.mean([p.averaging_steps for p in wins]) if wins else 0
    avg_steps_on_losses = np.mean([p.averaging_steps for p in losses]) if losses else 0

    return {
        'symbol': symbol,
        'total_trades': len(positions),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(positions) if positions else 0,
        'total_pnl': total_pnl,
        'avg_pnl': total_pnl / len(positions) if positions else 0,
        'close_reasons': close_reasons,
        'avg_steps_on_wins': avg_steps_on_wins,
        'avg_steps_on_losses': avg_steps_on_losses,
        'positions': positions
    }


def main():
    print("=" * 70)
    print("ZONE-BASED TRADING STRATEGY BACKTEST")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nZone Thresholds:")
    print(f"  Averaging: <{ZONE_THRESHOLDS['averaging']*100:.0f}% UPNL")
    print(f"  Profit Taking: >{ZONE_THRESHOLDS['profit_taking']*100:.0f}% UPNL")
    print(f"  Stop Loss: <{ZONE_THRESHOLDS['stop_loss']*100:.0f}% UPNL")
    print(f"\nPosition Sizing:")
    print(f"  Base Margin: ${BASE_MARGIN}")
    print(f"  Leverage: {LEVERAGE}x")
    print()

    exchange = get_exchange()
    exchange.load_markets()
    predictor = MarketShiftPredictor()

    test_symbols = [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT',
        'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'AVAX/USDT:USDT',
        'LINK/USDT:USDT', 'WIF/USDT:USDT', 'ARB/USDT:USDT'
    ]

    all_results = []

    for tf in ['1h', '4h']:
        print(f"\n{'='*60}")
        print(f"TIMEFRAME: {tf}")
        print(f"{'='*60}")

        for symbol in test_symbols:
            ohlcv = fetch_ohlcv(exchange, symbol, tf, limit=600)

            if ohlcv is None or len(ohlcv) < 200:
                print(f"  {symbol}: Insufficient data")
                continue

            result = run_zone_strategy_backtest(symbol, ohlcv, predictor)
            result['timeframe'] = tf
            all_results.append(result)

            base = symbol.split('/')[0]
            print(f"  {base:6} | Trades: {result['total_trades']:3} | " +
                  f"Win: {result['win_rate']:.0%} | " +
                  f"PnL: ${result['total_pnl']:+.2f} | " +
                  f"AvgSteps W/L: {result['avg_steps_on_wins']:.1f}/{result['avg_steps_on_losses']:.1f}")

    # Summary analysis
    print("\n" + "=" * 70)
    print("SUMMARY ANALYSIS")
    print("=" * 70)

    if not all_results:
        print("No results to analyze!")
        return

    # Convert to DataFrame for analysis
    df = pd.DataFrame([{
        'symbol': r['symbol'],
        'timeframe': r['timeframe'],
        'trades': r['total_trades'],
        'wins': r['wins'],
        'losses': r['losses'],
        'win_rate': r['win_rate'],
        'pnl': r['total_pnl'],
        'avg_steps_wins': r['avg_steps_on_wins'],
        'avg_steps_losses': r['avg_steps_on_losses']
    } for r in all_results if r['total_trades'] > 0])

    if len(df) == 0:
        print("No trades executed!")
        return

    print("\n1. BY TIMEFRAME:")
    print("-" * 40)
    tf_summary = df.groupby('timeframe').agg({
        'trades': 'sum',
        'wins': 'sum',
        'losses': 'sum',
        'pnl': 'sum'
    })
    tf_summary['win_rate'] = tf_summary['wins'] / (tf_summary['wins'] + tf_summary['losses'])
    print(tf_summary.to_string())

    print("\n2. BY SYMBOL:")
    print("-" * 40)
    sym_summary = df.groupby('symbol').agg({
        'trades': 'sum',
        'pnl': 'sum',
        'win_rate': 'mean'
    }).sort_values('pnl', ascending=False)
    print(sym_summary.to_string())

    print("\n3. AVERAGING ANALYSIS:")
    print("-" * 40)
    print(f"Avg Steps on Wins: {df['avg_steps_wins'].mean():.2f}")
    print(f"Avg Steps on Losses: {df['avg_steps_losses'].mean():.2f}")

    # Close reason analysis
    all_reasons = {}
    for r in all_results:
        for reason, count in r.get('close_reasons', {}).items():
            all_reasons[reason] = all_reasons.get(reason, 0) + count

    print("\n4. CLOSE REASONS:")
    print("-" * 40)
    for reason, count in sorted(all_reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")

    print("\n5. KEY FINDINGS:")
    print("-" * 40)

    best_tf = tf_summary['pnl'].idxmax() if not tf_summary.empty else 'N/A'
    print(f"  Best Timeframe: {best_tf}")

    best_symbol = sym_summary['pnl'].idxmax() if not sym_summary.empty else 'N/A'
    print(f"  Best Symbol: {best_symbol.split('/')[0] if '/' in best_symbol else best_symbol}")

    total_pnl = df['pnl'].sum()
    print(f"  Total P&L: ${total_pnl:+.2f}")
    print(f"  Total Trades: {df['trades'].sum()}")
    print(f"  Overall Win Rate: {df['wins'].sum() / (df['wins'].sum() + df['losses'].sum()):.1%}")

    print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
