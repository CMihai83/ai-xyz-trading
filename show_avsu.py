#!/usr/bin/env python3
import json

# Load position state
with open('/app/position_state.json', 'r') as f:
    state = json.load(f)

print('======== AVSU STATUS ========')
for symbol, pos_data in state.get('active_positions', {}).items():
    print(f'\n{symbol}:')
    print(f'  Entry: ${pos_data.get("entry_price", "N/A")}')
    print(f'  Current: ${pos_data.get("current_price", "N/A")}')
    print(f'  Amount: {pos_data.get("amount", "N/A")}')
    print(f'  Side: {pos_data.get("side", "N/A").upper()}')
    print(f'  Leverage: {pos_data.get("leverage", "N/A")}x')
    print(f'  Zone: {state["position_zones"].get(symbol, "N/A")}')
    print(f'  Averaging Steps: {state["averaging_steps"].get(symbol, 0)}')
    print(f'  Original Size: {state["original_sizes"].get(symbol, "N/A")}')
    
    # Calculate current size vs original
    if symbol in state['original_sizes']:
        multiplier = pos_data.get('amount', 0) / state['original_sizes'][symbol]
        print(f'  Size Multiplier: {multiplier:.2f}x')
    
    # Check surplus dump status
    if state['surplus_dump_stage'].get(symbol, 0) > 0:
        print(f'  💰 Surplus Dump Stage: {state["surplus_dump_stage"][symbol]}')
        print(f'  Peak UPNL: ${state["peak_upnl"].get(symbol, 0):.4f}')
    elif state["peak_upnl"].get(symbol, 0) > 0:
        print(f'  Peak UPNL: ${state["peak_upnl"].get(symbol, 0):.4f}')