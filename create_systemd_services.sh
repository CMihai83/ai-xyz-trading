#!/bin/bash

# Create SystemD services for AI-XYZ system
# This ensures services auto-start on boot and restart on failure

echo "Creating SystemD services for AI-XYZ..."

# 1. Main Orchestrator Service
cat << 'EOF' > /etc/systemd/system/ai-xyz-orchestrator.service
[Unit]
Description=AI-XYZ Trading System Orchestrator
After=network.target
Wants=ai-xyz-autonomous.service ai-xyz-momentum.service ai-xyz-surplus.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai_xyz
Environment="PYTHONPATH=/root/ai_xyz"
ExecStart=/usr/bin/python3 /root/ai_xyz/service_health_monitor.py
Restart=always
RestartSec=10
StandardOutput=append:/root/ai_xyz/logs/orchestrator.log
StandardError=append:/root/ai_xyz/logs/orchestrator_error.log

[Install]
WantedBy=multi-user.target
EOF

# 2. Autonomous Sync Service
cat << 'EOF' > /etc/systemd/system/ai-xyz-autonomous.service
[Unit]
Description=AI-XYZ Autonomous Sync Service
After=network.target
PartOf=ai-xyz-orchestrator.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai_xyz
Environment="PYTHONPATH=/root/ai_xyz"
ExecStart=/usr/bin/python3 /root/ai_xyz/autonomous_sync.py
Restart=always
RestartSec=5
StartLimitInterval=200
StartLimitBurst=5
StandardOutput=append:/root/ai_xyz/logs/autonomous_sync.log
StandardError=append:/root/ai_xyz/logs/autonomous_sync_error.log

[Install]
WantedBy=multi-user.target
EOF

# 3. Momentum Guardian Service
cat << 'EOF' > /etc/systemd/system/ai-xyz-momentum.service
[Unit]
Description=AI-XYZ Momentum Guardian Service
After=network.target
PartOf=ai-xyz-orchestrator.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai_xyz
Environment="PYTHONPATH=/root/ai_xyz"
ExecStart=/usr/bin/python3 /root/ai_xyz/momentum_guardian.py
Restart=always
RestartSec=5
StartLimitInterval=200
StartLimitBurst=5
StandardOutput=append:/root/ai_xyz/logs/momentum_guardian.log
StandardError=append:/root/ai_xyz/logs/momentum_guardian_error.log

[Install]
WantedBy=multi-user.target
EOF

# 4. Surplus Dump Manager Service
cat << 'EOF' > /etc/systemd/system/ai-xyz-surplus.service
[Unit]
Description=AI-XYZ Surplus Dump Manager Service
After=network.target
PartOf=ai-xyz-orchestrator.service

[Service]
Type=simple
User=root
WorkingDirectory=/root/ai_xyz
Environment="PYTHONPATH=/root/ai_xyz"
ExecStart=/usr/bin/python3 /root/ai_xyz/surplus_dump_manager.py
Restart=always
RestartSec=5
StartLimitInterval=200
StartLimitBurst=5
StandardOutput=append:/root/ai_xyz/logs/surplus_dump.log
StandardError=append:/root/ai_xyz/logs/surplus_dump_error.log

[Install]
WantedBy=multi-user.target
EOF

# 5. Create a timer for periodic health checks
cat << 'EOF' > /etc/systemd/system/ai-xyz-healthcheck.timer
[Unit]
Description=AI-XYZ Health Check Timer
Requires=ai-xyz-healthcheck.service

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF

# 6. Health check service
cat << 'EOF' > /etc/systemd/system/ai-xyz-healthcheck.service
[Unit]
Description=AI-XYZ Health Check
After=ai-xyz-orchestrator.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /root/ai_xyz/system_health_check.py
StandardOutput=append:/root/ai_xyz/logs/health_check.log
StandardError=append:/root/ai_xyz/logs/health_check_error.log
EOF

# Reload systemd daemon
systemctl daemon-reload

echo "SystemD services created successfully!"
echo ""
echo "Available commands:"
echo "  Start all services:    systemctl start ai-xyz-orchestrator"
echo "  Stop all services:     systemctl stop ai-xyz-orchestrator"
echo "  Check status:          systemctl status ai-xyz-*"
echo "  Enable on boot:        systemctl enable ai-xyz-orchestrator"
echo "  View logs:             journalctl -u ai-xyz-orchestrator -f"
echo ""
echo "To enable automatic start on boot, run:"
echo "  systemctl enable ai-xyz-orchestrator ai-xyz-autonomous ai-xyz-momentum ai-xyz-surplus"