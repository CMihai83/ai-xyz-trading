#!/usr/bin/env python3
"""
Stress Test Module for Profit Protection Hedge
===============================================
Tests the profit protection hedge under extreme market conditions.

Scenarios:
1. Flash Crash - Sudden 10-20% drop
2. Rapid Pump - Sudden 10-20% rise
3. Prolonged Downtrend - Steady decline over time
4. Prolonged Uptrend - Steady rise over time
5. High Volatility - Wild swings both directions
6. Low Volatility (Choppy) - Sideways movement
7. Black Swan - Extreme 30%+ moves
8. V-Shape Recovery - Drop then rapid recovery
9. Dead Cat Bounce - Drop, small recovery, then continued drop

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


class Scenario(Enum):
    FLASH_CRASH = "flash_crash"
    RAPID_PUMP = "rapid_pump"
    PROLONGED_DOWNTREND = "prolonged_downtrend"
    PROLONGED_UPTREND = "prolonged_uptrend"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BLACK_SWAN_DOWN = "black_swan_down"
    BLACK_SWAN_UP = "black_swan_up"
    V_SHAPE_RECOVERY = "v_shape_recovery"
    DEAD_CAT_BOUNCE = "dead_cat_bounce"


@dataclass
class StressTestResult:
    scenario: Scenario
    strategy: str
    initial_price: float = 100.0
    final_price: float = 0.0
    peak_upnl: float = 0.0
    final_pnl: float = 0.0
    hedge_pnl: float = 0.0
    combined_pnl: float = 0.0
    max_drawdown: float = 0.0
    hedge_triggered: bool = False
    exit_reason: str = ""
    price_path: List[float] = field(default_factory=list)


class MarketSimulator:
    """Generates synthetic price paths for stress testing"""

    def __init__(self, initial_price: float = 100.0, num_candles: int = 500):
        self.initial_price = initial_price
        self.num_candles = num_candles

    def generate_flash_crash(self, crash_pct: float = 0.15, recovery_pct: float = 0.05) -> np.ndarray:
        """Sudden sharp drop followed by partial recovery"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal movement for first 30%
        normal_period = int(self.num_candles * 0.3)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Sharp crash over 5% of candles
        crash_period = int(self.num_candles * 0.05)
        crash_per_candle = crash_pct / crash_period
        for i in range(normal_period, normal_period + crash_period):
            prices[i] = prices[i-1] * (1 - crash_per_candle + np.random.normal(0, 0.002))

        # Partial recovery and stabilization
        recovery_target = prices[normal_period + crash_period - 1] * (1 + recovery_pct)
        remaining = self.num_candles - normal_period - crash_period
        for i in range(normal_period + crash_period, self.num_candles):
            progress = (i - normal_period - crash_period) / remaining
            target = prices[normal_period + crash_period - 1] + (recovery_target - prices[normal_period + crash_period - 1]) * progress
            prices[i] = target * (1 + np.random.normal(0, 0.003))

        return prices

    def generate_rapid_pump(self, pump_pct: float = 0.15, pullback_pct: float = 0.05) -> np.ndarray:
        """Sudden sharp rise followed by pullback"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal movement for first 30%
        normal_period = int(self.num_candles * 0.3)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Sharp pump over 5% of candles
        pump_period = int(self.num_candles * 0.05)
        pump_per_candle = pump_pct / pump_period
        for i in range(normal_period, normal_period + pump_period):
            prices[i] = prices[i-1] * (1 + pump_per_candle + np.random.normal(0, 0.002))

        # Pullback and stabilization
        pullback_target = prices[normal_period + pump_period - 1] * (1 - pullback_pct)
        remaining = self.num_candles - normal_period - pump_period
        for i in range(normal_period + pump_period, self.num_candles):
            progress = (i - normal_period - pump_period) / remaining
            target = prices[normal_period + pump_period - 1] - (prices[normal_period + pump_period - 1] - pullback_target) * min(1, progress * 2)
            prices[i] = target * (1 + np.random.normal(0, 0.003))

        return prices

    def generate_prolonged_downtrend(self, total_decline: float = 0.30) -> np.ndarray:
        """Steady decline over the entire period"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        decline_per_candle = total_decline / self.num_candles
        for i in range(1, self.num_candles):
            # Trending down with some noise
            prices[i] = prices[i-1] * (1 - decline_per_candle + np.random.normal(0, 0.008))

        return prices

    def generate_prolonged_uptrend(self, total_gain: float = 0.30) -> np.ndarray:
        """Steady rise over the entire period"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        gain_per_candle = total_gain / self.num_candles
        for i in range(1, self.num_candles):
            prices[i] = prices[i-1] * (1 + gain_per_candle + np.random.normal(0, 0.008))

        return prices

    def generate_high_volatility(self, volatility: float = 0.03) -> np.ndarray:
        """Wild swings in both directions"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        for i in range(1, self.num_candles):
            # High volatility random walk
            prices[i] = prices[i-1] * (1 + np.random.normal(0, volatility))

        return prices

    def generate_low_volatility(self, volatility: float = 0.003) -> np.ndarray:
        """Sideways choppy movement"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        for i in range(1, self.num_candles):
            # Low volatility mean-reverting
            mean_reversion = (self.initial_price - prices[i-1]) * 0.01
            prices[i] = prices[i-1] * (1 + np.random.normal(mean_reversion/prices[i-1], volatility))

        return prices

    def generate_black_swan_down(self, crash_pct: float = 0.35) -> np.ndarray:
        """Extreme sudden drop (30%+)"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 40%
        normal_period = int(self.num_candles * 0.4)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Catastrophic crash over 3% of candles
        crash_period = int(self.num_candles * 0.03)
        crash_per_candle = crash_pct / crash_period
        for i in range(normal_period, normal_period + crash_period):
            prices[i] = prices[i-1] * (1 - crash_per_candle)

        # Slow recovery/stabilization
        for i in range(normal_period + crash_period, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.0005, 0.005))

        return prices

    def generate_black_swan_up(self, pump_pct: float = 0.35) -> np.ndarray:
        """Extreme sudden rise (30%+)"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 40%
        normal_period = int(self.num_candles * 0.4)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Massive pump over 3% of candles
        pump_period = int(self.num_candles * 0.03)
        pump_per_candle = pump_pct / pump_period
        for i in range(normal_period, normal_period + pump_period):
            prices[i] = prices[i-1] * (1 + pump_per_candle)

        # Slow decline/stabilization
        for i in range(normal_period + pump_period, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(-0.0003, 0.005))

        return prices

    def generate_v_shape_recovery(self, drop_pct: float = 0.20) -> np.ndarray:
        """Drop then rapid full recovery"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 20%
        normal_period = int(self.num_candles * 0.2)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Drop over 20%
        drop_period = int(self.num_candles * 0.2)
        drop_per_candle = drop_pct / drop_period
        for i in range(normal_period, normal_period + drop_period):
            prices[i] = prices[i-1] * (1 - drop_per_candle + np.random.normal(0, 0.003))

        # Recovery over 30%
        recovery_period = int(self.num_candles * 0.3)
        bottom_price = prices[normal_period + drop_period - 1]
        recovery_target = self.initial_price * 1.05  # Slight overshoot
        for i in range(normal_period + drop_period, normal_period + drop_period + recovery_period):
            progress = (i - normal_period - drop_period) / recovery_period
            target = bottom_price + (recovery_target - bottom_price) * progress
            prices[i] = target * (1 + np.random.normal(0, 0.003))

        # Stabilization
        for i in range(normal_period + drop_period + recovery_period, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(0, 0.005))

        return prices

    def generate_dead_cat_bounce(self, drop1_pct: float = 0.15, bounce_pct: float = 0.08, drop2_pct: float = 0.20) -> np.ndarray:
        """Drop, small recovery, then continued drop"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 15%
        phase1 = int(self.num_candles * 0.15)
        for i in range(1, phase1):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # First drop over 15%
        phase2 = int(self.num_candles * 0.15)
        drop_per_candle = drop1_pct / phase2
        for i in range(phase1, phase1 + phase2):
            prices[i] = prices[i-1] * (1 - drop_per_candle + np.random.normal(0, 0.003))

        # Bounce over 15%
        phase3 = int(self.num_candles * 0.15)
        bounce_per_candle = bounce_pct / phase3
        for i in range(phase1 + phase2, phase1 + phase2 + phase3):
            prices[i] = prices[i-1] * (1 + bounce_per_candle + np.random.normal(0, 0.003))

        # Second drop over 25%
        phase4 = int(self.num_candles * 0.25)
        drop_per_candle = drop2_pct / phase4
        for i in range(phase1 + phase2 + phase3, phase1 + phase2 + phase3 + phase4):
            prices[i] = prices[i-1] * (1 - drop_per_candle + np.random.normal(0, 0.003))

        # Stabilization
        for i in range(phase1 + phase2 + phase3 + phase4, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(0, 0.005))

        return prices


class ProfitProtectionHedgeStressTest:
    """Stress tests the profit protection hedge strategy"""

    # Configuration (matching hedge_gateway.py)
    HEDGE_SIZE = 0.50
    PROFIT_GATE = 0.10
    MAIN_DROP_GATE = 0.50
    STOP_LOSS = -0.05
    MIN_PROFIT = 5.00
    TAKE_PROFIT_TRIGGER = 0.70

    # Stress Test Improvements (V1.1.0)
    TRAILING_STOP_ACTIVATION = 0.03  # Activate trailing stop at 3% profit
    TRAILING_STOP_DISTANCE = 0.02    # Trail 2% behind peak profit
    MOMENTUM_RSI_OVERSOLD = 30       # Don't hedge if RSI < 30 (simulated)

    def __init__(self, leverage: int = 10, position_size_usd: float = 10.0):
        self.leverage = leverage
        self.position_size_usd = position_size_usd
        self.simulator = MarketSimulator()

    def calc_upnl(self, entry: float, current: float, size: float, side: str) -> Tuple[float, float]:
        """Calculate UPNL and percentage"""
        if side == 'long':
            pnl_pct = (current - entry) / entry
        else:
            pnl_pct = (entry - current) / entry
        margin = (size * entry) / self.leverage
        upnl = margin * pnl_pct * self.leverage
        return upnl, pnl_pct

    def simulate_traditional(self, prices: np.ndarray, side: str = 'long') -> StressTestResult:
        """Simulate traditional close-at-70% strategy"""
        entry_price = prices[0]
        size = (self.position_size_usd * self.leverage) / entry_price

        peak_upnl = 0.0
        max_drawdown = 0.0
        final_pnl = 0.0
        exit_reason = "timeout"

        for i, price in enumerate(prices):
            upnl, pct = self.calc_upnl(entry_price, price, size, side)

            if upnl > peak_upnl:
                peak_upnl = upnl

            if peak_upnl > 0:
                drawdown = (peak_upnl - upnl) / peak_upnl
                max_drawdown = max(max_drawdown, drawdown)

            # Traditional: Close at 70% of peak
            if peak_upnl >= self.MIN_PROFIT and upnl <= peak_upnl * self.TAKE_PROFIT_TRIGGER:
                final_pnl = upnl
                exit_reason = "close_70pct"
                break

            # Stop loss
            if pct <= -0.90:
                final_pnl = upnl
                exit_reason = "stop_loss"
                break

            final_pnl = upnl

        return StressTestResult(
            scenario=Scenario.FLASH_CRASH,  # Will be set by caller
            strategy="traditional",
            initial_price=entry_price,
            final_price=prices[-1],
            peak_upnl=peak_upnl,
            final_pnl=final_pnl,
            hedge_pnl=0,
            combined_pnl=final_pnl,
            max_drawdown=max_drawdown,
            hedge_triggered=False,
            exit_reason=exit_reason,
            price_path=prices.tolist()
        )

    def simulate_profit_hedge(self, prices: np.ndarray, side: str = 'long',
                               use_improvements: bool = True) -> StressTestResult:
        """Simulate profit protection hedge strategy with V1.1.0 improvements"""
        entry_price = prices[0]
        size = (self.position_size_usd * self.leverage) / entry_price

        peak_upnl = 0.0
        max_drawdown = 0.0
        final_pnl = 0.0
        hedge_pnl = 0.0
        exit_reason = "timeout"

        hedge_opened = False
        hedge_entry = 0.0
        hedge_size = 0.0

        # V1.1.0: Trailing stop tracking
        trailing_stop_activated = False
        hedge_peak_pct = 0.0

        # V1.1.0: Momentum filter state (simulated using price momentum)
        momentum_blocked = False

        for i, price in enumerate(prices):
            upnl, pct = self.calc_upnl(entry_price, price, size, side)

            if upnl > peak_upnl:
                peak_upnl = upnl

            if peak_upnl > 0:
                drawdown = (peak_upnl - upnl) / peak_upnl
                max_drawdown = max(max_drawdown, drawdown)

            # Open hedge at 70% of peak
            if peak_upnl >= self.MIN_PROFIT and not hedge_opened and upnl <= peak_upnl * self.TAKE_PROFIT_TRIGGER:
                # V1.1.0: Momentum filter simulation
                # Simulate RSI being oversold if price recently dropped sharply
                if use_improvements and i >= 14:
                    recent_prices = prices[max(0, i-14):i+1]
                    price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                    # If we're in a sharp downtrend (price dropped >10%), simulate oversold RSI
                    if price_change < -0.10 and side == 'long':
                        momentum_blocked = True
                        continue  # Skip hedge opening, price likely to bounce

                hedge_opened = True
                hedge_entry = price
                hedge_size = size * self.HEDGE_SIZE
                hedge_side = 'short' if side == 'long' else 'long'

            if hedge_opened:
                h_upnl, h_pct = self.calc_upnl(hedge_entry, price, hedge_size, 'short' if side == 'long' else 'long')
                hedge_margin = (hedge_size * hedge_entry) / self.leverage
                hedge_pct = h_upnl / hedge_margin if hedge_margin > 0 else 0

                # V1.1.0: Track peak hedge profit for trailing stop
                if hedge_pct > hedge_peak_pct:
                    hedge_peak_pct = hedge_pct

                # V1.1.0: Activate trailing stop at 3% profit
                if use_improvements and not trailing_stop_activated and hedge_pct >= self.TRAILING_STOP_ACTIVATION:
                    trailing_stop_activated = True

                # Gate 1: Profit target (10%)
                if hedge_pct >= self.PROFIT_GATE:
                    final_pnl = upnl
                    hedge_pnl = h_upnl
                    exit_reason = "hedge_profit_10pct"
                    break

                # V1.1.0 Gate 2: Trailing stop (drops 2% from peak after activation)
                if use_improvements and trailing_stop_activated:
                    trailing_stop_level = hedge_peak_pct - self.TRAILING_STOP_DISTANCE
                    if hedge_pct <= trailing_stop_level:
                        final_pnl = upnl
                        hedge_pnl = h_upnl
                        exit_reason = "trailing_stop"
                        break

                # Gate 3: Main drops to 50% of peak
                if peak_upnl > 0 and upnl <= peak_upnl * self.MAIN_DROP_GATE:
                    final_pnl = upnl
                    hedge_pnl = h_upnl
                    exit_reason = "main_drop"
                    break

                # Gate 4: Stop loss on hedge (-5%)
                if hedge_pct <= self.STOP_LOSS:
                    final_pnl = upnl
                    hedge_pnl = h_upnl
                    exit_reason = "hedge_stop_loss"
                    break

                hedge_pnl = h_upnl

            # Stop loss
            if pct <= -0.90:
                final_pnl = upnl
                exit_reason = "stop_loss"
                break

            final_pnl = upnl

        return StressTestResult(
            scenario=Scenario.FLASH_CRASH,  # Will be set by caller
            strategy="profit_hedge",
            initial_price=entry_price,
            final_price=prices[-1],
            peak_upnl=peak_upnl,
            final_pnl=final_pnl,
            hedge_pnl=hedge_pnl,
            combined_pnl=final_pnl + hedge_pnl,
            max_drawdown=max_drawdown,
            hedge_triggered=hedge_opened,
            exit_reason=exit_reason,
            price_path=prices.tolist()
        )

    def run_scenario(self, scenario: Scenario, num_runs: int = 50) -> Dict:
        """Run a specific scenario multiple times"""
        np.random.seed(42)

        traditional_results = []
        hedge_results = []

        # Generate price paths based on scenario
        for _ in range(num_runs):
            if scenario == Scenario.FLASH_CRASH:
                prices = self.simulator.generate_flash_crash()
            elif scenario == Scenario.RAPID_PUMP:
                prices = self.simulator.generate_rapid_pump()
            elif scenario == Scenario.PROLONGED_DOWNTREND:
                prices = self.simulator.generate_prolonged_downtrend()
            elif scenario == Scenario.PROLONGED_UPTREND:
                prices = self.simulator.generate_prolonged_uptrend()
            elif scenario == Scenario.HIGH_VOLATILITY:
                prices = self.simulator.generate_high_volatility()
            elif scenario == Scenario.LOW_VOLATILITY:
                prices = self.simulator.generate_low_volatility()
            elif scenario == Scenario.BLACK_SWAN_DOWN:
                prices = self.simulator.generate_black_swan_down()
            elif scenario == Scenario.BLACK_SWAN_UP:
                prices = self.simulator.generate_black_swan_up()
            elif scenario == Scenario.V_SHAPE_RECOVERY:
                prices = self.simulator.generate_v_shape_recovery()
            elif scenario == Scenario.DEAD_CAT_BOUNCE:
                prices = self.simulator.generate_dead_cat_bounce()
            else:
                continue

            # Run both strategies
            trad = self.simulate_traditional(prices)
            trad.scenario = scenario
            traditional_results.append(trad)

            hedge = self.simulate_profit_hedge(prices)
            hedge.scenario = scenario
            hedge_results.append(hedge)

        # Aggregate results
        trad_pnl = sum(r.combined_pnl for r in traditional_results)
        hedge_pnl = sum(r.combined_pnl for r in hedge_results)
        trad_drawdown = np.mean([r.max_drawdown for r in traditional_results])
        hedge_drawdown = np.mean([r.max_drawdown for r in hedge_results])

        hedge_triggers = sum(1 for r in hedge_results if r.hedge_triggered)
        hedge_exits = {}
        for r in hedge_results:
            hedge_exits[r.exit_reason] = hedge_exits.get(r.exit_reason, 0) + 1

        return {
            'scenario': scenario.value,
            'num_runs': num_runs,
            'traditional': {
                'total_pnl': trad_pnl,
                'avg_pnl': trad_pnl / num_runs,
                'avg_drawdown': trad_drawdown
            },
            'profit_hedge': {
                'total_pnl': hedge_pnl,
                'avg_pnl': hedge_pnl / num_runs,
                'avg_drawdown': hedge_drawdown,
                'hedge_triggers': hedge_triggers,
                'exit_reasons': hedge_exits
            },
            'improvement': (hedge_pnl - trad_pnl) / abs(trad_pnl) * 100 if trad_pnl != 0 else 0,
            'winner': 'profit_hedge' if hedge_pnl > trad_pnl else 'traditional'
        }

    def run_all_scenarios(self, num_runs: int = 50) -> Dict:
        """Run all stress test scenarios"""
        results = {}

        scenarios = [
            Scenario.FLASH_CRASH,
            Scenario.RAPID_PUMP,
            Scenario.PROLONGED_DOWNTREND,
            Scenario.PROLONGED_UPTREND,
            Scenario.HIGH_VOLATILITY,
            Scenario.LOW_VOLATILITY,
            Scenario.BLACK_SWAN_DOWN,
            Scenario.BLACK_SWAN_UP,
            Scenario.V_SHAPE_RECOVERY,
            Scenario.DEAD_CAT_BOUNCE
        ]

        for scenario in scenarios:
            print(f"  Running {scenario.value}...")
            results[scenario.value] = self.run_scenario(scenario, num_runs)

        return results

    def print_results(self, results: Dict):
        """Print stress test results"""
        print("\n" + "="*80)
        print("STRESS TEST RESULTS - PROFIT PROTECTION HEDGE")
        print("="*80)

        print(f"\n{'Scenario':<25} {'Traditional':<15} {'Hedge':<15} {'Improvement':<12} {'Winner':<12}")
        print("-"*80)

        total_trad = 0
        total_hedge = 0
        hedge_wins = 0

        for scenario, data in results.items():
            trad_pnl = data['traditional']['total_pnl']
            hedge_pnl = data['profit_hedge']['total_pnl']
            improvement = data['improvement']
            winner = data['winner']

            total_trad += trad_pnl
            total_hedge += hedge_pnl
            if winner == 'profit_hedge':
                hedge_wins += 1

            winner_icon = "✅" if winner == "profit_hedge" else "❌"
            print(f"{scenario:<25} ${trad_pnl:<14.2f} ${hedge_pnl:<14.2f} {improvement:>+10.1f}% {winner_icon} {winner}")

        print("-"*80)
        overall_improvement = (total_hedge - total_trad) / abs(total_trad) * 100 if total_trad != 0 else 0
        print(f"{'TOTAL':<25} ${total_trad:<14.2f} ${total_hedge:<14.2f} {overall_improvement:>+10.1f}%")
        print(f"\nHedge strategy wins: {hedge_wins}/{len(results)} scenarios ({hedge_wins/len(results)*100:.0f}%)")

        # Detailed breakdown
        print("\n" + "="*80)
        print("DETAILED SCENARIO ANALYSIS")
        print("="*80)

        for scenario, data in results.items():
            print(f"\n📊 {scenario.upper()}")
            print(f"   Traditional: ${data['traditional']['avg_pnl']:.2f} avg PnL, {data['traditional']['avg_drawdown']*100:.1f}% avg drawdown")
            print(f"   Profit Hedge: ${data['profit_hedge']['avg_pnl']:.2f} avg PnL, {data['profit_hedge']['avg_drawdown']*100:.1f}% avg drawdown")
            print(f"   Hedge triggers: {data['profit_hedge']['hedge_triggers']}/{data['num_runs']} ({data['profit_hedge']['hedge_triggers']/data['num_runs']*100:.0f}%)")
            if data['profit_hedge']['exit_reasons']:
                exits = ", ".join([f"{k}={v}" for k, v in data['profit_hedge']['exit_reasons'].items()])
                print(f"   Exit reasons: {exits}")

        # Recommendations
        print("\n" + "="*80)
        print("RECOMMENDATIONS")
        print("="*80)

        weak_scenarios = [s for s, d in results.items() if d['winner'] == 'traditional']
        strong_scenarios = [s for s, d in results.items() if d['winner'] == 'profit_hedge']

        if strong_scenarios:
            print(f"\n✅ STRONG SCENARIOS (hedge outperforms):")
            for s in strong_scenarios:
                print(f"   - {s}: {results[s]['improvement']:+.1f}%")

        if weak_scenarios:
            print(f"\n⚠️ WEAK SCENARIOS (traditional outperforms):")
            for s in weak_scenarios:
                print(f"   - {s}: {results[s]['improvement']:+.1f}%")

        return {
            'total_traditional': total_trad,
            'total_hedge': total_hedge,
            'overall_improvement': overall_improvement,
            'hedge_win_rate': hedge_wins / len(results),
            'weak_scenarios': weak_scenarios,
            'strong_scenarios': strong_scenarios
        }


def main():
    print("="*80)
    print("PROFIT PROTECTION HEDGE - STRESS TEST")
    print("="*80)
    print("Testing under extreme market conditions...\n")

    tester = ProfitProtectionHedgeStressTest()
    results = tester.run_all_scenarios(num_runs=50)
    summary = tester.print_results(results)

    # Save results
    with open('stress_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Results saved to stress_test_results.json")

    return summary


if __name__ == "__main__":
    main()
