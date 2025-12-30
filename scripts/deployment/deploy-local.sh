#!/bin/bash
set -e

echo "Deploying AI Trading System locally..."

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "Docker is required but not installed. Aborting." >&2; exit 1; }
command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required but not installed. Aborting." >&2; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "Helm is required but not installed. Aborting." >&2; exit 1; }

# Create namespace
kubectl create namespace trading-system --dry-run=client -o yaml | kubectl apply -f -

# Deploy infrastructure services
echo "Deploying infrastructure services..."
kubectl apply -f infrastructure/kubernetes/

# Wait for infrastructure to be ready
echo "Waiting for infrastructure services to be ready..."
kubectl wait --for=condition=ready pod -l app=postgres -n trading-system --timeout=300s || true
kubectl wait --for=condition=ready pod -l app=redis -n trading-system --timeout=300s || true
kubectl wait --for=condition=ready pod -l app=kafka -n trading-system --timeout=300s || true

# Deploy application services with Helm
echo "Deploying application services..."
helm upgrade --install trading-system infrastructure/helm/trading-system \
  --namespace trading-system \
  --set environment=development \
  --set image.tag=latest \
  --wait

echo "Deployment completed successfully!"
echo "Access the application at: http://localhost:8000"
echo "Access Grafana at: http://localhost:3001 (admin/admin)"
echo "Access Prometheus at: http://localhost:9090"
