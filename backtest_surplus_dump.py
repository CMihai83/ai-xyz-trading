#!/usr/bin/env python3
"""
Surplus Dump Optimization Backtest
==================================
Tests different stage 1/stage 2 threshold combinations to find optimal settings.

Current Config:
- Stage 1: 85% of peak → dump 50% of surplus
- Stage 2: 30% of peak → dump remaining 50%

Test Matrix:
- Stage 1: [90%, 85%, 80%, 75%, 70%]
- Stage 2: [40%, 35%, 30%, 25%, 20%]

Scenarios:
1. Gradual Profit Decay - Slow decline from peak
2. Sharp Reversal - Quick drop after peak
3. V-Shape Recovery - Drop then bounce back
4. Multiple Peaks - Price oscillates with multiple highs
5. Trend Continuation - Price keeps rising after initial peak

Author: Claude + Grok Consortium
Version: 1.0.0
Date: January 14, 2026
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from enum import Enum
import json
from itertools import product


class Scenario(Enum):
    GRADUAL_DECAY = "gradual_decay"
    SHARP_REVERSAL = "sharp_reversal"
    V_SHAPE_RECOVERY = "v_shape_recovery"
    MULTIPLE_PEAKS = "multiple_peaks"
    TREND_CONTINUATION = "trend_continuation"
    CHOPPY_PROFIT = "choppy_profit"


@dataclass
class SurplusDumpConfig:
    """Configuration for surplus dump thresholds"""
    stage1_threshold: float  # % of peak to trigger stage 1 (e.g., 0.85 = 85%)
    stage2_threshold: float  # % of peak to trigger stage 2 (e.g., 0.30 = 30%)
    stage1_dump_pct: float = 0.50  # % of surplus to dump in stage 1
    stage2_dump_pct: float = 0.50  # % of remaining surplus to dump in stage 2


@dataclass
class BacktestResult:
    """Results from a single backtest run"""
    config: SurplusDumpConfig
    scenario: str
    total_profit_captured: float  # Total $ captured across all dumps
    profit_capture_rate: float    # % of peak profit captured
    avg_exit_level: float         # Average % of peak at exit
    stage1_triggers: int          # How many times stage 1 triggered
    stage2_triggers: int          # How many times stage 2 triggered
    full_exits: int               # How many positions fully exited
    missed_recoveries: int        # Times we dumped but price recovered


class SurplusDumpBacktest:
    """
    Backtests surplus dump strategies under various market conditions.

    Key Metrics:
    1. Profit Capture Rate: How much of peak profit is locked in
    2. Exit Level: At what % of peak we exit (higher = better)
    3. Recovery Miss Rate: How often we dump and miss a recovery
    """

    def __init__(self, leverage: int = 5, position_size_usd: float = 10.0):
        self.leverage = leverage
        self.position_size_usd = position_size_usd
        self.base_price = 100.0

    def generate_scenario(self, scenario: Scenario, num_periods: int = 200) -> np.ndarray:
        """Generate price series for different market scenarios"""
        np.random.seed(None)  # Ensure randomness

        if scenario == Scenario.GRADUAL_DECAY:
            # Price rises to peak then slowly declines
            # Entry at 100, peak at ~115, slow decline to ~95
            rise = np.linspace(0, 15, num_periods // 3)
            peak_hold = np.ones(num_periods // 6) * 15
            decay = np.linspace(15, -5, num_periods - len(rise) - len(peak_hold))
            base = np.concatenate([rise, peak_hold, decay])
            noise = np.random.normal(0, 0.5, len(base))
            prices = self.base_price + base + noise

        elif scenario == Scenario.SHARP_REVERSAL:
            # Price rises to peak then drops quickly
            # Entry at 100, peak at ~120, quick drop to ~85
            rise = np.linspace(0, 20, num_periods // 3)
            sharp_drop = np.linspace(20, -15, num_periods // 4)
            bottom = np.ones(num_periods - len(rise) - len(sharp_drop)) * -15
            base = np.concatenate([rise, sharp_drop, bottom])
            noise = np.random.normal(0, 0.8, len(base))
            prices = self.base_price + base + noise

        elif scenario == Scenario.V_SHAPE_RECOVERY:
            # Price rises, drops, then recovers past original peak
            # Entry at 100, peak at ~112, drop to ~95, recover to ~118
            rise1 = np.linspace(0, 12, num_periods // 4)
            drop = np.linspace(12, -5, num_periods // 4)
            recovery = np.linspace(-5, 18, num_periods - len(rise1) - len(drop))
            base = np.concatenate([rise1, drop, recovery])
            noise = np.random.normal(0, 0.6, len(base))
            prices = self.base_price + base + noise

        elif scenario == Scenario.MULTIPLE_PEAKS:
            # Price oscillates with multiple peaks
            # Entry at 100, oscillates between 95-115 with multiple peaks
            t = np.linspace(0, 4 * np.pi, num_periods)
            base_trend = np.linspace(0, 5, num_periods)  # Slight upward trend
            oscillation = 10 * np.sin(t) + 5 * np.sin(2 * t)
            noise = np.random.normal(0, 0.5, num_periods)
            prices = self.base_price + base_trend + oscillation + noise

        elif scenario == Scenario.TREND_CONTINUATION:
            # Price keeps rising after initial pause
            # Entry at 100, pause at ~110, continues to ~130
            rise1 = np.linspace(0, 10, num_periods // 4)
            pause = np.ones(num_periods // 4) * 10 + np.random.normal(0, 1, num_periods // 4)
            rise2 = np.linspace(10, 30, num_periods - len(rise1) - len(pause))
            base = np.concatenate([rise1, pause, rise2])
            noise = np.random.normal(0, 0.7, len(base))
            prices = self.base_price + base + noise

        elif scenario == Scenario.CHOPPY_PROFIT:
            # Choppy price action around breakeven to small profit
            # Entry at 100, choppy between 98-108
            noise = np.random.normal(0, 3, num_periods)
            trend = np.linspace(0, 5, num_periods)
            prices = self.base_price + trend + noise

        else:
            raise ValueError(f"Unknown scenario: {scenario}")

        return np.maximum(prices, 1)  # Ensure positive prices

    def calc_upnl(self, entry: float, current: float) -> Tuple[float, float]:
        """Calculate UPNL in $ and %"""
        price_change_pct = (current - entry) / entry
        upnl_pct = price_change_pct * self.leverage
        upnl_usd = self.position_size_usd * upnl_pct
        return upnl_usd, upnl_pct

    def simulate_surplus_dump(
        self,
        prices: np.ndarray,
        config: SurplusDumpConfig,
        has_averaged: bool = True
    ) -> Dict:
        """
        Simulate surplus dump strategy on price series.

        Assumes position entered at prices[0] and has averaged (has surplus to dump).
        """
        entry_price = prices[0]

        # Position tracking
        original_size = 1.0  # Original position
        surplus_size = 0.5 if has_averaged else 0  # Surplus from averaging
        current_size = original_size + surplus_size

        # State tracking
        peak_upnl = 0.0
        dump_stage = 0
        total_captured = 0.0
        stage1_triggered = False
        stage2_triggered = False

        # For analysis
        dump_events = []
        final_position_value = 0.0
        peak_seen = 0.0

        for i, price in enumerate(prices):
            upnl_usd, upnl_pct = self.calc_upnl(entry_price, price)

            # Track peak
            if upnl_usd > peak_upnl:
                peak_upnl = upnl_usd
                peak_seen = peak_upnl

            # No surplus to dump
            if surplus_size <= 0:
                continue

            # Minimum profit threshold ($0.10)
            if peak_upnl < 0.10:
                continue

            # Stage 1: First dump
            if dump_stage == 0 and upnl_usd <= peak_upnl * config.stage1_threshold:
                dump_amount = surplus_size * config.stage1_dump_pct
                dump_value = dump_amount * upnl_usd  # Approximate value captured
                total_captured += dump_value
                surplus_size -= dump_amount
                current_size -= dump_amount
                dump_stage = 1
                stage1_triggered = True
                dump_events.append({
                    'stage': 1,
                    'period': i,
                    'price': price,
                    'upnl': upnl_usd,
                    'peak': peak_upnl,
                    'pct_of_peak': upnl_usd / peak_upnl if peak_upnl > 0 else 0,
                    'amount_dumped': dump_amount,
                    'value_captured': dump_value
                })

            # Stage 2: Second dump
            elif dump_stage == 1 and upnl_usd <= peak_upnl * config.stage2_threshold:
                dump_amount = surplus_size * config.stage2_dump_pct
                dump_value = dump_amount * upnl_usd
                total_captured += dump_value
                surplus_size -= dump_amount
                current_size -= dump_amount
                dump_stage = 2
                stage2_triggered = True
                dump_events.append({
                    'stage': 2,
                    'period': i,
                    'price': price,
                    'upnl': upnl_usd,
                    'peak': peak_upnl,
                    'pct_of_peak': upnl_usd / peak_upnl if peak_upnl > 0 else 0,
                    'amount_dumped': dump_amount,
                    'value_captured': dump_value
                })

        # Calculate final position value (remaining position at end)
        final_upnl, _ = self.calc_upnl(entry_price, prices[-1])
        final_position_value = current_size * final_upnl

        # Total value = captured + remaining
        total_value = total_captured + final_position_value

        # Calculate metrics
        profit_capture_rate = total_captured / peak_seen if peak_seen > 0 else 0

        # Check if we missed a recovery (dumped then price went higher)
        missed_recovery = False
        if dump_events:
            last_dump_period = dump_events[-1]['period']
            post_dump_max = max(prices[last_dump_period:]) if last_dump_period < len(prices) else prices[-1]
            dump_price = dump_events[-1]['price']
            if post_dump_max > dump_price * 1.05:  # 5% recovery threshold
                missed_recovery = True

        return {
            'total_captured': total_captured,
            'final_position_value': final_position_value,
            'total_value': total_value,
            'peak_upnl': peak_seen,
            'profit_capture_rate': profit_capture_rate,
            'stage1_triggered': stage1_triggered,
            'stage2_triggered': stage2_triggered,
            'dump_events': dump_events,
            'missed_recovery': missed_recovery,
            'avg_exit_level': np.mean([e['pct_of_peak'] for e in dump_events]) if dump_events else 0
        }

    def run_scenario_test(
        self,
        scenario: Scenario,
        config: SurplusDumpConfig,
        num_runs: int = 50
    ) -> BacktestResult:
        """Run multiple simulations of a scenario with given config"""

        results = []
        for _ in range(num_runs):
            prices = self.generate_scenario(scenario)
            result = self.simulate_surplus_dump(prices, config)
            results.append(result)

        # Aggregate results
        total_profit_captured = sum(r['total_captured'] for r in results)
        avg_capture_rate = np.mean([r['profit_capture_rate'] for r in results])
        avg_exit_level = np.mean([r['avg_exit_level'] for r in results if r['avg_exit_level'] > 0])
        stage1_triggers = sum(1 for r in results if r['stage1_triggered'])
        stage2_triggers = sum(1 for r in results if r['stage2_triggered'])
        full_exits = sum(1 for r in results if r['stage1_triggered'] and r['stage2_triggered'])
        missed_recoveries = sum(1 for r in results if r['missed_recovery'])

        return BacktestResult(
            config=config,
            scenario=scenario.value,
            total_profit_captured=total_profit_captured,
            profit_capture_rate=avg_capture_rate,
            avg_exit_level=avg_exit_level if not np.isnan(avg_exit_level) else 0,
            stage1_triggers=stage1_triggers,
            stage2_triggers=stage2_triggers,
            full_exits=full_exits,
            missed_recoveries=missed_recoveries
        )

    def run_full_backtest(self, num_runs: int = 50) -> Dict:
        """
        Run full backtest across all scenarios and configurations.
        Returns comparison matrix.
        """
        # Configuration matrix
        stage1_thresholds = [0.90, 0.85, 0.80, 0.75, 0.70]
        stage2_thresholds = [0.40, 0.35, 0.30, 0.25, 0.20]

        scenarios = [
            Scenario.GRADUAL_DECAY,
            Scenario.SHARP_REVERSAL,
            Scenario.V_SHAPE_RECOVERY,
            Scenario.MULTIPLE_PEAKS,
            Scenario.TREND_CONTINUATION,
            Scenario.CHOPPY_PROFIT
        ]

        all_results = {}

        print("=" * 80)
        print("SURPLUS DUMP OPTIMIZATION BACKTEST")
        print("=" * 80)
        print(f"Testing {len(stage1_thresholds) * len(stage2_thresholds)} configurations")
        print(f"Across {len(scenarios)} scenarios with {num_runs} runs each")
        print()

        for s1, s2 in product(stage1_thresholds, stage2_thresholds):
            config = SurplusDumpConfig(
                stage1_threshold=s1,
                stage2_threshold=s2
            )
            config_key = f"{int(s1*100)}/{int(s2*100)}"
            all_results[config_key] = {}

            print(f"Testing config {config_key}...", end=" ")

            for scenario in scenarios:
                result = self.run_scenario_test(scenario, config, num_runs)
                all_results[config_key][scenario.value] = {
                    'profit_captured': result.total_profit_captured,
                    'capture_rate': result.profit_capture_rate,
                    'avg_exit_level': result.avg_exit_level,
                    'stage1_triggers': result.stage1_triggers,
                    'stage2_triggers': result.stage2_triggers,
                    'missed_recoveries': result.missed_recoveries
                }

            # Calculate aggregate score for this config
            total_captured = sum(
                all_results[config_key][s.value]['profit_captured']
                for s in scenarios
            )
            avg_capture_rate = np.mean([
                all_results[config_key][s.value]['capture_rate']
                for s in scenarios
            ])
            total_missed = sum(
                all_results[config_key][s.value]['missed_recoveries']
                for s in scenarios
            )

            all_results[config_key]['_aggregate'] = {
                'total_profit_captured': total_captured,
                'avg_capture_rate': avg_capture_rate,
                'total_missed_recoveries': total_missed
            }

            print(f"Score: {total_captured:.2f}")

        return all_results

    def print_results(self, results: Dict):
        """Print formatted results comparison"""

        print("\n" + "=" * 80)
        print("RESULTS SUMMARY")
        print("=" * 80)

        # Sort configs by aggregate score
        sorted_configs = sorted(
            results.keys(),
            key=lambda k: results[k].get('_aggregate', {}).get('total_profit_captured', 0),
            reverse=True
        )

        print("\n📊 CONFIGURATION RANKING (by total profit captured):\n")
        print(f"{'Rank':<6} {'Config':<10} {'Total Profit':<15} {'Capture Rate':<15} {'Missed Recoveries':<20}")
        print("-" * 70)

        for rank, config_key in enumerate(sorted_configs, 1):
            agg = results[config_key].get('_aggregate', {})
            print(f"{rank:<6} {config_key:<10} ${agg.get('total_profit_captured', 0):<14.2f} "
                  f"{agg.get('avg_capture_rate', 0)*100:<14.1f}% "
                  f"{agg.get('total_missed_recoveries', 0):<20}")

        # Current config comparison
        current = "85/30"
        print(f"\n📍 Current Config ({current}):")
        if current in results:
            agg = results[current]['_aggregate']
            current_rank = sorted_configs.index(current) + 1
            print(f"   Rank: #{current_rank} of {len(sorted_configs)}")
            print(f"   Total Profit: ${agg['total_profit_captured']:.2f}")
            print(f"   Capture Rate: {agg['avg_capture_rate']*100:.1f}%")

        # Best config
        best = sorted_configs[0]
        print(f"\n🏆 Best Config ({best}):")
        agg = results[best]['_aggregate']
        print(f"   Total Profit: ${agg['total_profit_captured']:.2f}")
        print(f"   Capture Rate: {agg['avg_capture_rate']*100:.1f}%")
        print(f"   Missed Recoveries: {agg['total_missed_recoveries']}")

        # Per-scenario breakdown for best config
        print(f"\n📈 Best Config Scenario Breakdown:")
        for scenario in Scenario:
            if scenario.value in results[best]:
                data = results[best][scenario.value]
                print(f"   {scenario.value:<20}: ${data['profit_captured']:.2f} "
                      f"(capture: {data['capture_rate']*100:.1f}%, "
                      f"missed: {data['missed_recoveries']})")

        # Improvement recommendation
        if best != current:
            current_profit = results[current]['_aggregate']['total_profit_captured']
            best_profit = results[best]['_aggregate']['total_profit_captured']
            improvement = ((best_profit - current_profit) / current_profit) * 100 if current_profit > 0 else 0
            print(f"\n✅ RECOMMENDATION: Switch from {current} to {best}")
            print(f"   Expected improvement: {improvement:+.1f}%")
        else:
            print(f"\n✅ Current config ({current}) is already optimal!")

        return sorted_configs[0]  # Return best config


def main():
    """Run surplus dump optimization backtest"""
    backtest = SurplusDumpBacktest(leverage=5, position_size_usd=10.0)

    # Run full backtest
    results = backtest.run_full_backtest(num_runs=50)

    # Print results
    best_config = backtest.print_results(results)

    # Save results
    with open('surplus_dump_backtest_results.json', 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n✅ Results saved to surplus_dump_backtest_results.json")

    return results, best_config


if __name__ == "__main__":
    main()
