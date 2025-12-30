#!/bin/bash

# AI-XYZ System Status Check Script

echo "🔍 AI-XYZ System Status Check"
echo "=============================="
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

BASE_DIR="/root/ai_xyz"
cd $BASE_DIR

# Function to check service status
check_service() {
    local service_name=$1
    local pid_file="$BASE_DIR/pids/${service_name}.pid"
    
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            # Get memory usage
            mem_usage=$(ps -p $pid -o pmem= | tr -d ' ')
            cpu_usage=$(ps -p $pid -o pcpu= | tr -d ' ')
            echo -e "${GREEN}✅ $service_name${NC}"
            echo "   PID: $pid | CPU: ${cpu_usage}% | MEM: ${mem_usage}%"
        else
            echo -e "${RED}❌ $service_name (dead)${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  $service_name (not started)${NC}"
    fi
}

echo "📊 Core Components:"
echo "-------------------"
check_service "main_trading_engine"

echo ""
echo "🔧 Microservices:"
echo "-----------------"
check_service "risk-engine"
check_service "position-management"
check_service "market-scanner"
check_service "data-pipeline"
check_service "ml-framework"
check_service "monitoring-service"
check_service "notification-service"
check_service "fibonacci_service"
check_service "balance_manager"

echo ""
echo "📈 Trading Status:"
echo "------------------"

# Check current positions
if command -v python3 &> /dev/null; then
    python3 -c "
import ccxt
import os
from dotenv import load_dotenv

load_dotenv('/root/ai_xyz/.env')

try:
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {'defaultType': 'swap'}
    })
    
    balance = exchange.fetch_balance()
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    
    print(f'Balance: \${balance[\"USDT\"][\"total\"]:.2f} USDT')
    print(f'Active Positions: {len(active)}')
    
    total_pnl = sum(p['unrealizedPnl'] or 0 for p in active)
    print(f'Total Unrealized P&L: \${total_pnl:.2f}')
except Exception as e:
    print(f'Could not fetch trading data: {e}')
" 2>/dev/null
fi

echo ""
echo "💾 System Resources:"
echo "--------------------"
# Check disk usage for logs
log_size=$(du -sh logs 2>/dev/null | cut -f1)
echo "Log directory size: $log_size"

# Count running python processes
python_count=$(pgrep -c python3)
echo "Total Python processes: $python_count"

echo ""
echo "================================"
RUNNING=$(ls pids/*.pid 2>/dev/null | xargs -I {} sh -c 'cat {} | xargs ps -p 2>/dev/null' | grep -c python)
TOTAL=$(ls pids/*.pid 2>/dev/null | wc -l)

if [ "$RUNNING" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    echo -e "${GREEN}✅ System Status: FULLY OPERATIONAL ($RUNNING/$TOTAL services)${NC}"
elif [ "$RUNNING" -gt 0 ]; then
    echo -e "${YELLOW}⚠️  System Status: PARTIALLY RUNNING ($RUNNING/$TOTAL services)${NC}"
else
    echo -e "${RED}❌ System Status: NOT RUNNING${NC}"
fi