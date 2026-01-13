#!/usr/bin/env python3
"""
Grok Recommendation #9: Stress Testing Module
Regular stress testing against historical events.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class StressScenario:
    """Definition of a stress test scenario"""
    name: str
    description: str
    btc_drop_pct: float        # BTC price drop percentage
    alt_multiplier: float      # Altcoin drop multiplier (vs BTC)
    duration_hours: float      # Duration of stress event
    volatility_spike: float    # Volatility multiplier
    funding_rate_spike: float  # Funding rate spike (%)
    liquidity_reduction: float # Liquidity reduction factor
    correlation_spike: float   # Correlation increase to 1.0


@dataclass
class StressTestResult:
    """Result of a stress test"""
    scenario_name: str
    initial_portfolio_value: float
    final_portfolio_value: float
    max_drawdown_pct: float
    max_drawdown_usd: float
    positions_liquidated: int
    margin_call_triggered: bool
    recovery_time_hours: float
    risk_score: float  # 0-100, higher = more risk


class StressTester:
    """
    Portfolio stress testing module.

    Tests portfolio against various historical and hypothetical scenarios.
    """

    # Predefined stress scenarios based on historical events
    SCENARIOS = {
        'flash_crash_2021': StressScenario(
            name='flash_crash_2021',
            description='May 2021 BTC flash crash (-30% in hours)',
            btc_drop_pct=-30,
            alt_multiplier=1.5,  # Alts drop 45%
            duration_hours=4,
            volatility_spike=5.0,
            funding_rate_spike=0.3,
            liquidity_reduction=0.5,
            correlation_spike=0.95
        ),
        'ftx_collapse': StressScenario(
            name='ftx_collapse',
            description='FTX collapse Nov 2022 (-25% sustained)',
            btc_drop_pct=-25,
            alt_multiplier=2.0,  # Alts drop 50%
            duration_hours=72,
            volatility_spike=3.0,
            funding_rate_spike=0.5,
            liquidity_reduction=0.7,
            correlation_spike=0.98
        ),
        'luna_crash': StressScenario(
            name='luna_crash',
            description='LUNA/UST collapse May 2022',
            btc_drop_pct=-20,
            alt_multiplier=3.0,  # Alts devastated
            duration_hours=168,
            volatility_spike=4.0,
            funding_rate_spike=0.2,
            liquidity_reduction=0.6,
            correlation_spike=0.90
        ),
        'cascade_liquidation': StressScenario(
            name='cascade_liquidation',
            description='Cascade liquidation event',
            btc_drop_pct=-15,
            alt_multiplier=2.0,
            duration_hours=2,
            volatility_spike=8.0,
            funding_rate_spike=1.0,
            liquidity_reduction=0.3,
            correlation_spike=1.0
        ),
        'exchange_outage': StressScenario(
            name='exchange_outage',
            description='4-hour exchange outage during volatility',
            btc_drop_pct=-10,
            alt_multiplier=1.5,
            duration_hours=4,
            volatility_spike=2.0,
            funding_rate_spike=0.1,
            liquidity_reduction=1.0,  # Complete outage
            correlation_spike=0.85
        ),
        'black_swan': StressScenario(
            name='black_swan',
            description='Extreme black swan event (-50% BTC)',
            btc_drop_pct=-50,
            alt_multiplier=2.5,
            duration_hours=24,
            volatility_spike=10.0,
            funding_rate_spike=2.0,
            liquidity_reduction=0.2,
            correlation_spike=1.0
        ),
        'moderate_correction': StressScenario(
            name='moderate_correction',
            description='Typical market correction (-10%)',
            btc_drop_pct=-10,
            alt_multiplier=1.3,
            duration_hours=48,
            volatility_spike=1.5,
            funding_rate_spike=0.05,
            liquidity_reduction=0.9,
            correlation_spike=0.7
        ),
    }

    def __init__(self, results_file: str = '/app/stress_test_results.json'):
        self.results_file = results_file
        self.results_history: List[Dict] = []
        self._load_results()

    def _load_results(self):
        """Load historical results"""
        try:
            if os.path.exists(self.results_file):
                with open(self.results_file, 'r') as f:
                    self.results_history = json.load(f).get('results', [])
        except Exception as e:
            logger.warning(f"Could not load stress test results: {e}")

    def _save_results(self, result: StressTestResult):
        """Save test results"""
        try:
            self.results_history.append({
                'timestamp': datetime.now().isoformat(),
                'scenario': result.scenario_name,
                'initial_value': result.initial_portfolio_value,
                'final_value': result.final_portfolio_value,
                'max_drawdown_pct': result.max_drawdown_pct,
                'positions_liquidated': result.positions_liquidated,
                'risk_score': result.risk_score
            })

            with open(self.results_file, 'w') as f:
                json.dump({
                    'last_updated': datetime.now().isoformat(),
                    'results': self.results_history[-100:]  # Keep last 100
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save results: {e}")

    def simulate_position_pnl(
        self,
        position: Dict,
        scenario: StressScenario,
        is_altcoin: bool = True
    ) -> Tuple[float, bool]:
        """
        Simulate P&L for a single position under stress.

        Returns:
            Tuple of (final_pnl, was_liquidated)
        """
        entry_price = position['entry_price']
        contracts = position['contracts']
        leverage = position['leverage']
        margin = position['margin']
        side = position['side']

        # Calculate price drop
        drop_pct = scenario.btc_drop_pct
        if is_altcoin:
            drop_pct *= scenario.alt_multiplier

        # Add volatility randomness
        volatility_noise = np.random.normal(0, abs(drop_pct) * 0.1 * scenario.volatility_spike)
        final_drop_pct = drop_pct + volatility_noise

        # Calculate new price
        if side == 'buy':
            new_price = entry_price * (1 + final_drop_pct / 100)
            pnl_pct = ((new_price - entry_price) / entry_price) * leverage * 100
        else:
            new_price = entry_price * (1 + final_drop_pct / 100)
            pnl_pct = ((entry_price - new_price) / entry_price) * leverage * 100

        # Calculate USD P&L
        position_value = contracts * entry_price
        pnl_usd = position_value * (pnl_pct / 100) / leverage

        # Check liquidation (typically at -80% to -90% of margin)
        liquidation_threshold = -85  # -85% of margin = liquidation
        was_liquidated = pnl_pct < liquidation_threshold

        # Apply slippage during liquidation
        if was_liquidated:
            slippage = 1 + (1 - scenario.liquidity_reduction) * 0.1
            pnl_usd *= slippage  # Worse execution during liquidation

        return pnl_usd, was_liquidated

    def run_stress_test(
        self,
        positions: List[Dict],
        portfolio_value: float,
        scenario_name: str = 'flash_crash_2021'
    ) -> StressTestResult:
        """
        Run stress test on a portfolio.

        Args:
            positions: List of position dicts with keys:
                - symbol, entry_price, contracts, leverage, margin, side
            portfolio_value: Total portfolio value
            scenario_name: Name of stress scenario to run

        Returns:
            StressTestResult with simulation results
        """
        scenario = self.SCENARIOS.get(scenario_name)
        if not scenario:
            raise ValueError(f"Unknown scenario: {scenario_name}")

        logger.info(f"Running stress test: {scenario.description}")

        # Simulation
        total_pnl = 0
        positions_liquidated = 0
        min_portfolio_value = portfolio_value

        # Run Monte Carlo simulation (100 paths)
        n_simulations = 100
        all_drawdowns = []

        for sim in range(n_simulations):
            sim_pnl = 0
            sim_liquidations = 0

            for pos in positions:
                # Determine if altcoin
                symbol = pos.get('symbol', '')
                is_alt = 'BTC' not in symbol and 'ETH' not in symbol

                pnl, liquidated = self.simulate_position_pnl(pos, scenario, is_alt)
                sim_pnl += pnl
                if liquidated:
                    sim_liquidations += 1

            sim_portfolio = portfolio_value + sim_pnl
            drawdown = (sim_portfolio - portfolio_value) / portfolio_value * 100
            all_drawdowns.append(drawdown)

            if sim == 0:  # Use first sim for main results
                total_pnl = sim_pnl
                positions_liquidated = sim_liquidations
                min_portfolio_value = sim_portfolio

        # Calculate statistics
        max_drawdown_pct = min(all_drawdowns)
        mean_drawdown_pct = np.mean(all_drawdowns)
        std_drawdown_pct = np.std(all_drawdowns)

        final_portfolio_value = portfolio_value + total_pnl

        # Margin call check
        margin_used = sum(p.get('margin', 0) for p in positions)
        margin_call_triggered = final_portfolio_value < margin_used * 1.1

        # Recovery time estimate (hours)
        if max_drawdown_pct < 0:
            # Assume 1% recovery per day on average
            recovery_time = abs(max_drawdown_pct) * 24  # hours
        else:
            recovery_time = 0

        # Risk score (0-100)
        risk_score = min(100, max(0, (
            abs(max_drawdown_pct) * 1.5 +
            positions_liquidated * 10 +
            (20 if margin_call_triggered else 0) +
            std_drawdown_pct * 2
        )))

        result = StressTestResult(
            scenario_name=scenario_name,
            initial_portfolio_value=portfolio_value,
            final_portfolio_value=final_portfolio_value,
            max_drawdown_pct=max_drawdown_pct,
            max_drawdown_usd=portfolio_value * abs(max_drawdown_pct) / 100,
            positions_liquidated=positions_liquidated,
            margin_call_triggered=margin_call_triggered,
            recovery_time_hours=recovery_time,
            risk_score=risk_score
        )

        self._save_results(result)
        return result

    def run_all_scenarios(
        self,
        positions: List[Dict],
        portfolio_value: float
    ) -> Dict[str, StressTestResult]:
        """Run all stress scenarios"""
        results = {}

        for scenario_name in self.SCENARIOS:
            results[scenario_name] = self.run_stress_test(
                positions, portfolio_value, scenario_name
            )

        return results

    def get_risk_assessment(self, results: Dict[str, StressTestResult]) -> Dict:
        """Generate overall risk assessment from stress tests"""
        if not results:
            return {'risk_level': 'UNKNOWN', 'score': 0}

        avg_risk_score = np.mean([r.risk_score for r in results.values()])
        max_drawdown = min([r.max_drawdown_pct for r in results.values()])
        total_liquidations = sum([r.positions_liquidated for r in results.values()])

        # Risk level
        if avg_risk_score >= 75:
            risk_level = 'CRITICAL'
        elif avg_risk_score >= 50:
            risk_level = 'HIGH'
        elif avg_risk_score >= 25:
            risk_level = 'MODERATE'
        else:
            risk_level = 'LOW'

        return {
            'risk_level': risk_level,
            'avg_risk_score': avg_risk_score,
            'worst_case_drawdown': max_drawdown,
            'total_potential_liquidations': total_liquidations,
            'recommendations': self._generate_recommendations(results)
        }

    def _generate_recommendations(self, results: Dict[str, StressTestResult]) -> List[str]:
        """Generate risk mitigation recommendations"""
        recommendations = []

        # Check for liquidation risk
        for name, result in results.items():
            if result.positions_liquidated > 0:
                recommendations.append(
                    f"Reduce leverage or position size - {result.positions_liquidated} positions "
                    f"would be liquidated in {name} scenario"
                )

            if result.margin_call_triggered:
                recommendations.append(
                    f"Increase margin reserve - margin call would trigger in {name} scenario"
                )

            if result.max_drawdown_pct < -50:
                recommendations.append(
                    f"Consider hedging - {abs(result.max_drawdown_pct):.1f}% drawdown in {name} scenario"
                )

        # General recommendations
        avg_risk = np.mean([r.risk_score for r in results.values()])
        if avg_risk > 50:
            recommendations.append("Consider reducing overall portfolio exposure")
            recommendations.append("Add stop-loss orders for high-risk positions")

        return list(set(recommendations))[:5]  # Top 5 unique recommendations

    def print_report(self, results: Dict[str, StressTestResult]):
        """Print stress test report"""
        print("\n" + "=" * 70)
        print("📊 STRESS TEST REPORT")
        print("=" * 70)

        for name, result in sorted(results.items(), key=lambda x: x[1].risk_score, reverse=True):
            scenario = self.SCENARIOS[name]
            print(f"\n📌 {scenario.description}")
            print("-" * 50)
            print(f"  Initial Value:    ${result.initial_portfolio_value:,.2f}")
            print(f"  Final Value:      ${result.final_portfolio_value:,.2f}")
            print(f"  Max Drawdown:     {result.max_drawdown_pct:.1f}% (${result.max_drawdown_usd:,.2f})")
            print(f"  Liquidations:     {result.positions_liquidated}")
            print(f"  Margin Call:      {'YES ⚠️' if result.margin_call_triggered else 'No'}")
            print(f"  Risk Score:       {result.risk_score:.0f}/100")

        # Overall assessment
        assessment = self.get_risk_assessment(results)
        print("\n" + "=" * 70)
        print(f"📈 OVERALL RISK ASSESSMENT: {assessment['risk_level']}")
        print("=" * 70)
        print(f"Average Risk Score: {assessment['avg_risk_score']:.0f}/100")
        print(f"Worst Case Drawdown: {assessment['worst_case_drawdown']:.1f}%")

        if assessment['recommendations']:
            print("\n⚠️ RECOMMENDATIONS:")
            for rec in assessment['recommendations']:
                print(f"  • {rec}")


# Singleton
_stress_tester: Optional[StressTester] = None

def get_stress_tester() -> StressTester:
    """Get singleton stress tester"""
    global _stress_tester
    if _stress_tester is None:
        _stress_tester = StressTester()
    return _stress_tester


if __name__ == "__main__":
    # Demo
    tester = StressTester('/tmp/stress_test.json')

    # Sample portfolio
    positions = [
        {'symbol': 'BTC/USDT:USDT', 'entry_price': 42000, 'contracts': 0.1, 'leverage': 10, 'margin': 420, 'side': 'buy'},
        {'symbol': 'ETH/USDT:USDT', 'entry_price': 2200, 'contracts': 1, 'leverage': 10, 'margin': 220, 'side': 'buy'},
        {'symbol': 'SOL/USDT:USDT', 'entry_price': 100, 'contracts': 10, 'leverage': 10, 'margin': 100, 'side': 'buy'},
        {'symbol': 'DOGE/USDT:USDT', 'entry_price': 0.08, 'contracts': 10000, 'leverage': 15, 'margin': 53, 'side': 'buy'},
    ]

    portfolio_value = 5000

    # Run all scenarios
    results = tester.run_all_scenarios(positions, portfolio_value)

    # Print report
    tester.print_report(results)
