# Averaging Steps Counter - Fix Report

**Date**: January 3, 2026
**Issue**: `averaging_steps` counter shows 0 for all positions despite 6x-19x growth
**Status**: ⚠️ **ROOT CAUSE IDENTIFIED - FIX IN PROGRESS**

---

## 🔍 PROBLEM SUMMARY

All positions show `averaging_steps = 0` despite historical growth:
- RDNT: 9.91x growth (should be step 4)
- FLOKI: 9.53x growth (should be step 4)
- TURBO: 9.46x growth (should be step 4)
- CKB: 9.00x growth (should be step 4)
- ENA: 18.85x growth (should be step 6)

**Impact**:
- Liquidation protection won't trigger (requires step 5+)
- System can't track averaging progress
- Historical averaging data lost

---

## 🔬 ROOT CAUSE ANALYSIS

### **Discovery Process**

1. **Checked `position_persistence_manager.py`**
   - ✅ `averaging_steps` IS included in Redis persistence (line 95)
   - ✅ Save/load functions correctly handle `averaging_steps`

2. **Checked main system averaging execution**
   - ✅ Counter IS incremented when averaging executes (line 2984)
   - ✅ State IS saved after increment (lines 3001-3011)

3. **Found the reset location**
   - ❌ `reconcile_with_exchange()` function (line 3926) resets to 0 for "new" positions (line 4017)
   - ❌ This function runs on EVERY monitoring cycle (line 4139)

4. **Tested state persistence**
   - ✅ Fix script correctly calculates steps from size ratio
   - ✅ Redis and file state updated with correct values (4, 4, 4, 4, 6)
   - ✅ System loads correct values at startup
   - ❌ Values reset back to 0 during first monitoring cycle

### **The Bug**

**File**: `aixyz_continuous_profit_system.py`
**Function**: `reconcile_with_exchange()` (line 3926)

```python
def reconcile_with_exchange(self):
    """Reconcile system state with exchange positions"""
    # Get all positions from exchange
    exchange_positions = self.exchange.fetch_positions()

    for symbol, ex_pos in active_exchange.items():
        if symbol in self.active_positions:
            # UPDATE existing position
            self.active_positions[symbol]['amount'] = ex_pos['contracts']
            # ✅ Does NOT reset averaging_steps here
        else:
            # Add NEW position
            self.active_positions[symbol] = {...}
            # ❌ BUG: Resets averaging_steps to 0 (line 4017)
            self.averaging_steps[symbol] = 0
```

**Why it breaks**:
- On startup: Positions loaded with correct `averaging_steps` (4, 4, 4, 4, 6)
- First monitor cycle: `reconcile_with_exchange()` runs
- If ANY condition causes positions to be treated as "new", they get reset to 0
- OR if the reconcile logic has a bug where `symbol in self.active_positions` evaluates False

---

## ✅ FIXES APPLIED

### **1. Created Fix Script** (`fix_averaging_steps.py`)

Calculates correct step count from position size growth:

```python
def infer_averaging_steps(size_ratio):
    """Fibonacci growth pattern:
    1.0x = 0 steps
    2.0x = 1 step
    3.0x = 2 steps
    5.0x = 3 steps
    8.0x = 4 steps
    13.0x = 5 steps
    21.0x = 6 steps
    """
    if size_ratio < 1.5: return 0
    elif size_ratio < 2.5: return 1
    elif size_ratio < 4.0: return 2
    elif size_ratio < 6.5: return 3
    elif size_ratio < 10.5: return 4
    elif size_ratio < 17.0: return 5
    else: return 6
```

**Result**:
- RDNT: 0 → 4
- FLOKI: 0 → 4
- TURBO: 0 → 4
- CKB: 0 → 4
- ENA: 0 → 6

### **2. Added Debug Logging**

**File**: `position_persistence_manager.py` (line 177)
```python
logger.info(f"🔍 Reconcile: averaging_steps from saved state: {averaging_steps}")
```

**File**: `aixyz_continuous_profit_system.py` (line 3942)
```python
print(f"  🔄 Reconcile: {symbol} already tracked (averaging_steps={self.averaging_steps.get(symbol, 'N/A')})")
```

**Purpose**: Track when and how averaging_steps is being reset

### **3. State File and Redis Updated**

Both `position_state.json` and Redis `aixyz:position_state` updated with correct values.

---

## 📊 TEST RESULTS

### **Startup Behavior (Verified)**

```
2026-01-03 11:29:27 [info] 🔍 Reconcile: averaging_steps from saved state:
  {'RDNT/USDT:USDT': 4, 'FLOKI/USDT:USDT': 4, 'TURBO/USDT:USDT': 4,
   'CKB/USDT:USDT': 4, 'ENA/USDT:USDT': 6}

📂 Loaded 8 positions from saved state
  Loaded positions:
    RDNT/USDT:USDT: buy | Zone: AVERAGING | Avg Steps: 4 ✅
    FLOKI/USDT:USDT: buy | Zone: AVERAGING | Avg Steps: 4 ✅
    TURBO/USDT:USDT: buy | Zone: AVERAGING | Avg Steps: 4 ✅
    CKB/USDT:USDT: buy | Zone: AVERAGING | Avg Steps: 4 ✅
    ENA/USDT:USDT: buy | Zone: NEUTRAL | Avg Steps: 6 ✅
```

**✅ System loads correct values at startup**

### **First Monitoring Cycle (Problem)**

```
2026-01-03 11:29:47 [info] AVERAGING_CHECK_START current_step=0 symbol=RDNT/USDT:USDT
2026-01-03 11:29:47 [debug] Too early for liquidation protection current_step=0 symbol=CKB/USDT:USDT
2026-01-03 11:29:47 [debug] Too early for liquidation protection current_step=0 symbol=ENA/USDT:USDT
```

**❌ Values reset to 0 during first monitoring cycle**

---

## 🔧 REMAINING WORK

### **Option 1: Prevent Reset in reconcile_with_exchange()**

Modify the "new position" logic to check if `averaging_steps` already exists:

```python
# Line 4017 in aixyz_continuous_profit_system.py
# BEFORE:
self.averaging_steps[symbol] = 0

# AFTER:
# Preserve averaging_steps if already tracked
if symbol not in self.averaging_steps:
    self.averaging_steps[symbol] = 0
else:
    print(f"  ⚠️ Preserving averaging_steps={self.averaging_steps[symbol]} for {symbol}")
```

### **Option 2: Infer Steps from Size on Every Reconcile**

Add automatic inference logic to reconcile:

```python
# After adding position, check size vs original
if symbol in self.original_sizes:
    current_size = ex_pos['contracts']
    original_size = self.original_sizes[symbol]
    if current_size > original_size * 1.5:
        # Size grew - infer steps
        size_ratio = current_size / original_size
        inferred_steps = infer_averaging_steps(size_ratio)
        self.averaging_steps[symbol] = inferred_steps
        print(f"  🔧 Inferred averaging_steps={inferred_steps} from size ratio {size_ratio:.2f}x")
```

### **Option 3: Don't Reconcile on Every Cycle**

Limit reconcile to only run:
- At startup
- When explicitly needed (manual position detected)
- Not on every monitoring cycle

**Recommendation**: **Option 1** (simplest, preserves existing logic)

---

## 💡 TEMPORARY WORKAROUND

**Manual Fix Command** (run when needed):
```bash
python3 /root/ai_xyz/fix_averaging_steps.py && \
cat /root/ai_xyz/position_state.json | redis-cli -n 1 -x SET aixyz:position_state
```

**This recalculates steps from size growth and updates both file and Redis.**

---

## 🎯 EXPECTED BEHAVIOR AFTER FIX

Once fixed, the system should:

1. ✅ Load correct `averaging_steps` from persistence (4, 4, 4, 4, 6)
2. ✅ Preserve values during `reconcile_with_exchange()`
3. ✅ Enable liquidation protection for ENA (step 6 > 5 required)
4. ✅ Increment counters correctly when new averaging executes
5. ✅ Save and persist counters across restarts

---

## 📝 FILES MODIFIED

1. **`fix_averaging_steps.py`** - New file to calculate correct steps
2. **`position_persistence_manager.py`** - Added debug logging (line 177)
3. **`aixyz_continuous_profit_system.py`** - Added debug logging (line 3942)

**Files still need modification:**
- `aixyz_continuous_profit_system.py` (line 4017) - Apply Option 1 fix

---

## 🚀 NEXT STEPS

1. **Apply Option 1 fix** to prevent reset
2. **Test with system restart** to verify persistence
3. **Monitor ENA position** (should trigger liquidation protection at step 6)
4. **Remove debug logging** once verified working

---

**Status**: 🔨 **IN PROGRESS** - Root cause identified, fix ready to apply
