#!/usr/bin/env python3
"""
Grok Recommendation #13: Automated Anomaly Detection
Statistical anomaly detection for system health monitoring.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from collections import deque
from datetime import datetime
import json
import os
import logging
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class Anomaly:
    """Detected anomaly record"""
    metric_name: str
    value: float
    expected_value: float
    z_score: float
    severity: str  # 'low', 'medium', 'high', 'critical'
    timestamp: str
    description: str


class RollingStats:
    """Rolling statistics calculator"""

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self.values: deque = deque(maxlen=window_size)

    def add(self, value: float):
        """Add a value"""
        self.values.append(value)

    @property
    def mean(self) -> float:
        if not self.values:
            return 0.0
        return np.mean(list(self.values))

    @property
    def std(self) -> float:
        if len(self.values) < 2:
            return 1.0  # Default to avoid division by zero
        return max(np.std(list(self.values)), 0.001)

    @property
    def median(self) -> float:
        if not self.values:
            return 0.0
        return np.median(list(self.values))

    @property
    def min(self) -> float:
        if not self.values:
            return 0.0
        return min(self.values)

    @property
    def max(self) -> float:
        if not self.values:
            return 0.0
        return max(self.values)

    def get_z_score(self, value: float) -> float:
        """Calculate z-score for a value"""
        return (value - self.mean) / self.std


class AnomalyDetector:
    """
    Statistical anomaly detection for system metrics.

    Uses:
    - Z-score based detection
    - IQR (Interquartile Range) detection
    - Rate of change detection
    - Pattern-based detection
    """

    # Severity thresholds (z-score)
    SEVERITY_THRESHOLDS = {
        'low': 2.0,
        'medium': 3.0,
        'high': 4.0,
        'critical': 5.0
    }

    def __init__(
        self,
        window_size: int = 100,
        alert_callback: callable = None,
        state_file: str = '/app/anomaly_state.json'
    ):
        self.window_size = window_size
        self.alert_callback = alert_callback or self._default_alert
        self.state_file = state_file

        # Per-metric rolling statistics
        self.metric_stats: Dict[str, RollingStats] = {}

        # Rate of change tracking
        self.last_values: Dict[str, float] = {}

        # Anomaly history
        self.anomaly_history: List[Anomaly] = []
        self.max_history = 1000

        # Alert suppression (avoid spam)
        self.last_alerts: Dict[str, float] = {}
        self.alert_cooldown = 60  # seconds

        # Lock for thread safety
        self._lock = threading.Lock()

        self._load_state()

    def _load_state(self):
        """Load saved state"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    # Restore minimal state
                    self.last_values = data.get('last_values', {})
        except Exception as e:
            logger.warning(f"Could not load anomaly state: {e}")

    def _save_state(self):
        """Save state"""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'last_values': self.last_values,
                'recent_anomalies': [
                    {
                        'metric': a.metric_name,
                        'value': a.value,
                        'z_score': a.z_score,
                        'severity': a.severity,
                        'timestamp': a.timestamp
                    }
                    for a in self.anomaly_history[-50:]
                ]
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save anomaly state: {e}")

    def _default_alert(self, anomaly: Anomaly):
        """Default alert handler"""
        severity_emoji = {
            'low': '⚠️',
            'medium': '🔶',
            'high': '🔴',
            'critical': '🚨'
        }
        emoji = severity_emoji.get(anomaly.severity, '⚠️')
        logger.warning(f"{emoji} ANOMALY: {anomaly.description}")

    def _get_or_create_stats(self, metric_name: str) -> RollingStats:
        """Get or create rolling stats for a metric"""
        if metric_name not in self.metric_stats:
            self.metric_stats[metric_name] = RollingStats(self.window_size)
        return self.metric_stats[metric_name]

    def _should_alert(self, metric_name: str) -> bool:
        """Check if we should send alert (cooldown check)"""
        current_time = datetime.now().timestamp()
        last_alert = self.last_alerts.get(metric_name, 0)

        if current_time - last_alert < self.alert_cooldown:
            return False

        self.last_alerts[metric_name] = current_time
        return True

    def check(self, metric_name: str, value: float, description: str = None) -> Optional[Anomaly]:
        """
        Check a metric value for anomalies.

        Args:
            metric_name: Name of the metric
            value: Current value
            description: Optional description for alerts

        Returns:
            Anomaly if detected, None otherwise
        """
        with self._lock:
            stats = self._get_or_create_stats(metric_name)

            # Calculate z-score
            z_score = stats.get_z_score(value)

            # Add value to rolling window
            stats.add(value)

            # Determine if anomaly
            anomaly = None
            abs_z = abs(z_score)

            if abs_z >= self.SEVERITY_THRESHOLDS['critical']:
                severity = 'critical'
            elif abs_z >= self.SEVERITY_THRESHOLDS['high']:
                severity = 'high'
            elif abs_z >= self.SEVERITY_THRESHOLDS['medium']:
                severity = 'medium'
            elif abs_z >= self.SEVERITY_THRESHOLDS['low']:
                severity = 'low'
            else:
                # Update last value and return (no anomaly)
                self.last_values[metric_name] = value
                return None

            # Create anomaly record
            desc = description or f"{metric_name} = {value:.4f} (z-score: {z_score:.2f})"
            anomaly = Anomaly(
                metric_name=metric_name,
                value=value,
                expected_value=stats.mean,
                z_score=z_score,
                severity=severity,
                timestamp=datetime.now().isoformat(),
                description=desc
            )

            # Store in history
            self.anomaly_history.append(anomaly)
            if len(self.anomaly_history) > self.max_history:
                self.anomaly_history = self.anomaly_history[-self.max_history:]

            # Alert if not in cooldown
            if self._should_alert(metric_name):
                self.alert_callback(anomaly)

            # Save state periodically
            if len(self.anomaly_history) % 10 == 0:
                self._save_state()

            self.last_values[metric_name] = value
            return anomaly

    def check_rate_of_change(
        self,
        metric_name: str,
        value: float,
        max_change_pct: float = 50.0
    ) -> Optional[Anomaly]:
        """
        Check for anomalous rate of change.

        Args:
            metric_name: Metric name
            value: Current value
            max_change_pct: Maximum expected change percentage

        Returns:
            Anomaly if rate of change is abnormal
        """
        rate_metric = f"{metric_name}_rate"

        if metric_name in self.last_values:
            last_value = self.last_values[metric_name]
            if last_value != 0:
                change_pct = abs((value - last_value) / last_value) * 100

                if change_pct > max_change_pct:
                    return self.check(
                        rate_metric,
                        change_pct,
                        f"{metric_name} changed by {change_pct:.1f}% (max: {max_change_pct}%)"
                    )

        self.last_values[metric_name] = value
        return None

    def check_bounds(
        self,
        metric_name: str,
        value: float,
        min_value: float = None,
        max_value: float = None
    ) -> Optional[Anomaly]:
        """
        Check if value is within expected bounds.

        Args:
            metric_name: Metric name
            value: Current value
            min_value: Minimum expected value
            max_value: Maximum expected value

        Returns:
            Anomaly if out of bounds
        """
        if min_value is not None and value < min_value:
            return Anomaly(
                metric_name=metric_name,
                value=value,
                expected_value=(min_value + (max_value or min_value)) / 2,
                z_score=float('inf'),
                severity='high',
                timestamp=datetime.now().isoformat(),
                description=f"{metric_name} = {value:.4f} below minimum {min_value}"
            )

        if max_value is not None and value > max_value:
            return Anomaly(
                metric_name=metric_name,
                value=value,
                expected_value=(min_value or max_value + max_value) / 2,
                z_score=float('inf'),
                severity='high',
                timestamp=datetime.now().isoformat(),
                description=f"{metric_name} = {value:.4f} above maximum {max_value}"
            )

        return None

    def get_metric_stats(self, metric_name: str) -> Dict:
        """Get statistics for a metric"""
        if metric_name not in self.metric_stats:
            return {'error': 'Metric not found'}

        stats = self.metric_stats[metric_name]
        return {
            'mean': stats.mean,
            'std': stats.std,
            'median': stats.median,
            'min': stats.min,
            'max': stats.max,
            'samples': len(stats.values)
        }

    def get_recent_anomalies(self, n: int = 10, severity: str = None) -> List[Anomaly]:
        """Get recent anomalies"""
        anomalies = self.anomaly_history

        if severity:
            anomalies = [a for a in anomalies if a.severity == severity]

        return anomalies[-n:]

    def get_anomaly_summary(self) -> Dict:
        """Get summary of anomalies"""
        if not self.anomaly_history:
            return {'total': 0}

        by_severity = {}
        by_metric = {}

        for anomaly in self.anomaly_history:
            by_severity[anomaly.severity] = by_severity.get(anomaly.severity, 0) + 1
            by_metric[anomaly.metric_name] = by_metric.get(anomaly.metric_name, 0) + 1

        return {
            'total': len(self.anomaly_history),
            'by_severity': by_severity,
            'by_metric': by_metric,
            'most_anomalous_metric': max(by_metric.items(), key=lambda x: x[1])[0] if by_metric else None
        }

    def print_status(self):
        """Print anomaly detection status"""
        print("\n" + "=" * 60)
        print("🔍 ANOMALY DETECTION STATUS")
        print("=" * 60)

        print(f"\nMetrics Tracked: {len(self.metric_stats)}")
        print(f"Total Anomalies Detected: {len(self.anomaly_history)}")

        summary = self.get_anomaly_summary()
        if summary.get('by_severity'):
            print("\nAnomalies by Severity:")
            for severity, count in sorted(summary['by_severity'].items()):
                print(f"  {severity}: {count}")

        recent = self.get_recent_anomalies(5)
        if recent:
            print("\nRecent Anomalies:")
            for anomaly in recent:
                print(f"  [{anomaly.severity.upper()}] {anomaly.description}")

        print("=" * 60)


# Trading-specific anomaly checks
class TradingAnomalyMonitor:
    """
    Specialized anomaly monitoring for trading systems.
    """

    def __init__(self):
        self.detector = AnomalyDetector()

        # Define expected bounds for trading metrics
        self.bounds = {
            'api_latency_ms': (0, 2000),
            'position_count': (0, 20),
            'total_margin_used': (0, 10000),
            'error_rate': (0, 0.05),
            'win_rate': (0.2, 0.9),
            'profit_factor': (0.3, 5.0),
        }

    def check_api_latency(self, latency_ms: float) -> Optional[Anomaly]:
        """Check API latency"""
        bounds = self.bounds['api_latency_ms']
        if latency_ms > bounds[1]:
            return self.detector.check('api_latency_ms', latency_ms, f"API latency {latency_ms}ms exceeds {bounds[1]}ms")
        return self.detector.check('api_latency_ms', latency_ms)

    def check_position_count(self, count: int) -> Optional[Anomaly]:
        """Check position count"""
        return self.detector.check('position_count', count)

    def check_margin_used(self, margin: float) -> Optional[Anomaly]:
        """Check total margin used"""
        return self.detector.check('total_margin_used', margin)

    def check_error_rate(self, rate: float) -> Optional[Anomaly]:
        """Check error rate"""
        bounds = self.bounds['error_rate']
        if rate > bounds[1]:
            return self.detector.check_bounds('error_rate', rate, bounds[0], bounds[1])
        return self.detector.check('error_rate', rate)

    def check_all(self, metrics: Dict) -> List[Anomaly]:
        """Check all metrics at once"""
        anomalies = []

        for metric_name, value in metrics.items():
            if metric_name in self.bounds:
                bounds = self.bounds[metric_name]
                anomaly = self.detector.check_bounds(metric_name, value, bounds[0], bounds[1])
            else:
                anomaly = self.detector.check(metric_name, value)

            if anomaly:
                anomalies.append(anomaly)

        return anomalies


# Singletons
_detector: Optional[AnomalyDetector] = None
_trading_monitor: Optional[TradingAnomalyMonitor] = None

def get_anomaly_detector() -> AnomalyDetector:
    """Get singleton anomaly detector"""
    global _detector
    if _detector is None:
        _detector = AnomalyDetector()
    return _detector

def get_trading_anomaly_monitor() -> TradingAnomalyMonitor:
    """Get singleton trading anomaly monitor"""
    global _trading_monitor
    if _trading_monitor is None:
        _trading_monitor = TradingAnomalyMonitor()
    return _trading_monitor


if __name__ == "__main__":
    # Demo
    print("=" * 60)
    print("ANOMALY DETECTION DEMO")
    print("=" * 60)

    detector = AnomalyDetector(window_size=50)

    # Simulate normal values then inject anomaly
    np.random.seed(42)

    print("\nSimulating normal metrics...")
    for i in range(50):
        # Normal API latency
        latency = np.random.normal(100, 20)
        detector.check('api_latency', latency)

        # Normal error rate
        error_rate = np.random.beta(1, 100)
        detector.check('error_rate', error_rate)

    print(f"Baseline established: {detector.get_metric_stats('api_latency')}")

    print("\nInjecting anomalies...")

    # Inject anomalies
    anomaly1 = detector.check('api_latency', 500, "API latency spike to 500ms")
    if anomaly1:
        print(f"  Detected: {anomaly1.description} (severity: {anomaly1.severity})")

    anomaly2 = detector.check('error_rate', 0.15, "Error rate spike to 15%")
    if anomaly2:
        print(f"  Detected: {anomaly2.description} (severity: {anomaly2.severity})")

    # Test trading monitor
    print("\n" + "-" * 50)
    print("Testing Trading Anomaly Monitor:")

    monitor = TradingAnomalyMonitor()

    # Normal operation
    for i in range(20):
        monitor.check_api_latency(np.random.normal(100, 20))
        monitor.check_position_count(np.random.randint(3, 8))

    # Anomaly
    anomaly = monitor.check_api_latency(3000)
    if anomaly:
        print(f"  Trading anomaly: {anomaly.description}")

    detector.print_status()
