#!/bin/bash
#
# Start Fibonacci Services for AI-XYZ System
# These services provide surplus dump and exchange data updates
#

echo "🚀 Starting Fibonacci Services for AI-XYZ System..."

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Kill any existing processes
echo "Cleaning up old processes..."
pkill -f "automatic_surplus_executor.py" 2>/dev/null
pkill -f "exchange_connector.py" 2>/dev/null

# Start surplus dump executor
echo "Starting Automatic Surplus Executor..."
cd /root/server_deployment
nohup python3 automatic_surplus_executor.py > /var/log/surplus_executor.log 2>&1 &
echo "Surplus Executor PID: $!"

# Wait a moment
sleep 2

# Start exchange connector
echo "Starting Exchange Connector..."
cd /root/server_deployment/margin_optimized_trader
nohup python3 exchange_connector.py > /var/log/exchange_connector.log 2>&1 &
echo "Exchange Connector PID: $!"

# Verify services are running
sleep 3
if ps aux | grep -v grep | grep -q "automatic_surplus_executor.py"; then
    echo "✅ Surplus Executor is running"
else
    echo "❌ Surplus Executor failed to start"
fi

if ps aux | grep -v grep | grep -q "exchange_connector.py"; then
    echo "✅ Exchange Connector is running"
else
    echo "❌ Exchange Connector failed to start"
fi

echo "✅ Fibonacci services startup complete"
echo ""
echo "Logs:"
echo "  Surplus Executor: /var/log/surplus_executor.log"
echo "  Exchange Connector: /var/log/exchange_connector.log"