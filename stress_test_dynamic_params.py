#!/usr/bin/env python3
"""
Stress Test for Dynamic Parameter Manager
V1.0.0 - January 14, 2026

Tests the Dynamic Parameter Manager under extreme market conditions:
- Flash crashes (sudden volatility spikes)
- Prolonged high volatility
- Rapid regime transitions
- Edge cases (data gaps, extreme values)

Validates:
- Parameter adjustments are within safe bounds
- No over-adjustment in short-lived spikes
- Smooth transitions between regimes
- Fallback behavior on errors

Author: Claude + Grok Consortium
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import json
import sys
sys.path.insert(0, '/root/ai_xyz')

from dynamic_parameter_manager import DynamicParameterManager

# Test Results Storage
RESULTS_FILE = '/root/ai_xyz/stress_test_dynamic_params_results.json'


class StressTestScenario:
    """Defines a stress test scenario with simulated OHLCV data."""

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.ohlcv_data = []
        self.expected_regimes = []
        self.test_results = {}

    def generate_ohlcv(self, base_price: float, num_candles: int,
                       volatility_profile: List[float]) -> List[List]:
        """
        Generate synthetic OHLCV data with specified volatility profile.

        Args:
            base_price: Starting price
            num_candles: Number of 5-minute candles
            volatility_profile: List of volatility multipliers for each candle
        """
        ohlcv = []
        current_price = base_price
        timestamp = int(datetime.now().timestamp() * 1000)

        for i in range(num_candles):
            vol = volatility_profile[i] if i < len(volatility_profile) else volatility_profile[-1]

            # Generate candle with specified volatility
            change_pct = np.random.normal(0, vol / 100)
            high_add = abs(np.random.normal(0, vol / 100))
            low_sub = abs(np.random.normal(0, vol / 100))

            open_price = current_price
            close_price = current_price * (1 + change_pct)
            high_price = max(open_price, close_price) * (1 + high_add)
            low_price = min(open_price, close_price) * (1 - low_sub)
            volume = np.random.uniform(1000, 10000)

            ohlcv.append([
                timestamp + i * 300000,  # 5-minute intervals
                open_price,
                high_price,
                low_price,
                close_price,
                volume
            ])

            current_price = close_price

        self.ohlcv_data = ohlcv
        return ohlcv


class DynamicParamsStressTester:
    """
    Stress tester for Dynamic Parameter Manager.

    Tests various extreme scenarios to validate parameter adjustment behavior.
    """

    def __init__(self):
        self.manager = DynamicParameterManager()
        self.results = {
            'test_timestamp': datetime.now().isoformat(),
            'scenarios': {},
            'summary': {}
        }

    def create_scenarios(self) -> Dict[str, StressTestScenario]:
        """Create all stress test scenarios."""
        scenarios = {}

        # Scenario 1: Flash Crash (sudden spike then recovery)
        flash_crash = StressTestScenario(
            'flash_crash',
            'Sudden volatility spike (10x normal) lasting 5 minutes then recovery'
        )
        # Normal vol (1%) -> Spike (10%) -> Recovery (2%) -> Normal (1%)
        vol_profile = [1.0] * 10 + [10.0] * 3 + [5.0] * 3 + [2.0] * 5 + [1.0] * 10
        flash_crash.generate_ohlcv(50000, len(vol_profile), vol_profile)
        flash_crash.expected_regimes = ['NORMAL', 'HIGH_VOLATILITY', 'HIGH_VOLATILITY', 'NORMAL']
        scenarios['flash_crash'] = flash_crash

        # Scenario 2: Prolonged High Volatility
        prolonged_vol = StressTestScenario(
            'prolonged_high_vol',
            'Extended period of high volatility (3x normal) for 2 hours'
        )
        vol_profile = [1.0] * 5 + [4.0] * 25 + [2.0] * 10 + [1.0] * 5
        prolonged_vol.generate_ohlcv(50000, len(vol_profile), vol_profile)
        prolonged_vol.expected_regimes = ['NORMAL', 'HIGH_VOLATILITY', 'TRENDING', 'NORMAL']
        scenarios['prolonged_high_vol'] = prolonged_vol

        # Scenario 3: Rapid Regime Transitions
        rapid_transitions = StressTestScenario(
            'rapid_transitions',
            'Quick switches between high and low volatility'
        )
        vol_profile = []
        for _ in range(5):
            vol_profile.extend([0.3] * 5 + [5.0] * 5)  # Alternating low/high
        rapid_transitions.generate_ohlcv(50000, len(vol_profile), vol_profile)
        scenarios['rapid_transitions'] = rapid_transitions

        # Scenario 4: Extreme Volatility (Black Swan)
        black_swan = StressTestScenario(
            'black_swan',
            'Extreme volatility event (20x normal) - tests bounds'
        )
        vol_profile = [1.0] * 10 + [20.0] * 5 + [15.0] * 5 + [5.0] * 10 + [1.0] * 10
        black_swan.generate_ohlcv(50000, len(vol_profile), vol_profile)
        scenarios['black_swan'] = black_swan

        # Scenario 5: Low Volatility (Ranging Market)
        ranging = StressTestScenario(
            'ranging_market',
            'Extended low volatility period - tests RANGING regime'
        )
        vol_profile = [1.0] * 5 + [0.2] * 30 + [0.5] * 10
        ranging.generate_ohlcv(50000, len(vol_profile), vol_profile)
        ranging.expected_regimes = ['NORMAL', 'RANGING', 'RANGING']
        scenarios['ranging_market'] = ranging

        # Scenario 6: Trending Market
        trending = StressTestScenario(
            'trending_market',
            'Sustained directional movement with moderate volatility'
        )
        vol_profile = [1.5] * 5 + [2.5] * 20 + [1.8] * 15
        trending.generate_ohlcv(50000, len(vol_profile), vol_profile)
        scenarios['trending_market'] = trending

        # Scenario 7: Data Gap Simulation
        data_gap = StressTestScenario(
            'data_gap',
            'Missing or sparse data - tests fallback behavior'
        )
        # Only 10 candles (less than required for slow ATR)
        data_gap.ohlcv_data = [[int(datetime.now().timestamp() * 1000) + i * 300000,
                                50000, 50100, 49900, 50050, 1000] for i in range(10)]
        scenarios['data_gap'] = data_gap

        # Scenario 8: Extreme Price Movement
        extreme_move = StressTestScenario(
            'extreme_price_move',
            '50% price drop in 30 minutes - cascade liquidation scenario'
        )
        ohlcv = []
        price = 50000
        for i in range(20):
            drop = 0.025 if i < 10 else 0.01  # 2.5% per candle then 1%
            new_price = price * (1 - drop)
            ohlcv.append([
                int(datetime.now().timestamp() * 1000) + i * 300000,
                price, price * 1.01, new_price * 0.99, new_price, 50000
            ])
            price = new_price
        extreme_move.ohlcv_data = ohlcv
        scenarios['extreme_price_move'] = extreme_move

        return scenarios

    def test_parameter_bounds(self, params: Dict) -> Dict:
        """Test that parameters are within safe bounds."""
        bounds_check = {
            'averaging_trigger': {'min': -0.50, 'max': -0.15, 'value': params.get('averaging_trigger', -0.35)},
            'surplus_dump_stage1': {'min': 0.70, 'max': 0.95, 'value': params.get('surplus_dump_stage1', 0.85)},
            'surplus_dump_stage2': {'min': 0.30, 'max': 0.60, 'value': params.get('surplus_dump_stage2', 0.40)},
            'stop_loss': {'min': -0.95, 'max': -0.50, 'value': params.get('stop_loss', -0.90)}
        }

        results = {'all_within_bounds': True, 'violations': []}

        for param_name, bounds in bounds_check.items():
            value = bounds['value']
            if value < bounds['min'] or value > bounds['max']:
                results['all_within_bounds'] = False
                results['violations'].append({
                    'param': param_name,
                    'value': value,
                    'min': bounds['min'],
                    'max': bounds['max']
                })

        return results

    def test_regime_stability(self, regime_history: List[str], min_duration: int = 2) -> Dict:
        """Test that regimes don't oscillate too rapidly."""
        if len(regime_history) < 2:
            return {'stable': True, 'oscillations': 0, 'avg_duration': 0, 'transitions': 0, 'min_duration': 0, 'max_duration': 0}

        transitions = 0
        durations = []
        current_regime = regime_history[0]
        current_duration = 1

        for regime in regime_history[1:]:
            if regime != current_regime:
                transitions += 1
                durations.append(current_duration)
                current_regime = regime
                current_duration = 1
            else:
                current_duration += 1

        durations.append(current_duration)
        avg_duration = np.mean(durations) if durations else 0

        # Flag if average duration is less than minimum
        stable = avg_duration >= min_duration

        return {
            'stable': stable,
            'transitions': transitions,
            'avg_duration': avg_duration,
            'min_duration': min(durations) if durations else 0,
            'max_duration': max(durations) if durations else 0
        }

    def run_scenario(self, scenario: StressTestScenario) -> Dict:
        """Run a single stress test scenario."""
        print(f"\n{'='*60}")
        print(f"Running: {scenario.name}")
        print(f"Description: {scenario.description}")
        print(f"{'='*60}")

        # Reset manager state
        self.manager = DynamicParameterManager()

        results = {
            'name': scenario.name,
            'description': scenario.description,
            'num_candles': len(scenario.ohlcv_data),
            'regime_history': [],
            'param_history': [],
            'bounds_violations': [],
            'atr_ratios': []
        }

        # Process each time window (sliding window of 20 candles)
        window_size = 20

        for i in range(window_size, len(scenario.ohlcv_data)):
            window = scenario.ohlcv_data[i-window_size:i]

            # Manually inject OHLCV data into cache
            atr_ratio, regime = self.manager.calculate_atr_ratio('TEST/USDT:USDT', window)

            # Get dynamic parameters
            self.manager.volatility_cache['TEST/USDT:USDT'] = (datetime.now(), atr_ratio)
            params = self.manager.calculate_dynamic_params('TEST/USDT:USDT')

            results['regime_history'].append(regime)
            results['atr_ratios'].append(atr_ratio)
            results['param_history'].append({
                'averaging': params['averaging_trigger'],
                'sd1': params['surplus_dump_stage1'],
                'sd2': params['surplus_dump_stage2'],
                'stop_loss': params['stop_loss']
            })

            # Check bounds
            bounds_check = self.test_parameter_bounds(params)
            if not bounds_check['all_within_bounds']:
                results['bounds_violations'].extend(bounds_check['violations'])

        # Analyze regime stability
        stability = self.test_regime_stability(results['regime_history'])
        results['stability'] = stability

        # Summary statistics
        results['summary'] = {
            'unique_regimes': list(set(results['regime_history'])),
            'regime_counts': {r: results['regime_history'].count(r) for r in set(results['regime_history'])},
            'avg_atr_ratio': np.mean(results['atr_ratios']) if results['atr_ratios'] else 0,
            'max_atr_ratio': max(results['atr_ratios']) if results['atr_ratios'] else 0,
            'min_atr_ratio': min(results['atr_ratios']) if results['atr_ratios'] else 0,
            'bounds_violations_count': len(results['bounds_violations']),
            'regime_stable': stability['stable'],
            'regime_transitions': stability['transitions']
        }

        # Print results
        print(f"\nResults:")
        print(f"  Unique Regimes: {results['summary']['unique_regimes']}")
        print(f"  Regime Counts: {results['summary']['regime_counts']}")
        print(f"  ATR Ratio: min={results['summary']['min_atr_ratio']:.2f}, avg={results['summary']['avg_atr_ratio']:.2f}, max={results['summary']['max_atr_ratio']:.2f}")
        print(f"  Bounds Violations: {results['summary']['bounds_violations_count']}")
        print(f"  Regime Stable: {results['summary']['regime_stable']} (transitions: {results['summary']['regime_transitions']})")

        # Pass/Fail determination
        passed = (
            results['summary']['bounds_violations_count'] == 0 and
            results['summary']['regime_stable']
        )
        results['passed'] = passed
        print(f"  STATUS: {'✅ PASSED' if passed else '❌ FAILED'}")

        return results

    def run_all_scenarios(self) -> Dict:
        """Run all stress test scenarios."""
        print("\n" + "="*70)
        print("DYNAMIC PARAMETER MANAGER - STRESS TEST SUITE")
        print("="*70)
        print(f"Test Time: {datetime.now().isoformat()}")

        scenarios = self.create_scenarios()

        for name, scenario in scenarios.items():
            result = self.run_scenario(scenario)
            self.results['scenarios'][name] = result

        # Overall summary
        total = len(self.results['scenarios'])
        passed = sum(1 for r in self.results['scenarios'].values() if r['passed'])
        failed = total - passed

        self.results['summary'] = {
            'total_scenarios': total,
            'passed': passed,
            'failed': failed,
            'pass_rate': passed / total * 100 if total > 0 else 0,
            'all_passed': failed == 0
        }

        print("\n" + "="*70)
        print("OVERALL RESULTS")
        print("="*70)
        print(f"Total Scenarios: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Pass Rate: {self.results['summary']['pass_rate']:.1f}%")
        print(f"STATUS: {'✅ ALL TESTS PASSED' if failed == 0 else '❌ SOME TESTS FAILED'}")

        # Save results
        with open(RESULTS_FILE, 'w') as f:
            # Convert numpy types for JSON serialization
            json_results = json.loads(json.dumps(self.results, default=str))
            json.dump(json_results, f, indent=2)

        print(f"\nResults saved to: {RESULTS_FILE}")

        return self.results

    def run_dampening_test(self) -> Dict:
        """
        Test Grok's recommendation: dampening mechanism for short-lived spikes.

        Verifies that brief volatility spikes don't cause over-aggressive parameter changes.
        """
        print("\n" + "="*70)
        print("DAMPENING TEST - Short-lived Spike Behavior")
        print("="*70)

        # Create scenario with very brief spike
        brief_spike = StressTestScenario(
            'brief_spike_dampening',
            '1-minute volatility spike then immediate return to normal'
        )

        # Normal for 15 candles, spike for 1, back to normal
        vol_profile = [1.0] * 15 + [15.0] + [1.0] * 15
        brief_spike.generate_ohlcv(50000, len(vol_profile), vol_profile)

        # Track parameter changes
        self.manager = DynamicParameterManager()
        param_changes = []

        window_size = 20
        prev_params = None

        for i in range(window_size, len(brief_spike.ohlcv_data)):
            window = brief_spike.ohlcv_data[i-window_size:i]
            atr_ratio, regime = self.manager.calculate_atr_ratio('TEST/USDT:USDT', window)
            self.manager.volatility_cache['TEST/USDT:USDT'] = (datetime.now(), atr_ratio)
            params = self.manager.calculate_dynamic_params('TEST/USDT:USDT')

            if prev_params:
                change = abs(params['averaging_trigger'] - prev_params['averaging_trigger'])
                param_changes.append({
                    'candle': i,
                    'atr_ratio': atr_ratio,
                    'regime': regime,
                    'avg_trigger': params['averaging_trigger'],
                    'change': change
                })

            prev_params = params

        # Analyze: large changes should be rare
        large_changes = [p for p in param_changes if p['change'] > 0.05]

        result = {
            'scenario': 'brief_spike_dampening',
            'total_updates': len(param_changes),
            'large_changes': len(large_changes),
            'max_change': max(p['change'] for p in param_changes) if param_changes else 0,
            'recommendation': ''
        }

        if len(large_changes) > 2:
            result['recommendation'] = 'CONSIDER: Add moving average smoothing to ATR ratio calculation'
            print(f"⚠️ {len(large_changes)} large parameter changes detected during brief spike")
            print(f"   Recommendation: {result['recommendation']}")
        else:
            result['recommendation'] = 'Current dampening is adequate'
            print(f"✅ Parameter changes well-controlled ({len(large_changes)} large changes)")

        print(f"   Max single change: {result['max_change']*100:.1f}%")

        return result


def main():
    """Run all stress tests."""
    tester = DynamicParamsStressTester()

    # Run main test suite
    results = tester.run_all_scenarios()

    # Run dampening test (Grok recommendation)
    dampening_result = tester.run_dampening_test()
    results['dampening_test'] = dampening_result

    # Update saved results
    with open(RESULTS_FILE, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    return results


if __name__ == "__main__":
    main()
