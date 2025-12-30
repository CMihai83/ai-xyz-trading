#!/bin/bash

echo "═══════════════════════════════════════════════════════════════"
echo "     Starting AI-XYZ Full Trading System"
echo "═══════════════════════════════════════════════════════════════"

cd /root/ai_xyz

# Kill any existing processes
echo "Stopping any existing AI-XYZ processes..."
pkill -f "aixyz_continuous_profit_system.py"
pkill -f "services/"
sleep 2

# Activate virtual environment
source venv/bin/activate

# Start all microservices
echo "Starting microservices..."
for service in services/*.py; do
    if [ -f "$service" ]; then
        nohup python "$service" > /dev/null 2>&1 &
        echo "  ✅ Started $(basename $service)"
        sleep 1
    fi
done

# Wait for services to initialize
echo "Waiting for services to initialize..."
sleep 5

# Verify services are running
echo ""
echo "Verifying microservices..."
for port in 9000 9001 9002 9003 9004 9005 9006 9007 9008 9009; do
    if nc -z localhost $port 2>/dev/null; then
        echo "  ✅ Port $port: Service running"
    else
        echo "  ❌ Port $port: Service NOT running"
    fi
done

# Start main trading engine
echo ""
echo "Starting main trading engine..."
nohup python aixyz_continuous_profit_system.py > aixyz_main_trading.log 2>&1 &
MAIN_PID=$!
echo "  ✅ Main trading engine started with PID: $MAIN_PID"

# Wait and verify
sleep 3
if ps -p $MAIN_PID > /dev/null; then
    echo "  ✅ Main trading engine running successfully"
else
    echo "  ❌ Main trading engine failed to start"
    echo "  Check aixyz_main_trading.log for errors"
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "     AI-XYZ System Startup Complete"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "Monitor logs with:"
echo "  tail -f aixyz_main_trading.log"
echo ""
echo "Check positions with:"
echo "  cat position_state.json | jq ."