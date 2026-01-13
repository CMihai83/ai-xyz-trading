#!/usr/bin/env python3
"""
Trade Results Tracker - Proper Win/Loss Recording
Fixes the critical bug where only averaging losses were recorded.

This module tracks ACTUAL trade outcomes for profit factor calculation.
"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class TradeResult:
    """Single trade result record"""
    symbol: str
    side: str  # 'buy' or 'sell'
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    contracts: float
    leverage: float
    margin_used: float
    realized_pnl: float
    pnl_percent: float
    exit_reason: str  # 'profit_taking', 'stop_loss', 'surplus_dump', 'opportunity_cost', 'atr_stop'
    averaging_steps: int
    holding_time_hours: float
    peak_upnl: float
    is_winner: bool


class TradeResultsTracker:
    """
    Tracks actual trade outcomes for profit factor calculation.

    Key metrics tracked:
    - Win rate
    - Profit factor (gross profit / gross loss)
    - Average win/loss
    - Risk/reward ratio
    - Per-symbol performance
    """

    def __init__(self, results_file: str = '/app/trade_results.json'):
        self.results_file = results_file
        self.lock = threading.Lock()
        self.results: List[TradeResult] = []
        self.symbol_stats: Dict[str, Dict] = {}
        self._load_results()

    def _load_results(self):
        """Load existing results from file"""
        try:
            if os.path.exists(self.results_file):
                with open(self.results_file, 'r') as f:
                    data = json.load(f)
                    self.results = [TradeResult(**r) for r in data.get('trades', [])]
                    self.symbol_stats = data.get('symbol_stats', {})
                logger.info(f"Loaded {len(self.results)} trade results")
        except Exception as e:
            logger.warning(f"Could not load trade results: {e}")
            self.results = []
            self.symbol_stats = {}

    def _save_results(self):
        """Save results to file"""
        try:
            with self.lock:
                data = {
                    'last_updated': datetime.now().isoformat(),
                    'summary': self.get_summary(),
                    'trades': [asdict(r) for r in self.results[-1000:]],  # Keep last 1000
                    'symbol_stats': self.symbol_stats
                }
                with open(self.results_file, 'w') as f:
                    json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trade results: {e}")

    def record_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        exit_price: float,
        entry_time: str,
        contracts: float,
        leverage: float,
        margin_used: float,
        realized_pnl: float,
        exit_reason: str,
        averaging_steps: int = 0,
        peak_upnl: float = 0.0
    ):
        """
        Record a completed trade result.

        Args:
            symbol: Trading pair
            side: 'buy' or 'sell'
            entry_price: Average entry price
            exit_price: Exit price
            entry_time: ISO timestamp of entry
            contracts: Number of contracts traded
            leverage: Leverage used
            margin_used: Total margin used
            realized_pnl: Actual P&L in USD
            exit_reason: Why position was closed
            averaging_steps: Number of averaging steps executed
            peak_upnl: Peak unrealized P&L during trade
        """
        exit_time = datetime.now().isoformat()

        # Calculate P&L percentage
        if side == 'buy':
            pnl_percent = ((exit_price - entry_price) / entry_price) * leverage * 100
        else:
            pnl_percent = ((entry_price - exit_price) / entry_price) * leverage * 100

        # Calculate holding time
        try:
            entry_dt = datetime.fromisoformat(entry_time.replace('+00:00', ''))
            exit_dt = datetime.now()
            holding_hours = (exit_dt - entry_dt).total_seconds() / 3600
        except:
            holding_hours = 0.0

        is_winner = realized_pnl > 0

        result = TradeResult(
            symbol=symbol,
            side=side,
            entry_price=entry_price,
            exit_price=exit_price,
            entry_time=entry_time,
            exit_time=exit_time,
            contracts=contracts,
            leverage=leverage,
            margin_used=margin_used,
            realized_pnl=realized_pnl,
            pnl_percent=pnl_percent,
            exit_reason=exit_reason,
            averaging_steps=averaging_steps,
            holding_time_hours=holding_hours,
            peak_upnl=peak_upnl,
            is_winner=is_winner
        )

        with self.lock:
            self.results.append(result)
            self._update_symbol_stats(result)

        self._save_results()

        logger.info(f"📊 Trade recorded: {symbol} | {'WIN' if is_winner else 'LOSS'} | ${realized_pnl:.4f} | {exit_reason}")

        return result

    def _update_symbol_stats(self, result: TradeResult):
        """Update per-symbol statistics"""
        symbol = result.symbol

        if symbol not in self.symbol_stats:
            self.symbol_stats[symbol] = {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'gross_profit': 0.0,
                'gross_loss': 0.0,
                'total_averaging_steps': 0,
                'avg_holding_hours': 0.0
            }

        stats = self.symbol_stats[symbol]
        stats['total_trades'] += 1

        if result.is_winner:
            stats['wins'] += 1
            stats['gross_profit'] += result.realized_pnl
        else:
            stats['losses'] += 1
            stats['gross_loss'] += abs(result.realized_pnl)

        stats['total_averaging_steps'] += result.averaging_steps

        # Running average of holding time
        n = stats['total_trades']
        stats['avg_holding_hours'] = (
            (stats['avg_holding_hours'] * (n - 1) + result.holding_time_hours) / n
        )

    def get_summary(self) -> Dict:
        """Get overall trading performance summary"""
        if not self.results:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'net_pnl': 0.0
            }

        wins = [r for r in self.results if r.is_winner]
        losses = [r for r in self.results if not r.is_winner]

        total_trades = len(self.results)
        win_count = len(wins)
        loss_count = len(losses)

        gross_profit = sum(r.realized_pnl for r in wins)
        gross_loss = abs(sum(r.realized_pnl for r in losses))

        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')

        avg_win = (gross_profit / win_count) if win_count > 0 else 0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0
        risk_reward = (avg_win / avg_loss) if avg_loss > 0 else float('inf')

        # Expectancy = (Win% × Avg Win) - (Loss% × Avg Loss)
        expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)

        return {
            'total_trades': total_trades,
            'wins': win_count,
            'losses': loss_count,
            'win_rate': round(win_rate, 2),
            'profit_factor': round(profit_factor, 3),
            'gross_profit': round(gross_profit, 4),
            'gross_loss': round(gross_loss, 4),
            'net_pnl': round(gross_profit - gross_loss, 4),
            'avg_win': round(avg_win, 4),
            'avg_loss': round(avg_loss, 4),
            'risk_reward_ratio': round(risk_reward, 2),
            'expectancy': round(expectancy, 4),
            'avg_holding_hours': round(
                sum(r.holding_time_hours for r in self.results) / total_trades, 2
            ),
            'avg_averaging_steps': round(
                sum(r.averaging_steps for r in self.results) / total_trades, 2
            )
        }

    def get_recent_performance(self, n_trades: int = 20) -> Dict:
        """Get performance metrics for last N trades"""
        recent = self.results[-n_trades:] if len(self.results) >= n_trades else self.results

        if not recent:
            return {'trades': 0, 'win_rate': 0, 'profit_factor': 0}

        wins = [r for r in recent if r.is_winner]
        losses = [r for r in recent if not r.is_winner]

        gross_profit = sum(r.realized_pnl for r in wins)
        gross_loss = abs(sum(r.realized_pnl for r in losses))

        return {
            'trades': len(recent),
            'wins': len(wins),
            'losses': len(losses),
            'win_rate': round(len(wins) / len(recent) * 100, 2),
            'profit_factor': round(gross_profit / gross_loss, 3) if gross_loss > 0 else float('inf'),
            'net_pnl': round(gross_profit - gross_loss, 4)
        }

    def get_symbol_performance(self, symbol: str) -> Dict:
        """Get performance metrics for a specific symbol"""
        if symbol not in self.symbol_stats:
            return {'trades': 0}

        stats = self.symbol_stats[symbol]
        total = stats['total_trades']

        if total == 0:
            return {'trades': 0}

        return {
            'total_trades': total,
            'wins': stats['wins'],
            'losses': stats['losses'],
            'win_rate': round(stats['wins'] / total * 100, 2),
            'profit_factor': round(
                stats['gross_profit'] / stats['gross_loss'], 3
            ) if stats['gross_loss'] > 0 else float('inf'),
            'net_pnl': round(stats['gross_profit'] - stats['gross_loss'], 4),
            'avg_averaging_steps': round(stats['total_averaging_steps'] / total, 2),
            'avg_holding_hours': round(stats['avg_holding_hours'], 2)
        }

    def get_exit_reason_stats(self) -> Dict:
        """Get statistics by exit reason"""
        reasons = {}

        for result in self.results:
            reason = result.exit_reason
            if reason not in reasons:
                reasons[reason] = {
                    'count': 0,
                    'wins': 0,
                    'total_pnl': 0.0
                }

            reasons[reason]['count'] += 1
            if result.is_winner:
                reasons[reason]['wins'] += 1
            reasons[reason]['total_pnl'] += result.realized_pnl

        # Calculate win rates
        for reason, stats in reasons.items():
            stats['win_rate'] = round(stats['wins'] / stats['count'] * 100, 2) if stats['count'] > 0 else 0
            stats['avg_pnl'] = round(stats['total_pnl'] / stats['count'], 4) if stats['count'] > 0 else 0

        return reasons

    def print_dashboard(self):
        """Print a dashboard of trading performance"""
        summary = self.get_summary()
        recent = self.get_recent_performance(20)
        exit_stats = self.get_exit_reason_stats()

        print("\n" + "=" * 70)
        print("📊 AI-XYZ V2 TRADING PERFORMANCE DASHBOARD")
        print("=" * 70)

        print(f"\n📈 OVERALL PERFORMANCE ({summary['total_trades']} trades)")
        print("-" * 40)
        print(f"  Win Rate:        {summary['win_rate']:.1f}%")
        print(f"  Profit Factor:   {summary['profit_factor']:.3f}")
        print(f"  Net P&L:         ${summary['net_pnl']:.2f}")
        print(f"  Gross Profit:    ${summary['gross_profit']:.2f}")
        print(f"  Gross Loss:      ${summary['gross_loss']:.2f}")
        print(f"  Avg Win:         ${summary['avg_win']:.4f}")
        print(f"  Avg Loss:        ${summary['avg_loss']:.4f}")
        print(f"  Risk/Reward:     {summary['risk_reward_ratio']:.2f}")
        print(f"  Expectancy:      ${summary['expectancy']:.4f}/trade")

        print(f"\n📊 RECENT PERFORMANCE (last {recent['trades']} trades)")
        print("-" * 40)
        print(f"  Win Rate:        {recent['win_rate']:.1f}%")
        print(f"  Profit Factor:   {recent['profit_factor']:.3f}")
        print(f"  Net P&L:         ${recent['net_pnl']:.2f}")

        print(f"\n🎯 EXIT REASON ANALYSIS")
        print("-" * 40)
        for reason, stats in sorted(exit_stats.items(), key=lambda x: x[1]['count'], reverse=True):
            print(f"  {reason:<20} | {stats['count']:>3} trades | {stats['win_rate']:>5.1f}% WR | ${stats['avg_pnl']:>8.4f} avg")

        print("\n" + "=" * 70)


# Singleton instance
_tracker_instance = None

def get_trade_tracker() -> TradeResultsTracker:
    """Get singleton trade results tracker"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = TradeResultsTracker()
    return _tracker_instance


if __name__ == "__main__":
    # Demo/test
    tracker = TradeResultsTracker('/tmp/test_trades.json')

    # Simulate some trades
    tracker.record_trade(
        symbol="BTC/USDT:USDT",
        side="buy",
        entry_price=42000,
        exit_price=42500,
        entry_time="2026-01-11T10:00:00",
        contracts=0.1,
        leverage=10,
        margin_used=420,
        realized_pnl=50.0,
        exit_reason="profit_taking",
        averaging_steps=0,
        peak_upnl=55.0
    )

    tracker.record_trade(
        symbol="ETH/USDT:USDT",
        side="buy",
        entry_price=2200,
        exit_price=2150,
        entry_time="2026-01-11T08:00:00",
        contracts=1,
        leverage=10,
        margin_used=220,
        realized_pnl=-22.72,
        exit_reason="stop_loss",
        averaging_steps=2,
        peak_upnl=10.0
    )

    tracker.print_dashboard()
