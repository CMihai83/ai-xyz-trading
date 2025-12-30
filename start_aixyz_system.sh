#!/bin/bash

echo "==================================="
echo "Starting AI-XYZ Trading System"
echo "==================================="
echo ""

# Kill any existing processes
echo "Stopping existing processes..."
pkill -f aixyz_continuous_profit_system.py
pkill -f bitget_volatile_coins_service.py
sleep 2

# Test volatile coins service first
echo "Testing volatile coins service..."
python3 /root/ai_xyz/bitget_volatile_coins_service.py &
VOLATILE_PID=$!
sleep 5
if ps -p $VOLATILE_PID > /dev/null; then
    echo "✅ Volatile coins service test successful"
    kill $VOLATILE_PID
else
    echo "⚠️ Volatile coins service test failed, continuing anyway..."
fi

# Start the main trading system
echo ""
echo "Starting main trading system..."
cd /root/ai_xyz
nohup python3 aixyz_continuous_profit_system.py > /tmp/aixyz_main.log 2>&1 &
MAIN_PID=$!

echo "Main system PID: $MAIN_PID"
echo $MAIN_PID > /root/ai_xyz/aixyz.pid

# Wait and check if process started successfully
sleep 5
if ps -p $MAIN_PID > /dev/null; then
    echo "✅ AI-XYZ system started successfully!"
    
    # Start the Fibonacci services (surplus dump & exchange connector)
    echo ""
    echo "Starting Fibonacci Support Services..."
    ./services/start_fibonacci_services.sh
    
    echo ""
    echo "Features enabled:"
    echo "  ✅ Fibonacci Averaging Service (pre-calculated safe levels)"
    echo "  ✅ Top volatile coins prioritization (first 2 coins from Bitget)"
    echo "  ✅ Advanced Fibonacci distribution with liquidation safety"
    echo "  ✅ Portfolio direction balancing"
    echo "  ✅ Surplus dump mechanism (automatic executor running)"
    echo "  ✅ Exchange data sync (updates every 10 seconds)"
    echo "  ✅ Dynamic position limits"
    echo "  ✅ Backtesting validation support"
    echo ""
    echo "Monitor logs with: tail -f /tmp/aixyz_main.log"
    echo "Check status with: ./status.sh"
else
    echo "❌ Failed to start AI-XYZ system"
    echo "Check logs: tail -100 /tmp/aixyz_main.log"
    exit 1
fi