#!/usr/bin/env python3
"""
Profit Protection Hedge Backtest
================================
Backtests the profit protection hedge strategy vs traditional close-at-70%

Strategy Comparison:
1. TRADITIONAL: Close position when UPNL drops to 70% of peak
2. PROFIT HEDGE: Open 50% hedge at 70% of peak, keep main open

Hedge Gates:
- 10% profit on hedge → close hedge
- Main drops to 50% of peak → close hedge
- -5% stop loss on hedge → close hedge

Author: Claude + Grok Consortium
Version: 1.0.0
Date: January 14, 2026
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import ccxt
from dotenv import load_dotenv

load_dotenv()


class Strategy(Enum):
    TRADITIONAL = "traditional"  # Close at 70% of peak
    PROFIT_HEDGE = "profit_hedge"  # Open hedge at 70% of peak


@dataclass
class Position:
    """Represents a trading position"""
    symbol: str
    side: str  # 'long' or 'short'
    entry_price: float
    size: float
    leverage: int
    opened_at: datetime
    peak_upnl: float = 0.0
    hedge_opened: bool = False
    hedge_entry_price: float = 0.0
    hedge_size: float = 0.0
    closed: bool = False
    close_price: float = 0.0
    close_reason: str = ""
    realized_pnl: float = 0.0
    hedge_pnl: float = 0.0


@dataclass
class BacktestResult:
    """Results from a backtest run"""
    strategy: Strategy
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_hedge_pnl: float = 0.0
    avg_profit_captured: float = 0.0  # % of peak captured
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    trades: List[Dict] = field(default_factory=list)

    @property
    def win_rate(self) -> float:
        return self.winning_trades / max(1, self.total_trades)

    @property
    def combined_pnl(self) -> float:
        return self.total_pnl + self.total_hedge_pnl


class ProfitProtectionHedgeBacktest:
    """
    Backtests profit protection hedge strategy
    """

    # Configuration (matching hedge_gateway.py)
    PROFIT_PROTECTION_HEDGE_SIZE = 0.50  # 50% of main position
    PROFIT_HEDGE_PROFIT_GATE = 0.10      # 10% profit closes hedge
    PROFIT_HEDGE_MAIN_DROP_GATE = 0.50   # Main at 50% of peak closes hedge
    PROFIT_HEDGE_STOP_LOSS = -0.05       # -5% stop loss on hedge
    MIN_PROFIT_FOR_HEDGE = 5.00          # $5 minimum UPNL
    TAKE_PROFIT_TRIGGER = 0.70           # 70% of peak triggers action

    def __init__(self, leverage: int = 10, position_size_usd: float = 10.0):
        self.leverage = leverage
        self.position_size_usd = position_size_usd
        self.exchange = self._init_exchange()

    def _init_exchange(self):
        """Initialize exchange connection"""
        return ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {'defaultType': 'swap'}
        })

    def fetch_historical_data(self, symbol: str, timeframe: str = '5m',
                              days: int = 30) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data"""
        try:
            tf_minutes = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440}
            minutes = tf_minutes.get(timeframe, 5)
            limit = min(1000, int(days * 24 * 60 / minutes))

            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"  ❌ Failed to fetch data for {symbol}: {e}")
            return None

    def calculate_upnl(self, entry_price: float, current_price: float,
                       size: float, side: str) -> Tuple[float, float]:
        """Calculate UPNL and percentage"""
        if side == 'long':
            pnl_pct = (current_price - entry_price) / entry_price
        else:
            pnl_pct = (entry_price - current_price) / entry_price

        upnl = size * entry_price * pnl_pct * self.leverage / entry_price
        upnl_usd = upnl * current_price if side == 'long' else upnl * entry_price

        # Simplified: margin * pnl_pct * leverage
        margin = (size * entry_price) / self.leverage
        upnl_usd = margin * pnl_pct * self.leverage

        return upnl_usd, pnl_pct * 100

    def simulate_trade(self, df: pd.DataFrame, entry_idx: int, side: str,
                       strategy: Strategy) -> Optional[Dict]:
        """
        Simulate a single trade from entry to exit

        Returns trade result dictionary
        """
        entry_price = df.iloc[entry_idx]['close']
        entry_time = df.iloc[entry_idx]['timestamp']

        # Calculate position size
        margin = self.position_size_usd
        size = (margin * self.leverage) / entry_price

        # Track position state
        peak_upnl = 0.0
        peak_price = entry_price
        hedge_opened = False
        hedge_entry_price = 0.0
        hedge_size = 0.0
        hedge_peak_pnl = 0.0

        # Simulate price movement
        for i in range(entry_idx + 1, len(df)):
            current_price = df.iloc[i]['close']
            current_time = df.iloc[i]['timestamp']

            # Calculate main position UPNL
            main_upnl, main_pct = self.calculate_upnl(entry_price, current_price, size, side)

            # Update peak
            if main_upnl > peak_upnl:
                peak_upnl = main_upnl
                peak_price = current_price

            # Calculate hedge UPNL if open
            hedge_upnl = 0.0
            hedge_pct = 0.0
            if hedge_opened:
                hedge_side = 'short' if side == 'long' else 'long'
                hedge_upnl, hedge_pct = self.calculate_upnl(
                    hedge_entry_price, current_price, hedge_size, hedge_side
                )
                if hedge_upnl > hedge_peak_pnl:
                    hedge_peak_pnl = hedge_upnl

            # Check exit conditions based on strategy
            if strategy == Strategy.TRADITIONAL:
                # Traditional: Close at 70% of peak
                if peak_upnl >= self.MIN_PROFIT_FOR_HEDGE:
                    if main_upnl <= peak_upnl * self.TAKE_PROFIT_TRIGGER:
                        return {
                            'strategy': strategy.value,
                            'symbol': df.attrs.get('symbol', 'UNKNOWN'),
                            'side': side,
                            'entry_price': entry_price,
                            'entry_time': str(entry_time),
                            'exit_price': current_price,
                            'exit_time': str(current_time),
                            'exit_reason': 'take_profit_70pct',
                            'peak_upnl': peak_upnl,
                            'realized_pnl': main_upnl,
                            'hedge_pnl': 0.0,
                            'profit_captured_pct': (main_upnl / peak_upnl * 100) if peak_upnl > 0 else 0,
                            'duration_candles': i - entry_idx
                        }

            elif strategy == Strategy.PROFIT_HEDGE:
                # Profit Hedge: Open hedge at 70% of peak
                if peak_upnl >= self.MIN_PROFIT_FOR_HEDGE:
                    if not hedge_opened and main_upnl <= peak_upnl * self.TAKE_PROFIT_TRIGGER:
                        # Open hedge
                        hedge_opened = True
                        hedge_entry_price = current_price
                        hedge_size = size * self.PROFIT_PROTECTION_HEDGE_SIZE
                        hedge_peak_pnl = 0.0

                    if hedge_opened:
                        # Check hedge gates
                        hedge_margin = (hedge_size * hedge_entry_price) / self.leverage
                        hedge_pnl_pct = hedge_upnl / hedge_margin if hedge_margin > 0 else 0

                        # Gate 1: 10% profit on hedge
                        if hedge_pnl_pct >= self.PROFIT_HEDGE_PROFIT_GATE:
                            return {
                                'strategy': strategy.value,
                                'symbol': df.attrs.get('symbol', 'UNKNOWN'),
                                'side': side,
                                'entry_price': entry_price,
                                'entry_time': str(entry_time),
                                'exit_price': current_price,
                                'exit_time': str(current_time),
                                'exit_reason': 'hedge_profit_10pct',
                                'peak_upnl': peak_upnl,
                                'realized_pnl': main_upnl,
                                'hedge_pnl': hedge_upnl,
                                'profit_captured_pct': ((main_upnl + hedge_upnl) / peak_upnl * 100) if peak_upnl > 0 else 0,
                                'duration_candles': i - entry_idx
                            }

                        # Gate 2: Main drops to 50% of peak
                        if peak_upnl > 0 and main_upnl <= peak_upnl * self.PROFIT_HEDGE_MAIN_DROP_GATE:
                            return {
                                'strategy': strategy.value,
                                'symbol': df.attrs.get('symbol', 'UNKNOWN'),
                                'side': side,
                                'entry_price': entry_price,
                                'entry_time': str(entry_time),
                                'exit_price': current_price,
                                'exit_time': str(current_time),
                                'exit_reason': 'main_dropped_50pct',
                                'peak_upnl': peak_upnl,
                                'realized_pnl': main_upnl,
                                'hedge_pnl': hedge_upnl,
                                'profit_captured_pct': ((main_upnl + hedge_upnl) / peak_upnl * 100) if peak_upnl > 0 else 0,
                                'duration_candles': i - entry_idx
                            }

                        # Gate 3: -5% stop loss on hedge
                        if hedge_pnl_pct <= self.PROFIT_HEDGE_STOP_LOSS:
                            return {
                                'strategy': strategy.value,
                                'symbol': df.attrs.get('symbol', 'UNKNOWN'),
                                'side': side,
                                'entry_price': entry_price,
                                'entry_time': str(entry_time),
                                'exit_price': current_price,
                                'exit_time': str(current_time),
                                'exit_reason': 'hedge_stop_loss',
                                'peak_upnl': peak_upnl,
                                'realized_pnl': main_upnl,
                                'hedge_pnl': hedge_upnl,
                                'profit_captured_pct': ((main_upnl + hedge_upnl) / peak_upnl * 100) if peak_upnl > 0 else 0,
                                'duration_candles': i - entry_idx
                            }

            # Stop loss for both strategies
            if main_pct <= -90:
                return {
                    'strategy': strategy.value,
                    'symbol': df.attrs.get('symbol', 'UNKNOWN'),
                    'side': side,
                    'entry_price': entry_price,
                    'entry_time': str(entry_time),
                    'exit_price': current_price,
                    'exit_time': str(current_time),
                    'exit_reason': 'stop_loss',
                    'peak_upnl': peak_upnl,
                    'realized_pnl': main_upnl,
                    'hedge_pnl': hedge_upnl if hedge_opened else 0,
                    'profit_captured_pct': 0,
                    'duration_candles': i - entry_idx
                }

        # End of data - close at last price
        current_price = df.iloc[-1]['close']
        main_upnl, _ = self.calculate_upnl(entry_price, current_price, size, side)
        hedge_upnl = 0.0
        if hedge_opened:
            hedge_side = 'short' if side == 'long' else 'long'
            hedge_upnl, _ = self.calculate_upnl(hedge_entry_price, current_price, hedge_size, hedge_side)

        return {
            'strategy': strategy.value,
            'symbol': df.attrs.get('symbol', 'UNKNOWN'),
            'side': side,
            'entry_price': entry_price,
            'entry_time': str(entry_time),
            'exit_price': current_price,
            'exit_time': str(df.iloc[-1]['timestamp']),
            'exit_reason': 'end_of_data',
            'peak_upnl': peak_upnl,
            'realized_pnl': main_upnl,
            'hedge_pnl': hedge_upnl,
            'profit_captured_pct': ((main_upnl + hedge_upnl) / peak_upnl * 100) if peak_upnl > 0 else 0,
            'duration_candles': len(df) - entry_idx - 1
        }

    def run_backtest(self, symbol: str, timeframe: str = '5m', days: int = 30,
                     num_trades: int = 50) -> Tuple[BacktestResult, BacktestResult]:
        """
        Run backtest comparing both strategies

        Returns (traditional_result, profit_hedge_result)
        """
        print(f"\n{'='*60}")
        print(f"PROFIT PROTECTION HEDGE BACKTEST")
        print(f"{'='*60}")
        print(f"Symbol: {symbol}")
        print(f"Timeframe: {timeframe}")
        print(f"Days: {days}")
        print(f"Trades per strategy: {num_trades}")
        print(f"{'='*60}\n")

        # Fetch data
        print(f"📊 Fetching historical data...")
        df = self.fetch_historical_data(symbol, timeframe, days)
        if df is None or len(df) < 100:
            print(f"  ❌ Insufficient data")
            return BacktestResult(Strategy.TRADITIONAL), BacktestResult(Strategy.PROFIT_HEDGE)

        df.attrs['symbol'] = symbol
        print(f"  ✅ Loaded {len(df)} candles")

        # Generate random entry points
        np.random.seed(42)  # Reproducible results
        max_entry = len(df) - 100  # Leave room for trade duration
        entry_indices = np.random.choice(range(50, max_entry), size=num_trades, replace=False)
        entry_indices = sorted(entry_indices)

        # Alternate between long and short
        sides = ['long' if i % 2 == 0 else 'short' for i in range(num_trades)]

        # Run both strategies
        traditional_result = BacktestResult(Strategy.TRADITIONAL)
        profit_hedge_result = BacktestResult(Strategy.PROFIT_HEDGE)

        print(f"\n🔄 Running {num_trades} trades for each strategy...\n")

        for i, (entry_idx, side) in enumerate(zip(entry_indices, sides)):
            # Traditional strategy
            trade_trad = self.simulate_trade(df, entry_idx, side, Strategy.TRADITIONAL)
            if trade_trad:
                traditional_result.trades.append(trade_trad)
                traditional_result.total_trades += 1
                traditional_result.total_pnl += trade_trad['realized_pnl']
                if trade_trad['realized_pnl'] > 0:
                    traditional_result.winning_trades += 1
                else:
                    traditional_result.losing_trades += 1

            # Profit hedge strategy
            trade_hedge = self.simulate_trade(df, entry_idx, side, Strategy.PROFIT_HEDGE)
            if trade_hedge:
                profit_hedge_result.trades.append(trade_hedge)
                profit_hedge_result.total_trades += 1
                profit_hedge_result.total_pnl += trade_hedge['realized_pnl']
                profit_hedge_result.total_hedge_pnl += trade_hedge['hedge_pnl']
                combined = trade_hedge['realized_pnl'] + trade_hedge['hedge_pnl']
                if combined > 0:
                    profit_hedge_result.winning_trades += 1
                else:
                    profit_hedge_result.losing_trades += 1

            # Progress
            if (i + 1) % 10 == 0:
                print(f"  Completed {i + 1}/{num_trades} trades")

        # Calculate average profit captured
        if traditional_result.trades:
            traditional_result.avg_profit_captured = np.mean([
                t['profit_captured_pct'] for t in traditional_result.trades
            ])

        if profit_hedge_result.trades:
            profit_hedge_result.avg_profit_captured = np.mean([
                t['profit_captured_pct'] for t in profit_hedge_result.trades
            ])

        return traditional_result, profit_hedge_result

    def print_results(self, trad: BacktestResult, hedge: BacktestResult):
        """Print comparison results"""
        print(f"\n{'='*60}")
        print(f"BACKTEST RESULTS COMPARISON")
        print(f"{'='*60}\n")

        print(f"{'Metric':<30} {'Traditional':<15} {'Profit Hedge':<15} {'Diff':<10}")
        print(f"{'-'*70}")

        # Total PnL
        diff_pnl = hedge.combined_pnl - trad.total_pnl
        diff_pct = (diff_pnl / abs(trad.total_pnl) * 100) if trad.total_pnl != 0 else 0
        print(f"{'Total PnL':<30} ${trad.total_pnl:<14.2f} ${hedge.combined_pnl:<14.2f} {'+' if diff_pnl >= 0 else ''}{diff_pnl:.2f} ({diff_pct:+.1f}%)")

        # Main PnL
        print(f"{'  Main Position PnL':<30} ${trad.total_pnl:<14.2f} ${hedge.total_pnl:<14.2f}")

        # Hedge PnL
        print(f"{'  Hedge PnL':<30} {'N/A':<15} ${hedge.total_hedge_pnl:<14.2f}")

        # Win Rate
        diff_wr = hedge.win_rate - trad.win_rate
        print(f"{'Win Rate':<30} {trad.win_rate*100:<14.1f}% {hedge.win_rate*100:<14.1f}% {diff_wr*100:+.1f}%")

        # Avg Profit Captured
        diff_cap = hedge.avg_profit_captured - trad.avg_profit_captured
        print(f"{'Avg Profit Captured':<30} {trad.avg_profit_captured:<14.1f}% {hedge.avg_profit_captured:<14.1f}% {diff_cap:+.1f}%")

        # Trade counts
        print(f"{'Total Trades':<30} {trad.total_trades:<15} {hedge.total_trades:<15}")
        print(f"{'Winning Trades':<30} {trad.winning_trades:<15} {hedge.winning_trades:<15}")
        print(f"{'Losing Trades':<30} {trad.losing_trades:<15} {hedge.losing_trades:<15}")

        # Exit reasons for hedge strategy
        print(f"\n{'='*60}")
        print(f"PROFIT HEDGE EXIT REASONS")
        print(f"{'='*60}")

        reasons = {}
        for t in hedge.trades:
            r = t['exit_reason']
            reasons[r] = reasons.get(r, 0) + 1

        for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
            pct = count / len(hedge.trades) * 100
            print(f"  {reason:<25} {count:>5} ({pct:>5.1f}%)")

        # Recommendation
        print(f"\n{'='*60}")
        print(f"RECOMMENDATION")
        print(f"{'='*60}")

        if hedge.combined_pnl > trad.total_pnl:
            improvement = (hedge.combined_pnl - trad.total_pnl) / abs(trad.total_pnl) * 100 if trad.total_pnl != 0 else 0
            print(f"✅ PROFIT HEDGE STRATEGY outperforms by {improvement:.1f}%")
            print(f"   Combined PnL: ${hedge.combined_pnl:.2f} vs ${trad.total_pnl:.2f}")
        else:
            decline = (trad.total_pnl - hedge.combined_pnl) / abs(trad.total_pnl) * 100 if trad.total_pnl != 0 else 0
            print(f"⚠️ TRADITIONAL STRATEGY performs better by {decline:.1f}%")
            print(f"   Consider adjusting hedge parameters")

        return {
            'traditional': {
                'total_pnl': trad.total_pnl,
                'win_rate': trad.win_rate,
                'avg_profit_captured': trad.avg_profit_captured,
                'trades': len(trad.trades)
            },
            'profit_hedge': {
                'total_pnl': hedge.combined_pnl,
                'main_pnl': hedge.total_pnl,
                'hedge_pnl': hedge.total_hedge_pnl,
                'win_rate': hedge.win_rate,
                'avg_profit_captured': hedge.avg_profit_captured,
                'trades': len(hedge.trades),
                'exit_reasons': reasons
            },
            'improvement_pct': (hedge.combined_pnl - trad.total_pnl) / abs(trad.total_pnl) * 100 if trad.total_pnl != 0 else 0
        }


def run_multi_symbol_backtest(symbols: List[str], timeframe: str = '5m',
                              days: int = 30, trades_per_symbol: int = 30):
    """Run backtest across multiple symbols"""
    bt = ProfitProtectionHedgeBacktest()

    all_results = []
    total_trad_pnl = 0
    total_hedge_pnl = 0

    for symbol in symbols:
        try:
            trad, hedge = bt.run_backtest(symbol, timeframe, days, trades_per_symbol)
            result = bt.print_results(trad, hedge)
            result['symbol'] = symbol
            all_results.append(result)
            total_trad_pnl += trad.total_pnl
            total_hedge_pnl += hedge.combined_pnl
        except Exception as e:
            print(f"  ❌ Failed to backtest {symbol}: {e}")

    # Summary
    print(f"\n{'='*60}")
    print(f"MULTI-SYMBOL SUMMARY ({len(all_results)} symbols)")
    print(f"{'='*60}")
    print(f"Total Traditional PnL: ${total_trad_pnl:.2f}")
    print(f"Total Profit Hedge PnL: ${total_hedge_pnl:.2f}")
    improvement = (total_hedge_pnl - total_trad_pnl) / abs(total_trad_pnl) * 100 if total_trad_pnl != 0 else 0
    print(f"Overall Improvement: {improvement:+.1f}%")

    return all_results


if __name__ == "__main__":
    # Default symbols to test
    test_symbols = [
        'BTC/USDT:USDT',
        'ETH/USDT:USDT',
        'SOL/USDT:USDT',
        'LINK/USDT:USDT',
        'DOGE/USDT:USDT'
    ]

    # Run multi-symbol backtest
    results = run_multi_symbol_backtest(
        symbols=test_symbols,
        timeframe='5m',
        days=30,
        trades_per_symbol=30
    )

    # Save results
    with open('backtest_profit_hedge_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Results saved to backtest_profit_hedge_results.json")
