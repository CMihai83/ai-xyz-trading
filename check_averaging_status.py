#!/usr/bin/env python3

import json
import os
import sys
sys.path.insert(0, "/app")

def check_averaging_status():
    # Check for position registry file
    registry_file = "/app/data/position_registry.json"
    if os.path.exists(registry_file):
        with open(registry_file, "r") as f:
            registry = json.load(f)
        
        print("=== LIVE POSITIONS AVERAGING & SURPLUS STATUS ===\n")
        
        if registry.get("positions"):
            for symbol, pos in registry["positions"].items():
                print(f"Symbol: {symbol}")
                side = pos.get("side", "N/A")
                entry_price = pos.get("entry_price", 0)
                current_price = pos.get("current_price", 0)
                initial_size = pos.get("initial_size", 0)
                current_size = pos.get("current_size", 0)
                weighted_avg = pos.get("weighted_avg_price", 0)
                unrealized_pnl = pos.get("unrealized_pnl", 0)
                pnl_percentage = pos.get("pnl_percentage", 0)
                zone = pos.get("zone", "NEUTRAL")
                
                print(f"  Side: {side}")
                print(f"  Entry Price: ${entry_price:.4f}")
                print(f"  Current Price: ${current_price:.4f}")
                print(f"  Initial Size: {initial_size:.4f}")
                print(f"  Current Size: {current_size:.4f}")
                print(f"  Weighted Avg Price: ${weighted_avg:.4f}")
                print(f"  Unrealized PNL: ${unrealized_pnl:.2f} ({pnl_percentage:.2f}%)")
                print(f"  Current Zone: {zone}")
                
                # Averaging information
                averaging_steps = pos.get("averaging_steps", [])
                print(f"  Averaging Steps Taken: {len(averaging_steps)}")
                if averaging_steps:
                    print("  Averaging History:")
                    for i, step in enumerate(averaging_steps, 1):
                        step_price = step.get("price", 0)
                        step_size = step.get("size", 0)
                        step_pnl = step.get("pnl_at_averaging", 0)
                        print(f"    Step {i}: Price ${step_price:.4f}, Size {step_size:.4f}, At PNL {step_pnl:.2f}%")
                
                # Surplus Dump Status
                if zone == "SURPLUS_DUMP":
                    peak_upnl = pos.get("peak_upnl", 0)
                    surplus_size = pos.get("surplus_size", 0)
                    dumps_completed = pos.get("dumps_completed", 0)
                    
                    print(f"  === SURPLUS DUMP ACTIVE ===")
                    print(f"  Peak UPNL: ${peak_upnl:.2f}")
                    print(f"  Surplus Size: {surplus_size:.4f}")
                    print(f"  Dumps Completed: {dumps_completed}")
                    print(f"  85% Dump Target: ${peak_upnl * 0.85:.2f}")
                    print(f"  50% Dump Target: ${peak_upnl * 0.50:.2f}")
                elif len(averaging_steps) > 0 and pnl_percentage > 0.15:
                    print(f"  *** Position eligible for SURPLUS DUMP (has averaging, PNL > 0.15%) ***")
                
                print()
        else:
            print("No active positions found in registry")
    else:
        print("Position registry file not found")
    
    # Also check exchange data for comparison
    exchange_file = "/app/data/exchange_data.json"
    if os.path.exists(exchange_file):
        with open(exchange_file, "r") as f:
            exchange_data = json.load(f)
        
        if exchange_data.get("positions"):
            print("\n=== EXCHANGE POSITIONS (for verification) ===")
            for pos in exchange_data["positions"]:
                symbol = pos.get("symbol", "N/A")
                if "USDT" in symbol:
                    size = pos.get("size", 0)
                    avg_price = pos.get("avgPrice", 0)
                    upnl = pos.get("unrealizedPnl", 0)
                    print(f"{symbol}: Size={size:.4f}, Avg=${avg_price:.4f}, UPNL=${upnl:.2f}")

if __name__ == "__main__":
    check_averaging_status()
