"""
Live Positions Registry with Zone Management
Central nervous system for all position tracking and state management
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum
import redis.asyncio as redis
import structlog
from dataclasses import dataclass, asdict

logger = structlog.get_logger(__name__)

class PositionZone(Enum):
    """Position zones based on UPNL thresholds"""
    NEUTRAL = "neutral"
    AVERAGING = "averaging"
    SURPLUS_DUMP = "surplus_dump"
    PROFIT_TAKING = "profit_taking"
    STOP_LOSS = "stop_loss"

@dataclass
class AveragingStep:
    """Record of each averaging action"""
    step_number: int
    price: float
    quantity: float
    order_id: str
    timestamp: datetime
    upnl_at_step: float
    
@dataclass
class PositionParams:
    """Customizable parameters per position"""
    averaging_threshold: float = -0.15  # Default -$0.15
    neutral_upper: float = 0.15  # Default +$0.15
    profit_threshold: float = 0.30  # 30% profit target
    stop_loss: float = -1.00  # -$1.00 stop loss
    max_averaging_steps: int = 5
    surplus_dump_85: float = 0.85  # Dump at 85% of peak
    surplus_dump_50: float = 0.50  # Dump rest at 50% of peak
    averaging_multiplier: List[float] = None  # [1.0, 2.0, 3.0] for exponential
    
    def __post_init__(self):
        if self.averaging_multiplier is None:
            self.averaging_multiplier = [1.0, 2.0, 3.0, 4.0, 5.0]

@dataclass
class Position:
    """Complete position state and history"""
    # Core identifiers
    position_id: str
    symbol: str
    direction: str  # 'long' or 'short'
    
    # Entry data
    initial_entry_price: float
    initial_quantity: float
    initial_order_id: str
    entry_timestamp: datetime
    
    # Current state
    current_quantity: float
    weighted_avg_price: float
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    current_zone: PositionZone = PositionZone.NEUTRAL
    
    # Averaging data
    averaging_steps_taken: int = 0
    averaging_steps: List[AveragingStep] = None
    surplus_size: float = 0.0  # Size gained through averaging
    
    # Risk metrics
    max_delta_entry: float = 0.0  # Max drawdown from entry
    max_delta_avg: float = 0.0  # Max drawdown from average
    peak_upnl: float = 0.0  # Peak profit for surplus dump
    
    # Management data
    is_manual: bool = False
    method_used: str = "zone_based_v1"
    custom_params: PositionParams = None
    
    # Exchange data
    exchange: str = "bitget"
    margin_mode: str = "isolated"
    leverage: int = 20
    margin_used: float = 0.0
    
    def __post_init__(self):
        if self.averaging_steps is None:
            self.averaging_steps = []
        if self.custom_params is None:
            self.custom_params = PositionParams()
            
    def to_dict(self) -> Dict:
        """Convert to dictionary for Redis storage"""
        # Start with basic fields only, not the full asdict
        data = {
            'position_id': self.position_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'initial_entry_price': str(self.initial_entry_price),
            'initial_quantity': str(self.initial_quantity),
            'initial_order_id': self.initial_order_id,
            'entry_timestamp': self.entry_timestamp.isoformat(),
            'current_quantity': str(self.current_quantity),
            'weighted_avg_price': str(self.weighted_avg_price),
            'current_price': str(self.current_price),
            'unrealized_pnl': str(self.unrealized_pnl),
            'realized_pnl': str(self.realized_pnl),
            'current_zone': self.current_zone.value,
            'averaging_steps_taken': str(self.averaging_steps_taken),
            'averaging_steps': json.dumps([asdict(s) for s in self.averaging_steps] if self.averaging_steps else []),
            'surplus_size': str(self.surplus_size),
            'max_delta_entry': str(self.max_delta_entry),
            'max_delta_avg': str(self.max_delta_avg),
            'peak_upnl': str(self.peak_upnl),
            'is_manual': str(self.is_manual),
            'method_used': self.method_used,
            'custom_params': json.dumps(asdict(self.custom_params) if self.custom_params else {}),
            'exchange': self.exchange,
            'margin_mode': self.margin_mode,
            'leverage': str(self.leverage),
            'margin_used': str(self.margin_used)
        }
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Position':
        """Create from Redis data"""
        # Parse complex fields
        parsed_data = {
            'position_id': data['position_id'],
            'symbol': data['symbol'],
            'direction': data['direction'],
            'initial_entry_price': float(data['initial_entry_price']),
            'initial_quantity': float(data['initial_quantity']),
            'initial_order_id': data['initial_order_id'],
            'entry_timestamp': datetime.fromisoformat(data['entry_timestamp']),
            'current_quantity': float(data['current_quantity']),
            'weighted_avg_price': float(data['weighted_avg_price']),
            'current_price': float(data.get('current_price', 0)),
            'unrealized_pnl': float(data.get('unrealized_pnl', 0)),
            'realized_pnl': float(data.get('realized_pnl', 0)),
            'current_zone': PositionZone(data.get('current_zone', 'neutral')),
            'averaging_steps_taken': int(data.get('averaging_steps_taken', 0)),
            'averaging_steps': [
                AveragingStep(**s) for s in json.loads(data.get('averaging_steps', '[]'))
            ],
            'surplus_size': float(data.get('surplus_size', 0)),
            'max_delta_entry': float(data.get('max_delta_entry', 0)),
            'max_delta_avg': float(data.get('max_delta_avg', 0)),
            'peak_upnl': float(data.get('peak_upnl', 0)),
            'is_manual': data.get('is_manual', 'False') == 'True',
            'method_used': data.get('method_used', 'zone_based_v1'),
            'custom_params': PositionParams(**json.loads(data.get('custom_params', '{}'))),
            'exchange': data.get('exchange', 'bitget'),
            'margin_mode': data.get('margin_mode', 'isolated'),
            'leverage': int(data.get('leverage', 20)),
            'margin_used': float(data.get('margin_used', 0))
        }
                
        return cls(**parsed_data)

class LivePositionsRegistry:
    """
    Central registry for all live positions with zone management
    Uses Redis for sub-millisecond access and persistence
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self.positions_key = "positions:active"
        self.position_prefix = "position:"
        self.events_prefix = "events:"
        
    async def connect(self):
        """Initialize Redis connection"""
        self.redis_client = await redis.from_url(
            self.redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        logger.info("Connected to Redis for positions registry")
        
    async def disconnect(self):
        """Close Redis connection"""
        if self.redis_client:
            await self.redis_client.close()
            
    async def add_position(self, position: Position) -> bool:
        """Add new position to registry"""
        try:
            # Store position data
            key = f"{self.position_prefix}{position.position_id}"
            await self.redis_client.hset(key, mapping=position.to_dict())
            
            # Add to active positions set
            await self.redis_client.sadd(self.positions_key, position.position_id)
            
            # Log event
            await self._log_event(position.position_id, "position_opened", {
                "symbol": position.symbol,
                "direction": position.direction,
                "quantity": position.initial_quantity,
                "price": position.initial_entry_price
            })
            
            logger.info(f"Added position {position.position_id} to registry")
            return True
            
        except Exception as e:
            logger.error(f"Failed to add position: {e}")
            return False
            
    async def update_position(self, position_id: str, updates: Dict) -> bool:
        """Update position fields"""
        try:
            key = f"{self.position_prefix}{position_id}"
            
            # Convert zone enum if present
            if 'current_zone' in updates and isinstance(updates['current_zone'], PositionZone):
                updates['current_zone'] = updates['current_zone'].value
                
            await self.redis_client.hset(key, mapping=updates)
            
            # Log significant changes
            if 'current_zone' in updates:
                await self._log_event(position_id, "zone_change", updates)
                
            return True
            
        except Exception as e:
            logger.error(f"Failed to update position {position_id}: {e}")
            return False
            
    async def get_position(self, position_id: str) -> Optional[Position]:
        """Get single position by ID"""
        try:
            key = f"{self.position_prefix}{position_id}"
            data = await self.redis_client.hgetall(key)
            
            if not data:
                return None
                
            return Position.from_dict(data)
            
        except Exception as e:
            logger.error(f"Failed to get position {position_id}: {e}")
            return None
            
    async def get_all_positions(self) -> List[Position]:
        """Get all active positions"""
        try:
            position_ids = await self.redis_client.smembers(self.positions_key)
            positions = []
            
            for pid in position_ids:
                pos = await self.get_position(pid)
                if pos:
                    positions.append(pos)
                    
            return positions
            
        except Exception as e:
            logger.error(f"Failed to get all positions: {e}")
            return []
            
    async def get_position_by_symbol(self, symbol: str) -> Optional[Position]:
        """Get position by symbol"""
        try:
            positions = await self.get_all_positions()
            for pos in positions:
                if pos.symbol.upper() == symbol.upper():
                    return pos
            return None
        except Exception as e:
            logger.error(f"Failed to get position by symbol {symbol}: {e}")
            return None
            
    async def update_zone(self, position: Position) -> PositionZone:
        """
        Determine and update position zone based on UPNL
        Core state machine logic
        """
        previous_zone = position.current_zone
        params = position.custom_params
        upnl = position.unrealized_pnl
        
        # Stop Loss Check (highest priority)
        if upnl <= params.stop_loss:
            position.current_zone = PositionZone.STOP_LOSS
            
        # Averaging Zone
        elif upnl <= params.averaging_threshold:
            position.current_zone = PositionZone.AVERAGING
            
        # Surplus Dump Zone (only if we have averaging steps)
        elif upnl > params.neutral_upper and position.averaging_steps_taken > 0:
            position.current_zone = PositionZone.SURPLUS_DUMP
            # Track peak UPNL
            if upnl > position.peak_upnl:
                position.peak_upnl = upnl
                
        # Profit Taking Zone (no averaging history)
        elif upnl > params.profit_threshold and position.averaging_steps_taken == 0:
            position.current_zone = PositionZone.PROFIT_TAKING
            
        # Neutral Zone
        else:
            position.current_zone = PositionZone.NEUTRAL
            
        # Log zone transition
        if previous_zone != position.current_zone:
            await self._log_event(position.position_id, "zone_transition", {
                "from": previous_zone.value,
                "to": position.current_zone.value,
                "upnl": upnl
            })
            
            # Update in Redis
            await self.update_position(position.position_id, {
                "current_zone": position.current_zone,
                "peak_upnl": position.peak_upnl
            })
            
        return position.current_zone
        
    async def calculate_averaging_size(self, position: Position, step: int) -> float:
        """
        Calculate size for next averaging step
        Uses exponential increase based on configuration
        """
        if step >= len(position.custom_params.averaging_multiplier):
            return 0.0  # Max steps reached
            
        multiplier = position.custom_params.averaging_multiplier[step]
        
        if step == 0:
            # First averaging: multiplier of initial size
            return position.initial_quantity * multiplier
        else:
            # Subsequent: multiplier of total current size
            return position.current_quantity * multiplier
            
    async def record_averaging_step(self, position: Position, price: float, 
                                   quantity: float, order_id: str) -> bool:
        """Record a new averaging step"""
        try:
            step = AveragingStep(
                step_number=position.averaging_steps_taken + 1,
                price=price,
                quantity=quantity,
                order_id=order_id,
                timestamp=datetime.now(),
                upnl_at_step=position.unrealized_pnl
            )
            
            position.averaging_steps.append(step)
            position.averaging_steps_taken += 1
            position.surplus_size += quantity
            
            # Recalculate weighted average
            total_value = (position.weighted_avg_price * position.current_quantity) + (price * quantity)
            position.current_quantity += quantity
            position.weighted_avg_price = total_value / position.current_quantity
            
            # Update in Redis
            await self.update_position(position.position_id, {
                "averaging_steps": json.dumps([asdict(s) for s in position.averaging_steps]),
                "averaging_steps_taken": position.averaging_steps_taken,
                "surplus_size": position.surplus_size,
                "current_quantity": position.current_quantity,
                "weighted_avg_price": position.weighted_avg_price
            })
            
            await self._log_event(position.position_id, "averaging_executed", {
                "step": position.averaging_steps_taken,
                "price": price,
                "quantity": quantity,
                "new_avg": position.weighted_avg_price
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to record averaging step: {e}")
            return False
            
    async def calculate_surplus_dump(self, position: Position) -> Optional[float]:
        """
        Calculate how much surplus to dump based on UPNL decline from peak
        Returns quantity to sell or None
        """
        if position.current_zone != PositionZone.SURPLUS_DUMP or position.surplus_size <= 0:
            return None
            
        params = position.custom_params
        upnl = position.unrealized_pnl
        peak = position.peak_upnl
        
        # Check if we've dropped to 85% of peak
        if upnl <= peak * params.surplus_dump_85 and position.surplus_size > 0:
            # Dump 50% of surplus
            dump_quantity = position.surplus_size * 0.5
            
            # Check if we've dropped to 50% of peak (adjusted for new size)
            # This is more aggressive dumping
            if upnl <= peak * params.surplus_dump_50:
                # Dump all remaining surplus
                dump_quantity = position.surplus_size
                
            return dump_quantity
            
        return None
        
    async def record_surplus_dump(self, position: Position, quantity: float, 
                                 price: float, order_id: str) -> bool:
        """Record surplus dump action"""
        try:
            position.surplus_size -= quantity
            position.current_quantity -= quantity
            
            # If all surplus dumped, reset counters
            if position.surplus_size <= 0.001:  # Small threshold for float comparison
                position.averaging_steps_taken = 0
                position.peak_upnl = 0
                position.surplus_size = 0
                # Move back to neutral zone
                position.current_zone = PositionZone.NEUTRAL
                
            # Update in Redis
            await self.update_position(position.position_id, {
                "surplus_size": position.surplus_size,
                "current_quantity": position.current_quantity,
                "averaging_steps_taken": position.averaging_steps_taken,
                "peak_upnl": position.peak_upnl,
                "current_zone": position.current_zone
            })
            
            await self._log_event(position.position_id, "surplus_dump", {
                "quantity": quantity,
                "price": price,
                "remaining_surplus": position.surplus_size
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to record surplus dump: {e}")
            return False
            
    async def update_risk_metrics(self, position: Position) -> None:
        """Update max delta tracking"""
        if position.direction == "long":
            delta_entry = position.current_price - position.initial_entry_price
            delta_avg = position.current_price - position.weighted_avg_price
        else:  # short
            delta_entry = position.initial_entry_price - position.current_price
            delta_avg = position.weighted_avg_price - position.current_price
            
        # Track maximum negative deltas
        if delta_entry < position.max_delta_entry:
            position.max_delta_entry = delta_entry
            
        if delta_avg < position.max_delta_avg:
            position.max_delta_avg = delta_avg
            
        await self.update_position(position.position_id, {
            "max_delta_entry": position.max_delta_entry,
            "max_delta_avg": position.max_delta_avg
        })
        
    async def archive_position(self, position_id: str) -> bool:
        """Move closed position to historical storage"""
        try:
            position = await self.get_position(position_id)
            if not position:
                return False
                
            # Log to historical database (TimescaleDB integration would go here)
            await self._log_event(position_id, "position_closed", {
                "final_pnl": position.realized_pnl + position.unrealized_pnl,
                "total_trades": position.averaging_steps_taken + 1
            })
            
            # Remove from active set
            await self.redis_client.srem(self.positions_key, position_id)
            
            # Keep data for 24 hours for analysis
            key = f"{self.position_prefix}{position_id}"
            await self.redis_client.expire(key, 86400)
            
            logger.info(f"Archived position {position_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to archive position: {e}")
            return False
            
    async def _log_event(self, position_id: str, event_type: str, data: Dict) -> None:
        """Log position events for audit trail"""
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "data": data
        }
        
        # Store in Redis stream
        stream_key = f"{self.events_prefix}{position_id}"
        await self.redis_client.xadd(stream_key, event)
        
        # Trim to last 1000 events
        await self.redis_client.xtrim(stream_key, maxlen=1000, approximate=True)