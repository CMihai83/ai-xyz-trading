# Dynamic Position & Averaging Steps Management

## Core Principle
The system dynamically calculates the maximum number of positions and averaging steps based on available capital to ensure EVERY position has sufficient margin for ALL averaging steps.

## The Problem We Solved
Previously, the system would open up to 10 positions with insufficient capital to perform averaging, leading to:
- Positions hitting stop loss without averaging opportunity
- Failed averaging attempts due to "insufficient balance"
- Ineffective use of the Fibonacci averaging strategy

## Dynamic Calculation Logic

### 1. Position Sizing
```
Base Position Size: $10.83 (after leverage)
Leverage: 9x
Margin per Position: $10.83 / 9 = $1.20
```

### 2. Averaging Capital Requirements
Using Fibonacci multipliers: 1x, 2x, 3x, 5x, 8x
```
Total capital needed per position:
- Original position: 1x margin ($1.20)
- Averaging steps: 19x margin ($22.80)
- TOTAL: 20x margin ($24.00) per position
```

### 3. Dynamic Position Limit Calculation

#### For NEW Positions:
```python
# Reserve full averaging capital for existing positions
existing_reserve = existing_positions * remaining_averaging_capital

# Calculate available for new positions
available = free_capital - existing_reserve

# Maximum new positions with FULL averaging capability
max_new = available / (margin_per_position * 20)
```

#### Account Size Limits:
- **Small accounts (<$20)**: Max 2 positions
- **Medium accounts (<$50)**: Max 3 positions
- **Larger accounts (>$50)**: Max 4 positions

### 4. Dynamic Averaging Steps
The system ensures minimum 3 averaging steps by:
1. Calculating available capital after position opening
2. Determining how many Fibonacci steps can be executed
3. If less than 3 steps possible, position is NOT opened

## Implementation Example

### Scenario 1: Small Account ($10 balance)
```
Free Capital: $8.50
Position 1 margin: $1.20
Averaging reserve needed: $22.80
Total needed: $24.00

Result: Can't open position (insufficient for averaging)
System Action: Wait for capital or close existing positions
```

### Scenario 2: Medium Account ($30 balance)
```
Free Capital: $28.00
Position 1: $1.20 margin + $22.80 reserve = $24.00
Remaining: $4.00

Result: Can open 1 position with full averaging
Max Positions: 1
```

### Scenario 3: With Existing Positions
```
Account Balance: $50
Existing Positions: 2 (using $2.40 margin)
Free Capital: $47.60
Reserve for existing: 2 * $22.80 = $45.60
Available for new: $2.00

Result: Cannot open new positions
Action: Focus on managing existing positions
```

## Key Safety Features

### 1. Pre-Opening Validation
Before opening ANY position, system checks:
- Total capital available
- Existing position averaging needs
- Remaining capital for new position + averaging

### 2. Real-Time Recalculation
Every 30 seconds during scanning:
- Recalculate position limits
- Adjust for changed balances
- Account for completed averaging steps

### 3. Conservative Approach
- Never exceed calculated limits
- Always reserve FULL averaging capital
- Prefer fewer positions with proper averaging over many without

## Benefits of This Approach

1. **100% Averaging Success Rate**: Every position has guaranteed capital for all 5 averaging steps
2. **Reduced Stop Losses**: Positions can average down through drawdowns
3. **Better Capital Efficiency**: No wasted margin on positions that can't be managed
4. **Risk Management**: Limited exposure with proper position sizing

## Configuration Constants

```python
# Position Parameters
BASE_POSITION_SIZE = 10.83  # USD after leverage
LEVERAGE = 9
MARGIN_PER_POSITION = BASE_POSITION_SIZE / LEVERAGE  # ~$1.20

# Fibonacci Averaging
FIBONACCI_MULTIPLIERS = [1, 2, 3, 5, 8]  # Total: 19x
TOTAL_MARGIN_MULTIPLIER = 20  # Original + averaging = 20x

# Account Limits
SMALL_ACCOUNT_LIMIT = 20  # USD
MEDIUM_ACCOUNT_LIMIT = 50  # USD
MAX_POSITIONS_SMALL = 2
MAX_POSITIONS_MEDIUM = 3
MAX_POSITIONS_LARGE = 4
```

## System Behavior by Account Size

### $10 Account
- Max positions: 0-1 (only if no averaging needed)
- Focus: Capital preservation
- Strategy: Wait for opportunities after closing positions

### $20 Account
- Max positions: 1-2
- Each position: $1.20 margin + $22.80 reserve
- Total commitment: $24-48

### $50 Account
- Max positions: 2-3
- Flexible averaging capability
- Can weather significant drawdowns

### $100+ Account
- Max positions: 3-4
- Full Fibonacci averaging for all positions
- Optimal risk/reward balance

## Critical Rules

1. **NEVER** open a position without full averaging reserve
2. **ALWAYS** recalculate limits before scanning
3. **PRIORITY** goes to existing position management over new openings
4. **MINIMUM** 3 averaging steps must be possible or position is rejected

## Monitoring & Alerts

System logs when:
- Position limit changes
- Insufficient capital for averaging
- New position rejected due to capital constraints
- Averaging step executed successfully

## Example Log Output
```
📊 Dynamic position limit: 2 (was 10)
   Free capital: $28.50
   Reserved for averaging: $45.60
   Available for new: $-17.10
⚠️ No capital for new positions (need $45.60 for averaging)
```

---

*This logic ensures sustainable trading with proper risk management*