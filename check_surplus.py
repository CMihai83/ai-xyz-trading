#!/usr/bin/env python3
import json
import os

# Load exchange data
exchange_data_file = "/root/server_deployment/exchange_data.json"
if os.path.exists(exchange_data_file):
    with open(exchange_data_file, "r") as f:
        exchange_data = json.load(f)
    
    bitget_positions = exchange_data.get("bitget_positions", {})
    
    # Find BB position
    bb_position = None
    for symbol, pos in bitget_positions.items():
        if "BB" in symbol:
            bb_position = pos
            print(f"BB Position from Exchange:")
            print(f"  Symbol: {symbol}")
            print(f"  Side: {pos.get('side', 'N/A')}")
            print(f"  Size: {pos.get('size', 0)}")
            print(f"  Unrealized PNL: ${pos.get('unrealizedPnl', 0):.4f}")
            print(f"  Entry Price: {pos.get('averagePrice', 0)}")
            print(f"  Mark Price: {pos.get('markPrice', 0)}")
            break
    
    if not bb_position:
        print("BB position not found in exchange data")
else:
    print("Exchange data file not found")

# Check AI-XYZ position state
with open("/app/position_state.json", "r") as f:
    ai_data = json.load(f)

bb_peak = ai_data["peak_upnl"].get("BB/USDT:USDT", 0)
bb_steps = ai_data["averaging_steps"].get("BB/USDT:USDT", 0)
bb_zone = ai_data["position_zones"].get("BB/USDT:USDT", "N/A")

print(f"\nSurplus Dump Analysis:")
print(f"  Current Zone: {bb_zone}")
print(f"  Peak UPNL: ${bb_peak:.4f}")
print(f"  Averaging Steps: {bb_steps}")

if bb_peak > 0:
    stage1 = bb_peak * 0.85
    stage2 = bb_peak * 0.30
    print(f"  Stage 1 Threshold (85%): ${stage1:.4f}")
    print(f"  Stage 2 Threshold (30%): ${stage2:.4f}")
    
    if bb_position:
        current_upnl = bb_position.get("unrealizedPnl", 0)
        print(f"\n  Current UPNL: ${current_upnl:.4f}")
        
        if bb_steps > 0:  # Has averaging
            if current_upnl >= stage1:
                print("  ⚠️ Stage 1 surplus dump should trigger!")
            elif current_upnl >= stage2:
                print("  ⚠️ Stage 2 surplus dump should trigger!")
            elif current_upnl < 0:
                print("  Position is currently at a loss (no surplus dump)")
            else:
                print(f"  Position below Stage 2 threshold (${current_upnl:.4f} < ${stage2:.4f})")