#!/bin/bash

# AI_XYZ System Deployment Script
# Usage: ./deploy.sh

echo "🚀 AI_XYZ System Deployment"
echo "=========================="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Load environment variables
if [ -f .env ]; then
    echo "✅ Loading environment variables from .env"
    export $(cat .env | grep -v '^#' | xargs)
else
    echo "⚠️  No .env file found. Please create one with your API credentials:"
    echo "   BITGET_API_KEY=your_api_key"
    echo "   BITGET_SECRET=your_secret"
    echo "   BITGET_PASSPHRASE=your_passphrase"
    exit 1
fi

# Build and start containers
echo "🔨 Building Docker containers..."
docker-compose build

echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Check service status
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "✅ AI_XYZ System deployed successfully!"
echo ""
echo "📝 Useful commands:"
echo "  View logs:        docker-compose logs -f ai_xyz_trading"
echo "  Stop system:      docker-compose down"
echo "  Restart system:   docker-compose restart"
echo "  View positions:   docker exec ai_xyz_system cat position_state.json | jq"
echo ""