#!/usr/bin/env python3
"""
Patch the averaging system to use stored entry prices
This ensures averaging works automatically even when exchange API returns 0.0
"""

import json
import asyncio
import ccxt.async_support as ccxt
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

class AveragingSystemPatch:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'), 
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        
    async def patch_exchange_data_with_entry_prices(self):
        """
        Patch exchange_data.json with proper entry prices from position_state.json
        This makes averaging calculations work properly
        """
        # Load position state with stored entry prices
        with open('/app/position_state.json', 'r') as f:
            position_state = json.load(f)
            
        # Load exchange data
        with open('/root/server_deployment/exchange_data.json', 'r') as f:
            exchange_data = json.load(f)
            
        stored_positions = position_state.get('active_positions', {})
        exchange_positions = exchange_data.get('bitget_positions', {})
        
        patched_count = 0
        
        print("="*60)
        print("PATCHING EXCHANGE DATA WITH STORED ENTRY PRICES")
        print("="*60)
        
        # Create patched exchange data
        patched_positions = {}
        
        for symbol, stored_pos in stored_positions.items():
            # Find matching exchange position
            # Convert HOLO/USDT:USDT to HOLO_USDT_USDT
            base = symbol.split('/')[0]
            exchange_key = f"{base}_USDT_USDT"
            
            if exchange_key in exchange_positions:
                # Copy exchange position
                patched_pos = exchange_positions[exchange_key].copy()
                
                # Inject proper entry price
                old_entry = patched_pos.get('entry', '0.0')
                new_entry = str(stored_pos['entry_price'])
                patched_pos['entry'] = new_entry
                
                # Also calculate correct UPNL percentage
                current_price = float(patched_pos.get('current_price', 0))
                entry_price = stored_pos['entry_price']
                contracts = float(patched_pos.get('size', 0))
                side = patched_pos.get('side')
                
                if current_price > 0 and entry_price > 0 and contracts > 0:
                    # Calculate UPNL
                    if side == 'long':
                        upnl_pct = ((current_price - entry_price) / entry_price) * 100
                        upnl_dollar = (current_price - entry_price) * contracts
                    else:  # short
                        upnl_pct = ((entry_price - current_price) / entry_price) * 100
                        upnl_dollar = (entry_price - current_price) * contracts
                    
                    # Add calculated fields
                    patched_pos['upnl_percentage'] = upnl_pct
                    patched_pos['upnl_corrected'] = str(upnl_dollar)
                    
                    print(f"\n✅ Patched {symbol}:")
                    print(f"   Old entry: {old_entry} → New entry: {new_entry}")
                    print(f"   Current price: ${current_price:.6f}")
                    print(f"   UPNL: ${upnl_dollar:.2f} ({upnl_pct:.2f}%)")
                    
                    if upnl_pct < -15:
                        print(f"   ⚠️ NEEDS AVERAGING (loss > 15%)")
                    
                    patched_count += 1
                    
                patched_positions[exchange_key] = patched_pos
            else:
                print(f"\n⚠️ {symbol} not found in exchange data")
                
        # Copy remaining exchange positions not in position_state
        for key, pos in exchange_positions.items():
            if key not in patched_positions:
                patched_positions[key] = pos
                
        # Update exchange data
        exchange_data['bitget_positions'] = patched_positions
        exchange_data['last_patch'] = datetime.utcnow().isoformat()
        exchange_data['patch_applied'] = True
        
        # Save patched exchange data
        with open('/root/server_deployment/exchange_data_patched.json', 'w') as f:
            json.dump(exchange_data, f, indent=2)
            
        print(f"\n" + "="*60)
        print(f"PATCH COMPLETE:")
        print(f"✅ Patched {patched_count} positions with correct entry prices")
        print(f"💾 Saved to exchange_data_patched.json")
        
        # Also create a trigger file for averaging system
        trigger_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'positions_needing_averaging': []
        }
        
        for symbol, stored_pos in stored_positions.items():
            exchange_key = symbol.replace('/', '_').replace(':', '_')
            if exchange_key in patched_positions:
                pos = patched_positions[exchange_key]
                if 'upnl_percentage' in pos and pos['upnl_percentage'] < -15:
                    trigger_data['positions_needing_averaging'].append({
                        'symbol': symbol,
                        'upnl_pct': pos['upnl_percentage'],
                        'entry_price': stored_pos['entry_price'],
                        'current_price': float(pos.get('markPrice', 0))
                    })
                    
        with open('/app/averaging_triggers.json', 'w') as f:
            json.dump(trigger_data, f, indent=2)
            
        if trigger_data['positions_needing_averaging']:
            print(f"\n⚠️ AVERAGING NEEDED for {len(trigger_data['positions_needing_averaging'])} positions")
            print(f"💾 Triggers saved to averaging_triggers.json")
        else:
            print(f"\n✅ No positions currently need averaging")
            
        return patched_count

async def main():
    patch = AveragingSystemPatch()
    await patch.patch_exchange_data_with_entry_prices()
    await patch.exchange.close()

if __name__ == "__main__":
    asyncio.run(main())