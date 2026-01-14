#!/usr/bin/env python3
"""
Averaging Trigger Optimization Backtest
========================================
Tests different averaging trigger thresholds to find optimal settings.

Current Config:
- Averaging trigger: -25% UPNL

Test Matrix:
- Thresholds: [-15%, -20%, -25%, -30%, -35%, -40%]

Trade-offs:
- Lower threshold (e.g., -35%): Wait longer, bigger drawdown, more certain dip is real
- Higher threshold (e.g., -15%): Average sooner, less drawdown, might average on minor dips

Scenarios:
1. V-Shape Recovery - Dip then full recovery (averaging helps)
2. Continued Downtrend - Price keeps falling (averaging hurts)
3. Dead Cat Bounce - Small recovery then continued fall
4. Choppy Sideways - Multiple small dips and recoveries
5. Flash Crash Recovery - Sharp drop then gradual recovery
6. Slow Bleed - Gradual decline over time

Author: Claude + Grok Consortium
Version: 1.0.0
Date: January 14, 2026
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from enum import Enum
import json


class Scenario(Enum):
    V_SHAPE_RECOVERY = "v_shape_recovery"
    CONTINUED_DOWNTREND = "continued_downtrend"
    DEAD_CAT_BOUNCE = "dead_cat_bounce"
    CHOPPY_SIDEWAYS = "choppy_sideways"
    FLASH_CRASH_RECOVERY = "flash_crash_recovery"
    SLOW_BLEED = "slow_bleed"


@dataclass
class AveragingConfig:
    """Configuration for averaging trigger"""
    trigger_threshold: float  # UPNL % to trigger averaging (e.g., -0.25 = -25%)
    max_averaging_steps: int = 5
    fibonacci_multipliers: List[float] = field(default_factory=lambda: [1.0, 1.618, 2.618, 4.236, 6.854])


@dataclass
class BacktestResult:
    """Results from a single backtest run"""
    config: AveragingConfig
    scenario: str
    final_pnl: float
    max_drawdown: float
    averaging_triggers: int
    avg_entry_price: float
    recovery_rate: float  # % of positions that recovered to profit
    time_to_recovery: float  # Average periods to recover (if recovered)


class AveragingTriggerBacktest:
    """
    Backtests averaging trigger thresholds under various market conditions.

    Key Metrics:
    1. Final PnL: Overall profitability
    2. Max Drawdown: Worst point during position
    3. Recovery Rate: How often averaging leads to profit
    4. Time to Recovery: How long until position recovers
    """

    def __init__(self, leverage: int = 5, initial_position_usd: float = 5.0,
                 averaging_capital: float = 20.0):
        self.leverage = leverage
        self.initial_position_usd = initial_position_usd
        self.averaging_capital = averaging_capital  # Total capital for averaging
        self.base_price = 100.0

    def generate_scenario(self, scenario: Scenario, num_periods: int = 300) -> np.ndarray:
        """Generate price series for different market scenarios"""
        np.random.seed(None)

        if scenario == Scenario.V_SHAPE_RECOVERY:
            # Price drops 30% then recovers to +10% above entry
            drop = np.linspace(0, -30, num_periods // 3)
            bottom = np.ones(num_periods // 6) * -30
            recovery = np.linspace(-30, 10, num_periods - len(drop) - len(bottom))
            base = np.concatenate([drop, bottom, recovery])
            noise = np.random.normal(0, 1, len(base))
            prices = self.base_price * (1 + (base + noise) / 100)

        elif scenario == Scenario.CONTINUED_DOWNTREND:
            # Price drops 50% with small bounces
            trend = np.linspace(0, -50, num_periods)
            bounces = 5 * np.sin(np.linspace(0, 8 * np.pi, num_periods))
            noise = np.random.normal(0, 1, num_periods)
            prices = self.base_price * (1 + (trend + bounces + noise) / 100)

        elif scenario == Scenario.DEAD_CAT_BOUNCE:
            # Drop 25%, recover 10%, then drop another 30%
            drop1 = np.linspace(0, -25, num_periods // 4)
            bounce = np.linspace(-25, -15, num_periods // 6)
            drop2 = np.linspace(-15, -45, num_periods - len(drop1) - len(bounce))
            base = np.concatenate([drop1, bounce, drop2])
            noise = np.random.normal(0, 1, len(base))
            prices = self.base_price * (1 + (base + noise) / 100)

        elif scenario == Scenario.CHOPPY_SIDEWAYS:
            # Oscillates between -20% and +10%
            t = np.linspace(0, 6 * np.pi, num_periods)
            oscillation = 15 * np.sin(t) - 5  # Centers around -5%
            noise = np.random.normal(0, 2, num_periods)
            prices = self.base_price * (1 + (oscillation + noise) / 100)

        elif scenario == Scenario.FLASH_CRASH_RECOVERY:
            # Sharp 40% drop in 20 periods, then slow recovery over rest
            crash = np.linspace(0, -40, num_periods // 10)
            recovery = np.linspace(-40, 5, num_periods - len(crash))
            base = np.concatenate([crash, recovery])
            noise = np.random.normal(0, 1.5, len(base))
            prices = self.base_price * (1 + (base + noise) / 100)

        elif scenario == Scenario.SLOW_BLEED:
            # Gradual decline with occasional small bounces
            trend = np.linspace(0, -35, num_periods)
            bounces = 3 * np.sin(np.linspace(0, 10 * np.pi, num_periods))
            noise = np.random.normal(0, 0.8, num_periods)
            prices = self.base_price * (1 + (trend + bounces + noise) / 100)

        else:
            raise ValueError(f"Unknown scenario: {scenario}")

        return np.maximum(prices, 1)  # Ensure positive prices

    def calc_position_pnl(self, entry_price: float, current_price: float,
                          position_size: float, side: str = 'long') -> Tuple[float, float]:
        """Calculate position PnL in $ and %"""
        if side == 'long':
            price_change_pct = (current_price - entry_price) / entry_price
        else:
            price_change_pct = (entry_price - current_price) / entry_price

        pnl_pct = price_change_pct * self.leverage
        pnl_usd = position_size * pnl_pct
        return pnl_usd, pnl_pct

    def simulate_averaging(self, prices: np.ndarray, config: AveragingConfig) -> Dict:
        """
        Simulate averaging strategy on price series.

        Fibonacci averaging: Each step adds more capital based on multipliers.
        """
        entry_price = prices[0]

        # Position tracking
        total_position_cost = self.initial_position_usd
        total_position_size = self.initial_position_usd / entry_price
        weighted_entry = entry_price

        # Averaging state
        averaging_step = 0
        capital_used = self.initial_position_usd
        capital_remaining = self.averaging_capital

        # Tracking metrics
        max_drawdown = 0.0
        averaging_events = []
        recovered = False
        recovery_period = None
        peak_pnl = 0.0

        for i, price in enumerate(prices):
            # Calculate current PnL
            pnl_usd, pnl_pct = self.calc_position_pnl(weighted_entry, price, total_position_cost)

            # Track max drawdown
            if pnl_usd < max_drawdown:
                max_drawdown = pnl_usd

            # Track peak and recovery
            if pnl_usd > peak_pnl:
                peak_pnl = pnl_usd

            if not recovered and pnl_usd > 0 and averaging_step > 0:
                recovered = True
                recovery_period = i

            # Check averaging trigger
            if (pnl_pct <= config.trigger_threshold and
                averaging_step < config.max_averaging_steps and
                capital_remaining > 0):

                # Calculate amount to add (Fibonacci-based)
                multiplier = config.fibonacci_multipliers[min(averaging_step, len(config.fibonacci_multipliers) - 1)]
                add_amount = min(
                    self.initial_position_usd * multiplier,
                    capital_remaining
                )

                if add_amount > 0:
                    # Add to position
                    add_size = add_amount / price

                    # Update weighted entry
                    old_total = total_position_size * weighted_entry
                    new_total = old_total + (add_size * price)
                    total_position_size += add_size
                    weighted_entry = new_total / total_position_size

                    total_position_cost += add_amount
                    capital_used += add_amount
                    capital_remaining -= add_amount
                    averaging_step += 1

                    averaging_events.append({
                        'period': i,
                        'price': price,
                        'pnl_pct': pnl_pct,
                        'amount_added': add_amount,
                        'new_entry': weighted_entry,
                        'step': averaging_step
                    })

        # Calculate final PnL
        final_pnl, final_pnl_pct = self.calc_position_pnl(
            weighted_entry, prices[-1], total_position_cost
        )

        return {
            'final_pnl': final_pnl,
            'final_pnl_pct': final_pnl_pct,
            'max_drawdown': max_drawdown,
            'averaging_triggers': averaging_step,
            'avg_entry_price': weighted_entry,
            'original_entry': entry_price,
            'entry_improvement': (entry_price - weighted_entry) / entry_price if weighted_entry < entry_price else 0,
            'recovered': recovered,
            'recovery_period': recovery_period,
            'total_capital_used': capital_used,
            'averaging_events': averaging_events
        }

    def simulate_no_averaging(self, prices: np.ndarray) -> Dict:
        """Simulate holding without averaging (baseline comparison)"""
        entry_price = prices[0]
        position_cost = self.initial_position_usd

        max_drawdown = 0.0

        for price in prices:
            pnl_usd, _ = self.calc_position_pnl(entry_price, price, position_cost)
            if pnl_usd < max_drawdown:
                max_drawdown = pnl_usd

        final_pnl, final_pnl_pct = self.calc_position_pnl(entry_price, prices[-1], position_cost)

        return {
            'final_pnl': final_pnl,
            'final_pnl_pct': final_pnl_pct,
            'max_drawdown': max_drawdown,
            'total_capital_used': position_cost
        }

    def run_scenario_test(self, scenario: Scenario, config: AveragingConfig,
                          num_runs: int = 100) -> Dict:
        """Run multiple simulations of a scenario with given config"""

        averaging_results = []
        baseline_results = []

        for _ in range(num_runs):
            prices = self.generate_scenario(scenario)

            # Run with averaging
            avg_result = self.simulate_averaging(prices, config)
            averaging_results.append(avg_result)

            # Run baseline (no averaging)
            baseline_result = self.simulate_no_averaging(prices)
            baseline_results.append(baseline_result)

        # Aggregate averaging results
        avg_final_pnl = np.mean([r['final_pnl'] for r in averaging_results])
        avg_max_dd = np.mean([r['max_drawdown'] for r in averaging_results])
        avg_triggers = np.mean([r['averaging_triggers'] for r in averaging_results])
        recovery_rate = np.mean([1 if r['recovered'] else 0 for r in averaging_results])
        avg_recovery_time = np.mean([r['recovery_period'] for r in averaging_results if r['recovery_period']])
        avg_capital_used = np.mean([r['total_capital_used'] for r in averaging_results])

        # Aggregate baseline results
        baseline_final_pnl = np.mean([r['final_pnl'] for r in baseline_results])
        baseline_max_dd = np.mean([r['max_drawdown'] for r in baseline_results])
        baseline_capital = np.mean([r['total_capital_used'] for r in baseline_results])

        # Calculate improvement vs baseline
        pnl_improvement = avg_final_pnl - baseline_final_pnl
        dd_change = avg_max_dd - baseline_max_dd  # More negative = worse

        # Capital efficiency: PnL per dollar used
        avg_efficiency = avg_final_pnl / avg_capital_used if avg_capital_used > 0 else 0
        baseline_efficiency = baseline_final_pnl / baseline_capital if baseline_capital > 0 else 0

        return {
            'averaging': {
                'final_pnl': avg_final_pnl,
                'max_drawdown': avg_max_dd,
                'avg_triggers': avg_triggers,
                'recovery_rate': recovery_rate,
                'avg_recovery_time': avg_recovery_time if not np.isnan(avg_recovery_time) else 0,
                'capital_used': avg_capital_used,
                'efficiency': avg_efficiency
            },
            'baseline': {
                'final_pnl': baseline_final_pnl,
                'max_drawdown': baseline_max_dd,
                'capital_used': baseline_capital,
                'efficiency': baseline_efficiency
            },
            'improvement': {
                'pnl': pnl_improvement,
                'pnl_pct': (pnl_improvement / abs(baseline_final_pnl) * 100) if baseline_final_pnl != 0 else 0,
                'drawdown': dd_change,
                'efficiency': avg_efficiency - baseline_efficiency
            }
        }

    def run_full_backtest(self, num_runs: int = 100) -> Dict:
        """Run full backtest across all scenarios and thresholds"""

        thresholds = [-0.15, -0.20, -0.25, -0.30, -0.35, -0.40]
        scenarios = list(Scenario)

        all_results = {}

        print("=" * 80)
        print("AVERAGING TRIGGER OPTIMIZATION BACKTEST")
        print("=" * 80)
        print(f"Testing {len(thresholds)} thresholds across {len(scenarios)} scenarios")
        print(f"Runs per configuration: {num_runs}")
        print()

        for threshold in thresholds:
            config = AveragingConfig(trigger_threshold=threshold)
            threshold_key = f"{int(threshold * 100)}%"
            all_results[threshold_key] = {}

            print(f"Testing threshold {threshold_key}...", end=" ")

            scenario_pnls = []
            for scenario in scenarios:
                result = self.run_scenario_test(scenario, config, num_runs)
                all_results[threshold_key][scenario.value] = result
                scenario_pnls.append(result['averaging']['final_pnl'])

            total_pnl = sum(scenario_pnls)
            all_results[threshold_key]['_aggregate'] = {
                'total_pnl': total_pnl,
                'avg_pnl': np.mean(scenario_pnls)
            }

            print(f"Total PnL: ${total_pnl:.2f}")

        return all_results

    def print_results(self, results: Dict):
        """Print formatted results comparison"""

        print("\n" + "=" * 80)
        print("RESULTS SUMMARY")
        print("=" * 80)

        # Sort by total PnL
        sorted_thresholds = sorted(
            [k for k in results.keys() if not k.startswith('_')],
            key=lambda k: results[k].get('_aggregate', {}).get('total_pnl', 0),
            reverse=True
        )

        print("\n📊 THRESHOLD RANKING (by total PnL):\n")
        print(f"{'Rank':<6} {'Threshold':<12} {'Total PnL':<12} {'Avg PnL':<12} {'vs Baseline':<15}")
        print("-" * 60)

        for rank, threshold_key in enumerate(sorted_thresholds, 1):
            agg = results[threshold_key].get('_aggregate', {})

            # Calculate average improvement vs baseline
            improvements = []
            for scenario in Scenario:
                if scenario.value in results[threshold_key]:
                    imp = results[threshold_key][scenario.value]['improvement']['pnl']
                    improvements.append(imp)
            avg_improvement = np.mean(improvements) if improvements else 0

            print(f"{rank:<6} {threshold_key:<12} ${agg.get('total_pnl', 0):<11.2f} "
                  f"${agg.get('avg_pnl', 0):<11.2f} ${avg_improvement:+.2f}")

        # Current config
        current = "-25%"
        print(f"\n📍 Current Config ({current}):")
        if current in results:
            current_rank = sorted_thresholds.index(current) + 1
            agg = results[current]['_aggregate']
            print(f"   Rank: #{current_rank} of {len(sorted_thresholds)}")
            print(f"   Total PnL: ${agg['total_pnl']:.2f}")

        # Best config
        best = sorted_thresholds[0]
        print(f"\n🏆 Best Config ({best}):")
        agg = results[best]['_aggregate']
        print(f"   Total PnL: ${agg['total_pnl']:.2f}")

        # Per-scenario breakdown for best
        print(f"\n📈 Best Config Scenario Breakdown:")
        for scenario in Scenario:
            if scenario.value in results[best]:
                data = results[best][scenario.value]
                avg = data['averaging']
                imp = data['improvement']
                print(f"   {scenario.value:<25}: PnL ${avg['final_pnl']:>7.2f}, "
                      f"Recovery {avg['recovery_rate']*100:>5.1f}%, "
                      f"vs baseline {imp['pnl']:+.2f}")

        # Recommendation
        if best != current:
            current_pnl = results[current]['_aggregate']['total_pnl']
            best_pnl = results[best]['_aggregate']['total_pnl']
            improvement = ((best_pnl - current_pnl) / abs(current_pnl)) * 100 if current_pnl != 0 else 0
            print(f"\n✅ RECOMMENDATION: Change from {current} to {best}")
            print(f"   Expected improvement: {improvement:+.1f}%")
        else:
            print(f"\n✅ Current config ({current}) is already optimal!")

        return sorted_thresholds[0]


def main():
    """Run averaging trigger optimization backtest"""
    backtest = AveragingTriggerBacktest(
        leverage=5,
        initial_position_usd=5.0,
        averaging_capital=20.0
    )

    results = backtest.run_full_backtest(num_runs=100)
    best_config = backtest.print_results(results)

    # Save results
    with open('averaging_trigger_backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to averaging_trigger_backtest_results.json")

    return results, best_config


if __name__ == "__main__":
    main()
