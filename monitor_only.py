#!/usr/bin/env python3
"""
Monitoring-only mode - skips scanner, just monitors existing positions
"""
import sys
sys.path.insert(0, '/root/ai_xyz')

from aixyz_continuous_profit_system import AIXYZSystem
import time

if __name__ == "__main__":
    print("Starting AI-XYZ in MONITORING-ONLY mode...")
    system = AIXYZSystem()
    
    print(f"\n✅ Loaded {len(system.active_positions)} active positions")
    for symbol in system.active_positions:
        print(f"   - {symbol}")
    
    print("\n🔍 Starting monitoring loop (Ctrl+C to stop)...")
    system.running = True
    
    try:
        while system.running:
            system.monitor_positions()
            print(f"\n⏱️  Next check in 5 seconds...")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\n\n⛔ Shutting down...")
        system.running = False
