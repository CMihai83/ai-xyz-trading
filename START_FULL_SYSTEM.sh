#!/bin/bash

# AI-XYZ Full System Startup Script
# This script starts all AI-XYZ components and microservices

echo "🚀 Starting AI-XYZ Full System..."
echo "================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Base directory
BASE_DIR="/root/ai_xyz"
cd $BASE_DIR

# Create logs directory if it doesn't exist
mkdir -p $BASE_DIR/logs
mkdir -p $BASE_DIR/pids

# Function to start a service
start_service() {
    local service_name=$1
    local service_path=$2
    local service_file=$3
    local service_port=$4
    local log_file="$BASE_DIR/logs/${service_name}.log"
    local pid_file="$BASE_DIR/pids/${service_name}.pid"
    
    # Check if already running
    if [ -f "$pid_file" ]; then
        old_pid=$(cat "$pid_file")
        if ps -p $old_pid > /dev/null 2>&1; then
            echo -e "${YELLOW}⚠️  $service_name already running (PID: $old_pid)${NC}"
            return
        fi
    fi
    
    # Kill any process using this port first
    lsof -ti:$service_port | xargs -r kill -9 2>/dev/null
    sleep 1
    
    # Start the service with uvicorn
    cd $service_path
    nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $service_port > "$log_file" 2>&1 &
    new_pid=$!
    echo $new_pid > "$pid_file"
    
    # Check if started successfully
    sleep 2
    if ps -p $new_pid > /dev/null 2>&1; then
        echo -e "${GREEN}✅ $service_name started (PID: $new_pid)${NC}"
    else
        echo -e "${RED}❌ $service_name failed to start${NC}"
        tail -5 "$log_file"
    fi
    
    cd $BASE_DIR
}

# Stop any existing processes first
echo "🔄 Stopping existing AI-XYZ processes..."
pkill -f "aixyz_continuous" 2>/dev/null
pkill -f "ai_xyz/services" 2>/dev/null
sleep 2

echo ""
echo "📊 Starting Core Components..."
echo "------------------------------"

# 1. Start Main Trading Engine
echo "Starting Main Trading Engine..."
nohup python3 aixyz_continuous_profit_system.py > logs/main_trading_engine.log 2>&1 &
MAIN_PID=$!
echo $MAIN_PID > pids/main_trading_engine.pid
sleep 3
if ps -p $MAIN_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Main Trading Engine started (PID: $MAIN_PID)${NC}"
else
    echo -e "${RED}❌ Main Trading Engine failed${NC}"
    exit 1
fi

echo ""
echo "🔧 Starting Microservices..."
echo "----------------------------"

# 2. Start Risk Engine
start_service "risk-engine" "$BASE_DIR/services/risk-engine/src" "main.py" "8001"

# 3. Start Position Management
start_service "position-management" "$BASE_DIR/services/position-management/src" "main.py" "8002"

# 4. Start Market Scanner
start_service "market-scanner" "$BASE_DIR/services/market-scanner/src" "main.py" "8003"

# 5. Start Data Pipeline
start_service "data-pipeline" "$BASE_DIR/services/data-pipeline/src" "main.py" "8004"

# 6. Start ML Framework
start_service "ml-framework" "$BASE_DIR/services/ml-framework/src" "main.py" "8005"

# 7. Start Monitoring Service
start_service "monitoring-service" "$BASE_DIR/services/monitoring-service/src" "main.py" "8006"

# 8. Start Notification Service
start_service "notification-service" "$BASE_DIR/services/notification-service/src" "main.py" "8007"

# 9. Start API Gateway (Fibonacci services)
echo "Starting API Gateway services..."
cd $BASE_DIR/services/api-gateway/src
nohup python3 fibonacci_averaging_service.py > "$BASE_DIR/logs/fibonacci_service.log" 2>&1 &
FIB_PID=$!
echo $FIB_PID > "$BASE_DIR/pids/fibonacci_service.pid"
sleep 2
if ps -p $FIB_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Fibonacci Service started (PID: $FIB_PID)${NC}"
else
    echo -e "${RED}❌ Fibonacci Service failed${NC}"
fi

# 10. Start Balance Manager
cd $BASE_DIR/services
nohup python3 balance_manager.py > "$BASE_DIR/logs/balance_manager.log" 2>&1 &
BM_PID=$!
echo $BM_PID > "$BASE_DIR/pids/balance_manager.pid"
sleep 2
if ps -p $BM_PID > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Balance Manager started (PID: $BM_PID)${NC}"
else
    echo -e "${RED}❌ Balance Manager failed${NC}"
fi

cd $BASE_DIR

echo ""
echo "================================="
echo "📈 AI-XYZ System Status:"
echo "================================="

# Count running services
RUNNING_COUNT=$(ls pids/*.pid 2>/dev/null | wc -l)
EXPECTED_COUNT=10

if [ "$RUNNING_COUNT" -eq "$EXPECTED_COUNT" ]; then
    echo -e "${GREEN}✅ All $EXPECTED_COUNT services are running!${NC}"
else
    echo -e "${YELLOW}⚠️  $RUNNING_COUNT of $EXPECTED_COUNT services running${NC}"
fi

echo ""
echo "📁 Log files location: $BASE_DIR/logs/"
echo "🔍 To check status: $BASE_DIR/STATUS.sh"
echo "🛑 To stop all: $BASE_DIR/STOP_FULL_SYSTEM.sh"
echo ""
echo "✨ AI-XYZ Full System startup complete!"