# AI-XYZ SYSTEM: MUTUALLY AGREED UNDERSTANDING

**Date**: January 16, 2026
**Parties**: Claude (Opus 4.5) & Grok (grok-2-latest)
**Status**: AGREED on all points after code evidence review

---

## 1. ZONE-BASED POSITION MANAGEMENT

### 1.1 Zone Thresholds (AGREED)

**File**: `aixyz_continuous_profit_system.py` lines 731-746

```python
self.zone_thresholds = {
    'averaging': -0.25,      # -25% UPNL triggers averaging
    'profit_taking': 0.05,   # +5% UPNL enters surplus dump zone
    'stop_loss': -0.95       # -95% UPNL (liquidation prevention ONLY)
}
self.neutral_zone_upper_usd = 0.15  # $0.15 USD minimum UPNL to exit neutral
```

### 1.2 Zone State Machine (AGREED)

| Zone | Trigger Condition | Action |
|------|-------------------|--------|
| **NEUTRAL** | -$0.15 < UPNL < +$0.15 USD | Hold, no action |
| **AVERAGING** | UPNL ≤ -25% | Execute Fibonacci averaging steps |
| **PROFIT_TAKING** | UPNL > +5%, no averaging done | Monitor peak UPNL |
| **SURPLUS_DUMP** | UPNL > +5%, has averaged | Execute staged profit taking |
| **STOP_LOSS** | UPNL ≤ -95% | Emergency close (liquidation prevention) |

### 1.3 Stop-Loss Philosophy (AGREED)

**File**: `aixyz_continuous_profit_system.py` lines 737-741

```python
# Sprint 14: Stop Loss Philosophy
# - DISABLED traditional stop loss (positions can recover)
# - ONLY liquidation prevention at -95% UPNL
# - Instead of stop loss, use dynamic delta expansion in extreme markets
self.stop_loss_disabled = True
```

---

## 2. SURPLUS DUMP STRATEGY (AGREED)

### 2.1 Two-Stage Peak-Based Dumping

**File**: `aixyz_continuous_profit_system.py` lines 793-794

```python
self.surplus_dump_threshold = 0.85       # 85% of peak - Stage 1 (dump 50% of surplus)
self.surplus_dump_threshold_stage2 = 0.40  # 40% of peak - Stage 2 (dump remaining 50%)
```

### 2.2 Surplus Calculation

```
surplus = current_position_size - original_position_size
```

**Example**:
- Original position: 1000 contracts
- After averaging: 2500 contracts
- Surplus: 1500 contracts
- Peak UPNL reached: $100

**Stage 1** (UPNL drops to 85% = $85):
- Dump 50% of surplus = 750 contracts

**Stage 2** (UPNL drops to 40% = $40):
- Dump remaining 50% of surplus = 750 contracts

---

## 3. ADVERSE RECOVERY V3.1.0 (AGREED - NEW FEATURE)

### 3.1 Market Regime-Based Thresholds

**File**: `aixyz_continuous_profit_system.py` lines 796-807

```python
# V3.1.0: Market regime-based adverse recovery
self.adverse_recovery_threshold_stage1 = 0.50  # 50% of peak (hold longer)
self.adverse_recovery_threshold_stage2 = 0.20  # 20% of peak (hold longer)
self.adverse_market_regimes = ['high_vol', 'crisis']
self.recovered_market_regimes = ['normal_vol', 'low_vol']

# Track market regime when position was opened
self.position_opened_regime: Dict[str, str] = {}
```

### 3.2 Logic Flow

```
1. When position OPENS → record current market regime from Grok V2 HMM
2. During averaging → update to WORST regime seen (crisis > high_vol > normal_vol > low_vol)
3. At surplus dump check:
   - IF opened_regime IN ['high_vol', 'crisis']
   - AND current_regime IN ['normal_vol', 'low_vol']
   - THEN use 50/20 thresholds (ADVERSE RECOVERY MODE)
   - ELSE use 85/40 thresholds (STANDARD MODE)
```

### 3.3 Threshold Comparison

| Mode | Stage 1 | Stage 2 | Use Case |
|------|---------|---------|----------|
| **STANDARD** | 85% of peak | 40% of peak | Normal market conditions |
| **ADVERSE RECOVERY** | 50% of peak | 20% of peak | Opened in crisis, market recovered |

---

## 4. FIBONACCI AVERAGING SYSTEM (AGREED)

### 4.1 Base Averaging Multipliers

**File**: `aixyz_continuous_profit_system.py` lines 775-784

```python
self.base_averaging_multipliers = [
    0.5,   # Step 1: 0.5x original (small test)
    0.75,  # Step 2: 0.75x original (conservative)
    1.5,   # Step 3: 1.5x original (moderate)
    3.0,   # Step 4: 3x original (aggressive)
    5.0,   # Step 5: 5x original (Fibonacci F5)
    8.0,   # Step 6: 8x original (Fibonacci F6)
    12.0,  # Step 7: 12x original (extreme)
    15.0   # Step 8: 15x original (final push)
]
```

### 4.2 Grok V2 Reduced Multipliers

**File**: `aixyz_continuous_profit_system.py` lines 971-988

```python
# Grok V2: Reduced from 19x total to 10x total for better risk control
if averaging_steps_possible == 5:
    self.averaging_multipliers = [1.0, 1.5, 2.0, 2.5, 3.0]  # 10x total
elif averaging_steps_possible == 4:
    self.averaging_multipliers = [1.0, 1.5, 2.0, 2.5]       # 7x total
elif averaging_steps_possible == 3:
    self.averaging_multipliers = [1.0, 1.5, 2.0]            # 4.5x total
elif averaging_steps_possible == 2:
    self.averaging_multipliers = [1.0, 1.5]                 # 2.5x total
elif averaging_steps_possible == 1:
    self.averaging_multipliers = [1.0]                      # 1x only
```

### 4.3 Dynamic Delta Calculation

**File**: `dynamic_fibonacci_delta.py` lines 164-165

```python
Dynamic_Delta = Base_Delta × Volatility_Multiplier × Correlation_Factor

# Where:
# - Base_Delta: Per-coin calibration (BTC: 1.5%, SOL: 2.0%, DOGE: 3.0%)
# - Volatility_Multiplier = sqrt(current_vol / historical_vol), clamped [0.5, 2.0]
# - Correlation_Factor = 1.0 + (0.1 × (1 - BTC_correlation))
```

---

## 5. CSSI - CORRECTION-SUPPORT STRENGTH INDEX (AGREED)

### 5.1 CSSI Data Structure

**File**: `historical_correction_analyzer.py` lines 73-83

```python
@dataclass
class CSSI:
    symbol: str
    cssi_score: float              # Main metric (0-3+)
    correction_probability: float  # Historical correction % (0-1)
    support_proximity: float       # Distance to support (0-1)
    risk_factor: float            # Risk adjustment (0.3-1.0)
    recommended_action: str        # 'AVERAGE_IN', 'HOLD', 'REDUCE'
    step_multiplier: float        # Position size modifier (0.5-2.0)
```

### 5.2 CSSI Formula

```
CSSI = (correction_probability / 100) × proximity_to_support × risk_factor
```

### 5.3 Correction Probability (Logistic Regression)

**File**: `historical_correction_analyzer.py` (line reference in docs)

```
P(correction | depth) = 1 / (1 + exp(-β₀ - β₁×d - β₂×d²))

Default Coefficients:
β₀ = -1.0 (intercept)
β₁ = 20.0 (slope)
β₂ = 0.0  (quadratic term)

Example Probabilities:
- 5% drawdown:  ~50% correction probability
- 10% drawdown: ~80% correction probability
- 15% drawdown: ~92% correction probability
```

### 5.4 CSSI Decision Matrix

| CSSI Score | Action | Step Multiplier |
|------------|--------|-----------------|
| ≥ 1.5 | AVERAGE_IN_AGGRESSIVE | 1.45-2.0x |
| ≥ 1.0 | AVERAGE_IN | 1.2-1.5x |
| ≥ 0.5 | HOLD | 1.0x |
| < 0.5 | REDUCE | 0.5-1.0x |

---

## 6. VOLATILITY REGIME HMM (AGREED)

### 6.1 Four Regimes (Not Three)

**File**: `grok_v2_volatility_regime_hmm.py` lines 22-27

```python
class VolatilityRegime(Enum):
    LOW_VOL = "low_vol"
    NORMAL_VOL = "normal_vol"
    HIGH_VOL = "high_vol"
    CRISIS = "crisis"  # 4th regime - extreme market conditions
```

### 6.2 Volatility Thresholds

**File**: `grok_v2_volatility_regime_hmm.py` lines 63-68

```python
VOL_THRESHOLDS = {
    VolatilityRegime.LOW_VOL: (0, 20),      # 0-20% annualized
    VolatilityRegime.NORMAL_VOL: (15, 40),  # 15-40% annualized
    VolatilityRegime.HIGH_VOL: (35, 80),    # 35-80% annualized
    VolatilityRegime.CRISIS: (70, 200),     # 70-200% annualized
}
```

### 6.3 Transition Matrix

**File**: `grok_v2_volatility_regime_hmm.py` lines 55-60

```python
INITIAL_TRANSITION = np.array([
    [0.90, 0.08, 0.02, 0.00],  # LOW_VOL stays 90%
    [0.10, 0.80, 0.08, 0.02],  # NORMAL_VOL stays 80%
    [0.02, 0.10, 0.80, 0.08],  # HIGH_VOL stays 80%
    [0.00, 0.05, 0.15, 0.80],  # CRISIS stays 80%
])
```

---

## 7. LIQUIDATION PROTECTION (AGREED)

### 7.1 Protection Threshold

**File**: `position_sizing_config.py`

```python
LIQUIDATION_ORDER_UPNL_PERCENT = -82.5  # Protection at -82.5% UPNL
```

### 7.2 Trigger Conditions

**File**: `liquidation_protection_service.py`

```python
# ALL conditions must be met:
1. averaging_step >= 5  # (6th step or higher)
2. -82% <= upnl_pct <= -70%  # (danger zone)
3. No existing protection order for symbol
4. No previously executed protection order
```

### 7.3 Protection Order Calculation

```python
protection_price = entry_price × (1 - 0.825 / (leverage × 10))
additional_margin = margin_used × 1.0  # Match margin
protection_contracts = (additional_margin × leverage) / protection_price
```

---

## 8. MARKET SCANNER V4.0 (AGREED)

### 8.1 Two-Stage Filtering

**File**: `scanner_v4.py`

```
STAGE 1: Quick Filter (ALL ~497 USDT perpetual futures)
├─ Volume filter:     > $10M 24h volume (NOT $1M)
├─ Liquidity filter:  < 0.5% bid-ask spread
├─ Volatility filter: 1% ≤ volatility ≤ 20%
│
└─ Output: ~120-140 candidates (25-28%)

STAGE 2: Deep Analysis (Top 40 by volume × volatility)
├─ VSA (Volume Spread Analysis) scoring
├─ MACD divergence detection
├─ Support/resistance levels
├─ Multi-timeframe confirmation
│
└─ Output: Ranked opportunities
   ├─ Score ≥ 0.70: ENTRY signal
   ├─ Score 0.55-0.70: MONITOR
   └─ Score < 0.55: REJECT
```

### 8.2 Score Thresholds (Decimal, Not Percentage)

| Threshold | Value | Action |
|-----------|-------|--------|
| Entry | ≥ 0.70 | Open position |
| Minimum | ≥ 0.55 | Consider monitoring |
| Reject | < 0.55 | Skip opportunity |

---

## 9. GROK V2 MODULES (AGREED)

### 9.1 Complete Module List

**File**: `grok_v2_integration.py`

| # | Module | File | Purpose |
|---|--------|------|---------|
| 1 | Trade Tracker | `trade_results_tracker.py` | Profit factor metrics |
| 2 | Bayesian Correction | `grok_v2_bayesian_correction.py` | Per-symbol correction probability |
| 3 | Volatility HMM | `grok_v2_volatility_regime_hmm.py` | 4-regime detection |
| 4 | Redis Pool | `grok_v2_redis_pool.py` | Connection pooling |
| 5 | VaR Calculator | `grok_v2_var_integration.py` | Value at Risk limits |
| 6 | WebSocket Events | `grok_v2_websocket_events.py` | Real-time updates |
| 7 | Stress Testing | `grok_v2_stress_testing.py` | Scenario analysis |
| 8 | Ensemble Exit | `grok_v2_ensemble_exit.py` | Multi-model exit signals |
| 9 | Online CSSI | `grok_v2_online_cssi_learning.py` | Continuous learning |
| 10 | Anomaly Detection | `grok_v2_anomaly_detection.py` | Z-score anomalies |
| 11 | Graceful Degradation | `grok_v2_graceful_degradation.py` | Fallback mechanisms |

### 9.2 Integration Class

**File**: `grok_v2_integration.py` lines 68-84

```python
class GrokV2Integration:
    """
    Main integration class for all Grok V2 enhancements.

    Provides unified interface to:
    1. Trade result tracking
    2. Bayesian correction probability
    3. Volatility regime detection (HMM)
    4. Redis connection pooling
    5. VaR position limits
    6. WebSocket events (optional)
    7. Stress testing
    8. Ensemble exit model
    9. Online CSSI learning
    10. Anomaly detection
    11. Graceful degradation
    """
    VERSION = "2.0.0"
```

---

## 10. KEY CONFIGURATION VALUES (AGREED)

### 10.1 Position Sizing

| Parameter | Value | File Reference |
|-----------|-------|----------------|
| Max Positions | 12 (correlation-adjusted) | main.py |
| Base Margin | $5.00 | position_sizing_config.py |
| Averaging Capital | $20.00 | position_sizing_config.py |
| Total per Position | $25 + $25 protection = $50 | position_sizing_config.py |
| Default Leverage | 5x | .env |
| Max Leverage | 20x | .env |

### 10.2 Zone Thresholds

| Parameter | Value | File Reference |
|-----------|-------|----------------|
| Neutral Zone | -$0.15 to +$0.15 USD | main.py:746 |
| Averaging Trigger | -25% UPNL | main.py:732 |
| Profit Taking Trigger | +5% UPNL | main.py:733 |
| Stop Loss | -95% UPNL | main.py:734 |

### 10.3 Surplus Dump

| Parameter | Standard | Adverse Recovery |
|-----------|----------|------------------|
| Stage 1 | 85% of peak | 50% of peak |
| Stage 2 | 40% of peak | 20% of peak |

### 10.4 Risk Management

| Parameter | Value | File Reference |
|-----------|-------|----------------|
| Liquidation Protection | -82.5% UPNL at step ≥6 | position_sizing_config.py |
| High Correlation Limit | 4 positions (if corr > 0.7) | main.py:1016 |
| Moderate Correlation Limit | 6 positions (if corr > 0.5) | main.py:1020 |

---

## 11. HEDGE GATEWAY (ADDITIONAL - AGREED)

### 11.1 Hedge Position Averaging Gate

**File**: `aixyz_continuous_profit_system.py` lines 3015-3040 (per CLAUDE.md)

```python
# Hedge positions require -70% UPNL before averaging (stricter than main)
# Main positions: -25% UPNL gate (normal)
# Hedge positions: -70% UPNL gate (protective)
hedge_gate_threshold = -70.0
```

| Position Type | Averaging Gate |
|---------------|----------------|
| Main positions | -25% P&L |
| Hedge positions | -70% P&L |

---

## SIGNATURES

**Claude (Opus 4.5)**: ✅ AGREED - All findings verified against actual codebase
**Grok (grok-2-latest)**: ✅ AGREED - Corrected understanding based on code evidence

---

## DOCUMENT STATUS

- **Created**: January 16, 2026
- **Purpose**: Mutual agreement on AI-XYZ system understanding
- **Next Step**: User review, then update CLAUDE.md and memorize
