#!/usr/bin/env python3
"""
Trigger a test trade in the AI Trading System
"""

import requests
import json

def trigger_trade():
    # First, check the scanner for signals
    scanner_url = "http://localhost:8001/futures/scan"
    
    try:
        response = requests.get(scanner_url)
        if response.status_code == 200:
            data = response.json()
            print("📊 Current Signals:")
            print(json.dumps(data, indent=2))
            
            # If there are signals, they should be processed automatically
            if data.get('signals'):
                print("\n✅ Signals found! Trading engine should process them.")
            else:
                print("\n⚠️ No signals found. Waiting for market conditions...")
        else:
            print(f"❌ Scanner error: {response.status_code}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    # Check positions
    positions_url = "http://localhost:8000/futures/positions"
    try:
        response = requests.get(positions_url)
        if response.status_code == 200:
            data = response.json()
            print("\n📈 Current Positions:")
            print(json.dumps(data, indent=2))
        else:
            print(f"\n❌ Positions error: {response.status_code}")
    except Exception as e:
        print(f"❌ Error checking positions: {e}")

if __name__ == "__main__":
    print("🚀 AI TRADING SYSTEM - LIVE TRADE TRIGGER")
    print("=" * 50)
    trigger_trade()