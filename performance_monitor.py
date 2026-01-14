#!/usr/bin/env python3
"""
Real-Time Performance Monitor for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Tracks and optimizes system performance:
- Trade execution latency (<100ms target)
- Alert triggering latency
- API response times
- CPU/memory usage during high-volatility
- System bottleneck identification

Sprint 6 - Grok Recommendation:
"Implement latency tracking for trade execution and alert triggering.
Optimize resource usage during high-volatility periods."

Author: Claude + Grok Consortium
"""

import os
import time
import json
import psutil
import threading
import statistics
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from collections import deque
from enum import Enum
import logging
import redis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Results file
PERF_RESULTS_FILE = '/root/ai_xyz/performance_metrics.json'


class PerformanceLevel(Enum):
    """Performance health levels."""
    OPTIMAL = "OPTIMAL"       # All metrics within target
    GOOD = "GOOD"             # Minor degradation
    DEGRADED = "DEGRADED"     # Noticeable slowdown
    CRITICAL = "CRITICAL"     # Severe performance issues


@dataclass
class LatencyMetric:
    """Represents a latency measurement."""
    operation: str
    latency_ms: float
    timestamp: datetime
    success: bool = True
    metadata: Dict = field(default_factory=dict)


@dataclass
class ResourceMetric:
    """Represents resource usage measurement."""
    cpu_percent: float
    memory_percent: float
    memory_mb: float
    timestamp: datetime
    active_threads: int = 0
    open_connections: int = 0


class PerformanceMonitor:
    """
    Real-time performance monitoring for AI-XYZ trading system.

    Monitors:
    - Trade execution latency
    - Alert processing latency
    - API call latency
    - Scanner cycle time
    - Resource utilization
    """

    # Latency targets (milliseconds)
    LATENCY_TARGETS = {
        'trade_execution': 100,      # Target: <100ms
        'alert_trigger': 50,         # Target: <50ms
        'api_call': 200,             # Target: <200ms
        'scanner_cycle': 35000,      # Target: <35 seconds
        'position_sync': 500,        # Target: <500ms
        'redis_operation': 10,       # Target: <10ms
        'database_query': 50,        # Target: <50ms
    }

    # Resource thresholds
    RESOURCE_THRESHOLDS = {
        'cpu_warning': 70,           # >70% CPU = warning
        'cpu_critical': 90,          # >90% CPU = critical
        'memory_warning': 75,        # >75% memory = warning
        'memory_critical': 90,       # >90% memory = critical
    }

    # Performance degradation thresholds
    DEGRADATION_THRESHOLDS = {
        'latency_warning': 1.5,      # 1.5x target = warning
        'latency_critical': 3.0,     # 3x target = critical
    }

    def __init__(self):
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = self._connect_redis()

        # Latency tracking
        self.latency_history: Dict[str, deque] = {}
        for op in self.LATENCY_TARGETS:
            self.latency_history[op] = deque(maxlen=1000)

        # Resource tracking
        self.resource_history: deque = deque(maxlen=500)

        # Performance alerts
        self.performance_alerts: List[Dict] = []

        # Monitoring state
        self.monitoring_active = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.monitor_interval = 5  # seconds

        # Bottleneck tracking
        self.bottlenecks: Dict[str, int] = {}  # operation -> count

        # Callbacks for performance alerts
        self.alert_callbacks: List[Callable] = []

    def _connect_redis(self) -> Optional[redis.Redis]:
        """Connect to Redis."""
        try:
            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=1,
                decode_responses=True
            )
            client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            return None

    def add_alert_callback(self, callback: Callable):
        """Add callback for performance alerts."""
        self.alert_callbacks.append(callback)

    # =========================================================================
    # LATENCY TRACKING
    # =========================================================================

    def record_latency(self, operation: str, latency_ms: float,
                      success: bool = True, metadata: Dict = None):
        """
        Record a latency measurement.

        Args:
            operation: Type of operation (trade_execution, api_call, etc.)
            latency_ms: Latency in milliseconds
            success: Whether operation succeeded
            metadata: Additional context
        """
        metric = LatencyMetric(
            operation=operation,
            latency_ms=latency_ms,
            timestamp=datetime.now(),
            success=success,
            metadata=metadata or {}
        )

        if operation not in self.latency_history:
            self.latency_history[operation] = deque(maxlen=1000)

        self.latency_history[operation].append(metric)

        # Check for performance degradation
        target = self.LATENCY_TARGETS.get(operation, 100)
        if latency_ms > target * self.DEGRADATION_THRESHOLDS['latency_critical']:
            self._record_bottleneck(operation)
            self._trigger_performance_alert(
                f"CRITICAL: {operation} latency {latency_ms:.0f}ms (target: {target}ms)",
                PerformanceLevel.CRITICAL
            )
        elif latency_ms > target * self.DEGRADATION_THRESHOLDS['latency_warning']:
            self._trigger_performance_alert(
                f"WARNING: {operation} latency {latency_ms:.0f}ms (target: {target}ms)",
                PerformanceLevel.DEGRADED
            )

        # Store in Redis for dashboard
        if self.redis_client:
            try:
                self.redis_client.lpush(
                    f'perf:latency:{operation}',
                    json.dumps({
                        'latency_ms': latency_ms,
                        'timestamp': metric.timestamp.isoformat(),
                        'success': success
                    })
                )
                self.redis_client.ltrim(f'perf:latency:{operation}', 0, 99)
            except Exception:
                pass

    def measure_latency(self, operation: str):
        """
        Context manager for measuring operation latency.

        Usage:
            with monitor.measure_latency('trade_execution'):
                execute_trade()
        """
        return LatencyContext(self, operation)

    def get_latency_stats(self, operation: str, window_minutes: int = 5) -> Dict:
        """
        Get latency statistics for an operation.

        Returns:
            Dict with avg, min, max, p95, p99, count
        """
        if operation not in self.latency_history:
            return {}

        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        recent = [
            m.latency_ms for m in self.latency_history[operation]
            if m.timestamp > cutoff
        ]

        if not recent:
            return {'count': 0}

        sorted_latencies = sorted(recent)
        p95_idx = int(len(sorted_latencies) * 0.95)
        p99_idx = int(len(sorted_latencies) * 0.99)

        target = self.LATENCY_TARGETS.get(operation, 100)
        avg_latency = statistics.mean(recent)

        return {
            'operation': operation,
            'count': len(recent),
            'avg_ms': avg_latency,
            'min_ms': min(recent),
            'max_ms': max(recent),
            'p95_ms': sorted_latencies[p95_idx] if p95_idx < len(sorted_latencies) else max(recent),
            'p99_ms': sorted_latencies[p99_idx] if p99_idx < len(sorted_latencies) else max(recent),
            'target_ms': target,
            'within_target_pct': sum(1 for l in recent if l <= target) / len(recent) * 100,
            'status': self._get_latency_status(avg_latency, target)
        }

    def _get_latency_status(self, avg_latency: float, target: float) -> str:
        """Get status based on average latency vs target."""
        ratio = avg_latency / target
        if ratio <= 1.0:
            return 'OPTIMAL'
        elif ratio <= 1.5:
            return 'GOOD'
        elif ratio <= 3.0:
            return 'DEGRADED'
        return 'CRITICAL'

    # =========================================================================
    # RESOURCE MONITORING
    # =========================================================================

    def record_resources(self) -> ResourceMetric:
        """Record current resource utilization."""
        process = psutil.Process()

        metric = ResourceMetric(
            cpu_percent=psutil.cpu_percent(interval=0.1),
            memory_percent=psutil.virtual_memory().percent,
            memory_mb=process.memory_info().rss / 1024 / 1024,
            timestamp=datetime.now(),
            active_threads=threading.active_count(),
            open_connections=len(process.connections()) if hasattr(process, 'connections') else 0
        )

        self.resource_history.append(metric)

        # Check thresholds
        if metric.cpu_percent > self.RESOURCE_THRESHOLDS['cpu_critical']:
            self._trigger_performance_alert(
                f"CRITICAL: CPU at {metric.cpu_percent:.1f}%",
                PerformanceLevel.CRITICAL
            )
        elif metric.cpu_percent > self.RESOURCE_THRESHOLDS['cpu_warning']:
            self._trigger_performance_alert(
                f"WARNING: CPU at {metric.cpu_percent:.1f}%",
                PerformanceLevel.DEGRADED
            )

        if metric.memory_percent > self.RESOURCE_THRESHOLDS['memory_critical']:
            self._trigger_performance_alert(
                f"CRITICAL: Memory at {metric.memory_percent:.1f}%",
                PerformanceLevel.CRITICAL
            )
        elif metric.memory_percent > self.RESOURCE_THRESHOLDS['memory_warning']:
            self._trigger_performance_alert(
                f"WARNING: Memory at {metric.memory_percent:.1f}%",
                PerformanceLevel.DEGRADED
            )

        # Store in Redis
        if self.redis_client:
            try:
                self.redis_client.set('perf:resources:current', json.dumps({
                    'cpu_percent': metric.cpu_percent,
                    'memory_percent': metric.memory_percent,
                    'memory_mb': metric.memory_mb,
                    'threads': metric.active_threads,
                    'timestamp': metric.timestamp.isoformat()
                }))
            except Exception:
                pass

        return metric

    def get_resource_stats(self, window_minutes: int = 5) -> Dict:
        """Get resource usage statistics."""
        cutoff = datetime.now() - timedelta(minutes=window_minutes)
        recent = [m for m in self.resource_history if m.timestamp > cutoff]

        if not recent:
            return {}

        cpu_values = [m.cpu_percent for m in recent]
        mem_values = [m.memory_percent for m in recent]

        return {
            'cpu': {
                'avg': statistics.mean(cpu_values),
                'max': max(cpu_values),
                'min': min(cpu_values),
                'current': cpu_values[-1] if cpu_values else 0
            },
            'memory': {
                'avg': statistics.mean(mem_values),
                'max': max(mem_values),
                'min': min(mem_values),
                'current': mem_values[-1] if mem_values else 0
            },
            'threads': recent[-1].active_threads if recent else 0,
            'sample_count': len(recent)
        }

    # =========================================================================
    # BOTTLENECK DETECTION
    # =========================================================================

    def _record_bottleneck(self, operation: str):
        """Record a bottleneck occurrence."""
        self.bottlenecks[operation] = self.bottlenecks.get(operation, 0) + 1

    def get_bottlenecks(self) -> List[Dict]:
        """Get identified bottlenecks sorted by frequency."""
        return sorted(
            [{'operation': op, 'count': count} for op, count in self.bottlenecks.items()],
            key=lambda x: x['count'],
            reverse=True
        )

    def analyze_bottlenecks(self) -> Dict:
        """
        Analyze system bottlenecks and provide recommendations.

        Returns:
            Dict with bottleneck analysis and recommendations
        """
        bottlenecks = self.get_bottlenecks()
        recommendations = []

        for bn in bottlenecks[:5]:
            op = bn['operation']
            count = bn['count']

            if op == 'api_call' and count > 10:
                recommendations.append({
                    'issue': f"API calls slow ({count} incidents)",
                    'recommendation': "Consider implementing request batching or caching"
                })
            elif op == 'trade_execution' and count > 5:
                recommendations.append({
                    'issue': f"Trade execution slow ({count} incidents)",
                    'recommendation': "Check exchange connectivity, consider pre-signed orders"
                })
            elif op == 'scanner_cycle' and count > 3:
                recommendations.append({
                    'issue': f"Scanner cycles slow ({count} incidents)",
                    'recommendation': "Reduce scan scope or parallelize symbol analysis"
                })
            elif op == 'redis_operation' and count > 10:
                recommendations.append({
                    'issue': f"Redis operations slow ({count} incidents)",
                    'recommendation': "Check Redis memory, consider connection pooling"
                })

        # Check resource-related bottlenecks
        resource_stats = self.get_resource_stats()
        if resource_stats.get('cpu', {}).get('avg', 0) > 80:
            recommendations.append({
                'issue': "High average CPU usage",
                'recommendation': "Profile code for CPU-intensive operations, consider async processing"
            })
        if resource_stats.get('memory', {}).get('avg', 0) > 80:
            recommendations.append({
                'issue': "High average memory usage",
                'recommendation': "Check for memory leaks, reduce cache sizes, optimize data structures"
            })

        return {
            'bottlenecks': bottlenecks,
            'recommendations': recommendations,
            'analysis_time': datetime.now().isoformat()
        }

    # =========================================================================
    # PERFORMANCE ALERTS
    # =========================================================================

    def _trigger_performance_alert(self, message: str, level: PerformanceLevel):
        """Trigger a performance alert."""
        alert = {
            'message': message,
            'level': level.value,
            'timestamp': datetime.now().isoformat()
        }

        self.performance_alerts.append(alert)
        if len(self.performance_alerts) > 100:
            self.performance_alerts = self.performance_alerts[-50:]

        logger.warning(f"[PERF] {message}")

        # Call registered callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Performance alert callback failed: {e}")

    # =========================================================================
    # BACKGROUND MONITORING
    # =========================================================================

    def start_monitoring(self, interval: int = 5):
        """Start background resource monitoring."""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitor_interval = interval
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        logger.info(f"Performance monitoring started (interval: {interval}s)")

    def stop_monitoring(self):
        """Stop background resource monitoring."""
        self.monitoring_active = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("Performance monitoring stopped")

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.monitoring_active:
            try:
                self.record_resources()
            except Exception as e:
                logger.error(f"Resource monitoring error: {e}")
            time.sleep(self.monitor_interval)

    # =========================================================================
    # REPORTING
    # =========================================================================

    def get_performance_summary(self) -> Dict:
        """Get comprehensive performance summary."""
        summary = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': self._calculate_overall_status(),
            'latency': {},
            'resources': self.get_resource_stats(),
            'bottlenecks': self.get_bottlenecks()[:5],
            'recent_alerts': self.performance_alerts[-10:]
        }

        # Add latency stats for each operation
        for operation in self.LATENCY_TARGETS:
            stats = self.get_latency_stats(operation)
            if stats.get('count', 0) > 0:
                summary['latency'][operation] = stats

        return summary

    def _calculate_overall_status(self) -> str:
        """Calculate overall system performance status."""
        issues = 0
        critical = 0

        # Check latency
        for operation in self.LATENCY_TARGETS:
            stats = self.get_latency_stats(operation)
            if stats.get('status') == 'CRITICAL':
                critical += 1
            elif stats.get('status') == 'DEGRADED':
                issues += 1

        # Check resources
        resource_stats = self.get_resource_stats()
        if resource_stats.get('cpu', {}).get('avg', 0) > 90:
            critical += 1
        elif resource_stats.get('cpu', {}).get('avg', 0) > 70:
            issues += 1

        if critical > 0:
            return 'CRITICAL'
        elif issues > 2:
            return 'DEGRADED'
        elif issues > 0:
            return 'GOOD'
        return 'OPTIMAL'

    def save_metrics(self):
        """Save current metrics to file."""
        try:
            summary = self.get_performance_summary()
            with open(PERF_RESULTS_FILE, 'w') as f:
                json.dump(summary, f, indent=2, default=str)
            logger.info(f"Performance metrics saved to {PERF_RESULTS_FILE}")
        except Exception as e:
            logger.error(f"Failed to save performance metrics: {e}")

    def print_report(self):
        """Print performance report to console."""
        print("\n" + "=" * 70)
        print("PERFORMANCE MONITORING REPORT")
        print("=" * 70)
        print(f"Report Time: {datetime.now().isoformat()}")

        summary = self.get_performance_summary()
        print(f"\nOverall Status: {summary['overall_status']}")

        # Latency report
        print("\n" + "-" * 50)
        print("LATENCY METRICS")
        print("-" * 50)
        print(f"{'Operation':<20} {'Avg':>10} {'P95':>10} {'Target':>10} {'Status':>10}")
        print("-" * 60)

        for op, stats in summary['latency'].items():
            if stats.get('count', 0) > 0:
                print(f"{op:<20} {stats['avg_ms']:>8.1f}ms {stats['p95_ms']:>8.1f}ms "
                      f"{stats['target_ms']:>8}ms {stats['status']:>10}")

        # Resource report
        print("\n" + "-" * 50)
        print("RESOURCE UTILIZATION")
        print("-" * 50)
        resources = summary.get('resources', {})
        if resources:
            cpu = resources.get('cpu', {})
            mem = resources.get('memory', {})
            print(f"  CPU:    Current: {cpu.get('current', 0):.1f}%  Avg: {cpu.get('avg', 0):.1f}%  Max: {cpu.get('max', 0):.1f}%")
            print(f"  Memory: Current: {mem.get('current', 0):.1f}%  Avg: {mem.get('avg', 0):.1f}%  Max: {mem.get('max', 0):.1f}%")
            print(f"  Threads: {resources.get('threads', 0)}")

        # Bottlenecks
        if summary['bottlenecks']:
            print("\n" + "-" * 50)
            print("BOTTLENECKS DETECTED")
            print("-" * 50)
            for bn in summary['bottlenecks']:
                print(f"  {bn['operation']}: {bn['count']} incidents")

        # Recent alerts
        if summary['recent_alerts']:
            print("\n" + "-" * 50)
            print("RECENT PERFORMANCE ALERTS")
            print("-" * 50)
            for alert in summary['recent_alerts'][-5:]:
                print(f"  [{alert['level']}] {alert['message']}")

        print("\n" + "=" * 70)


class LatencyContext:
    """Context manager for measuring latency."""

    def __init__(self, monitor: PerformanceMonitor, operation: str):
        self.monitor = monitor
        self.operation = operation
        self.start_time = None
        self.success = True
        self.metadata = {}

    def __enter__(self):
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        elapsed_ms = (time.perf_counter() - self.start_time) * 1000
        self.success = exc_type is None
        self.monitor.record_latency(
            self.operation,
            elapsed_ms,
            success=self.success,
            metadata=self.metadata
        )
        return False  # Don't suppress exceptions

    def set_metadata(self, **kwargs):
        """Set additional metadata for this measurement."""
        self.metadata.update(kwargs)


# Singleton instance
_performance_monitor_instance = None

def get_performance_monitor() -> PerformanceMonitor:
    """Get or create the singleton PerformanceMonitor instance."""
    global _performance_monitor_instance
    if _performance_monitor_instance is None:
        _performance_monitor_instance = PerformanceMonitor()
    return _performance_monitor_instance


if __name__ == "__main__":
    print("=" * 60)
    print("PERFORMANCE MONITOR TEST")
    print("=" * 60)

    monitor = PerformanceMonitor()

    # Start background monitoring
    monitor.start_monitoring(interval=2)

    # Simulate some latency measurements
    print("\nSimulating latency measurements...")

    import random

    # Simulate trade executions
    for i in range(20):
        latency = random.gauss(80, 30)  # Target: 100ms
        monitor.record_latency('trade_execution', max(10, latency))

    # Simulate API calls
    for i in range(30):
        latency = random.gauss(150, 50)  # Target: 200ms
        monitor.record_latency('api_call', max(20, latency))

    # Simulate some slow operations (bottlenecks)
    for i in range(5):
        monitor.record_latency('trade_execution', 350)  # >3x target = critical

    # Simulate alert triggers
    for i in range(15):
        latency = random.gauss(40, 15)  # Target: 50ms
        monitor.record_latency('alert_trigger', max(5, latency))

    # Simulate Redis operations
    for i in range(50):
        latency = random.gauss(5, 2)  # Target: 10ms
        monitor.record_latency('redis_operation', max(1, latency))

    # Wait for resource monitoring
    print("Collecting resource metrics...")
    time.sleep(5)

    # Print report
    monitor.print_report()

    # Analyze bottlenecks
    print("\n" + "-" * 50)
    print("BOTTLENECK ANALYSIS")
    print("-" * 50)
    analysis = monitor.analyze_bottlenecks()
    for rec in analysis['recommendations']:
        print(f"  Issue: {rec['issue']}")
        print(f"  Recommendation: {rec['recommendation']}")
        print()

    # Stop monitoring
    monitor.stop_monitoring()

    # Save metrics
    monitor.save_metrics()

    print("\nPerformance Monitor test completed!")
