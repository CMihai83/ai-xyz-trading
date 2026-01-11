# AI-XYZ Trading System Documentation

## System Overview

The AI-XYZ Trading System is a sophisticated automated trading platform for Bitget exchange that implements advanced position management strategies including Fibonacci-based averaging, surplus dumping, and dynamic risk management.

## Core Components

### 1. Main Trading Engine
**File**: `aixyz_continuous_profit_system.py`
**Purpose**: Core trading logic and position management
**Features**:
- Market scanning and opportunity detection
- Position lifecycle management
- Zone-based trading (Neutral, Averaging, Surplus Dump, Profit Taking, Stop Loss)
- Portfolio direction balancing
- Position persistence with Redis

### 2. Adaptive Fibonacci Averaging System
**Files**: 
- `core/adaptive_fibonacci_averaging.py` - Main averaging logic
- `core/zone_state_machine.py` - Delta calculation
- `core/averaging_engine.py` - Execution engine

**SYSTEM LOGIC FLOW**:

#### Step 1: Maximum Delta Calculation
- **Module**: `zone_state_machine._calculate_dynamic_delta()`
- **Purpose**: Calculate maximum expected price deviation
- **Method**: 
  - Analyzes 7 days of historical price data
  - Calculates 95th percentile of 24h price swings
  - Adds 30% safety margin for extreme events
  - Returns absolute price delta (e.g., $100 for 30% of $333 entry)

#### Step 2: Fibonacci Distribution & Optimization
- **Module**: `adaptive_fibonacci_averaging.calculate_position_averaging_config()`
- **Receives**: Maximum delta from Step 1
- **Performs**:
  1. **Backtests** 3-7 averaging steps to find optimal count
  2. **Optimizes leverage** (tests 3x-10x) if not specified
  3. **Calculates K coefficient** for position sizing
  4. **Distributes steps** over delta using Fibonacci ratios

#### Fibonacci Step Distribution
- **Sequence Generation** (for n steps):
  - 3 steps: [8, 5, 3] = [F(6), F(5), F(4)]
  - 5 steps: [21, 13, 8, 5, 3] = [F(8), F(7), F(6), F(5), F(4)]
  - Always ends with 3, never 2 or 1

- **Delta Distribution**:
  - Each step gets: Fibonacci_number / Sum_of_all_numbers
  - Example for 5 steps: 21/50, 13/50, 8/50, 5/50, 3/50
  - Cumulative: 42%, 68%, 84%, 94%, 100% of max delta

- **Position Multipliers**:
  - Based on Fibonacci with K coefficient
  - Automatically adjusted for safety and margin limits

**Key Principle**: The system calculates ONE maximum delta based on historical data, then optimally distributes averaging steps across that delta range using backtesting and Fibonacci ratios.
- Stores configurations per position
- Falls back to original logic if unsafe

### 3. Market Scanner Services

#### Advanced Opportunity Engine
**File**: `advanced_opportunity_engine.py`
**Features**:
- Multi-timeframe analysis (5m, 15m, 1h, 4h, 1d)
- Elliott Wave analysis
- ML-based scoring
- Fibonacci retracement levels
- Calendar effect analysis

#### Volatile Coins Service
**File**: `bitget_volatile_coins_service.py`
**Purpose**: Identifies top volatile coins for trading
**Features**:
- Real-time volatility tracking
- Top 20 volatile coins caching
- 5-minute update cycle

### 4. Supporting Services

#### Portfolio Balancer
**File**: `portfolio_balancer.py`
**Purpose**: Maintains balanced long/short positions

#### Position Persistence Manager
**File**: `position_persistence_manager.py`
**Purpose**: Saves/loads position state from Redis

## System Architecture

```
┌─────────────────────────────────────────┐
│          AI-XYZ Trading System          │
└─────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
┌───────▼─────────┐    ┌───────▼─────────┐
│ Market Scanner  │    │ Fibonacci Service│
│    Services     │    │  (Pre-calculates)│
└────────┬────────┘    └────────┬────────┘
         │                      │
         └──────────┬───────────┘
                    │
            ┌───────▼─────────┐
            │  Main Trading   │
            │     Engine      │
            └───────┬─────────┘
                    │
         ┌──────────┴──────────┐
         │                     │
    ┌────▼────┐          ┌────▼────┐
    │ Bitget  │          │  Redis  │
    │Exchange │          │Storage  │
    └─────────┘          └─────────┘
```

## Trading Parameters

### Position Management
- **Minimum Position Size**: $6.50 after leverage (fixed requirement)
- **Maximum Positions**: Dynamic based on capital/25
- **Leverage**: Dynamically calculated to avoid liquidation
- **Maximum Averaging Steps**: Dynamically calculated based on available capital

### Capital Allocation (Per Position - Max $25)
- **70% for Position + Averaging**: 
  - Initial position: $6.50 after leverage
  - Remaining used for averaging steps with Fibonacci multipliers
  - Last step uses ALL remaining margin from this 70%
- **30% Safety Margin**: 
  - Reserved ONLY for the last averaging step
  - NOT added to initial position
  - Provides liquidation protection

### Zone Thresholds
- **Averaging Zone**: UPNL ≤ -1% (starts immediately)
- **Surplus Dump Zone**: UPNL ≥ +15% after averaging
- **Profit Taking**: UPNL ≥ +15% without averaging
- **Stop Loss**: -90% UPNL

### Dual Fibonacci Configuration

#### Price Levels (Distance from Entry)
- **Sequence**: [3, 5, 8, 13, 21, 34, 55, 89...] REVERSED for use
- **Examples**:
  - 3 steps: [8%, 5%, 3%] from entry
  - 5 steps: [21%, 13%, 8%, 5%, 3%] from entry
- **Logic**: Wider gaps early, tighter as position worsens

#### Position Size Multipliers  
- **Sequence**: [1, 1, 2, 3, 5, 8, 13...]
- **Features**:
  - Two conservative 1x additions first
  - Then follows Fibonacci progression
  - Last step uses remaining margin (might be 4.5x instead of 5x)

## Practical Example

### Position with $25 Allocation, 15x Leverage
1. **Capital Split**:
   - 70% = $17.50 for position + averaging
   - 30% = $7.50 safety margin (last step only)

2. **Initial Position**:
   - Size: $6.50 (after 15x leverage)
   - Base margin: $0.43

3. **Averaging Steps** (if capital allows 5 steps):
   - **Price Levels**: [21%, 13%, 8%, 5%, 3%] from entry
   - **Size Multipliers**: [1x, 1x, 2x, 3x, remaining]
   - Step 1: Add 1x ($0.43) at 21% away
   - Step 2: Add 1x ($0.43) at 13% away  
   - Step 3: Add 2x ($0.86) at 8% away
   - Step 4: Add 3x ($1.29) at 5% away
   - Step 5: Add remaining (~4.5x) + safety margin at 3% away

## Starting the System

### Quick Start
```bash
cd /root/ai_xyz
./start_aixyz_system.sh
```

### Manual Start
```bash
# Start with logging
python3 aixyz_continuous_profit_system.py > aixyz_continuous_profit.log 2>&1 &

# Start in background
nohup python3 aixyz_continuous_profit_system.py &
```

### Restart
```bash
./restart_aixyz_system.sh
```

## Monitoring

### Check Status
```bash
./status.sh
```

### View Logs
```bash
# Main system logs
tail -f /tmp/aixyz_main.log

# Or if running directly
tail -f aixyz_continuous_profit.log
```

### Check Positions
```bash
python3 -c "
import ccxt
import os
from dotenv import load_dotenv
load_dotenv('/root/ai_xyz/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

positions = exchange.fetch_positions()
for p in [pos for pos in positions if pos['contracts'] > 0]:
    print(f\"{p['symbol']}: {p['side']} {p['unrealizedPnl']:.2f}\")
"
```

## Configuration Files

### Environment Variables
**File**: `.env`
```
BITGET_API_KEY=your_api_key
BITGET_API_SECRET=your_secret
BITGET_API_PASSPHRASE=your_passphrase
```

### Redis Configuration
- **Host**: localhost
- **Port**: 6379
- **DB**: 0

## Trading Flow

1. **Market Scanning**
   - Scans for opportunities using multiple strategies
   - Prioritizes top volatile coins
   - Applies multi-timeframe analysis

2. **Position Opening**
   - Calls Fibonacci service for parameters
   - Calculates optimal leverage
   - Verifies liquidation safety
   - Opens position with calculated size

3. **Position Management**
   - Monitors UPNL continuously
   - Applies zone-based logic
   - Executes averaging at Fibonacci thresholds
   - Implements surplus dump when profitable

4. **Risk Management**
   - Portfolio direction balancing
   - Maximum position limits
   - Stop loss protection
   - Liquidation prevention

## API Endpoints

The system doesn't expose HTTP APIs but uses internal methods:

### Main System Methods
- `scan_for_opportunities()` - Find trading opportunities
- `open_position(opportunity)` - Open new position
- `check_averaging(symbol, position, upnl)` - Check/execute averaging
- `check_surplus_dump(symbol, position, upnl)` - Check/execute surplus dump
- `get_fibonacci_parameters(symbol, direction, volatility, confidence)` - Get Fibonacci config

### Fibonacci Service Methods
- `calculate_trading_parameters()` - Main calculation method
- `optimize_leverage()` - Find optimal leverage
- `calculate_averaging_steps()` - Calculate step distributions
- `verify_liquidation_safety()` - Safety checks

## Troubleshooting

### System Won't Start
```bash
# Check for existing processes
ps aux | grep aixyz

# Kill stuck processes
pkill -f aixyz_continuous_profit_system.py

# Check logs
tail -100 /tmp/aixyz_main.log
```

### Position Not Averaging
- Check zone thresholds in logs
- Verify Fibonacci calculations
- Check available margin
- Review averaging step limits

### Redis Connection Issues
```bash
# Check Redis status
redis-cli ping

# Start Redis if needed
redis-server --daemonize yes
```

## Performance Metrics

### System Requirements
- **Memory**: ~250MB Python process
- **CPU**: <5% average usage
- **Network**: Minimal (API calls only)
- **Storage**: <100MB logs

### Trading Performance
- **Average Response Time**: <1s for opportunities
- **Position Check Frequency**: Every 5 seconds
- **Market Scan Frequency**: Every 30 seconds
- **Averaging Calculation**: <100ms

## Version History

### Current Version: 2.0
- Integrated Fibonacci Averaging Service
- Pre-calculated liquidation safety
- Advanced position multipliers
- Backtesting support

### Previous: 1.0
- Basic averaging with fixed thresholds
- Simple leverage calculation
- Manual position management

## Support Files

- `test_fibonacci_integration.py` - Test Fibonacci integration
- `fibonacci_results_storage.py` - Store Fibonacci results
- `generate_fibonacci_report.py` - Generate reports
- `FIBONACCI_INTEGRATION_SUMMARY.md` - Integration details

## Maintenance

### Daily Tasks
- Monitor positions and P&L
- Check log files for errors
- Verify averaging execution

### Weekly Tasks
- Review trading performance
- Adjust parameters if needed
- Clean old log files

### Updates
- Always test in sandbox first
- Backup configuration before changes
- Use restart script for updates

## Contact & Support

For issues or questions about the AI-XYZ Trading System, refer to:
- System logs in `/tmp/aixyz_main.log`
- Fibonacci service logs in the main log
- Position state in Redis

---
*Last Updated: September 2025*
*Version: 2.0 with Fibonacci Integration*