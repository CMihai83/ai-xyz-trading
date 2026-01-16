#!/usr/bin/env python3
"""
Adverse Market Recovery Take Profit Backtest
=============================================
Tests different take profit thresholds for positions that:
1. Went through adverse market conditions (deep drawdown)
2. Averaged multiple times during adversity
3. Recovered to profit

The hypothesis: Positions that survive adversity and recover should use
HIGHER take profit thresholds (hold longer) because:
- Recovery pattern indicates trend reversal
- Market has "corrected" from extreme
- More upside potential remains

Based on AXS case study:
- Position went to -32% P&L (adverse)
- Averaged to 1,444 contracts ($160 margin)
- Recovered to +$88.17 peak
- Stage 2 triggered at $24.60 (28% capture rate)
- Could have captured more with higher threshold

Author: Claude + Grok Consortium
Version: 1.0.0
Date: January 16, 2026
"""

import numpy as np
from dataclasses import dataclass
from typing import Dict, List, Tuple
from enum import Enum
import json
from itertools import product
from datetime import datetime


@dataclass
class AdverseRecoveryConfig:
    """Configuration for adverse recovery take profit thresholds"""
    stage1_threshold: float  # % of peak to trigger stage 1
    stage2_threshold: float  # % of peak to trigger stage 2
    # For adverse recovery, these should be LOWER (hold longer)
    # e.g., 50% means dump when profit drops to 50% of peak (not 85%)
    min_adverse_drawdown: float = 0.25  # 25% drawdown to qualify as "adverse"
    min_averaging_steps: int = 3  # Minimum averaging to qualify
    stage1_dump_pct: float = 0.50
    stage2_dump_pct: float = 0.50


class AdverseRecoveryBacktest:
    """
    Backtests take profit strategies for positions that recovered from adversity.

    Key insight: Standard 85%/30% thresholds may be too aggressive for
    positions that have proven recovery momentum.

    Test hypothesis: Using 50%/20% or lower thresholds (hold longer)
    captures more profit during continued recovery.
    """

    def __init__(self, leverage: int = 10, position_size_usd: float = 5.0):
        self.leverage = leverage
        self.position_size_usd = position_size_usd
        self.base_price = 1.09  # Simulating AXS-like entry price

    def generate_adverse_recovery_scenario(
        self,
        num_periods: int = 300,
        adverse_depth: float = 0.32,  # -32% like AXS
        recovery_peak: float = 0.15,   # +15% peak like AXS
        recovery_style: str = "partial"  # partial, full, overshoot
    ) -> Tuple[np.ndarray, dict]:
        """
        Generate price series mimicking adverse market → averaging → recovery pattern.

        Phases:
        1. Initial small profit (entry timing)
        2. Adverse decline (triggers averaging)
        3. Recovery rally (market correction)
        4. Profit decay or continuation
        """
        np.random.seed(None)

        # Phase lengths
        initial_len = num_periods // 10
        adverse_len = num_periods // 3
        recovery_len = num_periods // 3
        post_recovery_len = num_periods - initial_len - adverse_len - recovery_len

        # Phase 1: Initial small profit
        initial = np.linspace(0, 0.02, initial_len)  # Small rise

        # Phase 2: Adverse decline (where averaging happens)
        adverse_bottom = -adverse_depth / self.leverage  # Convert P&L% to price%
        adverse_points = np.linspace(0.02, adverse_bottom, adverse_len)
        noise_adverse = np.random.normal(0, 0.003, adverse_len)
        adverse = adverse_points + noise_adverse

        # Phase 3: Recovery rally
        recovery_peak_price = recovery_peak / self.leverage
        if recovery_style == "partial":
            # Recovers but doesn't fully sustain
            recovery_up = np.linspace(adverse_bottom, recovery_peak_price, recovery_len * 2 // 3)
            recovery_down = np.linspace(recovery_peak_price, recovery_peak_price * 0.3, recovery_len // 3)
            recovery = np.concatenate([recovery_up, recovery_down])
        elif recovery_style == "full":
            # Sustains near peak
            recovery_up = np.linspace(adverse_bottom, recovery_peak_price, recovery_len * 2 // 3)
            recovery_hold = np.ones(recovery_len // 3) * recovery_peak_price * 0.9
            recovery = np.concatenate([recovery_up, recovery_hold])
        else:  # overshoot
            # Continues higher
            recovery_up = np.linspace(adverse_bottom, recovery_peak_price, recovery_len // 2)
            recovery_more = np.linspace(recovery_peak_price, recovery_peak_price * 1.5, recovery_len // 2)
            recovery = np.concatenate([recovery_up, recovery_more])

        noise_recovery = np.random.normal(0, 0.004, len(recovery))
        recovery = recovery + noise_recovery

        # Phase 4: Post-recovery (depends on style)
        if recovery_style == "partial":
            post_trend = np.linspace(recovery[-1], recovery_peak_price * 0.2, post_recovery_len)
        elif recovery_style == "full":
            post_trend = np.ones(post_recovery_len) * recovery_peak_price * 0.85 + np.random.normal(0, 0.005, post_recovery_len)
        else:
            post_trend = np.linspace(recovery[-1], recovery_peak_price * 1.8, post_recovery_len)

        # Combine phases
        price_changes = np.concatenate([initial, adverse, recovery, post_trend])
        prices = self.base_price * (1 + price_changes)

        # Track where averaging would occur
        metadata = {
            'adverse_start': initial_len,
            'adverse_end': initial_len + adverse_len,
            'recovery_start': initial_len + adverse_len,
            'recovery_peak_period': initial_len + adverse_len + len(recovery) * 2 // 3,
            'adverse_depth': adverse_depth,
            'recovery_peak': recovery_peak,
            'recovery_style': recovery_style
        }

        return prices, metadata

    def simulate_averaging(
        self,
        prices: np.ndarray,
        metadata: dict
    ) -> Tuple[float, float, int, float]:
        """
        Simulate averaging during adverse phase.
        Returns: (weighted_entry, total_contracts, averaging_steps, total_margin)
        """
        initial_entry = prices[0]
        initial_contracts = self.position_size_usd * self.leverage / initial_entry

        entries = [(initial_entry, initial_contracts)]
        averaging_steps = 0
        max_steps = 5

        # Fibonacci multipliers
        multipliers = [1.0, 1.5, 2.0, 2.5, 3.0]
        averaging_threshold = -0.25  # -25% P&L triggers averaging

        for i in range(metadata['adverse_start'], metadata['adverse_end']):
            if averaging_steps >= max_steps:
                break

            current_price = prices[i]

            # Calculate weighted entry so far
            total_contracts = sum(c for _, c in entries)
            weighted_entry = sum(e * c for e, c in entries) / total_contracts

            # Check if P&L triggers averaging
            pnl_pct = ((current_price - weighted_entry) / weighted_entry) * self.leverage

            if pnl_pct <= averaging_threshold:
                # Execute averaging step
                multiplier = multipliers[min(averaging_steps, len(multipliers) - 1)]
                new_contracts = initial_contracts * multiplier
                entries.append((current_price, new_contracts))
                averaging_steps += 1
                averaging_threshold -= 0.05  # Deeper threshold for next step

        # Calculate final weighted entry
        total_contracts = sum(c for _, c in entries)
        weighted_entry = sum(e * c for e, c in entries) / total_contracts
        total_margin = total_contracts * weighted_entry / self.leverage

        return weighted_entry, total_contracts, averaging_steps, total_margin

    def calc_upnl(self, entry: float, current: float, contracts: float) -> Tuple[float, float]:
        """Calculate UPNL in $ and %"""
        price_change_pct = (current - entry) / entry
        upnl_pct = price_change_pct * self.leverage
        notional = contracts * entry
        margin = notional / self.leverage
        upnl_usd = margin * upnl_pct
        return upnl_usd, upnl_pct

    def simulate_take_profit(
        self,
        prices: np.ndarray,
        weighted_entry: float,
        total_contracts: float,
        original_contracts: float,
        config: AdverseRecoveryConfig,
        start_period: int = 0
    ) -> Dict:
        """
        Simulate surplus dump strategy after recovery.
        """
        surplus_contracts = total_contracts - original_contracts
        current_contracts = total_contracts

        # State tracking
        peak_upnl = 0.0
        dump_stage = 0
        total_captured = 0.0
        dump_events = []

        for i in range(start_period, len(prices)):
            price = prices[i]
            upnl_usd, upnl_pct = self.calc_upnl(weighted_entry, price, current_contracts)

            # Track peak
            if upnl_usd > peak_upnl:
                peak_upnl = upnl_usd

            # No surplus to dump
            if surplus_contracts <= 0:
                continue

            # Minimum profit threshold
            if peak_upnl < 0.10:
                continue

            # Stage 1
            if dump_stage == 0 and upnl_usd <= peak_upnl * config.stage1_threshold:
                dump_amount = surplus_contracts * config.stage1_dump_pct
                # Value captured = contracts * (price - entry)
                profit_per_contract = price - weighted_entry
                dump_value = dump_amount * profit_per_contract * self.leverage
                total_captured += dump_value
                surplus_contracts -= dump_amount
                current_contracts -= dump_amount
                dump_stage = 1
                dump_events.append({
                    'stage': 1,
                    'period': i,
                    'price': price,
                    'upnl': upnl_usd,
                    'peak': peak_upnl,
                    'pct_of_peak': upnl_usd / peak_upnl if peak_upnl > 0 else 0,
                    'captured': dump_value
                })

            # Stage 2
            elif dump_stage == 1 and upnl_usd <= peak_upnl * config.stage2_threshold:
                dump_amount = surplus_contracts  # Dump remaining
                profit_per_contract = price - weighted_entry
                dump_value = dump_amount * profit_per_contract * self.leverage
                total_captured += dump_value
                surplus_contracts = 0
                current_contracts = original_contracts
                dump_stage = 2
                dump_events.append({
                    'stage': 2,
                    'period': i,
                    'price': price,
                    'upnl': upnl_usd,
                    'peak': peak_upnl,
                    'pct_of_peak': upnl_usd / peak_upnl if peak_upnl > 0 else 0,
                    'captured': dump_value
                })

        # Calculate final position value
        final_upnl, _ = self.calc_upnl(weighted_entry, prices[-1], current_contracts)

        # What if we held to end with original position only?
        hold_original_upnl, _ = self.calc_upnl(weighted_entry, prices[-1], original_contracts)

        # Total value = captured + remaining position value
        total_value = total_captured + final_upnl

        # Capture rate
        capture_rate = total_captured / peak_upnl if peak_upnl > 0 else 0

        return {
            'peak_upnl': peak_upnl,
            'total_captured': total_captured,
            'capture_rate': capture_rate,
            'final_position_value': final_upnl,
            'total_value': total_value,
            'hold_original_value': hold_original_upnl,
            'dump_events': dump_events,
            'avg_exit_level': np.mean([e['pct_of_peak'] for e in dump_events]) if dump_events else 0
        }

    def run_scenario(
        self,
        config: AdverseRecoveryConfig,
        recovery_style: str,
        num_runs: int = 50
    ) -> Dict:
        """Run multiple simulations for a scenario/config combination"""

        results = []
        for _ in range(num_runs):
            # Generate prices
            prices, metadata = self.generate_adverse_recovery_scenario(
                recovery_style=recovery_style
            )

            # Simulate averaging during adverse phase
            weighted_entry, total_contracts, avg_steps, total_margin = self.simulate_averaging(
                prices, metadata
            )

            # Skip if didn't average enough
            if avg_steps < config.min_averaging_steps:
                continue

            original_contracts = self.position_size_usd * self.leverage / prices[0]

            # Simulate take profit after recovery starts
            result = self.simulate_take_profit(
                prices,
                weighted_entry,
                total_contracts,
                original_contracts,
                config,
                start_period=metadata['recovery_start']
            )

            result['averaging_steps'] = avg_steps
            result['total_margin'] = total_margin
            results.append(result)

        if not results:
            return {'valid': False}

        # Aggregate
        return {
            'valid': True,
            'num_runs': len(results),
            'avg_peak_upnl': np.mean([r['peak_upnl'] for r in results]),
            'avg_captured': np.mean([r['total_captured'] for r in results]),
            'avg_capture_rate': np.mean([r['capture_rate'] for r in results]),
            'avg_total_value': np.mean([r['total_value'] for r in results]),
            'avg_exit_level': np.mean([r['avg_exit_level'] for r in results if r['avg_exit_level'] > 0]),
            'total_captured': sum(r['total_captured'] for r in results),
            'total_value': sum(r['total_value'] for r in results)
        }

    def run_full_backtest(self, num_runs: int = 100) -> Dict:
        """
        Compare standard thresholds vs adverse-recovery optimized thresholds.
        """

        # Standard thresholds
        standard_configs = [
            ("85/30 (Current)", AdverseRecoveryConfig(0.85, 0.30)),
            ("85/40 (Current+)", AdverseRecoveryConfig(0.85, 0.40)),
        ]

        # Adverse recovery optimized (hold longer)
        adverse_configs = [
            ("75/30 (Moderate)", AdverseRecoveryConfig(0.75, 0.30)),
            ("70/25 (Aggressive)", AdverseRecoveryConfig(0.70, 0.25)),
            ("65/20 (Very Aggressive)", AdverseRecoveryConfig(0.65, 0.20)),
            ("50/20 (Ultra)", AdverseRecoveryConfig(0.50, 0.20)),
            ("50/15 (Max Hold)", AdverseRecoveryConfig(0.50, 0.15)),
        ]

        all_configs = standard_configs + adverse_configs
        recovery_styles = ["partial", "full", "overshoot"]

        results = {}

        print("=" * 80)
        print("ADVERSE MARKET RECOVERY TAKE PROFIT BACKTEST")
        print("=" * 80)
        print(f"Testing {len(all_configs)} configurations across {len(recovery_styles)} recovery styles")
        print(f"Leverage: {self.leverage}x | Base Position: ${self.position_size_usd}")
        print()

        for name, config in all_configs:
            results[name] = {}
            print(f"Testing {name}...", end=" ")

            for style in recovery_styles:
                result = self.run_scenario(config, style, num_runs)
                results[name][style] = result

            # Aggregate across styles
            valid_results = [r for r in results[name].values() if r.get('valid', False)]
            if valid_results:
                results[name]['_aggregate'] = {
                    'total_captured': sum(r['total_captured'] for r in valid_results),
                    'total_value': sum(r['total_value'] for r in valid_results),
                    'avg_capture_rate': np.mean([r['avg_capture_rate'] for r in valid_results]),
                    'avg_exit_level': np.mean([r.get('avg_exit_level', 0) for r in valid_results])
                }
                print(f"Captured: ${results[name]['_aggregate']['total_captured']:.2f}")
            else:
                print("No valid runs")

        return results

    def print_results(self, results: Dict):
        """Print formatted results"""

        print("\n" + "=" * 80)
        print("ADVERSE RECOVERY BACKTEST RESULTS")
        print("=" * 80)

        # Sort by total captured
        sorted_configs = sorted(
            [k for k in results.keys() if '_aggregate' in results.get(k, {})],
            key=lambda k: results[k]['_aggregate']['total_captured'],
            reverse=True
        )

        print("\n📊 CONFIGURATION RANKING (by total profit captured):\n")
        print(f"{'Rank':<6} {'Config':<25} {'Captured':<15} {'Capture Rate':<15} {'Avg Exit':<12}")
        print("-" * 75)

        for rank, name in enumerate(sorted_configs, 1):
            agg = results[name]['_aggregate']
            print(f"{rank:<6} {name:<25} ${agg['total_captured']:<14.2f} "
                  f"{agg['avg_capture_rate']*100:<14.1f}% "
                  f"{agg.get('avg_exit_level', 0)*100:<11.1f}%")

        # Compare standard vs optimized
        if sorted_configs:
            current = "85/30 (Current)"
            best = sorted_configs[0]

            print(f"\n📍 Current Standard ({current}):")
            if current in results and '_aggregate' in results[current]:
                agg = results[current]['_aggregate']
                print(f"   Total Captured: ${agg['total_captured']:.2f}")
                print(f"   Capture Rate: {agg['avg_capture_rate']*100:.1f}%")

            print(f"\n🏆 Best for Adverse Recovery ({best}):")
            agg = results[best]['_aggregate']
            print(f"   Total Captured: ${agg['total_captured']:.2f}")
            print(f"   Capture Rate: {agg['avg_capture_rate']*100:.1f}%")

            if current in results and '_aggregate' in results[current]:
                current_captured = results[current]['_aggregate']['total_captured']
                best_captured = agg['total_captured']
                improvement = ((best_captured - current_captured) / current_captured) * 100 if current_captured > 0 else 0
                print(f"   Improvement: {improvement:+.1f}%")

        # Per-recovery-style breakdown
        print("\n📈 Best Config Performance by Recovery Style:")
        if sorted_configs:
            best = sorted_configs[0]
            for style in ["partial", "full", "overshoot"]:
                if style in results[best] and results[best][style].get('valid'):
                    data = results[best][style]
                    print(f"   {style:<12}: Captured ${data['total_captured']:.2f} "
                          f"(rate: {data['avg_capture_rate']*100:.1f}%)")

        print("\n" + "=" * 80)
        print("RECOMMENDATION FOR ADVERSE RECOVERY POSITIONS")
        print("=" * 80)

        if sorted_configs and sorted_configs[0] != "85/30 (Current)":
            best = sorted_configs[0]
            print(f"\n✅ For positions that survived adverse market and recovered:")
            print(f"   USE: {best} thresholds instead of standard 85/30")
            print(f"   - Hold longer during recovery")
            print(f"   - Capture more of the correction momentum")
            print(f"   - Better suited for 'V-shape' recovery patterns")
        else:
            print(f"\n⚠️ Standard thresholds still optimal for these scenarios")

        return sorted_configs[0] if sorted_configs else None


def main():
    print(f"\n{'='*80}")
    print(f"AI-XYZ Adverse Recovery Take Profit Backtest")
    print(f"Based on AXS Position Case Study")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*80}\n")

    backtest = AdverseRecoveryBacktest(leverage=10, position_size_usd=5.0)

    results = backtest.run_full_backtest(num_runs=100)

    best_config = backtest.print_results(results)

    # Save results
    output_file = 'adverse_recovery_backtest_results.json'
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Results saved to {output_file}")

    return results, best_config


if __name__ == "__main__":
    main()
