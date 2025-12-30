#!/bin/bash

# AI-XYZ Audit Service Deployment Script
echo "🚀 Setting up AI-XYZ Audit Service..."

# 1. Ensure nginx is configured for reports
echo "📝 Configuring nginx for reports..."

# Check if reports location is already configured
if ! grep -q "location /reports" /etc/nginx/sites-available/default; then
    # Add reports location to nginx config
    sed -i '/location \/ {/i\
        location /reports {\
            alias /var/www/html/reports/;\
            index index.html;\
            autoindex on;\
            try_files $uri $uri/ =404;\
        }' /etc/nginx/sites-available/default
    
    echo "✅ Added reports location to nginx"
else
    echo "✅ Reports location already configured"
fi

# 2. Reload nginx to apply changes
systemctl reload nginx
echo "✅ Nginx reloaded"

# 3. Set up automated audit scheduling (every 30 minutes)
echo "📅 Setting up automated audit scheduling..."

# Create cron job entry
CRON_ENTRY="*/30 * * * * cd /root/ai_xyz && python3 audit_service.py >> /var/log/audit_service.log 2>&1"

# Check if cron job already exists
if ! crontab -l 2>/dev/null | grep -q "audit_service.py"; then
    # Add cron job
    (crontab -l 2>/dev/null; echo "$CRON_ENTRY") | crontab -
    echo "✅ Added cron job for automated audits every 30 minutes"
else
    echo "✅ Cron job already exists"
fi

# 4. Generate initial report
echo "📊 Generating initial report..."
cd /root/ai_xyz
python3 audit_service.py
echo "✅ Initial report generated"

# 5. Set proper permissions
chmod -R 755 /var/www/html/reports
echo "✅ Set proper permissions"

# 6. Display status
echo ""
echo "🎉 AI-XYZ Audit Service Deployment Complete!"
echo ""
echo "📊 Reports available at: https://moondox.eu/reports/"
echo "📅 Automated audits: Every 30 minutes"
echo "📋 Log file: /var/log/audit_service.log"
echo ""
echo "🔍 Next audit will run at: $(date -d '+30 minutes' '+%Y-%m-%d %H:%M')"