"""
Position Management Service - Advanced Zone-Based Position Management
Implements sophisticated position management with zone-based strategies.
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime, timedelta
import asyncio
import numpy as np
import pandas as pd
import json
import redis
import structlog
import uuid

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Position Management Service",
    description="Advanced zone-based position management system",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Redis connection
redis_client = redis.Redis(host='localhost', port=6379, db=3, decode_responses=True)

class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIAL = "PARTIAL"
    PENDING = "PENDING"

class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"
    STOP_LIMIT = "STOP_LIMIT"

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class ZoneType(str, Enum):
    ACCUMULATION = "ACCUMULATION"
    DISTRIBUTION = "DISTRIBUTION"
    PROFIT_TAKING = "PROFIT_TAKING"
    STOP_LOSS = "STOP_LOSS"

class Position(BaseModel):
    id: str
    symbol: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    status: PositionStatus
    zones: List[Dict[str, Any]] = []
    opened_at: datetime
    updated_at: datetime

class Order(BaseModel):
    id: str
    position_id: Optional[str] = None
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: str = "PENDING"
    created_at: datetime

class ZoneBasedPositionManager:
    """Advanced zone-based position management system."""
    
    def __init__(self):
        self.positions: Dict[str, Position] = {}
        self.orders: Dict[str, Order] = {}
        self.zone_strategies = {
            ZoneType.ACCUMULATION: self.accumulation_strategy,
            ZoneType.DISTRIBUTION: self.distribution_strategy,
            ZoneType.PROFIT_TAKING: self.profit_taking_strategy,
            ZoneType.STOP_LOSS: self.stop_loss_strategy
        }
    
    async def create_position(self, symbol: str, quantity: float, entry_price: float) -> Position:
        """Create a new position with zone-based management."""
        position_id = str(uuid.uuid4())
        
        # Define initial zones based on entry price
        zones = self.create_initial_zones(entry_price, quantity)
        
        position = Position(
            id=position_id,
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            current_price=entry_price,
            unrealized_pnl=0.0,
            status=PositionStatus.OPEN,
            zones=zones,
            opened_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self.positions[position_id] = position
        
        # Store in Redis
        await self.store_position(position)
        
        logger.info(f"Created position {position_id} for {symbol}")
        return position
    
    def create_initial_zones(self, entry_price: float, quantity: float) -> List[Dict[str, Any]]:
        """Create initial zone structure for position management."""
        zones = []
        
        # Accumulation zones (below entry for long positions)
        for i in range(3):
            zone_price = entry_price * (1 - (i + 1) * 0.05)  # 5%, 10%, 15% below entry
            zones.append({
                'id': str(uuid.uuid4()),
                'type': ZoneType.ACCUMULATION.value,
                'price': zone_price,
                'quantity': quantity * 0.5,  # Add 50% more at each zone
                'active': True,
                'triggered': False,
                'description': f'Accumulation zone {i+1} at {zone_price:.2f}'
            })
        
        # Profit-taking zones (above entry for long positions)
        for i in range(4):
            zone_price = entry_price * (1 + (i + 1) * 0.1)  # 10%, 20%, 30%, 40% above entry
            take_quantity = quantity * [0.25, 0.25, 0.3, 0.2][i]  # Graduated profit taking
            zones.append({
                'id': str(uuid.uuid4()),
                'type': ZoneType.PROFIT_TAKING.value,
                'price': zone_price,
                'quantity': take_quantity,
                'active': True,
                'triggered': False,
                'description': f'Profit taking zone {i+1} at {zone_price:.2f}'
            })
        
        # Stop-loss zone
        stop_price = entry_price * 0.85  # 15% below entry
        zones.append({
            'id': str(uuid.uuid4()),
            'type': ZoneType.STOP_LOSS.value,
            'price': stop_price,
            'quantity': quantity,  # Close entire position
            'active': True,
            'triggered': False,
            'description': f'Stop loss at {stop_price:.2f}'
        })
        
        return zones
    
    async def update_position_price(self, position_id: str, current_price: float):
        """Update position with current market price and check zones."""
        if position_id not in self.positions:
            raise ValueError(f"Position {position_id} not found")
        
        position = self.positions[position_id]
        old_price = position.current_price
        position.current_price = current_price
        position.unrealized_pnl = (current_price - position.entry_price) * position.quantity
        position.updated_at = datetime.now()
        
        # Check if any zones are triggered
        triggered_zones = await self.check_zone_triggers(position, old_price, current_price)
        
        # Execute zone strategies
        for zone in triggered_zones:
            await self.execute_zone_strategy(position, zone)
        
        # Update position in storage
        await self.store_position(position)
        
        return position
    
    async def check_zone_triggers(self, position: Position, old_price: float, new_price: float) -> List[Dict]:
        """Check if price movement has triggered any zones."""
        triggered_zones = []
        
        for zone in position.zones:
            if not zone['active'] or zone['triggered']:
                continue
            
            zone_price = zone['price']
            zone_type = zone['type']
            
            # Check if zone was crossed
            if zone_type in [ZoneType.ACCUMULATION.value, ZoneType.STOP_LOSS.value]:
                # Trigger on price moving down through zone
                if old_price > zone_price >= new_price:
                    zone['triggered'] = True
                    triggered_zones.append(zone)
                    logger.info(f"Zone triggered: {zone['description']}")
            
            elif zone_type == ZoneType.PROFIT_TAKING.value:
                # Trigger on price moving up through zone
                if old_price < zone_price <= new_price:
                    zone['triggered'] = True
                    triggered_zones.append(zone)
                    logger.info(f"Zone triggered: {zone['description']}")
        
        return triggered_zones
    
    async def execute_zone_strategy(self, position: Position, zone: Dict):
        """Execute the strategy for a triggered zone."""
        zone_type = ZoneType(zone['type'])
        strategy_func = self.zone_strategies.get(zone_type)
        
        if strategy_func:
            await strategy_func(position, zone)
        else:
            logger.warning(f"No strategy found for zone type: {zone_type}")
    
    async def accumulation_strategy(self, position: Position, zone: Dict):
        """Execute accumulation strategy - add to position."""
        additional_quantity = zone['quantity']
        zone_price = zone['price']
        
        # Create buy order
        order = await self.create_order(
            position_id=position.id,
            symbol=position.symbol,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=additional_quantity,
            price=zone_price
        )
        
        # Simulate order execution (in real system, this would be handled by execution engine)
        await self.simulate_order_execution(order, position)
        
        logger.info(f"Executed accumulation: added {additional_quantity} shares at {zone_price}")
    
    async def distribution_strategy(self, position: Position, zone: Dict):
        """Execute distribution strategy - reduce position size."""
        reduce_quantity = zone['quantity']
        zone_price = zone['price']
        
        # Create sell order
        order = await self.create_order(
            position_id=position.id,
            symbol=position.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=reduce_quantity,
            price=zone_price
        )
        
        await self.simulate_order_execution(order, position)
        
        logger.info(f"Executed distribution: sold {reduce_quantity} shares at {zone_price}")
    
    async def profit_taking_strategy(self, position: Position, zone: Dict):
        """Execute profit-taking strategy."""
        take_quantity = min(zone['quantity'], position.quantity)
        zone_price = zone['price']
        
        # Create sell order for profit taking
        order = await self.create_order(
            position_id=position.id,
            symbol=position.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.LIMIT,
            quantity=take_quantity,
            price=zone_price
        )
        
        await self.simulate_order_execution(order, position)
        
        logger.info(f"Executed profit taking: sold {take_quantity} shares at {zone_price}")
    
    async def stop_loss_strategy(self, position: Position, zone: Dict):
        """Execute stop-loss strategy - close position."""
        zone_price = zone['price']
        
        # Create market sell order to close position immediately
        order = await self.create_order(
            position_id=position.id,
            symbol=position.symbol,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=position.quantity,
            price=zone_price
        )
        
        await self.simulate_order_execution(order, position)
        
        # Close position
        position.status = PositionStatus.CLOSED
        
        logger.info(f"Executed stop loss: closed position at {zone_price}")
    
    async def create_order(self, position_id: str, symbol: str, side: OrderSide, 
                          order_type: OrderType, quantity: float, price: Optional[float] = None,
                          stop_price: Optional[float] = None) -> Order:
        """Create a new order."""
        order_id = str(uuid.uuid4())
        
        order = Order(
            id=order_id,
            position_id=position_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price,
            created_at=datetime.now()
        )
        
        self.orders[order_id] = order
        
        # Store in Redis
        redis_client.setex(f"order:{order_id}", 3600, order.json())
        
        return order
    
    async def simulate_order_execution(self, order: Order, position: Position):
        """Simulate order execution (in real system, this would be handled by broker)."""
        if order.side == OrderSide.BUY:
            # Add to position
            total_cost = position.quantity * position.entry_price + order.quantity * order.price
            total_quantity = position.quantity + order.quantity
            position.entry_price = total_cost / total_quantity  # Update average entry price
            position.quantity = total_quantity
        
        elif order.side == OrderSide.SELL:
            # Reduce position
            sell_pnl = (order.price - position.entry_price) * order.quantity
            position.realized_pnl += sell_pnl
            position.quantity -= order.quantity
            
            if position.quantity <= 0:
                position.status = PositionStatus.CLOSED
        
        order.status = "FILLED"
        
        # Update order in storage
        redis_client.setex(f"order:{order.id}", 3600, order.json())
    
    async def store_position(self, position: Position):
        """Store position in Redis."""
        redis_client.setex(f"position:{position.id}", 3600, position.json())
    
    async def get_position(self, position_id: str) -> Optional[Position]:
        """Retrieve position from storage."""
        if position_id in self.positions:
            return self.positions[position_id]
        
        # Try to load from Redis
        position_data = redis_client.get(f"position:{position_id}")
        if position_data:
            position_dict = json.loads(position_data)
            position = Position(**position_dict)
            self.positions[position_id] = position
            return position
        
        return None
    
    async def get_all_positions(self) -> List[Position]:
        """Get all active positions."""
        return [pos for pos in self.positions.values() if pos.status == PositionStatus.OPEN]
    
    async def calculate_portfolio_metrics(self) -> Dict[str, Any]:
        """Calculate portfolio-level metrics."""
        positions = await self.get_all_positions()
        
        if not positions:
            return {
                'total_value': 0.0,
                'total_pnl': 0.0,
                'total_unrealized_pnl': 0.0,
                'total_realized_pnl': 0.0,
                'position_count': 0
            }
        
        total_value = sum(pos.quantity * pos.current_price for pos in positions)
        total_unrealized_pnl = sum(pos.unrealized_pnl for pos in positions)
        total_realized_pnl = sum(pos.realized_pnl for pos in positions)
        
        return {
            'total_value': total_value,
            'total_pnl': total_unrealized_pnl + total_realized_pnl,
            'total_unrealized_pnl': total_unrealized_pnl,
            'total_realized_pnl': total_realized_pnl,
            'position_count': len(positions),
            'positions': [
                {
                    'symbol': pos.symbol,
                    'quantity': pos.quantity,
                    'current_value': pos.quantity * pos.current_price,
                    'unrealized_pnl': pos.unrealized_pnl,
                    'pnl_percent': (pos.unrealized_pnl / (pos.quantity * pos.entry_price)) * 100
                }
                for pos in positions
            ]
        }

# Initialize position manager
position_manager = ZoneBasedPositionManager()

@app.get("/")
async def root():
    return {
        "service": "position-management",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "active_positions": len(await position_manager.get_all_positions())
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "position-management",
        "timestamp": datetime.now().isoformat(),
        "redis_connected": redis_client.ping()
    }

@app.post("/positions", response_model=Position)
async def create_position(symbol: str, quantity: float, entry_price: float):
    """Create a new position."""
    try:
        position = await position_manager.create_position(symbol, quantity, entry_price)
        return position
    except Exception as e:
        logger.error(f"Error creating position: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating position: {str(e)}")

@app.get("/positions", response_model=List[Position])
async def get_positions():
    """Get all active positions."""
    try:
        positions = await position_manager.get_all_positions()
        return positions
    except Exception as e:
        logger.error(f"Error retrieving positions: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving positions: {str(e)}")

@app.get("/positions/{position_id}", response_model=Position)
async def get_position(position_id: str):
    """Get a specific position."""
    try:
        position = await position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        return position
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving position: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving position: {str(e)}")

@app.put("/positions/{position_id}/price")
async def update_position_price(position_id: str, current_price: float):
    """Update position with current market price."""
    try:
        position = await position_manager.update_position_price(position_id, current_price)
        return position
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating position price: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error updating position price: {str(e)}")

@app.get("/portfolio/metrics")
async def get_portfolio_metrics():
    """Get portfolio-level metrics."""
    try:
        metrics = await position_manager.calculate_portfolio_metrics()
        return metrics
    except Exception as e:
        logger.error(f"Error calculating portfolio metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error calculating portfolio metrics: {str(e)}")

@app.get("/positions/{position_id}/zones")
async def get_position_zones(position_id: str):
    """Get zones for a specific position."""
    try:
        position = await position_manager.get_position(position_id)
        if not position:
            raise HTTPException(status_code=404, detail="Position not found")
        
        return {
            "position_id": position_id,
            "symbol": position.symbol,
            "zones": position.zones,
            "total_zones": len(position.zones),
            "active_zones": len([z for z in position.zones if z['active'] and not z['triggered']])
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving position zones: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving position zones: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
