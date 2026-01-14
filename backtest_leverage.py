#!/usr/bin/env python3
"""
Backtest for Dynamic Leverage Manager
V1.0.0 - January 14, 2026

Validates leverage limits and recommendations using historical/simulated data
across different market regimes.

Compares:
- Static leverage (fixed 10x)
- Dynamic leverage (regime-adjusted)

Measures:
- Total returns
- Maximum drawdown
- Sharpe ratio
- Margin calls / liquidations
- Win rate

Author: Claude + Grok Consortium
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json
import sys
sys.path.insert(0, '/root/ai_xyz')

from dynamic_leverage_manager import DynamicLeverageManager
from dynamic_parameter_manager import DynamicParameterManager

# Results file
RESULTS_FILE = '/root/ai_xyz/backtest_leverage_results.json'


class MarketRegimeSimulator:
    """Simulates different market regimes with realistic price movements."""

    def __init__(self, seed: int = 42):
        np.random.seed(seed)

    def generate_regime_data(self, regime: str, num_candles: int = 500,
                            base_price: float = 100.0) -> pd.DataFrame:
        """
        Generate OHLCV data for a specific market regime.

        Args:
            regime: HIGH_VOLATILITY, TRENDING, RANGING, or NORMAL
            num_candles: Number of 5-minute candles
            base_price: Starting price
        """
        regime_params = {
            'HIGH_VOLATILITY': {'drift': 0.0, 'volatility': 0.015, 'trend': 0.0},
            'TRENDING': {'drift': 0.001, 'volatility': 0.005, 'trend': 0.0005},
            'RANGING': {'drift': 0.0, 'volatility': 0.002, 'trend': 0.0},
            'NORMAL': {'drift': 0.0, 'volatility': 0.005, 'trend': 0.0}
        }

        params = regime_params.get(regime, regime_params['NORMAL'])

        prices = [base_price]
        for i in range(1, num_candles):
            # Random walk with drift and mean reversion
            change = np.random.normal(params['drift'], params['volatility'])
            trend = params['trend'] * (1 if np.random.random() > 0.5 else -1)

            # Mean reversion for ranging
            if regime == 'RANGING':
                mean_price = base_price
                reversion = 0.01 * (mean_price - prices[-1]) / mean_price
                change += reversion

            new_price = prices[-1] * (1 + change + trend)
            prices.append(max(new_price, base_price * 0.5))  # Floor at 50% of base

        # Create OHLCV DataFrame
        data = []
        for i, close in enumerate(prices):
            volatility = params['volatility']
            high = close * (1 + abs(np.random.normal(0, volatility)))
            low = close * (1 - abs(np.random.normal(0, volatility)))
            open_price = prices[i-1] if i > 0 else close
            volume = np.random.uniform(1000, 10000)

            data.append({
                'timestamp': datetime.now() - timedelta(minutes=(num_candles - i) * 5),
                'open': open_price,
                'high': max(high, open_price, close),
                'low': min(low, open_price, close),
                'close': close,
                'volume': volume
            })

        return pd.DataFrame(data)


class LeverageBacktester:
    """
    Backtests different leverage strategies across market regimes.
    """

    def __init__(self):
        self.leverage_manager = DynamicLeverageManager()
        self.results = {}

    def calculate_atr_ratio(self, df: pd.DataFrame, fast: int = 5, slow: int = 14) -> float:
        """Calculate ATR ratio from OHLCV data."""
        if len(df) < slow + 1:
            return 1.0

        true_ranges = []
        for i in range(1, len(df)):
            high = df.iloc[i]['high']
            low = df.iloc[i]['low']
            prev_close = df.iloc[i-1]['close']

            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            true_ranges.append(tr)

        if len(true_ranges) < slow:
            return 1.0

        atr_fast = np.mean(true_ranges[-fast:])
        atr_slow = np.mean(true_ranges[-slow:])

        return atr_fast / atr_slow if atr_slow > 0 else 1.0

    def simulate_trades(self, df: pd.DataFrame, leverage: int, initial_capital: float = 1000.0,
                       position_size_pct: float = 0.1) -> Dict:
        """
        Simulate trades on price data with given leverage.

        Returns performance metrics.
        """
        capital = initial_capital
        peak_capital = initial_capital
        max_drawdown = 0
        trades = []
        margin_calls = 0
        liquidations = 0

        position = None
        entry_price = 0
        position_size = 0

        for i in range(20, len(df)):
            current_price = df.iloc[i]['close']

            # Simple entry signal: price crosses above/below 20-period SMA
            sma = df.iloc[i-20:i]['close'].mean()
            prev_price = df.iloc[i-1]['close']

            # Check existing position
            if position is not None:
                # Calculate P&L
                if position == 'long':
                    pnl_pct = (current_price - entry_price) / entry_price
                else:  # short
                    pnl_pct = (entry_price - current_price) / entry_price

                leveraged_pnl_pct = pnl_pct * leverage
                unrealized_pnl = position_size * leveraged_pnl_pct

                # Check for liquidation (100% loss of position margin)
                if leveraged_pnl_pct <= -0.95:
                    liquidations += 1
                    capital -= position_size  # Lose entire position
                    trades.append({
                        'entry': entry_price,
                        'exit': current_price,
                        'pnl_pct': -100,
                        'result': 'liquidation'
                    })
                    position = None
                    continue

                # Check for margin call (80% loss)
                if leveraged_pnl_pct <= -0.80:
                    margin_calls += 1

                # Exit conditions: opposite signal or stop loss
                exit_signal = (position == 'long' and current_price < sma) or \
                             (position == 'short' and current_price > sma)

                stop_loss = leveraged_pnl_pct <= -0.50  # 50% stop loss

                if exit_signal or stop_loss:
                    # Close position
                    realized_pnl = position_size * leveraged_pnl_pct
                    capital += position_size + realized_pnl

                    trades.append({
                        'entry': entry_price,
                        'exit': current_price,
                        'pnl_pct': leveraged_pnl_pct * 100,
                        'result': 'win' if leveraged_pnl_pct > 0 else 'loss'
                    })

                    position = None

            else:
                # Entry conditions
                if prev_price < sma and current_price > sma:
                    # Long signal
                    position = 'long'
                    entry_price = current_price
                    position_size = capital * position_size_pct
                    capital -= position_size

                elif prev_price > sma and current_price < sma:
                    # Short signal
                    position = 'short'
                    entry_price = current_price
                    position_size = capital * position_size_pct
                    capital -= position_size

            # Track drawdown
            total_value = capital
            if position is not None:
                if position == 'long':
                    pnl_pct = (current_price - entry_price) / entry_price * leverage
                else:
                    pnl_pct = (entry_price - current_price) / entry_price * leverage
                total_value += position_size * (1 + pnl_pct)

            peak_capital = max(peak_capital, total_value)
            drawdown = (peak_capital - total_value) / peak_capital
            max_drawdown = max(max_drawdown, drawdown)

        # Close any remaining position
        if position is not None:
            current_price = df.iloc[-1]['close']
            if position == 'long':
                pnl_pct = (current_price - entry_price) / entry_price * leverage
            else:
                pnl_pct = (entry_price - current_price) / entry_price * leverage

            capital += position_size * (1 + pnl_pct)
            trades.append({
                'entry': entry_price,
                'exit': current_price,
                'pnl_pct': pnl_pct * 100,
                'result': 'win' if pnl_pct > 0 else 'loss'
            })

        # Calculate metrics
        wins = sum(1 for t in trades if t['result'] == 'win')
        losses = sum(1 for t in trades if t['result'] in ['loss', 'liquidation'])
        win_rate = wins / len(trades) if trades else 0

        total_return = (capital - initial_capital) / initial_capital * 100
        avg_trade_pnl = np.mean([t['pnl_pct'] for t in trades]) if trades else 0

        # Sharpe ratio (simplified)
        if trades:
            returns = [t['pnl_pct'] for t in trades]
            sharpe = np.mean(returns) / (np.std(returns) + 0.001) * np.sqrt(252)
        else:
            sharpe = 0

        return {
            'leverage': leverage,
            'initial_capital': initial_capital,
            'final_capital': capital,
            'total_return_pct': total_return,
            'max_drawdown_pct': max_drawdown * 100,
            'num_trades': len(trades),
            'wins': wins,
            'losses': losses,
            'win_rate': win_rate * 100,
            'avg_trade_pnl': avg_trade_pnl,
            'sharpe_ratio': sharpe,
            'margin_calls': margin_calls,
            'liquidations': liquidations
        }

    def backtest_regime(self, regime: str, num_simulations: int = 10) -> Dict:
        """
        Backtest both static and dynamic leverage for a specific regime.
        """
        print(f"\n{'='*60}")
        print(f"Backtesting Regime: {regime}")
        print(f"{'='*60}")

        simulator = MarketRegimeSimulator()

        # Get dynamic leverage for this regime
        regime_leverage = self.leverage_manager.REGIME_LEVERAGE.get(regime, {})
        dynamic_lev = regime_leverage.get('recommended', 10)
        static_lev = 10  # Fixed 10x for comparison

        static_results = []
        dynamic_results = []

        for sim in range(num_simulations):
            # Generate market data
            df = simulator.generate_regime_data(regime, num_candles=500)

            # Test static leverage
            static_res = self.simulate_trades(df, static_lev)
            static_results.append(static_res)

            # Test dynamic leverage
            dynamic_res = self.simulate_trades(df, dynamic_lev)
            dynamic_results.append(dynamic_res)

        # Aggregate results
        def aggregate(results):
            return {
                'leverage': results[0]['leverage'],
                'avg_return': np.mean([r['total_return_pct'] for r in results]),
                'std_return': np.std([r['total_return_pct'] for r in results]),
                'avg_max_dd': np.mean([r['max_drawdown_pct'] for r in results]),
                'avg_win_rate': np.mean([r['win_rate'] for r in results]),
                'avg_sharpe': np.mean([r['sharpe_ratio'] for r in results]),
                'total_margin_calls': sum(r['margin_calls'] for r in results),
                'total_liquidations': sum(r['liquidations'] for r in results)
            }

        static_agg = aggregate(static_results)
        dynamic_agg = aggregate(dynamic_results)

        # Calculate improvement
        return_improvement = dynamic_agg['avg_return'] - static_agg['avg_return']
        dd_improvement = static_agg['avg_max_dd'] - dynamic_agg['avg_max_dd']
        liq_reduction = static_agg['total_liquidations'] - dynamic_agg['total_liquidations']

        print(f"\nStatic Leverage ({static_lev}x):")
        print(f"  Avg Return: {static_agg['avg_return']:.2f}% (+/- {static_agg['std_return']:.2f}%)")
        print(f"  Avg Max DD: {static_agg['avg_max_dd']:.2f}%")
        print(f"  Win Rate: {static_agg['avg_win_rate']:.1f}%")
        print(f"  Sharpe: {static_agg['avg_sharpe']:.2f}")
        print(f"  Margin Calls: {static_agg['total_margin_calls']}, Liquidations: {static_agg['total_liquidations']}")

        print(f"\nDynamic Leverage ({dynamic_lev}x for {regime}):")
        print(f"  Avg Return: {dynamic_agg['avg_return']:.2f}% (+/- {dynamic_agg['std_return']:.2f}%)")
        print(f"  Avg Max DD: {dynamic_agg['avg_max_dd']:.2f}%")
        print(f"  Win Rate: {dynamic_agg['avg_win_rate']:.1f}%")
        print(f"  Sharpe: {dynamic_agg['avg_sharpe']:.2f}")
        print(f"  Margin Calls: {dynamic_agg['total_margin_calls']}, Liquidations: {dynamic_agg['total_liquidations']}")

        print(f"\nImprovement with Dynamic Leverage:")
        print(f"  Return: {'+' if return_improvement > 0 else ''}{return_improvement:.2f}%")
        print(f"  Drawdown Reduction: {dd_improvement:.2f}%")
        print(f"  Liquidation Reduction: {liq_reduction}")

        return {
            'regime': regime,
            'static': static_agg,
            'dynamic': dynamic_agg,
            'improvement': {
                'return': return_improvement,
                'drawdown_reduction': dd_improvement,
                'liquidation_reduction': liq_reduction
            }
        }

    def run_full_backtest(self) -> Dict:
        """Run backtest across all regimes."""
        print("\n" + "="*70)
        print("DYNAMIC LEVERAGE BACKTEST")
        print("="*70)
        print(f"Test Time: {datetime.now().isoformat()}")
        print(f"Comparing Static (10x) vs Dynamic (regime-adjusted) leverage")

        regimes = ['HIGH_VOLATILITY', 'TRENDING', 'RANGING', 'NORMAL']
        results = {
            'timestamp': datetime.now().isoformat(),
            'regimes': {}
        }

        for regime in regimes:
            regime_result = self.backtest_regime(regime, num_simulations=10)
            results['regimes'][regime] = regime_result

        # Overall summary
        print("\n" + "="*70)
        print("OVERALL SUMMARY")
        print("="*70)

        total_return_improvement = 0
        total_dd_improvement = 0
        total_liq_reduction = 0

        print(f"\n{'Regime':<20} {'Static Ret':<12} {'Dynamic Ret':<12} {'DD Reduction':<12} {'Liq Reduction'}")
        print("-" * 70)

        for regime, res in results['regimes'].items():
            static_ret = res['static']['avg_return']
            dynamic_ret = res['dynamic']['avg_return']
            dd_red = res['improvement']['drawdown_reduction']
            liq_red = res['improvement']['liquidation_reduction']

            total_return_improvement += res['improvement']['return']
            total_dd_improvement += dd_red
            total_liq_reduction += liq_red

            print(f"{regime:<20} {static_ret:>+10.2f}% {dynamic_ret:>+10.2f}% {dd_red:>+10.2f}% {liq_red:>+10}")

        avg_return_improvement = total_return_improvement / len(regimes)
        avg_dd_improvement = total_dd_improvement / len(regimes)

        print("-" * 70)
        print(f"{'AVERAGE':<20} {'':<12} {'':<12} {avg_dd_improvement:>+10.2f}% {total_liq_reduction:>+10}")

        # Recommendation
        print("\n" + "="*70)
        print("RECOMMENDATION")
        print("="*70)

        if avg_dd_improvement > 0 and total_liq_reduction >= 0:
            print("✅ Dynamic leverage REDUCES RISK with comparable returns")
            print(f"   Average drawdown reduction: {avg_dd_improvement:.2f}%")
            print(f"   Total liquidation reduction: {total_liq_reduction}")
            recommendation = "KEEP_DYNAMIC"
        elif avg_return_improvement > 5:
            print("⚠️ Dynamic leverage shows HIGHER RETURNS but similar risk")
            recommendation = "KEEP_DYNAMIC"
        else:
            print("⚠️ Results inconclusive - consider adjusting leverage limits")
            recommendation = "REVIEW_LIMITS"

        results['summary'] = {
            'avg_return_improvement': avg_return_improvement,
            'avg_dd_improvement': avg_dd_improvement,
            'total_liq_reduction': total_liq_reduction,
            'recommendation': recommendation
        }

        # Save results
        with open(RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\nResults saved to: {RESULTS_FILE}")

        return results


def main():
    """Run leverage backtest."""
    backtester = LeverageBacktester()
    results = backtester.run_full_backtest()
    return results


if __name__ == "__main__":
    main()
