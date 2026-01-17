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
**File**: `aixyz_continuous_profit_system.py` lines 731-746
```python
zone_thresholds = {
    'averaging': -0.25,      # -25% UPNL triggers averaging (AI can override)
    'profit_taking': 0.05,   # +5% UPNL enters surplus dump zone
    'stop_loss': -0.95       # -95% UPNL (liquidation prevention ONLY, not traditional stop-loss)
}
neutral_zone_upper_usd = 0.15  # $0.15 minimum UPNL to exit neutral

# Sprint 14: Stop-loss is DISABLED - positions can recover
# Only -95% threshold for liquidation prevention
stop_loss_disabled = True
```

### 3.2 Zone States
| Zone | Trigger | Action |
|------|---------|--------|
| **NEUTRAL** | -$0.15 to +$0.15 UPNL | Hold, no action |
| **AVERAGING** | UPNL ≤ -25% | Execute Fibonacci averaging steps |
| **PROFIT_TAKING** | UPNL > +5%, no averaging | Monitor peak UPNL |
| **SURPLUS_DUMP** | UPNL > +5%, has averaged | Execute staged profit taking |
| **STOP_LOSS** | UPNL ≤ -95% | Liquidation prevention (not traditional stop-loss) |

### 3.3 Surplus Dump Strategy (Two-Stage Peak-Based)
**File**: `aixyz_continuous_profit_system.py` lines 793-794
```python
surplus_dump_threshold = 0.85       # Stage 1: 85% of PEAK → dump 50% of surplus
surplus_dump_threshold_stage2 = 0.40  # Stage 2: 40% of PEAK → dump remaining 50%
profit_threshold = 0.015            # 1.5% profit threshold for large positions
```

**How it works:**
- Tracks `peak_upnl[symbol]` - highest UPNL reached
- When UPNL drops to 85% of peak → dump 50% of surplus contracts
- When UPNL drops to 40% of peak → dump remaining 50% of surplus
- Surplus = current_size - original_size

### 3.4 Adverse Recovery V3.1.0 (Market Regime-Based)
**File**: `aixyz_continuous_profit_system.py` lines 796-807
```python
# V3.1.0: Lenient thresholds for positions opened during adverse market conditions
adverse_recovery_threshold_stage1 = 0.50  # 50% of peak (hold longer)
adverse_recovery_threshold_stage2 = 0.20  # 20% of peak (hold longer)
adverse_market_regimes = ['high_vol', 'crisis']
recovered_market_regimes = ['normal_vol', 'low_vol']

# Tracks market regime when position was opened
position_opened_regime: Dict[str, str] = {}
```

**Logic:**
1. When position OPENS → record current market regime from Grok V2 HMM
2. During averaging → update to WORST regime seen
3. At surplus dump: if opened in HIGH_VOL/CRISIS and now NORMAL/LOW → use 50/20 thresholds

| Mode | Stage 1 | Stage 2 | When Used |
|------|---------|---------|-----------|
| STANDARD | 85% of peak | 40% of peak | Normal market conditions |
| ADVERSE RECOVERY | 50% of peak | 20% of peak | Opened in crisis, market recovered |

---

## 4. Adaptive Fibonacci Averaging System

### 4.1 Core Concept
- Uses golden ratio (φ = 1.618) for position scaling
- Dynamic delta calculation based on market volatility
- Timeframe-based capital allocation (1m, 5m, 15m, 1h, 4h, 1d)
- Maximum 8 averaging steps per position

### 4.2 Key Components
```python
AdaptiveFibonacciAveraging(total_capital=20.0)  # Core averaging logic
DynamicFibonacciDeltaService                     # Volatility-adaptive delta
TimeframeSpeedTracker                            # Dynamic threshold adjustment
TimeframeCapitalAllocator                        # Capital distribution
```

### 4.3 Base Averaging Multipliers
**File**: `aixyz_continuous_profit_system.py` lines 775-784
```python
base_averaging_multipliers = [
    0.5,   # Step 1: 0.5x original (small test)
    0.75,  # Step 2: 0.75x original (conservative)
    1.5,   # Step 3: 1.5x original (moderate)
    3.0,   # Step 4: 3x original (aggressive)
    5.0,   # Step 5: 5x original (Fibonacci F5)
    8.0,   # Step 6: 8x original (Fibonacci F6)
    12.0,  # Step 7: 12x original (extreme)
    15.0   # Step 8: 15x original (final push)
]
```

### 4.4 Grok V2 Reduced Multipliers
**File**: `aixyz_continuous_profit_system.py` lines 971-988
```python
# Grok V2: Reduced from 19x total to 10x total for better risk control
if averaging_steps_possible == 5:
    averaging_multipliers = [1.0, 1.5, 2.0, 2.5, 3.0]  # 10x total
elif averaging_steps_possible == 4:
    averaging_multipliers = [1.0, 1.5, 2.0, 2.5]       # 7x total
elif averaging_steps_possible == 3:
    averaging_multipliers = [1.0, 1.5, 2.0]            # 4.5x total
```

### 4.5 Averaging Execution
- Tracks `averaging_steps[symbol]` (0-8)
- Tracks `original_sizes[symbol]` for surplus calculation
- Tracks `peak_upnl[symbol]` for profit taking
- Tracks `position_opened_regime[symbol]` for adverse recovery

---

## 5. Market Scanner (V4.0)

### 5.1 Two-Stage Filtering
**File**: `scanner_v4.py`
```
Stage 1: Quick Filter (ALL ~497 USDT perpetual futures)
  → Volume filter: > $10M 24h volume
  → Liquidity filter: < 0.5% bid-ask spread
  → Volatility filter: 1% ≤ volatility ≤ 20%
  → Output: ~120-140 candidates (25-28%)

Stage 2: Deep Analysis (Top 40 by volume × volatility)
  → VSA (Volume Spread Analysis) scoring
  → MACD divergence detection
  → Support/resistance levels
  → Multi-timeframe confirmation
  → Entry threshold: >= 0.70
  → Minimum score: >= 0.55
```

### 5.2 Scan Cycle
- Scans every ~60 seconds
- Target scan time: 25-35 seconds
- API calls per scan: ~160-330

---

## 6. AI/ML Modules

### 6.1 Grok V2 Integration Modules (11 Modules)
**File**: `grok_v2_integration.py`

| # | Module | File | Purpose |
|---|--------|------|---------|
| 1 | Trade Tracker | `trade_results_tracker.py` | Profit factor metrics |
| 2 | Bayesian Correction | `grok_v2_bayesian_correction.py` | Per-symbol correction probability |
| 3 | Volatility HMM | `grok_v2_volatility_regime_hmm.py` | 4-regime detection |
| 4 | Redis Pool | `grok_v2_redis_pool.py` | Connection pooling |
| 5 | VaR Calculator | `grok_v2_var_integration.py` | Value at Risk limits |
| 6 | WebSocket Events | `grok_v2_websocket_events.py` | Real-time updates |
| 7 | Stress Testing | `grok_v2_stress_testing.py` | Scenario analysis |
| 8 | Ensemble Exit | `grok_v2_ensemble_exit.py` | Multi-model exit signals |
| 9 | Online CSSI | `grok_v2_online_cssi_learning.py` | Continuous learning |
| 10 | Anomaly Detection | `grok_v2_anomaly_detection.py` | Z-score anomalies |
| 11 | Graceful Degradation | `grok_v2_graceful_degradation.py` | Fallback mechanisms |

### 6.2 Volatility Regime HMM (4 Regimes)
**File**: `grok_v2_volatility_regime_hmm.py` lines 22-27
```python
class VolatilityRegime(Enum):
    LOW_VOL = "low_vol"       # 0-20% annualized
    NORMAL_VOL = "normal_vol" # 15-40% annualized
    HIGH_VOL = "high_vol"     # 35-80% annualized
    CRISIS = "crisis"         # 70-200% annualized
```

**Transition Matrix** (regimes tend to persist):
```
             LOW    NORMAL  HIGH   CRISIS
LOW_VOL    [ 0.90,  0.08,  0.02,  0.00 ]
NORMAL_VOL [ 0.10,  0.80,  0.08,  0.02 ]
HIGH_VOL   [ 0.02,  0.10,  0.80,  0.08 ]
CRISIS     [ 0.00,  0.05,  0.15,  0.80 ]
```

### 6.3 Category 1 - High Priority (Active)
| Module | Purpose | Benefit |
|--------|---------|---------|
| `RLClosingAgent` | Q-learning exit timing | +15-25% better exits |
| `MarkowitzOptimizer` | Portfolio optimization | +20% capital efficiency, -30% risk |
| `CorrelationMatrixAnalyzer` | Diversification | -25% correlated drawdowns |
| `OpportunityCostPredictor` | ML capital rotation | +20% faster rotation |

### 6.4 Performance Modules (V1.1.0)
- `MomentumBurstDetector` - 1% burst threshold
- `ConfidenceTierSystem` - Signal quality filtering (min 0.55)
- `DynamicPositionSizer` - +30% profit per winning trade
- `KellyCriterionSizer` - Optimal growth rate
- `VelocityProfitTaker` - Speed-based profit taking

### 6.5 Market Microstructure (V1.2.0)
- `FundingRateOptimizer` - Funding rate arbitrage
- `OrderBookImbalanceDetector` - Order flow analysis
- `PartialCloseLadder` - Staged exits (25% at 2%, 4%, 6%)
- `ATRStopLoss` / `TrailingATRStop` - Volatility-based stops (1.5x ATR)

### 6.6 V3 AI Components (TensorFlow)
- `AdaptiveThresholdEngine` - AI-driven thresholds
- `AIMarketIntelligence` - Market regime detection
- `OpportunityCostEngine` - V3 opportunity analysis
- `AdvancedDeltaEngine` - AI delta calculation
- `AdaptiveAveragingEngine` - AI averaging decisions

### 6.7 CSSI - Correction-Support Strength Index
**File**: `historical_correction_analyzer.py` lines 73-83
```python
@dataclass
class CSSI:
    cssi_score: float              # Main metric (0-3+)
    correction_probability: float  # From logistic regression
    support_proximity: float       # 0-1 (1 = at support)
    risk_factor: float            # 0.3-1.0
    recommended_action: str        # 'AVERAGE_IN', 'HOLD', 'REDUCE'
    step_multiplier: float        # Position size modifier (0.5-2.0)
```

**Formula**:
```
CSSI = (correction_probability / 100) × proximity_to_support × risk_factor

Correction Probability (Logistic Regression):
P(correction | depth) = 1 / (1 + exp(-β₀ - β₁×d - β₂×d²))
  β₀ = -1.0, β₁ = 20.0, β₂ = 0.0

Example Probabilities:
- 5% drawdown:  ~50% correction probability
- 10% drawdown: ~80% correction probability
- 15% drawdown: ~92% correction probability
```

| CSSI Score | Action | Step Multiplier |
|------------|--------|-----------------|
| ≥ 1.5 | AVERAGE_IN_AGGRESSIVE | 1.45-2.0x |
| ≥ 1.0 | AVERAGE_IN | 1.2-1.5x |
| ≥ 0.5 | HOLD | 1.0x |
| < 0.5 | REDUCE | 0.5-1.0x |

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

### 8.3 Hedge Gateway
Automatic hedge protection system that opens counter-positions.

```python
HedgeGateway:
  - Auto-opens hedge (opposite position) when main position opens
  - Tracks hedges separately in Redis (hedge_gateway:state)
  - Gate system: closes hedge portions at averaging steps 2 and 5
  - State: hedges dict with symbol, side, size, remaining
```

**Hedge Position Averaging Gate** (V2 - January 2026):
```python
# Hedge positions require -70% UPNL before averaging (stricter than main)
# Main positions: -25% UPNL gate (normal)
# Hedge positions: -70% UPNL gate (protective)

# Location: aixyz_continuous_profit_system.py:3015-3040
hedge_gate_threshold = -70.0  # Only for hedge positions
```

| Position Type | Averaging Gate |
|---------------|----------------|
| Main positions | -25% P&L |
| Hedge positions | -70% P&L |

**Check active hedges:**
```bash
docker exec ai_xyz_redis redis-cli GET "hedge_gateway:state" | python3 -m json.tool
```

### 8.4 Position Sync State Synchronization (Critical Fix)

**Important**: When averaging steps execute, the counter MUST be synced to EnhancedPositionSync.

```python
# After incrementing averaging_steps, sync to EnhancedPositionSync:
if hasattr(self, 'sync_integration') and self.sync_integration:
    self.sync_integration.sync.update_averaging_state(
        symbol,
        self.averaging_steps[symbol],
        multipliers=self.position_multipliers.get(symbol, []),
        last_price=current_price,
        fibonacci_config=self.fibonacci_configs.get(symbol)
    )
```

**Why this matters:**
- `position_sync_integration._update_system_state()` OVERWRITES all tracking dicts from EnhancedPositionSync
- If EnhancedPositionSync isn't notified of averaging, reconciliation resets the counter to 0
- This caused liquidations because protection orders only placed after max steps

**Sync calls are at:**
- `aixyz_continuous_profit_system.py:3178` - historical averaging
- `aixyz_continuous_profit_system.py:3487` - adaptive averaging
- `aixyz_continuous_profit_system.py:4364` - pyramid execution

### 8.5 Redis Database Configuration (CRITICAL)

**IMPORTANT**: The persistence manager uses Redis database 1 (db=1), NOT database 0!

```python
# position_persistence_manager.py - connects to db=1
self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=1)
```

**State storage locations:**
| Source | Redis DB | Key Pattern | Priority |
|--------|----------|-------------|----------|
| PositionPersistenceManager | db=1 | `aixyz:position_state` | 1 (highest) |
| EnhancedPositionSync | db=0 | `aixyz:sync:position:{symbol}` | 2 |
| Host file (fallback) | N/A | `/app/position_state.json` | 3 (lowest) |

**To fix corrupted averaging_steps:**
```bash
# 1. Stop the container
docker stop ai_xyz_trading_system

# 2. Delete corrupted state from db=1 (NOT db=0!)
docker exec ai_xyz_redis redis-cli -n 1 DEL "aixyz:position_state"
docker exec ai_xyz_redis redis-cli -n 1 KEYS "aixyz:*" | xargs -r -I{} docker exec ai_xyz_redis redis-cli -n 1 DEL "{}"

# 3. Also delete sync keys from db=0
docker exec ai_xyz_redis redis-cli -n 0 KEYS "aixyz:sync:position:*" | xargs -r -I{} docker exec ai_xyz_redis redis-cli -n 0 DEL "{}"

# 4. Fix the host file (edit averaging_steps values)
vim /root/ai_xyz/position_state.json

# 5. Start the container (will load from file)
docker start ai_xyz_trading_system
```

---

## 9. Key Files Reference

### 9.1 Main System
```
aixyz_continuous_profit_system.py  - Main trading loop (258KB)
hedge_gateway.py                    - Hedge position management
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

## 15. TIERED CAPITAL ALLOCATION (V3.1.0)

### 15.1 Regime-Based Position Limits
**File**: `tiered_capital_allocation.py` lines 236-328

| HMM Regime | Tiers Active | Positions Allowed |
|------------|--------------|-------------------|
| LOW_VOL / NORMAL_VOL | Tier 1 only | 1/3 of max |
| HIGH_VOL | Tier 1 + Tier 2 | 2/3 of max |
| CRISIS | Tier 1 + Tier 2 + Tier 3 | 3/3 (full) |

**Example** (max_positions = 30):
- NORMAL_VOL: 10 positions max
- HIGH_VOL: 20 positions max
- CRISIS: 30 positions max

### 15.2 Key Methods
```python
# Get max positions for current HMM regime
tiered = get_tiered_allocation()
regime_max = tiered.get_max_positions_for_regime(hmm_regime)

# Check if new position should be blocked
blocked, reason = tiered.should_block_new_position(current_count, hmm_regime)

# Get tier from HMM regime
tier = tiered.get_tier_from_hmm_regime(hmm_regime)
```

### 15.3 Integration with Scanner
**File**: `aixyz_continuous_profit_system.py` lines 6569-6603
```python
# Scanner loop enforces regime-based limits
if TIERED_ALLOCATION_AVAILABLE:
    tiered = get_tiered_allocation()
    regime_state = self.grok_v2.volatility_hmm.get_regime()
    current_regime = regime_state.regime.value
    regime_max_positions = tiered.get_max_positions_for_regime(current_regime)
```

---

## 16. SYMBOL-SPECIFIC THRESHOLD CALIBRATION (V3.4.0)

### 16.1 Overview
**File**: `symbol_threshold_calibrator.py`

The averaging P&L threshold is now calibrated per-symbol based on:
1. **HMM Volatility Regime** - Base threshold from market conditions
2. **Volatility Ratio vs BTC** - Higher vol coins get wider thresholds
3. **BTC Correlation** - Uncorrelated coins get wider thresholds
4. **CSSI Correction Probability** - WIDER if correction likely (V3.4.0 inverted)
5. **Historical Max Drawdown** - Based on backtest data

**V3.4.0 Changes (Grok recommendations):**
- A: Reduced vol weight from 0.5 to 0.3 for mid-caps (vol_ratio 1.5-2.5)
- B: Inverted CSSI logic (correction likely = WIDER threshold, wait longer)
- C: Live data priority (try exchange first, then defaults)
- D: Widened clamp range from [-50%, -20%] to [-60%, -15%]

### 16.2 Base Thresholds (from HMM Regime)
| HMM Regime | Base Threshold | Rationale |
|------------|----------------|-----------|
| LOW_VOL | -25% | Aggressive - stable market |
| NORMAL_VOL | -30% | Balanced approach |
| HIGH_VOL | -35% | Conservative |
| CRISIS | -45% | Very conservative |

### 16.3 Calibration Formula (V3.4.0)
```python
def get_symbol_adjusted_threshold(symbol, hmm_regime, current_drawdown):
    base_threshold = regime_thresholds[hmm_regime]  # e.g., -30%

    # Get symbol factors (V3.4.0: try LIVE data first)
    vol_ratio = get_volatility_ratio(symbol)      # e.g., DOGE=2.5x BTC
    btc_corr = get_btc_correlation(symbol)        # 0-1
    correction_prob = get_correction_probability(symbol)
    max_dd = get_historical_max_drawdown(symbol)

    # V3.4.0-A: Volatility weight varies by coin type
    if vol_ratio <= 2.5:
        vol_weight = 0.3  # Mid-caps: reduced weight
    else:
        vol_weight = 0.5  # Meme coins: full weight
    vol_adj = (vol_ratio - 1) * vol_weight

    corr_adj = (1 - btc_corr) * 0.2       # +20% for uncorrelated

    # V3.4.0-B: INVERTED CSSI logic
    cssi_adj = +correction_prob * 0.1     # +10% if correction likely (wait LONGER)

    backtest_adj = max_dd / 200           # +25% for 50% historical DD

    adjusted = base_threshold * (1 + vol_adj + corr_adj + cssi_adj + backtest_adj)
    return max(-60.0, min(-15.0, adjusted))  # V3.4.0-D: Widened clamp range
```

### 16.4 Example Calibrated Thresholds (NORMAL_VOL, V3.4.0)
| Symbol | Vol Ratio | Vol Weight | BTC Corr | Calibrated Threshold |
|--------|-----------|------------|----------|---------------------|
| BTC | 1.0x | 0.3 | 1.0 | -30.0% (base) |
| ETH | 1.2x | 0.3 | 0.85 | -31.5% |
| SOL | 1.5x | 0.3 | 0.75 | -33.8% |
| POL | 1.8x | 0.3 | 0.65 | -37.6% |
| DOGE | 2.5x | 0.3 | 0.60 | -41.2% |
| PEPE | 3.5x | 0.5 | 0.45 | -53.4% |
| WIF | 3.0x | 0.5 | 0.40 | -49.8% |

### 16.5 Alignment with Tiered Capital Allocation
| Regime | Position Limit | Base Threshold | Per-Symbol Adjustment |
|--------|----------------|----------------|----------------------|
| LOW_VOL/NORMAL_VOL | 1/3 of max | -25%/-30% | ±10-20% based on factors |
| HIGH_VOL | 2/3 of max | -35% | ±10-15% based on factors |
| CRISIS | 3/3 of max | -45% | ±5-10% based on factors |

---

## QUICK REFERENCE TABLE

| Parameter | Value |
|-----------|-------|
| Exchange | Bitget (USDT-M Futures) |
| Max Positions | 30 total (tiered: 10/20/30 based on regime) |
| Base Margin | $5.00 |
| Averaging Capital | $20.00 |
| Total per Position | $25 + $25 protection = $50 |
| Leverage | 5x default, 20x max |
| Averaging Steps | 8 max |
| Neutral Zone | -$0.15 to +$0.15 USD |
| Averaging Trigger (Main) | Dynamic: -25%/-30%/-35%/-45% based on HMM regime |
| Averaging Trigger (Hedge) | -70% UPNL |
| Profit Taking | +5% UPNL |
| Stop Loss | -95% UPNL (liquidation prevention only) |
| Surplus Dump Stage 1 | 85% of peak |
| Surplus Dump Stage 2 | 40% of peak |
| Adverse Recovery Stage 1 | 50% of peak |
| Adverse Recovery Stage 2 | 20% of peak |
| Liquidation Protection | -82.5% UPNL at step ≥ 6 |
| Scanner Entry Threshold | >= 0.70 |
| Scanner Minimum Score | >= 0.55 |
| Scanner Volume Filter | > $10M 24h |
| HMM Regimes | LOW_VOL, NORMAL_VOL, HIGH_VOL, CRISIS |
| Balance Manager Threshold | $400 |
| Transfer Increment | $15 |

---

## 13. AUTHORITATIVE SYSTEM DOCUMENTATION

### 13.1 Primary Documentation (MEMORIZED)

**IMPORTANT**: The authoritative comprehensive system documentation is:

```
/root/ai_xyz/AI_XYZ_SYSTEM_DOCUMENTATION_V2.md
```

**Version**: 2.0
**Created**: January 11, 2026
**Authors**: Claude (Opus 4.5) & Grok Consortium Analysis
**Lines**: 1,188

This document contains:
- Complete system architecture with diagrams
- ALL mathematical formulas with file:line references
- Zone-based position management state machine
- Fibonacci averaging system with golden ratio tiers
- CSSI (Correction-Support Strength Index) full documentation
- Multi-timeframe confirmation (MTF) logic
- Risk management framework
- AI/ML modules catalog (68+ modules documented)
- State management and persistence details
- Market Scanner V4.0 two-stage filtering
- Complete file reference with line numbers
- All configuration variables
- 14 improvement recommendations with code examples

### 13.2 Archived Documentation

**Location**: `/root/ai_xyz/docs_archive/`

All previous documentation files (86 files) were archived on January 11, 2026.
These are **OBSOLETE** and superseded by `AI_XYZ_SYSTEM_DOCUMENTATION_V2.md`.

See `docs_archive/ARCHIVE_NOTICE.md` for details.

### 13.3 Key Formula Quick Reference

| Formula | Expression | Source |
|---------|------------|--------|
| **UPNL%** | `(current - entry) / entry × lev × 100` | main.py:2556 |
| **Dynamic Delta** | `base × vol_mult × corr_factor` | delta.py:165 |
| **Liquidation Price** | `entry × (1 ± upnl% / (lev × 100))` | liq.py:258 |
| **CSSI** | `correction% × proximity × risk_factor` | cssi.py:713 |
| **Correction Prob** | `1 / (1 + exp(-(β₀ + β₁d + β₂d²)))` | cssi.py:360 |

---

## 14. MUTUAL AGREEMENT DOCUMENT

A comprehensive review was conducted on January 16, 2026 between Claude (Opus 4.5) and Grok (grok-2-latest) to verify system understanding against actual codebase.

**Document**: `/root/ai_xyz/MUTUALLY_AGREED_SYSTEM_UNDERSTANDING.md`

All discrepancies were resolved with code evidence. Key corrections:
- Stop-loss is -95% (not -90%) - liquidation prevention only
- Surplus Dump Stage 2 is 40% (not 30%)
- 4 volatility regimes including CRISIS (not 3)
- Scanner volume filter is $10M (not $1M)
- V3.1.0 Adverse Recovery is market regime-based

---

## 17. OPPORTUNITY COST SERVICE V3.5.0

### 17.1 Overview
**Files**: `v3_opportunity_cost_engine.py`, `opportunity_cost_calibrator.py`

The opportunity cost service determines when to close profitable positions based on
whether better opportunities exist in the market. V3.5.0 implements symbol-specific
calibration based on backtest validation with real market data.

### 17.2 Backtest Findings (30 days, 8 symbols, 240 trades)

| Metric | Current (V3) | Proposed (V3.5) | Change |
|--------|--------------|-----------------|--------|
| Total P&L | $16.48 | $168.00 | **+919%** |
| Win Rate | 52.5% | 62.1% | **+9.6%** |
| Avg Holding | 8h fixed | 80.5h tiered | Flexible |
| Opp Cost at Exit | 1.62% | 0.83% | Better timing |

**Critical Finding**: Fixed 8-hour max holding was forcing exits on ALL trades.

### 17.3 V3.5.0 Changes (Grok Recommendations)

| ID | Change | Before | After |
|----|--------|--------|-------|
| 1A/1B | Symbol-specific thresholds | Fixed 5%/3%/2% | Calibrated by vol/corr |
| 2A/2B | Percentage-based guard | Fixed $0.15 | 3% of position |
| 5A/5B | Tiered max holding | Fixed 480min | Tiered by vol/avg |

### 17.4 Tiered Max Holding Times
**File**: `opportunity_cost_calibrator.py`

| Condition | Max Holding | Rationale |
|-----------|-------------|-----------|
| Averaged positions (steps > 0) | 7 days | Recovery trades need time |
| Low vol (BTC-like, ratio ≤ 1.5) | 12 hours | Steady, can hold longer |
| Mid vol (alts, ratio 1.5-2.5) | 8 hours | Balanced approach |
| High vol (meme, ratio > 2.5) | **4 hours** | Backtest showed -11.8% with long holds |

### 17.5 Symbol-Specific Thresholds
```python
# Calibration formula
vol_mult = 1.0 + (vol_ratio - 1.5) * weight  # weight: 0.3 mid, 0.5 meme
corr_mult = 1.0 + (1 - btc_corr) * 0.2

calibrated_threshold = base_threshold * vol_mult * corr_mult
```

| Symbol | Vol Ratio | BTC Corr | High Cost | Max Hold |
|--------|-----------|----------|-----------|----------|
| BTC | 1.0 | 1.0 | 5.0% | 720min |
| ETH | 1.2 | 0.85 | 5.2% | 720min |
| SOL | 1.5 | 0.75 | 5.3% | 480min |
| POL | 1.8 | 0.65 | 5.8% | 480min |
| DOGE | 2.5 | 0.60 | 7.0% | 480min |
| PEPE | 3.5 | 0.45 | 11.1% | **240min** |

### 17.6 Percentage-Based Guard
```python
# Old: Fixed guard
if unrealized_pl_usd <= 0.15:  # $0.15 fixed
    return HOLD

# New: Percentage-based guard (3% of position)
guard_usd = position_size_usd * 0.03  # Scales with position
if unrealized_pl_usd <= guard_usd:
    return HOLD
```

### 17.7 AI Components (Unchanged)
- **DynamicThresholdEngine**: Adjusts thresholds by market regime
- **OpportunityCostPredictor**: ML ensemble (RF + GB + LSTM)
- **CorrelationMatrixAnalyzer**: Portfolio correlation analysis
- **MarkowitzOptimizer**: Mean-variance optimization
- **RLClosingAgent**: Q-learning for exit timing

---

**Version**: 3.5.0 | **Last Updated**: January 16, 2026
**Reviewed By**: Claude (Opus 4.5) & Grok (grok-2-latest)
**Status**: Mutually Agreed

### V3.5.0 Changelog
- Opportunity Cost Service calibration (Grok recommendations 1-6)
- Symbol-specific thresholds based on volatility/correlation
- Percentage-based guard (3% instead of fixed $0.15)
- Tiered max holding times (meme=4h, averaged=7d)
- Backtest validated with real market data (+919% P&L improvement)

---

## MEMORIZED PRINCIPLES

### Always Backtest First with Real Data
**CRITICAL**: Before implementing any parameter changes or strategy modifications:
1. Create a backtest script that uses REAL market data from the exchange
2. Compare current vs proposed implementation
3. Validate improvements across different symbol volatility profiles (BTC, alts, meme coins)
4. Only implement changes that show measurable improvement in backtest
5. Document backtest results in CLAUDE.md

Example workflow:
```bash
# 1. Create backtest
python3 opportunity_cost_backtest.py

# 2. Analyze results by volatility category
# - Low vol (BTC-like): Should benefit from longer holding
# - Mid vol (alts): Balanced approach
# - High vol (meme): May need SHORTER holding (inverse of intuition!)

# 3. Implement based on data, not assumptions
# 4. Rebuild and verify
docker compose build ai_xyz_trading --no-cache
docker compose up -d ai_xyz_trading
```

### Live Data Priority
Always try to fetch LIVE data from the exchange before falling back to defaults.
This ensures calibration adapts to current market conditions.

### Always Backtest with Different Timeframes
**CRITICAL**: A strategy that works on 1h candles may FAIL on 5m or 4h candles. Before implementing:
1. Test across multiple timeframes: 5m, 15m, 1h, 4h (minimum)
2. Verify improvement is CONSISTENT across timeframes
3. If strategy works on some timeframes but not others:
   - Consider timeframe-adaptive parameters
   - Investigate why it fails on specific timeframes
   - Do NOT implement until understood
4. Document which timeframe shows best results

Example workflow:
```bash
# Run multi-timeframe backtest
python3 opportunity_cost_backtest.py --mode multi --timeframes 5m 15m 1h 4h

# Verify CONSISTENT improvement across ALL timeframes
# If improvement is negative on ANY timeframe, investigate before implementing
```

**Key Insight**: High-frequency timeframes (1m, 5m) capture different market dynamics than low-frequency (4h, 1d). A robust strategy should work across the spectrum.

### V3.4.0 Changelog
- Symbol-specific calibration improvements (Grok recommendations A-D)
- Reduced volatility weight for mid-caps (0.5 → 0.3)
- Inverted CSSI logic (correction likely = wait longer)
- Live data priority for volatility/correlation
- Widened clamp range (-60% to -15%)

---

## 18. Dynamic Position Manager V1.0.0 (Consortium Design)

**File**: `dynamic_position_manager.py`
**Design**: Claude + Grok Consortium (January 16, 2026)

### Multi-Factor Position Sizing

Determines position parameters based on 4 factors:

| Factor | Weight | Effect |
|--------|--------|--------|
| **Volatility** | 40% | Higher vol = smaller positions, more averaging room |
| **BTC Correlation** | 30% | High corr = reduce allocation (systemic risk) |
| **Trend Strength** | 20% | Strong trend = larger positions, more averaging |
| **Funding Rate** | 10% | Extreme funding = reduce exposure |

### Factor Calculation

```python
vol_score = min(annualized_vol / 0.50, 1.0)
corr_score = (1 + pearson_corr(asset, btc)) / 2
trend_score = min(ADX / 50, 1.0)
funding_score = min(abs(funding_rate) / 0.001, 1.0)

# Combined Position Type Score (higher = riskier)
PTS = 0.4*vol + 0.3*corr + 0.2*(1-trend) + 0.1*funding
```

### Position Parameters from PTS

```python
base_margin = base_max * (1 - 0.6*vol - 0.3*corr + 0.1*trend)
total_allocation = alloc_max * (1 - 0.5*vol - 0.3*corr - 0.2*funding)
max_steps = round(8 * (0.5*trend + 0.3*(1-vol) + 0.2*(1-funding)))
```

### Risk Tiers

| Tier | PTS Range | base_margin | total_allocation | max_steps | leverage |
|------|-----------|-------------|------------------|-----------|----------|
| CONSERVATIVE | < 0.35 | $1.50-2.00 | $15-20 | 5-8 | 10x |
| MODERATE | 0.35-0.65 | $0.70-1.50 | $10-15 | 4-6 | 7x |
| AGGRESSIVE | > 0.65 | $0.30-0.70 | $5-10 | 2-4 | 5x |

### Dynamic MAX_POSITIONS

```python
max_positions = min(
    equity * 0.25 / base_allocation_reference,
    HARD_CAP_30
)

effective_slots_used = sum(pos.total_allocation / 25.0)
remaining_capacity = max_positions - effective_slots_used
```

### Safety Mechanisms

1. **Block high-risk positions** when equity < 50% of initial
2. **Only allow CONSERVATIVE** when equity < 30% of initial
3. **Emergency de-risk** when UPNL < -20% of equity

### Backtest Results (240 trades, $404 equity)

| Timeframe | Trades | P&L | Win Rate |
|-----------|--------|-----|----------|
| 15m | 80 | $1.09 | 57.5% |
| 1h | 80 | $9.69 | 83.8% |
| 4h | 80 | $40.41 | 98.8% |
| **TOTAL** | 240 | **$51.19** | - |

### Usage

```python
from dynamic_position_manager import get_dynamic_position_manager

manager = get_dynamic_position_manager(equity=404.0)
config = manager.calculate_position_parameters('PEPE/USDT:USDT')

print(f"Tier: {config.risk_tier.value}")
print(f"Base: ${config.base_margin:.2f}")
print(f"Allocation: ${config.total_allocation:.2f}")
print(f"Max Steps: {config.max_averaging_steps}")
```

---

## 19. V3.5.1 STATE SYNCHRONIZATION FIX (Jan 17, 2026)

### 19.1 Bug Description
**Issue**: Position state (averaging_steps) persisted across position cycles, causing surplus dump failures.

**Root Cause**: Multiple Redis persistence layers (db=0: EnhancedPositionSync, db=1: PositionPersistenceManager) storing state independently. When a position closed, db=1 was cleared but db=0 retained stale state that was restored on new position open.

**Impact**: BLUR position stuck at +59% profit with near-zero surplus (0.1 contracts instead of expected ~38,000).

### 19.2 Fix Implementation

**File**: `aixyz_continuous_profit_system.py`

**Change 1: Clear EnhancedPositionSync on position close (line 5840-5847)**
```python
# V3.5.1 FIX: Clear EnhancedPositionSync state (Redis db=0)
if hasattr(self, 'sync_integration') and self.sync_integration:
    try:
        self.sync_integration.sync._remove_position_state(symbol)
        print(f"  🔄 Cleared EnhancedPositionSync state for {symbol}")
    except Exception as sync_err:
        print(f"  ⚠️ Failed to clear sync state: {sync_err}")
```

**Change 2: Startup validation for stale averaging_steps (line 655-685)**
```python
# V3.5.1 FIX: Detect STALE averaging_steps (high steps but no actual surplus)
if steps > 0 and symbol in self.original_sizes:
    surplus = current - original
    margin = pos.get('initial_margin', 5.0)

    # If surplus is <20% of current AND margin is small, state is stale
    if actual_surplus_ratio < 0.2 and margin < expected_min_margin:
        print(f"⚠️ STALE STATE DETECTED for {symbol}")
        self.averaging_steps[symbol] = 0
        self.original_sizes[symbol] = current
        self.position_zones[symbol] = 'NEUTRAL'
```

### 19.3 Grok Feedback (Jan 17, 2026)

**Recommendations integrated into Sprint 15 backlog:**
1. ✅ V3.5.1 fix approach confirmed correct
2. Add position timestamp tracking for stale state detection
3. Implement automated alerts for stuck positions
4. Add zone transition logging for monitoring
5. Extend startup validation to other critical state variables
6. Conduct stress testing for state synchronization

### 19.4 Sprint 15 Backlog

See `/root/ai_xyz/SPRINT_BACKLOG.json` for full backlog.

| ID | Title | Priority | Status |
|----|-------|----------|--------|
| S15-001 | BLUR State Corruption Fix | P0 | ✅ Completed |
| S15-002 | Position Timestamp Tracking | P1 | Backlog |
| S15-003 | Automated Stuck Position Alerts | P2 | Backlog |
| S15-004 | Zone Transition Logging | P2 | Backlog |
| S15-005 | Extend Startup Validation | P1 | Backlog |
| S15-006 | State Sync Stress Testing | P2 | Backlog |

---

**Version**: 3.5.1 | **Last Updated**: January 17, 2026
**Reviewed By**: Claude (Opus 4.5) & Grok (grok-2-latest)
**Status**: Deployed & Operational
