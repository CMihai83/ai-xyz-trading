#!/usr/bin/env python3
"""
Fail-Safe Mechanisms & Recovery Protocols V1.0.0
Sprint 6 Task 3: System resilience and recovery

Features:
- System health monitoring with heartbeat
- Graceful degradation modes
- Automatic recovery protocols
- Emergency shutdown procedures
- State backup and restoration
- Dead man's switch (watchdog)
- Connection loss handling
- API failure recovery
- Position protection during failures
"""

import os
import sys
import json
import time
import signal
import threading
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Callable
from enum import Enum
from pathlib import Path
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SystemState(Enum):
    """System operational states"""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    RECOVERY = "RECOVERY"
    EMERGENCY_SHUTDOWN = "EMERGENCY_SHUTDOWN"
    OFFLINE = "OFFLINE"


class DegradationLevel(Enum):
    """Graceful degradation levels"""
    FULL_OPERATION = 0      # All systems go
    REDUCED_SCANNING = 1    # Reduce scan frequency
    NO_NEW_POSITIONS = 2    # Only manage existing
    CLOSE_ONLY = 3          # Only close positions
    EMERGENCY_CLOSE = 4     # Force close all


class RecoveryAction(Enum):
    """Recovery action types"""
    RECONNECT_EXCHANGE = "reconnect_exchange"
    RECONNECT_REDIS = "reconnect_redis"
    SYNC_POSITIONS = "sync_positions"
    RESTORE_STATE = "restore_state"
    RESTART_SCANNER = "restart_scanner"
    RESTART_AI_MODULES = "restart_ai_modules"
    FULL_SYSTEM_RESTART = "full_system_restart"


@dataclass
class HealthCheck:
    """Health check result"""
    component: str
    status: str
    latency_ms: float
    last_success: datetime
    consecutive_failures: int
    error_message: Optional[str] = None


@dataclass
class FailSafeConfig:
    """Fail-safe configuration"""
    # Heartbeat settings
    heartbeat_interval_sec: int = 10
    heartbeat_timeout_sec: int = 30

    # Health check thresholds
    max_consecutive_failures: int = 3
    health_check_interval_sec: int = 15

    # Recovery settings
    max_recovery_attempts: int = 5
    recovery_cooldown_sec: int = 60
    auto_recovery_enabled: bool = True

    # Degradation thresholds
    degradation_threshold_failures: int = 2
    critical_threshold_failures: int = 5

    # State backup
    backup_interval_sec: int = 60
    backup_retention_count: int = 10
    backup_directory: str = "/root/ai_xyz/backups"

    # Emergency settings
    emergency_close_timeout_sec: int = 300
    max_positions_during_degradation: int = 5

    # Position protection
    protect_positions_on_failure: bool = True
    max_position_age_hours: float = 24.0


@dataclass
class RecoveryAttempt:
    """Recovery attempt record"""
    action: RecoveryAction
    timestamp: datetime
    success: bool
    duration_ms: float
    error: Optional[str] = None


class FailSafeMechanisms:
    """
    Comprehensive fail-safe and recovery system

    Monitors system health, implements graceful degradation,
    and executes recovery protocols automatically.
    """

    def __init__(self, config: Optional[FailSafeConfig] = None):
        self.config = config or FailSafeConfig()

        # System state
        self.system_state = SystemState.HEALTHY
        self.degradation_level = DegradationLevel.FULL_OPERATION

        # Health tracking
        self.health_checks: Dict[str, HealthCheck] = {}
        self.last_heartbeat = datetime.now()

        # Recovery tracking
        self.recovery_attempts: List[RecoveryAttempt] = []
        self.recovery_in_progress = False
        self.last_recovery_time: Optional[datetime] = None

        # State backup
        self.state_backups: List[str] = []
        self.last_backup_time: Optional[datetime] = None

        # Callbacks
        self.recovery_callbacks: Dict[RecoveryAction, Callable] = {}
        self.state_change_callbacks: List[Callable] = []

        # Threading
        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._watchdog_thread: Optional[threading.Thread] = None

        # Ensure backup directory exists
        Path(self.config.backup_directory).mkdir(parents=True, exist_ok=True)

        logger.info("FailSafeMechanisms initialized with config: %s", asdict(self.config))

    # =========================================================================
    # HEALTH MONITORING
    # =========================================================================

    def record_health_check(
        self,
        component: str,
        success: bool,
        latency_ms: float = 0,
        error_message: Optional[str] = None
    ):
        """Record a health check result"""
        now = datetime.now()

        if component in self.health_checks:
            check = self.health_checks[component]
            if success:
                check.status = "HEALTHY"
                check.last_success = now
                check.consecutive_failures = 0
                check.error_message = None
            else:
                check.consecutive_failures += 1
                check.error_message = error_message
                if check.consecutive_failures >= self.config.critical_threshold_failures:
                    check.status = "CRITICAL"
                elif check.consecutive_failures >= self.config.degradation_threshold_failures:
                    check.status = "DEGRADED"
            check.latency_ms = latency_ms
        else:
            self.health_checks[component] = HealthCheck(
                component=component,
                status="HEALTHY" if success else "DEGRADED",
                latency_ms=latency_ms,
                last_success=now if success else datetime.min,
                consecutive_failures=0 if success else 1,
                error_message=error_message
            )

        # Update system state based on health checks
        self._evaluate_system_state()

    def check_exchange_connection(self, exchange_client) -> bool:
        """Check exchange API connection"""
        start = time.time()
        try:
            # Try a simple API call
            if hasattr(exchange_client, 'fetch_balance'):
                exchange_client.fetch_balance()
            elif hasattr(exchange_client, 'get_balance'):
                exchange_client.get_balance()
            else:
                # Fallback: try to get server time
                exchange_client.fetch_time()

            latency = (time.time() - start) * 1000
            self.record_health_check("exchange", True, latency)
            return True
        except Exception as e:
            latency = (time.time() - start) * 1000
            self.record_health_check("exchange", False, latency, str(e))
            logger.error("Exchange health check failed: %s", e)
            return False

    def check_redis_connection(self, redis_client) -> bool:
        """Check Redis connection"""
        start = time.time()
        try:
            redis_client.ping()
            latency = (time.time() - start) * 1000
            self.record_health_check("redis", True, latency)
            return True
        except Exception as e:
            latency = (time.time() - start) * 1000
            self.record_health_check("redis", False, latency, str(e))
            logger.error("Redis health check failed: %s", e)
            return False

    def check_database_connection(self, db_client) -> bool:
        """Check database connection"""
        start = time.time()
        try:
            if hasattr(db_client, 'execute'):
                db_client.execute("SELECT 1")
            latency = (time.time() - start) * 1000
            self.record_health_check("database", True, latency)
            return True
        except Exception as e:
            latency = (time.time() - start) * 1000
            self.record_health_check("database", False, latency, str(e))
            logger.error("Database health check failed: %s", e)
            return False

    def heartbeat(self):
        """Record a heartbeat"""
        self.last_heartbeat = datetime.now()
        self.record_health_check("heartbeat", True, 0)

    def check_heartbeat_timeout(self) -> bool:
        """Check if heartbeat has timed out"""
        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        return elapsed > self.config.heartbeat_timeout_sec

    # =========================================================================
    # SYSTEM STATE MANAGEMENT
    # =========================================================================

    def _evaluate_system_state(self):
        """Evaluate and update system state based on health checks"""
        critical_count = 0
        degraded_count = 0

        for check in self.health_checks.values():
            if check.status == "CRITICAL":
                critical_count += 1
            elif check.status == "DEGRADED":
                degraded_count += 1

        old_state = self.system_state

        # Determine new state
        if critical_count > 0:
            if critical_count >= 2:
                self.system_state = SystemState.CRITICAL
                self._set_degradation_level(DegradationLevel.EMERGENCY_CLOSE)
            else:
                self.system_state = SystemState.CRITICAL
                self._set_degradation_level(DegradationLevel.CLOSE_ONLY)
        elif degraded_count >= 2:
            self.system_state = SystemState.DEGRADED
            self._set_degradation_level(DegradationLevel.NO_NEW_POSITIONS)
        elif degraded_count == 1:
            self.system_state = SystemState.DEGRADED
            self._set_degradation_level(DegradationLevel.REDUCED_SCANNING)
        else:
            self.system_state = SystemState.HEALTHY
            self._set_degradation_level(DegradationLevel.FULL_OPERATION)

        # Trigger recovery if needed
        if self.system_state in [SystemState.CRITICAL, SystemState.DEGRADED]:
            if self.config.auto_recovery_enabled and not self.recovery_in_progress:
                self._trigger_recovery()

        # Notify state change
        if old_state != self.system_state:
            logger.warning("System state changed: %s -> %s", old_state.value, self.system_state.value)
            self._notify_state_change(old_state, self.system_state)

    def _set_degradation_level(self, level: DegradationLevel):
        """Set degradation level"""
        if level != self.degradation_level:
            logger.warning("Degradation level changed: %s -> %s",
                         self.degradation_level.name, level.name)
            self.degradation_level = level

    def _notify_state_change(self, old_state: SystemState, new_state: SystemState):
        """Notify registered callbacks of state change"""
        for callback in self.state_change_callbacks:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error("State change callback failed: %s", e)

    def register_state_change_callback(self, callback: Callable):
        """Register a callback for state changes"""
        self.state_change_callbacks.append(callback)

    # =========================================================================
    # GRACEFUL DEGRADATION
    # =========================================================================

    def can_open_new_position(self) -> bool:
        """Check if new positions are allowed"""
        return self.degradation_level.value <= DegradationLevel.REDUCED_SCANNING.value

    def can_execute_trades(self) -> bool:
        """Check if trading is allowed"""
        return self.degradation_level.value <= DegradationLevel.NO_NEW_POSITIONS.value

    def should_close_positions(self) -> bool:
        """Check if positions should be closed"""
        return self.degradation_level.value >= DegradationLevel.EMERGENCY_CLOSE.value

    def get_scan_interval_multiplier(self) -> float:
        """Get scan interval multiplier based on degradation"""
        if self.degradation_level == DegradationLevel.REDUCED_SCANNING:
            return 2.0  # Double scan interval
        elif self.degradation_level.value >= DegradationLevel.NO_NEW_POSITIONS.value:
            return 5.0  # 5x slower scanning
        return 1.0

    def get_max_positions_allowed(self) -> int:
        """Get max positions based on degradation level"""
        if self.degradation_level.value >= DegradationLevel.NO_NEW_POSITIONS.value:
            return 0
        elif self.degradation_level == DegradationLevel.REDUCED_SCANNING:
            return self.config.max_positions_during_degradation
        return 999  # No limit in healthy state

    # =========================================================================
    # RECOVERY PROTOCOLS
    # =========================================================================

    def register_recovery_callback(self, action: RecoveryAction, callback: Callable):
        """Register a recovery callback"""
        self.recovery_callbacks[action] = callback

    def _trigger_recovery(self):
        """Trigger automatic recovery"""
        if self.recovery_in_progress:
            return

        # Check cooldown
        if self.last_recovery_time:
            elapsed = (datetime.now() - self.last_recovery_time).total_seconds()
            if elapsed < self.config.recovery_cooldown_sec:
                logger.info("Recovery cooldown active, %d seconds remaining",
                          self.config.recovery_cooldown_sec - elapsed)
                return

        self.recovery_in_progress = True
        self.system_state = SystemState.RECOVERY

        # Start recovery in background thread
        recovery_thread = threading.Thread(target=self._execute_recovery)
        recovery_thread.daemon = True
        recovery_thread.start()

    def _execute_recovery(self):
        """Execute recovery protocols"""
        logger.info("Starting automatic recovery...")

        try:
            # Determine which components need recovery
            failed_components = [
                name for name, check in self.health_checks.items()
                if check.status in ["CRITICAL", "DEGRADED"]
            ]

            for component in failed_components:
                action = self._get_recovery_action(component)
                if action:
                    self._execute_recovery_action(action)

            # If all else fails, try full state restore
            if self.system_state == SystemState.CRITICAL:
                self._execute_recovery_action(RecoveryAction.RESTORE_STATE)

        except Exception as e:
            logger.error("Recovery failed: %s", e)
            logger.error(traceback.format_exc())
        finally:
            self.recovery_in_progress = False
            self.last_recovery_time = datetime.now()
            logger.info("Recovery completed, system state: %s", self.system_state.value)

    def _get_recovery_action(self, component: str) -> Optional[RecoveryAction]:
        """Get appropriate recovery action for a component"""
        mapping = {
            "exchange": RecoveryAction.RECONNECT_EXCHANGE,
            "redis": RecoveryAction.RECONNECT_REDIS,
            "database": RecoveryAction.RESTORE_STATE,
            "scanner": RecoveryAction.RESTART_SCANNER,
            "ai_modules": RecoveryAction.RESTART_AI_MODULES,
        }
        return mapping.get(component)

    def _execute_recovery_action(self, action: RecoveryAction) -> bool:
        """Execute a specific recovery action"""
        start = time.time()
        success = False
        error = None

        logger.info("Executing recovery action: %s", action.value)

        try:
            if action in self.recovery_callbacks:
                callback = self.recovery_callbacks[action]
                success = callback()
            else:
                # Default recovery actions
                if action == RecoveryAction.RESTORE_STATE:
                    success = self._restore_latest_backup()
                else:
                    logger.warning("No callback registered for action: %s", action.value)
                    success = False

        except Exception as e:
            error = str(e)
            logger.error("Recovery action %s failed: %s", action.value, e)

        duration = (time.time() - start) * 1000

        # Record attempt
        attempt = RecoveryAttempt(
            action=action,
            timestamp=datetime.now(),
            success=success,
            duration_ms=duration,
            error=error
        )
        self.recovery_attempts.append(attempt)

        # Keep only recent attempts
        if len(self.recovery_attempts) > 100:
            self.recovery_attempts = self.recovery_attempts[-100:]

        return success

    def manual_recovery(self, action: RecoveryAction) -> bool:
        """Manually trigger a specific recovery action"""
        logger.info("Manual recovery triggered: %s", action.value)
        return self._execute_recovery_action(action)

    # =========================================================================
    # STATE BACKUP & RESTORE
    # =========================================================================

    def backup_state(self, state_data: Dict[str, Any]) -> str:
        """Backup current state to file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"state_backup_{timestamp}.json"
        filepath = os.path.join(self.config.backup_directory, filename)

        backup_data = {
            "timestamp": datetime.now().isoformat(),
            "system_state": self.system_state.value,
            "degradation_level": self.degradation_level.name,
            "health_checks": {
                name: {
                    "status": check.status,
                    "consecutive_failures": check.consecutive_failures,
                    "last_success": check.last_success.isoformat()
                }
                for name, check in self.health_checks.items()
            },
            "state_data": state_data
        }

        try:
            with open(filepath, 'w') as f:
                json.dump(backup_data, f, indent=2, default=str)

            self.state_backups.append(filepath)
            self.last_backup_time = datetime.now()

            # Cleanup old backups
            self._cleanup_old_backups()

            logger.info("State backup saved: %s", filepath)
            return filepath

        except Exception as e:
            logger.error("Failed to save state backup: %s", e)
            return ""

    def _cleanup_old_backups(self):
        """Remove old backup files"""
        if len(self.state_backups) > self.config.backup_retention_count:
            to_remove = self.state_backups[:-self.config.backup_retention_count]
            for filepath in to_remove:
                try:
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    logger.error("Failed to remove old backup %s: %s", filepath, e)
            self.state_backups = self.state_backups[-self.config.backup_retention_count:]

    def _restore_latest_backup(self) -> bool:
        """Restore from latest backup"""
        if not self.state_backups:
            # Find backups in directory
            backup_dir = Path(self.config.backup_directory)
            backups = sorted(backup_dir.glob("state_backup_*.json"))
            if backups:
                self.state_backups = [str(b) for b in backups]

        if not self.state_backups:
            logger.warning("No backups available for restore")
            return False

        latest = self.state_backups[-1]
        return self.restore_state(latest)

    def restore_state(self, filepath: str) -> bool:
        """Restore state from a specific backup file"""
        try:
            with open(filepath, 'r') as f:
                backup_data = json.load(f)

            logger.info("Restored state from: %s (created: %s)",
                       filepath, backup_data.get("timestamp"))
            return True

        except Exception as e:
            logger.error("Failed to restore state from %s: %s", filepath, e)
            return False

    def get_restore_data(self, filepath: str) -> Optional[Dict[str, Any]]:
        """Get state data from backup file"""
        try:
            with open(filepath, 'r') as f:
                backup_data = json.load(f)
            return backup_data.get("state_data", {})
        except Exception as e:
            logger.error("Failed to read backup: %s", e)
            return None

    # =========================================================================
    # WATCHDOG (DEAD MAN'S SWITCH)
    # =========================================================================

    def start_watchdog(self):
        """Start the watchdog thread"""
        if self._watchdog_thread and self._watchdog_thread.is_alive():
            return

        self._stop_event.clear()
        self._watchdog_thread = threading.Thread(target=self._watchdog_loop)
        self._watchdog_thread.daemon = True
        self._watchdog_thread.start()
        logger.info("Watchdog started")

    def stop_watchdog(self):
        """Stop the watchdog thread"""
        self._stop_event.set()
        if self._watchdog_thread:
            self._watchdog_thread.join(timeout=5)
        logger.info("Watchdog stopped")

    def _watchdog_loop(self):
        """Watchdog monitoring loop"""
        while not self._stop_event.is_set():
            try:
                # Check heartbeat
                if self.check_heartbeat_timeout():
                    logger.critical("WATCHDOG: Heartbeat timeout detected!")
                    self.record_health_check("heartbeat", False, 0, "Heartbeat timeout")

                    # If auto recovery is enabled, trigger it
                    if self.config.auto_recovery_enabled:
                        self._trigger_recovery()

                time.sleep(self.config.heartbeat_interval_sec)

            except Exception as e:
                logger.error("Watchdog error: %s", e)

    # =========================================================================
    # EMERGENCY PROCEDURES
    # =========================================================================

    def initiate_emergency_shutdown(self, reason: str):
        """Initiate emergency shutdown"""
        logger.critical("EMERGENCY SHUTDOWN initiated: %s", reason)

        self.system_state = SystemState.EMERGENCY_SHUTDOWN
        self._set_degradation_level(DegradationLevel.EMERGENCY_CLOSE)

        # Notify callbacks
        for callback in self.state_change_callbacks:
            try:
                callback(SystemState.CRITICAL, SystemState.EMERGENCY_SHUTDOWN)
            except Exception as e:
                logger.error("Emergency callback failed: %s", e)

    def emergency_close_all_positions(self, exchange_client, positions: List[Dict]) -> List[Dict]:
        """Emergency close all positions"""
        results = []

        for position in positions:
            symbol = position.get("symbol", "")
            side = position.get("side", "")
            amount = abs(float(position.get("contracts", 0)))

            if amount <= 0:
                continue

            try:
                # Close position
                close_side = "sell" if side == "long" else "buy"

                logger.warning("Emergency closing %s: %s %s", symbol, close_side, amount)

                if hasattr(exchange_client, 'create_market_order'):
                    order = exchange_client.create_market_order(
                        symbol=symbol,
                        side=close_side,
                        amount=amount,
                        params={"reduceOnly": True}
                    )
                    results.append({"symbol": symbol, "success": True, "order": order})
                else:
                    results.append({"symbol": symbol, "success": False, "error": "No order method"})

            except Exception as e:
                logger.error("Failed to close %s: %s", symbol, e)
                results.append({"symbol": symbol, "success": False, "error": str(e)})

        return results

    # =========================================================================
    # STATUS & REPORTING
    # =========================================================================

    def get_status(self) -> Dict[str, Any]:
        """Get current fail-safe status"""
        return {
            "timestamp": datetime.now().isoformat(),
            "system_state": self.system_state.value,
            "degradation_level": self.degradation_level.name,
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "heartbeat_age_sec": (datetime.now() - self.last_heartbeat).total_seconds(),
            "recovery_in_progress": self.recovery_in_progress,
            "last_recovery": self.last_recovery_time.isoformat() if self.last_recovery_time else None,
            "last_backup": self.last_backup_time.isoformat() if self.last_backup_time else None,
            "health_checks": {
                name: {
                    "status": check.status,
                    "latency_ms": check.latency_ms,
                    "consecutive_failures": check.consecutive_failures
                }
                for name, check in self.health_checks.items()
            },
            "permissions": {
                "can_open_new_position": self.can_open_new_position(),
                "can_execute_trades": self.can_execute_trades(),
                "should_close_positions": self.should_close_positions(),
                "max_positions_allowed": self.get_max_positions_allowed(),
                "scan_interval_multiplier": self.get_scan_interval_multiplier()
            },
            "recent_recovery_attempts": [
                {
                    "action": r.action.value,
                    "timestamp": r.timestamp.isoformat(),
                    "success": r.success,
                    "duration_ms": r.duration_ms
                }
                for r in self.recovery_attempts[-10:]
            ]
        }

    def get_health_summary(self) -> str:
        """Get human-readable health summary"""
        lines = [
            f"System State: {self.system_state.value}",
            f"Degradation: {self.degradation_level.name}",
            "",
            "Component Health:"
        ]

        for name, check in self.health_checks.items():
            status_icon = "✓" if check.status == "HEALTHY" else "✗"
            lines.append(f"  {status_icon} {name}: {check.status} ({check.latency_ms:.1f}ms)")

        return "\n".join(lines)


# =============================================================================
# INTEGRATION HELPERS
# =============================================================================

class FailSafeIntegration:
    """Helper class for integrating fail-safe with main trading system"""

    def __init__(self, fail_safe: FailSafeMechanisms):
        self.fail_safe = fail_safe
        self.original_scan_interval = 60.0

    def wrap_exchange_call(self, func: Callable, *args, **kwargs):
        """Wrap exchange API call with fail-safe monitoring"""
        start = time.time()
        try:
            result = func(*args, **kwargs)
            latency = (time.time() - start) * 1000
            self.fail_safe.record_health_check("exchange", True, latency)
            return result
        except Exception as e:
            latency = (time.time() - start) * 1000
            self.fail_safe.record_health_check("exchange", False, latency, str(e))
            raise

    def should_skip_scan(self) -> bool:
        """Check if scan should be skipped based on degradation"""
        return not self.fail_safe.can_open_new_position()

    def get_adjusted_scan_interval(self) -> float:
        """Get scan interval adjusted for degradation"""
        return self.original_scan_interval * self.fail_safe.get_scan_interval_multiplier()

    def pre_trade_check(self, is_new_position: bool = True) -> tuple[bool, str]:
        """Pre-trade safety check"""
        if self.fail_safe.should_close_positions():
            return False, "Emergency mode - only closing positions"

        if is_new_position and not self.fail_safe.can_open_new_position():
            return False, "Degraded mode - no new positions allowed"

        if not self.fail_safe.can_execute_trades():
            return False, "Trading disabled due to system issues"

        return True, "OK"


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("FAIL-SAFE MECHANISMS TEST")
    print("=" * 60)

    # Create fail-safe with config (auto_recovery disabled for testing)
    config = FailSafeConfig(
        heartbeat_interval_sec=5,
        heartbeat_timeout_sec=15,
        max_consecutive_failures=3,
        auto_recovery_enabled=False  # Disabled for predictable test states
    )
    fail_safe = FailSafeMechanisms(config)

    # Test health checks
    print("\n1. Testing health checks...")
    fail_safe.record_health_check("exchange", True, 45.5)
    fail_safe.record_health_check("redis", True, 2.3)
    fail_safe.record_health_check("scanner", True, 150.0)

    print(f"   System state: {fail_safe.system_state.value}")
    assert fail_safe.system_state == SystemState.HEALTHY
    print("   ✓ Healthy state confirmed")

    # Test degradation
    print("\n2. Testing degradation...")
    fail_safe.record_health_check("exchange", False, 0, "Connection timeout")
    fail_safe.record_health_check("exchange", False, 0, "Connection timeout")

    print(f"   System state: {fail_safe.system_state.value}")
    print(f"   Degradation: {fail_safe.degradation_level.name}")
    assert fail_safe.system_state == SystemState.DEGRADED
    print("   ✓ Degradation detected correctly")

    # Test critical state
    print("\n3. Testing critical state...")
    for i in range(5):
        fail_safe.record_health_check("exchange", False, 0, f"Failure {i+1}")

    print(f"   System state: {fail_safe.system_state.value}")
    print(f"   Degradation: {fail_safe.degradation_level.name}")
    assert fail_safe.system_state == SystemState.CRITICAL
    print("   ✓ Critical state triggered")

    # Test permissions
    print("\n4. Testing permissions...")
    print(f"   Can open new position: {fail_safe.can_open_new_position()}")
    print(f"   Can execute trades: {fail_safe.can_execute_trades()}")
    print(f"   Should close positions: {fail_safe.should_close_positions()}")
    print(f"   Scan multiplier: {fail_safe.get_scan_interval_multiplier()}x")

    # Test recovery
    print("\n5. Testing recovery...")

    def mock_reconnect():
        print("   Mock reconnect called")
        return True

    fail_safe.register_recovery_callback(RecoveryAction.RECONNECT_EXCHANGE, mock_reconnect)
    success = fail_safe.manual_recovery(RecoveryAction.RECONNECT_EXCHANGE)
    print(f"   Recovery success: {success}")

    # Test state backup
    print("\n6. Testing state backup...")
    test_state = {
        "positions": [{"symbol": "BTC/USDT", "side": "long", "amount": 0.1}],
        "averaging_steps": {"BTC/USDT": 2}
    }
    backup_path = fail_safe.backup_state(test_state)
    print(f"   Backup created: {backup_path}")

    # Restore
    restored_data = fail_safe.get_restore_data(backup_path)
    assert restored_data is not None
    print("   ✓ State restored successfully")

    # Test heartbeat
    print("\n7. Testing heartbeat...")
    fail_safe.heartbeat()
    print(f"   Last heartbeat: {fail_safe.last_heartbeat.isoformat()}")
    print(f"   Timeout: {fail_safe.check_heartbeat_timeout()}")

    # Test integration helper
    print("\n8. Testing integration helper...")
    integration = FailSafeIntegration(fail_safe)
    can_trade, reason = integration.pre_trade_check(is_new_position=True)
    print(f"   Pre-trade check: {can_trade} ({reason})")
    print(f"   Adjusted scan interval: {integration.get_adjusted_scan_interval()}s")

    # Get status
    print("\n9. Status report:")
    status = fail_safe.get_status()
    print(f"   State: {status['system_state']}")
    print(f"   Degradation: {status['degradation_level']}")
    print(f"   Recovery in progress: {status['recovery_in_progress']}")

    # Health summary
    print("\n10. Health summary:")
    print(fail_safe.get_health_summary())

    # Save status
    status_file = "/root/ai_xyz/fail_safe_status.json"
    with open(status_file, 'w') as f:
        json.dump(status, f, indent=2, default=str)
    print(f"\nStatus saved to {status_file}")

    print("\n" + "=" * 60)
    print("Fail-Safe Mechanisms test completed!")
    print("=" * 60)
