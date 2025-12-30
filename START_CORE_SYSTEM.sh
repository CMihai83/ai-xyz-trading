#!/bin/bash

# AI-XYZ Core System Startup (Essential Services Only)
# This starts the core trading engine and essential services

echo "🚀 Starting AI-XYZ Core System..."
echo "================================="

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_DIR="/root/ai_xyz"
cd $BASE_DIR

# Create directories
mkdir -p logs pids

# Stop any existing processes
echo "🔄 Cleaning up existing processes..."
pkill -f "aixyz_continuous" 2>/dev/null
pkill -f "balance_manager" 2>/dev/null
sleep 2

echo ""
echo "📊 Starting Essential Components..."
echo "-----------------------------------"

# 1. Main Trading Engine (Core)
echo -n "1. Main Trading Engine: "
nohup python3 aixyz_continuous_profit_system.py > logs/main_trading_engine.log 2>&1 &
MAIN_PID=$!
echo $MAIN_PID > pids/main_trading_engine.pid
sleep 3
if ps -p $MAIN_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Running (PID: $MAIN_PID)${NC}"
else
    echo "❌ Failed"
    exit 1
fi

# 2. Balance Manager
echo -n "2. Balance Manager: "
cd services
nohup python3 balance_manager.py > ../logs/balance_manager.log 2>&1 &
BM_PID=$!
echo $BM_PID > ../pids/balance_manager.pid
cd ..
sleep 2
if ps -p $BM_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Running (PID: $BM_PID)${NC}"
else
    echo "⚠️ Failed (non-critical)"
fi

# 3. Market Scanner (if available)
if [ -f "services/market-scanner/src/futures_scanner.py" ]; then
    echo -n "3. Market Scanner: "
    cd services/market-scanner/src
    nohup python3 futures_scanner.py > ../../../logs/market_scanner.log 2>&1 &
    MS_PID=$!
    echo $MS_PID > ../../../pids/market_scanner.pid
    cd ../../..
    sleep 2
    if ps -p $MS_PID > /dev/null 2>&1; then
        echo -e "${GREEN}✅ Running (PID: $MS_PID)${NC}"
    else
        echo "⚠️ Failed (non-critical)"
    fi
else
    echo "3. Market Scanner: ⏭️ Skipped"
fi

echo ""
echo "================================="
echo "📈 AI-XYZ Core System Status:"
echo "================================="

# Check what's running
RUNNING=$(ps aux | grep -E "aixyz_continuous|balance_manager|futures_scanner" | grep -v grep | wc -l)

if [ "$RUNNING" -ge 2 ]; then
    echo -e "${GREEN}✅ Core system operational${NC}"
    echo ""
    echo "🔍 Features Active:"
    echo "  • Position monitoring with -25% gate"
    echo "  • Fibonacci-based averaging (fixed)"
    echo "  • Surplus dump detection"
    echo "  • Balance management"
else
    echo -e "${YELLOW}⚠️ Partial system running${NC}"
fi

echo ""
echo "📁 Logs: $BASE_DIR/logs/"
echo "📊 Status: ./STATUS.sh"
echo "🛑 Stop: ./STOP_FULL_SYSTEM.sh"
echo ""
echo "✨ Core system ready for trading!"