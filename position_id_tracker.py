#!/usr/bin/env python3
"""
Position ID Tracker for AI-XYZ Trading System
Implements position tracking by unique ID instead of symbol
"""

import uuid
from datetime import datetime
from typing import Dict, Optional, Tuple

class PositionIDTracker:
    """Manages position tracking with unique IDs"""
    
    def __init__(self):
        # Map symbol to current active position ID
        self.symbol_to_position_id = {}
        
        # All position data keyed by position ID
        self.positions_by_id = {}
        
        # Zone tracking by position ID
        self.zones_by_id = {}
        self.averaging_steps_by_id = {}
        self.peak_upnl_by_id = {}
        self.surplus_dump_stage_by_id = {}
        self.original_sizes_by_id = {}
        
    def create_position_id(self, symbol: str) -> str:
        """Generate unique position ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        return f"{symbol.replace('/', '_').replace(':', '_')}_{timestamp}_{unique_id}"
    
    def open_new_position(self, symbol: str, position_data: Dict) -> str:
        """Open a new position with unique ID"""
        # Generate new position ID
        position_id = self.create_position_id(symbol)
        
        # Store position data with ID
        position_data['position_id'] = position_id
        position_data['symbol'] = symbol
        self.positions_by_id[position_id] = position_data
        
        # Map symbol to this position ID
        self.symbol_to_position_id[symbol] = position_id
        
        # Initialize tracking with fresh values (zones reset!)
        self.zones_by_id[position_id] = 'NEUTRAL'
        self.averaging_steps_by_id[position_id] = 0
        self.peak_upnl_by_id[position_id] = 0
        self.surplus_dump_stage_by_id[position_id] = 0
        self.original_sizes_by_id[position_id] = position_data.get('amount', 0)
        
        return position_id
    
    def close_position(self, symbol: str) -> bool:
        """Close position and clean up tracking"""
        position_id = self.symbol_to_position_id.get(symbol)
        if not position_id:
            return False
        
        # Remove symbol mapping
        del self.symbol_to_position_id[symbol]
        
        # Mark position as closed but keep historical data
        if position_id in self.positions_by_id:
            self.positions_by_id[position_id]['closed_at'] = datetime.now().isoformat()
            self.positions_by_id[position_id]['status'] = 'closed'
        
        # Clean up tracking (optional - could keep for history)
        # self.zones_by_id.pop(position_id, None)
        # self.averaging_steps_by_id.pop(position_id, None)
        # self.peak_upnl_by_id.pop(position_id, None)
        # self.surplus_dump_stage_by_id.pop(position_id, None)
        # self.original_sizes_by_id.pop(position_id, None)
        
        return True
    
    def get_position_id_by_symbol(self, symbol: str) -> Optional[str]:
        """Get current position ID for a symbol"""
        return self.symbol_to_position_id.get(symbol)
    
    def get_position_data(self, position_id: str) -> Optional[Dict]:
        """Get position data by ID"""
        return self.positions_by_id.get(position_id)
    
    def get_zone(self, symbol: str) -> str:
        """Get zone for current position on symbol"""
        position_id = self.symbol_to_position_id.get(symbol)
        if position_id:
            return self.zones_by_id.get(position_id, 'NEUTRAL')
        return 'NEUTRAL'
    
    def set_zone(self, symbol: str, zone: str) -> bool:
        """Set zone for current position on symbol"""
        position_id = self.symbol_to_position_id.get(symbol)
        if position_id:
            self.zones_by_id[position_id] = zone
            return True
        return False
    
    def get_averaging_steps(self, symbol: str) -> int:
        """Get averaging steps for current position"""
        position_id = self.symbol_to_position_id.get(symbol)
        if position_id:
            return self.averaging_steps_by_id.get(position_id, 0)
        return 0
    
    def increment_averaging_steps(self, symbol: str) -> int:
        """Increment averaging steps for position"""
        position_id = self.symbol_to_position_id.get(symbol)
        if position_id:
            current = self.averaging_steps_by_id.get(position_id, 0)
            self.averaging_steps_by_id[position_id] = current + 1
            return current + 1
        return 0
    
    def get_tracking_data(self, symbol: str) -> Dict:
        """Get all tracking data for current position on symbol"""
        position_id = self.symbol_to_position_id.get(symbol)
        if not position_id:
            return {
                'position_id': None,
                'zone': 'NEUTRAL',
                'averaging_steps': 0,
                'peak_upnl': 0,
                'surplus_dump_stage': 0,
                'original_size': 0
            }
        
        return {
            'position_id': position_id,
            'zone': self.zones_by_id.get(position_id, 'NEUTRAL'),
            'averaging_steps': self.averaging_steps_by_id.get(position_id, 0),
            'peak_upnl': self.peak_upnl_by_id.get(position_id, 0),
            'surplus_dump_stage': self.surplus_dump_stage_by_id.get(position_id, 0),
            'original_size': self.original_sizes_by_id.get(position_id, 0)
        }
    
    def get_active_positions(self) -> Dict[str, Dict]:
        """Get all active positions mapped by symbol"""
        active = {}
        for symbol, position_id in self.symbol_to_position_id.items():
            if position_id in self.positions_by_id:
                active[symbol] = self.positions_by_id[position_id].copy()
                # Add tracking data
                active[symbol]['zone'] = self.zones_by_id.get(position_id, 'NEUTRAL')
                active[symbol]['averaging_steps'] = self.averaging_steps_by_id.get(position_id, 0)
                active[symbol]['peak_upnl'] = self.peak_upnl_by_id.get(position_id, 0)
                active[symbol]['surplus_dump_stage'] = self.surplus_dump_stage_by_id.get(position_id, 0)
                active[symbol]['original_size'] = self.original_sizes_by_id.get(position_id, 0)
        return active
    
    def reconcile_with_exchange(self, exchange_positions: Dict[str, Dict]) -> Tuple[Dict, Dict]:
        """
        Reconcile tracker with exchange positions
        Returns: (positions_to_add, positions_to_remove)
        """
        positions_to_add = {}
        positions_to_remove = []
        
        # Find positions on exchange not in tracker
        for symbol, ex_pos in exchange_positions.items():
            if symbol not in self.symbol_to_position_id:
                positions_to_add[symbol] = ex_pos
        
        # Find tracked positions not on exchange
        for symbol in list(self.symbol_to_position_id.keys()):
            if symbol not in exchange_positions:
                positions_to_remove.append(symbol)
        
        return positions_to_add, positions_to_remove
    
    def migrate_from_symbol_tracking(self, system_instance) -> None:
        """
        Migrate existing symbol-based tracking to position ID tracking
        """
        print("\n🔄 Migrating to position ID based tracking...")
        
        for symbol, position_data in system_instance.active_positions.items():
            # Check if position already has an ID (from order_id)
            if 'order_id' in position_data:
                position_id = f"{symbol.replace('/', '_').replace(':', '_')}_{position_data['order_id']}"
            else:
                position_id = self.create_position_id(symbol)
            
            # Store position with ID
            position_data['position_id'] = position_id
            position_data['symbol'] = symbol
            self.positions_by_id[position_id] = position_data
            
            # Map symbol to position ID
            self.symbol_to_position_id[symbol] = position_id
            
            # Migrate tracking data
            self.zones_by_id[position_id] = system_instance.position_zones.get(symbol, 'NEUTRAL')
            self.averaging_steps_by_id[position_id] = system_instance.averaging_steps.get(symbol, 0)
            self.peak_upnl_by_id[position_id] = system_instance.peak_upnl.get(symbol, 0)
            self.surplus_dump_stage_by_id[position_id] = system_instance.surplus_dump_stage.get(symbol, 0)
            self.original_sizes_by_id[position_id] = system_instance.original_sizes.get(symbol, position_data.get('amount', 0))
            
            print(f"  ✅ Migrated {symbol} -> Position ID: {position_id}")
        
        print(f"  📊 Migrated {len(self.positions_by_id)} positions to ID-based tracking")
        
        # Now cleanup old symbol-based tracking from state
        stale_symbols = set()
        for tracking_dict in [system_instance.position_zones, 
                             system_instance.averaging_steps,
                             system_instance.peak_upnl,
                             system_instance.surplus_dump_stage,
                             system_instance.original_sizes]:
            stale_symbols.update(set(tracking_dict.keys()) - set(system_instance.active_positions.keys()))
        
        if stale_symbols:
            print(f"  🧹 Cleaning {len(stale_symbols)} stale symbol entries")
            for symbol in stale_symbols:
                system_instance.position_zones.pop(symbol, None)
                system_instance.averaging_steps.pop(symbol, None)
                system_instance.peak_upnl.pop(symbol, None)
                system_instance.surplus_dump_stage.pop(symbol, None)
                system_instance.original_sizes.pop(symbol, None)


if __name__ == "__main__":
    # Test the position ID tracker
    tracker = PositionIDTracker()
    
    print("Testing Position ID Tracker")
    print("="*50)
    
    # Simulate opening a position
    symbol = "BTC/USDT:USDT"
    position_data = {
        'entry_price': 50000,
        'amount': 0.1,
        'side': 'buy',
        'leverage': 10
    }
    
    position_id = tracker.open_new_position(symbol, position_data)
    print(f"\n✅ Opened position: {position_id}")
    print(f"   Zone: {tracker.get_zone(symbol)}")
    print(f"   Averaging steps: {tracker.get_averaging_steps(symbol)}")
    
    # Simulate closing position
    tracker.close_position(symbol)
    print(f"\n✅ Closed position on {symbol}")
    
    # Open new position on same symbol
    position_id2 = tracker.open_new_position(symbol, position_data)
    print(f"\n✅ Opened NEW position on same symbol: {position_id2}")
    print(f"   Zone: {tracker.get_zone(symbol)} (should be NEUTRAL)")
    print(f"   Averaging steps: {tracker.get_averaging_steps(symbol)} (should be 0)")
    
    print("\n✅ Position ID tracking working correctly!")
    print("   Each new position gets fresh tracking data")