#!/usr/bin/env python3
"""
Continuous Position Registry Sync Service
Automatically syncs exchange positions to all tracking systems
Removes closed positions and updates active ones
"""

import json
import os
import time
import logging
from datetime import datetime, timezone
from pathlib import Path
import signal
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/position_registry_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# File paths
EXCHANGE_DATA_PATH = "/root/server_deployment/exchange_data.json"
POSITION_REGISTRY_PATH = "/root/server_deployment/margin_optimized_trader/data/unified_position_registry.json"
SURPLUS_STATES_PATH = "/root/server_deployment/data/surplus_states.json"
AVERAGING_HISTORY_PATH = "/root/server_deployment/margin_optimized_trader/data/real_time_averaging/averaging_history.json"
PID_FILE = "/var/run/position_registry_sync.pid"

# Configuration
SYNC_INTERVAL = 30  # seconds
running = True

def signal_handler(signum, frame):
    """Handle shutdown signals"""
    global running
    logger.info(f"Received signal {signum}, shutting down...")
    running = False
    sys.exit(0)

def load_json(filepath, default=None):
    """Load JSON file with error handling"""
    if default is None:
        default = {}
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filepath}: {e}")
    return default

def save_json(filepath, data):
    """Save JSON file with pretty formatting"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return True
    except Exception as e:
        logger.error(f"Error saving {filepath}: {e}")
        return False

def sync_positions():
    """Sync positions from exchange to all tracking systems"""
    try:
        # Load current data
        exchange_data = load_json(EXCHANGE_DATA_PATH)
        position_registry = load_json(POSITION_REGISTRY_PATH)
        surplus_states = load_json(SURPLUS_STATES_PATH)
        averaging_history = load_json(AVERAGING_HISTORY_PATH)
        
        if not exchange_data.get('bitget_positions'):
            logger.info("No positions found in exchange data")
            # Clear all tracking if no positions
            if position_registry or surplus_states or averaging_history:
                logger.info("Clearing all tracking systems (no active positions)")
                save_json(POSITION_REGISTRY_PATH, {})
                save_json(SURPLUS_STATES_PATH, {})
                save_json(AVERAGING_HISTORY_PATH, {})
            return
        
        # Get current positions from exchange
        current_positions = exchange_data['bitget_positions']
        current_symbols = set(current_positions.keys())
        
        # Get tracked positions
        tracked_symbols = set()
        for pid in position_registry.keys():
            # Extract symbol from position ID
            for symbol in current_symbols:
                if symbol in pid or symbol.replace('_USDT', '') in pid:
                    tracked_symbols.add(symbol)
                    break
        
        # Find positions to add, update, and remove
        to_add = current_symbols - tracked_symbols
        to_update = current_symbols & tracked_symbols
        to_remove = set()
        
        # Check for closed positions in registry
        for pid, pos_data in list(position_registry.items()):
            found = False
            for symbol in current_symbols:
                if symbol in pid or symbol.replace('_USDT', '') in pid:
                    found = True
                    break
            if not found:
                to_remove.add(pid)
        
        # Update position registry
        updated_registry = {}
        
        # Keep existing positions that are still active
        for pid, pos_data in position_registry.items():
            if pid not in to_remove:
                # Find matching current position
                for symbol, current_pos in current_positions.items():
                    if symbol in pid or symbol.replace('_USDT', '') in pid:
                        # Update with latest data
                        pos_data['unrealized_pnl'] = float(current_pos['upnl'])
                        pos_data['current_size'] = float(current_pos['size'])
                        pos_data['last_updated'] = datetime.now(timezone.utc).isoformat()
                        
                        # Update stage if size changed (averaging detected)
                        if pos_data.get('original_size') and float(current_pos['size']) > pos_data['original_size']:
                            if pos_data['stage'] == 'ENTRY':
                                pos_data['stage'] = 'AVERAGING'
                            pos_data['averaging_count'] = pos_data.get('averaging_count', 0) + 1
                        
                        # Update peak P&L
                        if float(current_pos['upnl']) > pos_data.get('peak_pnl', 0):
                            pos_data['peak_pnl'] = float(current_pos['upnl'])
                            pos_data['peak_pnl_timestamp'] = datetime.now(timezone.utc).isoformat()
                        
                        pos_data['exchange_info'] = current_pos
                        break
                
                updated_registry[pid] = pos_data
        
        # Add new positions
        for symbol in to_add:
            pos_data = current_positions[symbol]
            position_id = f"{symbol}_{pos_data.get('timestamp', '')}"
            
            registry_entry = {
                "position_id": position_id,
                "symbol": symbol,
                "contracts": float(pos_data['size']),
                "side": pos_data['side'],
                "entry_price": float(pos_data['entry']),
                "current_price": None,
                "unrealized_pnl": float(pos_data['upnl']),
                "margin": float(pos_data['size']) * float(pos_data['entry']) / pos_data['leverage'],
                "leverage": pos_data['leverage'],
                "created_at": datetime.fromtimestamp(int(pos_data['timestamp'])/1000, tz=timezone.utc).isoformat() if pos_data.get('timestamp') else datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "status": "ACTIVE",
                "stage": "ENTRY",
                "peak_pnl": float(pos_data['upnl']) if float(pos_data['upnl']) > 0 else 0,
                "peak_pnl_timestamp": datetime.now(timezone.utc).isoformat() if float(pos_data['upnl']) > 0 else None,
                "averaging_count": 0,
                "original_size": float(pos_data['size']),
                "current_size": float(pos_data['size']),
                "surplus_dumped": 0,
                "exchange_info": pos_data
            }
            
            updated_registry[position_id] = registry_entry
            logger.info(f"Added new position: {symbol} ({pos_data['side']}) - Size: {pos_data['size']}")
        
        # Update surplus states
        updated_surplus = {}
        for pid, pos_data in updated_registry.items():
            if pos_data['unrealized_pnl'] > 0:
                # Keep existing surplus data or create new
                if pid in surplus_states:
                    surplus_entry = surplus_states[pid]
                    # Update peak if needed
                    if pos_data['unrealized_pnl'] > surplus_entry.get('peak_pnl', 0):
                        surplus_entry['peak_pnl'] = pos_data['unrealized_pnl']
                        surplus_entry['peak_pnl_timestamp'] = datetime.now(timezone.utc).isoformat()
                else:
                    surplus_entry = {
                        "position_id": pid,
                        "original_size": pos_data['original_size'],
                        "current_size": pos_data['current_size'],
                        "surplus_size": max(0, pos_data['current_size'] - pos_data['original_size']),
                        "effective_surplus": max(0, pos_data['current_size'] - pos_data['original_size']),
                        "peak_pnl": pos_data['unrealized_pnl'],
                        "peak_pnl_timestamp": datetime.now(timezone.utc).isoformat(),
                        "dump_stage": 0,
                        "first_dump_size": 0.0,
                        "second_dump_size": 0.0,
                        "total_dumped": 0.0
                    }
                
                updated_surplus[pid] = surplus_entry
        
        # Update averaging history (keep existing, remove closed)
        updated_averaging = {}
        for pid, avg_data in averaging_history.items():
            if pid in updated_registry:
                updated_averaging[pid] = avg_data
        
        # Save all updated files
        changes_made = False
        
        if updated_registry != position_registry:
            if save_json(POSITION_REGISTRY_PATH, updated_registry):
                logger.info(f"Position Registry updated: {len(updated_registry)} active positions")
                changes_made = True
        
        if updated_surplus != surplus_states:
            if save_json(SURPLUS_STATES_PATH, updated_surplus):
                logger.info(f"Surplus States updated: {len(updated_surplus)} positions tracked")
                changes_made = True
        
        if updated_averaging != averaging_history:
            if save_json(AVERAGING_HISTORY_PATH, updated_averaging):
                logger.info(f"Averaging History updated: {len(updated_averaging)} positions with averaging")
                changes_made = True
        
        # Log summary
        if changes_made:
            logger.info(f"Sync complete - Active: {len(updated_registry)}, Added: {len(to_add)}, Removed: {len(to_remove)}")
        
        # Log removed positions
        for pid in to_remove:
            logger.info(f"Removed closed position: {pid}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error during sync: {e}")
        return False

def main():
    """Main service loop"""
    global running
    
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Write PID file
    try:
        with open(PID_FILE, 'w') as f:
            f.write(str(os.getpid()))
        logger.info(f"Position Registry Sync Service started (PID: {os.getpid()})")
    except Exception as e:
        logger.error(f"Failed to write PID file: {e}")
    
    # Initial sync
    sync_positions()
    
    # Main loop
    last_sync = time.time()
    
    while running:
        try:
            current_time = time.time()
            
            # Sync every interval
            if current_time - last_sync >= SYNC_INTERVAL:
                sync_positions()
                last_sync = current_time
            
            # Sleep briefly to avoid CPU usage
            time.sleep(1)
            
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down...")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
            time.sleep(5)  # Wait before retrying
    
    # Cleanup
    try:
        if os.path.exists(PID_FILE):
            os.remove(PID_FILE)
    except:
        pass
    
    logger.info("Position Registry Sync Service stopped")

if __name__ == "__main__":
    main()