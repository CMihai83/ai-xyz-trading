# AI-XYZ Service Registry

## Core Services

### 1. Main Trading Engine
- **Service**: `aixyz_continuous_profit_system.py`
- **Status**: ACTIVE
- **PID File**: `/root/ai_xyz/aixyz.pid`
- **Log File**: `/tmp/aixyz_main.log`
- **Dependencies**: 
  - Fibonacci Averaging Service
  - Volatile Coins Service
  - Redis (port 6379)
  - Bitget API

### 2. Fibonacci Averaging Service
- **Service**: `services/api-gateway/src/fibonacci_averaging_service.py`
- **Status**: INTEGRATED (runs within main engine)
- **Type**: Library Service
- **Features**:
  - Pre-calculation of safe averaging levels
  - Liquidation safety verification
  - Fibonacci sequence distribution
  - Position multiplier calculation
  - Backtesting support

### 3. Volatile Coins Service
- **Service**: `bitget_volatile_coins_service.py`
- **Status**: INTEGRATED (runs within main engine)
- **Update Frequency**: 5 minutes
- **Cache**: In-memory + file cache
- **Output**: Top 20 volatile coins

### 4. Advanced Opportunity Engine
- **Service**: `advanced_opportunity_engine.py`
- **Status**: INTEGRATED
- **Features**:
  - Multi-timeframe analysis
  - Elliott Wave patterns
  - ML scoring
  - Fibonacci retracements

### 5. Portfolio Balancer
- **Service**: `portfolio_balancer.py`
- **Status**: INTEGRATED
- **Purpose**: Maintains long/short balance

### 6. Position Persistence Manager
- **Service**: `position_persistence_manager.py`
- **Status**: INTEGRATED
- **Storage**: Redis
- **Backup Frequency**: Every position update

## Supporting Services

### Redis
- **Port**: 6379
- **Database**: 0
- **Purpose**: Position state persistence
- **Keys**:
  - `aixyz:positions` - Current positions
  - `aixyz:state` - System state
  - `aixyz:averaging_steps` - Averaging history
  - `seamless_position:*` - Individual position data

### Bitget Exchange API
- **Type**: External Service
- **Endpoints Used**:
  - Market data (WebSocket & REST)
  - Position management
  - Order execution
  - Balance queries

## Service Dependencies

```
aixyz_continuous_profit_system.py
├── fibonacci_averaging_service.py
├── bitget_volatile_coins_service.py
├── advanced_opportunity_engine.py
├── portfolio_balancer.py
├── position_persistence_manager.py
├── Redis (localhost:6379)
└── Bitget API
```

## Start/Stop Commands

### Start All Services
```bash
./start_aixyz_system.sh
```

### Stop All Services
```bash
pkill -f aixyz_continuous_profit_system.py
```

### Restart All Services
```bash
./restart_aixyz_system.sh
```

### Check Service Status
```bash
./status.sh
```

## Service Health Checks

### Main System
```bash
ps aux | grep aixyz_continuous_profit_system.py
```

### Redis
```bash
redis-cli ping
```

### Check Logs
```bash
tail -f /tmp/aixyz_main.log
```

## Service Configuration

### Environment Variables (.env)
- `BITGET_API_KEY`
- `BITGET_API_SECRET`
- `BITGET_API_PASSPHRASE`

### System Parameters (in code)
- Max Positions: 2
- Min Position Size: $6.50
- Leverage Range: 7-10x
- Max Averaging Steps: 8
- Zone Thresholds: Configurable

## Service Monitoring

### Key Metrics
- Position count
- Total UPNL
- Averaging step usage
- API call frequency
- Error rate

### Log Locations
- Main: `/tmp/aixyz_main.log`
- Alternative: `aixyz_continuous_profit.log`
- Redis: `/var/log/redis/redis-server.log`

## Service Recovery

### If Main System Crashes
1. Check logs: `tail -100 /tmp/aixyz_main.log`
2. Restart: `./restart_aixyz_system.sh`
3. Verify positions are loaded from Redis

### If Redis Crashes
1. Start Redis: `redis-server --daemonize yes`
2. System will auto-reconnect
3. Positions will be restored from last save

### If API Connection Fails
1. System has auto-retry with exponential backoff
2. Check API credentials in `.env`
3. Verify network connectivity

## Service Updates

### Adding New Service
1. Create service file in appropriate directory
2. Add integration in main system
3. Update this registry
4. Update start/restart scripts
5. Test thoroughly before deployment

### Updating Existing Service
1. Test changes locally
2. Stop system: `pkill -f aixyz_continuous_profit_system.py`
3. Apply updates
4. Restart: `./restart_aixyz_system.sh`
5. Monitor logs for errors

## Performance Specifications

| Service | Memory | CPU | Network |
|---------|--------|-----|---------|
| Main Engine | ~250MB | <5% | Low |
| Fibonacci Service | Included | <1% | None |
| Volatile Coins | ~50MB | <1% | Low |
| Redis | ~100MB | <1% | None |
| **Total** | **~400MB** | **<8%** | **Low** |

## Version Control

| Component | Version | Last Updated |
|-----------|---------|--------------|
| Main System | 2.0 | Sept 2025 |
| Fibonacci Service | 1.0 | Sept 2025 |
| Volatile Coins | 1.1 | Sept 2025 |
| Advanced Engine | 1.0 | Sept 2025 |

---
*Service Registry Last Updated: September 2025*