#!/usr/bin/env python3
"""Analyze current positions and surplus dump logic"""

import json
from datetime import datetime

# Load position state
with open('/app/position_state.json', 'r') as f:
    state = json.load(f)

print('=== CURRENT POSITION ANALYSIS FOR SURPLUS DUMP ===')
print(f'Timestamp: {state["timestamp"]}')
print()

for symbol in state['active_positions']:
    pos = state['active_positions'][symbol]
    zone = state['position_zones'][symbol]
    steps = state['averaging_steps'][symbol]
    peak = state['peak_upnl'][symbol]
    stage = state['surplus_dump_stage'][symbol]
    
    # Calculate surplus (positions with averaging steps have larger size)
    original_size = state['original_sizes'][symbol]
    current_size = pos['amount']
    surplus_size = current_size - original_size if current_size > original_size else 0
    
    print(f'{symbol}:')
    print(f'  Zone: {zone}')
    print(f'  Current Size: {current_size:.1f}')
    print(f'  Original Size: {original_size:.1f}') 
    print(f'  Surplus Size: {surplus_size:.1f}')
    print(f'  Averaging Steps: {steps}')
    print(f'  Peak UPNL: ${peak:.4f}')
    print(f'  Surplus Dump Stage: {stage}')
    
    # Check for surplus dump eligibility according to specs
    if zone == 'PROFIT_TAKING' and steps > 0:
        print(f'  ⚠️  ISSUE: Position has averaging steps ({steps}) but in PROFIT_TAKING zone')
        print(f'      According to Cardinal Rule 5, should be in SURPLUS_DUMP zone!')
        print(f'      Surplus Dump Thresholds:')
        print(f'        - Stage 1 at 85% of peak: ${peak * 0.85:.4f}')
        print(f'        - Stage 2 at 50% of peak: ${peak * 0.50:.4f}')  # Should be 30% according to some specs
    elif zone == 'SURPLUS_DUMP':
        print(f'  ✅ Correctly in SURPLUS_DUMP zone')
        print(f'      85% threshold: ${peak * 0.85:.4f}')
        print(f'      50% threshold: ${peak * 0.50:.4f}')
    elif steps > 0 and surplus_size > 0:
        print(f'  ⚠️  Position has surplus ({surplus_size:.1f}) but zone is {zone}')
        
    print()

print('=== SURPLUS DUMP SPECIFICATION ANALYSIS ===')
print('Current Implementation (surplus_dump_manager.py):')
print('  - Single dump at 70% of peak (100% of surplus)')
print('  - Only one stage implemented')
print()
print('Original Specification (AI_Trading_System_Complete_Discussion.md):')
print('  - Stage 1: 50% of surplus at 85% of peak')  
print('  - Stage 2: Remaining 50% at 50% of peak')
print('  - Two-stage hierarchical dumping')
print()
print('Cardinal Rule 5:')
print('  - First dump: 50% of surplus at 85% of peak UPNL') 
print('  - Second dump: Remaining surplus at 50% of peak (size-adjusted)')
print('  - After full dump: Reset averaging counter and peak tracking')
print()
print('DISCREPANCY FOUND:')
print('  Implementation uses 70% single dump vs specification 85%+50% dual dump')