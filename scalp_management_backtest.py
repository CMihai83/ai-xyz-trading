#!/usr/bin/env python3
"""
Scalp Position Management Backtest
===================================

Compares two approaches for managing scalp positions:

STRATEGY A: Quick Scalper Self-Managed
- Micro TP/SL: 0.15% / 0.08%
- Max hold: 5 minutes
- No averaging

STRATEGY B: Main Engine Managed
- Fibonacci averaging (up to 3 steps for scalps)
- Surplus dump at 85%/40% of peak
- Wider TP/SL: 0.5% / 0.3%
- Max hold: 30 minutes

Uses 1-minute candles with RSI + OrderBook signals.

DESIGN: Claude (Opus 4.5) + Grok Consortium
DATE: January 17, 2026
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import json
import os
from dotenv import load_dotenv

load_dotenv()


@dataclass
class BacktestConfig:
    """Backtest configuration"""
    # Symbols to test
    SYMBOLS: List[str] = field(default_factory=lambda: [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT',
        'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'PEPE/USDT:USDT',
        'XMR/USDT:USDT', 'DASH/USDT:USDT'
    ])

    # Timeframe
    TIMEFRAME: str = '1m'
    CANDLES_TO_FETCH: int = 4320  # 72 hours of 1m candles (more data for signals)

    # Signal thresholds (relaxed for more signals)
    RSI_OVERSOLD: float = 30.0  # Relaxed from 25 to get more signals
    RSI_OVERBOUGHT: float = 70.0  # Relaxed from 75 to get more signals
    OB_IMBALANCE_THRESHOLD: float = 0.15  # Relaxed from 0.20

    # Position sizing
    POSITION_SIZE_USD: float = 20.0
    LEVERAGE: int = 10

    # Strategy A: Quick Scalper Self-Managed (no averaging)
    SCALPER_TP_PCT: float = 0.15
    SCALPER_SL_PCT: float = 0.08
    SCALPER_MAX_HOLD_CANDLES: int = 5  # 5 minutes

    # Strategy B: Same TP/SL/MaxHold + Averaging + Surplus Dump
    # Uses SAME TP/SL and max hold as scalper
    ENGINE_TP_PCT: float = 0.15  # Same as scalper
    ENGINE_SL_PCT: float = 0.08  # Same as scalper
    ENGINE_MAX_HOLD_CANDLES: int = 5  # Same as scalper (5 minutes)
    # But adds averaging and surplus dump
    ENGINE_AVG_THRESHOLD_PCT: float = -0.05  # Average at -0.05% (micro threshold for scalps)
    ENGINE_AVG_MULTIPLIERS: List[float] = field(default_factory=lambda: [0.5, 1.0, 1.5])  # Small scalp averaging
    ENGINE_SURPLUS_DUMP_1: float = 0.85  # 85% of peak
    ENGINE_SURPLUS_DUMP_2: float = 0.40  # 40% of peak


@dataclass
class Trade:
    """Single trade record"""
    symbol: str
    side: str
    entry_price: float
    entry_time: int  # candle index
    exit_price: float = 0.0
    exit_time: int = 0
    exit_reason: str = ""
    pnl_pct: float = 0.0
    pnl_usd: float = 0.0
    averaging_steps: int = 0
    peak_pnl_pct: float = 0.0


class ScalpManagementBacktest:
    """Backtest comparing scalp management strategies"""

    def __init__(self):
        self.config = BacktestConfig()
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {'defaultType': 'swap'}
        })

        self.results = {
            'strategy_a': {'trades': [], 'stats': {}},
            'strategy_b': {'trades': [], 'stats': {}}
        }

    def fetch_data(self, symbol: str) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for a symbol"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                self.config.TIMEFRAME,
                limit=self.config.CANDLES_TO_FETCH
            )
            df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            df['ts'] = pd.to_datetime(df['ts'], unit='ms')
            return df
        except Exception as e:
            print(f"  Error fetching {symbol}: {e}")
            return None

    def calculate_rsi(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate RSI"""
        delta = df['c'].diff()
        gain = delta.where(delta > 0, 0).rolling(period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def simulate_orderbook_imbalance(self, df: pd.DataFrame, idx: int) -> float:
        """
        Simulate orderbook imbalance based on price action.
        In real trading we'd use actual orderbook data.
        """
        if idx < 5:
            return 0.0

        # Use recent price momentum as proxy for orderbook imbalance
        recent_returns = df['c'].iloc[idx-5:idx].pct_change().dropna()
        momentum = recent_returns.mean()

        # Volume spike indicates stronger imbalance
        vol_avg = df['v'].iloc[max(0, idx-20):idx].mean()
        vol_current = df['v'].iloc[idx]
        vol_factor = min(vol_current / vol_avg, 2.0) if vol_avg > 0 else 1.0

        # Convert to imbalance (-1 to +1)
        imbalance = np.tanh(momentum * 100) * vol_factor * 0.5
        return imbalance

    def find_signals(self, df: pd.DataFrame) -> List[Tuple[int, str]]:
        """Find RSI signals (simplified for backtest - no simulated orderbook)"""
        signals = []
        rsi = self.calculate_rsi(df)

        min_gap = 10  # Minimum 10 candles between signals to avoid overlapping trades
        last_signal_idx = -min_gap

        for i in range(20, len(df) - 30):  # Leave room for position management
            if i - last_signal_idx < min_gap:
                continue

            rsi_val = rsi.iloc[i]

            # Long signal: RSI oversold
            if rsi_val < self.config.RSI_OVERSOLD:
                signals.append((i, 'long'))
                last_signal_idx = i

            # Short signal: RSI overbought
            elif rsi_val > self.config.RSI_OVERBOUGHT:
                signals.append((i, 'short'))
                last_signal_idx = i

        return signals

    def simulate_strategy_a(self, df: pd.DataFrame, entry_idx: int, side: str) -> Trade:
        """
        Strategy A: Quick Scalper self-managed
        - Micro TP/SL
        - No averaging
        - Short max hold
        """
        entry_price = df['c'].iloc[entry_idx]

        # Calculate TP/SL prices
        if side == 'long':
            tp_price = entry_price * (1 + self.config.SCALPER_TP_PCT / 100)
            sl_price = entry_price * (1 - self.config.SCALPER_SL_PCT / 100)
        else:
            tp_price = entry_price * (1 - self.config.SCALPER_TP_PCT / 100)
            sl_price = entry_price * (1 + self.config.SCALPER_SL_PCT / 100)

        # Simulate position
        for i in range(entry_idx + 1, min(entry_idx + self.config.SCALPER_MAX_HOLD_CANDLES + 1, len(df))):
            high = df['h'].iloc[i]
            low = df['l'].iloc[i]
            close = df['c'].iloc[i]

            if side == 'long':
                # Check TP first (optimistic)
                if high >= tp_price:
                    pnl_pct = self.config.SCALPER_TP_PCT
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=tp_price,
                        exit_time=i,
                        exit_reason='TP',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE
                    )
                # Check SL
                if low <= sl_price:
                    pnl_pct = -self.config.SCALPER_SL_PCT
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=sl_price,
                        exit_time=i,
                        exit_reason='SL',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE
                    )
            else:  # short
                if low <= tp_price:
                    pnl_pct = self.config.SCALPER_TP_PCT
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=tp_price,
                        exit_time=i,
                        exit_reason='TP',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE
                    )
                if high >= sl_price:
                    pnl_pct = -self.config.SCALPER_SL_PCT
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=sl_price,
                        exit_time=i,
                        exit_reason='SL',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE
                    )

        # Max hold reached - exit at close
        exit_idx = min(entry_idx + self.config.SCALPER_MAX_HOLD_CANDLES, len(df) - 1)
        exit_price = df['c'].iloc[exit_idx]

        if side == 'long':
            pnl_pct = (exit_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - exit_price) / entry_price * 100

        return Trade(
            symbol=df.name if hasattr(df, 'name') else 'unknown',
            side=side,
            entry_price=entry_price,
            entry_time=entry_idx,
            exit_price=exit_price,
            exit_time=exit_idx,
            exit_reason='MAX_HOLD',
            pnl_pct=pnl_pct,
            pnl_usd=pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE
        )

    def simulate_strategy_b(self, df: pd.DataFrame, entry_idx: int, side: str) -> Trade:
        """
        Strategy B: Main Engine managed
        - Fibonacci averaging
        - Surplus dump at peak percentage
        - Longer hold time
        """
        entry_price = df['c'].iloc[entry_idx]
        avg_entry = entry_price
        total_size = 1.0  # Normalized size
        averaging_step = 0
        peak_pnl_pct = 0.0
        dumped_stage1 = False

        # Calculate initial TP/SL
        if side == 'long':
            tp_price = entry_price * (1 + self.config.ENGINE_TP_PCT / 100)
            sl_price = entry_price * (1 - self.config.ENGINE_SL_PCT / 100)
        else:
            tp_price = entry_price * (1 - self.config.ENGINE_TP_PCT / 100)
            sl_price = entry_price * (1 + self.config.ENGINE_SL_PCT / 100)

        for i in range(entry_idx + 1, min(entry_idx + self.config.ENGINE_MAX_HOLD_CANDLES + 1, len(df))):
            close = df['c'].iloc[i]
            high = df['h'].iloc[i]
            low = df['l'].iloc[i]

            # Calculate current PnL
            if side == 'long':
                current_pnl_pct = (close - avg_entry) / avg_entry * 100
            else:
                current_pnl_pct = (avg_entry - close) / avg_entry * 100

            # Track peak
            if current_pnl_pct > peak_pnl_pct:
                peak_pnl_pct = current_pnl_pct

            # Check for averaging opportunity
            if current_pnl_pct <= self.config.ENGINE_AVG_THRESHOLD_PCT and averaging_step < len(self.config.ENGINE_AVG_MULTIPLIERS):
                # Average in
                multiplier = self.config.ENGINE_AVG_MULTIPLIERS[averaging_step]
                new_size = multiplier

                # Recalculate average entry
                new_total = total_size + new_size
                avg_entry = (avg_entry * total_size + close * new_size) / new_total
                total_size = new_total
                averaging_step += 1

                # Recalculate TP/SL from new average
                if side == 'long':
                    tp_price = avg_entry * (1 + self.config.ENGINE_TP_PCT / 100)
                    sl_price = avg_entry * (1 - self.config.ENGINE_SL_PCT / 100)
                else:
                    tp_price = avg_entry * (1 - self.config.ENGINE_TP_PCT / 100)
                    sl_price = avg_entry * (1 + self.config.ENGINE_SL_PCT / 100)

            # Check surplus dump (only if we've averaged and in profit)
            if averaging_step > 0 and current_pnl_pct > 0 and peak_pnl_pct > 0.1:
                current_vs_peak = current_pnl_pct / peak_pnl_pct if peak_pnl_pct > 0 else 1.0

                # Stage 1: Dump 50% at 85% of peak
                if not dumped_stage1 and current_vs_peak <= self.config.ENGINE_SURPLUS_DUMP_1:
                    # Partial exit - for backtest, just track that it happened
                    dumped_stage1 = True

                # Stage 2: Dump remaining at 40% of peak
                if dumped_stage1 and current_vs_peak <= self.config.ENGINE_SURPLUS_DUMP_2:
                    pnl_usd = current_pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE * total_size
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=close,
                        exit_time=i,
                        exit_reason='SURPLUS_DUMP',
                        pnl_pct=current_pnl_pct,
                        pnl_usd=pnl_usd,
                        averaging_steps=averaging_step,
                        peak_pnl_pct=peak_pnl_pct
                    )

            # Check TP
            if side == 'long':
                if high >= tp_price:
                    pnl_pct = (tp_price - avg_entry) / avg_entry * 100
                    pnl_usd = pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE * total_size
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=tp_price,
                        exit_time=i,
                        exit_reason='TP',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_usd,
                        averaging_steps=averaging_step,
                        peak_pnl_pct=peak_pnl_pct
                    )
                if low <= sl_price:
                    pnl_pct = (sl_price - avg_entry) / avg_entry * 100
                    pnl_usd = pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE * total_size
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=sl_price,
                        exit_time=i,
                        exit_reason='SL',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_usd,
                        averaging_steps=averaging_step,
                        peak_pnl_pct=peak_pnl_pct
                    )
            else:  # short
                if low <= tp_price:
                    pnl_pct = (avg_entry - tp_price) / avg_entry * 100
                    pnl_usd = pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE * total_size
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=tp_price,
                        exit_time=i,
                        exit_reason='TP',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_usd,
                        averaging_steps=averaging_step,
                        peak_pnl_pct=peak_pnl_pct
                    )
                if high >= sl_price:
                    pnl_pct = (avg_entry - sl_price) / avg_entry * 100
                    pnl_usd = pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE * total_size
                    return Trade(
                        symbol=df.name if hasattr(df, 'name') else 'unknown',
                        side=side,
                        entry_price=entry_price,
                        entry_time=entry_idx,
                        exit_price=sl_price,
                        exit_time=i,
                        exit_reason='SL',
                        pnl_pct=pnl_pct,
                        pnl_usd=pnl_usd,
                        averaging_steps=averaging_step,
                        peak_pnl_pct=peak_pnl_pct
                    )

        # Max hold - exit at close
        exit_idx = min(entry_idx + self.config.ENGINE_MAX_HOLD_CANDLES, len(df) - 1)
        exit_price = df['c'].iloc[exit_idx]

        if side == 'long':
            pnl_pct = (exit_price - avg_entry) / avg_entry * 100
        else:
            pnl_pct = (avg_entry - exit_price) / avg_entry * 100

        pnl_usd = pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE * total_size

        return Trade(
            symbol=df.name if hasattr(df, 'name') else 'unknown',
            side=side,
            entry_price=entry_price,
            entry_time=entry_idx,
            exit_price=exit_price,
            exit_time=exit_idx,
            exit_reason='MAX_HOLD',
            pnl_pct=pnl_pct,
            pnl_usd=pnl_usd,
            averaging_steps=averaging_step,
            peak_pnl_pct=peak_pnl_pct
        )

    def calculate_stats(self, trades: List[Trade]) -> Dict:
        """Calculate statistics for a list of trades"""
        if not trades:
            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'total_pnl_usd': 0,
                'avg_pnl_usd': 0,
                'profit_factor': 0,
                'avg_hold_candles': 0,
                'tp_exits': 0,
                'sl_exits': 0,
                'max_hold_exits': 0,
                'surplus_dump_exits': 0,
                'avg_averaging_steps': 0
            }

        wins = [t for t in trades if t.pnl_usd > 0]
        losses = [t for t in trades if t.pnl_usd <= 0]

        gross_profit = sum(t.pnl_usd for t in wins)
        gross_loss = abs(sum(t.pnl_usd for t in losses))

        return {
            'total_trades': len(trades),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': len(wins) / len(trades) * 100 if trades else 0,
            'total_pnl_usd': sum(t.pnl_usd for t in trades),
            'avg_pnl_usd': sum(t.pnl_usd for t in trades) / len(trades) if trades else 0,
            'profit_factor': gross_profit / gross_loss if gross_loss > 0 else float('inf'),
            'avg_hold_candles': sum(t.exit_time - t.entry_time for t in trades) / len(trades) if trades else 0,
            'tp_exits': len([t for t in trades if t.exit_reason == 'TP']),
            'sl_exits': len([t for t in trades if t.exit_reason == 'SL']),
            'max_hold_exits': len([t for t in trades if t.exit_reason == 'MAX_HOLD']),
            'surplus_dump_exits': len([t for t in trades if t.exit_reason == 'SURPLUS_DUMP']),
            'avg_averaging_steps': sum(t.averaging_steps for t in trades) / len(trades) if trades else 0
        }

    def run(self):
        """Run the backtest"""
        print("=" * 70)
        print("SCALP POSITION MANAGEMENT BACKTEST")
        print("Comparing: No Averaging vs Averaging + Surplus Dump")
        print("=" * 70)
        print(f"\nStrategy A: No Averaging (TP {self.config.SCALPER_TP_PCT}%, SL {self.config.SCALPER_SL_PCT}%, {self.config.SCALPER_MAX_HOLD_CANDLES}min)")
        print(f"Strategy B: With Averaging + Surplus Dump (same TP/SL/max hold)")
        print(f"           Avg threshold: {self.config.ENGINE_AVG_THRESHOLD_PCT}%, multipliers: {self.config.ENGINE_AVG_MULTIPLIERS}")
        print(f"           Surplus dump: {self.config.ENGINE_SURPLUS_DUMP_1*100:.0f}% / {self.config.ENGINE_SURPLUS_DUMP_2*100:.0f}% of peak")
        print(f"\nSymbols: {len(self.config.SYMBOLS)}")
        print(f"Timeframe: {self.config.TIMEFRAME}")
        print(f"Candles: {self.config.CANDLES_TO_FETCH} (~{self.config.CANDLES_TO_FETCH // 60} hours)")
        print("-" * 70)

        all_trades_a = []
        all_trades_b = []

        for symbol in self.config.SYMBOLS:
            sym = symbol.replace('/USDT:USDT', '')
            print(f"\n[{sym}] Fetching data...")

            df = self.fetch_data(symbol)
            if df is None or len(df) < 100:
                print(f"  Skipped - insufficient data")
                continue

            df.name = symbol

            # Find signals
            signals = self.find_signals(df)
            print(f"  Found {len(signals)} signals")

            if not signals:
                continue

            # Simulate both strategies on each signal
            symbol_trades_a = []
            symbol_trades_b = []

            last_exit_a = 0
            last_exit_b = 0

            for entry_idx, side in signals:
                # Strategy A
                if entry_idx > last_exit_a:
                    trade_a = self.simulate_strategy_a(df, entry_idx, side)
                    trade_a.symbol = symbol
                    symbol_trades_a.append(trade_a)
                    last_exit_a = trade_a.exit_time

                # Strategy B
                if entry_idx > last_exit_b:
                    trade_b = self.simulate_strategy_b(df, entry_idx, side)
                    trade_b.symbol = symbol
                    symbol_trades_b.append(trade_b)
                    last_exit_b = trade_b.exit_time

            # Calculate per-symbol stats
            stats_a = self.calculate_stats(symbol_trades_a)
            stats_b = self.calculate_stats(symbol_trades_b)

            print(f"  Strategy A: {stats_a['total_trades']} trades, WR {stats_a['win_rate']:.1f}%, PnL ${stats_a['total_pnl_usd']:.2f}")
            print(f"  Strategy B: {stats_b['total_trades']} trades, WR {stats_b['win_rate']:.1f}%, PnL ${stats_b['total_pnl_usd']:.2f}")

            all_trades_a.extend(symbol_trades_a)
            all_trades_b.extend(symbol_trades_b)

        # Overall stats
        print("\n" + "=" * 70)
        print("OVERALL RESULTS")
        print("=" * 70)

        stats_a = self.calculate_stats(all_trades_a)
        stats_b = self.calculate_stats(all_trades_b)

        print(f"\n{'Metric':<25} {'Strategy A':>15} {'Strategy B':>15} {'Winner':>10}")
        print("-" * 70)

        metrics = [
            ('Total Trades', stats_a['total_trades'], stats_b['total_trades']),
            ('Win Rate %', stats_a['win_rate'], stats_b['win_rate']),
            ('Total PnL $', stats_a['total_pnl_usd'], stats_b['total_pnl_usd']),
            ('Avg PnL/Trade $', stats_a['avg_pnl_usd'], stats_b['avg_pnl_usd']),
            ('Profit Factor', stats_a['profit_factor'], stats_b['profit_factor']),
            ('Avg Hold (candles)', stats_a['avg_hold_candles'], stats_b['avg_hold_candles']),
            ('TP Exits', stats_a['tp_exits'], stats_b['tp_exits']),
            ('SL Exits', stats_a['sl_exits'], stats_b['sl_exits']),
            ('Max Hold Exits', stats_a['max_hold_exits'], stats_b['max_hold_exits']),
        ]

        for name, val_a, val_b in metrics:
            if isinstance(val_a, float):
                winner = 'A' if val_a > val_b else ('B' if val_b > val_a else 'TIE')
                # For SL Exits and Max Hold, lower is better
                if 'SL' in name or 'Max Hold' in name:
                    winner = 'A' if val_a < val_b else ('B' if val_b < val_a else 'TIE')
                print(f"{name:<25} {val_a:>15.2f} {val_b:>15.2f} {winner:>10}")
            else:
                winner = 'A' if val_a > val_b else ('B' if val_b > val_a else 'TIE')
                if 'SL' in name:
                    winner = 'A' if val_a < val_b else ('B' if val_b < val_a else 'TIE')
                print(f"{name:<25} {val_a:>15} {val_b:>15} {winner:>10}")

        if stats_b.get('surplus_dump_exits', 0) > 0:
            print(f"{'Surplus Dump Exits':<25} {'N/A':>15} {stats_b['surplus_dump_exits']:>15}")
        if stats_b.get('avg_averaging_steps', 0) > 0:
            print(f"{'Avg Averaging Steps':<25} {'0':>15} {stats_b['avg_averaging_steps']:>15.2f}")

        # Recommendation
        print("\n" + "=" * 70)
        print("RECOMMENDATION")
        print("=" * 70)

        if stats_a['total_trades'] == 0 and stats_b['total_trades'] == 0:
            print("\n⚠️  No trades executed - insufficient signals in data period")
            print("   Try extending data window or relaxing signal thresholds")
        elif stats_a['total_pnl_usd'] > stats_b['total_pnl_usd']:
            print("\n✓ Strategy A (No Averaging) is BETTER for scalps")
            print(f"  PnL advantage: ${stats_a['total_pnl_usd'] - stats_b['total_pnl_usd']:.2f}")
            print("  → Keep scalp positions self-managed with micro TP/SL")
        else:
            print("\n✓ Strategy B (With Averaging + Surplus Dump) is BETTER for scalps")
            print(f"  PnL advantage: ${stats_b['total_pnl_usd'] - stats_a['total_pnl_usd']:.2f}")
            print(f"  → Averaging converted {stats_b['avg_averaging_steps']:.1f} avg steps/trade")
            if stats_b['surplus_dump_exits'] > 0:
                print(f"  → Surplus dump triggered {stats_b['surplus_dump_exits']} times")

        # Save results
        results = {
            'timestamp': datetime.now().isoformat(),
            'config': {
                'symbols': self.config.SYMBOLS,
                'candles': self.config.CANDLES_TO_FETCH,
                'strategy_a': {
                    'tp_pct': self.config.SCALPER_TP_PCT,
                    'sl_pct': self.config.SCALPER_SL_PCT,
                    'max_hold': self.config.SCALPER_MAX_HOLD_CANDLES
                },
                'strategy_b': {
                    'tp_pct': self.config.ENGINE_TP_PCT,
                    'sl_pct': self.config.ENGINE_SL_PCT,
                    'max_hold': self.config.ENGINE_MAX_HOLD_CANDLES,
                    'avg_threshold': self.config.ENGINE_AVG_THRESHOLD_PCT
                }
            },
            'strategy_a': stats_a,
            'strategy_b': stats_b,
            'recommendation': 'A' if stats_a['total_pnl_usd'] > stats_b['total_pnl_usd'] else 'B'
        }

        with open('scalp_management_backtest_results.json', 'w') as f:
            json.dump(results, f, indent=2)

        print(f"\nResults saved to scalp_management_backtest_results.json")

        return results


if __name__ == '__main__':
    backtest = ScalpManagementBacktest()
    backtest.run()
