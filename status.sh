#!/bin/bash

echo "============================================"
echo "       AI-XYZ SYSTEM STATUS CHECK          "
echo "============================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check main process
echo "🔍 Checking Main Trading Engine..."
if pgrep -f "aixyz_continuous_profit_system.py" > /dev/null; then
    PID=$(pgrep -f "aixyz_continuous_profit_system.py")
    echo -e "${GREEN}✅ Main engine is RUNNING (PID: $PID)${NC}"
    
    # Get memory and CPU usage
    PS_INFO=$(ps -p $PID -o pid,vsz,rss,%cpu,%mem,etime --no-headers)
    echo "   Resources: $(echo $PS_INFO | awk '{print "CPU: "$4"%, MEM: "$5"%, Runtime: "$6}')"
else
    echo -e "${RED}❌ Main engine is NOT RUNNING${NC}"
fi

echo ""
echo "🔍 Checking Redis..."
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅ Redis is RUNNING${NC}"
    KEYS=$(redis-cli --scan --pattern "aixyz:*" | wc -l)
    echo "   Stored keys: $KEYS AI-XYZ keys"
else
    echo -e "${RED}❌ Redis is NOT RUNNING${NC}"
fi

echo ""
echo "🔍 Checking Fibonacci Service..."
if [ -f "/root/ai_xyz/services/api-gateway/src/fibonacci_averaging_service.py" ]; then
    echo -e "${GREEN}✅ Fibonacci service is AVAILABLE${NC}"
    echo "   Type: Integrated library service"
    echo "   Features: Pre-calculated safe levels, liquidation safety"
else
    echo -e "${YELLOW}⚠️ Fibonacci service file not found${NC}"
fi

echo ""
echo "📊 Current Trading Positions:"
python3 -c "
import ccxt
import os
from dotenv import load_dotenv
import sys

load_dotenv('/root/ai_xyz/.env')

try:
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'enableRateLimit': True,
        'options': {
            'defaultType': 'swap',
            'defaultMarginMode': 'isolated'
        }
    })

    # Get balance
    balance = exchange.fetch_balance()
    total = balance['USDT']['total']
    free = balance['USDT']['free']
    
    print(f'💰 Balance: \${total:.2f} USDT (Free: \${free:.2f})')
    
    # Get positions
    positions = exchange.fetch_positions()
    active = [p for p in positions if p['contracts'] > 0]
    
    if active:
        print(f'📈 Active Positions: {len(active)}')
        total_upnl = 0
        for pos in active:
            upnl = pos['unrealizedPnl']
            total_upnl += upnl
            color = '\033[0;32m' if upnl > 0 else '\033[0;31m'
            reset = '\033[0m'
            
            print(f'   {pos[\"symbol\"]}: {pos[\"side\"].upper()} | {color}\${upnl:.2f}{reset} ({pos[\"percentage\"]:.1f}%)')
        
        color = '\033[0;32m' if total_upnl > 0 else '\033[0;31m'
        print(f'   {color}Total UPNL: \${total_upnl:.2f}{reset}')
    else:
        print('📊 No active positions')
        
except Exception as e:
    print(f'❌ Error checking positions: {e}')
" 2>/dev/null

echo ""
echo "📝 Recent Log Activity:"
if [ -f "/tmp/aixyz_main.log" ]; then
    echo "Last 5 log entries:"
    tail -5 /tmp/aixyz_main.log | sed 's/^/   /'
elif [ -f "aixyz_continuous_profit.log" ]; then
    echo "Last 5 log entries:"
    tail -5 aixyz_continuous_profit.log | sed 's/^/   /'
else
    echo "   No log files found"
fi

echo ""
echo "🔧 System Configuration:"
echo "   Max Positions: 2"
echo "   Min Position Size: \$6.50"
echo "   Fibonacci Service: Enabled"
echo "   Volatile Coins Priority: Enabled"
echo "   Portfolio Balancing: Enabled"

echo ""
echo "============================================"
echo "Use './restart_aixyz_system.sh' to restart"
echo "Use 'tail -f /tmp/aixyz_main.log' to monitor"
echo "============================================"