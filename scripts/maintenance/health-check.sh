#!/bin/bash

echo "Running AI Trading System health check..."

# Check Kubernetes pods
echo "Checking pod status..."
kubectl get pods -n trading-system

# Check services
echo "Checking service status..."
kubectl get services -n trading-system

# Check ingress
echo "Checking ingress status..."
kubectl get ingress -n trading-system

# Test API endpoints
echo "Testing API endpoints..."
API_URL="http://localhost:8000"

# Test health endpoint
if curl -f "$API_URL/health" > /dev/null 2>&1; then
    echo "✓ API Gateway health check passed"
else
    echo "✗ API Gateway health check failed"
fi

# Test info endpoint
if curl -f "$API_URL/info" > /dev/null 2>&1; then
    echo "✓ API Gateway info endpoint accessible"
else
    echo "✗ API Gateway info endpoint failed"
fi

echo "Health check completed."
