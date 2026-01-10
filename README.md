# Florin Trading System

A completely isolated Docker-based cryptocurrency trading system, cloned from the ai_xyz trading platform. This system operates independently with its own Redis database, PostgreSQL instance, and configuration.

## Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [System Architecture](#system-architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the System](#running-the-system)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)
- [Isolation from ai_xyz](#isolation-from-ai_xyz)
- [Security Best Practices](#security-best-practices)

## Overview

The Florin Trading System is a sophisticated AI-powered cryptocurrency futures trading platform that includes:

- **Adaptive Fibonacci Averaging**: Dynamic position averaging based on market conditions
- **Multi-timeframe Analysis**: Trading across 1m, 5m, 15m, 1h, 4h, and 1d timeframes
- **Risk Management**: Advanced stop-loss, liquidation protection, and position sizing
- **Market Intelligence**: Real-time market scanning and opportunity detection
- **Complete Isolation**: Separate from ai_xyz system with dedicated resources

## Key Features

### Trading Capabilities
- ✅ Bitget Futures Trading (USDT-M)
- ✅ Automated position management
- ✅ Fibonacci-based averaging system
- ✅ Dynamic leverage adjustment (1x-20x)
- ✅ Real-time market scanning
- ✅ Multiple position strategies

### Technical Features
- ✅ Docker containerized deployment
- ✅ Redis caching (DB 2 - isolated)
- ✅ PostgreSQL data persistence
- ✅ Health monitoring
- ✅ Automatic restarts
- ✅ Comprehensive logging

### Risk Management
- ✅ Liquidation protection
- ✅ ATR-based stop losses
- ✅ Position size limits
- ✅ Daily loss limits
- ✅ Margin awareness

## System Architecture

```
florin_trading/
├── Docker Services
│   ├── florin_trading_system (Main trading bot)
│   ├── florin_redis (Redis DB 2)
│   └── florin_postgres (PostgreSQL)
│
├── Data Persistence
│   ├── /var/log/florin_trading/ (Logs)
│   ├── /app/data/ (Market data)
│   └── State files (JSON)
│
└── Network: florin_trading_network
```

## Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 20.04+ recommended) or macOS
- **RAM**: Minimum 2GB, recommended 4GB+
- **Storage**: 10GB free space
- **Network**: Stable internet connection

### Software Requirements
- Docker Engine 20.10+
- Docker Compose 2.0+
- Git (for cloning)

### API Requirements
- Bitget account with API access
- API Key with Futures Trading permissions
- **Important**: Enable Read + Trade, NOT Withdraw

## Installation

### 1. Navigate to the Directory

```bash
cd /root/florin_trading
```

### 2. Create Environment File

```bash
# Copy the example environment file
cp .env.example .env

# Edit with your API credentials
nano .env
```

### 3. Configure Your API Keys

Edit `.env` and set at minimum:

```bash
FLORIN_BITGET_API_KEY=your_actual_api_key
FLORIN_BITGET_API_SECRET=your_actual_api_secret
FLORIN_BITGET_API_PASSPHRASE=your_actual_passphrase
FLORIN_DB_PASSWORD=secure_database_password
```

### 4. Review Configuration

Check other settings in `.env`:
- Initial balance tracking
- Position limits
- Leverage settings
- Risk management parameters

## Configuration

### Essential Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FLORIN_BITGET_API_KEY` | - | Your Bitget API key (required) |
| `FLORIN_BITGET_API_SECRET` | - | Your Bitget API secret (required) |
| `FLORIN_BITGET_API_PASSPHRASE` | - | Your Bitget passphrase (required) |
| `FLORIN_INITIAL_BALANCE` | 100.00 | Starting balance for tracking |
| `FLORIN_MAX_POSITIONS` | 10 | Max simultaneous positions |
| `FLORIN_DEFAULT_LEVERAGE` | 5 | Default leverage multiplier |
| `FLORIN_POSITION_SIZE_USD` | 10 | Size per position in USD |

### Advanced Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `FLORIN_USE_TESTNET` | false | Use testnet (true) or live (false) |
| `FLORIN_LOG_LEVEL` | INFO | Logging verbosity |
| `FLORIN_DASHBOARD_PORT` | 8081 | Web dashboard port |
| `REDIS_DB` | 2 | Redis database number |

## Running the System

### Build and Start

```bash
# Build the Docker images
docker-compose build

# Start all services
docker-compose up -d

# View logs
docker-compose logs -f florin_trading
```

### Stop the System

```bash
# Stop all services
docker-compose down

# Stop and remove volumes (WARNING: deletes all data)
docker-compose down -v
```

### Restart the System

```bash
# Restart specific service
docker-compose restart florin_trading

# Restart all services
docker-compose restart
```

## Monitoring

### View Logs

```bash
# Real-time logs from trading system
docker-compose logs -f florin_trading

# Last 100 lines
docker-compose logs --tail=100 florin_trading

# All services
docker-compose logs -f
```

### Check System Status

```bash
# View running containers
docker-compose ps

# Check resource usage
docker stats florin_trading_system

# Check health status
docker inspect florin_trading_system | grep -A 10 Health
```

### Access Container Shell

```bash
# Interactive shell
docker-compose exec florin_trading bash

# Run Python config test
docker-compose exec florin_trading python3 florin_config.py

# Check Redis connection
docker-compose exec florin_trading python3 -c "from florin_config import get_redis_connection; r = get_redis_connection(); print('Connected:', r.ping())"
```

### Monitor Redis

```bash
# Access Redis CLI
docker-compose exec redis redis-cli

# Select Florin database (DB 2)
redis> SELECT 2
redis> KEYS *

# Monitor commands in real-time
redis> MONITOR
```

### Monitor PostgreSQL

```bash
# Access PostgreSQL
docker-compose exec postgres psql -U florin_user -d florin_trading

# List tables
florin_trading=> \dt

# Check recent activity
florin_trading=> SELECT * FROM positions ORDER BY created_at DESC LIMIT 10;
```

## Troubleshooting

### Container Won't Start

```bash
# Check logs for errors
docker-compose logs florin_trading

# Check if ports are available
netstat -tulpn | grep 8081

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### API Connection Issues

```bash
# Verify API credentials in container
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
print('Balance:', exchange.fetch_balance())
"
```

### Redis Connection Issues

```bash
# Check Redis is running
docker-compose ps redis

# Test connection
docker-compose exec redis redis-cli ping

# Check database isolation
docker-compose exec florin_trading python3 florin_config.py
```

### Database Migration Issues

```bash
# Reset database (WARNING: deletes all data)
docker-compose down
docker volume rm florin_trading_florin_postgres_data
docker-compose up -d
```

### Log Files Growing Too Large

```bash
# Check log sizes
du -sh /var/log/florin_trading/*

# Rotate logs (inside container)
docker-compose exec florin_trading bash -c "
    cd /var/log/florin_trading
    for log in *.log; do
        mv \$log \$log.old
        gzip \$log.old
    done
"
```

## Isolation from ai_xyz

This system is **completely isolated** from the ai_xyz trading system:

### Separate Resources

| Resource | ai_xyz | florin_trading |
|----------|--------|----------------|
| Redis DB | 1 | 2 |
| Container Name | `ai_xyz_system` | `florin_trading_system` |
| Network | `ai_xyz_network` | `florin_trading_network` |
| PostgreSQL DB | `ai_xyz` | `florin_trading` |
| Logs | `/var/log/ai_xyz` | `/var/log/florin_trading` |
| Dashboard Port | 8080 | 8081 |
| Docker Volumes | `ai_xyz_*` | `florin_*` |

### Verification

```bash
# Check Redis isolation
docker-compose exec redis redis-cli

# In Redis CLI:
SELECT 1  # ai_xyz database
DBSIZE    # Number of keys in ai_xyz

SELECT 2  # florin_trading database
DBSIZE    # Number of keys in florin_trading

# Check container isolation
docker network inspect florin_trading_network
docker network inspect ai_xyz_network
```

### Running Both Systems

Both systems can run simultaneously without conflict:

```bash
# Terminal 1: ai_xyz
cd /root/ai_xyz
docker-compose up -d

# Terminal 2: florin_trading
cd /root/florin_trading
docker-compose up -d

# Both systems running independently
docker ps
```

## Security Best Practices

### API Security

1. **Never commit .env file** - It's in .gitignore
2. **Use API keys with minimal permissions**:
   - ✅ Enable: Read, Trade
   - ❌ Disable: Withdraw
3. **Rotate API keys regularly**
4. **Use IP whitelist on Bitget** (if available)

### Database Security

1. **Change default passwords** in `.env`
2. **Don't expose PostgreSQL port** publicly
3. **Regular backups** of critical data
4. **Encrypted connections** in production

### Container Security

1. **Keep Docker updated**
2. **Use specific image versions** (not `latest`)
3. **Limit container resources**:
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '1'
         memory: 2G
   ```
4. **Regular security updates**:
   ```bash
   docker-compose pull
   docker-compose up -d
   ```

### Monitoring Security

1. **Watch for unusual activity**:
   ```bash
   docker-compose logs -f | grep -i error
   ```
2. **Monitor system resources**:
   ```bash
   docker stats
   ```
3. **Set up alerts** for critical events

## File Structure

```
/root/florin_trading/
├── Dockerfile                          # Container definition
├── docker-compose.yml                  # Multi-container orchestration
├── .env.example                        # Environment template
├── .env                                # Your credentials (DO NOT COMMIT)
├── README.md                           # This file
├── florin_config.py                    # Central configuration
├── requirements.txt                    # Python dependencies
│
├── aixyz_continuous_profit_system.py   # Main trading system
├── scanner_v4.py                       # Market scanner
├── enhanced_market_scanner.py          # Market intelligence
├── liquidation_protection_service.py   # Risk management
│
├── data/                               # Persistent data
├── logs/                               # Application logs
├── pids/                               # Process IDs
│
└── State Files (JSON)
    ├── position_state.json             # Active positions
    ├── averaging_state.json            # Averaging data
    ├── continuous_trading_state.json   # System state
    └── performance_history.json        # Performance metrics
```

## Support

### Logs to Check

1. **Trading System**: `docker-compose logs florin_trading`
2. **Redis**: `docker-compose logs redis`
3. **PostgreSQL**: `docker-compose logs postgres`

### Configuration Test

```bash
# Test configuration
docker-compose exec florin_trading python3 florin_config.py

# Should output:
# - Redis connection status
# - Database isolation verification
# - API key configuration status
```

### Health Check

```bash
# Check all services healthy
docker-compose ps

# All should show "Up" and "healthy"
```

## License

This is a private trading system. Do not distribute without permission.

## Disclaimer

**CRYPTOCURRENCY TRADING INVOLVES SIGNIFICANT RISK**

- This software is provided "as is" without warranty
- Past performance does not guarantee future results
- Only trade with capital you can afford to lose
- Test thoroughly on testnet before live trading
- The authors are not responsible for trading losses

---

**Last Updated**: January 2026  
**Version**: 1.0.0  
**System**: Florin Trading (Isolated from ai_xyz)
