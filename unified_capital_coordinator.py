#!/usr/bin/env python3
"""
Unified Capital Coordinator V2.0.0 - Shared Capital Allocation for AI-XYZ
==========================================================================

Consortium Design: Claude (Opus 4.5) + Grok (grok-2-latest)
Date: January 17, 2026

V2.0.0 Improvements (Grok Recommendations):
- Redis distributed locking for conflict prevention
- Position reconciliation process
- Circuit breaker for anomaly detection
- Regime switching buffer (prevents rapid changes)
- Enhanced logging with audit trail
- Robust error handling with retries

Single source of truth for capital allocation between:
- Main Engine (TieredCapitalAllocation) - DRIVER
- Quick Scalper V3 (ScalperCapitalManager) - READER

ARCHITECTURE:
```
Main Engine (DRIVER) ──► Redis ◄── Quick Scalper (READER)
       │                  │
       ├── update_regime()   └── get_scalper_allocation()
       ├── update_equity()
       ├── main_allocate()    [with distributed lock]
       ├── main_release()
       └── main_sync_positions()

Safety Features:
- Distributed locks prevent race conditions
- Circuit breaker halts on anomalies
- Reconciliation detects discrepancies
- Regime buffer prevents rapid switching
```
"""

import os
import json
import redis
import time
import threading
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from dotenv import load_dotenv
from enum import Enum

load_dotenv()


# ========== CONFIGURATION ==========

class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Halted - anomaly detected
    HALF_OPEN = "half_open"  # Testing recovery


# Regime allocation percentages
REGIME_ALLOCATION = {
    'low_vol': {
        'scalper_pct': 0.10,
        'main_pct': 0.90,
        'scalper_max_positions': 1,
        'main_position_multiplier': 1.0
    },
    'normal_vol': {
        'scalper_pct': 0.15,
        'main_pct': 0.85,
        'scalper_max_positions': 2,
        'main_position_multiplier': 1.0
    },
    'high_vol': {
        'scalper_pct': 0.20,
        'main_pct': 0.80,
        'scalper_max_positions': 3,
        'main_position_multiplier': 1.2
    },
    'crisis': {
        'scalper_pct': 0.05,
        'main_pct': 0.95,
        'scalper_max_positions': 1,
        'main_position_multiplier': 1.5
    }
}

# Safety thresholds
REGIME_SWITCH_BUFFER_SECONDS = 30  # Minimum time between regime switches
CIRCUIT_BREAKER_THRESHOLD = 5      # Errors before circuit opens
CIRCUIT_BREAKER_RESET_SECONDS = 60 # Time before circuit resets
LOCK_TIMEOUT_SECONDS = 5           # Redis lock timeout
LOCK_RETRY_ATTEMPTS = 3            # Lock acquisition retries
RECONCILIATION_INTERVAL = 60       # Seconds between reconciliations


@dataclass
class UnifiedCapitalState:
    """Current state of unified capital allocation"""
    total_equity: float
    current_regime: str
    scalper_allocated: float
    main_allocated: float
    scalper_used: float
    main_used: float
    scalper_positions: int
    scalper_max_positions: int
    main_positions: int
    main_max_positions: int
    last_update: str
    last_regime_change: str
    circuit_state: str = "closed"
    discrepancies_detected: int = 0


@dataclass
class AuditLogEntry:
    """Audit log entry for capital operations"""
    timestamp: str
    operation: str
    system: str  # 'main' or 'scalper'
    symbol: str
    amount: float
    success: bool
    message: str
    regime: str


class UnifiedCapitalCoordinator:
    """
    Unified Capital Coordinator V2.0.0

    Features:
    - Distributed Redis locking for thread safety
    - Circuit breaker pattern for fault tolerance
    - Position reconciliation
    - Regime switching buffer
    - Comprehensive audit logging
    """

    # Redis keys
    REDIS_KEY_STATE = "unified_capital:state"
    REDIS_KEY_MAIN_POSITIONS = "unified_capital:main_positions"
    REDIS_KEY_SCALPER_POSITIONS = "unified_capital:scalper_positions"
    REDIS_KEY_LOCK = "unified_capital:lock"
    REDIS_KEY_AUDIT_LOG = "unified_capital:audit_log"
    REDIS_KEY_CIRCUIT_STATE = "unified_capital:circuit"
    REDIS_KEY_REGIME_TIMESTAMP = "unified_capital:regime_ts"

    def __init__(
        self,
        total_equity: float = None,
        redis_host: str = None,
        redis_port: int = None,
        max_main_positions: int = 30
    ):
        """Initialize Unified Capital Coordinator V2.0.0"""
        self.total_equity = total_equity or float(os.getenv('INITIAL_BALANCE', 400.0))
        self.max_main_positions = max_main_positions
        self.current_regime = 'normal_vol'

        # Redis setup
        self.redis_host = redis_host or os.getenv('REDIS_HOST', 'redis')
        self.redis_port = redis_port or int(os.getenv('REDIS_PORT', 6379))
        self.redis = None
        self._init_redis()

        # Circuit breaker state
        self.circuit_state = CircuitState.CLOSED
        self.error_count = 0
        self.last_error_time = None
        self.circuit_opened_at = None

        # Regime switching buffer
        self.last_regime_change = None

        # Reconciliation tracking
        self.last_reconciliation = None
        self.discrepancies_detected = 0

        # Thread lock for local operations
        self._local_lock = threading.Lock()

        # Load or initialize state
        self._load_or_init_state()

        print(f"UnifiedCapitalCoordinator V2.0.0 initialized")
        print(f"   Total Equity: ${self.total_equity:.2f}")
        print(f"   Regime: {self.current_regime}")
        print(f"   Safety: Locking={LOCK_TIMEOUT_SECONDS}s, CircuitBreaker={CIRCUIT_BREAKER_THRESHOLD} errors")
        self._print_allocation()

    # ========== REDIS & ERROR HANDLING ==========

    def _init_redis(self):
        """Initialize Redis connection with retry logic"""
        for attempt in range(3):
            try:
                self.redis = redis.Redis(
                    host=self.redis_host,
                    port=self.redis_port,
                    db=0,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
                )
                self.redis.ping()
                return
            except Exception as e:
                print(f"   Redis connection attempt {attempt + 1} failed: {e}")
                time.sleep(1)

        print(f"   Warning: Redis connection failed after 3 attempts")
        self.redis = None

    def _handle_error(self, operation: str, error: Exception):
        """Handle errors and update circuit breaker"""
        self.error_count += 1
        self.last_error_time = datetime.now()

        self._log(f"ERROR in {operation}: {error}", "error")

        if self.error_count >= CIRCUIT_BREAKER_THRESHOLD:
            self._open_circuit(f"Error threshold reached: {error}")

    def _reset_error_count(self):
        """Reset error count on successful operation"""
        if self.error_count > 0:
            self.error_count = max(0, self.error_count - 1)

    # ========== DISTRIBUTED LOCKING ==========

    def _acquire_lock(self, lock_name: str = None) -> bool:
        """Acquire distributed Redis lock"""
        if not self.redis:
            return True  # Allow local operation if no Redis

        lock_key = lock_name or self.REDIS_KEY_LOCK

        for attempt in range(LOCK_RETRY_ATTEMPTS):
            try:
                # Use SET NX with expiry for distributed lock
                acquired = self.redis.set(
                    lock_key,
                    f"lock:{datetime.now().isoformat()}",
                    nx=True,
                    ex=LOCK_TIMEOUT_SECONDS
                )
                if acquired:
                    return True

                # Wait before retry
                time.sleep(0.1 * (attempt + 1))

            except Exception as e:
                self._handle_error("acquire_lock", e)

        self._log(f"Failed to acquire lock after {LOCK_RETRY_ATTEMPTS} attempts", "warning")
        return False

    def _release_lock(self, lock_name: str = None):
        """Release distributed Redis lock"""
        if not self.redis:
            return

        lock_key = lock_name or self.REDIS_KEY_LOCK

        try:
            self.redis.delete(lock_key)
        except Exception as e:
            self._handle_error("release_lock", e)

    # ========== CIRCUIT BREAKER ==========

    def _open_circuit(self, reason: str):
        """Open circuit breaker - halt operations"""
        if self.circuit_state != CircuitState.OPEN:
            self.circuit_state = CircuitState.OPEN
            self.circuit_opened_at = datetime.now()
            self._log(f"CIRCUIT BREAKER OPENED: {reason}", "critical")

            # Store in Redis for other systems
            if self.redis:
                try:
                    self.redis.set(
                        self.REDIS_KEY_CIRCUIT_STATE,
                        json.dumps({
                            'state': 'open',
                            'reason': reason,
                            'opened_at': self.circuit_opened_at.isoformat()
                        }),
                        ex=CIRCUIT_BREAKER_RESET_SECONDS * 2
                    )
                except:
                    pass

    def _check_circuit(self) -> Tuple[bool, str]:
        """Check if circuit allows operations"""
        if self.circuit_state == CircuitState.CLOSED:
            return True, "OK"

        if self.circuit_state == CircuitState.OPEN:
            # Check if we should try half-open
            if self.circuit_opened_at:
                elapsed = (datetime.now() - self.circuit_opened_at).total_seconds()
                if elapsed >= CIRCUIT_BREAKER_RESET_SECONDS:
                    self.circuit_state = CircuitState.HALF_OPEN
                    self._log("Circuit breaker entering HALF_OPEN state", "info")
                    return True, "HALF_OPEN - testing"

            return False, "Circuit breaker OPEN - operations halted"

        # HALF_OPEN - allow operation but watch for errors
        return True, "HALF_OPEN"

    def _close_circuit(self):
        """Close circuit breaker - resume normal operations"""
        if self.circuit_state != CircuitState.CLOSED:
            self.circuit_state = CircuitState.CLOSED
            self.error_count = 0
            self.circuit_opened_at = None
            self._log("Circuit breaker CLOSED - normal operations resumed", "info")

            if self.redis:
                try:
                    self.redis.delete(self.REDIS_KEY_CIRCUIT_STATE)
                except:
                    pass

    def get_circuit_state(self) -> Dict:
        """Get current circuit breaker state"""
        return {
            'state': self.circuit_state.value,
            'error_count': self.error_count,
            'threshold': CIRCUIT_BREAKER_THRESHOLD,
            'opened_at': self.circuit_opened_at.isoformat() if self.circuit_opened_at else None
        }

    # ========== LOGGING & AUDIT ==========

    def _log(self, message: str, level: str = "info"):
        """Enhanced logging with timestamp"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = {
            "info": "   ",
            "warning": "   ⚠️ ",
            "error": "   ❌ ",
            "critical": "   🚨 ",
            "audit": "   📝 "
        }.get(level, "   ")

        print(f"{prefix}[{timestamp}] {message}")

    def _audit_log(self, operation: str, system: str, symbol: str,
                   amount: float, success: bool, message: str):
        """Write to audit log"""
        entry = AuditLogEntry(
            timestamp=datetime.now().isoformat(),
            operation=operation,
            system=system,
            symbol=symbol,
            amount=amount,
            success=success,
            message=message,
            regime=self.current_regime
        )

        # Store in Redis (keep last 100 entries)
        if self.redis:
            try:
                self.redis.lpush(self.REDIS_KEY_AUDIT_LOG, json.dumps(asdict(entry)))
                self.redis.ltrim(self.REDIS_KEY_AUDIT_LOG, 0, 99)
            except:
                pass

        self._log(f"AUDIT: {operation} {system} {symbol} ${amount:.2f} - {message}", "audit")

    def get_audit_log(self, limit: int = 20) -> List[Dict]:
        """Get recent audit log entries"""
        if not self.redis:
            return []

        try:
            entries = self.redis.lrange(self.REDIS_KEY_AUDIT_LOG, 0, limit - 1)
            return [json.loads(e) for e in entries]
        except:
            return []

    # ========== STATE MANAGEMENT ==========

    def _load_or_init_state(self):
        """Load existing state from Redis or initialize new"""
        if self.redis:
            try:
                state_json = self.redis.get(self.REDIS_KEY_STATE)
                if state_json:
                    state = json.loads(state_json)
                    self.current_regime = state.get('current_regime', 'normal_vol')
                    self.total_equity = state.get('total_equity', self.total_equity)

                    # Load regime timestamp
                    ts = self.redis.get(self.REDIS_KEY_REGIME_TIMESTAMP)
                    if ts:
                        self.last_regime_change = datetime.fromisoformat(ts)

                    # Load circuit state
                    circuit_json = self.redis.get(self.REDIS_KEY_CIRCUIT_STATE)
                    if circuit_json:
                        circuit = json.loads(circuit_json)
                        if circuit.get('state') == 'open':
                            self.circuit_state = CircuitState.OPEN
                            self.circuit_opened_at = datetime.fromisoformat(circuit['opened_at'])

                    self._log(f"Loaded state from Redis (regime: {self.current_regime})")
                    return
            except Exception as e:
                self._log(f"State load error: {e}", "warning")

        self._save_state()

    def _save_state(self):
        """Save current state to Redis with lock"""
        if not self.redis:
            return

        if not self._acquire_lock("unified_capital:state_lock"):
            return

        try:
            allocation = self.get_allocation()
            state = {
                'total_equity': self.total_equity,
                'current_regime': self.current_regime,
                'scalper_pct': allocation['scalper_pct'],
                'main_pct': allocation['main_pct'],
                'scalper_allocated': allocation['scalper_capital'],
                'main_allocated': allocation['main_capital'],
                'scalper_max_positions': allocation['scalper_max_positions'],
                'main_max_positions': allocation['main_max_positions'],
                'last_update': datetime.now().isoformat(),
                'circuit_state': self.circuit_state.value,
                'version': '2.0.0'
            }
            self.redis.set(self.REDIS_KEY_STATE, json.dumps(state))
            self._reset_error_count()
        except Exception as e:
            self._handle_error("save_state", e)
        finally:
            self._release_lock("unified_capital:state_lock")

    def _print_allocation(self):
        """Print current allocation"""
        alloc = self.get_allocation()
        print(f"   Scalper: {alloc['scalper_pct']*100:.0f}% = ${alloc['scalper_capital']:.2f} (max {alloc['scalper_max_positions']} pos)")
        print(f"   Main: {alloc['main_pct']*100:.0f}% = ${alloc['main_capital']:.2f} (max {alloc['main_max_positions']} pos)")

    # ========== CORE METHODS ==========

    def update_regime(self, regime: str) -> Tuple[bool, str]:
        """
        Update HMM regime with buffer to prevent rapid switching.

        Returns:
            Tuple of (success, message)
        """
        # Check circuit breaker
        allowed, reason = self._check_circuit()
        if not allowed:
            return False, reason

        regime = regime.lower()
        if regime not in REGIME_ALLOCATION:
            regime = 'normal_vol'

        if regime == self.current_regime:
            return True, "No change"

        # Check regime switching buffer
        if self.last_regime_change:
            elapsed = (datetime.now() - self.last_regime_change).total_seconds()
            if elapsed < REGIME_SWITCH_BUFFER_SECONDS:
                remaining = REGIME_SWITCH_BUFFER_SECONDS - elapsed
                return False, f"Regime switch buffer: wait {remaining:.0f}s"

        # Apply change
        old_regime = self.current_regime
        self.current_regime = regime
        self.last_regime_change = datetime.now()

        # Store timestamp in Redis
        if self.redis:
            try:
                self.redis.set(self.REDIS_KEY_REGIME_TIMESTAMP, self.last_regime_change.isoformat())
            except:
                pass

        self._save_state()
        self._log(f"Regime change: {old_regime} -> {regime}")
        self._print_allocation()

        # Close circuit if in half-open and operation succeeded
        if self.circuit_state == CircuitState.HALF_OPEN:
            self._close_circuit()

        return True, f"Regime changed: {old_regime} -> {regime}"

    def update_equity(self, new_equity: float) -> Tuple[bool, str]:
        """Update total equity with validation"""
        allowed, reason = self._check_circuit()
        if not allowed:
            return False, reason

        # Validate equity change
        if new_equity <= 0:
            return False, "Invalid equity: must be positive"

        change_pct = abs(new_equity - self.total_equity) / self.total_equity * 100

        # Alert on large changes (potential anomaly)
        if change_pct > 20:
            self._log(f"Large equity change detected: {change_pct:.1f}%", "warning")

        if abs(new_equity - self.total_equity) > 1.0:
            old_equity = self.total_equity
            self.total_equity = new_equity
            self._save_state()
            self._log(f"Equity updated: ${old_equity:.2f} -> ${new_equity:.2f} ({change_pct:+.1f}%)")

        return True, f"Equity: ${new_equity:.2f}"

    def get_allocation(self) -> Dict:
        """Get current capital allocation based on regime"""
        regime_config = REGIME_ALLOCATION.get(
            self.current_regime,
            REGIME_ALLOCATION['normal_vol']
        )

        scalper_capital = self.total_equity * regime_config['scalper_pct']
        main_capital = self.total_equity * regime_config['main_pct']
        main_max = int(self.max_main_positions * regime_config['main_position_multiplier'])

        return {
            'regime': self.current_regime,
            'total_equity': self.total_equity,
            'scalper_pct': regime_config['scalper_pct'],
            'main_pct': regime_config['main_pct'],
            'scalper_capital': scalper_capital,
            'main_capital': main_capital,
            'scalper_max_positions': regime_config['scalper_max_positions'],
            'main_max_positions': main_max
        }

    # ========== SCALPER METHODS ==========

    def get_scalper_allocation(self) -> Dict:
        """Get allocation for Quick Scalper"""
        alloc = self.get_allocation()

        scalper_used = 0.0
        scalper_positions = 0
        if self.redis:
            try:
                positions = self.redis.hgetall(self.REDIS_KEY_SCALPER_POSITIONS)
                scalper_positions = len(positions)
                scalper_used = sum(float(v) for v in positions.values())
            except:
                pass

        return {
            'regime': self.current_regime,
            'allocated': alloc['scalper_capital'],
            'used': scalper_used,
            'available': max(0, alloc['scalper_capital'] - scalper_used),
            'positions': scalper_positions,
            'max_positions': alloc['scalper_max_positions'],
            'can_open': scalper_positions < alloc['scalper_max_positions'],
            'circuit_state': self.circuit_state.value
        }

    def scalper_allocate(self, symbol: str, margin: float) -> Tuple[bool, str]:
        """Allocate capital for scalper position with locking"""
        # Check circuit
        allowed, reason = self._check_circuit()
        if not allowed:
            self._audit_log("allocate", "scalper", symbol, margin, False, reason)
            return False, reason

        # Acquire lock
        if not self._acquire_lock("unified_capital:scalper_lock"):
            return False, "Could not acquire lock"

        try:
            alloc = self.get_scalper_allocation()

            if not alloc['can_open']:
                msg = f"Scalper position limit: {alloc['positions']}/{alloc['max_positions']}"
                self._audit_log("allocate", "scalper", symbol, margin, False, msg)
                return False, msg

            if margin > alloc['available']:
                msg = f"Insufficient scalper capital: ${margin:.2f} > ${alloc['available']:.2f}"
                self._audit_log("allocate", "scalper", symbol, margin, False, msg)
                return False, msg

            # Check main engine conflict
            if self.redis:
                main_has = self.redis.hexists(self.REDIS_KEY_MAIN_POSITIONS, symbol)
                if main_has:
                    msg = f"Main engine has position in {symbol}"
                    self._audit_log("allocate", "scalper", symbol, margin, False, msg)
                    return False, msg

                # Allocate
                self.redis.hset(self.REDIS_KEY_SCALPER_POSITIONS, symbol, str(margin))

            msg = f"Allocated ${margin:.2f} for {symbol}"
            self._audit_log("allocate", "scalper", symbol, margin, True, msg)

            # Close circuit if half-open
            if self.circuit_state == CircuitState.HALF_OPEN:
                self._close_circuit()

            return True, msg

        except Exception as e:
            self._handle_error("scalper_allocate", e)
            return False, str(e)
        finally:
            self._release_lock("unified_capital:scalper_lock")

    def scalper_release(self, symbol: str) -> Tuple[bool, str]:
        """Release scalper position capital"""
        if self.redis:
            margin = self.redis.hget(self.REDIS_KEY_SCALPER_POSITIONS, symbol) or "0"
            self.redis.hdel(self.REDIS_KEY_SCALPER_POSITIONS, symbol)
            self._audit_log("release", "scalper", symbol, float(margin), True, f"Released {symbol}")
        return True, f"Released {symbol}"

    # ========== MAIN ENGINE METHODS ==========

    def get_main_allocation(self) -> Dict:
        """Get allocation for Main Engine"""
        alloc = self.get_allocation()

        main_used = 0.0
        main_positions = 0
        if self.redis:
            try:
                positions = self.redis.hgetall(self.REDIS_KEY_MAIN_POSITIONS)
                main_positions = len(positions)
                main_used = sum(float(v) for v in positions.values())
            except:
                pass

        return {
            'regime': self.current_regime,
            'allocated': alloc['main_capital'],
            'used': main_used,
            'available': max(0, alloc['main_capital'] - main_used),
            'positions': main_positions,
            'max_positions': alloc['main_max_positions'],
            'can_open': main_positions < alloc['main_max_positions'],
            'circuit_state': self.circuit_state.value
        }

    def main_allocate(self, symbol: str, margin: float) -> Tuple[bool, str]:
        """Allocate capital for main engine position with locking"""
        allowed, reason = self._check_circuit()
        if not allowed:
            self._audit_log("allocate", "main", symbol, margin, False, reason)
            return False, reason

        if not self._acquire_lock("unified_capital:main_lock"):
            return False, "Could not acquire lock"

        try:
            alloc = self.get_main_allocation()

            if not alloc['can_open']:
                msg = f"Main position limit: {alloc['positions']}/{alloc['max_positions']}"
                self._audit_log("allocate", "main", symbol, margin, False, msg)
                return False, msg

            if margin > alloc['available']:
                msg = f"Insufficient main capital: ${margin:.2f} > ${alloc['available']:.2f}"
                self._audit_log("allocate", "main", symbol, margin, False, msg)
                return False, msg

            if self.redis:
                self.redis.hset(self.REDIS_KEY_MAIN_POSITIONS, symbol, str(margin))

            msg = f"Allocated ${margin:.2f} for {symbol}"
            self._audit_log("allocate", "main", symbol, margin, True, msg)

            if self.circuit_state == CircuitState.HALF_OPEN:
                self._close_circuit()

            return True, msg

        except Exception as e:
            self._handle_error("main_allocate", e)
            return False, str(e)
        finally:
            self._release_lock("unified_capital:main_lock")

    def main_release(self, symbol: str) -> Tuple[bool, str]:
        """Release main engine position capital"""
        if self.redis:
            margin = self.redis.hget(self.REDIS_KEY_MAIN_POSITIONS, symbol) or "0"
            self.redis.hdel(self.REDIS_KEY_MAIN_POSITIONS, symbol)
            self._audit_log("release", "main", symbol, float(margin), True, f"Released {symbol}")
        return True, f"Released {symbol}"

    def main_sync_positions(self, positions: list):
        """Sync main engine positions from exchange with locking"""
        if not self.redis:
            return

        if not self._acquire_lock("unified_capital:sync_lock"):
            self._log("Could not acquire lock for position sync", "warning")
            return

        try:
            # Get current positions before sync
            old_positions = set(self.redis.hkeys(self.REDIS_KEY_MAIN_POSITIONS))

            # Clear and rebuild
            self.redis.delete(self.REDIS_KEY_MAIN_POSITIONS)

            new_positions = set()
            for pos in positions:
                symbol = pos.get('symbol', '')
                margin = abs(pos.get('initialMargin', 0)) or abs(pos.get('margin', 0))
                if symbol and margin > 0:
                    self.redis.hset(self.REDIS_KEY_MAIN_POSITIONS, symbol, str(margin))
                    new_positions.add(symbol)

            # Log changes
            added = new_positions - old_positions
            removed = old_positions - new_positions

            if added:
                self._log(f"Position sync: added {len(added)} positions")
            if removed:
                self._log(f"Position sync: removed {len(removed)} positions")

            self._reset_error_count()

        except Exception as e:
            self._handle_error("main_sync_positions", e)
        finally:
            self._release_lock("unified_capital:sync_lock")

    # ========== RECONCILIATION ==========

    def reconcile(self, main_exchange_positions: List[str] = None,
                  scalper_exchange_positions: List[str] = None) -> Dict:
        """
        Reconcile coordinator state with exchange positions.

        Args:
            main_exchange_positions: List of symbols main engine has on exchange
            scalper_exchange_positions: List of symbols scalper has on exchange

        Returns:
            Dict with reconciliation results
        """
        if not self.redis:
            return {'success': False, 'reason': 'No Redis connection'}

        results = {
            'success': True,
            'main_discrepancies': [],
            'scalper_discrepancies': [],
            'actions_taken': []
        }

        try:
            # Check main positions
            if main_exchange_positions is not None:
                coordinator_main = set(self.redis.hkeys(self.REDIS_KEY_MAIN_POSITIONS))
                exchange_main = set(main_exchange_positions)

                # Positions in coordinator but not on exchange (stale)
                stale_main = coordinator_main - exchange_main
                for symbol in stale_main:
                    results['main_discrepancies'].append({
                        'symbol': symbol,
                        'issue': 'in_coordinator_not_exchange',
                        'action': 'removed'
                    })
                    self.redis.hdel(self.REDIS_KEY_MAIN_POSITIONS, symbol)
                    results['actions_taken'].append(f"Removed stale main position: {symbol}")

                # Positions on exchange but not in coordinator (missing)
                missing_main = exchange_main - coordinator_main
                for symbol in missing_main:
                    results['main_discrepancies'].append({
                        'symbol': symbol,
                        'issue': 'on_exchange_not_coordinator',
                        'action': 'flagged'
                    })

            # Check scalper positions
            if scalper_exchange_positions is not None:
                coordinator_scalper = set(self.redis.hkeys(self.REDIS_KEY_SCALPER_POSITIONS))
                exchange_scalper = set(scalper_exchange_positions)

                stale_scalper = coordinator_scalper - exchange_scalper
                for symbol in stale_scalper:
                    results['scalper_discrepancies'].append({
                        'symbol': symbol,
                        'issue': 'in_coordinator_not_exchange',
                        'action': 'removed'
                    })
                    self.redis.hdel(self.REDIS_KEY_SCALPER_POSITIONS, symbol)
                    results['actions_taken'].append(f"Removed stale scalper position: {symbol}")

            # Update discrepancy count
            total_discrepancies = len(results['main_discrepancies']) + len(results['scalper_discrepancies'])
            self.discrepancies_detected += total_discrepancies

            if total_discrepancies > 0:
                self._log(f"Reconciliation found {total_discrepancies} discrepancies", "warning")

                # Open circuit if too many discrepancies
                if total_discrepancies >= 5:
                    self._open_circuit(f"Too many discrepancies: {total_discrepancies}")
                    results['circuit_opened'] = True

            self.last_reconciliation = datetime.now()

        except Exception as e:
            self._handle_error("reconcile", e)
            results['success'] = False
            results['error'] = str(e)

        return results

    def check_conflicts(self) -> List[Dict]:
        """Check for position conflicts between main and scalper"""
        conflicts = []

        if not self.redis:
            return conflicts

        try:
            main_positions = set(self.redis.hkeys(self.REDIS_KEY_MAIN_POSITIONS))
            scalper_positions = set(self.redis.hkeys(self.REDIS_KEY_SCALPER_POSITIONS))

            # Same symbol in both systems = conflict
            overlapping = main_positions & scalper_positions
            for symbol in overlapping:
                main_margin = float(self.redis.hget(self.REDIS_KEY_MAIN_POSITIONS, symbol) or 0)
                scalper_margin = float(self.redis.hget(self.REDIS_KEY_SCALPER_POSITIONS, symbol) or 0)

                conflicts.append({
                    'symbol': symbol,
                    'main_margin': main_margin,
                    'scalper_margin': scalper_margin,
                    'resolution': 'scalper_should_close'  # Main has priority
                })

                self._log(f"CONFLICT: {symbol} in both main (${main_margin:.2f}) and scalper (${scalper_margin:.2f})", "warning")

        except Exception as e:
            self._handle_error("check_conflicts", e)

        return conflicts

    # ========== STATUS ==========

    def get_full_state(self) -> UnifiedCapitalState:
        """Get complete unified capital state"""
        alloc = self.get_allocation()
        scalper = self.get_scalper_allocation()
        main = self.get_main_allocation()

        return UnifiedCapitalState(
            total_equity=self.total_equity,
            current_regime=self.current_regime,
            scalper_allocated=alloc['scalper_capital'],
            main_allocated=alloc['main_capital'],
            scalper_used=scalper['used'],
            main_used=main['used'],
            scalper_positions=scalper['positions'],
            scalper_max_positions=scalper['max_positions'],
            main_positions=main['positions'],
            main_max_positions=main['max_positions'],
            last_update=datetime.now().isoformat(),
            last_regime_change=self.last_regime_change.isoformat() if self.last_regime_change else "",
            circuit_state=self.circuit_state.value,
            discrepancies_detected=self.discrepancies_detected
        )

    def print_status(self):
        """Print formatted status"""
        state = self.get_full_state()

        print("\n" + "=" * 70)
        print("UNIFIED CAPITAL COORDINATOR V2.0.0 STATUS")
        print("=" * 70)
        print(f"Regime: {state.current_regime.upper()}")
        print(f"Total Equity: ${state.total_equity:.2f}")
        print(f"Circuit: {state.circuit_state.upper()} | Discrepancies: {state.discrepancies_detected}")
        print("-" * 70)
        print(f"SCALPER:  ${state.scalper_allocated:.2f} allocated | "
              f"${state.scalper_used:.2f} used | "
              f"${state.scalper_allocated - state.scalper_used:.2f} avail | "
              f"{state.scalper_positions}/{state.scalper_max_positions} pos")
        print(f"MAIN:     ${state.main_allocated:.2f} allocated | "
              f"${state.main_used:.2f} used | "
              f"${state.main_allocated - state.main_used:.2f} avail | "
              f"{state.main_positions}/{state.main_max_positions} pos")
        print("=" * 70)

    def reset_circuit_breaker(self) -> Tuple[bool, str]:
        """Manually reset circuit breaker"""
        if self.circuit_state == CircuitState.CLOSED:
            return True, "Circuit already closed"

        self._close_circuit()
        return True, "Circuit breaker manually reset"


# ========== SINGLETON ==========

_coordinator: Optional[UnifiedCapitalCoordinator] = None


def get_capital_coordinator(
    total_equity: float = None,
    max_main_positions: int = 30
) -> UnifiedCapitalCoordinator:
    """Get or create the unified capital coordinator singleton"""
    global _coordinator

    if _coordinator is None:
        _coordinator = UnifiedCapitalCoordinator(
            total_equity=total_equity,
            max_main_positions=max_main_positions
        )
    elif total_equity:
        _coordinator.update_equity(total_equity)

    return _coordinator


# ========== TESTING ==========
if __name__ == '__main__':
    print("Testing UnifiedCapitalCoordinator V2.0.0")
    print("=" * 70)

    coord = UnifiedCapitalCoordinator(total_equity=400.0, max_main_positions=30)

    # Test regime changes with buffer
    print("\n--- Regime Buffer Test ---")
    success, msg = coord.update_regime('high_vol')
    print(f"Change to high_vol: {success} - {msg}")

    # Try immediate change (should be blocked by buffer)
    success, msg = coord.update_regime('low_vol')
    print(f"Immediate change to low_vol: {success} - {msg}")

    # Test allocation with locking
    print("\n--- Allocation Test ---")
    success, msg = coord.scalper_allocate('BTC/USDT:USDT', 10.0)
    print(f"Scalper allocate BTC: {success} - {msg}")

    success, msg = coord.main_allocate('ETH/USDT:USDT', 25.0)
    print(f"Main allocate ETH: {success} - {msg}")

    # Test conflict
    success, msg = coord.scalper_allocate('ETH/USDT:USDT', 10.0)
    print(f"Scalper allocate ETH (conflict): {success} - {msg}")

    # Test reconciliation
    print("\n--- Reconciliation Test ---")
    results = coord.reconcile(
        main_exchange_positions=['ETH/USDT:USDT'],
        scalper_exchange_positions=['BTC/USDT:USDT']
    )
    print(f"Reconciliation: {results}")

    # Check conflicts
    print("\n--- Conflict Check ---")
    conflicts = coord.check_conflicts()
    print(f"Conflicts: {conflicts}")

    # Test circuit breaker
    print("\n--- Circuit Breaker Test ---")
    print(f"Circuit state: {coord.get_circuit_state()}")

    # Get audit log
    print("\n--- Audit Log ---")
    audit = coord.get_audit_log(5)
    for entry in audit:
        print(f"  {entry['timestamp']}: {entry['operation']} {entry['system']} {entry['symbol']}")

    coord.print_status()
