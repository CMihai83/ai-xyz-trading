#!/bin/bash

# AI-XYZ Health Check and Auto-Restart Script
# This script checks all AI-XYZ services and restarts any that are not running
# To be run via cron every 15 minutes

# Base directory
BASE_DIR="/root/ai_xyz"
LOG_FILE="$BASE_DIR/logs/health_check.log"
DATE=$(date '+%Y-%m-%d %H:%M:%S')

# Colors for output (even though cron won't see them, useful for manual runs)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Function to log messages
log_message() {
    echo "[$DATE] $1" >> "$LOG_FILE"
    echo "$1"
}

# Function to check and restart a service
check_and_restart_service() {
    local service_name=$1
    local service_path=$2
    local service_file=$3
    local service_port=$4
    local pid_file="$BASE_DIR/pids/${service_name}.pid"
    local log_file="$BASE_DIR/logs/${service_name}.log"
    
    # Check if PID file exists and if process is running
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            log_message "✅ $service_name is running (PID: $pid)"
            return 0
        else
            log_message "⚠️ $service_name PID file exists but process is dead"
        fi
    else
        log_message "⚠️ $service_name PID file not found"
    fi
    
    # Service is not running, restart it
    log_message "🔄 Restarting $service_name..."
    
    # Kill any process using the port first
    if [ ! -z "$service_port" ]; then
        lsof -ti:$service_port | xargs -r kill -9 2>/dev/null
        sleep 1
    fi
    
    # Start the service
    cd "$service_path"
    if [ "$service_name" = "main_trading_engine" ]; then
        nohup python3 aixyz_continuous_profit_system.py > "$log_file" 2>&1 &
    elif [ "$service_name" = "fibonacci_service" ]; then
        nohup python3 fibonacci_averaging_service.py > "$log_file" 2>&1 &
    elif [ "$service_name" = "balance_manager" ]; then
        nohup python3 balance_manager.py > "$log_file" 2>&1 &
    else
        # Regular microservices use uvicorn
        nohup python3 -m uvicorn main:app --host 0.0.0.0 --port $service_port > "$log_file" 2>&1 &
    fi
    
    new_pid=$!
    echo $new_pid > "$pid_file"
    
    # Check if started successfully
    sleep 3
    if ps -p $new_pid > /dev/null 2>&1; then
        log_message "✅ $service_name restarted successfully (PID: $new_pid)"
        return 0
    else
        log_message "❌ $service_name failed to restart"
        return 1
    fi
}

# Main execution
log_message "========================================="
log_message "Starting AI-XYZ Health Check"
log_message "========================================="

# Change to base directory
cd "$BASE_DIR"

# Check Main Trading Engine
check_and_restart_service "main_trading_engine" "$BASE_DIR" "aixyz_continuous_profit_system.py" ""

# Check Risk Engine
check_and_restart_service "risk-engine" "$BASE_DIR/services/risk-engine/src" "main.py" "8001"

# Check Position Management
check_and_restart_service "position-management" "$BASE_DIR/services/position-management/src" "main.py" "8002"

# Check Market Scanner
check_and_restart_service "market-scanner" "$BASE_DIR/services/market-scanner/src" "main.py" "8003"

# Check Data Pipeline
check_and_restart_service "data-pipeline" "$BASE_DIR/services/data-pipeline/src" "main.py" "8004"

# Check ML Framework
check_and_restart_service "ml-framework" "$BASE_DIR/services/ml-framework/src" "main.py" "8005"

# Check Monitoring Service
check_and_restart_service "monitoring-service" "$BASE_DIR/services/monitoring-service/src" "main.py" "8006"

# Check Notification Service
check_and_restart_service "notification-service" "$BASE_DIR/services/notification-service/src" "main.py" "8007"

# Skip Fibonacci Service (it's a library, not a standalone service)
# The fibonacci_averaging_service.py is imported by other services
log_message "ℹ️ fibonacci_service is a library module (not checked)"

# Check Balance Manager
check_and_restart_service "balance_manager" "$BASE_DIR/services" "balance_manager.py" ""

# Count running services
RUNNING_COUNT=0
EXPECTED_COUNT=9  # 9 services (fibonacci is a library)

for pid_file in "$BASE_DIR"/pids/*.pid; do
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            RUNNING_COUNT=$((RUNNING_COUNT + 1))
        fi
    fi
done

log_message "========================================="
log_message "Health Check Complete: $RUNNING_COUNT/$EXPECTED_COUNT services running"
log_message "========================================="

# Return exit code based on service health
if [ "$RUNNING_COUNT" -eq "$EXPECTED_COUNT" ]; then
    exit 0
else
    exit 1
fi