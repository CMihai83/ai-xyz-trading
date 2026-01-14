#!/usr/bin/env python3
"""
Risk Management Validator for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Validates risk management systems with live/shadow data:
- Dynamic leverage trigger validation
- Alert false positive/negative analysis
- Circuit breaker effectiveness testing
- Hysteresis tuning recommendations

Sprint 6 - Grok Recommendation:
"Conduct live or shadow trading to validate dynamic leverage triggers
and circuit breaker effectiveness. Analyze false positives/negatives
in risk alerts and refine if needed."

Author: Claude + Grok Consortium
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum
import logging
import statistics

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Results file
VALIDATION_RESULTS_FILE = '/root/ai_xyz/risk_validation_results.json'


class ValidationResult(Enum):
    """Validation outcome."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NEEDS_TUNING = "NEEDS_TUNING"


@dataclass
class AlertValidation:
    """Represents an alert validation result."""
    alert_type: str
    triggered_at: datetime
    actual_outcome: str  # 'true_positive', 'false_positive', 'true_negative', 'false_negative'
    value_at_trigger: float
    threshold: float
    subsequent_value: float  # Value after some time to verify if alert was correct
    notes: str = ""


@dataclass
class LeverageValidation:
    """Represents a leverage adjustment validation."""
    symbol: str
    regime: str
    leverage_recommended: int
    leverage_used: int
    atr_ratio: float
    outcome: str  # 'correct', 'too_conservative', 'too_aggressive'
    pnl_impact: float = 0.0
    notes: str = ""


class RiskValidator:
    """
    Validates risk management systems against live/historical data.

    Tracks:
    - Alert accuracy (true/false positives/negatives)
    - Leverage adjustment effectiveness
    - Circuit breaker trigger accuracy
    - Hysteresis performance
    """

    def __init__(self):
        # Alert tracking
        self.alert_validations: List[AlertValidation] = []
        self.alert_stats: Dict[str, Dict] = defaultdict(lambda: {
            'true_positives': 0,
            'false_positives': 0,
            'true_negatives': 0,
            'false_negatives': 0,
            'total': 0
        })

        # Leverage tracking
        self.leverage_validations: List[LeverageValidation] = []
        self.leverage_outcomes: Dict[str, List[str]] = defaultdict(list)

        # Circuit breaker tracking
        self.circuit_breaker_events: List[Dict] = []
        self.circuit_breaker_effectiveness: Dict[str, int] = {
            'triggered_correctly': 0,
            'triggered_incorrectly': 0,
            'missed_trigger': 0
        }

        # Hysteresis tracking
        self.hysteresis_events: List[Dict] = []

        # Shadow trading results
        self.shadow_trades: List[Dict] = []

    # =========================================================================
    # ALERT VALIDATION
    # =========================================================================

    def record_alert_validation(self, alert_type: str, triggered: bool,
                               value_at_trigger: float, threshold: float,
                               subsequent_value: float, time_delta_min: int = 15):
        """
        Record an alert validation event.

        Args:
            alert_type: Type of alert (drawdown, margin, etc.)
            triggered: Whether alert was triggered
            value_at_trigger: Value when alert was checked
            threshold: Threshold that would trigger alert
            subsequent_value: Value after time_delta_min minutes
            time_delta_min: Time window for outcome validation
        """
        # Determine if alert was correct
        breach_at_trigger = value_at_trigger >= threshold
        breach_after = subsequent_value >= threshold
        worsened = subsequent_value > value_at_trigger

        if triggered:
            if breach_after or worsened:
                outcome = 'true_positive'
                self.alert_stats[alert_type]['true_positives'] += 1
            else:
                outcome = 'false_positive'
                self.alert_stats[alert_type]['false_positives'] += 1
        else:
            if not breach_after and not worsened:
                outcome = 'true_negative'
                self.alert_stats[alert_type]['true_negatives'] += 1
            else:
                outcome = 'false_negative'
                self.alert_stats[alert_type]['false_negatives'] += 1

        self.alert_stats[alert_type]['total'] += 1

        validation = AlertValidation(
            alert_type=alert_type,
            triggered_at=datetime.now(),
            actual_outcome=outcome,
            value_at_trigger=value_at_trigger,
            threshold=threshold,
            subsequent_value=subsequent_value
        )

        self.alert_validations.append(validation)

        if len(self.alert_validations) > 1000:
            self.alert_validations = self.alert_validations[-500:]

        return outcome

    def get_alert_accuracy(self, alert_type: str = None) -> Dict:
        """
        Get alert accuracy statistics.

        Returns:
            Dict with precision, recall, F1 score, accuracy
        """
        if alert_type:
            stats = self.alert_stats.get(alert_type, {})
            return self._calculate_accuracy_metrics(stats)

        # Overall accuracy across all alert types
        combined = {
            'true_positives': sum(s['true_positives'] for s in self.alert_stats.values()),
            'false_positives': sum(s['false_positives'] for s in self.alert_stats.values()),
            'true_negatives': sum(s['true_negatives'] for s in self.alert_stats.values()),
            'false_negatives': sum(s['false_negatives'] for s in self.alert_stats.values()),
            'total': sum(s['total'] for s in self.alert_stats.values())
        }
        return self._calculate_accuracy_metrics(combined)

    def _calculate_accuracy_metrics(self, stats: Dict) -> Dict:
        """Calculate precision, recall, F1, accuracy from stats."""
        tp = stats.get('true_positives', 0)
        fp = stats.get('false_positives', 0)
        tn = stats.get('true_negatives', 0)
        fn = stats.get('false_negatives', 0)
        total = stats.get('total', 0)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        accuracy = (tp + tn) / total if total > 0 else 0

        # Determine if tuning is needed
        needs_tuning = False
        tuning_reason = ""

        if fp > tp * 0.3:  # >30% false positive rate
            needs_tuning = True
            tuning_reason = "High false positive rate - consider increasing hysteresis"
        elif fn > tp * 0.2:  # >20% false negative rate
            needs_tuning = True
            tuning_reason = "High false negative rate - consider lowering thresholds"

        return {
            'true_positives': tp,
            'false_positives': fp,
            'true_negatives': tn,
            'false_negatives': fn,
            'total': total,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'accuracy': accuracy,
            'false_positive_rate': fp / (fp + tn) if (fp + tn) > 0 else 0,
            'false_negative_rate': fn / (fn + tp) if (fn + tp) > 0 else 0,
            'needs_tuning': needs_tuning,
            'tuning_reason': tuning_reason
        }

    # =========================================================================
    # LEVERAGE VALIDATION
    # =========================================================================

    def record_leverage_validation(self, symbol: str, regime: str,
                                  leverage_recommended: int, leverage_used: int,
                                  atr_ratio: float, actual_pnl: float,
                                  position_outcome: str):
        """
        Record a leverage adjustment validation.

        Args:
            symbol: Trading symbol
            regime: Market regime
            leverage_recommended: Recommended leverage from system
            leverage_used: Actual leverage used
            atr_ratio: ATR ratio at time of trade
            actual_pnl: Actual P&L outcome
            position_outcome: 'profit', 'loss', 'liquidation'
        """
        # Determine if leverage was appropriate
        if position_outcome == 'liquidation':
            outcome = 'too_aggressive'
        elif position_outcome == 'loss' and leverage_used > leverage_recommended:
            outcome = 'too_aggressive'
        elif position_outcome == 'profit' and leverage_used < leverage_recommended * 0.5:
            outcome = 'too_conservative'
        else:
            outcome = 'correct'

        validation = LeverageValidation(
            symbol=symbol,
            regime=regime,
            leverage_recommended=leverage_recommended,
            leverage_used=leverage_used,
            atr_ratio=atr_ratio,
            outcome=outcome,
            pnl_impact=actual_pnl
        )

        self.leverage_validations.append(validation)
        self.leverage_outcomes[regime].append(outcome)

        if len(self.leverage_validations) > 500:
            self.leverage_validations = self.leverage_validations[-250:]

        return outcome

    def get_leverage_effectiveness(self, regime: str = None) -> Dict:
        """Get leverage adjustment effectiveness by regime."""
        if regime:
            outcomes = self.leverage_outcomes.get(regime, [])
        else:
            outcomes = [o for outcomes in self.leverage_outcomes.values() for o in outcomes]

        if not outcomes:
            return {'total': 0}

        correct = outcomes.count('correct')
        too_aggressive = outcomes.count('too_aggressive')
        too_conservative = outcomes.count('too_conservative')
        total = len(outcomes)

        return {
            'total': total,
            'correct': correct,
            'correct_pct': correct / total * 100,
            'too_aggressive': too_aggressive,
            'too_aggressive_pct': too_aggressive / total * 100,
            'too_conservative': too_conservative,
            'too_conservative_pct': too_conservative / total * 100,
            'effectiveness_score': correct / total if total > 0 else 0,
            'needs_adjustment': too_aggressive > total * 0.2 or too_conservative > total * 0.3
        }

    # =========================================================================
    # CIRCUIT BREAKER VALIDATION
    # =========================================================================

    def record_circuit_breaker_event(self, triggered: bool, trigger_reason: str,
                                    conditions_at_trigger: Dict,
                                    outcome_after_cooldown: Dict):
        """
        Record a circuit breaker validation event.

        Args:
            triggered: Whether circuit breaker was triggered
            trigger_reason: Reason for trigger (or would-be reason)
            conditions_at_trigger: Market/account conditions at trigger time
            outcome_after_cooldown: Conditions after cooldown period
        """
        # Determine if trigger was correct
        loss_before = conditions_at_trigger.get('session_pnl', 0)
        loss_after = outcome_after_cooldown.get('session_pnl', 0)
        positions_closed = outcome_after_cooldown.get('positions_closed', 0)

        if triggered:
            # Was the trigger necessary?
            if loss_after < loss_before or positions_closed > 0:
                effectiveness = 'triggered_correctly'
                self.circuit_breaker_effectiveness['triggered_correctly'] += 1
            else:
                effectiveness = 'triggered_incorrectly'
                self.circuit_breaker_effectiveness['triggered_incorrectly'] += 1
        else:
            # Should it have triggered?
            if loss_after < loss_before * 0.8:  # Significant additional loss
                effectiveness = 'missed_trigger'
                self.circuit_breaker_effectiveness['missed_trigger'] += 1
            else:
                effectiveness = 'correctly_not_triggered'

        event = {
            'timestamp': datetime.now().isoformat(),
            'triggered': triggered,
            'trigger_reason': trigger_reason,
            'conditions_at_trigger': conditions_at_trigger,
            'outcome_after_cooldown': outcome_after_cooldown,
            'effectiveness': effectiveness
        }

        self.circuit_breaker_events.append(event)

        if len(self.circuit_breaker_events) > 100:
            self.circuit_breaker_events = self.circuit_breaker_events[-50:]

        return effectiveness

    def get_circuit_breaker_effectiveness(self) -> Dict:
        """Get circuit breaker effectiveness statistics."""
        total = sum(self.circuit_breaker_effectiveness.values())

        if total == 0:
            return {'total': 0, 'effectiveness': 'unknown'}

        correct = self.circuit_breaker_effectiveness['triggered_correctly']
        incorrect = self.circuit_breaker_effectiveness['triggered_incorrectly']
        missed = self.circuit_breaker_effectiveness['missed_trigger']

        effectiveness_score = correct / total if total > 0 else 0

        return {
            'total': total,
            'triggered_correctly': correct,
            'triggered_incorrectly': incorrect,
            'missed_triggers': missed,
            'effectiveness_score': effectiveness_score,
            'needs_tuning': incorrect > total * 0.2 or missed > total * 0.1
        }

    # =========================================================================
    # HYSTERESIS VALIDATION
    # =========================================================================

    def record_hysteresis_event(self, alert_type: str, breach_count: int,
                               hysteresis_threshold: int, triggered: bool,
                               was_real_issue: bool):
        """
        Record a hysteresis validation event.

        Args:
            alert_type: Type of alert
            breach_count: Number of consecutive breaches
            hysteresis_threshold: Required breaches for trigger
            triggered: Whether alert was triggered
            was_real_issue: Whether this was a real issue (in hindsight)
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'alert_type': alert_type,
            'breach_count': breach_count,
            'hysteresis_threshold': hysteresis_threshold,
            'triggered': triggered,
            'was_real_issue': was_real_issue,
            'correct': (triggered and was_real_issue) or (not triggered and not was_real_issue)
        }

        self.hysteresis_events.append(event)

        if len(self.hysteresis_events) > 200:
            self.hysteresis_events = self.hysteresis_events[-100:]

        return event['correct']

    def get_hysteresis_effectiveness(self) -> Dict:
        """Analyze hysteresis effectiveness."""
        if not self.hysteresis_events:
            return {'total': 0}

        correct = sum(1 for e in self.hysteresis_events if e['correct'])
        total = len(self.hysteresis_events)

        # Analyze if threshold should be adjusted
        triggered_too_early = sum(1 for e in self.hysteresis_events
                                 if e['triggered'] and not e['was_real_issue'])
        triggered_too_late = sum(1 for e in self.hysteresis_events
                                if not e['triggered'] and e['was_real_issue'])

        recommendation = "optimal"
        if triggered_too_early > total * 0.2:
            recommendation = "increase_threshold"
        elif triggered_too_late > total * 0.15:
            recommendation = "decrease_threshold"

        return {
            'total': total,
            'correct': correct,
            'accuracy': correct / total if total > 0 else 0,
            'triggered_too_early': triggered_too_early,
            'triggered_too_late': triggered_too_late,
            'recommendation': recommendation
        }

    # =========================================================================
    # SHADOW TRADING
    # =========================================================================

    def record_shadow_trade(self, symbol: str, side: str, leverage: int,
                           entry_price: float, exit_price: float,
                           risk_checks: Dict, actual_outcome: str):
        """
        Record a shadow trade for validation.

        Args:
            symbol: Trading symbol
            side: 'long' or 'short'
            leverage: Leverage used
            entry_price: Entry price
            exit_price: Exit price
            risk_checks: Results of risk checks at entry
            actual_outcome: What actually happened
        """
        pnl_pct = ((exit_price - entry_price) / entry_price) * leverage
        if side == 'short':
            pnl_pct = -pnl_pct

        trade = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'side': side,
            'leverage': leverage,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct * 100,
            'risk_checks': risk_checks,
            'actual_outcome': actual_outcome,
            'risk_checks_valid': self._validate_risk_checks(risk_checks, actual_outcome)
        }

        self.shadow_trades.append(trade)

        if len(self.shadow_trades) > 200:
            self.shadow_trades = self.shadow_trades[-100:]

        return trade

    def _validate_risk_checks(self, risk_checks: Dict, actual_outcome: str) -> bool:
        """Validate if risk checks correctly predicted outcome."""
        # If risk checks said "don't trade" and outcome was bad, they were right
        if risk_checks.get('recommendation') == 'avoid' and actual_outcome in ['loss', 'liquidation']:
            return True
        # If risk checks said "ok to trade" and outcome was good, they were right
        if risk_checks.get('recommendation') in ['proceed', 'ok'] and actual_outcome == 'profit':
            return True
        # If risk checks said "ok" but outcome was bad, they were wrong
        if risk_checks.get('recommendation') in ['proceed', 'ok'] and actual_outcome in ['loss', 'liquidation']:
            return False
        return True  # Default to valid if unclear

    def get_shadow_trading_results(self) -> Dict:
        """Get shadow trading validation results."""
        if not self.shadow_trades:
            return {'total': 0}

        total = len(self.shadow_trades)
        valid_checks = sum(1 for t in self.shadow_trades if t['risk_checks_valid'])
        profitable = sum(1 for t in self.shadow_trades if t['pnl_pct'] > 0)
        losses = sum(1 for t in self.shadow_trades if t['pnl_pct'] < 0)
        liquidations = sum(1 for t in self.shadow_trades if t['actual_outcome'] == 'liquidation')

        avg_pnl = statistics.mean(t['pnl_pct'] for t in self.shadow_trades)
        avg_leverage = statistics.mean(t['leverage'] for t in self.shadow_trades)

        return {
            'total': total,
            'profitable': profitable,
            'losses': losses,
            'liquidations': liquidations,
            'win_rate': profitable / total * 100 if total > 0 else 0,
            'avg_pnl_pct': avg_pnl,
            'avg_leverage': avg_leverage,
            'risk_check_accuracy': valid_checks / total * 100 if total > 0 else 0
        }

    # =========================================================================
    # COMPREHENSIVE VALIDATION REPORT
    # =========================================================================

    def generate_validation_report(self) -> Dict:
        """Generate comprehensive risk validation report."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'alert_validation': {
                'overall': self.get_alert_accuracy(),
                'by_type': {
                    alert_type: self.get_alert_accuracy(alert_type)
                    for alert_type in self.alert_stats
                }
            },
            'leverage_validation': {
                'overall': self.get_leverage_effectiveness(),
                'by_regime': {
                    regime: self.get_leverage_effectiveness(regime)
                    for regime in self.leverage_outcomes
                }
            },
            'circuit_breaker': self.get_circuit_breaker_effectiveness(),
            'hysteresis': self.get_hysteresis_effectiveness(),
            'shadow_trading': self.get_shadow_trading_results(),
            'recommendations': self._generate_recommendations()
        }

        return report

    def _generate_recommendations(self) -> List[Dict]:
        """Generate tuning recommendations based on validation data."""
        recommendations = []

        # Alert recommendations
        alert_accuracy = self.get_alert_accuracy()
        if alert_accuracy.get('needs_tuning'):
            recommendations.append({
                'area': 'alert_thresholds',
                'issue': alert_accuracy.get('tuning_reason', 'Accuracy below target'),
                'recommendation': 'Review and adjust alert thresholds or hysteresis settings',
                'priority': 'HIGH'
            })

        # Leverage recommendations
        leverage_eff = self.get_leverage_effectiveness()
        if leverage_eff.get('needs_adjustment'):
            if leverage_eff.get('too_aggressive_pct', 0) > 20:
                recommendations.append({
                    'area': 'leverage_limits',
                    'issue': f"Too aggressive {leverage_eff['too_aggressive_pct']:.1f}% of time",
                    'recommendation': 'Reduce max leverage limits, especially in HIGH_VOLATILITY',
                    'priority': 'HIGH'
                })
            elif leverage_eff.get('too_conservative_pct', 0) > 30:
                recommendations.append({
                    'area': 'leverage_limits',
                    'issue': f"Too conservative {leverage_eff['too_conservative_pct']:.1f}% of time",
                    'recommendation': 'Consider increasing leverage in TRENDING/NORMAL regimes',
                    'priority': 'MEDIUM'
                })

        # Circuit breaker recommendations
        cb_eff = self.get_circuit_breaker_effectiveness()
        if cb_eff.get('needs_tuning'):
            if cb_eff.get('triggered_incorrectly', 0) > cb_eff.get('total', 1) * 0.2:
                recommendations.append({
                    'area': 'circuit_breaker',
                    'issue': 'Too many false triggers',
                    'recommendation': 'Increase circuit breaker thresholds (consecutive losses, session loss %)',
                    'priority': 'MEDIUM'
                })
            elif cb_eff.get('missed_triggers', 0) > cb_eff.get('total', 1) * 0.1:
                recommendations.append({
                    'area': 'circuit_breaker',
                    'issue': 'Missing critical triggers',
                    'recommendation': 'Lower circuit breaker thresholds for earlier activation',
                    'priority': 'HIGH'
                })

        # Hysteresis recommendations
        hyst_eff = self.get_hysteresis_effectiveness()
        if hyst_eff.get('recommendation') == 'increase_threshold':
            recommendations.append({
                'area': 'hysteresis',
                'issue': 'Alerts triggering too early (false positives)',
                'recommendation': 'Increase hysteresis_samples from 3 to 4-5',
                'priority': 'MEDIUM'
            })
        elif hyst_eff.get('recommendation') == 'decrease_threshold':
            recommendations.append({
                'area': 'hysteresis',
                'issue': 'Alerts triggering too late (missing issues)',
                'recommendation': 'Decrease hysteresis_samples from 3 to 2',
                'priority': 'HIGH'
            })

        return recommendations

    def save_report(self):
        """Save validation report to file."""
        try:
            report = self.generate_validation_report()
            with open(VALIDATION_RESULTS_FILE, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Validation report saved to {VALIDATION_RESULTS_FILE}")
        except Exception as e:
            logger.error(f"Failed to save validation report: {e}")

    def print_report(self):
        """Print validation report to console."""
        report = self.generate_validation_report()

        print("\n" + "=" * 70)
        print("RISK MANAGEMENT VALIDATION REPORT")
        print("=" * 70)
        print(f"Report Time: {report['timestamp']}")

        # Alert validation
        print("\n" + "-" * 50)
        print("ALERT VALIDATION")
        print("-" * 50)
        alert = report['alert_validation']['overall']
        if alert.get('total', 0) > 0:
            print(f"  Total alerts validated: {alert['total']}")
            print(f"  Precision: {alert['precision']*100:.1f}%")
            print(f"  Recall: {alert['recall']*100:.1f}%")
            print(f"  F1 Score: {alert['f1_score']*100:.1f}%")
            print(f"  False Positive Rate: {alert['false_positive_rate']*100:.1f}%")
            print(f"  False Negative Rate: {alert['false_negative_rate']*100:.1f}%")
            if alert.get('needs_tuning'):
                print(f"  TUNING NEEDED: {alert['tuning_reason']}")
        else:
            print("  No alert validations recorded yet")

        # Leverage validation
        print("\n" + "-" * 50)
        print("LEVERAGE VALIDATION")
        print("-" * 50)
        leverage = report['leverage_validation']['overall']
        if leverage.get('total', 0) > 0:
            print(f"  Total validations: {leverage['total']}")
            print(f"  Correct: {leverage['correct_pct']:.1f}%")
            print(f"  Too Aggressive: {leverage['too_aggressive_pct']:.1f}%")
            print(f"  Too Conservative: {leverage['too_conservative_pct']:.1f}%")
            print(f"  Effectiveness Score: {leverage['effectiveness_score']*100:.1f}%")
        else:
            print("  No leverage validations recorded yet")

        # Circuit breaker
        print("\n" + "-" * 50)
        print("CIRCUIT BREAKER VALIDATION")
        print("-" * 50)
        cb = report['circuit_breaker']
        if cb.get('total', 0) > 0:
            print(f"  Total events: {cb['total']}")
            print(f"  Triggered correctly: {cb['triggered_correctly']}")
            print(f"  Triggered incorrectly: {cb['triggered_incorrectly']}")
            print(f"  Missed triggers: {cb['missed_triggers']}")
            print(f"  Effectiveness: {cb['effectiveness_score']*100:.1f}%")
        else:
            print("  No circuit breaker events recorded yet")

        # Hysteresis
        print("\n" + "-" * 50)
        print("HYSTERESIS VALIDATION")
        print("-" * 50)
        hyst = report['hysteresis']
        if hyst.get('total', 0) > 0:
            print(f"  Total events: {hyst['total']}")
            print(f"  Accuracy: {hyst['accuracy']*100:.1f}%")
            print(f"  Triggered too early: {hyst['triggered_too_early']}")
            print(f"  Triggered too late: {hyst['triggered_too_late']}")
            print(f"  Recommendation: {hyst['recommendation']}")
        else:
            print("  No hysteresis events recorded yet")

        # Shadow trading
        print("\n" + "-" * 50)
        print("SHADOW TRADING VALIDATION")
        print("-" * 50)
        shadow = report['shadow_trading']
        if shadow.get('total', 0) > 0:
            print(f"  Total trades: {shadow['total']}")
            print(f"  Win rate: {shadow['win_rate']:.1f}%")
            print(f"  Average P&L: {shadow['avg_pnl_pct']:.2f}%")
            print(f"  Average leverage: {shadow['avg_leverage']:.1f}x")
            print(f"  Risk check accuracy: {shadow['risk_check_accuracy']:.1f}%")
        else:
            print("  No shadow trades recorded yet")

        # Recommendations
        print("\n" + "-" * 50)
        print("RECOMMENDATIONS")
        print("-" * 50)
        if report['recommendations']:
            for rec in report['recommendations']:
                print(f"  [{rec['priority']}] {rec['area']}")
                print(f"    Issue: {rec['issue']}")
                print(f"    Action: {rec['recommendation']}")
                print()
        else:
            print("  No tuning recommendations at this time")

        print("=" * 70)


# Singleton instance
_risk_validator_instance = None

def get_risk_validator() -> RiskValidator:
    """Get or create the singleton RiskValidator instance."""
    global _risk_validator_instance
    if _risk_validator_instance is None:
        _risk_validator_instance = RiskValidator()
    return _risk_validator_instance


if __name__ == "__main__":
    import random

    print("=" * 60)
    print("RISK VALIDATOR TEST")
    print("=" * 60)

    validator = RiskValidator()

    # Simulate alert validations
    print("\nSimulating alert validations...")
    for i in range(50):
        alert_type = random.choice(['drawdown', 'margin', 'averaging'])
        value = random.uniform(0.05, 0.25)
        threshold = 0.15
        triggered = value >= threshold and random.random() > 0.3  # Some hysteresis effect
        subsequent = value + random.uniform(-0.05, 0.05)
        validator.record_alert_validation(alert_type, triggered, value, threshold, subsequent)

    # Simulate leverage validations
    print("Simulating leverage validations...")
    regimes = ['HIGH_VOLATILITY', 'TRENDING', 'NORMAL', 'RANGING']
    for i in range(40):
        regime = random.choice(regimes)
        recommended = {'HIGH_VOLATILITY': 4, 'TRENDING': 8, 'NORMAL': 10, 'RANGING': 10}[regime]
        used = recommended + random.randint(-2, 2)
        outcome = random.choices(['profit', 'loss', 'liquidation'], weights=[0.5, 0.45, 0.05])[0]
        validator.record_leverage_validation(
            f"TEST{i}/USDT", regime, recommended, used,
            random.uniform(1.0, 2.5), random.uniform(-10, 20), outcome
        )

    # Simulate circuit breaker events
    print("Simulating circuit breaker events...")
    for i in range(15):
        triggered = random.random() > 0.5
        conditions = {'session_pnl': random.uniform(-0.20, 0.05)}
        outcome = {'session_pnl': conditions['session_pnl'] + random.uniform(-0.10, 0.05),
                  'positions_closed': random.randint(0, 3) if triggered else 0}
        validator.record_circuit_breaker_event(
            triggered, 'session_loss' if triggered else 'none',
            conditions, outcome
        )

    # Simulate hysteresis events
    print("Simulating hysteresis events...")
    for i in range(30):
        breach_count = random.randint(1, 5)
        threshold = 3
        triggered = breach_count >= threshold
        was_real = random.random() > 0.3
        validator.record_hysteresis_event('drawdown', breach_count, threshold, triggered, was_real)

    # Simulate shadow trades
    print("Simulating shadow trades...")
    for i in range(25):
        entry = 100.0
        exit_price = entry * (1 + random.uniform(-0.05, 0.08))
        outcome = 'profit' if exit_price > entry else 'loss'
        if random.random() < 0.05:
            outcome = 'liquidation'
        validator.record_shadow_trade(
            f"BTC{i}/USDT", random.choice(['long', 'short']),
            random.randint(3, 10), entry, exit_price,
            {'recommendation': random.choice(['proceed', 'avoid', 'ok'])},
            outcome
        )

    # Print report
    validator.print_report()

    # Save report
    validator.save_report()

    print("\nRisk Validator test completed!")
