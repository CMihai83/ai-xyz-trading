#!/usr/bin/env python3
"""
Position format mapper for exchange_data.json
Ensures positions have the correct field names expected by the trading engine.
"""

import json
import time
from pathlib import Path
from datetime import datetime

class PositionMapper:
    def __init__(self):
        self.exchange_data_path = Path('/root/server_deployment/exchange_data.json')
        self.fixed_data_path = Path('/root/server_deployment/exchange_data_fixed.json')
    
    def map_positions(self):
        """Map position fields to the format expected by trading engine"""
        try:
            # Read exchange data
            with open(self.exchange_data_path, 'r') as f:
                data = json.load(f)
            
            # Map position fields
            if 'bitget_positions' in data:
                for symbol, position in data['bitget_positions'].items():
                    # Map 'size' to 'contracts' (both fields will exist)
                    if 'size' in position:
                        position['contracts'] = float(position['size'])
                    
                    # Ensure entry_price exists
                    if 'entry' in position and 'entry_price' not in position:
                        position['entry_price'] = float(position['entry'])
                    
                    # Ensure mark_price exists (use entry if not available)
                    if 'mark_price' not in position:
                        position['mark_price'] = float(position.get('entry', 0))
                    
                    # Map upnl to unrealizedPnl
                    if 'upnl' in position and 'unrealizedPnl' not in position:
                        position['unrealizedPnl'] = float(position['upnl'])
                    
                    # Calculate P&L percentage if not present
                    if 'pnl_pct' not in position and position.get('entry_price'):
                        entry = float(position['entry_price'])
                        if entry > 0:
                            current = float(position.get('mark_price', entry))
                            side = position.get('side', 'long')
                            if side == 'long':
                                position['pnl_pct'] = ((current - entry) / entry) * 100
                            else:
                                position['pnl_pct'] = ((entry - current) / entry) * 100
            
            # Write fixed data
            with open(self.fixed_data_path, 'w') as f:
                json.dump(data, f, indent=2)
            
            return data
            
        except Exception as e:
            print(f"Error mapping positions: {e}")
            return None
    
    def run_continuous(self):
        """Run continuous mapping"""
        print("Starting position format mapper...")
        while True:
            try:
                self.map_positions()
                time.sleep(1)  # Map every second
            except KeyboardInterrupt:
                print("\nStopping position mapper...")
                break
            except Exception as e:
                print(f"Error in continuous mapping: {e}")
                time.sleep(5)

if __name__ == "__main__":
    mapper = PositionMapper()
    mapper.run_continuous()
