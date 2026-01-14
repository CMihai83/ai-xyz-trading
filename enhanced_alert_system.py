#!/usr/bin/env python3
"""
Enhanced Alert Detection System - Sprint 9
V1.0.0 - January 2026

Purpose: Reduce alert false negative rate from 62.8% to <40%

Key improvements:
1. Early warning signals - Detect patterns before threshold breach
2. Velocity-based detection - Rapid changes trigger alerts
3. Multi-signal fusion - Multiple weak signals = strong alert
4. Adaptive hysteresis - CRITICAL alerts need fewer samples
5. Proximity alerting - Warn when approaching thresholds

Author: Claude + Grok Consortium
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import logging
import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """Enhanced alert levels with pre-warning."""
    INFO = "INFO"              # Informational only
    EARLY_WARNING = "EARLY"    # Approaching threshold
    WARNING = "WARNING"        # Threshold breached
    CRITICAL = "CRITICAL"      # Severe breach
    EMERGENCY = "EMERGENCY"    # Requires immediate action


class SignalType(Enum):
    """Types of detection signals."""
    THRESHOLD_BREACH = "THRESHOLD"       # Direct threshold breach
    VELOCITY = "VELOCITY"                 # Rapid change detected
    PROXIMITY = "PROXIMITY"               # Approaching threshold
    PATTERN = "PATTERN"                   # Historical pattern match
    MULTI_SIGNAL = "MULTI_SIGNAL"         # Combined weak signals


@dataclass
class DetectionSignal:
    """Individual detection signal."""
    signal_type: SignalType
    metric_name: str
    current_value: float
    reference_value: float  # Threshold or previous value
    strength: float         # 0-1 signal strength
    timestamp: datetime = field(default_factory=datetime.now)
    message: str = ""


@dataclass
class EnhancedAlert:
    """Enhanced alert with multiple signals."""
    level: AlertLevel
    category: str
    signals: List[DetectionSignal]
    aggregate_strength: float  # Combined strength of all signals
    timestamp: datetime
    symbol: Optional[str] = None
    recommended_action: str = ""
    expires_at: Optional[datetime] = None  # For early warnings


@dataclass
class AdaptiveHysteresisConfig:
    """Adaptive hysteresis based on severity."""
    # Samples required for each level
    info_samples: int = 5
    early_warning_samples: int = 3
    warning_samples: int = 2
    critical_samples: int = 1  # CRITICAL triggers immediately!
    emergency_samples: int = 1  # EMERGENCY triggers immediately!

    # Velocity detection thresholds (% change per minute)
    velocity_warning: float = 0.05     # 5%/min
    velocity_critical: float = 0.10    # 10%/min

    # Proximity detection (% away from threshold)
    proximity_early: float = 0.20      # 20% away → early warning
    proximity_imminent: float = 0.10   # 10% away → imminent warning


class EnhancedAlertDetector:
    """
    Enhanced alert detection with improved recall.

    Target: Reduce false negative rate from 62.8% to <40%
    """

    VERSION = "1.0.0"

    # Metric thresholds (same as RiskAlertManager for compatibility)
    THRESHOLDS = {
        'drawdown': {
            AlertLevel.EARLY_WARNING: 0.07,  # 7% drawdown
            AlertLevel.WARNING: 0.10,
            AlertLevel.CRITICAL: 0.15,
            AlertLevel.EMERGENCY: 0.20
        },
        'margin_used': {
            AlertLevel.EARLY_WARNING: 0.60,
            AlertLevel.WARNING: 0.70,
            AlertLevel.CRITICAL: 0.85,
            AlertLevel.EMERGENCY: 0.95
        },
        'averaging_positions': {
            AlertLevel.EARLY_WARNING: 3,
            AlertLevel.WARNING: 5,
            AlertLevel.CRITICAL: 8,
            AlertLevel.EMERGENCY: 10
        },
        'position_loss_pct': {  # Individual position P&L
            AlertLevel.EARLY_WARNING: -0.15,  # -15%
            AlertLevel.WARNING: -0.25,        # -25%
            AlertLevel.CRITICAL: -0.50,       # -50%
            AlertLevel.EMERGENCY: -0.75       # -75%
        },
        'averaging_steps': {
            AlertLevel.EARLY_WARNING: 2,
            AlertLevel.WARNING: 3,
            AlertLevel.CRITICAL: 4,
            AlertLevel.EMERGENCY: 5
        }
    }

    def __init__(self, config: AdaptiveHysteresisConfig = None):
        self.config = config or AdaptiveHysteresisConfig()

        # Metric history for velocity and trend detection
        self.metric_history: Dict[str, deque] = {}
        self.max_history_size = 60  # 60 data points

        # Breach tracking for hysteresis
        self.breach_counts: Dict[str, int] = {}

        # Signal fusion buffer
        self.pending_signals: Dict[str, List[DetectionSignal]] = {}

        # Alert history for deduplication
        self.recent_alerts: List[EnhancedAlert] = []
        self.alert_cooldown_minutes = 5

        # Statistics tracking
        self.stats = {
            'total_checks': 0,
            'alerts_triggered': 0,
            'early_warnings': 0,
            'velocity_detections': 0,
            'proximity_detections': 0,
            'multi_signal_fusions': 0
        }

        # Redis connection (optional)
        self.redis_client = self._connect_redis()

    def _connect_redis(self) -> Optional[redis.Redis]:
        """Connect to Redis for state persistence."""
        try:
            client = redis.Redis(
                host=os.getenv('REDIS_HOST', 'localhost'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                db=1,
                decode_responses=True
            )
            client.ping()
            return client
        except Exception:
            return None

    def _record_metric(self, metric_name: str, value: float, symbol: str = None):
        """Record metric value for velocity and trend analysis."""
        key = f"{metric_name}:{symbol}" if symbol else metric_name

        if key not in self.metric_history:
            self.metric_history[key] = deque(maxlen=self.max_history_size)

        self.metric_history[key].append({
            'timestamp': datetime.now(),
            'value': value
        })

    def _calculate_velocity(self, metric_name: str, symbol: str = None) -> float:
        """Calculate rate of change per minute."""
        key = f"{metric_name}:{symbol}" if symbol else metric_name

        if key not in self.metric_history or len(self.metric_history[key]) < 2:
            return 0.0

        history = list(self.metric_history[key])

        # Get first and last values
        first = history[0]
        last = history[-1]

        time_diff = (last['timestamp'] - first['timestamp']).total_seconds() / 60
        if time_diff < 0.1:  # Less than 6 seconds
            return 0.0

        value_diff = last['value'] - first['value']

        # Return rate of change per minute (as percentage if > 1 for pct metrics)
        if abs(first['value']) > 0.001:
            return (value_diff / abs(first['value'])) / time_diff
        return 0.0

    def _check_proximity(self, metric_name: str, value: float) -> Optional[DetectionSignal]:
        """Check if value is approaching a threshold (proximity detection)."""
        if metric_name not in self.THRESHOLDS:
            return None

        thresholds = self.THRESHOLDS[metric_name]
        warning_thresh = thresholds.get(AlertLevel.WARNING, 0)

        if warning_thresh == 0:
            return None

        # Calculate distance to threshold
        if warning_thresh > 0:  # Positive threshold (breach when > threshold)
            distance_pct = (warning_thresh - value) / warning_thresh
            approaching = value < warning_thresh and distance_pct < self.config.proximity_early
        else:  # Negative threshold (breach when < threshold)
            distance_pct = (value - warning_thresh) / abs(warning_thresh)
            approaching = value > warning_thresh and distance_pct < self.config.proximity_early

        if approaching:
            strength = 1.0 - (distance_pct / self.config.proximity_early)
            return DetectionSignal(
                signal_type=SignalType.PROXIMITY,
                metric_name=metric_name,
                current_value=value,
                reference_value=warning_thresh,
                strength=min(0.9, strength),  # Cap at 0.9 for proximity
                message=f"{metric_name} at {value:.2%} approaching threshold {warning_thresh:.2%}"
            )

        return None

    def _check_velocity_breach(self, metric_name: str, symbol: str = None) -> Optional[DetectionSignal]:
        """Check for rapid changes (velocity-based detection)."""
        velocity = self._calculate_velocity(metric_name, symbol)

        if abs(velocity) >= self.config.velocity_critical:
            return DetectionSignal(
                signal_type=SignalType.VELOCITY,
                metric_name=metric_name,
                current_value=velocity,
                reference_value=self.config.velocity_critical,
                strength=1.0,  # Critical velocity = full strength
                message=f"Rapid change detected: {velocity:.2%}/min (critical threshold: {self.config.velocity_critical:.2%}/min)"
            )
        elif abs(velocity) >= self.config.velocity_warning:
            return DetectionSignal(
                signal_type=SignalType.VELOCITY,
                metric_name=metric_name,
                current_value=velocity,
                reference_value=self.config.velocity_warning,
                strength=0.7,
                message=f"Elevated change rate: {velocity:.2%}/min"
            )

        return None

    def _get_adaptive_hysteresis(self, level: AlertLevel) -> int:
        """Get hysteresis samples required for given alert level."""
        mapping = {
            AlertLevel.INFO: self.config.info_samples,
            AlertLevel.EARLY_WARNING: self.config.early_warning_samples,
            AlertLevel.WARNING: self.config.warning_samples,
            AlertLevel.CRITICAL: self.config.critical_samples,
            AlertLevel.EMERGENCY: self.config.emergency_samples
        }
        return mapping.get(level, self.config.warning_samples)

    def _check_hysteresis(self, alert_key: str, level: AlertLevel, is_breaching: bool) -> bool:
        """Check if alert passes adaptive hysteresis filter."""
        if is_breaching:
            self.breach_counts[alert_key] = self.breach_counts.get(alert_key, 0) + 1
        else:
            # Only reset if NOT breaching (value recovered)
            # Don't reset if we're just below threshold temporarily
            if self.breach_counts.get(alert_key, 0) > 0:
                # Decay instead of hard reset for better recall
                self.breach_counts[alert_key] = max(0, self.breach_counts.get(alert_key, 0) - 1)

        required = self._get_adaptive_hysteresis(level)
        return self.breach_counts.get(alert_key, 0) >= required

    def _check_threshold_breach(self, metric_name: str, value: float) -> Tuple[Optional[AlertLevel], Optional[DetectionSignal]]:
        """Check for threshold breach and return level + signal."""
        if metric_name not in self.THRESHOLDS:
            return None, None

        thresholds = self.THRESHOLDS[metric_name]

        # Check from highest to lowest severity
        for level in [AlertLevel.EMERGENCY, AlertLevel.CRITICAL, AlertLevel.WARNING, AlertLevel.EARLY_WARNING]:
            if level not in thresholds:
                continue

            threshold = thresholds[level]

            # Determine breach direction
            is_breach = False
            if isinstance(threshold, int):  # Count-based threshold
                is_breach = value >= threshold
            elif threshold > 0:  # Positive = breach when exceeds
                is_breach = value >= threshold
            else:  # Negative = breach when below
                is_breach = value <= threshold

            if is_breach:
                # Check hysteresis
                alert_key = f"{metric_name}:{level.value}"
                if self._check_hysteresis(alert_key, level, True):
                    return level, DetectionSignal(
                        signal_type=SignalType.THRESHOLD_BREACH,
                        metric_name=metric_name,
                        current_value=value,
                        reference_value=threshold,
                        strength=1.0 if level in [AlertLevel.CRITICAL, AlertLevel.EMERGENCY] else 0.8,
                        message=f"{metric_name} breached {level.value} threshold: {value} vs {threshold}"
                    )

        # No breach - reset hysteresis for this metric
        for level in AlertLevel:
            alert_key = f"{metric_name}:{level.value}"
            self._check_hysteresis(alert_key, level, False)

        return None, None

    def _fuse_signals(self, metric_name: str, signals: List[DetectionSignal]) -> Optional[EnhancedAlert]:
        """
        Fuse multiple weak signals into a strong alert (multi-signal fusion).

        Multiple weak signals combined can trigger an alert even if no single
        signal is strong enough. This improves recall for edge cases.
        """
        if len(signals) < 2:
            return None

        # Calculate aggregate strength
        aggregate = sum(s.strength for s in signals) / len(signals)

        # Boost if multiple signal types
        signal_types = set(s.signal_type for s in signals)
        if len(signal_types) >= 2:
            aggregate *= 1.2  # 20% boost for diversity

        # Trigger if aggregate strength exceeds threshold
        if aggregate >= 0.6:
            self.stats['multi_signal_fusions'] += 1

            return EnhancedAlert(
                level=AlertLevel.WARNING if aggregate >= 0.8 else AlertLevel.EARLY_WARNING,
                category=metric_name,
                signals=signals,
                aggregate_strength=min(1.0, aggregate),
                timestamp=datetime.now(),
                recommended_action="Monitor closely - multiple warning signs detected"
            )

        return None

    def check_metric(self, metric_name: str, value: float, symbol: str = None) -> List[EnhancedAlert]:
        """
        Check a metric value and return any triggered alerts.

        This is the main entry point for alert detection.
        """
        self.stats['total_checks'] += 1
        alerts = []
        signals = []

        # Record metric for history
        self._record_metric(metric_name, value, symbol)

        # 1. Check threshold breach
        level, breach_signal = self._check_threshold_breach(metric_name, value)
        if breach_signal:
            signals.append(breach_signal)

        # 2. Check velocity (rapid change)
        velocity_signal = self._check_velocity_breach(metric_name, symbol)
        if velocity_signal:
            signals.append(velocity_signal)
            self.stats['velocity_detections'] += 1

        # 3. Check proximity (approaching threshold)
        if level is None:  # Only check proximity if not already breached
            proximity_signal = self._check_proximity(metric_name, value)
            if proximity_signal:
                signals.append(proximity_signal)
                self.stats['proximity_detections'] += 1

        # 4. Create alert if we have a threshold breach
        if level and breach_signal:
            alert = EnhancedAlert(
                level=level,
                category=metric_name,
                signals=signals,
                aggregate_strength=max(s.strength for s in signals),
                timestamp=datetime.now(),
                symbol=symbol,
                recommended_action=self._get_recommended_action(metric_name, level, value)
            )
            alerts.append(alert)
            self.stats['alerts_triggered'] += 1

            if level == AlertLevel.EARLY_WARNING:
                self.stats['early_warnings'] += 1

        # 5. Try signal fusion if no direct alert
        elif len(signals) >= 2:
            fused_alert = self._fuse_signals(metric_name, signals)
            if fused_alert:
                fused_alert.symbol = symbol
                alerts.append(fused_alert)
                self.stats['alerts_triggered'] += 1

        # Store pending signals for fusion across metrics
        if symbol:
            signal_key = symbol
        else:
            signal_key = 'global'

        if signal_key not in self.pending_signals:
            self.pending_signals[signal_key] = []
        self.pending_signals[signal_key].extend(signals)

        # Clean old pending signals (keep last 5 minutes)
        cutoff = datetime.now() - timedelta(minutes=5)
        self.pending_signals[signal_key] = [
            s for s in self.pending_signals[signal_key]
            if s.timestamp > cutoff
        ]

        return alerts

    def _get_recommended_action(self, metric_name: str, level: AlertLevel, value: float) -> str:
        """Get recommended action based on alert type and level."""
        actions = {
            'drawdown': {
                AlertLevel.EARLY_WARNING: "Monitor drawdown - consider reducing exposure",
                AlertLevel.WARNING: "Review positions - reduce risk if possible",
                AlertLevel.CRITICAL: "Immediately close losing positions",
                AlertLevel.EMERGENCY: "EMERGENCY: Close all positions to prevent further losses"
            },
            'margin_used': {
                AlertLevel.EARLY_WARNING: "Monitor margin usage",
                AlertLevel.WARNING: "Reduce position sizes or close some positions",
                AlertLevel.CRITICAL: "Close positions to free margin immediately",
                AlertLevel.EMERGENCY: "EMERGENCY: Liquidation risk - close positions NOW"
            },
            'averaging_steps': {
                AlertLevel.EARLY_WARNING: "Position is accumulating - monitor closely",
                AlertLevel.WARNING: "Consider partial profit taking",
                AlertLevel.CRITICAL: "Close position if profitable, monitor if not",
                AlertLevel.EMERGENCY: "CRITICAL: Max averaging reached - close at next profit opportunity"
            },
            'position_loss_pct': {
                AlertLevel.EARLY_WARNING: "Position is losing - review thesis",
                AlertLevel.WARNING: "Consider stop loss",
                AlertLevel.CRITICAL: "Close position to limit losses",
                AlertLevel.EMERGENCY: "EMERGENCY: Close position immediately"
            }
        }

        return actions.get(metric_name, {}).get(level, "Take appropriate action")

    def get_stats(self) -> Dict:
        """Get detection statistics."""
        return {
            **self.stats,
            'detection_rate': (
                (self.stats['velocity_detections'] + self.stats['proximity_detections'] +
                 self.stats['multi_signal_fusions']) / max(1, self.stats['total_checks'])
            ),
            'early_warning_rate': self.stats['early_warnings'] / max(1, self.stats['alerts_triggered'])
        }

    def reset_stats(self):
        """Reset statistics."""
        for key in self.stats:
            self.stats[key] = 0


def test_enhanced_alert_system():
    """Test the enhanced alert detection system."""
    print("=" * 60)
    print("Testing Enhanced Alert Detection System V1.0.0")
    print("=" * 60)

    detector = EnhancedAlertDetector()

    # Test 1: Gradual drawdown approach - should trigger EARLY_WARNING at 0.07
    print("\n[Test 1] Gradual drawdown increase:")
    for dd in [0.05, 0.06, 0.07, 0.08, 0.09, 0.10, 0.11, 0.12, 0.15]:
        alerts = detector.check_metric('drawdown', dd)
        if alerts:
            for alert in alerts:
                print(f"  ✅ {alert.level.value} at {dd:.0%}: {alert.signals[0].message}")

    # Test 2: Rapid change (velocity detection)
    print("\n[Test 2] Rapid margin increase:")
    detector2 = EnhancedAlertDetector()
    for margin in [0.40, 0.45, 0.55, 0.65]:  # Rapid 25% increase
        alerts = detector2.check_metric('margin_used', margin)
        if alerts:
            for alert in alerts:
                print(f"  ✅ {alert.level.value}: {alert.aggregate_strength:.2f} strength")
                for sig in alert.signals:
                    print(f"      - {sig.signal_type.value}: {sig.message}")

    # Test 3: Position loss detection
    print("\n[Test 3] Position loss progression:")
    detector3 = EnhancedAlertDetector()
    for loss in [-0.10, -0.15, -0.20, -0.25, -0.30]:
        alerts = detector3.check_metric('position_loss_pct', loss, symbol='TEST/USDT')
        if alerts:
            for alert in alerts:
                print(f"  ✅ {alert.level.value} for {alert.symbol}: {alert.recommended_action}")

    # Test 4: Averaging steps
    print("\n[Test 4] Averaging steps increase:")
    detector4 = EnhancedAlertDetector()
    for steps in [1, 2, 3, 4, 5]:
        alerts = detector4.check_metric('averaging_steps', steps, symbol='PEOPLE/USDT')
        if alerts:
            for alert in alerts:
                print(f"  ✅ {alert.level.value} for {alert.symbol}: Step {steps}")

    # Print statistics
    print("\n" + "=" * 60)
    print("Detection Statistics:")
    print("=" * 60)
    all_stats = [detector.get_stats(), detector2.get_stats(),
                 detector3.get_stats(), detector4.get_stats()]

    totals = {}
    for stats in all_stats:
        for key, val in stats.items():
            if key not in totals:
                totals[key] = 0
            totals[key] += val if isinstance(val, int) else 0

    print(f"  Total checks: {totals.get('total_checks', 0)}")
    print(f"  Alerts triggered: {totals.get('alerts_triggered', 0)}")
    print(f"  Early warnings: {totals.get('early_warnings', 0)}")
    print(f"  Velocity detections: {totals.get('velocity_detections', 0)}")
    print(f"  Proximity detections: {totals.get('proximity_detections', 0)}")
    print(f"  Multi-signal fusions: {totals.get('multi_signal_fusions', 0)}")

    print("\n✅ Enhanced Alert System Test Complete")


if __name__ == '__main__':
    test_enhanced_alert_system()
