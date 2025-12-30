# Adaptive Fibonacci Averaging System

## Overview

The Adaptive Fibonacci Averaging System is a sophisticated position management strategy that uses Fibonacci numbers to determine optimal entry points and position sizes for dollar-cost averaging (DCA) in trading. This system is designed to maximize capital efficiency while maintaining strict risk management.

## Key Concepts

### 1. Fibonacci Sequence Generation

**CRITICAL RULE:** The last Fibonacci number in any sequence is ALWAYS 3 (F(4)), never 2 or 1.

For n averaging steps, the system uses n consecutive Fibonacci numbers from F(n+3) down to F(4):

| Steps | Fibonacci Sequence | Formula |
|-------|-------------------|---------|
| 3 | [8, 5, 3] | [F(6), F(5), F(4)] |
| 4 | [13, 8, 5, 3] | [F(7), F(6), F(5), F(4)] |
| 5 | [21, 13, 8, 5, 3] | [F(8), F(7), F(6), F(5), F(4)] |
| 6 | [34, 21, 13, 8, 5, 3] | [F(9), F(8), F(7), F(6), F(5), F(4)] |
| 7 | [55, 34, 21, 13, 8, 5, 3] | [F(10), F(9), F(8), F(7), F(6), F(5), F(4)] |

### 2. Delta Threshold Calculation

Each averaging step has a delta threshold that determines when to trigger that step. The threshold is calculated as:

```
Step Threshold = Fibonacci_Number / Sum_of_All_Fibonacci_Numbers
```

**Example for 5 steps [21, 13, 8, 5, 3]:**
- Sum = 21 + 13 + 8 + 5 + 3 = 50
- Step 1: 21/50 = 0.42 (42% of max delta)
- Step 2: 13/50 = 0.26 (26% of max delta)
- Step 3: 8/50 = 0.16 (16% of max delta)
- Step 4: 5/50 = 0.10 (10% of max delta)
- Step 5: 3/50 = 0.06 (6% of max delta)

### 3. Trigger Price Calculation

**IMPORTANT:** Trigger prices use CUMULATIVE thresholds, not individual thresholds.

```
Cumulative Threshold = Sum of all thresholds up to and including current step
Trigger Price (Long) = Entry Price - (Max Delta × Cumulative Threshold)
Trigger Price (Short) = Entry Price + (Max Delta × Cumulative Threshold)
```

**Example for Entry = $10,000, Max Delta = $1,000 (Long Position):**

| Step | Individual | Cumulative | Trigger Price |
|------|------------|------------|---------------|
| 1 | 42% | 42% | $9,580 |
| 2 | 26% | 68% | $9,320 |
| 3 | 16% | 84% | $9,160 |
| 4 | 10% | 94% | $9,060 |
| 5 | 6% | 100% | $9,000 |

### 4. Position Sizing with K Coefficient

The K coefficient is a multiplier that determines position size at each averaging step:

```
Step Position Size = Initial Margin × Fibonacci_Weight × K_Coefficient
```

- **K < 1.0**: Conservative sizing, allows more averaging steps
- **K = 1.0**: Standard sizing based on pure Fibonacci weights
- **K > 1.0**: Aggressive sizing, fewer but larger averaging steps

The system automatically optimizes K to maximize the number of safe averaging steps while maintaining a minimum 10% distance from liquidation.

### 5. Backtesting for Optimal Steps

The system can backtest different step counts (3-7) to find the optimal configuration based on:

1. **Number of Safe Steps** (40% weight): More steps = better
2. **K Coefficient** (20% weight): Lower K = more conservative = better
3. **Safety Distance** (30% weight): Distance from liquidation
4. **Margin Efficiency** (10% weight): How well margin is utilized

## Usage Example

```python
from core.adaptive_fibonacci_averaging import AdaptiveFibonacciCalculator

# Initialize calculator
calculator = AdaptiveFibonacciCalculator(num_steps=5)

# Define position parameters
position_data = {
    'entry_price': 10000,      # Entry price
    'leverage': 7,              # Leverage multiplier
    'initial_margin': 1.0,      # Initial margin in USD
    'total_margin': 25.0,       # Total available margin
    'max_delta': 1000,          # Maximum price movement to cover
    'direction': 'long'         # 'long' or 'short'
}

# Calculate optimal configuration
config = calculator.calculate_adaptive_config(position_data)

# Or backtest to find optimal number of steps
optimal_steps, best_config, results = calculator.backtest_optimal_steps(
    position_data,
    min_steps=3,
    max_steps=7
)
```

## Configuration Output

The system provides:

1. **K Coefficient**: Optimal multiplier for position sizing
2. **Averaging Steps**: List of trigger prices and sizes for each step
3. **Safety Metrics**: Distance from liquidation at each step
4. **Margin Requirements**: Total margin needed for all steps
5. **Final Average Entry**: Weighted average entry if all steps execute

## Safety Features

1. **Minimum 10% Distance from Liquidation**: Every averaging step maintains at least 10% distance
2. **Margin Limits**: Stops adding steps if margin would be exceeded
3. **Safety Reserve**: 30% of total margin kept as reserve
4. **Automatic K Optimization**: Finds safest K value that maximizes steps

## Integration with Trading System

The averaging configuration integrates with:

1. **Position Manager**: Tracks current averaging step and triggers
2. **Risk Manager**: Monitors safety distances and margin usage
3. **Order Executor**: Places orders when trigger prices are hit
4. **Zone State Machine**: Transitions between Neutral, Averaging, and Surplus Dump zones

## Important Notes

1. **Excel Compatibility**: The 5-step configuration matches the provided Excel example exactly
2. **Production Ready**: Thoroughly tested with backtesting capabilities
3. **Dynamic Adaptation**: Can adjust to different market conditions and position sizes
4. **Risk-First Design**: Prioritizes capital preservation over aggressive averaging

## Mathematical Foundation

The system is based on the mathematical principle that Fibonacci ratios provide optimal distribution of capital across averaging steps:

1. **Larger early steps** (21, 13) capture significant moves quickly
2. **Smaller later steps** (5, 3) provide safety net for extreme moves
3. **Cumulative approach** ensures smooth position building
4. **Always ending with 3** provides consistent final safety step

## Troubleshooting

If trigger prices don't match expectations:

1. Verify you're using CUMULATIVE thresholds, not individual
2. Check that Fibonacci sequence ends with 3
3. Ensure max_delta is calculated correctly
4. Verify K coefficient is within reasonable range (0.1 - 3.0)

## References

- Excel Example: `/root/ai_xyz/example of averaging =.xlsx`
- Test Suite: `/root/ai_xyz/test_fibonacci_complete.py`
- Main Module: `/root/ai_xyz/core/adaptive_fibonacci_averaging.py`