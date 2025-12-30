"""
Exchange Reconciliation Service
Ensures local position state matches exchange reality
"""

import asyncio
import time
from typing import List, Optional, Dict
from datetime import datetime, timedelta
import structlog

from live_positions_registry import LivePositionsRegistry, Position, PositionZone
from bitget_futures_client import BitgetFuturesClient

logger = structlog.get_logger(__name__)

class ExchangeReconciliationService:
    """
    Continuously reconciles local position registry with exchange state
    Handles discrepancies and ensures data consistency
    """
    
    def __init__(self, 
                 registry: LivePositionsRegistry,
                 bitget_client: BitgetFuturesClient,
                 interval: int = 5,
                 max_retries: int = 3):
        self.registry = registry
        self.bitget = bitget_client
        self.interval = interval  # Reconciliation interval in seconds
        self.max_retries = max_retries
        self.running = False
        self.last_reconciliation = None
        self.reconciliation_errors = 0
        self.backoff_multiplier = 1
        
    async def start(self):
        """Start reconciliation loop"""
        self.running = True
        logger.info("Starting exchange reconciliation service")
        asyncio.create_task(self.reconciliation_loop())
        
    async def stop(self):
        """Stop reconciliation loop"""
        self.running = False
        logger.info("Stopping exchange reconciliation service")
        
    async def reconciliation_loop(self):
        """Main reconciliation loop"""
        while self.running:
            try:
                await self.reconcile_positions()
                self.reconciliation_errors = 0
                self.backoff_multiplier = 1
                
            except Exception as e:
                self.reconciliation_errors += 1
                logger.error(f"Reconciliation error #{self.reconciliation_errors}: {e}")
                
                if self.reconciliation_errors >= self.max_retries:
                    await self.handle_critical_failure()
                    
                # Exponential backoff
                self.backoff_multiplier = min(self.backoff_multiplier * 2, 60)
                
            # Wait for next cycle with backoff
            await asyncio.sleep(self.interval * self.backoff_multiplier)
            
    async def reconcile_positions(self):
        """
        Core reconciliation logic
        Compares exchange positions with local registry
        """
        start_time = time.time()
        
        # Get positions from both sources
        exchange_positions = await self.fetch_exchange_positions()
        registry_positions = await self.registry.get_all_positions()
        
        # Create lookup maps
        exchange_map = {self.get_position_key(p): p for p in exchange_positions}
        registry_map = {p.symbol: p for p in registry_positions}
        
        reconciliation_stats = {
            "updated": 0,
            "closed": 0,
            "unknown": 0,
            "errors": 0
        }
        
        # Update existing positions from exchange data
        for symbol, reg_pos in registry_map.items():
            exchange_key = self.get_position_key_from_symbol(symbol)
            
            if exchange_key in exchange_map:
                # Position exists on both sides - update local state
                ex_pos = exchange_map[exchange_key]
                await self.update_position_from_exchange(reg_pos, ex_pos)
                reconciliation_stats["updated"] += 1
                
            else:
                # Position in registry but not on exchange - it was closed
                await self.handle_closed_position(reg_pos)
                reconciliation_stats["closed"] += 1
                
        # Check for positions on exchange but not in registry
        for exchange_key, ex_pos in exchange_map.items():
            symbol = self.extract_symbol(exchange_key)
            if symbol not in registry_map:
                # Unknown position on exchange
                await self.handle_unknown_position(ex_pos)
                reconciliation_stats["unknown"] += 1
                
        # Log reconciliation metrics
        elapsed = time.time() - start_time
        logger.info(f"Reconciliation completed in {elapsed:.2f}s", 
                   stats=reconciliation_stats)
        
        self.last_reconciliation = datetime.now()
        
    async def fetch_exchange_positions(self) -> List[Dict]:
        """Fetch all positions from Bitget"""
        try:
            positions = self.bitget.get_all_positions()
            # Filter for positions with actual size
            return [p for p in positions if float(p.get('total', 0)) > 0]
            
        except Exception as e:
            logger.error(f"Failed to fetch exchange positions: {e}")
            raise
            
    async def update_position_from_exchange(self, local_pos: Position, 
                                           exchange_pos: Dict):
        """Update local position with exchange data"""
        try:
            # Extract key fields from exchange
            current_price = float(exchange_pos.get('marketPrice', 0))
            current_quantity = float(exchange_pos.get('total', 0))
            unrealized_pnl = float(exchange_pos.get('unrealizedPL', 0))
            margin_used = float(exchange_pos.get('margin', 0))
            
            # Update local position
            local_pos.current_price = current_price
            local_pos.current_quantity = current_quantity
            local_pos.unrealized_pnl = unrealized_pnl
            local_pos.margin_used = margin_used
            
            # Update risk metrics
            await self.registry.update_risk_metrics(local_pos)
            
            # Check and update zone
            await self.registry.update_zone(local_pos)
            
            # Update in registry
            updates = {
                "current_price": current_price,
                "current_quantity": current_quantity,
                "unrealized_pnl": unrealized_pnl,
                "margin_used": margin_used
            }
            
            await self.registry.update_position(local_pos.position_id, updates)
            
        except Exception as e:
            logger.error(f"Failed to update position {local_pos.symbol}: {e}")
            
    async def handle_closed_position(self, position: Position):
        """Handle position that was closed on exchange"""
        logger.info(f"Position {position.symbol} closed on exchange")
        
        # Archive the position
        await self.registry.archive_position(position.position_id)
        
        # Send notification (integrate with notification service)
        await self.send_position_closed_alert(position)
        
    async def handle_unknown_position(self, exchange_pos: Dict):
        """
        Handle position that exists on exchange but not in registry
        This could be a manually opened position
        """
        logger.warning(f"Unknown position found on exchange: {exchange_pos.get('symbol')}")
        
        # Create position in registry
        position = await self.create_position_from_exchange(exchange_pos)
        
        if position:
            position.is_manual = True  # Flag as manual
            await self.registry.add_position(position)
            logger.info(f"Added manual position {position.symbol} to registry")
            
    async def create_position_from_exchange(self, exchange_pos: Dict) -> Optional[Position]:
        """Create Position object from exchange data"""
        try:
            from uuid import uuid4
            
            symbol = exchange_pos.get('symbol', '').replace('_UMCBL', '')
            
            position = Position(
                position_id=str(uuid4()),
                symbol=symbol,
                direction=exchange_pos.get('holdSide', 'long'),
                initial_entry_price=float(exchange_pos.get('averageOpenPrice', 0)),
                initial_quantity=float(exchange_pos.get('total', 0)),
                initial_order_id="manual",
                entry_timestamp=datetime.now(),
                current_quantity=float(exchange_pos.get('total', 0)),
                weighted_avg_price=float(exchange_pos.get('averageOpenPrice', 0)),
                current_price=float(exchange_pos.get('marketPrice', 0)),
                unrealized_pnl=float(exchange_pos.get('unrealizedPL', 0)),
                leverage=int(exchange_pos.get('leverage', 20)),
                margin_used=float(exchange_pos.get('margin', 0)),
                margin_mode=exchange_pos.get('marginMode', 'fixed'),
                is_manual=True
            )
            
            return position
            
        except Exception as e:
            logger.error(f"Failed to create position from exchange data: {e}")
            return None
            
    async def handle_critical_failure(self):
        """Handle critical reconciliation failures"""
        logger.critical(f"Reconciliation failed {self.max_retries} times!")
        
        # Send urgent alert
        await self.send_critical_alert()
        
        # Could implement fallback logic here
        # For now, continue with exponential backoff
        
    async def send_position_closed_alert(self, position: Position):
        """Send alert when position is closed"""
        # Integration point for notification service
        logger.info(f"Alert: Position {position.symbol} closed. "
                   f"Final P&L: {position.unrealized_pnl + position.realized_pnl}")
        
    async def send_critical_alert(self):
        """Send critical system alert"""
        # Integration point for notification service
        logger.critical("CRITICAL: Exchange reconciliation is failing!")
        
    def get_position_key(self, exchange_pos: Dict) -> str:
        """Generate unique key for position"""
        symbol = exchange_pos.get('symbol', '')
        side = exchange_pos.get('holdSide', '')
        return f"{symbol}_{side}"
        
    def get_position_key_from_symbol(self, symbol: str) -> str:
        """Generate exchange key from symbol"""
        # Assuming we track one position per symbol for now
        return f"{symbol}_UMCBL_long"  # This needs to be more sophisticated
        
    def extract_symbol(self, exchange_key: str) -> str:
        """Extract symbol from exchange key"""
        return exchange_key.split('_')[0]
        
    async def force_reconciliation(self):
        """Force immediate reconciliation"""
        logger.info("Forcing immediate reconciliation")
        await self.reconcile_positions()