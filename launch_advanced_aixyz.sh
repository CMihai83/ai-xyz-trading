#!/bin/bash

# Launch AI-XYZ with Advanced Opportunity Engine in background

echo "======================================================================="
echo "LAUNCHING AI-XYZ WITH ADVANCED OPPORTUNITY ENGINE"
echo "======================================================================="

# Kill any existing AI-XYZ processes
pkill -f aixyz_continuous_profit_system.py 2>/dev/null

# Start in background with logging
nohup python3 /root/ai_xyz/aixyz_continuous_profit_system.py > /root/ai_xyz/aixyz_advanced.log 2>&1 &
PID=$!

echo "✅ AI-XYZ started with PID: $PID"
echo "📝 Logs: /root/ai_xyz/aixyz_advanced.log"
echo ""
echo "Waiting for system to initialize..."
sleep 5

# Check if it's running and using advanced engine
if ps -p $PID > /dev/null; then
    echo "✅ System is running"
    echo ""
    echo "Checking scanner type..."
    grep -i "advanced\|elliott\|fibonacci" /root/ai_xyz/aixyz_advanced.log | head -5
    echo ""
    echo "First scan results:"
    tail -20 /root/ai_xyz/aixyz_advanced.log
else
    echo "❌ System failed to start"
    echo "Last error:"
    tail -10 /root/ai_xyz/aixyz_advanced.log
fi

echo ""
echo "======================================================================="
echo "Commands:"
echo "  View logs:    tail -f /root/ai_xyz/aixyz_advanced.log"
echo "  Stop system:  kill $PID"
echo "  Check status: ps -p $PID"
echo "======================================================================="