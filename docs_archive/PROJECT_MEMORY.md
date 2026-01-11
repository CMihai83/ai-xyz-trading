# AI-XYZ System Architecture and Flow Knowledge

## System Components Overview

### Main Entry Point
- **File**: `/root/ai_xyz/start_integrated_fibonacci.py`
- **Process**: PID 1881540 (running since Sep 14)
- **Functions**:
  - `main()`: Entry point, starts all services
  - `start_service()`: Launches microservices on designated ports
  - `verify_integration()`: Tests Fibonacci module imports
  - `monitor_system()`: Polls Bitget every 10 seconds for positions

### Core Modules

#### 1. AdaptiveFibonacciCalculator
- **Location**: `/root/ai_xyz/core/adaptive_fibonacci_averaging.py`
- **Purpose**: Distributes delta across Fibonacci steps for averaging
- **Key Methods**:
  - `calculate_adaptive_config()`: Main config generator
  - `generate_fibonacci_sequence()`: Creates [21, 13, 8, 5, 3] sequence
  - `calculate_cumulative_thresholds()`: Cumulative percentages
  - `optimize_k_coefficient()`: Position size multiplier
  - `backtest_configurations()`: Tests 3-7 steps for optimal config

#### 2. FibonacciDeltaCalculator  
- **Location**: `/root/ai_xyz/services/api-gateway/src/fibonacci_delta_calculator.py`
- **Purpose**: Calculates optimal delta from market conditions
- **Key Methods**:
  - `calculate_dynamic_thresholds()`: Main entry point
  - `_fetch_market_data()`: Gets multi-timeframe data
  - `_analyze_market_regime()`: Detects market state
  - `_calculate_volatility()`: Volatility analysis
  - `_calculate_optimal_delta()`: Determines max price movement

### Microservices Architecture

#### Service Ports and Locations
1. **API Gateway** (Port 9000)
   - Path: `/root/ai_xyz/services/api-gateway/src/main.py`
   - Imports: futures_trading_engine, bitget_futures_client, live_positions_registry
   - Functions: startup_event(), get_system_status(), process_trading_signal()

2. **Market Scanner** (Port 9001)
   - Path: `/root/ai_xyz/services/market-scanner/src/main.py`
   - Scans Bitget for opportunities
   - Sends to AI Decision Engine

3. **AI Decision Engine** (Port 9002)
   - Path: `/root/ai_xyz/services/ai-decision-engine/src/main.py`
   - Analyzes signals with Fibonacci
   - Validates through Risk Engine

4. **Position Management** (Port 9003)
   - Path: `/root/ai_xyz/services/position-management/src/main.py`
   - Redis DB 3 for storage
   - Zone-based management (Accumulation, Distribution, Profit Taking, Stop Loss)

5. **Risk Engine** (Port 9009)
   - Path: `/root/ai_xyz/services/risk-engine/src/main.py`
   - Validates all trades
   - Enforces risk limits

### Data Flow

1. **Market Scanning**:
   ```
   Market Scanner → Bitget API → Opportunities → AI Decision Engine
   ```

2. **Position Opening**:
   ```
   AI Decision Engine → Risk Engine → Position Manager → Bitget Execute → Redis Store
   ```

3. **Position Monitoring**:
   ```
   start_integrated_fibonacci → monitor_system() → Bitget fetch_positions() → Display
   ```

4. **Fibonacci Integration**:
   ```
   FibonacciDeltaCalculator (calculates delta) → AdaptiveFibonacciCalculator (distributes) → Position Manager
   ```

### Key Integration Points

#### Exchange Integration
- **Client**: BitgetFuturesClient
- **Reconciliation**: ExchangeReconciliationService
- **API Credentials**: Stored in settings module
- **Position Format**: SYMBOL/USDT:USDT

#### Data Persistence
- **Redis DB 3**: Live position registry
- **In-memory cache**: Market data with 5min TTL
- **Log files**: `/root/ai_xyz/integrated_system.log`

#### Zone Management
- **Neutral Zone**: Default state
- **Averaging Zone**: UPNL ≤ -15%
- **Surplus Dump**: After averaging, UPNL > +15%
- **Profit Taking**: Direct profit without averaging
- **Stop Loss**: Critical loss threshold

### Current System Status
- **Running Services**: 5 microservices
- **Active Positions**: 5 (monitored every 10s)
- **Balance**: $25.56 USDT
- **Fibonacci Sequence**: [21, 13, 8, 5, 3]
- **Cumulative Thresholds**: [42%, 68%, 84%, 94%, 100%]

### File Dependencies Map
```
start_integrated_fibonacci.py
├── adaptive_fibonacci_averaging.py
│   └── fibonacci_delta_calculator.py
├── api-gateway/main.py
│   ├── futures_trading_engine.py
│   ├── bitget_futures_client.py
│   ├── live_positions_registry.py
│   ├── exchange_reconciliation.py
│   └── position_zone_manager.py
├── market-scanner/main.py
├── ai-decision-engine/main.py
├── position-management/main.py
│   └── Redis DB 3
└── risk-engine/main.py
```

### Critical Functions by File

**start_integrated_fibonacci.py**:
- main(): Orchestrates everything
- start_service(): Launches services via uvicorn
- verify_integration(): Validates Fibonacci modules
- monitor_system(): Live position tracking

**adaptive_fibonacci_averaging.py**:
- __init__(num_steps): Configure steps (3-7)
- calculate_adaptive_config(): Generate full config
- optimize_k_coefficient(): Find best multiplier

**fibonacci_delta_calculator.py**:
- calculate_dynamic_thresholds(): Main calculation
- _analyze_market_regime(): Market state detection
- _generate_fibonacci_thresholds(): Apply Fibonacci levels

**API Gateway (main.py)**:
- startup_event(): Initialize all components
- process_trading_signal(): Handle incoming signals
- get_positions(): Retrieve current positions

**Position Management (main.py)**:
- create_position(): Open new position
- apply_zone_strategy(): Zone-based logic
- update_position(): Modify existing

### System Commands

Start system:
```bash
python3 /root/ai_xyz/start_integrated_fibonacci.py
```

Check status:
```bash
./status.sh
```

View logs:
```bash
tail -f /root/ai_xyz/integrated_system.log
```

### Known Issues & Solutions

1. **Services not starting**: Check ports 9000-9009 availability
2. **Bitget connection errors**: API rate limits, wait and retry
3. **Redis connection**: Ensure Redis is running on port 6379
4. **Module import errors**: Check PYTHONPATH includes /root/ai_xyz

### Documentation URLs

- System Flow Analysis: https://moondox.eu/reports/ai-xyz-system-flow.html
- Reports Index: https://moondox.eu/reports/
- AI-XYZ Dashboard: https://moondox.eu/ai-xyz/

---
Generated: 2025-09-16
This document serves as permanent memory for understanding the AI-XYZ system architecture.