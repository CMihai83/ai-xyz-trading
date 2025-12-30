# Delta Calculation System Documentation

## Overview

The AI-XYZ trading system uses a unified adaptive delta calculation service: **AdaptiveTimeframeDeltaService**. This service provides multi-timeframe delta analysis with automatic expansion from smallest to largest timeframes as market volatility increases.

## Core Concept: Adaptive Timeframe Expansion

The system implements a **progressive expansion strategy**:
1. **Starts Small**: New positions begin with 1m timeframe (tightest delta ~2-5%)
2. **Monitors Movement**: Tracks price movement relative to current delta
3. **Expands When Needed**: When price moves beyond 80% of current delta, switches to next larger timeframe
4. **No Artificial Caps**: Deltas can range from 2% (1m) to 100%+ (1d) based on actual volatility

## Primary Service: AdaptiveTimeframeDeltaService

**Location:** `/root/ai_xyz/core/adaptive_timeframe_delta.py`

### Key Features:

1. **Multi-Timeframe Analysis with Responsive Candle Counts**
   - **1m**: 50 candles (~50 minutes) - captures very recent volatility
   - **5m**: 100 candles (~8 hours) - recent day movements  
   - **15m**: 200 candles (~2 days) - short-term trends
   - **1h**: 300 candles (~12 days) - medium-term patterns
   - **4h**: 400 candles (~66 days) - longer-term volatility
   - **1d**: 365 candles (1 year) - historical perspective
   - Uses 95th percentile of price ranges for safety
   - Applies volatility-based scaling (up to 2x multiplier)
   - Adds 30% safety buffer to final delta

2. **Safety Mechanism**
   - Checks if delta keeps last averaging step before -75% UPNL
   - No delta capping - relies on timeframe selection for safety
   - Prevents positions from reaching liquidation zone (-90% to -95%)
   - Formula: `is_safe = (delta_pct * leverage) < 0.75`

3. **Adaptive Expansion Behavior**
   - **New Position**: Starts with smallest safe delta (typically 1m)
   - **Price Movement Check**: `if price_movement > current_delta * 0.8`
   - **Expansion**: Switches to next larger timeframe (1m → 5m → 15m → 1h → 4h → 1d)
   - **Position Tracking**: Maintains timeframe index per symbol
   - **Reset on Close**: Clears tracking when position is closed

## Integration Points

### 1. Main Trading System
**File:** `/root/ai_xyz/aixyz_continuous_profit_system.py`

- **Method:** `get_delta_for_position()`
- Calls AdaptiveTimeframeDeltaService for all delta calculations
- No longer uses deprecated `calculate_historical_delta()` methods
- Fallback: Returns 34% delta if service fails (ensures -85% UPNL safety at 10x leverage)

### 2. Fibonacci Averaging Service
**File:** `/root/ai_xyz/services/api-gateway/src/fibonacci_averaging_service.py`

- **Method:** `get_adaptive_delta()`
- Integrated with AdaptiveTimeframeDeltaService
- Uses service-calculated delta for Fibonacci step positioning
- Distributes averaging steps across the safe delta range

### 3. Position Management
- Delta determines averaging trigger thresholds
- Fibonacci weights distribute steps: [89, 55, 34, 21, 13, 8, 5, 3] for 8 steps
- Last step reaches ~25% of total delta
- With proper delta (34%+), last step is before -85% UPNL

## Delta Calculation Formula

```python
# For each timeframe:
1. Calculate consecutive candle ranges (high-low from previous close)
2. Take 95th percentile of ranges
3. Apply volatility multiplier (recent volatility vs average)
4. Add 30% safety buffer
5. Final delta = base_delta × volatility_multiplier × 1.3
```

## K-Coefficient Integration

The system uses **calculate_position_averaging_config()** to optimize:
1. **K-Coefficient**: Multiplier for position sizing (0.1 to 3.0)
   - Lower k = smaller positions, more conservative
   - Automatically optimized based on volatility
   - Volatile assets get k=0.1, stable assets up to k=1.0+
2. **Leverage**: Tests 3x to 10x, selects safest option
3. **Step Count**: Tests 3-7 steps, maximizes based on safety

## Safety Requirements

- **Safety Check Formula:** `(delta_pct * leverage) < 0.75`
  - Ensures last averaging step stays before -75% UPNL
  - No artificial delta capping
  - Relies on timeframe selection for safety

## Emergency Fallbacks

1. **Primary:** AdaptiveTimeframeDeltaService calculates optimal delta
2. **Secondary:** If service fails, use 34% minimum delta
3. **Emergency:** Force averaging at -85% UPNL regardless of calculations

## Deprecated Methods

The following methods are deprecated and should NOT be used:
- `calculate_historical_delta()` - Replaced by AdaptiveTimeframeDeltaService
- `calculate_historical_delta_async()` - Replaced by AdaptiveTimeframeDeltaService
- `FibonacciDeltaCalculator` - Not integrated, use AdaptiveTimeframeDeltaService

## Configuration

No hardcoded delta values. All deltas are dynamically calculated based on:
- Market conditions
- Volatility
- Safety thresholds
- Position leverage

## Usage Example

```python
# In main trading system
delta_info = self.get_delta_for_position(symbol, position_data)
delta_pct = delta_info['percentage']  # e.g., 0.34 (34%)
delta_abs = delta_info['absolute']    # e.g., $0.034 for $0.10 price
timeframe = delta_info['best_timeframe']  # e.g., '4h'

# In Fibonacci service
delta = await self.get_adaptive_delta(symbol, entry_price, leverage)
```

## Monitoring

The system logs:
- Selected timeframe and delta percentage
- Volatility multiplier applied
- Safety checks performed
- Any fallback scenarios triggered

## Critical Notes

1. **Never bypass AdaptiveTimeframeDeltaService** - It ensures position safety
2. **No manual delta overrides** - System automatically selects safe values
3. **Emergency averaging at -85%** - Hardcoded safety net if all else fails
4. **Continuous monitoring** - Service adapts to changing market conditions

---

*Last Updated: 2024-09-14*
*System Version: AI-XYZ Continuous Profit System with Unified Delta Calculation*