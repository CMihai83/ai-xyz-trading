#!/usr/bin/env python3
"""
Adverse/Black Swan Market Regime Backtest
==========================================
Tests 50% take profit threshold for adverse and black swan market conditions.

This backtest specifically targets:
1. HIGH_VOLATILITY regime - ATR ratio > 2.0
2. CRISIS regime - Extreme volatility / black swan events

Test Matrix:
- Stage 1 Thresholds: [85%, 75%, 65%, 50%] (current vs aggressive)
- Stage 2 Thresholds: [40%, 35%, 30%, 25%, 20%]

Scenarios:
1. Flash Crash - Extreme 30%+ drop
2. High Volatility Chop - Large swings both directions
3. Black Swan Dump - Gradual then sudden collapse
4. Volatility Spike Recovery - High vol then stabilize
5. Multi-leg Crash - Stair-step decline

Author: Claude + Grok Consortium
Version: 1.0.0
Date: January 16, 2026
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from enum import Enum
import json
from itertools import product
from datetime import datetime


class AdverseScenario(Enum):
    FLASH_CRASH = "flash_crash"
    HIGH_VOL_CHOP = "high_vol_chop"
    BLACK_SWAN_DUMP = "black_swan_dump"
    VOLATILITY_SPIKE_RECOVERY = "volatility_spike_recovery"
    MULTI_LEG_CRASH = "multi_leg_crash"
    EXTREME_WHIPSAW = "extreme_whipsaw"


@dataclass
class SurplusDumpConfig:
    """Configuration for surplus dump thresholds"""
    stage1_threshold: float  # % of peak to trigger stage 1 (e.g., 0.50 = 50%)
    stage2_threshold: float  # % of peak to trigger stage 2 (e.g., 0.30 = 30%)
    stage1_dump_pct: float = 0.50
    stage2_dump_pct: float = 0.50
    regime: str = "ADVERSE"


@dataclass
class BacktestResult:
    """Results from a single backtest run"""
    config: SurplusDumpConfig
    scenario: str
    total_profit_captured: float
    profit_capture_rate: float
    avg_exit_level: float
    stage1_triggers: int
    stage2_triggers: int
    full_exits: int
    missed_recoveries: int
    max_drawdown: float
    recovery_profit: float  # Profit if held through recovery


class AdverseConditionsBacktest:
    """
    Backtests surplus dump strategies specifically for adverse/black swan conditions.

    Key difference from normal backtest:
    - More extreme price movements
    - Higher volatility (ATR ratio > 2.0)
    - Tests aggressive take-profit thresholds (50% instead of 85%)
    """

    def __init__(self, leverage: int = 5, position_size_usd: float = 10.0):
        self.leverage = leverage
        self.position_size_usd = position_size_usd
        self.base_price = 100.0

    def generate_adverse_scenario(self, scenario: AdverseScenario, num_periods: int = 200) -> np.ndarray:
        """Generate price series for adverse/black swan scenarios"""
        np.random.seed(None)

        if scenario == AdverseScenario.FLASH_CRASH:
            # Rapid rise then flash crash (30%+ drop in short period)
            # Entry at 100, peak at ~115, crash to ~75, slight recovery to ~85
            rise = np.linspace(0, 15, num_periods // 5)
            peak_hold = np.ones(num_periods // 10) * 15
            crash = np.linspace(15, -25, num_periods // 8)  # 40% drop
            bottom = np.ones(num_periods // 5) * -25
            recovery = np.linspace(-25, -15, num_periods - len(rise) - len(peak_hold) - len(crash) - len(bottom))
            base = np.concatenate([rise, peak_hold, crash, bottom, recovery])
            noise = np.random.normal(0, 2.0, len(base))  # High volatility noise
            prices = self.base_price + base + noise

        elif scenario == AdverseScenario.HIGH_VOL_CHOP:
            # Large swings in both directions - difficult to time exits
            # Entry at 100, oscillates ±20% with high frequency
            t = np.linspace(0, 8 * np.pi, num_periods)
            primary_wave = 15 * np.sin(t)
            secondary_wave = 8 * np.sin(3 * t)
            tertiary_wave = 4 * np.sin(7 * t)
            noise = np.random.normal(0, 3.0, num_periods)
            prices = self.base_price + primary_wave + secondary_wave + tertiary_wave + noise

        elif scenario == AdverseScenario.BLACK_SWAN_DUMP:
            # Gradual rise, then sudden catastrophic drop (black swan)
            # Entry at 100, gradual rise to ~120, sudden drop to ~60
            gradual_rise = np.linspace(0, 20, num_periods // 2)
            small_dip = np.linspace(20, 15, num_periods // 10)
            black_swan = np.linspace(15, -40, num_periods // 10)  # Sudden 55% drop
            bottom = np.ones(num_periods - len(gradual_rise) - len(small_dip) - len(black_swan)) * -40
            base = np.concatenate([gradual_rise, small_dip, black_swan, bottom])
            noise = np.random.normal(0, 1.5, len(base))
            prices = self.base_price + base + noise

        elif scenario == AdverseScenario.VOLATILITY_SPIKE_RECOVERY:
            # High volatility event then stabilization
            # Tests if early exit misses recovery
            normal_rise = np.linspace(0, 10, num_periods // 4)
            vol_spike = np.random.normal(0, 8, num_periods // 4) + 10  # High vol period
            recovery = np.linspace(np.mean(vol_spike[-5:]), 25, num_periods // 2)
            base = np.concatenate([normal_rise, vol_spike, recovery])
            if len(base) < num_periods:
                base = np.concatenate([base, np.ones(num_periods - len(base)) * 25])
            prices = self.base_price + base[:num_periods]

        elif scenario == AdverseScenario.MULTI_LEG_CRASH:
            # Stair-step decline with dead cat bounces
            # Entry at 100, drops in stages: 110 -> 95 -> 100 -> 85 -> 90 -> 70
            leg1_up = np.linspace(0, 10, num_periods // 8)
            leg1_down = np.linspace(10, -5, num_periods // 8)
            bounce1 = np.linspace(-5, 0, num_periods // 8)
            leg2_down = np.linspace(0, -15, num_periods // 8)
            bounce2 = np.linspace(-15, -10, num_periods // 8)
            leg3_down = np.linspace(-10, -30, num_periods // 8)
            final = np.ones(num_periods - 6 * (num_periods // 8)) * -30
            base = np.concatenate([leg1_up, leg1_down, bounce1, leg2_down, bounce2, leg3_down, final])
            noise = np.random.normal(0, 2.0, len(base))
            prices = self.base_price + base[:num_periods] + noise[:num_periods]

        elif scenario == AdverseScenario.EXTREME_WHIPSAW:
            # Multiple rapid reversals - tests premature exit cost
            # Entry at 100, rapid swings between profit and loss
            t = np.linspace(0, 6 * np.pi, num_periods)
            whipsaw = 20 * np.sin(t) * np.exp(-t / (4 * np.pi))  # Dampening oscillation
            trend = np.linspace(0, -10, num_periods)  # Slight downward trend
            noise = np.random.normal(0, 4.0, num_periods)
            prices = self.base_price + whipsaw + trend + noise

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
        """Simulate surplus dump strategy on price series"""
        entry_price = prices[0]

        # Position tracking
        original_size = 1.0
        surplus_size = 0.5 if has_averaged else 0
        current_size = original_size + surplus_size

        # State tracking
        peak_upnl = 0.0
        dump_stage = 0
        total_captured = 0.0
        stage1_triggered = False
        stage2_triggered = False

        # For analysis
        dump_events = []
        max_drawdown = 0.0
        peak_seen = 0.0
        min_upnl = float('inf')

        for i, price in enumerate(prices):
            upnl_usd, upnl_pct = self.calc_upnl(entry_price, price)

            # Track peak and drawdown
            if upnl_usd > peak_upnl:
                peak_upnl = upnl_usd
                peak_seen = peak_upnl

            if upnl_usd < min_upnl:
                min_upnl = upnl_usd

            current_drawdown = (peak_upnl - upnl_usd) / peak_upnl if peak_upnl > 0 else 0
            max_drawdown = max(max_drawdown, current_drawdown)

            # No surplus to dump
            if surplus_size <= 0:
                continue

            # Minimum profit threshold ($0.10)
            if peak_upnl < 0.10:
                continue

            # Stage 1: First dump
            if dump_stage == 0 and upnl_usd <= peak_upnl * config.stage1_threshold:
                dump_amount = surplus_size * config.stage1_dump_pct
                dump_value = dump_amount * upnl_usd
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

        # Calculate final position value
        final_upnl, _ = self.calc_upnl(entry_price, prices[-1])
        final_position_value = current_size * final_upnl
        total_value = total_captured + final_position_value

        # Calculate what we would have if we held (no dump)
        hold_value = (original_size + 0.5) * final_upnl  # Full position held

        # Check if we missed a recovery
        missed_recovery = False
        recovery_profit = 0.0
        if dump_events:
            last_dump_period = dump_events[-1]['period']
            if last_dump_period < len(prices) - 1:
                post_dump_max_price = max(prices[last_dump_period:])
                post_dump_max_upnl, _ = self.calc_upnl(entry_price, post_dump_max_price)
                dump_upnl = dump_events[-1]['upnl']
                if post_dump_max_upnl > dump_upnl * 1.10:  # 10% recovery threshold
                    missed_recovery = True
                    recovery_profit = post_dump_max_upnl - dump_upnl

        profit_capture_rate = total_captured / peak_seen if peak_seen > 0 else 0

        return {
            'total_captured': total_captured,
            'final_position_value': final_position_value,
            'total_value': total_value,
            'hold_value': hold_value,
            'peak_upnl': peak_seen,
            'min_upnl': min_upnl,
            'profit_capture_rate': profit_capture_rate,
            'stage1_triggered': stage1_triggered,
            'stage2_triggered': stage2_triggered,
            'dump_events': dump_events,
            'missed_recovery': missed_recovery,
            'recovery_profit': recovery_profit,
            'max_drawdown': max_drawdown,
            'avg_exit_level': np.mean([e['pct_of_peak'] for e in dump_events]) if dump_events else 0,
            'dump_vs_hold': total_value - hold_value  # Positive = dump strategy better
        }

    def run_scenario_test(
        self,
        scenario: AdverseScenario,
        config: SurplusDumpConfig,
        num_runs: int = 100
    ) -> Dict:
        """Run multiple simulations of a scenario with given config"""

        results = []
        for _ in range(num_runs):
            prices = self.generate_adverse_scenario(scenario)
            result = self.simulate_surplus_dump(prices, config)
            results.append(result)

        # Aggregate results
        return {
            'total_profit_captured': sum(r['total_captured'] for r in results),
            'avg_capture_rate': np.mean([r['profit_capture_rate'] for r in results]),
            'avg_exit_level': np.mean([r['avg_exit_level'] for r in results if r['avg_exit_level'] > 0]),
            'stage1_triggers': sum(1 for r in results if r['stage1_triggered']),
            'stage2_triggers': sum(1 for r in results if r['stage2_triggered']),
            'full_exits': sum(1 for r in results if r['stage1_triggered'] and r['stage2_triggered']),
            'missed_recoveries': sum(1 for r in results if r['missed_recovery']),
            'avg_max_drawdown': np.mean([r['max_drawdown'] for r in results]),
            'dump_vs_hold_advantage': sum(r['dump_vs_hold'] for r in results),
            'total_value': sum(r['total_value'] for r in results),
            'hold_value': sum(r['hold_value'] for r in results)
        }

    def run_full_backtest(self, num_runs: int = 100) -> Dict:
        """Run backtest with focus on 50% take profit threshold for adverse conditions"""

        # Configuration matrix - testing aggressive 50% threshold
        stage1_thresholds = [0.85, 0.75, 0.65, 0.50]  # Testing down to 50%
        stage2_thresholds = [0.40, 0.35, 0.30, 0.25, 0.20]

        scenarios = list(AdverseScenario)

        all_results = {}

        print("=" * 80)
        print("ADVERSE/BLACK SWAN CONDITIONS BACKTEST")
        print("Testing 50% Take Profit Threshold")
        print("=" * 80)
        print(f"Testing {len(stage1_thresholds) * len(stage2_thresholds)} configurations")
        print(f"Across {len(scenarios)} adverse scenarios with {num_runs} runs each")
        print(f"Leverage: {self.leverage}x | Position Size: ${self.position_size_usd}")
        print()

        for s1, s2 in product(stage1_thresholds, stage2_thresholds):
            config = SurplusDumpConfig(
                stage1_threshold=s1,
                stage2_threshold=s2,
                regime="ADVERSE/BLACK_SWAN"
            )
            config_key = f"{int(s1*100)}/{int(s2*100)}"
            all_results[config_key] = {}

            print(f"Testing config {config_key}...", end=" ", flush=True)

            for scenario in scenarios:
                result = self.run_scenario_test(scenario, config, num_runs)
                all_results[config_key][scenario.value] = result

            # Calculate aggregate score for this config
            total_value = sum(
                all_results[config_key][s.value]['total_value']
                for s in scenarios
            )
            hold_value = sum(
                all_results[config_key][s.value]['hold_value']
                for s in scenarios
            )
            dump_advantage = sum(
                all_results[config_key][s.value]['dump_vs_hold_advantage']
                for s in scenarios
            )
            avg_capture_rate = np.mean([
                all_results[config_key][s.value]['avg_capture_rate']
                for s in scenarios
            ])
            total_missed = sum(
                all_results[config_key][s.value]['missed_recoveries']
                for s in scenarios
            )

            all_results[config_key]['_aggregate'] = {
                'total_value': total_value,
                'hold_value': hold_value,
                'dump_advantage': dump_advantage,
                'avg_capture_rate': avg_capture_rate,
                'total_missed_recoveries': total_missed
            }

            status = "+" if dump_advantage > 0 else "-"
            print(f"Value: ${total_value:.2f} | vs Hold: {status}${abs(dump_advantage):.2f}")

        return all_results

    def print_results(self, results: Dict):
        """Print formatted results comparison"""

        print("\n" + "=" * 80)
        print("ADVERSE/BLACK SWAN BACKTEST RESULTS")
        print("=" * 80)

        # Sort configs by dump_advantage (positive = better than holding)
        sorted_configs = sorted(
            results.keys(),
            key=lambda k: results[k].get('_aggregate', {}).get('dump_advantage', float('-inf')),
            reverse=True
        )

        print("\n📊 CONFIGURATION RANKING (by advantage over holding):\n")
        print(f"{'Rank':<6} {'Config':<10} {'Total Value':<14} {'vs Hold':<12} {'Capture Rate':<14} {'Missed':<8}")
        print("-" * 70)

        for rank, config_key in enumerate(sorted_configs, 1):
            agg = results[config_key].get('_aggregate', {})
            advantage = agg.get('dump_advantage', 0)
            sign = "+" if advantage >= 0 else ""
            print(f"{rank:<6} {config_key:<10} ${agg.get('total_value', 0):<13.2f} "
                  f"{sign}${advantage:<11.2f} "
                  f"{agg.get('avg_capture_rate', 0)*100:<13.1f}% "
                  f"{agg.get('total_missed_recoveries', 0):<8}")

        # Current config (85/40) comparison
        current = "85/40"
        print(f"\n📍 Current Config ({current}) in Adverse Conditions:")
        if current in results:
            agg = results[current]['_aggregate']
            try:
                current_rank = sorted_configs.index(current) + 1
            except ValueError:
                current_rank = "N/A"
            print(f"   Rank: #{current_rank} of {len(sorted_configs)}")
            print(f"   Total Value: ${agg['total_value']:.2f}")
            print(f"   vs Hold: ${agg['dump_advantage']:+.2f}")

        # Best config for adverse conditions
        best = sorted_configs[0]
        print(f"\n🏆 Best Config for Adverse/Black Swan ({best}):")
        agg = results[best]['_aggregate']
        print(f"   Total Value: ${agg['total_value']:.2f}")
        print(f"   vs Hold Advantage: ${agg['dump_advantage']:+.2f}")
        print(f"   Capture Rate: {agg['avg_capture_rate']*100:.1f}%")
        print(f"   Missed Recoveries: {agg['total_missed_recoveries']}")

        # Highlight 50% threshold specifically
        print("\n🎯 50% Take Profit Threshold Analysis:")
        fifty_pct_configs = [k for k in sorted_configs if k.startswith("50/")]
        if fifty_pct_configs:
            best_50 = fifty_pct_configs[0]
            agg_50 = results[best_50]['_aggregate']
            print(f"   Best 50% config: {best_50}")
            print(f"   Total Value: ${agg_50['total_value']:.2f}")
            print(f"   vs Hold Advantage: ${agg_50['dump_advantage']:+.2f}")

            # Compare to current (85%)
            if current in results:
                current_adv = results[current]['_aggregate']['dump_advantage']
                fifty_adv = agg_50['dump_advantage']
                improvement = fifty_adv - current_adv
                print(f"   vs Current (85%): ${improvement:+.2f} {'BETTER' if improvement > 0 else 'WORSE'}")

        # Per-scenario breakdown for best config
        print(f"\n📈 Best Config ({best}) Scenario Breakdown:")
        for scenario in AdverseScenario:
            if scenario.value in results[best]:
                data = results[best][scenario.value]
                advantage = data['dump_vs_hold_advantage']
                sign = "+" if advantage >= 0 else ""
                print(f"   {scenario.value:<25}: ${data['total_value']:.2f} "
                      f"(vs hold: {sign}${advantage:.2f}, "
                      f"missed: {data['missed_recoveries']})")

        # Recommendation
        print("\n" + "=" * 80)
        print("RECOMMENDATION FOR ADVERSE/BLACK SWAN CONDITIONS")
        print("=" * 80)

        if best.startswith("50/") or best.startswith("65/"):
            print(f"\n✅ AGGRESSIVE take profit ({best}) RECOMMENDED for adverse conditions")
            print(f"   - Triggers earlier exit at {best.split('/')[0]}% of peak")
            print(f"   - Better capital preservation during crashes")
            print(f"   - Expected advantage: ${agg['dump_advantage']:+.2f}")
        else:
            print(f"\n⚠️  Conservative approach ({best}) still best for these adverse scenarios")
            print(f"   - 50% threshold may be too aggressive")
            print(f"   - Risk of missing recoveries")

        return best


def main():
    """Run adverse/black swan conditions backtest"""
    print(f"\n{'='*80}")
    print(f"AI-XYZ Adverse/Black Swan Backtest")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*80}\n")

    backtest = AdverseConditionsBacktest(leverage=5, position_size_usd=10.0)

    # Run full backtest
    results = backtest.run_full_backtest(num_runs=100)

    # Print results
    best_config = backtest.print_results(results)

    # Save results
    output_file = 'adverse_blackswan_backtest_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Results saved to {output_file}")

    return results, best_config


if __name__ == "__main__":
    main()
