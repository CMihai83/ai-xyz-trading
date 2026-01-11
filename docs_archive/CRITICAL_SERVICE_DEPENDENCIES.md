# 🚨 CRITICAL AI-XYZ SERVICE DEPENDENCIES 🚨
## DO NOT MODIFY OR STOP SERVICES WITHOUT UNDERSTANDING THESE DEPENDENCIES

Last Updated: 2025-09-23 21:38

## ⚠️ IMPORTANT: ALL SERVICES ARE INTERDEPENDENT
**NEVER run or modify one service without ensuring ALL dependent services are running**

## Complete Service List & Dependencies

### 1. **autonomous_sync.py** 
   - **Purpose**: Core position management, averaging logic, zone transitions
   - **Depends on**: 
     - momentum_guardian.py (for averaging permission)
     - surplus_dump_manager.py (for profit taking)
     - Position Management Service (port 8002)
     - Risk Engine (port 8001)
   - **Modified files affect**: ALL trading operations
   - **Status**: RUNNING (PIDs: 1277091, 1278099)

### 2. **momentum_guardian.py**
   - **Purpose**: Controls averaging permission based on momentum indicators
   - **Depends on**: position_state.json
   - **Used by**: autonomous_sync.py for averaging decisions
   - **Status**: RUNNING (PID: 1247769)

### 3. **surplus_dump_manager.py**
   - **Purpose**: Manages profit taking at 85%/50% of peak UPNL
   - **Depends on**: position_state.json
   - **Used by**: autonomous_sync.py for surplus dump execution
   - **Status**: RUNNING (PID: 1248777)

### 4. **aixyz_continuous_profit_system.py** (Main Trading Engine)
   - **Purpose**: Main trading orchestrator
   - **Depends on**: ALL services below
   - **Coordinates**: All position management and trading decisions
   - **Status**: RUNNING (PID: 1311880)

### 5. **Risk Engine** (Port 8001)
   - **Purpose**: Risk assessment and position limits
   - **Used by**: autonomous_sync.py, Main Trading Engine
   - **API**: http://localhost:8001
   - **Status**: RUNNING (PID: 1311924)

### 6. **Position Management** (Port 8002)
   - **Purpose**: Central position registry and management
   - **Used by**: ALL trading services
   - **API**: http://localhost:8002
   - **Status**: RUNNING (PID: 1311955)

### 7. **Market Scanner** (Port 8003)
   - **Purpose**: Scans markets for opportunities
   - **Feeds**: Main Trading Engine, advanced_opportunity_engine.py
   - **API**: http://localhost:8003
   - **Status**: RUNNING (PID: 1311975)

### 8. **Data Pipeline** (Port 8004)
   - **Purpose**: Real-time and historical data management
   - **Used by**: ALL services for market data
   - **API**: http://localhost:8004
   - **Status**: RUNNING (PID: 1312007)

### 9. **ML Framework** (Port 8005)
   - **Purpose**: AI/ML model serving for predictions
   - **Used by**: Main Trading Engine, Risk Engine
   - **API**: http://localhost:8005
   - **Status**: RUNNING (PID: 1312032)

### 10. **Monitoring Service** (Port 8006)
   - **Purpose**: System health and performance monitoring
   - **Monitors**: ALL services
   - **API**: http://localhost:8006
   - **Status**: RUNNING (PID: 1312063)

### 11. **Notification Service** (Port 8007)
   - **Purpose**: Alerts and notifications
   - **Triggered by**: Risk events, trade executions
   - **API**: http://localhost:8007
   - **Status**: RUNNING (PID: 1312085)

### 12. **fibonacci_averaging_service.py**
   - **Purpose**: Fibonacci-based averaging calculations
   - **Used by**: autonomous_sync.py for threshold calculations
   - **Location**: /root/ai_xyz/services/api-gateway/src/
   - **Status**: Should be running but failed to start

### 13. **balance_manager.py**
   - **Purpose**: Balance and capital management
   - **Used by**: autonomous_sync.py for capital limits
   - **Status**: RUNNING (PID: 1312103)

### 14. **enhanced_market_scanner.py**
   - **Purpose**: Advanced market scanning with technical analysis
   - **Feeds**: Market Scanner API (port 8003)
   - **Status**: Check if running

### 15. **advanced_opportunity_engine.py**
   - **Purpose**: Opportunity filtering and scoring
   - **Depends on**: Market Scanner output
   - **Status**: Check if running

## 🔴 CRITICAL RULES

1. **NEVER modify autonomous_sync.py without ensuring ALL services are running**
   - It depends on: momentum_guardian, surplus_dump_manager, Risk Engine, Position Management

2. **NEVER stop the Main Trading Engine without stopping dependent services first**
   - Stop order: Trading services → API services → Main Engine

3. **NEVER modify position_state.json structure without updating ALL readers**
   - Used by: autonomous_sync, momentum_guardian, surplus_dump_manager, main engine

4. **ALWAYS check service health after modifications**
   ```bash
   curl http://localhost:8001/health  # Risk Engine
   curl http://localhost:8002/health  # Position Management
   curl http://localhost:8003/health  # Market Scanner
   ```

5. **ALWAYS use START_FULL_SYSTEM.sh to start all services**
   ```bash
   cd /root/ai_xyz
   ./START_FULL_SYSTEM.sh
   ```

6. **ALWAYS use STOP_FULL_SYSTEM.sh to stop all services**
   ```bash
   cd /root/ai_xyz
   ./STOP_FULL_SYSTEM.sh
   ```

## 📊 Service Integration Map

```
aixyz_continuous_profit_system.py (Main Engine)
    ├── autonomous_sync.py
    │   ├── momentum_guardian.py
    │   ├── surplus_dump_manager.py
    │   ├── Risk Engine (8001)
    │   └── Position Management (8002)
    ├── Market Scanner (8003)
    │   └── enhanced_market_scanner.py
    ├── Data Pipeline (8004)
    ├── ML Framework (8005)
    ├── advanced_opportunity_engine.py
    ├── balance_manager.py
    └── fibonacci_averaging_service.py
```

## ⚠️ WARNING
Modifying ANY service without understanding these dependencies can break:
- Position averaging logic
- Surplus dump execution
- Risk management
- Capital allocation
- Market scanning
- Trade execution

## Recovery Commands
If services are not running:
```bash
# Start all services
cd /root/ai_xyz
./START_FULL_SYSTEM.sh

# Check status
./STATUS.sh

# Stop all services
./STOP_FULL_SYSTEM.sh
```

## Modified During Session
- autonomous_sync.py: Fixed entry_price bug (lines 210, 334)
- No other core files were modified