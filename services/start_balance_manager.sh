#!/bin/bash
# Balance Manager Service Startup Script

echo "🚀 Starting Balance Manager Service..."

# Change to AI-XYZ directory
cd /root/ai_xyz

# Kill any existing balance manager process
pkill -f "balance_manager.py" 2>/dev/null

# Start the balance manager
nohup python3 services/balance_manager.py > /var/log/balance_manager.log 2>&1 &
PID=$!

echo "✅ Balance Manager started with PID: $PID"
echo $PID > /root/ai_xyz/balance_manager.pid

echo "📊 Service Configuration:"
echo "  • Target futures balance: $25"
echo "  • Transfer increment: $5"
echo "  • Check interval: Every hour"
echo "  • Log file: /var/log/balance_manager.log"

# Show initial status
sleep 2
if ps -p $PID > /dev/null; then
    echo "✅ Service is running successfully"
    tail -5 /var/log/balance_manager.log
else
    echo "❌ Service failed to start"
    tail -20 /var/log/balance_manager.log
fi