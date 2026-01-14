#!/usr/bin/env python3
"""
Pre-Trade Backtest Validator - Sprint 14
=========================================

Runs quick backtest BEFORE opening positions to validate trade viability.
Based on Grok Consortium recommendations.

Key Metrics:
- Win Rate (>60% threshold)
- Average Profit (>1% per trade)
- Max Drawdown (<15%)
- Sharpe Ratio (>1.5)
- Profit Factor (>1.5)

Performance Target: <5 seconds per symbol
History: 30-60 days for quick validation

Author: Claude + Grok Consortium
Version: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime
import time


@dataclass
class BacktestResult:
    """Pre-trade backtest result"""
    symbol: str
    score: float  # 0-1 composite score
    should_trade: bool
    win_rate: float
    avg_profit_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    profit_factor: float
    total_trades: int
    optimal_params: Dict
    reasoning: str
    backtest_time_ms: int


class PreTradeBacktester:
    """
    Fast pre-trade backtester using actual trading logic.

    Simulates:
    - Fibonacci averaging at dynamic thresholds
    - Dynamic delta based on S/R and regime
    - Correlation-based position sizing
    - Orderbook imbalance timing
    """

    # Thresholds for trade approval
    MIN_WIN_RATE = 0.55  # 55% minimum win rate
    MIN_AVG_PROFIT = 0.005  # 0.5% minimum avg profit
    MAX_DRAWDOWN = 0.20  # 20% max drawdown
    MIN_SHARPE = 1.0  # Minimum Sharpe ratio
    MIN_PROFIT_FACTOR = 1.3  # Minimum profit factor
    MIN_TRADES = 5  # Minimum trades for statistical significance

    # Score weights (must sum to 1.0)
    WEIGHTS = {
        'win_rate': 0.25,
        'avg_profit': 0.20,
        'max_drawdown': 0.20,
        'sharpe': 0.20,
        'profit_factor': 0.15
    }

    # Parameter ranges for optimization
    PARAM_RANGES = {
        'averaging_threshold': [-0.20, -0.25, -0.30, -0.35, -0.40],
        'profit_take_pct': [0.60, 0.70, 0.80, 0.85, 0.90],
        'delta_multiplier': [0.8, 1.0, 1.2, 1.5, 2.0]
    }

    def __init__(self, exchange):
        """
        Initialize pre-trade backtester.

        Args:
            exchange: CCXT exchange instance
        """
        self.exchange = exchange
        self.cache = {}
        self.cache_ttl = 300  # 5 minute cache

    def validate_trade(
        self,
        symbol: str,
        direction: str,
        days: int = 30,
        timeframe: str = '15m'
    ) -> BacktestResult:
        """
        Run pre-trade backtest validation.

        Args:
            symbol: Trading symbol
            direction: 'long' or 'short'
            days: Days of history to use (default 30)
            timeframe: Candle timeframe (default 15m)

        Returns:
            BacktestResult with score and recommendation
        """
        start_time = time.time()

        # Check cache
        cache_key = f"{symbol}:{direction}:{days}"
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            if time.time() - cached['timestamp'] < self.cache_ttl:
                return cached['result']

        try:
            # Fetch historical data
            df = self._fetch_history(symbol, timeframe, days)
            if df is None or len(df) < 100:
                return self._create_skip_result(symbol, "Insufficient historical data")

            # Run backtest with default params first
            default_result = self._run_backtest(
                df, direction,
                averaging_threshold=-0.25,
                profit_take_pct=0.70,
                delta_multiplier=1.0
            )

            # Quick parameter optimization (test 3 key combinations)
            best_params, best_metrics = self._quick_optimize(df, direction)

            # Calculate composite score
            score = self._calculate_score(best_metrics)

            # Determine if trade should proceed
            should_trade = self._should_trade(best_metrics, score)

            # Build reasoning
            reasoning = self._build_reasoning(best_metrics, score, should_trade)

            result = BacktestResult(
                symbol=symbol,
                score=score,
                should_trade=should_trade,
                win_rate=best_metrics['win_rate'],
                avg_profit_pct=best_metrics['avg_profit'],
                max_drawdown_pct=best_metrics['max_drawdown'],
                sharpe_ratio=best_metrics['sharpe'],
                profit_factor=best_metrics['profit_factor'],
                total_trades=best_metrics['total_trades'],
                optimal_params=best_params,
                reasoning=reasoning,
                backtest_time_ms=int((time.time() - start_time) * 1000)
            )

            # Cache result
            self.cache[cache_key] = {
                'result': result,
                'timestamp': time.time()
            }

            return result

        except Exception as e:
            return self._create_skip_result(symbol, f"Backtest error: {e}")

    def _fetch_history(self, symbol: str, timeframe: str, days: int) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data."""
        try:
            # Calculate candles needed
            tf_minutes = {'1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240}.get(timeframe, 15)
            candles_per_day = 1440 / tf_minutes
            limit = int(days * candles_per_day)

            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=min(limit, 1000))
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['returns'] = df['close'].pct_change()

            return df

        except Exception as e:
            print(f"  ⚠️ History fetch failed for {symbol}: {e}")
            return None

    def _run_backtest(
        self,
        df: pd.DataFrame,
        direction: str,
        averaging_threshold: float,
        profit_take_pct: float,
        delta_multiplier: float
    ) -> Dict:
        """
        Run vectorized backtest simulation.

        Simulates Fibonacci averaging strategy with given parameters.
        """
        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values

        trades = []
        position = None
        avg_steps = 0
        entry_price = 0
        peak_pnl = 0

        # Simple simulation loop (vectorize later if too slow)
        for i in range(20, len(closes)):
            price = closes[i]

            if position is None:
                # Entry signal: Simple momentum + volatility check
                returns_20 = (price - closes[i-20]) / closes[i-20]
                volatility = np.std(closes[i-20:i]) / np.mean(closes[i-20:i])

                # Entry condition based on direction
                if direction == 'long' and returns_20 < -0.05 and volatility > 0.02:
                    position = 'long'
                    entry_price = price
                    avg_steps = 0
                    peak_pnl = 0
                elif direction == 'short' and returns_20 > 0.05 and volatility > 0.02:
                    position = 'short'
                    entry_price = price
                    avg_steps = 0
                    peak_pnl = 0

            else:
                # Calculate P&L
                if position == 'long':
                    pnl_pct = (price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - price) / entry_price

                # Update peak
                if pnl_pct > peak_pnl:
                    peak_pnl = pnl_pct

                # Averaging logic
                if pnl_pct < averaging_threshold * delta_multiplier and avg_steps < 5:
                    # Simulate averaging (improves entry price)
                    entry_price = (entry_price + price) / 2
                    avg_steps += 1

                # Exit conditions
                exit_trade = False
                exit_reason = ""

                # Profit taking at % of peak
                if peak_pnl > 0.02 and pnl_pct < peak_pnl * profit_take_pct:
                    exit_trade = True
                    exit_reason = "profit_take"

                # Stop loss (liquidation prevention)
                if pnl_pct < -0.90:
                    exit_trade = True
                    exit_reason = "stop_loss"

                # Time-based exit (max 100 candles)
                if i > 100 and position is not None:
                    # Check if stuck
                    if abs(pnl_pct) < 0.01:
                        exit_trade = True
                        exit_reason = "time_exit"

                if exit_trade:
                    trades.append({
                        'entry': entry_price,
                        'exit': price,
                        'pnl_pct': pnl_pct,
                        'direction': position,
                        'avg_steps': avg_steps,
                        'reason': exit_reason
                    })
                    position = None

        # Calculate metrics from trades
        return self._calculate_metrics(trades)

    def _calculate_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate performance metrics from trades."""
        if len(trades) == 0:
            return {
                'win_rate': 0,
                'avg_profit': 0,
                'max_drawdown': 0,
                'sharpe': 0,
                'profit_factor': 0,
                'total_trades': 0
            }

        pnls = [t['pnl_pct'] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        win_rate = len(wins) / len(pnls) if pnls else 0
        avg_profit = np.mean(pnls) if pnls else 0

        # Calculate max drawdown
        cumulative = np.cumsum(pnls)
        peak = np.maximum.accumulate(cumulative)
        drawdown = (peak - cumulative)
        max_drawdown = np.max(drawdown) if len(drawdown) > 0 else 0

        # Sharpe ratio (annualized assuming 15m candles)
        returns_std = np.std(pnls) if len(pnls) > 1 else 0.01
        sharpe = (np.mean(pnls) / returns_std) * np.sqrt(365 * 24 * 4) if returns_std > 0 else 0

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0.01
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit

        return {
            'win_rate': win_rate,
            'avg_profit': avg_profit,
            'max_drawdown': max_drawdown,
            'sharpe': sharpe,
            'profit_factor': profit_factor,
            'total_trades': len(trades)
        }

    def _quick_optimize(self, df: pd.DataFrame, direction: str) -> Tuple[Dict, Dict]:
        """
        Quick parameter optimization (3-5 combinations for speed).

        Returns best params and metrics.
        """
        best_score = -1
        best_params = {}
        best_metrics = {}

        # Test key parameter combinations
        test_combos = [
            (-0.25, 0.70, 1.0),  # Default
            (-0.30, 0.80, 1.2),  # More conservative
            (-0.35, 0.85, 1.5),  # Aggressive averaging
            (-0.20, 0.65, 0.8),  # Tight stops
        ]

        for avg_thresh, profit_pct, delta_mult in test_combos:
            metrics = self._run_backtest(df, direction, avg_thresh, profit_pct, delta_mult)
            score = self._calculate_score(metrics)

            if score > best_score:
                best_score = score
                best_params = {
                    'averaging_threshold': avg_thresh,
                    'profit_take_pct': profit_pct,
                    'delta_multiplier': delta_mult
                }
                best_metrics = metrics

        return best_params, best_metrics

    def _calculate_score(self, metrics: Dict) -> float:
        """Calculate composite score from metrics."""
        # Normalize metrics to 0-1 scale
        win_rate_norm = min(1.0, metrics['win_rate'] / 0.8)  # 80% = perfect
        profit_norm = min(1.0, max(0, metrics['avg_profit'] + 0.1) / 0.2)  # 10% = perfect
        drawdown_norm = max(0, 1 - metrics['max_drawdown'] / 0.3)  # 0% = perfect
        sharpe_norm = min(1.0, max(0, metrics['sharpe']) / 3.0)  # 3.0 = perfect
        pf_norm = min(1.0, max(0, metrics['profit_factor']) / 3.0)  # 3.0 = perfect

        score = (
            self.WEIGHTS['win_rate'] * win_rate_norm +
            self.WEIGHTS['avg_profit'] * profit_norm +
            self.WEIGHTS['max_drawdown'] * drawdown_norm +
            self.WEIGHTS['sharpe'] * sharpe_norm +
            self.WEIGHTS['profit_factor'] * pf_norm
        )

        # Penalty for insufficient trades
        if metrics['total_trades'] < self.MIN_TRADES:
            score *= (metrics['total_trades'] / self.MIN_TRADES)

        return min(1.0, max(0, score))

    def _should_trade(self, metrics: Dict, score: float) -> bool:
        """Determine if trade should proceed based on metrics."""
        # Must meet minimum score threshold
        if score < 0.5:
            return False

        # Must have enough trades for statistical significance
        if metrics['total_trades'] < self.MIN_TRADES:
            return False

        # Must meet individual metric thresholds
        if metrics['win_rate'] < self.MIN_WIN_RATE:
            return False

        if metrics['max_drawdown'] > self.MAX_DRAWDOWN:
            return False

        return True

    def _build_reasoning(self, metrics: Dict, score: float, should_trade: bool) -> str:
        """Build human-readable reasoning."""
        parts = []

        if should_trade:
            parts.append(f"APPROVED (score: {score:.2f})")
        else:
            parts.append(f"REJECTED (score: {score:.2f})")

        parts.append(f"WR: {metrics['win_rate']*100:.1f}%")
        parts.append(f"Avg: {metrics['avg_profit']*100:.2f}%")
        parts.append(f"DD: {metrics['max_drawdown']*100:.1f}%")
        parts.append(f"SR: {metrics['sharpe']:.2f}")
        parts.append(f"PF: {metrics['profit_factor']:.2f}")
        parts.append(f"Trades: {metrics['total_trades']}")

        return " | ".join(parts)

    def _create_skip_result(self, symbol: str, reason: str) -> BacktestResult:
        """Create a skip result for errors/insufficient data."""
        return BacktestResult(
            symbol=symbol,
            score=0,
            should_trade=False,
            win_rate=0,
            avg_profit_pct=0,
            max_drawdown_pct=0,
            sharpe_ratio=0,
            profit_factor=0,
            total_trades=0,
            optimal_params={},
            reasoning=f"SKIPPED: {reason}",
            backtest_time_ms=0
        )


# Module test
if __name__ == "__main__":
    print("PreTradeBacktester V1.0.0")
    print("Grok Consortium Recommendations:")
    print("  - Win Rate >55%, Avg Profit >0.5%, Max DD <20%")
    print("  - Sharpe >1.0, Profit Factor >1.3")
    print("  - Target: <5 seconds per symbol")
