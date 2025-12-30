#!/usr/bin/env python3
"""Analyze BB position for Stage 2 surplus dump trigger"""

import json
import asyncio
import sys
import ccxt

sys.path.insert(0, '/app')
sys.path.insert(0, '/app/core')

from core.live_positions_registry import LivePositionsRegistry
from core.surplus_dump_manager import SurplusDumpManager

async def analyze_bb():
    # Get current positions from exchange
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
    
    positions = exchange.fetch_positions()
    bb_pos = None
    
    for pos in positions:
        if 'BB' in pos['symbol']:
            bb_pos = pos
            break
    
    if bb_pos:
        print('BB Position Found:')
        print(f"  Symbol: {bb_pos['symbol']}")
        print(f"  Side: {bb_pos['side']}")
        print(f"  Contracts: {bb_pos['contracts']}")
        print(f"  UPNL: ${bb_pos['unrealizedPnl']:.2f} ({bb_pos['percentage']:.1f}%)")
        print(f"  Mark Price: ${bb_pos['markPrice']:.4f}")
        print(f"  Entry Price: ${bb_pos['entryPrice']:.4f}")
        print()
        
        # Initialize registry to check stored data
        registry = LivePositionsRegistry()
        await registry.initialize()
        surplus_manager = SurplusDumpManager(registry)
        
        # Get stored position
        stored_positions = await registry.get_all_positions()
        stored_bb = None
        
        for pos in stored_positions:
            if 'BB' in pos.symbol:
                stored_bb = pos
                break
        
        if stored_bb:
            print('Stored Position Data:')
            print(f'  Current Zone: {stored_bb.current_zone}')
            print(f'  Peak UPNL: ${stored_bb.peak_upnl:.2f}')
            print(f'  Surplus Size: {stored_bb.surplus_size}')
            print(f'  Surplus Dump Stage: {stored_bb.surplus_dump_stage}')
            print(f'  Averaging Steps: {stored_bb.averaging_steps_taken}')
            print()
            
            # Calculate thresholds
            current_upnl = bb_pos['unrealizedPnl']
            
            # For Stage 2, we need peak UPNL
            if stored_bb.peak_upnl > 0:
                stage1_threshold = stored_bb.peak_upnl * 0.85
                stage2_threshold = stored_bb.peak_upnl * 0.30
                
                print('Stage 2 Surplus Dump Analysis:')
                print(f'  Peak UPNL: ${stored_bb.peak_upnl:.2f}')
                print(f'  Current UPNL: ${current_upnl:.2f}')
                print()
                print(f'  Stage 1 Threshold (85% of peak): ${stage1_threshold:.2f}')
                print(f'  Stage 2 Threshold (30% of peak): ${stage2_threshold:.2f}')
                print()
                
                if stored_bb.surplus_dump_stage == 0:
                    print('  Status: ⏳ Waiting for Stage 1 trigger')
                    if current_upnl <= stage1_threshold:
                        print(f'  🔴 READY FOR STAGE 1! Current ${current_upnl:.2f} <= ${stage1_threshold:.2f}')
                    else:
                        print(f'  Need UPNL to drop by: ${current_upnl - stage1_threshold:.2f}')
                        
                elif stored_bb.surplus_dump_stage == 1:
                    print('  Status: ✅ Stage 1 complete, waiting for Stage 2')
                    if current_upnl <= stage2_threshold:
                        print(f'  🔴 READY FOR STAGE 2! Current ${current_upnl:.2f} <= ${stage2_threshold:.2f}')
                    else:
                        print(f'  Need UPNL to drop by: ${current_upnl - stage2_threshold:.2f}')
                        print(f'  Price needs to move against position by: {((current_upnl - stage2_threshold) / current_upnl * 100):.1f}%')
                        
                else:
                    print('  Status: ✅ Both stages completed')
            else:
                print('⚠️  No peak UPNL recorded yet - position needs to be profitable first')
                
            # Check if position should be in surplus dump zone
            if stored_bb.averaging_steps_taken > 0 and current_upnl > 0.15:
                print()
                print('⚠️  ZONE CHECK:')
                print(f'  Position SHOULD be in SURPLUS_DUMP zone!')
                print(f'  Reason: Has {stored_bb.averaging_steps_taken} averaging steps and UPNL > $0.15')
                
    else:
        print('No BB position found in exchange')

if __name__ == "__main__":
    asyncio.run(analyze_bb())