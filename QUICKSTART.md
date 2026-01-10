# Florin Trading System - Quick Start Guide

Get up and running in **5 minutes**!

## Prerequisites Check

- ✅ Docker installed (`docker --version`)
- ✅ Docker Compose installed (`docker-compose --version`)
- ✅ Bitget API credentials ready

## Step 1: Configure API Credentials (2 minutes)

```bash
cd /root/florin_trading

# Copy the example environment file
cp .env.example .env

# Edit the file and add your credentials
nano .env
```

**Required variables to set:**

```bash
FLORIN_BITGET_API_KEY=your_actual_api_key_here
FLORIN_BITGET_API_SECRET=your_actual_secret_here
FLORIN_BITGET_API_PASSPHRASE=your_actual_passphrase_here
```

**Optional but recommended:**

```bash
FLORIN_DB_PASSWORD=change_this_to_secure_password
FLORIN_INITIAL_BALANCE=100.00
FLORIN_MAX_POSITIONS=10
```

Save and exit (Ctrl+X, then Y, then Enter in nano).

## Step 2: Start the System (2 minutes)

### Option A: Interactive Start (Recommended for first time)

```bash
./start_florin.sh
```

This will:
- Check all prerequisites
- Verify configuration
- Build Docker images
- Start all services
- Show you the logs

### Option B: Quick Start (If everything is configured)

```bash
./start_florin.sh --quick
```

Or manually:

```bash
docker-compose build
docker-compose up -d
docker-compose logs -f florin_trading
```

## Step 3: Verify It's Running (1 minute)

```bash
# Check status
./start_florin.sh --status

# Or manually
docker-compose ps
```

You should see:
- ✅ `florin_trading_system` - Up
- ✅ `florin_redis` - Up (healthy)
- ✅ `florin_postgres` - Up (healthy)

### Verify Isolation from ai_xyz

```bash
./verify_isolation.sh
```

This confirms that florin_trading is completely separate from ai_xyz.

## Step 4: Monitor (Ongoing)

### View Live Logs

```bash
# Continuous logs
docker-compose logs -f florin_trading

# Last 100 lines
docker-compose logs --tail=100 florin_trading

# All services
docker-compose logs -f
```

### Check Trading Activity

```bash
# Inside container
docker-compose exec florin_trading bash

# Check position state
cat position_state.json

# View configuration
python3 florin_config.py
```

### Monitor Resources

```bash
# Resource usage
docker stats florin_trading_system florin_redis florin_postgres

# Detailed status
./start_florin.sh --status
```

## Common Commands

### Starting and Stopping

```bash
# Start
./start_florin.sh --start

# Stop
./start_florin.sh --stop

# Restart
./start_florin.sh --restart

# View logs
./start_florin.sh --logs

# Check status
./start_florin.sh --status
```

### Manual Docker Commands

```bash
# Start services
docker-compose up -d

# Stop services
docker-compose down

# Restart specific service
docker-compose restart florin_trading

# View logs
docker-compose logs -f florin_trading

# Access shell
docker-compose exec florin_trading bash

# Check Redis
docker-compose exec redis redis-cli -n 2 KEYS "*"

# Check PostgreSQL
docker-compose exec postgres psql -U florin_user -d florin_trading
```

## Troubleshooting

### Problem: Container won't start

```bash
# Check logs for errors
docker-compose logs florin_trading

# Check if port is already in use
lsof -i :8081

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Problem: API connection errors

```bash
# Verify credentials are set
docker-compose exec florin_trading env | grep FLORIN_BITGET

# Test API connection
docker-compose exec florin_trading python3 -c "
import os
import ccxt
exchange = ccxt.bitget({
    'apiKey': os.getenv('FLORIN_BITGET_API_KEY'),
    'secret': os.getenv('FLORIN_BITGET_API_SECRET'),
    'password': os.getenv('FLORIN_BITGET_API_PASSPHRASE')
})
print('API Test:', exchange.fetch_balance())
"
```

### Problem: Redis connection issues

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping

# Verify database isolation
docker-compose exec florin_trading python3 florin_config.py
```

### Problem: Out of disk space

```bash
# Check disk usage
df -h

# Clean up old Docker data
docker system prune -a

# Check log sizes
du -sh /var/log/florin_trading/*
```

## Next Steps

1. **Monitor your first trades**: Watch the logs and position_state.json
2. **Adjust configuration**: Modify .env for your risk tolerance
3. **Set up monitoring**: Consider adding Telegram notifications
4. **Backup state files**: Regularly backup position_state.json and averaging_state.json

## Important Notes

### Isolation from ai_xyz

- ✅ Uses Redis DB 2 (ai_xyz uses DB 1)
- ✅ Separate Docker network
- ✅ Separate PostgreSQL database
- ✅ Different container names
- ✅ Different ports (8081 vs 8080)
- ✅ Separate log directories
- ✅ Separate state files

**Both systems can run simultaneously without interference!**

### Security Reminders

- 🔒 **Never commit .env file** to version control
- 🔒 **Use API keys without withdrawal permissions**
- 🔒 **Change default database password**
- 🔒 **Monitor logs for suspicious activity**
- 🔒 **Keep Docker images updated**

### Files to Backup Regularly

```bash
# Critical state files
position_state.json
averaging_state.json
continuous_trading_state.json
performance_history.json

# Configuration
.env (keep secure!)

# Backup command
tar -czf florin_backup_$(date +%Y%m%d).tar.gz \
    position_state.json averaging_state.json \
    continuous_trading_state.json performance_history.json
```

## Support

For issues or questions:

1. Check the logs: `docker-compose logs -f florin_trading`
2. Verify isolation: `./verify_isolation.sh`
3. Check status: `./start_florin.sh --status`
4. Review README.md for detailed documentation

## Summary

```bash
# Complete startup sequence (copy-paste friendly)
cd /root/florin_trading
cp .env.example .env
nano .env  # Add your API credentials
./start_florin.sh
```

That's it! Your isolated trading system is now running.

---

**Happy Trading!** 🚀

Remember: This is a live trading system. Start with small amounts and monitor closely.
