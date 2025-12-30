"""
Position Zone Manager - Executes zone-based trading actions
Bridges the LivePositionsRegistry with BitgetFuturesClient for order execution
"""

import asyncio
import time
from typing import Dict, Optional, List
from datetime import datetime
import structlog

from live_positions_registry import LivePositionsRegistry, Position, PositionZone
from bitget_futures_client import BitgetFuturesClient
from futures_symbols_config import format_quantity, format_price, validate_order_size
from fibonacci_delta_calculator import FibonacciDeltaCalculator, DynamicThreshold

logger = structlog.get_logger(__name__)

class PositionZoneManager:
    """
    Executes trading actions based on position zones
    Handles averaging, surplus dumps, and position closures
    """
    
    def __init__(self, 
                 registry: LivePositionsRegistry,
                 bitget_client: BitgetFuturesClient,
                 check_interval: int = 3,
                 manage_manual_positions: bool = True):
        self.registry = registry
        self.bitget = bitget_client
        self.check_interval = check_interval
        self.running = False
        self.execution_lock = asyncio.Lock()
        self.fib_calculator = FibonacciDeltaCalculator(bitget_client)
        self.position_thresholds = {}  # Cache for dynamic thresholds
        self.manage_manual_positions = manage_manual_positions  # Enable management of manual positions
        
    async def start(self):
        """Start zone management loop"""
        self.running = True
        logger.info("Starting Position Zone Manager")
        asyncio.create_task(self.zone_management_loop())
        
    async def stop(self):
        """Stop zone management loop"""
        self.running = False
        logger.info("Stopping Position Zone Manager")
        
    async def zone_management_loop(self):
        """Main loop that monitors positions and executes zone actions"""
        while self.running:
            try:
                positions = await self.registry.get_all_positions()
                
                for position in positions:
                    # Skip manual positions only if configured to do so
                    if position.is_manual and not self.manage_manual_positions:
                        logger.debug(f"Skipping manual position {position.symbol}")
                        continue
                    
                    # Log if managing manual position
                    if position.is_manual:
                        logger.debug(f"Managing manual position {position.symbol} with dynamic thresholds")
                        
                    # Update zone based on current UPNL
                    await self.registry.update_zone(position)
                    
                    # Execute zone-specific actions
                    await self.execute_zone_action(position)
                    
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Zone management error: {e}")
                await asyncio.sleep(self.check_interval * 2)
                
    async def execute_zone_action(self, position: Position):
        """Execute appropriate action based on position zone"""
        async with self.execution_lock:
            try:
                if position.current_zone == PositionZone.AVERAGING:
                    await self.execute_averaging(position)
                    
                elif position.current_zone == PositionZone.SURPLUS_DUMP:
                    await self.execute_surplus_dump(position)
                    
                elif position.current_zone == PositionZone.PROFIT_TAKING:
                    await self.execute_profit_taking(position)
                    
                elif position.current_zone == PositionZone.STOP_LOSS:
                    await self.execute_stop_loss(position)
                    
            except Exception as e:
                logger.error(f"Failed to execute zone action for {position.symbol}: {e}")
                
    async def execute_averaging(self, position: Position):
        """Execute averaging (DCA) for position in averaging zone"""
        try:
            # Check if we can still average
            if position.averaging_steps_taken >= position.custom_params.max_averaging_steps:
                logger.info(f"Max averaging steps reached for {position.symbol}")
                return
            
            # Check if dynamic thresholds are met
            if not await self.should_average_position(position):
                return
            
            # Get dynamic multiplier for this level
            next_level = position.averaging_steps_taken + 1
            multiplier = await self.get_dynamic_multiplier(position, next_level)
            
            # Calculate next averaging size with dynamic multiplier
            base_size = position.initial_quantity
            next_size = base_size * multiplier
            
            if next_size <= 0:
                return
                
            # Format for exchange
            symbol_with_suffix = f"{position.symbol}_UMCBL"
            formatted_size = format_quantity(symbol_with_suffix, next_size)
            
            # Validate order
            is_valid, msg = validate_order_size(
                symbol_with_suffix, 
                float(formatted_size), 
                position.current_price
            )
            
            if not is_valid:
                logger.warning(f"Invalid averaging size for {position.symbol}: {msg}")
                return
                
            # Place averaging order
            side = "open_long" if position.direction == "long" else "open_short"
            
            result = self.bitget.place_futures_order(
                symbol=symbol_with_suffix,
                margin_coin="USDT",
                size=formatted_size,
                side=side,
                order_type="market",
                margin_mode="isolated"
            )
            
            if result and result.get('orderId'):
                # Record the averaging step
                await self.registry.record_averaging_step(
                    position,
                    position.current_price,
                    float(formatted_size),
                    result['orderId']
                )
                
                logger.info(f"Averaging executed for {position.symbol}",
                          step=position.averaging_steps_taken,
                          size=formatted_size,
                          price=position.current_price)
                          
        except Exception as e:
            logger.error(f"Failed to execute averaging for {position.symbol}: {e}")
            
    async def execute_surplus_dump(self, position: Position):
        """Execute surplus dump for positions that recovered after averaging"""
        try:
            # Calculate dump quantity
            dump_quantity = await self.registry.calculate_surplus_dump(position)
            
            if not dump_quantity or dump_quantity <= 0:
                return
                
            # Format for exchange
            symbol_with_suffix = f"{position.symbol}_UMCBL"
            formatted_size = format_quantity(symbol_with_suffix, dump_quantity)
            
            # Validate order
            is_valid, msg = validate_order_size(
                symbol_with_suffix,
                float(formatted_size),
                position.current_price
            )
            
            if not is_valid:
                logger.warning(f"Invalid surplus dump size for {position.symbol}: {msg}")
                return
                
            # Place surplus dump order (closing position)
            side = "close_long" if position.direction == "long" else "close_short"
            
            result = self.bitget.place_futures_order(
                symbol=symbol_with_suffix,
                margin_coin="USDT",
                size=formatted_size,
                side=side,
                order_type="market",
                reduce_only=True,
                margin_mode="isolated"
            )
            
            if result and result.get('orderId'):
                # Record the surplus dump
                await self.registry.record_surplus_dump(
                    position,
                    float(formatted_size),
                    position.current_price,
                    result['orderId']
                )
                
                logger.info(f"Surplus dump executed for {position.symbol}",
                          quantity=formatted_size,
                          remaining_surplus=position.surplus_size)
                          
        except Exception as e:
            logger.error(f"Failed to execute surplus dump for {position.symbol}: {e}")
            
    async def execute_profit_taking(self, position: Position):
        """Execute profit taking for positions meeting profit threshold"""
        try:
            # Only take profit on positions without averaging history
            if position.averaging_steps_taken > 0:
                return
                
            # Close entire position
            symbol_with_suffix = f"{position.symbol}_UMCBL"
            formatted_size = format_quantity(symbol_with_suffix, position.current_quantity)
            
            # Place closing order
            side = "close_long" if position.direction == "long" else "close_short"
            
            result = self.bitget.place_futures_order(
                symbol=symbol_with_suffix,
                margin_coin="USDT",
                size=formatted_size,
                side=side,
                order_type="market",
                reduce_only=True,
                margin_mode="isolated"
            )
            
            if result and result.get('orderId'):
                logger.info(f"Profit taking executed for {position.symbol}",
                          profit=position.unrealized_pnl,
                          size=formatted_size)
                          
                # Archive the position
                await self.registry.archive_position(position.position_id)
                
        except Exception as e:
            logger.error(f"Failed to execute profit taking for {position.symbol}: {e}")
            
    async def execute_stop_loss(self, position: Position):
        """Execute stop loss for positions exceeding loss threshold"""
        try:
            # Emergency close entire position
            symbol_with_suffix = f"{position.symbol}_UMCBL"
            formatted_size = format_quantity(symbol_with_suffix, position.current_quantity)
            
            # Place emergency closing order
            side = "close_long" if position.direction == "long" else "close_short"
            
            result = self.bitget.place_futures_order(
                symbol=symbol_with_suffix,
                margin_coin="USDT",
                size=formatted_size,
                side=side,
                order_type="market",
                reduce_only=True,
                margin_mode="isolated"
            )
            
            if result and result.get('orderId'):
                logger.warning(f"STOP LOSS executed for {position.symbol}",
                             loss=position.unrealized_pnl,
                             size=formatted_size)
                             
                # Archive the position
                await self.registry.archive_position(position.position_id)
                
        except Exception as e:
            logger.error(f"Failed to execute stop loss for {position.symbol}: {e}")
            
    async def calculate_dynamic_thresholds(self, position: Position) -> List[DynamicThreshold]:
        """Calculate dynamic thresholds for a position"""
        try:
            # Check cache
            cache_key = f"{position.symbol}_{position.direction}"
            if cache_key in self.position_thresholds:
                cached_thresholds, cache_time = self.position_thresholds[cache_key]
                # Use cache if less than 5 minutes old
                if time.time() - cache_time < 300:
                    return cached_thresholds
            
            # Calculate new thresholds
            thresholds = await self.fib_calculator.calculate_dynamic_thresholds(
                symbol=position.symbol,
                entry_price=position.weighted_avg_price,
                side=position.direction,
                max_levels=position.custom_params.max_averaging_steps
            )
            
            # Update cache
            self.position_thresholds[cache_key] = (thresholds, time.time())
            
            # Log threshold summary
            summary = self.fib_calculator.get_threshold_summary(thresholds)
            logger.info(f"Dynamic thresholds calculated for {position.symbol}",
                       summary=summary)
            
            return thresholds
            
        except Exception as e:
            logger.error(f"Failed to calculate dynamic thresholds: {e}")
            return []
    
    async def should_average_position(self, position: Position) -> bool:
        """Determine if position should be averaged based on dynamic thresholds"""
        try:
            # Get dynamic thresholds
            thresholds = await self.calculate_dynamic_thresholds(position)
            if not thresholds:
                # Fallback to static threshold
                return position.unrealized_pnl < position.custom_params.averaging_threshold
            
            # Find appropriate threshold for current averaging level
            current_level = position.averaging_steps_taken + 1
            threshold = None
            
            for t in thresholds:
                if t.level == current_level:
                    threshold = t
                    break
            
            if not threshold:
                return False
            
            # Calculate current loss percentage
            current_loss_pct = (position.unrealized_pnl / 
                              (position.weighted_avg_price * position.current_quantity)) * 100
            
            # Check if threshold is met with confidence
            should_average = (current_loss_pct <= threshold.threshold_pct and 
                            threshold.confidence > 0.5)
            
            if should_average:
                logger.info(f"Dynamic averaging triggered for {position.symbol}",
                          level=current_level,
                          loss_pct=f"{current_loss_pct:.2f}%",
                          threshold=f"{threshold.threshold_pct:.2f}%",
                          confidence=threshold.confidence,
                          expected_bounce=f"{threshold.expected_bounce:.1f}%")
            
            return should_average
            
        except Exception as e:
            logger.error(f"Error checking averaging condition: {e}")
            return False
    
    async def get_dynamic_multiplier(self, position: Position, level: int) -> float:
        """Get position size multiplier from dynamic thresholds"""
        try:
            thresholds = await self.calculate_dynamic_thresholds(position)
            if not thresholds:
                # Fallback to exponential multiplier
                return position.custom_params.averaging_multiplier ** level
            
            for t in thresholds:
                if t.level == level:
                    return t.multiplier
            
            # Default multiplier if level not found
            return 1.618 ** level  # Golden ratio fallback
            
        except Exception as e:
            logger.error(f"Error getting dynamic multiplier: {e}")
            return 1.0
    
    async def on_position_opened(self, symbol: str, side: str, entry_price: float,
                                 quantity: float, order_id: str) -> Position:
        """
        Called when a new position is opened by the trading engine
        Creates and registers the position in the registry
        """
        from uuid import uuid4
        
        position = Position(
            position_id=str(uuid4()),
            symbol=symbol,
            direction=side,
            initial_entry_price=entry_price,
            initial_quantity=quantity,
            initial_order_id=order_id,
            entry_timestamp=datetime.now(),
            current_quantity=quantity,
            weighted_avg_price=entry_price,
            current_price=entry_price,
            leverage=20,
            margin_mode="isolated"
        )
        
        # Add to registry
        await self.registry.add_position(position)
        
        logger.info(f"New position registered: {symbol} {side} @ {entry_price}")
        return position