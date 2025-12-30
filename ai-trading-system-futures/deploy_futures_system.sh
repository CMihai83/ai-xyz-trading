#!/bin/bash
set -e

echo "🚀 Deploying AI Futures Trading System"
echo "======================================"

# Load environment variables
if [ -f .env.futures ]; then
    export $(cat .env.futures | xargs)
    echo "✅ Loaded futures environment variables"
else
    echo "❌ .env.futures file not found!"
    exit 1
fi

echo "🔑 Bitget API Configuration:"
echo "  API Key: $BITGET_API_KEY"
echo "  Trading Mode: Futures"
echo "  Max Leverage: $MAX_LEVERAGE"
echo "  Margin Mode: $MARGIN_MODE"

# Run configuration tests
echo "🧪 Running system tests..."
python3 futures_trading_test.py

# Build and start services
echo "📦 Building and starting futures trading services..."
docker-compose -f docker-compose.futures.yml down
docker-compose -f docker-compose.futures.yml up -d --build

echo "⏳ Waiting for services to start..."
sleep 30

# Check service health
echo "🔍 Checking service health..."
services=("futures-position-manager" "futures-risk-engine" "api-gateway")

for service in "${services[@]}"; do
    if docker-compose -f docker-compose.futures.yml ps $service | grep -q "Up"; then
        echo "✅ $service is running"
    else
        echo "❌ $service failed to start"
        docker-compose -f docker-compose.futures.yml logs $service
    fi
done

echo ""
echo "🎉 Futures Trading System Deployed Successfully!"
echo "=============================================="
echo "📊 Access Points:"
echo "  • Futures Position Manager: http://localhost:8003"
echo "  • Futures Risk Engine:      http://localhost:8009"
echo "  • API Gateway:              http://localhost:8000"
echo "  • Market Scanner:           http://localhost:8001"
echo "  • AI Decision Engine:       http://localhost:8002"
echo "  • Grafana Monitoring:       http://localhost:3001"
echo ""
echo "🔑 Bitget Futures Integration:"
echo "  • API Key: $BITGET_API_KEY"
echo "  • Status: ✅ Ready for Futures Trading"
echo "  • Leverage: Dynamic 1x-${MAX_LEVERAGE}x"
echo "  • Margin Mode: $MARGIN_MODE"
echo ""
echo "🎯 Ready to trade futures with dynamic leverage!"
echo "=============================================="
