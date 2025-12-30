# AI-XYZ Trading System Logic Documentation

## System Overview
The AI-XYZ system is an adaptive, multi-timeframe trading system that automatically adjusts to market volatility through dynamic delta calculation, k-coefficient optimization, and Fibonacci-based position averaging.

## Core Components and Logic Flow

### 1. DELTA CALCULATION (Adaptive Timeframe Expansion)

**Service:** `AdaptiveTimeframeDeltaService`

#### Logic Flow:
1. **New Position**: Starts with 1-minute timeframe (smallest delta ~2-5%)
2. **Price Monitoring**: Tracks `price_movement = abs(current_price - entry_price) / entry_price`
3. **Expansion Trigger**: When `price_movement > current_delta * 0.8`
4. **Timeframe Switch**: Moves to next larger timeframe (1m → 5m → 15m → 1h → 4h → 1d)
5. **No Artificial Caps**: Deltas can range from 2% to 100%+ based on actual volatility

#### Candle Counts (Responsive):
- **1m**: 50 candles (~50 minutes) - very recent volatility
- **5m**: 100 candles (~8 hours) - recent day
- **15m**: 200 candles (~2 days) - short term
- **1h**: 300 candles (~12 days) - medium term
- **4h**: 400 candles (~66 days) - longer term
- **1d**: 365 candles (1 year) - historical

#### Delta Formula:
```
base_delta = 95th_percentile(price_ranges)
volatility_multiplier = min(2.0, recent_volatility / avg_volatility)
final_delta = base_delta × volatility_multiplier × 1.3 (30% safety buffer)
```

### 2. K-COEFFICIENT OPTIMIZATION

**Function:** `calculate_position_averaging_config()`

#### What is K-Coefficient?
The k-coefficient is a multiplier that scales position sizes at each averaging step:
- **k=0.1**: Very conservative (for extreme volatility like BTR with 100%+ daily moves)
- **k=0.5**: Moderate (for medium volatility)
- **k=1.0**: Standard (for stable assets)
- **k>1.0**: Aggressive (for very stable assets)

#### Optimization Process:
1. Tests k values from 0.1 to 3.0 in 0.05 increments
2. For each k, simulates all averaging steps
3. Checks liquidation safety at each step
4. Selects k that maximizes steps while maintaining safety

#### Position Sizing Formula:
```
step_margin = initial_margin × fibonacci_multiplier × k_coefficient
```

Example with k=0.1:
- Fibonacci multipliers: [8, 5, 3, 2, 1]
- Actual multipliers: [0.8, 0.5, 0.3, 0.2, 0.1]

### 3. AVERAGING LOGIC

#### Fibonacci Distribution:
The system uses Fibonacci numbers to distribute averaging steps across the delta range:
- **Weights**: [89, 55, 34, 21, 13, 8, 5, 3] for 8 steps
- **Cumulative Thresholds**: [39%, 63%, 78%, 87%, 93%, 96%, 98%, 100%]

#### Averaging Trigger Conditions:
1. **UPNL Check**: `current_upnl_pct <= threshold_pct`
2. **Step Available**: `current_step < max_steps`
3. **Margin Available**: `used_margin < allocated_margin`
4. **Safety Check**: Position remains safe from liquidation after averaging

#### Emergency Averaging:
- At -85% UPNL, system forces averaging regardless of thresholds
- If averaging fails at -85%, emergency close to prevent liquidation

### 4. SURPLUS DUMP LOGIC

**When Triggered**: Position recovers from negative to positive after averaging

#### Process:
1. **Peak Tracking**: Records highest UPNL achieved
2. **First Dump** (85% of peak): Sells 50% of surplus
3. **Second Dump** (50% of peak): Sells remaining 50%
4. **Reset**: Returns to neutral zone after complete dump

#### Surplus Calculation:
```
surplus_size = total_position_size - initial_position_size
surplus_value = surplus_size × current_price
```

### 5. TAKE PROFIT LOGIC

**Minimum Threshold**: $0.10 profit (updated January 2025)

#### Conditions:
1. No averaging steps taken (position in profit from start)
2. UPNL > $0.10
3. Position in Neutral zone

#### Formula:
```
if upnl > 0.10 and averaging_steps == 0:
    close_position()
```

### 6. STOP LOSS LOGIC

**Trigger**: -85% to -90% UPNL (near liquidation)

#### Emergency Actions:
1. **First**: Attempt emergency averaging
2. **If Fails**: Close position immediately
3. **Liquidation Prevention**: Always acts before -90% UPNL

### 7. POSITION LIFECYCLE

```
NEW POSITION
    ↓
[NEUTRAL ZONE] ← Entry point
    ↓
Price moves against position
    ↓
[AVERAGING ZONE] ← Multiple steps with k-coefficient
    ↓
Position recovers
    ↓
[SURPLUS DUMP ZONE] ← Gradual profit taking
    ↓
Return to [NEUTRAL ZONE]
    ↓
CLOSE POSITION
```

## Safety Mechanisms

### 1. Delta Safety Check:
```python
is_safe = (delta_pct * leverage) < 0.75  # Keep last step before -75% UPNL
```

### 2. Liquidation Distance Check:
```python
distance_to_liquidation = (trigger_price - liquidation_price) / trigger_price
is_safe = distance_to_liquidation > 0.10  # Minimum 10% buffer
```

### 3. Margin Allocation:
- Initial position: 10% of allocated margin
- Averaging steps: Distributed by Fibonacci × k-coefficient
- Safety reserve: 30% added to last step

## Configuration Parameters

### Dynamic (Calculated):
- Delta: Based on market volatility
- K-coefficient: Based on asset volatility
- Leverage: Optimized 3x-10x
- Step count: Optimized 3-7 steps

### Fixed:
- Max margin per position: $25
- Minimum position value: $6.50
- Take profit minimum: $0.10
- Emergency close: -85% UPNL
- Delta expansion trigger: 80% of current delta

## System States

1. **SCANNING**: Looking for opportunities
2. **OPENING**: Placing initial position
3. **MONITORING**: Tracking position performance
4. **AVERAGING**: Executing DCA steps
5. **RECOVERING**: Position moving back to profit
6. **DUMPING**: Taking profits gradually
7. **CLOSING**: Exiting position

## Critical Rules

1. **Never exceed allocated margin** ($25 per position)
2. **Always maintain liquidation buffer** (10% minimum)
3. **Start with smallest timeframe** for new positions
4. **Expand timeframes progressively** as volatility increases
5. **Apply k-coefficient** to all averaging calculations
6. **Force emergency action** at -85% UPNL
7. **Track surplus separately** for dump management
8. **No artificial delta caps** - let market determine range

## Monitoring Points

- Delta changes and timeframe switches
- K-coefficient calculations
- Averaging step executions
- Surplus dump triggers
- Emergency close events
- Margin usage vs allocation

## Version History

- **2025-09-14**: Added adaptive timeframe expansion
- **2025-09-14**: Integrated k-coefficient optimization
- **2025-09-14**: Removed delta capping
- **2025-09-14**: Added responsive candle counts
- **2025-09-14**: Documented complete system logic