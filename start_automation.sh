#!/bin/bash

# AI-XYZ Automated System Startup Script
# Handles all automated processes for position management

echo "=== Starting AI-XYZ Automation System ==="
echo "Time: $(date)"

# Set environment
export PYTHONPATH=/root/ai_xyz:$PYTHONPATH
source /root/ai_xyz/.env

# Check if already running
if pgrep -f "automated_position_manager.py" > /dev/null; then
    echo "⚠️  Automation already running"
    exit 1
fi

# Create log directory
mkdir -p /var/log/aixyz
mkdir -p /root/ai_xyz/logs

# Start automated position manager in background
echo "Starting Automated Position Manager..."
nohup python3 /root/ai_xyz/automated_position_manager.py > /var/log/aixyz/automation.log 2>&1 &
APM_PID=$!
echo "  PID: $APM_PID"

# Save PID for management
echo $APM_PID > /root/ai_xyz/automation.pid

# Wait for startup
sleep 5

# Verify it's running
if ps -p $APM_PID > /dev/null; then
    echo "✅ Automated Position Manager started successfully"
else
    echo "❌ Failed to start Automated Position Manager"
    exit 1
fi

# Start compliance monitor in background
echo "Starting Compliance Monitor..."
cat > /tmp/compliance_monitor.py << 'EOF'
import asyncio
import json
from datetime import datetime
import sys
sys.path.append('/root/ai_xyz')
from automated_position_manager import AutomatedPositionManager

async def monitor_compliance():
    manager = AutomatedPositionManager()
    while True:
        try:
            status = await manager.get_status()
            
            # Check for zone mismatches
            mismatches = []
            for pos in status['positions']:
                if pos['zone'] != pos['correct_zone']:
                    mismatches.append({
                        'symbol': pos['symbol'],
                        'current': pos['zone'],
                        'correct': pos['correct_zone']
                    })
            
            if mismatches:
                print(f"[{datetime.now()}] Zone mismatches detected: {mismatches}")
                
            # Check for surplus eligible positions
            surplus_eligible = [p for p in status['positions'] if p['surplus_eligible']]
            if surplus_eligible:
                print(f"[{datetime.now()}] Surplus eligible positions: {[p['symbol'] for p in surplus_eligible]}")
                
            # Save status
            with open('/root/ai_xyz/logs/automation_status.json', 'w') as f:
                json.dump(status, f, indent=2)
                
        except Exception as e:
            print(f"[{datetime.now()}] Monitor error: {e}")
            
        await asyncio.sleep(30)

asyncio.run(monitor_compliance())
EOF

nohup python3 /tmp/compliance_monitor.py > /var/log/aixyz/compliance.log 2>&1 &
CM_PID=$!
echo "  Compliance Monitor PID: $CM_PID"
echo $CM_PID > /root/ai_xyz/compliance_monitor.pid

echo ""
echo "=== Automation System Started ==="
echo "Main Process: $APM_PID"
echo "Compliance Monitor: $CM_PID"
echo ""
echo "Logs:"
echo "  - Main: /var/log/aixyz/automation.log"
echo "  - Compliance: /var/log/aixyz/compliance.log"
echo "  - Alerts: /root/ai_xyz/logs/alerts.json"
echo ""
echo "To stop: ./stop_automation.sh"