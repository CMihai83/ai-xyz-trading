#!/bin/bash

# AI-XYZ Full System Stop Script

echo "🛑 Stopping AI-XYZ Full System..."
echo "================================="

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_DIR="/root/ai_xyz"
cd $BASE_DIR

# Function to stop a service
stop_service() {
    local service_name=$1
    local pid_file="$BASE_DIR/pids/${service_name}.pid"
    
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid 2>/dev/null
            sleep 1
            
            # Force kill if still running
            if ps -p $pid > /dev/null 2>&1; then
                kill -9 $pid 2>/dev/null
            fi
            
            echo -e "${GREEN}✅ Stopped $service_name (PID: $pid)${NC}"
        else
            echo -e "${YELLOW}⚠️  $service_name was not running${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠️  $service_name pid file not found${NC}"
    fi
}

echo "Stopping all services..."
echo "------------------------"

# Stop all services
stop_service "main_trading_engine"
stop_service "risk-engine"
stop_service "position-management"
stop_service "market-scanner"
stop_service "data-pipeline"
stop_service "ml-framework"
stop_service "monitoring-service"
stop_service "notification-service"
stop_service "fibonacci_service"
stop_service "balance_manager"

# Kill any remaining AI-XYZ processes
echo ""
echo "Cleaning up remaining processes..."
pkill -f "aixyz_continuous" 2>/dev/null
pkill -f "ai_xyz/services" 2>/dev/null
pkill -f "fibonacci_averaging" 2>/dev/null
pkill -f "balance_manager" 2>/dev/null

# Clean up PID directory
rm -f pids/*.pid 2>/dev/null

echo ""
echo "================================="
echo -e "${GREEN}✅ AI-XYZ System fully stopped${NC}"
echo ""
echo "📁 Logs preserved in: $BASE_DIR/logs/"
echo "🚀 To restart: $BASE_DIR/START_FULL_SYSTEM.sh"