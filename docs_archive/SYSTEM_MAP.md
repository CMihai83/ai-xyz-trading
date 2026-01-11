# AI_XYZ System Architecture Map

## Active Processes
- **aixyz_continuous_profit_system.py** (PID: 3848635) - Main trading engine
- **Log Monitor** (PID: 3163428) - Monitoring automated_manager_fixed.log

## Core Components

### 1. Trading Engine
- **Main Script**: `/root/ai_xyz/aixyz_continuous_profit_system.py`
- **Features**:
  - Market scanning with opportunity filtering
  - Position lifecycle management (Entry → Averaging → Surplus Dump → Exit)
  - Two-stage surplus dump (85% and 30% of peak)
  - Fibonacci-based position sizing
  - ML-driven decision making

### 2. Position Management
- **Registry**: Live position tracking with zones
- **Zones**: NEUTRAL, AVERAGING, SURPLUS_DUMP, PROFIT_TAKING, STOP_LOSS
- **State Files**:
  - `position_state.json` - Main position state
  - `averaging_state.json` - Averaging history
  - `continuous_trading_state.json` - Trading session state

### 3. Core Modules
```
/root/ai_xyz/core/
├── surplus_dump_manager.py      # Two-stage surplus dump logic
├── live_positions_registry.py   # Position registry
├── enhanced_position_registry.py # Enhanced tracking
├── position_lifecycle_manager.py # Lifecycle management
└── fibonacci_averaging_system.py # Fibonacci-based sizing
```

### 4. Services
```
/root/ai_xyz/services/
├── api-gateway/             # API endpoints
├── balance-manager/         # Portfolio balancing
├── market-scanner/          # Market opportunity detection
└── fibonacci-service/       # Fibonacci analysis
```

### 5. Configuration
- **Environment**: `/root/ai_xyz/.env`
- **Exchange**: Bitget (CCXT integration)
- **Leverage**: Dynamic (5-10x based on volatility)
- **Position Size**: Min $6.50 after leverage

## Dependencies
- Python 3.11+
- ccxt (exchange connectivity)
- structlog (logging)
- asyncio (async operations)
- redis (position registry)
- timescaledb (historical data)

## Data Flow
1. Market Scanner → Opportunity Detection
2. Fibonacci Service → Position Sizing
3. Position Manager → Order Execution
4. Registry → State Management
5. Surplus Dump Manager → Profit Taking
6. Risk Manager → Portfolio Protection

## API Endpoints
- Position status: Internal
- Market data: Bitget WebSocket
- Trading execution: Bitget REST API

## Monitoring
- Logs: `/root/ai_xyz/logs/`
- State: JSON files in root directory
- Health: Process monitoring via ps

## Cardinal Rules Compliance
- ✅ Rule 5: Two-stage surplus dump (85%/30%)
- ✅ Rule 7: Zone-based state machine
- ✅ Rule 12: Minimum position size enforcement
- ✅ Rule 15: Position registry with unique IDs