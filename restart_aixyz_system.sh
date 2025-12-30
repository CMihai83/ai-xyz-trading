#!/bin/bash

echo "==================================="
echo "Restarting AI-XYZ Trading System"
echo "==================================="
echo ""

# Stop existing processes
echo "Stopping existing processes..."
if [ -f /root/ai_xyz/aixyz.pid ]; then
    OLD_PID=$(cat /root/ai_xyz/aixyz.pid)
    if ps -p $OLD_PID > /dev/null; then
        kill $OLD_PID
        echo "Stopped process $OLD_PID"
    fi
fi

pkill -f aixyz_continuous_profit_system.py
pkill -f bitget_volatile_coins_service.py
sleep 2

# Clear old logs
echo "Rotating logs..."
if [ -f /tmp/aixyz_main.log ]; then
    mv /tmp/aixyz_main.log /tmp/aixyz_main.log.$(date +%Y%m%d_%H%M%S)
fi

# Start the system using the standard startup script
echo "Starting system..."
./start_aixyz_system.sh