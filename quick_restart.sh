#!/bin/bash
cd /root/ai_xyz
pkill -9 -f "python.*aixyz_continuous"
sleep 2
nohup python3 /root/ai_xyz/aixyz_continuous_profit_system.py > /tmp/aixyz_live.log 2>&1 &
PID=$!
echo $PID > /root/ai_xyz/aixyz.pid
echo "Started AI-XYZ Trading System"
echo "PID: $PID"
echo "Log: tail -f /tmp/aixyz_live.log"
sleep 5
if ps -p $PID > /dev/null; then
    echo "✅ System running"
else
    echo "❌ Failed to start"
fi
