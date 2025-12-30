"""
Enhanced Live Position Sync - V1.3.0
Complete position lifecycle synchronization with exchange

Synchronizes ALL position tracking data:
- Core position data (entry, size, side, leverage)
- Averaging state (steps taken, multipliers, Fibonacci config)
- Surplus dump state (stage, original size, peak UPNL)
- Take profit state (partial close ladder progress, velocity tracking)
- Stop loss state (ATR peaks, trailing stop levels)
- Zone state (current zone, thresholds)
- Cooldown tracking (recently closed symbols)

Features:
- Real-time sync with exchange every 3 seconds
- Atomic state updates via Redis transactions
- Automatic recovery from disconnections
- State persistence across restarts
- Conflict resolution (exchange is source of truth)
"""

import asyncio
import json
import time
import redis
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import structlog
import ccxt

logger = structlog.get_logger(__name__)


class SyncStatus(str, Enum):
    """Position sync status"""
    SYNCED = "SYNCED"
    PENDING = "PENDING"
    CONFLICT = "CONFLICT"
    STALE = "STALE"
    ERROR = "ERROR"


@dataclass
class PositionLifecycleState:
    """Complete position lifecycle state for synchronization"""
    # Core position data
    symbol: str
    entry_price: float
    amount: float
    side: str  # 'buy' or 'sell'
    leverage: float
    opened_at: str  # ISO timestamp or 'manual'

    # Exchange data (source of truth)
    exchange_contracts: float = 0.0
    exchange_entry_price: float = 0.0
    exchange_unrealized_pnl: float = 0.0
    exchange_mark_price: float = 0.0
    exchange_liquidation_price: float = 0.0

    # Averaging state
    averaging_steps: int = 0
    averaging_multipliers: List[float] = field(default_factory=list)
    fibonacci_config: Optional[Dict] = None
    last_averaging_price: float = 0.0
    last_averaging_time: Optional[str] = None

    # Surplus dump state
    surplus_dump_stage: int = 0  # 0=none, 1=first dump done, 2=second dump done
    original_size: float = 0.0
    surplus_size: float = 0.0  # amount - original_size

    # Peak tracking (for surplus dump and trailing)
    peak_upnl: float = 0.0
    peak_upnl_timestamp: Optional[str] = None
    peak_price: float = 0.0  # For ATR trailing stop

    # Take profit state
    partial_close_stage: int = 0  # 0-3 ladder stages
    partial_close_executed: List[bool] = field(default_factory=lambda: [False, False, False])
    position_open_time: Optional[str] = None  # For time-decay profit taking

    # Stop loss state
    atr_stop_price: float = 0.0
    atr_value: float = 0.0
    trailing_stop_active: bool = False

    # Zone state
    current_zone: str = "NEUTRAL"
    zone_thresholds: Dict[str, float] = field(default_factory=lambda: {
        'averaging': -0.15,
        'surplus_dump': 0.15,
        'profit_taking': 0.05,
        'stop_loss': -0.25
    })

    # Sync metadata
    last_sync_time: Optional[str] = None
    sync_status: str = "PENDING"
    sync_errors: List[str] = field(default_factory=list)
    version: int = 0  # For optimistic locking

    def to_dict(self) -> Dict:
        """Convert to dictionary for Redis storage"""
        return {
            'symbol': self.symbol,
            'entry_price': self.entry_price,
            'amount': self.amount,
            'side': self.side,
            'leverage': self.leverage,
            'opened_at': self.opened_at,
            'exchange_contracts': self.exchange_contracts,
            'exchange_entry_price': self.exchange_entry_price,
            'exchange_unrealized_pnl': self.exchange_unrealized_pnl,
            'exchange_mark_price': self.exchange_mark_price,
            'exchange_liquidation_price': self.exchange_liquidation_price,
            'averaging_steps': self.averaging_steps,
            'averaging_multipliers': self.averaging_multipliers,
            'fibonacci_config': self.fibonacci_config,
            'last_averaging_price': self.last_averaging_price,
            'last_averaging_time': self.last_averaging_time,
            'surplus_dump_stage': self.surplus_dump_stage,
            'original_size': self.original_size,
            'surplus_size': self.surplus_size,
            'peak_upnl': self.peak_upnl,
            'peak_upnl_timestamp': self.peak_upnl_timestamp,
            'peak_price': self.peak_price,
            'partial_close_stage': self.partial_close_stage,
            'partial_close_executed': self.partial_close_executed,
            'position_open_time': self.position_open_time,
            'atr_stop_price': self.atr_stop_price,
            'atr_value': self.atr_value,
            'trailing_stop_active': self.trailing_stop_active,
            'current_zone': self.current_zone,
            'zone_thresholds': self.zone_thresholds,
            'last_sync_time': self.last_sync_time,
            'sync_status': self.sync_status,
            'sync_errors': self.sync_errors,
            'version': self.version
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'PositionLifecycleState':
        """Create from dictionary"""
        return cls(
            symbol=data['symbol'],
            entry_price=float(data.get('entry_price', 0)),
            amount=float(data.get('amount', 0)),
            side=data.get('side', 'buy'),
            leverage=float(data.get('leverage', 1)),
            opened_at=data.get('opened_at', ''),
            exchange_contracts=float(data.get('exchange_contracts', 0)),
            exchange_entry_price=float(data.get('exchange_entry_price', 0)),
            exchange_unrealized_pnl=float(data.get('exchange_unrealized_pnl', 0)),
            exchange_mark_price=float(data.get('exchange_mark_price', 0)),
            exchange_liquidation_price=float(data.get('exchange_liquidation_price', 0)),
            averaging_steps=int(data.get('averaging_steps', 0)),
            averaging_multipliers=data.get('averaging_multipliers', []),
            fibonacci_config=data.get('fibonacci_config'),
            last_averaging_price=float(data.get('last_averaging_price', 0)),
            last_averaging_time=data.get('last_averaging_time'),
            surplus_dump_stage=int(data.get('surplus_dump_stage', 0)),
            original_size=float(data.get('original_size', 0)),
            surplus_size=float(data.get('surplus_size', 0)),
            peak_upnl=float(data.get('peak_upnl', 0)),
            peak_upnl_timestamp=data.get('peak_upnl_timestamp'),
            peak_price=float(data.get('peak_price', 0)),
            partial_close_stage=int(data.get('partial_close_stage', 0)),
            partial_close_executed=data.get('partial_close_executed', [False, False, False]),
            position_open_time=data.get('position_open_time'),
            atr_stop_price=float(data.get('atr_stop_price', 0)),
            atr_value=float(data.get('atr_value', 0)),
            trailing_stop_active=bool(data.get('trailing_stop_active', False)),
            current_zone=data.get('current_zone', 'NEUTRAL'),
            zone_thresholds=data.get('zone_thresholds', {}),
            last_sync_time=data.get('last_sync_time'),
            sync_status=data.get('sync_status', 'PENDING'),
            sync_errors=data.get('sync_errors', []),
            version=int(data.get('version', 0))
        )


class EnhancedPositionSync:
    """
    Enhanced position synchronization with complete lifecycle tracking

    Cardinal Rule: Exchange is the source of truth for position existence and size.
    Local state tracks additional metadata for trading logic.
    """

    # Redis key prefixes
    KEY_PREFIX = "aixyz:sync:"
    POSITION_KEY = KEY_PREFIX + "position:"
    COOLDOWN_KEY = KEY_PREFIX + "cooldown:"
    GLOBAL_STATE_KEY = KEY_PREFIX + "global_state"
    SYNC_LOCK_KEY = KEY_PREFIX + "lock"

    def __init__(self, exchange: ccxt.Exchange, redis_host: str = 'localhost',
                 redis_port: int = 6379, redis_db: int = 0):
        """
        Initialize enhanced position sync

        Args:
            exchange: CCXT exchange instance
            redis_host: Redis host
            redis_port: Redis port
            redis_db: Redis database number
        """
        self.exchange = exchange
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )

        # Local cache for fast access
        self._position_cache: Dict[str, PositionLifecycleState] = {}
        self._cooldown_cache: Dict[str, float] = {}  # symbol -> expiry timestamp

        # Sync configuration
        self.sync_interval = 3  # Sync every 3 seconds
        self.stale_threshold = 30  # Position data stale after 30 seconds
        self.cooldown_duration = 180  # 3 minute cooldown after close

        # Sync state
        self._running = False
        self._last_sync_time = 0
        self._sync_errors = []

        logger.info("EnhancedPositionSync initialized",
                   redis_host=redis_host, redis_port=redis_port)

    def start_sync(self):
        """Start background sync loop"""
        if self._running:
            return
        self._running = True
        logger.info("Starting position sync loop")

    def stop_sync(self):
        """Stop background sync loop"""
        self._running = False
        logger.info("Stopping position sync loop")

    async def sync_loop(self):
        """Main sync loop - call this from asyncio event loop"""
        while self._running:
            try:
                await self.sync_with_exchange()
            except Exception as e:
                logger.error(f"Sync loop error: {e}")
                self._sync_errors.append(str(e))

            await asyncio.sleep(self.sync_interval)

    def sync_with_exchange_sync(self) -> Dict[str, Any]:
        """
        Synchronous version of sync_with_exchange for non-async contexts

        Returns:
            Dict with sync results
        """
        try:
            # Fetch positions from exchange
            exchange_positions = self.exchange.fetch_positions()

            # Filter to active positions only
            active_exchange = {
                p['symbol']: p for p in exchange_positions
                if p.get('contracts', 0) > 0
            }

            # Get all tracked symbols from Redis
            tracked_symbols = self._get_all_tracked_symbols()

            results = {
                'synced': [],
                'added': [],
                'removed': [],
                'conflicts': [],
                'errors': []
            }

            # Sync existing positions
            for symbol, ex_pos in active_exchange.items():
                try:
                    if symbol in tracked_symbols:
                        # Update existing position
                        self._update_position_from_exchange(symbol, ex_pos)
                        results['synced'].append(symbol)
                    else:
                        # New position detected on exchange
                        self._create_position_from_exchange(symbol, ex_pos)
                        results['added'].append(symbol)
                except Exception as e:
                    results['errors'].append({'symbol': symbol, 'error': str(e)})

            # Check for positions closed on exchange
            for symbol in tracked_symbols:
                if symbol not in active_exchange:
                    # Position closed on exchange
                    self._handle_position_closed(symbol)
                    results['removed'].append(symbol)

            self._last_sync_time = time.time()

            return results

        except Exception as e:
            logger.error(f"Sync with exchange failed: {e}")
            return {'error': str(e)}

    async def sync_with_exchange(self) -> Dict[str, Any]:
        """
        Async version - sync all positions with exchange

        Returns:
            Dict with sync results
        """
        # For now, wrap sync version
        return self.sync_with_exchange_sync()

    def _get_all_tracked_symbols(self) -> List[str]:
        """Get all symbols being tracked in Redis"""
        try:
            keys = self.redis_client.keys(f"{self.POSITION_KEY}*")
            symbols = [k.replace(self.POSITION_KEY, '') for k in keys]
            return symbols
        except Exception as e:
            logger.error(f"Failed to get tracked symbols: {e}")
            return []

    def _update_position_from_exchange(self, symbol: str, ex_pos: Dict):
        """Update position state from exchange data"""
        # Get current state
        state = self.get_position_state(symbol)
        if not state:
            # Position exists on exchange but not in our tracking - create it
            self._create_position_from_exchange(symbol, ex_pos)
            return

        # Update exchange data (source of truth)
        state.exchange_contracts = ex_pos.get('contracts', 0)
        state.exchange_entry_price = ex_pos.get('entryPrice', ex_pos.get('avgPrice', 0))
        state.exchange_unrealized_pnl = ex_pos.get('unrealizedPnl', 0)
        state.exchange_mark_price = ex_pos.get('markPrice', 0)
        state.exchange_liquidation_price = ex_pos.get('liquidationPrice', 0)

        # Sync core position data with exchange
        state.amount = state.exchange_contracts
        if state.exchange_entry_price > 0:
            state.entry_price = state.exchange_entry_price

        # Update surplus size calculation
        if state.original_size > 0:
            state.surplus_size = max(0, state.amount - state.original_size)

        # Update peak tracking
        current_upnl = state.exchange_unrealized_pnl
        if current_upnl > state.peak_upnl:
            state.peak_upnl = current_upnl
            state.peak_upnl_timestamp = datetime.now(timezone.utc).isoformat()

        # Update peak price for ATR trailing
        current_price = state.exchange_mark_price
        if state.side == 'buy' and current_price > state.peak_price:
            state.peak_price = current_price
        elif state.side == 'sell' and (state.peak_price == 0 or current_price < state.peak_price):
            state.peak_price = current_price

        # Update sync metadata
        state.last_sync_time = datetime.now(timezone.utc).isoformat()
        state.sync_status = SyncStatus.SYNCED.value
        state.version += 1

        # Save to Redis
        self._save_position_state(state)

        # Update local cache
        self._position_cache[symbol] = state

    def _create_position_from_exchange(self, symbol: str, ex_pos: Dict):
        """Create new position state from exchange data"""
        now = datetime.now(timezone.utc).isoformat()

        # Determine side
        side = 'buy' if ex_pos.get('side', 'long') == 'long' else 'sell'

        # Create new state
        state = PositionLifecycleState(
            symbol=symbol,
            entry_price=ex_pos.get('entryPrice', ex_pos.get('avgPrice', 0)),
            amount=ex_pos.get('contracts', 0),
            side=side,
            leverage=ex_pos.get('leverage', 1),
            opened_at=now,
            exchange_contracts=ex_pos.get('contracts', 0),
            exchange_entry_price=ex_pos.get('entryPrice', ex_pos.get('avgPrice', 0)),
            exchange_unrealized_pnl=ex_pos.get('unrealizedPnl', 0),
            exchange_mark_price=ex_pos.get('markPrice', 0),
            exchange_liquidation_price=ex_pos.get('liquidationPrice', 0),
            original_size=ex_pos.get('contracts', 0),
            peak_price=ex_pos.get('markPrice', 0),
            position_open_time=now,
            last_sync_time=now,
            sync_status=SyncStatus.SYNCED.value,
            version=1
        )

        # Save to Redis
        self._save_position_state(state)

        # Update local cache
        self._position_cache[symbol] = state

        logger.info(f"Created new position state: {symbol}")

    def _handle_position_closed(self, symbol: str):
        """Handle position that was closed on exchange"""
        # Get final state
        state = self.get_position_state(symbol)

        if state:
            # Archive the position state
            self._archive_position_state(state)

        # Remove from active tracking
        self._remove_position_state(symbol)

        # Add to cooldown
        self._add_to_cooldown(symbol)

        # Remove from local cache
        self._position_cache.pop(symbol, None)

        logger.info(f"Position closed and archived: {symbol}")

    def _save_position_state(self, state: PositionLifecycleState):
        """Save position state to Redis atomically"""
        key = f"{self.POSITION_KEY}{state.symbol}"
        try:
            # Use Redis transaction for atomic update
            pipe = self.redis_client.pipeline()
            pipe.set(key, json.dumps(state.to_dict()))
            pipe.expire(key, 86400)  # 24 hour expiry
            pipe.execute()
        except Exception as e:
            logger.error(f"Failed to save position state {state.symbol}: {e}")
            raise

    def _remove_position_state(self, symbol: str):
        """Remove position state from Redis"""
        key = f"{self.POSITION_KEY}{symbol}"
        try:
            self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"Failed to remove position state {symbol}: {e}")

    def _archive_position_state(self, state: PositionLifecycleState):
        """Archive closed position state for historical reference"""
        archive_key = f"{self.KEY_PREFIX}archive:{state.symbol}:{int(time.time())}"
        try:
            state.sync_status = "CLOSED"
            self.redis_client.set(archive_key, json.dumps(state.to_dict()))
            self.redis_client.expire(archive_key, 604800)  # 7 day retention
        except Exception as e:
            logger.error(f"Failed to archive position state {state.symbol}: {e}")

    def _add_to_cooldown(self, symbol: str):
        """Add symbol to cooldown tracking"""
        expiry = time.time() + self.cooldown_duration
        key = f"{self.COOLDOWN_KEY}{symbol}"
        try:
            self.redis_client.set(key, str(expiry))
            self.redis_client.expire(key, self.cooldown_duration + 60)
            self._cooldown_cache[symbol] = expiry
        except Exception as e:
            logger.error(f"Failed to add cooldown for {symbol}: {e}")

    def is_in_cooldown(self, symbol: str) -> Tuple[bool, float]:
        """
        Check if symbol is in cooldown period

        Returns:
            Tuple of (is_in_cooldown, remaining_seconds)
        """
        # Check local cache first
        if symbol in self._cooldown_cache:
            remaining = self._cooldown_cache[symbol] - time.time()
            if remaining > 0:
                return True, remaining
            else:
                del self._cooldown_cache[symbol]

        # Check Redis
        key = f"{self.COOLDOWN_KEY}{symbol}"
        try:
            expiry_str = self.redis_client.get(key)
            if expiry_str:
                expiry = float(expiry_str)
                remaining = expiry - time.time()
                if remaining > 0:
                    self._cooldown_cache[symbol] = expiry
                    return True, remaining
                else:
                    self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"Failed to check cooldown for {symbol}: {e}")

        return False, 0

    def get_position_state(self, symbol: str) -> Optional[PositionLifecycleState]:
        """
        Get position state from cache or Redis

        Args:
            symbol: Trading symbol

        Returns:
            PositionLifecycleState or None
        """
        # Check local cache first
        if symbol in self._position_cache:
            state = self._position_cache[symbol]
            # Check if stale
            if state.last_sync_time:
                sync_time = datetime.fromisoformat(state.last_sync_time.replace('Z', '+00:00'))
                age = (datetime.now(timezone.utc) - sync_time).total_seconds()
                if age < self.stale_threshold:
                    return state

        # Fetch from Redis
        key = f"{self.POSITION_KEY}{symbol}"
        try:
            data = self.redis_client.get(key)
            if data:
                state = PositionLifecycleState.from_dict(json.loads(data))
                self._position_cache[symbol] = state
                return state
        except Exception as e:
            logger.error(f"Failed to get position state {symbol}: {e}")

        return None

    def get_all_position_states(self) -> Dict[str, PositionLifecycleState]:
        """Get all active position states"""
        symbols = self._get_all_tracked_symbols()
        states = {}
        for symbol in symbols:
            state = self.get_position_state(symbol)
            if state:
                states[symbol] = state
        return states

    # ==================== State Update Methods ====================

    def update_averaging_state(self, symbol: str, steps: int,
                               multipliers: List[float] = None,
                               last_price: float = None,
                               fibonacci_config: Dict = None):
        """Update averaging state for a position"""
        state = self.get_position_state(symbol)
        if not state:
            logger.warning(f"Cannot update averaging state - position not found: {symbol}")
            return False

        state.averaging_steps = steps
        if multipliers:
            state.averaging_multipliers = multipliers
        if last_price:
            state.last_averaging_price = last_price
            state.last_averaging_time = datetime.now(timezone.utc).isoformat()
        if fibonacci_config:
            state.fibonacci_config = fibonacci_config

        state.version += 1
        self._save_position_state(state)
        self._position_cache[symbol] = state

        logger.info(f"Updated averaging state for {symbol}: steps={steps}")
        return True

    def update_surplus_dump_state(self, symbol: str, stage: int,
                                  original_size: float = None):
        """Update surplus dump state for a position"""
        state = self.get_position_state(symbol)
        if not state:
            logger.warning(f"Cannot update surplus dump state - position not found: {symbol}")
            return False

        state.surplus_dump_stage = stage
        if original_size is not None:
            state.original_size = original_size

        # Recalculate surplus size
        state.surplus_size = max(0, state.amount - state.original_size)

        state.version += 1
        self._save_position_state(state)
        self._position_cache[symbol] = state

        logger.info(f"Updated surplus dump state for {symbol}: stage={stage}")
        return True

    def update_peak_upnl(self, symbol: str, peak: float):
        """Update peak UPNL for a position"""
        state = self.get_position_state(symbol)
        if not state:
            return False

        if peak > state.peak_upnl:
            state.peak_upnl = peak
            state.peak_upnl_timestamp = datetime.now(timezone.utc).isoformat()
            state.version += 1
            self._save_position_state(state)
            self._position_cache[symbol] = state

        return True

    def update_partial_close_state(self, symbol: str, stage: int,
                                   executed: List[bool] = None):
        """Update partial close ladder state"""
        state = self.get_position_state(symbol)
        if not state:
            return False

        state.partial_close_stage = stage
        if executed:
            state.partial_close_executed = executed

        state.version += 1
        self._save_position_state(state)
        self._position_cache[symbol] = state

        return True

    def update_atr_stop_state(self, symbol: str, stop_price: float,
                              atr_value: float, peak_price: float = None,
                              trailing_active: bool = None):
        """Update ATR stop loss state"""
        state = self.get_position_state(symbol)
        if not state:
            return False

        state.atr_stop_price = stop_price
        state.atr_value = atr_value
        if peak_price is not None:
            state.peak_price = peak_price
        if trailing_active is not None:
            state.trailing_stop_active = trailing_active

        state.version += 1
        self._save_position_state(state)
        self._position_cache[symbol] = state

        return True

    def update_zone(self, symbol: str, zone: str):
        """Update position zone"""
        state = self.get_position_state(symbol)
        if not state:
            return False

        old_zone = state.current_zone
        state.current_zone = zone
        state.version += 1
        self._save_position_state(state)
        self._position_cache[symbol] = state

        if old_zone != zone:
            logger.info(f"Zone transition for {symbol}: {old_zone} -> {zone}")

        return True

    # ==================== Conversion Methods ====================

    def to_legacy_format(self) -> Dict[str, Dict]:
        """
        Convert current state to legacy format for backward compatibility

        Returns:
            Dict with legacy format dictionaries
        """
        states = self.get_all_position_states()

        active_positions = {}
        position_zones = {}
        averaging_steps = {}
        peak_upnl = {}
        peak_upnl_timestamps = {}
        surplus_dump_stage = {}
        original_sizes = {}
        position_multipliers = {}
        fibonacci_configs = {}

        for symbol, state in states.items():
            active_positions[symbol] = {
                'entry_price': state.entry_price,
                'amount': state.amount,
                'side': state.side,
                'leverage': state.leverage,
                'opened_at': state.opened_at
            }
            position_zones[symbol] = state.current_zone
            averaging_steps[symbol] = state.averaging_steps
            peak_upnl[symbol] = state.peak_upnl
            peak_upnl_timestamps[symbol] = state.peak_upnl_timestamp
            surplus_dump_stage[symbol] = state.surplus_dump_stage
            original_sizes[symbol] = state.original_size
            position_multipliers[symbol] = state.averaging_multipliers
            if state.fibonacci_config:
                fibonacci_configs[symbol] = state.fibonacci_config

        return {
            'active_positions': active_positions,
            'position_zones': position_zones,
            'averaging_steps': averaging_steps,
            'peak_upnl': peak_upnl,
            'peak_upnl_timestamps': peak_upnl_timestamps,
            'surplus_dump_stage': surplus_dump_stage,
            'original_sizes': original_sizes,
            'position_multipliers': position_multipliers,
            'fibonacci_configs': fibonacci_configs
        }

    def from_legacy_format(self, legacy_data: Dict):
        """
        Import state from legacy format

        Args:
            legacy_data: Dict with legacy format dictionaries
        """
        active_positions = legacy_data.get('active_positions', {})
        position_zones = legacy_data.get('position_zones', {})
        averaging_steps = legacy_data.get('averaging_steps', {})
        peak_upnl = legacy_data.get('peak_upnl', {})
        peak_upnl_timestamps = legacy_data.get('peak_upnl_timestamps', {})
        surplus_dump_stage = legacy_data.get('surplus_dump_stage', {})
        original_sizes = legacy_data.get('original_sizes', {})
        position_multipliers = legacy_data.get('position_multipliers', {})
        fibonacci_configs = legacy_data.get('fibonacci_configs', {})

        for symbol, pos_data in active_positions.items():
            state = PositionLifecycleState(
                symbol=symbol,
                entry_price=pos_data.get('entry_price', 0),
                amount=pos_data.get('amount', 0),
                side=pos_data.get('side', 'buy'),
                leverage=pos_data.get('leverage', 1),
                opened_at=pos_data.get('opened_at', ''),
                averaging_steps=averaging_steps.get(symbol, 0),
                averaging_multipliers=position_multipliers.get(symbol, []),
                fibonacci_config=fibonacci_configs.get(symbol),
                surplus_dump_stage=surplus_dump_stage.get(symbol, 0),
                original_size=original_sizes.get(symbol, pos_data.get('amount', 0)),
                peak_upnl=peak_upnl.get(symbol, 0),
                peak_upnl_timestamp=peak_upnl_timestamps.get(symbol),
                current_zone=position_zones.get(symbol, 'NEUTRAL'),
                last_sync_time=datetime.now(timezone.utc).isoformat(),
                sync_status=SyncStatus.PENDING.value,
                version=1
            )

            self._save_position_state(state)
            self._position_cache[symbol] = state

        logger.info(f"Imported {len(active_positions)} positions from legacy format")

    # ==================== Diagnostics ====================

    def get_sync_status(self) -> Dict:
        """Get current sync status and diagnostics"""
        states = self.get_all_position_states()

        synced = sum(1 for s in states.values() if s.sync_status == SyncStatus.SYNCED.value)
        pending = sum(1 for s in states.values() if s.sync_status == SyncStatus.PENDING.value)
        stale = sum(1 for s in states.values() if s.sync_status == SyncStatus.STALE.value)
        errors = sum(1 for s in states.values() if s.sync_status == SyncStatus.ERROR.value)

        # Get cooldown count
        cooldown_keys = self.redis_client.keys(f"{self.COOLDOWN_KEY}*")

        return {
            'total_positions': len(states),
            'synced': synced,
            'pending': pending,
            'stale': stale,
            'errors': errors,
            'cooldown_symbols': len(cooldown_keys),
            'last_sync_time': self._last_sync_time,
            'sync_interval': self.sync_interval,
            'recent_errors': self._sync_errors[-10:] if self._sync_errors else []
        }

    def force_full_sync(self) -> Dict:
        """Force a full synchronization with exchange"""
        logger.info("Forcing full sync with exchange")

        # Clear local cache
        self._position_cache.clear()

        # Perform sync
        return self.sync_with_exchange_sync()
