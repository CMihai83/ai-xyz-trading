#!/bin/bash
set -e

echo "Deploying AI Trading System to production..."

# Check prerequisites
command -v kubectl >/dev/null 2>&1 || { echo "kubectl is required but not installed. Aborting." >&2; exit 1; }
command -v helm >/dev/null 2>&1 || { echo "Helm is required but not installed. Aborting." >&2; exit 1; }

# Verify we're in the right context
CURRENT_CONTEXT=$(kubectl config current-context)
echo "Current Kubernetes context: $CURRENT_CONTEXT"
read -p "Are you sure you want to deploy to production? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled."
    exit 1
fi

# Create namespace
kubectl create namespace trading-system --dry-run=client -o yaml | kubectl apply -f -

# Deploy with production values
echo "Deploying to production..."
helm upgrade --install trading-system infrastructure/helm/trading-system \
  --namespace trading-system \
  --set environment=production \
  --set image.tag=${IMAGE_TAG:-latest} \
  --set replicaCount=3 \
  --set autoscaling.enabled=true \
  --set ingress.enabled=true \
  --wait

echo "Production deployment completed successfully!"
