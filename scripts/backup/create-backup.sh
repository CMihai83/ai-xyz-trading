#!/bin/bash
set -e

BACKUP_DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/tmp/trading-system-backup-$BACKUP_DATE"

echo "Creating backup for AI Trading System..."

mkdir -p "$BACKUP_DIR"

# Backup database
echo "Backing up database..."
kubectl exec -n trading-system deployment/postgres -- pg_dump -U trading_user trading_system > "$BACKUP_DIR/database.sql"

# Backup Redis data
echo "Backing up Redis data..."
kubectl exec -n trading-system deployment/redis -- redis-cli BGSAVE
kubectl cp trading-system/redis:/data/dump.rdb "$BACKUP_DIR/redis-dump.rdb"

# Backup Kubernetes manifests
echo "Backing up Kubernetes manifests..."
kubectl get all -n trading-system -o yaml > "$BACKUP_DIR/kubernetes-manifests.yaml"

# Create archive
echo "Creating backup archive..."
tar -czf "trading-system-backup-$BACKUP_DATE.tar.gz" -C /tmp "trading-system-backup-$BACKUP_DATE"

echo "Backup created: trading-system-backup-$BACKUP_DATE.tar.gz"
echo "Backup location: $(pwd)/trading-system-backup-$BACKUP_DATE.tar.gz"

# Cleanup temporary directory
rm -rf "$BACKUP_DIR"
