#!/usr/bin/env python3
"""
Grok Recommendation #14: Graceful Degradation
Fallback modes for component failures.
"""
import json
import os
import time
import threading
from typing import Any, Callable, Dict, Optional, TypeVar, Generic
from dataclasses import dataclass
from enum import Enum
from functools import wraps
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

T = TypeVar('T')


class DegradationLevel(Enum):
    """System degradation levels"""
    NORMAL = "normal"           # All systems operational
    DEGRADED = "degraded"       # Some features disabled
    MINIMAL = "minimal"         # Only essential features
    EMERGENCY = "emergency"     # Critical path only


@dataclass
class ComponentStatus:
    """Status of a system component"""
    name: str
    healthy: bool
    last_check: float
    failure_count: int
    last_error: Optional[str]
    degradation_level: DegradationLevel


class CircuitBreaker:
    """
    Circuit breaker pattern for component protection.

    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Failures exceeded threshold, requests blocked
    - HALF_OPEN: Testing if service recovered
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_requests: int = 3
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_requests = half_open_requests

        self.failures = 0
        self.successes = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
        self._lock = threading.Lock()

    def can_execute(self) -> bool:
        """Check if request can proceed"""
        with self._lock:
            if self.state == "CLOSED":
                return True

            if self.state == "OPEN":
                # Check if recovery timeout has passed
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = "HALF_OPEN"
                    self.successes = 0
                    logger.info("Circuit breaker: OPEN -> HALF_OPEN")
                    return True
                return False

            if self.state == "HALF_OPEN":
                return True

            return False

    def record_success(self):
        """Record successful execution"""
        with self._lock:
            if self.state == "HALF_OPEN":
                self.successes += 1
                if self.successes >= self.half_open_requests:
                    self.state = "CLOSED"
                    self.failures = 0
                    logger.info("Circuit breaker: HALF_OPEN -> CLOSED (recovered)")
            else:
                self.failures = max(0, self.failures - 1)

    def record_failure(self):
        """Record failed execution"""
        with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()

            if self.state == "HALF_OPEN":
                self.state = "OPEN"
                logger.warning("Circuit breaker: HALF_OPEN -> OPEN (failed recovery)")
            elif self.failures >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"Circuit breaker: CLOSED -> OPEN (failures: {self.failures})")


class GracefulDegradation:
    """
    Graceful degradation manager for system resilience.

    Features:
    - Component health tracking
    - Automatic fallback execution
    - Circuit breaker protection
    - Degradation level management
    """

    def __init__(self, state_file: str = '/app/degradation_state.json'):
        self.state_file = state_file
        self.components: Dict[str, ComponentStatus] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.fallbacks: Dict[str, Callable] = {}
        self.current_level = DegradationLevel.NORMAL

        self._lock = threading.Lock()
        self._load_state()

    def _load_state(self):
        """Load saved state"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    level_name = data.get('current_level', 'normal')
                    self.current_level = DegradationLevel(level_name)
        except Exception as e:
            logger.warning(f"Could not load degradation state: {e}")

    def _save_state(self):
        """Save state"""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'current_level': self.current_level.value,
                'components': {
                    name: {
                        'healthy': status.healthy,
                        'failure_count': status.failure_count,
                        'degradation_level': status.degradation_level.value
                    }
                    for name, status in self.components.items()
                }
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save degradation state: {e}")

    def register_component(
        self,
        name: str,
        fallback: Callable = None,
        failure_threshold: int = 5
    ):
        """Register a component for monitoring"""
        with self._lock:
            self.components[name] = ComponentStatus(
                name=name,
                healthy=True,
                last_check=time.time(),
                failure_count=0,
                last_error=None,
                degradation_level=DegradationLevel.NORMAL
            )

            self.circuit_breakers[name] = CircuitBreaker(
                failure_threshold=failure_threshold
            )

            if fallback:
                self.fallbacks[name] = fallback

            logger.info(f"Registered component: {name}")

    def execute_with_fallback(
        self,
        component_name: str,
        primary_fn: Callable[[], T],
        fallback_fn: Callable[[], T] = None
    ) -> T:
        """
        Execute function with fallback on failure.

        Args:
            component_name: Name of the component
            primary_fn: Primary function to execute
            fallback_fn: Fallback function (optional, uses registered fallback)

        Returns:
            Result from primary or fallback function
        """
        # Get or create circuit breaker
        if component_name not in self.circuit_breakers:
            self.register_component(component_name)

        breaker = self.circuit_breakers[component_name]
        fallback = fallback_fn or self.fallbacks.get(component_name)

        # Check circuit breaker
        if not breaker.can_execute():
            logger.warning(f"Circuit breaker OPEN for {component_name}, using fallback")
            if fallback:
                return fallback()
            raise RuntimeError(f"Component {component_name} unavailable and no fallback")

        # Try primary
        try:
            result = primary_fn()
            breaker.record_success()
            self._mark_healthy(component_name)
            return result

        except Exception as e:
            breaker.record_failure()
            self._mark_unhealthy(component_name, str(e))

            logger.warning(f"Primary failed for {component_name}: {e}, using fallback")

            if fallback:
                try:
                    return fallback()
                except Exception as fallback_error:
                    logger.error(f"Fallback also failed: {fallback_error}")
                    raise

            raise

    def _mark_healthy(self, component_name: str):
        """Mark component as healthy"""
        with self._lock:
            if component_name in self.components:
                status = self.components[component_name]
                status.healthy = True
                status.last_check = time.time()
                status.failure_count = max(0, status.failure_count - 1)
                status.degradation_level = DegradationLevel.NORMAL

        self._update_system_level()

    def _mark_unhealthy(self, component_name: str, error: str):
        """Mark component as unhealthy"""
        with self._lock:
            if component_name in self.components:
                status = self.components[component_name]
                status.healthy = False
                status.last_check = time.time()
                status.failure_count += 1
                status.last_error = error

                # Escalate degradation level based on failures
                if status.failure_count >= 10:
                    status.degradation_level = DegradationLevel.EMERGENCY
                elif status.failure_count >= 5:
                    status.degradation_level = DegradationLevel.MINIMAL
                elif status.failure_count >= 2:
                    status.degradation_level = DegradationLevel.DEGRADED

        self._update_system_level()
        self._save_state()

    def _update_system_level(self):
        """Update overall system degradation level"""
        with self._lock:
            if not self.components:
                return

            # System level is worst component level
            worst_level = DegradationLevel.NORMAL

            unhealthy_count = 0
            for status in self.components.values():
                if not status.healthy:
                    unhealthy_count += 1

                if status.degradation_level.value > worst_level.value:
                    worst_level = status.degradation_level

            # Additional escalation based on unhealthy count
            unhealthy_ratio = unhealthy_count / len(self.components)
            if unhealthy_ratio > 0.5:
                worst_level = max(worst_level, DegradationLevel.MINIMAL, key=lambda x: x.value)
            elif unhealthy_ratio > 0.25:
                worst_level = max(worst_level, DegradationLevel.DEGRADED, key=lambda x: x.value)

            if worst_level != self.current_level:
                logger.warning(f"System degradation level: {self.current_level.value} -> {worst_level.value}")
                self.current_level = worst_level

    def is_feature_available(self, feature_name: str) -> bool:
        """
        Check if a feature should be available at current degradation level.

        Features are categorized:
        - NORMAL: All features
        - DEGRADED: Core trading features only
        - MINIMAL: Position monitoring only
        - EMERGENCY: Close positions only
        """
        feature_levels = {
            # Always available
            'position_monitoring': DegradationLevel.EMERGENCY,
            'stop_loss': DegradationLevel.EMERGENCY,
            'close_position': DegradationLevel.EMERGENCY,

            # Available in minimal mode
            'averaging': DegradationLevel.MINIMAL,
            'surplus_dump': DegradationLevel.MINIMAL,

            # Available in degraded mode
            'new_positions': DegradationLevel.DEGRADED,
            'ai_analysis': DegradationLevel.DEGRADED,

            # Only in normal mode
            'advanced_analytics': DegradationLevel.NORMAL,
            'backtesting': DegradationLevel.NORMAL,
            'optimization': DegradationLevel.NORMAL,
        }

        required_level = feature_levels.get(feature_name, DegradationLevel.NORMAL)

        # Feature available if current level is at or below required level
        level_order = [DegradationLevel.NORMAL, DegradationLevel.DEGRADED,
                       DegradationLevel.MINIMAL, DegradationLevel.EMERGENCY]

        current_idx = level_order.index(self.current_level)
        required_idx = level_order.index(required_level)

        return current_idx <= required_idx

    def get_status(self) -> Dict:
        """Get overall system status"""
        with self._lock:
            healthy_count = sum(1 for s in self.components.values() if s.healthy)
            total_count = len(self.components)

            return {
                'degradation_level': self.current_level.value,
                'healthy_components': healthy_count,
                'total_components': total_count,
                'health_percentage': (healthy_count / total_count * 100) if total_count > 0 else 100,
                'components': {
                    name: {
                        'healthy': status.healthy,
                        'failures': status.failure_count,
                        'level': status.degradation_level.value,
                        'last_error': status.last_error
                    }
                    for name, status in self.components.items()
                }
            }

    def reset_component(self, component_name: str):
        """Reset component health status"""
        with self._lock:
            if component_name in self.components:
                self.components[component_name].healthy = True
                self.components[component_name].failure_count = 0
                self.components[component_name].last_error = None
                self.components[component_name].degradation_level = DegradationLevel.NORMAL

            if component_name in self.circuit_breakers:
                breaker = self.circuit_breakers[component_name]
                breaker.state = "CLOSED"
                breaker.failures = 0

        self._update_system_level()
        logger.info(f"Reset component: {component_name}")

    def print_status(self):
        """Print system status"""
        status = self.get_status()

        print("\n" + "=" * 60)
        print("🛡️ GRACEFUL DEGRADATION STATUS")
        print("=" * 60)

        level_emoji = {
            'normal': '🟢',
            'degraded': '🟡',
            'minimal': '🟠',
            'emergency': '🔴'
        }
        emoji = level_emoji.get(status['degradation_level'], '⚪')

        print(f"\nSystem Level: {emoji} {status['degradation_level'].upper()}")
        print(f"Health: {status['health_percentage']:.0f}% ({status['healthy_components']}/{status['total_components']})")

        if status['components']:
            print("\nComponents:")
            for name, info in status['components'].items():
                health_icon = "✅" if info['healthy'] else "❌"
                print(f"  {health_icon} {name}: {info['level']} (failures: {info['failures']})")
                if info['last_error']:
                    print(f"     └─ Last error: {info['last_error'][:50]}...")

        print("\nFeature Availability:")
        features = ['position_monitoring', 'averaging', 'new_positions', 'ai_analysis', 'backtesting']
        for feature in features:
            available = self.is_feature_available(feature)
            icon = "✅" if available else "❌"
            print(f"  {icon} {feature}")

        print("=" * 60)


# Decorator for graceful degradation
def with_fallback(component_name: str, fallback_value: Any = None):
    """
    Decorator for graceful degradation.

    Usage:
        @with_fallback('redis', fallback_value={})
        def get_cache():
            return redis.get('key')
    """
    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args, **kwargs):
            degradation = get_graceful_degradation()

            def primary():
                return fn(*args, **kwargs)

            def fallback():
                if callable(fallback_value):
                    return fallback_value()
                return fallback_value

            return degradation.execute_with_fallback(component_name, primary, fallback)

        return wrapper
    return decorator


# Singleton
_degradation: Optional[GracefulDegradation] = None

def get_graceful_degradation() -> GracefulDegradation:
    """Get singleton graceful degradation manager"""
    global _degradation
    if _degradation is None:
        _degradation = GracefulDegradation()
    return _degradation


if __name__ == "__main__":
    # Demo
    print("=" * 60)
    print("GRACEFUL DEGRADATION DEMO")
    print("=" * 60)

    degradation = GracefulDegradation('/tmp/degradation_test.json')

    # Register components
    degradation.register_component('redis', fallback=lambda: {}, failure_threshold=3)
    degradation.register_component('exchange_api', failure_threshold=5)
    degradation.register_component('database', fallback=lambda: [], failure_threshold=3)

    # Simulate successful operations
    print("\nSimulating successful operations...")
    for i in range(5):
        result = degradation.execute_with_fallback(
            'redis',
            lambda: {'key': 'value'},
            lambda: {}
        )
        print(f"  Redis call {i+1}: {result}")

    # Simulate failures
    print("\nSimulating failures...")

    def failing_function():
        raise ConnectionError("Connection refused")

    for i in range(5):
        try:
            result = degradation.execute_with_fallback(
                'exchange_api',
                failing_function,
                lambda: {'fallback': True}
            )
            print(f"  Exchange call {i+1}: {result}")
        except Exception as e:
            print(f"  Exchange call {i+1}: Error - {e}")

    # Test decorator
    print("\nTesting decorator...")

    @with_fallback('database', fallback_value=[])
    def get_positions():
        raise Exception("Database error")

    positions = get_positions()
    print(f"  Positions (fallback): {positions}")

    # Print status
    degradation.print_status()

    # Test feature availability
    print("\nFeature availability at current level:")
    for feature in ['stop_loss', 'averaging', 'new_positions', 'backtesting']:
        available = degradation.is_feature_available(feature)
        print(f"  {feature}: {'Available' if available else 'Disabled'}")
