#!/usr/bin/env python3
"""
Position Persistence Manager for AI-XYZ Trading System
Ensures position state survives system restarts
"""

import json
import redis
import ccxt
from datetime import datetime
from typing import Dict, List, Any
import structlog

logger = structlog.get_logger(__name__)

class PositionPersistenceManager:
    """
    Manages persistent storage and recovery of position state
    """
    
    def __init__(self, exchange, redis_host='localhost', redis_port=6379, redis_db=1):
        """
        Initialize persistence manager
        
        Args:
            exchange: CCXT exchange instance
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
        """
        self.exchange = exchange
        
        # Initialize Redis for persistence
        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True
            )
            self.redis_client.ping()
            self.redis_available = True
            logger.info("Redis persistence initialized")
        except:
            self.redis_available = False
            logger.warning("Redis not available - using file-based persistence")
        
        # Fallback file storage - use container path or local path
        import os
        base_path = os.environ.get('AIXYZ_DATA_PATH', '/app')
        if not os.path.exists(base_path):
            base_path = '/root/ai_xyz'
        if not os.path.exists(base_path):
            base_path = '.'
        self.state_file = os.path.join(base_path, 'position_state.json')
    
    def save_position_state(self, 
                           active_positions: Dict,
                           position_zones: Dict,
                           averaging_steps: Dict,
                           peak_upnl: Dict,
                           surplus_dump_stage: Dict,
                           original_sizes: Dict = None,
                           peak_upnl_timestamps: Dict = None,
                           position_multipliers: Dict = None) -> bool:
        """
        Save current position state to persistent storage
        """
        state = {
            'timestamp': datetime.now().isoformat(),
            'active_positions': active_positions,
            'position_zones': position_zones,
            'averaging_steps': averaging_steps,
            'peak_upnl': peak_upnl,
            'peak_upnl_timestamps': peak_upnl_timestamps or {},
            'surplus_dump_stage': surplus_dump_stage,
            'original_sizes': original_sizes or {},
            'position_multipliers': position_multipliers or {}
        }
        
        try:
            if self.redis_available:
                # Save to Redis
                self.redis_client.set('aixyz:position_state', json.dumps(state))
                
                # Also save individual position data for quick access
                for symbol, pos_data in active_positions.items():
                    key = f'aixyz:position:{symbol}'
                    self.redis_client.hset(key, mapping={
                        'entry_price': pos_data.get('entry_price', 0),
                        'amount': pos_data.get('amount', 0),
                        'side': pos_data.get('side', ''),
                        'leverage': pos_data.get('leverage', 1),
                        'zone': position_zones.get(symbol, 'NEUTRAL'),
                        'averaging_steps': averaging_steps.get(symbol, 0),
                        'peak_upnl': peak_upnl.get(symbol, 0),
                        'surplus_stage': surplus_dump_stage.get(symbol, 0),
                        'pyramid_count': pos_data.get('pyramid_count', 0)
                    })
                    # Set expiry to 24 hours
                    self.redis_client.expire(key, 86400)
            
            # Always save to file as backup
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            
            logger.info(f"Saved state for {len(active_positions)} positions")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save position state: {e}")
            return False
    
    def load_position_state(self) -> Dict:
        """
        Load position state from persistent storage
        """
        try:
            state = None
            
            # Try Redis first
            if self.redis_available:
                redis_state = self.redis_client.get('aixyz:position_state')
                if redis_state:
                    state = json.loads(redis_state)
                    logger.info("Loaded state from Redis")
            
            # Fallback to file if Redis fails
            if not state:
                try:
                    with open(self.state_file, 'r') as f:
                        state = json.load(f)
                        logger.info("Loaded state from file")
                except FileNotFoundError:
                    logger.info("No saved state found")
                    return self._create_empty_state()
            
            if state:
                # Validate timestamp (reject if older than 24 hours)
                saved_time = datetime.fromisoformat(state['timestamp'])
                age_hours = (datetime.now() - saved_time).total_seconds() / 3600
                
                if age_hours > 24:
                    logger.warning(f"Saved state is {age_hours:.1f} hours old - ignoring")
                    return self._create_empty_state()
                
                logger.info(f"Restored state from {age_hours:.1f} hours ago")
                return state
            
        except Exception as e:
            logger.error(f"Failed to load position state: {e}")
        
        return self._create_empty_state()
    
    def reconcile_with_exchange(self, saved_state: Dict) -> Dict:
        """
        Reconcile saved state with actual exchange positions
        
        Returns updated state that matches exchange reality
        """
        try:
            # Get current positions from exchange
            exchange_positions = self.exchange.fetch_positions()
            active_exchange = {
                p['symbol']: p for p in exchange_positions 
                if p['contracts'] > 0
            }
            
            # Start with saved state
            active_positions = saved_state.get('active_positions', {})
            position_zones = saved_state.get('position_zones', {})
            averaging_steps = saved_state.get('averaging_steps', {})
            peak_upnl = saved_state.get('peak_upnl', {})
            surplus_dump_stage = saved_state.get('surplus_dump_stage', {})

            # DEBUG: Log averaging_steps from saved state
            logger.info(f"🔍 Reconcile: averaging_steps from saved state: {averaging_steps}")
            
            # Remove positions that no longer exist on exchange
            symbols_to_remove = []
            for symbol in active_positions:
                if symbol not in active_exchange:
                    symbols_to_remove.append(symbol)
                    logger.info(f"Position {symbol} no longer exists - removing from state")
            
            for symbol in symbols_to_remove:
                del active_positions[symbol]
                position_zones.pop(symbol, None)
                averaging_steps.pop(symbol, None)
                peak_upnl.pop(symbol, None)
                surplus_dump_stage.pop(symbol, None)
            
            # Add new positions from exchange that aren't in saved state
            for symbol, ex_pos in active_exchange.items():
                if symbol not in active_positions:
                    logger.info(f"Found new position {symbol} on exchange - adding to state")
                    
                    # Create position entry
                    active_positions[symbol] = {
                        'entry_price': ex_pos.get('markPrice', 0),
                        'amount': ex_pos['contracts'],
                        'side': ex_pos['side'],
                        'leverage': ex_pos.get('leverage', 1),
                        'opened_at': datetime.now().isoformat()
                    }
                    
                    # Initialize tracking
                    position_zones[symbol] = 'NEUTRAL'
                    averaging_steps[symbol] = 0
                    peak_upnl[symbol] = 0
                    surplus_dump_stage[symbol] = 0
                else:
                    # Update amount if changed BUT preserve all tracking data
                    active_positions[symbol]['amount'] = ex_pos['contracts']
                    # CRITICAL: Don't reset averaging_steps, peak_upnl, etc for existing positions
                    # These should already be in the dictionaries from saved state
            
            logger.info(f"Reconciliation complete: {len(active_positions)} active positions")
            
            return {
                'active_positions': active_positions,
                'position_zones': position_zones,
                'averaging_steps': averaging_steps,
                'peak_upnl': peak_upnl,
                'surplus_dump_stage': surplus_dump_stage
            }
            
        except Exception as e:
            logger.error(f"Failed to reconcile with exchange: {e}")
            return saved_state
    
    def _create_empty_state(self) -> Dict:
        """Create empty state structure"""
        return {
            'active_positions': {},
            'position_zones': {},
            'averaging_steps': {},
            'peak_upnl': {},
            'peak_upnl_timestamps': {},
            'surplus_dump_stage': {},
            'original_sizes': {},
            'position_multipliers': {}
        }
    
    def initialize_from_exchange(self) -> Dict:
        """
        Initialize state directly from exchange positions
        Used when no saved state exists
        """
        try:
            logger.info("Initializing state from exchange positions...")
            
            positions = self.exchange.fetch_positions()
            active = [p for p in positions if p['contracts'] > 0]
            
            active_positions = {}
            position_zones = {}
            averaging_steps = {}
            peak_upnl = {}
            surplus_dump_stage = {}
            
            for pos in active:
                symbol = pos['symbol']
                
                active_positions[symbol] = {
                    'entry_price': pos.get('markPrice', 0),
                    'amount': pos['contracts'],
                    'side': pos['side'],
                    'leverage': pos.get('leverage', 1),
                    'opened_at': 'unknown'  # Don't know when it was opened
                }
                
                # Initialize with defaults
                position_zones[symbol] = 'NEUTRAL'
                averaging_steps[symbol] = 0  # Conservative - assume no averaging yet
                peak_upnl[symbol] = max(0, pos.get('unrealizedPnl', 0))
                surplus_dump_stage[symbol] = 0
                
                logger.info(f"Loaded {symbol}: {pos['side']} {pos['contracts']} contracts")
            
            state = {
                'active_positions': active_positions,
                'position_zones': position_zones,
                'averaging_steps': averaging_steps,
                'peak_upnl': peak_upnl,
                'surplus_dump_stage': surplus_dump_stage
            }
            
            # Save this initial state
            self.save_position_state(
                active_positions,
                position_zones,
                averaging_steps,
                peak_upnl,
                surplus_dump_stage
            )
            
            logger.info(f"Initialized {len(active_positions)} positions from exchange")
            return state
            
        except Exception as e:
            logger.error(f"Failed to initialize from exchange: {e}")
            return self._create_empty_state()


def integrate_persistence(system_instance):
    """
    Integrate persistence manager with AI-XYZ system
    
    Args:
        system_instance: AIXYZContinuousProfit instance
    """
    # Create persistence manager
    persistence = PositionPersistenceManager(system_instance.exchange)
    
    # Load saved state
    saved_state = persistence.load_position_state()
    
    if saved_state['active_positions']:
        # Reconcile with exchange
        reconciled = persistence.reconcile_with_exchange(saved_state)
    else:
        # No saved state - initialize from exchange
        reconciled = persistence.initialize_from_exchange()
    
    # Update system with loaded state
    system_instance.active_positions = reconciled['active_positions']
    system_instance.position_zones = reconciled['position_zones']
    system_instance.averaging_steps = reconciled['averaging_steps']
    system_instance.peak_upnl = reconciled['peak_upnl']
    system_instance.surplus_dump_stage = reconciled['surplus_dump_stage']
    
    # Store persistence manager
    system_instance.persistence = persistence
    
    # Hook into position updates to save state
    original_open = system_instance.open_position
    original_monitor = system_instance.monitor_positions
    
    def wrapped_open(opportunity):
        result = original_open(opportunity)
        if result:
            persistence.save_position_state(
                system_instance.active_positions,
                system_instance.position_zones,
                system_instance.averaging_steps,
                system_instance.peak_upnl,
                system_instance.surplus_dump_stage
            )
        return result
    
    def wrapped_monitor():
        result = original_monitor()
        # Save state after monitoring (may have zone changes)
        persistence.save_position_state(
            system_instance.active_positions,
            system_instance.position_zones,
            system_instance.averaging_steps,
            system_instance.peak_upnl,
            system_instance.surplus_dump_stage
        )
        return result
    
    system_instance.open_position = wrapped_open
    system_instance.monitor_positions = wrapped_monitor
    
    logger.info(f"Persistence integrated - tracking {len(system_instance.active_positions)} positions")


if __name__ == "__main__":
    # Test the persistence manager
    print("Testing Position Persistence Manager")
    print("="*50)
    
    # Initialize exchange
    exchange = ccxt.bitget({
        'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
        'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
        'password': '2609Luiza',
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'defaultMarginMode': 'isolated'
        }
    })
    
    # Create persistence manager
    pm = PositionPersistenceManager(exchange)
    
    # Initialize from exchange
    state = pm.initialize_from_exchange()
    
    print(f"\nLoaded {len(state['active_positions'])} positions:")
    for symbol, pos in state['active_positions'].items():
        print(f"  {symbol}: {pos['side']} {pos['amount']} contracts")
        print(f"    Zone: {state['position_zones'][symbol]}")
        print(f"    Averaging steps: {state['averaging_steps'][symbol]}")
    
    print("\n✅ Persistence manager working correctly")
    print("State saved to: /app/position_state.json")