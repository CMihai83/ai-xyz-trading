# AI-XYZ CONTINUOUS PROFIT TRADING SYSTEM

## System Overview

AI-XYZ is an autonomous cryptocurrency futures trading system running on Bitget exchange. It uses adaptive Fibonacci averaging, zone-based position management, and multiple AI/ML modules for intelligent trading decisions.

**Location**: `/root/ai_xyz/`
**Main Script**: `aixyz_continuous_profit_system.py` (258KB)
**Repository**: https://github.com/CMihai83/ai-xyz-trading.git

---

## 1. Docker Architecture

### 1.1 Running Containers
```
ai_xyz_trading_system   - Main trading engine (aixyz_continuous_profit_system.py)
ai_xyz_redis            - Redis 7 Alpine (position state, caching)
ai_xyz_postgres         - TimescaleDB PostgreSQL 15 (historical data)
ai_xyz_telegram_bot     - Telegram notifications
ai_xyz_backtest         - Backtesting service (port 8008)
```

### 1.2 Available Microservices (docker-compose.yml)
| Service | Port | Purpose |
|---------|------|---------|
| risk-engine | 8001 | Risk assessment |
| position-management | 8002 | Position tracking |
| market-scanner | 8003 | Market analysis |
| data-pipeline | 8004 | Data ingestion |
| ml-framework | 8005 | ML predictions |
| monitoring-service | 8006 | System monitoring |
| notification-service | 8007 | Alerts |
| backtest | 8008 | Strategy backtesting |

### 1.3 Network Configuration
- **Network**: `ai_xyz_trading_network` (bridge)
- **Redis**: `redis:6379` (inside Docker), `localhost:6379` (host fallback)
- **PostgreSQL**: `postgres:5432`
- **Environment Variables**: Use `REDIS_HOST`, `REDIS_PORT` for Redis connections

---

## 2. Trading Configuration

### 2.1 Account Settings (.env)
```
BITGET_API_KEY=bg_1dfc40220e38b5b118c4828b0cbcc2cb
BITGET_API_SECRET=<secret>
BITGET_API_PASSPHRASE=<passphrase>

INITIAL_BALANCE=65.70
MAX_POSITIONS=10 (actual runtime: 12)
DEFAULT_LEVERAGE=5
MAX_LEVERAGE=20
POSITION_SIZE_USD=10
USE_TESTNET=false
```

### 2.2 Position Sizing
- **Base Margin**: $0.70 (initial position)
- **Total Capital per Position**: $5.00
- **Trading Capital**: 70% = $3.50
- **Safety Reserve**: 30% = $1.50
- **Averaging Capital**: $2.80 ($3.50 - $0.70)

---

## 3. Zone-Based Position Management

### 3.1 Zone Thresholds
```python
zone_thresholds = {
    'averaging': -0.25,      # -25% UPNL triggers averaging (AI can override)
    'profit_taking': 0.05,   # +5% UPNL enters surplus dump zone
    'stop_loss': -0.90       # -90% UPNL (safe for 15x leverage)
}
neutral_zone_upper_usd = 0.15  # $0.15 minimum UPNL to exit neutral
```

### 3.2 Zone States
| Zone | Trigger | Action |
|------|---------|--------|
| **NEUTRAL** | -$0.15 to +$0.15 UPNL | Hold, no action |
| **AVERAGING** | UPNL < -25% | Execute Fibonacci averaging steps |
| **PROFIT_TAKING** | UPNL > +5% | Monitor for surplus dump |
| **SURPLUS_DUMP** | Peak tracking active | Execute staged profit taking |
| **STOP_LOSS** | UPNL < -90% | Emergency close |

### 3.3 Surplus Dump Strategy (Two-Stage)
```python
surplus_dump_threshold = 0.85      # Stage 1: 85% of peak → dump 50% of surplus
surplus_dump_threshold_stage2 = 0.30  # Stage 2: 30% of peak → dump remaining 50%
profit_threshold = 0.015           # 1.5% profit threshold for large positions
```

---

## 4. Adaptive Fibonacci Averaging System

### 4.1 Core Concept
- Uses golden ratio (φ = 1.618) for position scaling
- Dynamic delta calculation based on market volatility
- Timeframe-based capital allocation (1m, 5m, 15m, 1h, 4h, 1d)
- Maximum 5 averaging steps per position

### 4.2 Key Components
```python
AdaptiveFibonacciAveraging(total_capital=2.80)  # Core averaging logic
DynamicFibonacciDeltaService                     # Volatility-adaptive delta
TimeframeSpeedTracker                            # Dynamic threshold adjustment
TimeframeCapitalAllocator                        # Capital distribution
```

### 4.3 Averaging Execution
- Tracks `averaging_steps[symbol]` (0-5)
- Tracks `original_sizes[symbol]` for surplus calculation
- Tracks `peak_upnl[symbol]` for profit taking
- Fibonacci multipliers: [1.0, 2.0, 3.0, 4.0, 5.0]

---

## 5. Market Scanner (V4.0)

### 5.1 Two-Stage Filtering
```
Stage 1: Quick Filter (ALL 497 USDT perpetual futures)
  → Filter to ~137 candidates based on volume/volatility

Stage 2: Deep Analysis (Top 40 candidates)
  → VSA (Volume Spread Analysis) scoring
  → Minimum score threshold: 0.55
  → Entry threshold: 0.70
```

### 5.2 Scan Cycle
- Scans every ~60 seconds
- Target scan time: 25-35 seconds
- API calls per scan: ~160-330

---

## 6. AI/ML Modules

### 6.1 Category 1 - High Priority (Active)
| Module | Purpose | Benefit |
|--------|---------|---------|
| `RLClosingAgent` | Q-learning exit timing | +15-25% better exits |
| `MarkowitzOptimizer` | Portfolio optimization | +20% capital efficiency, -30% risk |
| `CorrelationMatrixAnalyzer` | Diversification | -25% correlated drawdowns |
| `OpportunityCostPredictor` | ML capital rotation | +20% faster rotation |

### 6.2 Performance Modules (V1.1.0)
- `MomentumBurstDetector` - 1% burst threshold
- `ConfidenceTierSystem` - Signal quality filtering
- `DynamicPositionSizer` - +30% profit per winning trade
- `KellyCriterionSizer` - Optimal growth rate
- `VelocityProfitTaker` - Speed-based profit taking

### 6.3 Market Microstructure (V1.2.0)
- `FundingRateOptimizer` - Funding rate arbitrage
- `OrderBookImbalanceDetector` - Order flow analysis
- `PartialCloseLadder` - Staged exits
- `ATRStopLoss` / `TrailingATRStop` - Volatility-based stops

### 6.4 V3 AI Components (TensorFlow)
- `AdaptiveThresholdEngine` - AI-driven thresholds
- `AIMarketIntelligence` - Market regime detection
- `OpportunityCostEngine` - V3 opportunity analysis
- `AdvancedDeltaEngine` - AI delta calculation
- `AdaptiveAveragingEngine` - AI averaging decisions

---

## 7. State Persistence

### 7.1 Redis Keys
```
position:{symbol}     - Position state hash
positions:active      - Active positions set
fibonacci_config:{symbol} - Fibonacci parameters
system:status         - System status
```

### 7.2 JSON State Files (Docker volumes)
```
/app/position_state.json           - Position tracking
/app/averaging_state.json          - Averaging step tracking
/app/continuous_trading_state.json - System state
/app/performance_history.json      - Performance metrics
```

### 7.3 State Recovery
- `PositionPersistenceManager` - Redis persistence
- `EnhancedPositionSync` v1.3.0 - Exchange reconciliation
- `LivePositionsRegistry` - Central position tracking

---

## 8. Risk Management

### 8.1 Liquidation Protection
```python
LiquidationProtectionService:
  - Additional $25 margin per position
  - Limit orders at -82.5% UPNL (before liquidation)
  - Total capital per position: $50 ($25 averaging + $25 protection)
```

### 8.2 Safety Features
- 3-minute cooldown after position close
- Margin-aware position sizing (prevents liquidation)
- Correlation-based diversification
- Stop-loss at -90% UPNL

---

## 9. Key Files Reference

### 9.1 Main System
```
aixyz_continuous_profit_system.py  - Main trading loop (258KB)
position_persistence_manager.py     - Redis state management
live_positions_registry.py          - Position tracking
enhanced_position_sync.py           - Exchange sync
redis_state_manager.py              - Redis operations
```

### 9.2 Fibonacci System
```
adaptive_fibonacci_system.py        - Core Fibonacci logic
adaptive_fibonacci_averaging.py     - Averaging implementation
dynamic_fibonacci_delta.py          - Delta calculation
timeframe_capital_allocator.py      - Capital distribution
timeframe_speed_tracker.py          - Speed-based adjustments
fibonacci_results_storage.py        - Results persistence
```

### 9.3 Scanners
```
scanner_v4.py                       - V4 all-market scanner
enhanced_market_scanner.py          - Enhanced scanner
```

### 9.4 Services Directory
```
services/balance_manager.py         - Margin management ($400 threshold, $15 increments)
services/api-gateway/              - API services
services/market-scanner/           - Scanner microservice
services/position-management/      - Position microservice
services/ai-decision-engine/       - AI decision service
services/data-pipeline/            - Data ingestion
services/risk-engine/              - Risk assessment
services/ml-framework/             - ML predictions
services/monitoring-service/       - System monitoring
services/notification-service/     - Alerts/notifications
```

### 9.5 Core Directory
```
core/live_positions_registry.py    - Position registry
core/adaptive_timeframe_delta.py   - Timeframe delta service
```

---

## 10. Common Operations

### 10.1 Check Status
```bash
docker ps --format "table {{.Names}}\t{{.Status}}" | grep ai_xyz
docker logs ai_xyz_trading_system --tail 50
docker exec ai_xyz_redis redis-cli INFO clients
```

### 10.2 Restart System
```bash
cd /root/ai_xyz
docker compose build ai_xyz_trading --no-cache
docker compose up -d ai_xyz_trading
```

### 10.3 View Positions
```bash
docker logs ai_xyz_trading_system 2>&1 | grep -E "UPNL|Zone:"
```

### 10.4 Check Redis State
```bash
docker exec ai_xyz_redis redis-cli KEYS "position:*"
docker exec ai_xyz_redis redis-cli HGETALL "position:SYMBOL/USDT:USDT"
```

---

## 11. Balance Manager Service

Monitors and manages margin between futures and spot accounts.

### Configuration
- **Margin Threshold**: $400 (triggers transfer when exceeded)
- **Transfer Increment**: $15 (amount moved per transfer)
- **Direction**: Futures → Spot (when excess margin detected)

### Location
- `services/balance_manager.py`
- `services/Dockerfile.balance_manager`

---

## 12. Important Notes

### 12.1 DO NOT Confuse With
- **Florin Trading** (`/root/florin_trading/`) - Separate trading system, DO NOT TOUCH
- Uses separate Docker containers (`florin_redis`, `florin_postgres`)

### 12.2 Redis Connection Pattern
All files use environment variables for Redis:
```python
redis_host = os.getenv('REDIS_HOST', 'localhost')
redis_port = int(os.getenv('REDIS_PORT', 6379))
```

### 12.3 Git Repository
- Branch: `master`
- Remote: `origin` → `https://github.com/CMihai83/ai-xyz-trading.git`
- Always commit changes before restarting containers

---

## QUICK REFERENCE TABLE

| Parameter | Value |
|-----------|-------|
| Exchange | Bitget (USDT-M Futures) |
| Max Positions | 12 |
| Position Size | $5-10 USD |
| Leverage | 5x default, 20x max |
| Averaging Steps | 5 max |
| Neutral Zone | -$0.15 to +$0.15 |
| Averaging Trigger | -25% UPNL |
| Profit Taking | +5% UPNL |
| Stop Loss | -90% UPNL |
| Surplus Dump Stage 1 | 85% of peak |
| Surplus Dump Stage 2 | 30% of peak |
| Profit Threshold | 1.5% |
| Scanner Score Threshold | 0.70 |
| Balance Manager Threshold | $400 |
| Transfer Increment | $15 |

---

**Version**: 1.0 | **Last Updated**: January 10, 2026
