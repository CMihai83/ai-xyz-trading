#!/bin/bash

# Stop AI-XYZ Automation System

echo "=== Stopping AI-XYZ Automation System ==="

# Stop automated position manager
if [ -f /root/ai_xyz/automation.pid ]; then
    APM_PID=$(cat /root/ai_xyz/automation.pid)
    if ps -p $APM_PID > /dev/null 2>&1; then
        echo "Stopping Automated Position Manager (PID: $APM_PID)..."
        kill $APM_PID
        sleep 2
        if ps -p $APM_PID > /dev/null 2>&1; then
            echo "Force killing..."
            kill -9 $APM_PID
        fi
    fi
    rm /root/ai_xyz/automation.pid
fi

# Stop compliance monitor
if [ -f /root/ai_xyz/compliance_monitor.pid ]; then
    CM_PID=$(cat /root/ai_xyz/compliance_monitor.pid)
    if ps -p $CM_PID > /dev/null 2>&1; then
        echo "Stopping Compliance Monitor (PID: $CM_PID)..."
        kill $CM_PID
    fi
    rm /root/ai_xyz/compliance_monitor.pid
fi

# Kill any remaining processes
pkill -f "automated_position_manager.py"
pkill -f "compliance_monitor.py"

echo "✅ Automation system stopped"