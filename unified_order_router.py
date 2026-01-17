#!/usr/bin/env python3
"""
AI-XYZ Unified Order Router V1.0.0
===================================

Central gateway for all trading systems to route orders through.
Prevents conflicts, tracks position ownership, manages lifecycle.

ARCHITECTURE:
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  Main Trading   │  │  Quick Scalper  │  │  Other Systems  │
│     System      │  │       V3        │  │                 │
└────────┬────────┘  └────────┬────────┘  └────────┬────────┘
         │                    │                    │
         └────────────────────┼────────────────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │   UNIFIED ORDER ROUTER │
                 │   - Position Registry  │
                 │   - Conflict Detection │
                 │   - Ownership Tracking │
                 └────────────┬───────────┘
                              │
                              ▼
                 ┌────────────────────────┐
                 │    BITGET EXCHANGE     │
                 └────────────────────────┘

REDIS SCHEMA:
- router:position:{symbol} - Hash with position details
- router:locks:{symbol} - Position lock for atomic operations
- router:orders:pending - List of pending order requests
- router:orders:history - Recent order history

DESIGN: Claude (Opus 4.5) + Grok Consortium
DATE: January 17, 2026
"""

import ccxt
import redis
import json
import time
import os
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from enum import Enum
from dotenv import load_dotenv

load_dotenv()


# ========== ENUMS ==========

class SystemType(Enum):
    """Trading system identifiers"""
    MAIN_TRADING = "main_trading"
    QUICK_SCALPER = "quick_scalper"
    GRID_DCA = "grid_dca"
    MANUAL = "manual"


class OrderAction(Enum):
    """Order action types"""
    OPEN = "open"
    CLOSE = "close"
    AVERAGE = "average"
    PARTIAL_CLOSE = "partial_close"


class ConflictType(Enum):
    """Types of order conflicts"""
    NONE = "none"
    SYMBOL_LOCKED = "symbol_locked"
    OPPOSITE_DIRECTION = "opposite_direction"
    SYSTEM_NOT_OWNER = "system_not_owner"
    MAX_POSITIONS_REACHED = "max_positions_reached"
    INSUFFICIENT_MARGIN = "insufficient_margin"


# ========== DATA CLASSES ==========

@dataclass
class OrderRequest:
    """Order request from a trading system"""
    request_id: str
    system: str
    symbol: str
    action: str  # open, close, average, partial_close
    side: str    # long, short
    size_usd: float
    price: Optional[float] = None
    leverage: int = 10
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None
    metadata: Optional[Dict] = None
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


@dataclass
class OrderResponse:
    """Response to an order request"""
    request_id: str
    status: str  # accepted, rejected, pending
    conflict: Optional[str] = None
    message: str = ""
    position_id: Optional[str] = None
    order_id: Optional[str] = None
    fill_price: Optional[float] = None


@dataclass
class Position:
    """Position in the global registry"""
    symbol: str
    owner_system: str
    side: str
    size: float
    entry_price: float
    leverage: int
    opened_at: str
    last_updated: str
    averaging_steps: int = 0
    tp_price: Optional[float] = None
    sl_price: Optional[float] = None
    metadata: Optional[Dict] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        return cls(**data)


# ========== CONFIGURATION ==========

class RouterConfig:
    """Configuration for the Unified Order Router"""

    # Redis keys
    POSITION_KEY_PREFIX = "router:position:"
    LOCK_KEY_PREFIX = "router:lock:"
    ORDERS_PENDING = "router:orders:pending"
    ORDERS_HISTORY = "router:orders:history"
    STATS_KEY = "router:stats"

    # Limits
    MAX_GLOBAL_POSITIONS = 25
    MAX_POSITIONS_PER_SYSTEM = {
        SystemType.MAIN_TRADING.value: 20,
        SystemType.QUICK_SCALPER.value: 6,
        SystemType.GRID_DCA.value: 10,
    }

    # Lock settings
    LOCK_TIMEOUT_SECONDS = 30
    LOCK_RETRY_DELAY = 0.1

    # Conflict resolution
    ALLOW_SAME_DIRECTION_STACKING = True  # Multiple systems can add to same direction
    OWNER_ONLY_CLOSE = False  # If True, only owner can close position


# ========== UNIFIED ORDER ROUTER ==========

class UnifiedOrderRouter:
    """
    Central order routing and position management.

    All trading systems should use this to:
    - Open positions (checks for conflicts)
    - Close positions (checks ownership)
    - Average into positions (updates registry)
    - Query positions (global view)
    """

    def __init__(self):
        # Exchange connection
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {'defaultType': 'swap'}
        })

        # Redis connection
        self.redis = redis.Redis(
            host=os.getenv('REDIS_HOST', 'redis'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=2,  # Use separate DB for router
            decode_responses=True
        )

        # Stats
        self.stats = {
            'orders_processed': 0,
            'orders_accepted': 0,
            'orders_rejected': 0,
            'conflicts_detected': 0
        }

        print("=" * 65)
        print("Unified Order Router V1.0.0")
        print("=" * 65)
        self._sync_exchange_positions()

    # ========== POSITION LOCKING ==========

    def _acquire_lock(self, symbol: str, timeout: int = 30) -> bool:
        """Acquire a lock on a symbol for atomic operations"""
        lock_key = f"{RouterConfig.LOCK_KEY_PREFIX}{symbol}"
        lock_id = f"{os.getpid()}:{threading.current_thread().ident}"

        end_time = time.time() + timeout
        while time.time() < end_time:
            if self.redis.set(lock_key, lock_id, nx=True, ex=RouterConfig.LOCK_TIMEOUT_SECONDS):
                return True
            time.sleep(RouterConfig.LOCK_RETRY_DELAY)
        return False

    def _release_lock(self, symbol: str):
        """Release a symbol lock"""
        lock_key = f"{RouterConfig.LOCK_KEY_PREFIX}{symbol}"
        self.redis.delete(lock_key)

    # ========== POSITION REGISTRY ==========

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position from registry"""
        key = f"{RouterConfig.POSITION_KEY_PREFIX}{symbol}"
        data = self.redis.hgetall(key)
        if not data:
            return None

        # Convert types
        data['size'] = float(data.get('size', 0))
        data['entry_price'] = float(data.get('entry_price', 0))
        data['leverage'] = int(data.get('leverage', 10))
        data['averaging_steps'] = int(data.get('averaging_steps', 0))
        if data.get('tp_price'):
            data['tp_price'] = float(data['tp_price'])
        if data.get('sl_price'):
            data['sl_price'] = float(data['sl_price'])
        if data.get('metadata'):
            data['metadata'] = json.loads(data['metadata'])

        return Position.from_dict(data)

    def set_position(self, position: Position):
        """Save position to registry"""
        key = f"{RouterConfig.POSITION_KEY_PREFIX}{position.symbol}"
        data = position.to_dict()
        if data.get('metadata'):
            data['metadata'] = json.dumps(data['metadata'])
        self.redis.hset(key, mapping=data)

    def delete_position(self, symbol: str):
        """Remove position from registry"""
        key = f"{RouterConfig.POSITION_KEY_PREFIX}{symbol}"
        self.redis.delete(key)

    def get_all_positions(self) -> Dict[str, Position]:
        """Get all positions in registry"""
        positions = {}
        keys = self.redis.keys(f"{RouterConfig.POSITION_KEY_PREFIX}*")
        for key in keys:
            symbol = key.replace(RouterConfig.POSITION_KEY_PREFIX, "")
            pos = self.get_position(symbol)
            if pos:
                positions[symbol] = pos
        return positions

    def get_positions_by_system(self, system: str) -> Dict[str, Position]:
        """Get positions owned by a specific system"""
        all_positions = self.get_all_positions()
        return {k: v for k, v in all_positions.items() if v.owner_system == system}

    # ========== CONFLICT DETECTION ==========

    def check_conflicts(self, request: OrderRequest) -> Tuple[ConflictType, str]:
        """Check for conflicts before processing order"""

        # Check global position limit
        all_positions = self.get_all_positions()
        if len(all_positions) >= RouterConfig.MAX_GLOBAL_POSITIONS:
            if request.action == OrderAction.OPEN.value:
                return ConflictType.MAX_POSITIONS_REACHED, f"Max global positions ({RouterConfig.MAX_GLOBAL_POSITIONS}) reached"

        # Check per-system limit
        system_positions = self.get_positions_by_system(request.system)
        max_for_system = RouterConfig.MAX_POSITIONS_PER_SYSTEM.get(request.system, 10)
        if len(system_positions) >= max_for_system:
            if request.action == OrderAction.OPEN.value:
                return ConflictType.MAX_POSITIONS_REACHED, f"System {request.system} at max positions ({max_for_system})"

        # Check existing position
        existing = self.get_position(request.symbol)

        if existing:
            # Opening new position but symbol already has one
            if request.action == OrderAction.OPEN.value:
                if existing.side != request.side:
                    return ConflictType.OPPOSITE_DIRECTION, f"Existing {existing.side} position owned by {existing.owner_system}"

                if RouterConfig.ALLOW_SAME_DIRECTION_STACKING:
                    # Allow stacking in same direction - treat as average
                    pass
                else:
                    return ConflictType.SYMBOL_LOCKED, f"Position already exists for {request.symbol}"

            # Closing but not owner
            if request.action in [OrderAction.CLOSE.value, OrderAction.PARTIAL_CLOSE.value]:
                if RouterConfig.OWNER_ONLY_CLOSE and existing.owner_system != request.system:
                    return ConflictType.SYSTEM_NOT_OWNER, f"Position owned by {existing.owner_system}, not {request.system}"

            # Averaging but wrong direction
            if request.action == OrderAction.AVERAGE.value:
                if existing.side != request.side:
                    return ConflictType.OPPOSITE_DIRECTION, f"Cannot average {request.side} into {existing.side} position"

        else:
            # No existing position
            if request.action in [OrderAction.CLOSE.value, OrderAction.AVERAGE.value]:
                return ConflictType.NONE, "No position to close/average"

        return ConflictType.NONE, ""

    # ========== ORDER PROCESSING ==========

    def submit_order(self, request: OrderRequest) -> OrderResponse:
        """Submit an order request"""
        self.stats['orders_processed'] += 1

        # Acquire lock
        if not self._acquire_lock(request.symbol):
            return OrderResponse(
                request_id=request.request_id,
                status="rejected",
                conflict=ConflictType.SYMBOL_LOCKED.value,
                message="Could not acquire symbol lock"
            )

        try:
            # Check conflicts
            conflict, message = self.check_conflicts(request)
            if conflict != ConflictType.NONE:
                self.stats['orders_rejected'] += 1
                self.stats['conflicts_detected'] += 1
                return OrderResponse(
                    request_id=request.request_id,
                    status="rejected",
                    conflict=conflict.value,
                    message=message
                )

            # Execute order based on action
            if request.action == OrderAction.OPEN.value:
                return self._execute_open(request)
            elif request.action == OrderAction.CLOSE.value:
                return self._execute_close(request)
            elif request.action == OrderAction.AVERAGE.value:
                return self._execute_average(request)
            elif request.action == OrderAction.PARTIAL_CLOSE.value:
                return self._execute_partial_close(request)
            else:
                return OrderResponse(
                    request_id=request.request_id,
                    status="rejected",
                    message=f"Unknown action: {request.action}"
                )

        finally:
            self._release_lock(request.symbol)

    def _execute_open(self, request: OrderRequest) -> OrderResponse:
        """Execute an open order"""
        try:
            # Check if adding to existing position
            existing = self.get_position(request.symbol)

            # Set leverage
            try:
                self.exchange.set_leverage(request.leverage, request.symbol)
            except:
                pass

            # Calculate amount
            ticker = self.exchange.fetch_ticker(request.symbol)
            price = ticker['last']
            amount = request.size_usd / price

            # Place order
            side = 'buy' if request.side == 'long' else 'sell'
            order = self.exchange.create_market_order(
                request.symbol, side, amount,
                params={
                    'tradeSide': 'open',
                    'holdSide': request.side,
                    'productType': 'USDT-FUTURES'
                }
            )

            # Calculate TP/SL prices
            tp_price = None
            sl_price = None
            if request.tp_pct:
                if request.side == 'long':
                    tp_price = price * (1 + request.tp_pct / 100)
                else:
                    tp_price = price * (1 - request.tp_pct / 100)
            if request.sl_pct:
                if request.side == 'long':
                    sl_price = price * (1 - request.sl_pct / 100)
                else:
                    sl_price = price * (1 + request.sl_pct / 100)

            # Update or create position in registry
            if existing and existing.side == request.side:
                # Adding to existing - update size and average entry
                new_size = existing.size + amount
                new_entry = (existing.entry_price * existing.size + price * amount) / new_size
                existing.size = new_size
                existing.entry_price = new_entry
                existing.last_updated = datetime.now().isoformat()
                existing.averaging_steps += 1
                self.set_position(existing)
            else:
                # New position
                position = Position(
                    symbol=request.symbol,
                    owner_system=request.system,
                    side=request.side,
                    size=amount,
                    entry_price=price,
                    leverage=request.leverage,
                    opened_at=datetime.now().isoformat(),
                    last_updated=datetime.now().isoformat(),
                    tp_price=tp_price,
                    sl_price=sl_price,
                    metadata=request.metadata
                )
                self.set_position(position)

            self.stats['orders_accepted'] += 1

            print(f"[ROUTER] OPEN {request.side.upper()} {request.symbol} by {request.system}")
            print(f"  Size: {amount:.6f} @ ${price:.4f}")

            return OrderResponse(
                request_id=request.request_id,
                status="accepted",
                message=f"Opened {request.side} position",
                position_id=request.symbol,
                order_id=order.get('id'),
                fill_price=price
            )

        except Exception as e:
            self.stats['orders_rejected'] += 1
            return OrderResponse(
                request_id=request.request_id,
                status="rejected",
                message=f"Order execution failed: {str(e)}"
            )

    def _execute_close(self, request: OrderRequest) -> OrderResponse:
        """Execute a close order"""
        try:
            existing = self.get_position(request.symbol)
            if not existing:
                return OrderResponse(
                    request_id=request.request_id,
                    status="rejected",
                    message="No position to close"
                )

            # Place close order
            side = 'sell' if existing.side == 'long' else 'buy'
            order = self.exchange.create_market_order(
                request.symbol, side, existing.size,
                params={
                    'tradeSide': 'close',
                    'holdSide': existing.side,
                    'productType': 'USDT-FUTURES'
                }
            )

            # Get fill price
            ticker = self.exchange.fetch_ticker(request.symbol)
            fill_price = ticker['last']

            # Calculate PnL
            if existing.side == 'long':
                pnl_pct = (fill_price - existing.entry_price) / existing.entry_price * 100
            else:
                pnl_pct = (existing.entry_price - fill_price) / existing.entry_price * 100

            # Remove from registry
            self.delete_position(request.symbol)
            self.stats['orders_accepted'] += 1

            print(f"[ROUTER] CLOSE {existing.side.upper()} {request.symbol} by {request.system}")
            print(f"  PnL: {pnl_pct:+.2f}%")

            return OrderResponse(
                request_id=request.request_id,
                status="accepted",
                message=f"Closed position, PnL: {pnl_pct:+.2f}%",
                fill_price=fill_price
            )

        except Exception as e:
            # Check if position already closed
            if '22002' in str(e) or 'No position' in str(e):
                self.delete_position(request.symbol)
                return OrderResponse(
                    request_id=request.request_id,
                    status="accepted",
                    message="Position already closed externally"
                )

            self.stats['orders_rejected'] += 1
            return OrderResponse(
                request_id=request.request_id,
                status="rejected",
                message=f"Close failed: {str(e)}"
            )

    def _execute_average(self, request: OrderRequest) -> OrderResponse:
        """Execute an averaging order (add to existing position)"""
        existing = self.get_position(request.symbol)
        if not existing:
            return OrderResponse(
                request_id=request.request_id,
                status="rejected",
                message="No position to average into"
            )

        # Treat as open with existing position
        return self._execute_open(request)

    def _execute_partial_close(self, request: OrderRequest) -> OrderResponse:
        """Execute a partial close order"""
        try:
            existing = self.get_position(request.symbol)
            if not existing:
                return OrderResponse(
                    request_id=request.request_id,
                    status="rejected",
                    message="No position to partially close"
                )

            # Calculate close amount
            ticker = self.exchange.fetch_ticker(request.symbol)
            price = ticker['last']
            close_amount = request.size_usd / price

            if close_amount >= existing.size:
                # Close entire position
                return self._execute_close(request)

            # Place partial close order
            side = 'sell' if existing.side == 'long' else 'buy'
            order = self.exchange.create_market_order(
                request.symbol, side, close_amount,
                params={
                    'tradeSide': 'close',
                    'holdSide': existing.side,
                    'productType': 'USDT-FUTURES'
                }
            )

            # Update position size
            existing.size -= close_amount
            existing.last_updated = datetime.now().isoformat()
            self.set_position(existing)

            self.stats['orders_accepted'] += 1

            print(f"[ROUTER] PARTIAL CLOSE {request.symbol} by {request.system}")
            print(f"  Closed: {close_amount:.6f}, Remaining: {existing.size:.6f}")

            return OrderResponse(
                request_id=request.request_id,
                status="accepted",
                message=f"Partially closed {close_amount:.6f}",
                fill_price=price
            )

        except Exception as e:
            self.stats['orders_rejected'] += 1
            return OrderResponse(
                request_id=request.request_id,
                status="rejected",
                message=f"Partial close failed: {str(e)}"
            )

    # ========== SYNC WITH EXCHANGE ==========

    def _sync_exchange_positions(self):
        """Sync registry with actual exchange positions on startup"""
        try:
            print("[ROUTER] Syncing with exchange positions...")
            positions = self.exchange.fetch_positions()

            for pos in positions:
                if float(pos.get('contracts', 0)) > 0:
                    symbol = pos['symbol']
                    existing = self.get_position(symbol)

                    if not existing:
                        # Position exists on exchange but not in registry
                        # Mark as owned by main_trading (default)
                        side = 'long' if pos.get('side') == 'long' else 'short'
                        position = Position(
                            symbol=symbol,
                            owner_system=SystemType.MAIN_TRADING.value,
                            side=side,
                            size=float(pos['contracts']),
                            entry_price=float(pos.get('entryPrice', 0)),
                            leverage=int(pos.get('leverage', 10)),
                            opened_at=datetime.now().isoformat(),
                            last_updated=datetime.now().isoformat(),
                            metadata={'synced_from_exchange': True}
                        )
                        self.set_position(position)
                        print(f"  Synced: {symbol} ({side})")

            print(f"[ROUTER] Synced {len(self.get_all_positions())} positions")

        except Exception as e:
            print(f"[ROUTER] Sync error: {e}")

    # ========== STATUS ==========

    def get_status(self) -> Dict:
        """Get router status"""
        all_positions = self.get_all_positions()
        by_system = {}
        for pos in all_positions.values():
            system = pos.owner_system
            if system not in by_system:
                by_system[system] = 0
            by_system[system] += 1

        return {
            'total_positions': len(all_positions),
            'positions_by_system': by_system,
            'stats': self.stats
        }


# ========== SINGLETON INSTANCE ==========

_router_instance = None

def get_order_router() -> UnifiedOrderRouter:
    """Get singleton router instance"""
    global _router_instance
    if _router_instance is None:
        _router_instance = UnifiedOrderRouter()
    return _router_instance


# ========== HELPER FUNCTIONS FOR OTHER SYSTEMS ==========

def submit_order(
    system: str,
    symbol: str,
    action: str,
    side: str,
    size_usd: float,
    leverage: int = 10,
    tp_pct: float = None,
    sl_pct: float = None,
    metadata: Dict = None
) -> OrderResponse:
    """
    Convenience function for other systems to submit orders.

    Usage:
        from unified_order_router import submit_order

        response = submit_order(
            system="quick_scalper",
            symbol="BTC/USDT:USDT",
            action="open",
            side="long",
            size_usd=20,
            leverage=10,
            tp_pct=0.15,
            sl_pct=0.08
        )

        if response.status == "accepted":
            print(f"Order filled at {response.fill_price}")
        else:
            print(f"Order rejected: {response.message}")
    """
    router = get_order_router()

    request = OrderRequest(
        request_id=f"{system}_{symbol}_{datetime.now().timestamp()}",
        system=system,
        symbol=symbol,
        action=action,
        side=side,
        size_usd=size_usd,
        leverage=leverage,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        metadata=metadata
    )

    return router.submit_order(request)


def get_position(symbol: str) -> Optional[Position]:
    """Get position from global registry"""
    router = get_order_router()
    return router.get_position(symbol)


def get_all_positions() -> Dict[str, Position]:
    """Get all positions"""
    router = get_order_router()
    return router.get_all_positions()


def can_open_position(system: str, symbol: str, side: str) -> Tuple[bool, str]:
    """Check if a position can be opened without actually opening it"""
    router = get_order_router()

    request = OrderRequest(
        request_id="check",
        system=system,
        symbol=symbol,
        action=OrderAction.OPEN.value,
        side=side,
        size_usd=0  # Dummy value for check
    )

    conflict, message = router.check_conflicts(request)
    return conflict == ConflictType.NONE, message


# ========== MAIN (for testing) ==========

if __name__ == '__main__':
    router = get_order_router()
    status = router.get_status()
    print(f"\nRouter Status:")
    print(f"  Total positions: {status['total_positions']}")
    print(f"  By system: {status['positions_by_system']}")
