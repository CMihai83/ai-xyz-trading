#!/usr/bin/env python3
import ccxt
import json
import os
from datetime import datetime

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_SECRET'),
    'password': os.getenv('BITGET_PASSWORD'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

print("=== CHECKING ESPORTS POSITION FOR SURPLUS DUMP ===\n")

# Get position details
try:
    positions = exchange.fetch_positions()
    esport_found = False
    
    for pos in positions:
        if 'ESPORT' in pos['symbol'].upper():
            esport_found = True
            print(f'✅ Found ESPORTS position: {pos["symbol"]}')
            print(f'   Side: {pos["side"].upper()}')
            print(f'   Contracts: {pos["contracts"]}')
            print(f'   Notional Size: ${pos.get("notional", 0):.2f}')
            print(f'   Entry Price: ${pos.get("markPrice", 0):.6f}')
            print(f'   Current Price: ${pos.get("markPrice", 0):.6f}')
            print(f'   Unrealized PNL: ${pos.get("unrealizedPnl", 0):.4f}')
            print(f'   PNL Percentage: {pos.get("percentage", 0):.2f}%')
            print(f'   Initial Margin: ${pos.get("initialMargin", 0):.2f}')
            
            # Check surplus dump eligibility based on cardinal rules
            pnl_pct = pos.get('percentage', 0)
            print(f'\n=== SURPLUS DUMP ANALYSIS ===')
            
            # According to cardinal rules:
            # - Positions enter Surplus Dump zone when UPNL > +0.15% AND averaging_steps > 0
            # - Since this is a SHORT position with +16.7% profit, check if averaging occurred
            
            if pnl_pct > 0.15:
                print(f'✅ PNL Check: {pnl_pct:.2f}% > 0.15% threshold')
                
                # Check position registry for averaging steps
                registry_file = '/app/services/position-manager/position_registry.json'
                averaging_steps = 0
                
                if os.path.exists(registry_file):
                    with open(registry_file, 'r') as f:
                        registry = json.load(f)
                        esport_key = None
                        for key in registry.get('positions', {}):
                            if 'ESPORT' in key.upper():
                                esport_key = key
                                break
                        
                        if esport_key:
                            pos_data = registry['positions'][esport_key]
                            averaging_steps = pos_data.get('averaging_steps', 0)
                            print(f'   Averaging Steps Taken: {averaging_steps}')
                            
                            if averaging_steps > 0:
                                print(f'✅ ELIGIBLE FOR SURPLUS DUMP ZONE')
                                print(f'   Reason: UPNL > 0.15% AND averaging_steps > 0')
                                
                                # Calculate surplus dump levels
                                peak_upnl = pos_data.get('peak_upnl', pos.get('unrealizedPnl', 0))
                                print(f'\n   SURPLUS DUMP EXECUTION LEVELS:')
                                print(f'   Peak UPNL tracked: ${peak_upnl:.4f}')
                                print(f'   Level 1 (85% of peak): Dump 50% at ${peak_upnl * 0.85:.4f}')
                                print(f'   Level 2 (50% of peak): Dump remaining 50% at ${peak_upnl * 0.50:.4f}')
                                
                                # Check current dump stage
                                dump_stage = pos_data.get('surplus_dump_stage', 'none')
                                print(f'\n   Current Dump Stage: {dump_stage}')
                                
                                if dump_stage == 'none':
                                    print('   ⚠️  Surplus dump not yet initiated')
                                elif dump_stage == 'partial':
                                    print('   ✅ First 50% dump completed, waiting for Level 2')
                                elif dump_stage == 'complete':
                                    print('   ✅ Surplus dump completed, position reset to neutral')
                            else:
                                print(f'❌ NOT ELIGIBLE FOR SURPLUS DUMP')
                                print(f'   Reason: No averaging steps taken (averaging_steps = 0)')
                                print(f'   Note: Position is in PROFIT TAKING zone instead')
                else:
                    print('⚠️  Cannot verify averaging steps - registry file not found')
                    print('   Assuming standard profit-taking zone')
                    
            else:
                print(f'❌ NOT ELIGIBLE: PNL {pnl_pct:.2f}% < 0.15% threshold')
                
                if pnl_pct < -0.15:
                    print(f'   Position would be in AVERAGING zone (PNL < -0.15%)')
                else:
                    print(f'   Position is in NEUTRAL zone (-0.15% < PNL < +0.15%)')
    
    if not esport_found:
        print("❌ No ESPORTS position found on exchange")
        
except Exception as e:
    print(f"❌ Error fetching positions: {e}")

print("\n=== SURPLUS DUMP LOGIC VERIFICATION ===")
print("According to Cardinal Rules:")
print("1. Surplus Dump triggers when: UPNL > +0.15% AND averaging_steps > 0")
print("2. Execution: 50% at 85% of peak, 50% at 50% of peak")
print("3. After dump: averaging_steps reset to 0, position returns to Neutral")
print("4. If no averaging occurred: Position enters Profit Taking zone instead")
