# Averaging System - Complete Engineering Report

**Analysis Date**: January 3, 2026
**System**: AI-XYZ Fibonacci-Based Adaptive Averaging
**Purpose**: Understand how positions grew 6x-19x through delta-based UPNL threshold averaging

---

## EXECUTIVE SUMMARY

**Averaging is triggered by UPNL percentage thresholds**, NOT price movements.
**Steps are distributed** using Fibonacci multipliers over a calculated delta based on market volatility.
**Delta determines spacing** between averaging levels, adapted to each symbol's volatility regime.

---

## HOW AVERAGING WORKS - COMPLETE FLOW

### Step 1: Delta Calculation (Dynamic per Symbol)

**Service**: `DynamicFibonacciDeltaService` (`dynamic_fibonacci_delta.py`)

**Formula**:
```
Dynamic Delta = Base Delta × Volatility Multiplier × Correlation Factor
```

**Base Deltas** (coin-specific):
```python
"BTC/USDT:USDT": 1.5%   # Stable coins - tight averaging
"DOGE/USDT:USDT": 3.0%  # Volatile coins - wide averaging
"DEFAULT": 2.0%         # Unknown coins
```

**Volatility Multiplier**:
- Calculated from multi-timeframe ATR (Average True Range)
- Weights: 1h (50%), 4h (30%), 1d (20%)
- Composite: ATR (70%) + Short-term volatility (30%)
- Regime detection: LOW/NORMAL/HIGH volatility states

**Correlation Factor**:
- BTC correlation: 0.0 to 1.0
- Higher correlation = tighter delta (moves with BTC)
- Lower correlation = wider delta (independent moves)

**Smoothing**:
- EMA: 80% previous + 20% new
- Update interval: 10 minutes
- Prevents erratic delta changes

**Safety Bounds**:
```python
Stable coins: 0.5% to 5.0%
Volatile coins: 1.0% to 10.0%
Default: 0.5% to 8.0%
```

---

### Step 2: Fibonacci Threshold Generation

**From Logs Example** (DOGE):
```
Delta: 3.21%
Max Steps: 7
Price Thresholds:
  Step 1: 1.60%   (delta × 0.5)
  Step 2: 3.21%   (delta × 1.0)
  Step 3: 2.41%   (delta × 0.75)
  Step 4: 4.81%   (delta × 1.5)
  Step 5: 6.42%   (delta × 2.0)
  Step 6: 9.63%   (delta × 3.0)
  Step 7: 16.05%  (delta × 5.0)
```

**Fibonacci Pattern** (Multipliers):
```
1, 1, 2, 3, 5, 8, 13, 21...
Applied as: 0.5, 1.0, 0.75, 1.5, 2.0, 3.0, 5.0...
```

**Purpose**:
- Earlier steps: Tight spacing (catch small reversals)
- Later steps: Wide spacing (survive deep drawdowns)
- Progressive: Each step requires deeper loss

---

### Step 3: Price Threshold → UPNL Threshold Conversion

**Critical Calculation** (Line 2542-2555):
```python
# Price change% × Leverage = UPNL% (relative to margin)

if is_long:
    # Long: price drops by threshold% = negative UPNL
    upnl_threshold_pct = -abs(price_threshold_pct × leverage)
else:
    # Short: price rises by threshold% = negative UPNL
    upnl_threshold_pct = -abs(price_threshold_pct × leverage)
```

**Example** (10x leverage):
```
Price Threshold    Leverage    UPNL Threshold
1.60%        ×     10x    =    -16.0%
3.21%        ×     10x    =    -32.1%
4.81%        ×     10x    =    -48.1%
6.42%        ×     10x    =    -64.2%
```

**This is WHY 10x leverage causes deep UPNL%**: Small price moves become large P&L moves.

---

### Step 4: Safety Caps (Prevent Over-Averaging)

**Hard Caps by Step** (Lines 2557-2571):
```python
Step 5 (index 4): Cap at -60% UPNL
Step 6 (index 5): Cap at -70% UPNL
Step 7+ (index 6+): Cap at -80% UPNL
Steps 1-4: No cap (use calculated threshold)
```

**Emergency Override** (Line 2618-2635):
```python
If UPNL ≤ -85% and step < 3:
    Force averaging at: -23%, -47%, -70%
    Override all Fibonacci calculations
    Purpose: Prevent liquidation (occurs at -90% to -95%)
```

---

### Step 5: Dual-Gate Trigger System

**Gate 1: P&L Threshold** (Line 2646):
```python
averaging_pnl_threshold = -25.0  # Must be ≤ -25% P&L
```

**Gate 2: Fibonacci UPNL Threshold** (Line 2654):
```python
fibonacci_triggered = upnl_pct ≤ safe_threshold_pct
```

**Both Must Pass** (Line 2655):
```python
should_average = gate_passed AND fibonacci_triggered
```

**Purpose**:
- Gate 1: Prevents averaging on small losses
- Gate 2: Ensures Fibonacci spacing is respected
- Combined: Only average when truly needed

---

## ACTUAL TRIGGER EXAMPLES (From Current Logs)

### Example 1: RDNT (Step 1)
```
Symbol: RDNT/USDT:USDT
Current UPNL: -53.75%
Price Threshold: 11.00% (from delta calculation)
UPNL Threshold: -110.00% (11% × 10x leverage)
Current vs Threshold: -53.75% > -110.00%
Decision: ❌ BLOCKED (not deep enough)
```

### Example 2: TURBO (Step 1)
```
Symbol: TURBO/USDT:USDT
Current UPNL: -47.33%
Price Threshold: 4.63%
UPNL Threshold: -46.34% (4.63% × 10x leverage)
Current vs Threshold: -47.33% ≤ -46.34%
Decision: ✅ TRIGGERED (threshold reached)
```

### Example 3: FLOKI (Step 1)
```
Symbol: FLOKI/USDT:USDT
Current UPNL: -36.82%
Price Threshold: 6.32%
UPNL Threshold: -63.16%
Current vs Threshold: -36.82% > -63.16%
Decision: ❌ BLOCKED (not deep enough yet)
```

---

## WHY POSITIONS GREW 6x-19x

### Fibonacci Capital Multipliers

**From Code** (Lines 2871-2880):
```python
margin_to_add = original_margin × multiplier
```

**Multipliers by Step**:
```
Step 1: 1x original margin
Step 2: 1x original margin
Step 3: 2x original margin
Step 4: 3x original margin
Step 5: 5x original margin
Step 6: 8x original margin
Step 7: 13x original margin
```

**Total Capital After Each Step**:
```
Start:   $25 (1.0x)
Step 1:  $50 (2.0x) = $25 + ($25 × 1)
Step 2:  $75 (3.0x) = $50 + ($25 × 1)
Step 3:  $125 (5.0x) = $75 + ($25 × 2)
Step 4:  $200 (8.0x) = $125 + ($25 × 3)
Step 5:  $325 (13.0x) = $200 + ($25 × 5)
```

**Position Size Growth** (at same price):
```
If 1 contract costs $0.10:
Step 0: 2,500 contracts ($25 margin at 10x)
Step 1: 5,000 contracts ($50 margin)
Step 2: 7,500 contracts ($75 margin)
Step 3: 12,500 contracts ($125 margin)
Step 4: 20,000 contracts ($200 margin)

Growth: 8.0x after Step 4
```

**Matches Observed Growth**:
- RDNT: 9.91x → Likely Step 4-5
- FLOKI: 9.53x → Likely Step 4-5
- TURBO: 9.46x → Likely Step 4-5
- CKB: 9.00x → Likely Step 4
- DOGE: 6.44x → Likely Step 3-4
- ENA: 18.85x → Likely Step 5+ (13x-20x range)

---

## CRITICAL INSIGHT: AVERAGING AT CURRENT PRICE

### The Code (Line 2868-2880)

```python
# Get current ticker price for new order
ticker = self.exchange.fetch_ticker(symbol)
current_price = ticker['last']  # ← Current market price

# Calculate contracts to add at current price
avg_amount = dollar_to_add / current_price

# ❌ NO CHECK if current_price improves entry_price
# Just averages at whatever price market is at when threshold triggers
```

### What This Means

**Averaging happens at WHATEVER PRICE when UPNL threshold triggers**, not at a better price.

**Example Timeline**:
1. Enter LONG at $1.00 (1000 contracts, $100 margin at 10x)
2. Price drops to $0.97 (-3%)
   - UPNL: -$30 (-30% of margin)
   - Triggers Step 1 threshold (-16%)
3. **System averages at $0.97** (current price)
4. New weighted avg: ($1.00×1000 + $0.97×1000) / 2000 = **$0.985**
   - ✅ **Improved** from $1.00 → $0.985

**But if price bounces before averaging**:
1. Enter at $1.00
2. Price drops to $0.96 (-4%), triggers averaging threshold
3. **Price bounces to $0.99** before order executes
4. **System averages at $0.99** (current price)
5. New weighted avg: ($1.00×1000 + $0.99×1000) / 2000 = **$0.995**
   - ⚠️ **Slightly improved** but barely

**Worst case - price in uptrend after triggering**:
1. Enter at $1.00
2. Price drops to $0.95 (-5%), deep UPNL triggers Step 2
3. **Price rallies to $1.02** (market reverses)
4. **System averages at $1.02** (current price when order executes)
5. New weighted avg: ($1.00×1000 + $1.02×2000) / 3000 = **$1.013**
   - ❌ **DEGRADED** from $1.00 → $1.013

---

## THE MISSING PRICE CHECK

### Current Logic
```python
if upnl_pct ≤ threshold_pct:
    # Average at current_price (whatever it is)
    avg_amount = dollar_to_add / current_price
```

### Should Add (Like Pyramid Fix)
```python
if upnl_pct ≤ threshold_pct:
    # CHECK: Only average if price improves weighted avg
    if side == 'buy':
        if current_price >= position['entry_price']:
            print(f"  ❌ Averaging blocked: Price bounced to ${current_price}")
            print(f"     Would degrade weighted avg ${position['entry_price']}")
            print(f"     Wait for price to drop below ${position['entry_price']}")
            return False

    # If price check passes, average at better price
    avg_amount = dollar_to_add / current_price
```

---

## WHY ENTRY PRICES DIDN'T CHANGE MUCH

### Hypothesis
Positions show original entry prices despite 10x growth because:

**Option 1: Averaging at Similar Prices**
- Triggers fired at various UPNL levels
- But price stayed in similar range (±2-3%)
- Weighted average moved slightly but not dramatically
- Example: $0.24 → $0.2399 (0.04% change)

**Option 2: Exchange Entry Price Lag**
- Exchange updates weighted avg after each order
- System reads entry_price on position load
- Possible sync delay or caching issue

**Option 3: Price Bounced Before Averaging**
- Threshold triggered at low price
- Price bounced up before order executed
- Averaged at higher price, degrading average
- Net result: Entry price stayed near original

**Most Likely**: Combination of all three
- Some averages improved entry slightly
- Some degraded it (price bounced)
- Net result: Entry price changed < 1%
- With 10x leverage, 1% entry change = minimal vs UPNL impact

---

## CURRENT STATE ANALYSIS

### Position State (Jan 3, 2026)

| Symbol | Original | Current | Steps Likely | UPNL % | Zone |
|--------|----------|---------|--------------|--------|------|
| RDNT | 2,337 | 23,171 | 4-5 | -53.75% | AVERAGING |
| ENA | 117 | 2,205 | 5+ | -28.32% | AVERAGING |
| FLOKI | 564k | 5.3M | 4-5 | -36.82% | AVERAGING |
| TURBO | 13,305 | 125,853 | 4-5 | -47.33% | AVERAGING |
| CKB | 10,372 | 93,348 | 4 | -33.72% | AVERAGING |
| DOGE | 194 | 1,250 | 3-4 | -1.7% | NEUTRAL |

### Averaging Steps Counter = 0 (Why?)

**From state**: `"averaging_steps": {"RDNT": 0, "TURBO": 0, ...}`

**But positions grew 6x-19x** → Steps WERE executed

**Likely Causes**:
1. **Counter persistence bug** (like pyramid_count)
2. **Counter reset on restart**
3. **Counter not saved to Redis/JSON properly**

**Evidence**:
- Logs show "Averaging executed - Fibonacci step 1/2/3/4"
- Position sizes match 4-5 step execution
- But counter shows 0

**Similar to pyramid_count bug**: Field not persisted correctly.

---

## SYSTEM DESIGN REVIEW

### What Works Well ✅

1. **Dynamic Delta Calculation**
   - Adapts to volatility regimes
   - Coin-specific base deltas
   - Multi-timeframe ATR measurement
   - Correlation adjustment

2. **Fibonacci Spacing**
   - Progressive thresholds
   - Earlier steps: Tight (catch reversals)
   - Later steps: Wide (survive drawdowns)

3. **Dual-Gate System**
   - Gate 1: -25% P&L prevents early averaging
   - Gate 2: Fibonacci threshold ensures proper spacing

4. **Capital Management**
   - Fibonacci multipliers (1, 1, 2, 3, 5, 8)
   - Progressively larger adds
   - Designed to recover from deep losses

5. **Safety Systems**
   - Hard caps at -60%, -70%, -80%
   - Emergency override at -85%
   - Liquidation prevention

### What Needs Fixing ❌

1. **No Price Improvement Check**
   - Averages at current price when threshold triggers
   - Can degrade weighted average if price bounced
   - **Fix**: Add same check as pyramid (current < entry for LONG)

2. **Averaging Counter Not Persisting**
   - Steps execute but counter shows 0
   - Similar to pyramid_count bug
   - **Fix**: Add to Redis persistence mapping

3. **Entry Price Sync**
   - May not be syncing from exchange after averaging
   - Position shows original entry despite adds
   - **Fix**: Fetch and update entry_price from exchange positions

---

## RECOMMENDATIONS

### Priority 1: Add Price Improvement Check
Same logic as pyramid fix - only average if price improves weighted average.

### Priority 2: Fix Averaging Counter Persistence
Add `averaging_steps` to position_persistence_manager.py Redis mapping.

### Priority 3: Sync Entry Price from Exchange
After each averaging execution, fetch updated entry_price from exchange API.

### Priority 4: Log Averaging Execution Details
```python
print(f"  📊 Averaging at ${current_price:.6f}")
print(f"     Previous entry: ${entry_price:.6f}")
print(f"     Adding {avg_amount:,.0f} contracts")
print(f"     Capital: ${margin_to_add:.2f} (Step {step+1} = {multiplier}x original)")
print(f"     New position size: {new_total:,.0f} contracts")
print(f"     Exchange will calculate new weighted avg entry")
```

---

## CONCLUSION

**Averaging System is UPNL threshold-based, NOT price-based**:

1. **Delta** calculated from volatility (0.5%-10%)
2. **Fibonacci thresholds** generated from delta (step spacing)
3. **Price thresholds** converted to **UPNL thresholds** (× leverage)
4. **Dual gates** check: P&L ≤ -25% AND UPNL ≤ threshold
5. **Fibonacci multipliers** add exponentially more capital (1, 1, 2, 3, 5, 8)
6. **Averages at current price** when threshold triggers

**Position growth 6x-19x is BY DESIGN** - Fibonacci recovery system working as intended.

**The BUG**: No price check means averaging can happen at ANY price when threshold triggers, potentially degrading weighted average instead of improving it.

**The FIX**: Add price improvement check (current < entry for LONG) before averaging execution - same as pyramid fix.
