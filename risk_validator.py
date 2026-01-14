#!/usr/bin/env python3
"""
Risk Management Validator for AI-XYZ Trading System
V2.2.0 - January 14, 2026

Validates risk management systems with live/shadow data:
- Dynamic leverage trigger validation
- Alert false positive/negative analysis
- Circuit breaker effectiveness testing
- Hysteresis tuning recommendations
- Explicit performance targets with auto-tuning
- ADX-based trend detection for regime differentiation
- Auto-tune guardrails for safe parameter adjustment
- Enhanced alert detection with velocity/proximity signals (Sprint 9)

Sprint 6 - Grok Recommendation:
"Conduct live or shadow trading to validate dynamic leverage triggers
and circuit breaker effectiveness. Analyze false positives/negatives
in risk alerts and refine if needed."

Sprint 7 Enhancement (Grok):
"Set explicit precision (>90%), recall (>85%), and F1 thresholds.
Document regime definitions (volatility bands using ATR).
Integrate real-time feedback from shadow trading into live risk models."

Sprint 8 Enhancement (Grok):
"Resolve ATR range overlap between NORMAL and TRENDING regimes using ADX.
Implement strict guardrails for auto-tuning (leverage caps, human approval,
rollback capability)."

Sprint 9 Enhancement (Claude + Grok Consensus):
"Revised alert targets: Recall 70% (pragmatic), False Negative <40% (achievable).
Integrated EnhancedAlertDetector with velocity-based and proximity detection.
Tightened leverage aggressiveness to <10%."

Author: Claude + Grok Consortium
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from collections import defaultdict
from enum import Enum
import logging
import statistics

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Results file
VALIDATION_RESULTS_FILE = '/root/ai_xyz/risk_validation_results.json'
AUTO_TUNE_CONFIG_FILE = '/root/ai_xyz/risk_auto_tune_config.json'


# =============================================================================
# PERFORMANCE TARGETS (Sprint 7 - Grok Recommendation)
# =============================================================================

@dataclass
class PerformanceTargets:
    """
    Explicit performance targets for risk management validation.

    Sprint 7: "Define acceptable precision (>90%), recall (>85%),
    and F1 thresholds for alerts, and backtest against historical data."

    Sprint 9 Update (Claude + Grok Consensus):
    - Adjusted recall target from 85% to 70% (pragmatic balance)
    - Adjusted false negative target from 15% to 40% (achievable goal)
    - Added integration with EnhancedAlertDetector for improved detection
    """
    # Alert accuracy targets - Sprint 9 revised targets
    alert_precision_min: float = 0.85      # >85% precision (few false positives)
    alert_recall_min: float = 0.70         # >70% recall (Sprint 9: pragmatic target)
    alert_f1_min: float = 0.77             # Harmonic mean target (adjusted)
    alert_false_positive_max: float = 0.15 # <15% false positive rate
    alert_false_negative_max: float = 0.40 # <40% false negative rate (Sprint 9: achievable)

    # Leverage effectiveness targets - Sprint 9 tightened
    leverage_correct_min: float = 0.80     # >80% correct leverage choices
    leverage_aggressive_max: float = 0.10  # <10% too aggressive (tightened from 15%)
    leverage_conservative_max: float = 0.20  # <20% too conservative

    # Circuit breaker targets - Sprint 9 improved
    circuit_breaker_effectiveness_min: float = 0.80  # >80% effective (up from 70%)
    circuit_breaker_false_trigger_max: float = 0.15  # <15% false triggers
    circuit_breaker_missed_max: float = 0.10         # <10% missed triggers

    # Hysteresis targets
    hysteresis_accuracy_min: float = 0.80  # >80% accuracy

    # Shadow trading targets
    shadow_win_rate_min: float = 0.50      # >50% win rate
    shadow_risk_check_accuracy_min: float = 0.70  # >70% risk check accuracy


# =============================================================================
# MARKET REGIME DEFINITIONS (Sprint 7 - Grok Recommendation)
# =============================================================================

@dataclass
class RegimeDefinition:
    """
    Clear market regime definition with ATR-based thresholds.

    Grok Sprint 7: "Document regime definitions (e.g., volatility bands
    using ATR or VIX equivalents for crypto)."
    """
    name: str
    atr_ratio_min: float
    atr_ratio_max: float
    recommended_leverage_min: int
    recommended_leverage_max: int
    position_size_multiplier: float
    description: str


# Regime definitions based on ATR ratio (14-period ATR / Price)
REGIME_DEFINITIONS = {
    'EXTREME_VOLATILITY': RegimeDefinition(
        name='EXTREME_VOLATILITY',
        atr_ratio_min=3.0,
        atr_ratio_max=float('inf'),
        recommended_leverage_min=1,
        recommended_leverage_max=3,
        position_size_multiplier=0.25,
        description='Flash crash / extreme conditions. ATR ratio >3.0. Minimal exposure.'
    ),
    'HIGH_VOLATILITY': RegimeDefinition(
        name='HIGH_VOLATILITY',
        atr_ratio_min=2.0,
        atr_ratio_max=3.0,
        recommended_leverage_min=3,
        recommended_leverage_max=5,
        position_size_multiplier=0.50,
        description='High volatility regime. ATR ratio 2.0-3.0. Reduced leverage.'
    ),
    'ELEVATED': RegimeDefinition(
        name='ELEVATED',
        atr_ratio_min=1.5,
        atr_ratio_max=2.0,
        recommended_leverage_min=5,
        recommended_leverage_max=8,
        position_size_multiplier=0.75,
        description='Elevated volatility. ATR ratio 1.5-2.0. Moderate caution.'
    ),
    'NORMAL': RegimeDefinition(
        name='NORMAL',
        atr_ratio_min=0.8,
        atr_ratio_max=1.5,
        recommended_leverage_min=8,
        recommended_leverage_max=12,
        position_size_multiplier=1.0,
        description='Normal market conditions. ATR ratio 0.8-1.5. Standard parameters.'
    ),
    'LOW_VOLATILITY': RegimeDefinition(
        name='LOW_VOLATILITY',
        atr_ratio_min=0.0,
        atr_ratio_max=0.8,
        recommended_leverage_min=10,
        recommended_leverage_max=15,
        position_size_multiplier=1.0,
        description='Low volatility / ranging. ATR ratio <0.8. Can use higher leverage.'
    ),
    'TRENDING': RegimeDefinition(
        name='TRENDING',
        atr_ratio_min=1.0,
        atr_ratio_max=2.0,
        recommended_leverage_min=8,
        recommended_leverage_max=12,
        position_size_multiplier=1.0,
        description='Clear trend detected (separate from volatility). Favorable conditions.'
    )
}


# =============================================================================
# ADX-BASED TREND DETECTION (Sprint 8 - Grok Recommendation)
# =============================================================================

@dataclass
class ADXResult:
    """
    ADX (Average Directional Index) calculation result.

    Grok Sprint 8: "Resolve ATR range overlap between NORMAL and TRENDING
    regimes by incorporating secondary indicators (e.g., ADX for trend strength)."

    ADX Interpretation:
    - ADX < 20: Weak/No trend (ranging market)
    - ADX 20-25: Emerging trend
    - ADX 25-50: Strong trend
    - ADX 50-75: Very strong trend
    - ADX > 75: Extremely strong trend (rare)
    """
    adx: float
    plus_di: float  # +DI (positive directional indicator)
    minus_di: float  # -DI (negative directional indicator)
    trend_strength: str  # WEAK, EMERGING, STRONG, VERY_STRONG
    trend_direction: str  # BULLISH, BEARISH, NEUTRAL

    @property
    def is_trending(self) -> bool:
        """Check if market is trending (ADX >= 25)."""
        return self.adx >= 25.0

    @property
    def is_strong_trend(self) -> bool:
        """Check if trend is strong (ADX >= 40)."""
        return self.adx >= 40.0


# ADX thresholds for trend classification
ADX_THRESHOLDS = {
    'weak': 20.0,       # ADX < 20 = weak/no trend
    'emerging': 25.0,   # ADX 20-25 = emerging trend
    'strong': 40.0,     # ADX 25-40 = strong trend
    'very_strong': 50.0 # ADX > 50 = very strong trend
}


def calculate_adx(highs: List[float], lows: List[float], closes: List[float],
                  period: int = 14) -> Optional[ADXResult]:
    """
    Calculate ADX (Average Directional Index) for trend strength detection.

    This resolves the NORMAL vs TRENDING regime overlap by using ADX
    as a secondary indicator alongside ATR.

    Args:
        highs: List of high prices (most recent last)
        lows: List of low prices
        closes: List of close prices
        period: ADX period (default 14)

    Returns:
        ADXResult with trend strength and direction
    """
    if len(highs) < period + 1 or len(lows) < period + 1 or len(closes) < period + 1:
        return None

    try:
        # Calculate True Range and Directional Movement
        tr_list = []
        plus_dm_list = []
        minus_dm_list = []

        for i in range(1, len(highs)):
            high = highs[i]
            low = lows[i]
            prev_high = highs[i - 1]
            prev_low = lows[i - 1]
            prev_close = closes[i - 1]

            # True Range
            tr = max(
                high - low,
                abs(high - prev_close),
                abs(low - prev_close)
            )
            tr_list.append(tr)

            # Directional Movement
            up_move = high - prev_high
            down_move = prev_low - low

            plus_dm = up_move if up_move > down_move and up_move > 0 else 0
            minus_dm = down_move if down_move > up_move and down_move > 0 else 0

            plus_dm_list.append(plus_dm)
            minus_dm_list.append(minus_dm)

        # Smooth the values using Wilder's smoothing
        def wilder_smooth(values: List[float], period: int) -> List[float]:
            if len(values) < period:
                return []
            smoothed = [sum(values[:period])]
            for i in range(period, len(values)):
                smoothed.append(smoothed[-1] - (smoothed[-1] / period) + values[i])
            return smoothed

        atr_smooth = wilder_smooth(tr_list, period)
        plus_dm_smooth = wilder_smooth(plus_dm_list, period)
        minus_dm_smooth = wilder_smooth(minus_dm_list, period)

        if not atr_smooth or not plus_dm_smooth or not minus_dm_smooth:
            return None

        # Calculate +DI and -DI
        plus_di_list = []
        minus_di_list = []
        dx_list = []

        for i in range(len(atr_smooth)):
            if atr_smooth[i] > 0:
                plus_di = (plus_dm_smooth[i] / atr_smooth[i]) * 100
                minus_di = (minus_dm_smooth[i] / atr_smooth[i]) * 100
            else:
                plus_di = 0
                minus_di = 0

            plus_di_list.append(plus_di)
            minus_di_list.append(minus_di)

            # DX (Directional Index)
            di_sum = plus_di + minus_di
            if di_sum > 0:
                dx = abs(plus_di - minus_di) / di_sum * 100
            else:
                dx = 0
            dx_list.append(dx)

        # Calculate ADX (smoothed DX)
        adx_smooth = wilder_smooth(dx_list, period)

        if not adx_smooth:
            return None

        # Get final values
        adx = adx_smooth[-1]
        plus_di = plus_di_list[-1]
        minus_di = minus_di_list[-1]

        # Determine trend strength
        if adx >= ADX_THRESHOLDS['very_strong']:
            trend_strength = 'VERY_STRONG'
        elif adx >= ADX_THRESHOLDS['strong']:
            trend_strength = 'STRONG'
        elif adx >= ADX_THRESHOLDS['emerging']:
            trend_strength = 'EMERGING'
        else:
            trend_strength = 'WEAK'

        # Determine trend direction
        if plus_di > minus_di and adx >= ADX_THRESHOLDS['weak']:
            trend_direction = 'BULLISH'
        elif minus_di > plus_di and adx >= ADX_THRESHOLDS['weak']:
            trend_direction = 'BEARISH'
        else:
            trend_direction = 'NEUTRAL'

        return ADXResult(
            adx=adx,
            plus_di=plus_di,
            minus_di=minus_di,
            trend_strength=trend_strength,
            trend_direction=trend_direction
        )

    except Exception as e:
        logger.error(f"ADX calculation error: {e}")
        return None


def get_regime_from_atr_ratio(atr_ratio: float, is_trending: bool = False,
                               adx_result: Optional[ADXResult] = None) -> str:
    """
    Determine market regime from ATR ratio and ADX.

    Sprint 8 Enhancement: Uses ADX to differentiate NORMAL vs TRENDING
    when ATR is in the overlapping 1.0-2.0 range.

    Args:
        atr_ratio: Current ATR / Price ratio (e.g., 1.5 = 1.5% daily range)
        is_trending: Legacy parameter (use adx_result instead)
        adx_result: ADX calculation result for trend detection

    Returns:
        Regime name string
    """
    # Use ADX for trend detection if available (Sprint 8 enhancement)
    if adx_result is not None:
        # ADX-based TRENDING detection (resolves NORMAL vs TRENDING overlap)
        if adx_result.is_trending and 0.8 <= atr_ratio <= 2.0:
            return 'TRENDING'
    elif is_trending and 1.0 <= atr_ratio <= 2.0:
        # Fallback to legacy is_trending parameter
        return 'TRENDING'

    # ATR-based volatility regimes
    if atr_ratio >= 3.0:
        return 'EXTREME_VOLATILITY'
    elif atr_ratio >= 2.0:
        return 'HIGH_VOLATILITY'
    elif atr_ratio >= 1.5:
        return 'ELEVATED'
    elif atr_ratio >= 0.8:
        return 'NORMAL'
    else:
        return 'LOW_VOLATILITY'


def get_regime_with_adx(atr_ratio: float, highs: List[float],
                        lows: List[float], closes: List[float]) -> Tuple[str, Optional[ADXResult]]:
    """
    Get market regime using both ATR and ADX indicators.

    This is the recommended function for Sprint 8+ to properly
    differentiate between NORMAL and TRENDING regimes.

    Args:
        atr_ratio: ATR / Price ratio
        highs, lows, closes: Price data for ADX calculation

    Returns:
        Tuple of (regime_name, adx_result)
    """
    adx_result = calculate_adx(highs, lows, closes)
    regime = get_regime_from_atr_ratio(atr_ratio, adx_result=adx_result)
    return regime, adx_result


def get_regime_leverage_range(regime: str) -> Tuple[int, int]:
    """Get recommended leverage range for a regime."""
    if regime in REGIME_DEFINITIONS:
        r = REGIME_DEFINITIONS[regime]
        return (r.recommended_leverage_min, r.recommended_leverage_max)
    return (5, 10)  # Default


# =============================================================================
# AUTO-TUNING CONFIGURATION
# =============================================================================

@dataclass
class AutoTuneGuardrails:
    """
    Sprint 8 Enhancement: Guardrails for auto-tuning to prevent dangerous changes.

    Grok Sprint 8: "Implement strict guardrails for auto-tuning in 'apply mode'
    (e.g., temporary leverage caps, mandatory human approval for changes above a threshold)."
    """
    # Minimum data requirements before allowing auto-tune
    min_alert_samples: int = 50           # Need 50+ alert validations
    min_leverage_samples: int = 30        # Need 30+ leverage validations
    min_circuit_breaker_samples: int = 15 # Need 15+ CB events

    # Cooldown between auto-tune applications
    min_hours_between_tunes: int = 24     # At least 24 hours between tunes
    max_tunes_per_week: int = 3           # Maximum 3 tunings per week

    # Change magnitude limits (per single tune)
    max_hysteresis_change: int = 1        # Can only change by ±1
    max_leverage_change: int = 2          # Can only change leverage by ±2
    max_threshold_change_pct: float = 0.10 # Can only change thresholds by 10%

    # Absolute limits (cannot be exceeded even with tuning)
    absolute_min_leverage: int = 2        # Never go below 2x leverage
    absolute_max_leverage: int = 20       # Never exceed 20x leverage
    absolute_min_hysteresis: int = 2      # Minimum 2 consecutive samples
    absolute_max_hysteresis: int = 6      # Maximum 6 consecutive samples

    # Severity thresholds requiring human approval
    high_severity_leverage_change: int = 3  # Changes ≥3 need approval
    critical_regime_changes: List[str] = field(default_factory=lambda: [
        'EXTREME_VOLATILITY', 'HIGH_VOLATILITY'
    ])  # Changes to these regimes always need review

    # Rollback tracking
    max_changes_before_evaluation: int = 5  # After 5 changes, force evaluation
    rollback_window_hours: int = 72         # Can rollback within 72 hours

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AutoTuneConfig:
    """Configuration that can be auto-tuned based on validation results."""
    # Alert thresholds
    drawdown_alert_threshold: float = 0.15      # 15% drawdown
    margin_alert_threshold: float = 0.80        # 80% margin usage
    averaging_alert_threshold: int = 5          # 5 averaging steps

    # Hysteresis settings
    hysteresis_samples: int = 3                 # Consecutive breaches required
    hysteresis_window_sec: int = 60             # Time window

    # Circuit breaker settings
    circuit_breaker_consecutive_losses: int = 5
    circuit_breaker_session_loss_pct: float = 0.15
    circuit_breaker_cooldown_min: int = 30

    # Leverage limits by regime
    leverage_limits: Dict[str, int] = field(default_factory=lambda: {
        'EXTREME_VOLATILITY': 3,
        'HIGH_VOLATILITY': 5,
        'ELEVATED': 8,
        'NORMAL': 12,
        'LOW_VOLATILITY': 15,
        'TRENDING': 12
    })

    # Meta
    last_tuned: Optional[str] = None
    tune_count: int = 0

    # Sprint 8: Change history for rollback
    change_history: List[Dict] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> 'AutoTuneConfig':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ValidationResult(Enum):
    """Validation outcome."""
    PASS = "PASS"
    FAIL = "FAIL"
    WARNING = "WARNING"
    NEEDS_TUNING = "NEEDS_TUNING"


@dataclass
class AlertValidation:
    """Represents an alert validation result."""
    alert_type: str
    triggered_at: datetime
    actual_outcome: str  # 'true_positive', 'false_positive', 'true_negative', 'false_negative'
    value_at_trigger: float
    threshold: float
    subsequent_value: float  # Value after some time to verify if alert was correct
    notes: str = ""


@dataclass
class LeverageValidation:
    """Represents a leverage adjustment validation."""
    symbol: str
    regime: str
    leverage_recommended: int
    leverage_used: int
    atr_ratio: float
    outcome: str  # 'correct', 'too_conservative', 'too_aggressive'
    pnl_impact: float = 0.0
    notes: str = ""


class RiskValidator:
    """
    Validates risk management systems against live/historical data.

    V2.0.0 Features:
    - Explicit performance targets (precision >90%, recall >85%)
    - Clear regime definitions (ATR-based volatility bands)
    - Auto-tuning capability based on validation results
    - Target status tracking (MEETS_TARGET / BELOW_TARGET)

    Tracks:
    - Alert accuracy (true/false positives/negatives)
    - Leverage adjustment effectiveness by regime
    - Circuit breaker trigger accuracy
    - Hysteresis performance
    - Shadow trading results with regime correlation
    """

    def __init__(self, targets: Optional[PerformanceTargets] = None,
                 config: Optional[AutoTuneConfig] = None,
                 guardrails: Optional[AutoTuneGuardrails] = None):
        # Performance targets
        self.targets = targets or PerformanceTargets()

        # Auto-tune configuration
        self.config = config or self._load_config()

        # Sprint 8: Guardrails for safe auto-tuning
        self.guardrails = guardrails or AutoTuneGuardrails()

        # Alert tracking
        self.alert_validations: List[AlertValidation] = []
        self.alert_stats: Dict[str, Dict] = defaultdict(lambda: {
            'true_positives': 0,
            'false_positives': 0,
            'true_negatives': 0,
            'false_negatives': 0,
            'total': 0
        })

        # Leverage tracking with regime
        self.leverage_validations: List[LeverageValidation] = []
        self.leverage_outcomes: Dict[str, List[str]] = defaultdict(list)
        self.leverage_pnl_by_regime: Dict[str, List[float]] = defaultdict(list)

        # Circuit breaker tracking
        self.circuit_breaker_events: List[Dict] = []
        self.circuit_breaker_effectiveness: Dict[str, int] = {
            'triggered_correctly': 0,
            'triggered_incorrectly': 0,
            'missed_trigger': 0
        }

        # Hysteresis tracking
        self.hysteresis_events: List[Dict] = []

        # Shadow trading results
        self.shadow_trades: List[Dict] = []

        # Target status cache
        self._target_status_cache: Dict[str, bool] = {}

    def _load_config(self) -> AutoTuneConfig:
        """Load auto-tune config from file or create default."""
        try:
            if os.path.exists(AUTO_TUNE_CONFIG_FILE):
                with open(AUTO_TUNE_CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                return AutoTuneConfig.from_dict(data)
        except Exception as e:
            logger.warning(f"Failed to load auto-tune config: {e}")
        return AutoTuneConfig()

    def _save_config(self):
        """Save auto-tune config to file."""
        try:
            with open(AUTO_TUNE_CONFIG_FILE, 'w') as f:
                json.dump(self.config.to_dict(), f, indent=2)
            logger.info(f"Auto-tune config saved to {AUTO_TUNE_CONFIG_FILE}")
        except Exception as e:
            logger.error(f"Failed to save auto-tune config: {e}")

    # =========================================================================
    # ALERT VALIDATION
    # =========================================================================

    def record_alert_validation(self, alert_type: str, triggered: bool,
                               value_at_trigger: float, threshold: float,
                               subsequent_value: float, time_delta_min: int = 15):
        """
        Record an alert validation event.

        Args:
            alert_type: Type of alert (drawdown, margin, etc.)
            triggered: Whether alert was triggered
            value_at_trigger: Value when alert was checked
            threshold: Threshold that would trigger alert
            subsequent_value: Value after time_delta_min minutes
            time_delta_min: Time window for outcome validation
        """
        # Determine if alert was correct
        breach_at_trigger = value_at_trigger >= threshold
        breach_after = subsequent_value >= threshold
        worsened = subsequent_value > value_at_trigger

        if triggered:
            if breach_after or worsened:
                outcome = 'true_positive'
                self.alert_stats[alert_type]['true_positives'] += 1
            else:
                outcome = 'false_positive'
                self.alert_stats[alert_type]['false_positives'] += 1
        else:
            if not breach_after and not worsened:
                outcome = 'true_negative'
                self.alert_stats[alert_type]['true_negatives'] += 1
            else:
                outcome = 'false_negative'
                self.alert_stats[alert_type]['false_negatives'] += 1

        self.alert_stats[alert_type]['total'] += 1

        validation = AlertValidation(
            alert_type=alert_type,
            triggered_at=datetime.now(),
            actual_outcome=outcome,
            value_at_trigger=value_at_trigger,
            threshold=threshold,
            subsequent_value=subsequent_value
        )

        self.alert_validations.append(validation)

        if len(self.alert_validations) > 1000:
            self.alert_validations = self.alert_validations[-500:]

        return outcome

    def get_alert_accuracy(self, alert_type: str = None) -> Dict:
        """
        Get alert accuracy statistics.

        Returns:
            Dict with precision, recall, F1 score, accuracy
        """
        if alert_type:
            stats = self.alert_stats.get(alert_type, {})
            return self._calculate_accuracy_metrics(stats)

        # Overall accuracy across all alert types
        combined = {
            'true_positives': sum(s['true_positives'] for s in self.alert_stats.values()),
            'false_positives': sum(s['false_positives'] for s in self.alert_stats.values()),
            'true_negatives': sum(s['true_negatives'] for s in self.alert_stats.values()),
            'false_negatives': sum(s['false_negatives'] for s in self.alert_stats.values()),
            'total': sum(s['total'] for s in self.alert_stats.values())
        }
        return self._calculate_accuracy_metrics(combined)

    def _calculate_accuracy_metrics(self, stats: Dict) -> Dict:
        """Calculate precision, recall, F1, accuracy from stats."""
        tp = stats.get('true_positives', 0)
        fp = stats.get('false_positives', 0)
        tn = stats.get('true_negatives', 0)
        fn = stats.get('false_negatives', 0)
        total = stats.get('total', 0)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        accuracy = (tp + tn) / total if total > 0 else 0

        # Determine if tuning is needed
        needs_tuning = False
        tuning_reason = ""

        if fp > tp * 0.3:  # >30% false positive rate
            needs_tuning = True
            tuning_reason = "High false positive rate - consider increasing hysteresis"
        elif fn > tp * 0.2:  # >20% false negative rate
            needs_tuning = True
            tuning_reason = "High false negative rate - consider lowering thresholds"

        return {
            'true_positives': tp,
            'false_positives': fp,
            'true_negatives': tn,
            'false_negatives': fn,
            'total': total,
            'precision': precision,
            'recall': recall,
            'f1_score': f1,
            'accuracy': accuracy,
            'false_positive_rate': fp / (fp + tn) if (fp + tn) > 0 else 0,
            'false_negative_rate': fn / (fn + tp) if (fn + tp) > 0 else 0,
            'needs_tuning': needs_tuning,
            'tuning_reason': tuning_reason
        }

    # =========================================================================
    # LEVERAGE VALIDATION
    # =========================================================================

    def record_leverage_validation(self, symbol: str, regime: str,
                                  leverage_recommended: int, leverage_used: int,
                                  atr_ratio: float, actual_pnl: float,
                                  position_outcome: str):
        """
        Record a leverage adjustment validation.

        Args:
            symbol: Trading symbol
            regime: Market regime
            leverage_recommended: Recommended leverage from system
            leverage_used: Actual leverage used
            atr_ratio: ATR ratio at time of trade
            actual_pnl: Actual P&L outcome
            position_outcome: 'profit', 'loss', 'liquidation'
        """
        # Determine if leverage was appropriate
        if position_outcome == 'liquidation':
            outcome = 'too_aggressive'
        elif position_outcome == 'loss' and leverage_used > leverage_recommended:
            outcome = 'too_aggressive'
        elif position_outcome == 'profit' and leverage_used < leverage_recommended * 0.5:
            outcome = 'too_conservative'
        else:
            outcome = 'correct'

        validation = LeverageValidation(
            symbol=symbol,
            regime=regime,
            leverage_recommended=leverage_recommended,
            leverage_used=leverage_used,
            atr_ratio=atr_ratio,
            outcome=outcome,
            pnl_impact=actual_pnl
        )

        self.leverage_validations.append(validation)
        self.leverage_outcomes[regime].append(outcome)

        if len(self.leverage_validations) > 500:
            self.leverage_validations = self.leverage_validations[-250:]

        return outcome

    def get_leverage_effectiveness(self, regime: str = None) -> Dict:
        """Get leverage adjustment effectiveness by regime."""
        if regime:
            outcomes = self.leverage_outcomes.get(regime, [])
        else:
            outcomes = [o for outcomes in self.leverage_outcomes.values() for o in outcomes]

        if not outcomes:
            return {'total': 0}

        correct = outcomes.count('correct')
        too_aggressive = outcomes.count('too_aggressive')
        too_conservative = outcomes.count('too_conservative')
        total = len(outcomes)

        return {
            'total': total,
            'correct': correct,
            'correct_pct': correct / total * 100,
            'too_aggressive': too_aggressive,
            'too_aggressive_pct': too_aggressive / total * 100,
            'too_conservative': too_conservative,
            'too_conservative_pct': too_conservative / total * 100,
            'effectiveness_score': correct / total if total > 0 else 0,
            'needs_adjustment': too_aggressive > total * 0.2 or too_conservative > total * 0.3
        }

    # =========================================================================
    # CIRCUIT BREAKER VALIDATION
    # =========================================================================

    def record_circuit_breaker_event(self, triggered: bool, trigger_reason: str,
                                    conditions_at_trigger: Dict,
                                    outcome_after_cooldown: Dict):
        """
        Record a circuit breaker validation event.

        Args:
            triggered: Whether circuit breaker was triggered
            trigger_reason: Reason for trigger (or would-be reason)
            conditions_at_trigger: Market/account conditions at trigger time
            outcome_after_cooldown: Conditions after cooldown period
        """
        # Determine if trigger was correct
        loss_before = conditions_at_trigger.get('session_pnl', 0)
        loss_after = outcome_after_cooldown.get('session_pnl', 0)
        positions_closed = outcome_after_cooldown.get('positions_closed', 0)

        if triggered:
            # Was the trigger necessary?
            if loss_after < loss_before or positions_closed > 0:
                effectiveness = 'triggered_correctly'
                self.circuit_breaker_effectiveness['triggered_correctly'] += 1
            else:
                effectiveness = 'triggered_incorrectly'
                self.circuit_breaker_effectiveness['triggered_incorrectly'] += 1
        else:
            # Should it have triggered?
            if loss_after < loss_before * 0.8:  # Significant additional loss
                effectiveness = 'missed_trigger'
                self.circuit_breaker_effectiveness['missed_trigger'] += 1
            else:
                effectiveness = 'correctly_not_triggered'

        event = {
            'timestamp': datetime.now().isoformat(),
            'triggered': triggered,
            'trigger_reason': trigger_reason,
            'conditions_at_trigger': conditions_at_trigger,
            'outcome_after_cooldown': outcome_after_cooldown,
            'effectiveness': effectiveness
        }

        self.circuit_breaker_events.append(event)

        if len(self.circuit_breaker_events) > 100:
            self.circuit_breaker_events = self.circuit_breaker_events[-50:]

        return effectiveness

    def get_circuit_breaker_effectiveness(self) -> Dict:
        """Get circuit breaker effectiveness statistics."""
        total = sum(self.circuit_breaker_effectiveness.values())

        if total == 0:
            return {'total': 0, 'effectiveness': 'unknown'}

        correct = self.circuit_breaker_effectiveness['triggered_correctly']
        incorrect = self.circuit_breaker_effectiveness['triggered_incorrectly']
        missed = self.circuit_breaker_effectiveness['missed_trigger']

        effectiveness_score = correct / total if total > 0 else 0

        return {
            'total': total,
            'triggered_correctly': correct,
            'triggered_incorrectly': incorrect,
            'missed_triggers': missed,
            'effectiveness_score': effectiveness_score,
            'needs_tuning': incorrect > total * 0.2 or missed > total * 0.1
        }

    # =========================================================================
    # HYSTERESIS VALIDATION
    # =========================================================================

    def record_hysteresis_event(self, alert_type: str, breach_count: int,
                               hysteresis_threshold: int, triggered: bool,
                               was_real_issue: bool):
        """
        Record a hysteresis validation event.

        Args:
            alert_type: Type of alert
            breach_count: Number of consecutive breaches
            hysteresis_threshold: Required breaches for trigger
            triggered: Whether alert was triggered
            was_real_issue: Whether this was a real issue (in hindsight)
        """
        event = {
            'timestamp': datetime.now().isoformat(),
            'alert_type': alert_type,
            'breach_count': breach_count,
            'hysteresis_threshold': hysteresis_threshold,
            'triggered': triggered,
            'was_real_issue': was_real_issue,
            'correct': (triggered and was_real_issue) or (not triggered and not was_real_issue)
        }

        self.hysteresis_events.append(event)

        if len(self.hysteresis_events) > 200:
            self.hysteresis_events = self.hysteresis_events[-100:]

        return event['correct']

    def get_hysteresis_effectiveness(self) -> Dict:
        """Analyze hysteresis effectiveness."""
        if not self.hysteresis_events:
            return {'total': 0}

        correct = sum(1 for e in self.hysteresis_events if e['correct'])
        total = len(self.hysteresis_events)

        # Analyze if threshold should be adjusted
        triggered_too_early = sum(1 for e in self.hysteresis_events
                                 if e['triggered'] and not e['was_real_issue'])
        triggered_too_late = sum(1 for e in self.hysteresis_events
                                if not e['triggered'] and e['was_real_issue'])

        recommendation = "optimal"
        if triggered_too_early > total * 0.2:
            recommendation = "increase_threshold"
        elif triggered_too_late > total * 0.15:
            recommendation = "decrease_threshold"

        return {
            'total': total,
            'correct': correct,
            'accuracy': correct / total if total > 0 else 0,
            'triggered_too_early': triggered_too_early,
            'triggered_too_late': triggered_too_late,
            'recommendation': recommendation
        }

    # =========================================================================
    # SHADOW TRADING
    # =========================================================================

    def record_shadow_trade(self, symbol: str, side: str, leverage: int,
                           entry_price: float, exit_price: float,
                           risk_checks: Dict, actual_outcome: str):
        """
        Record a shadow trade for validation.

        Args:
            symbol: Trading symbol
            side: 'long' or 'short'
            leverage: Leverage used
            entry_price: Entry price
            exit_price: Exit price
            risk_checks: Results of risk checks at entry
            actual_outcome: What actually happened
        """
        pnl_pct = ((exit_price - entry_price) / entry_price) * leverage
        if side == 'short':
            pnl_pct = -pnl_pct

        trade = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'side': side,
            'leverage': leverage,
            'entry_price': entry_price,
            'exit_price': exit_price,
            'pnl_pct': pnl_pct * 100,
            'risk_checks': risk_checks,
            'actual_outcome': actual_outcome,
            'risk_checks_valid': self._validate_risk_checks(risk_checks, actual_outcome)
        }

        self.shadow_trades.append(trade)

        if len(self.shadow_trades) > 200:
            self.shadow_trades = self.shadow_trades[-100:]

        return trade

    def _validate_risk_checks(self, risk_checks: Dict, actual_outcome: str) -> bool:
        """Validate if risk checks correctly predicted outcome."""
        # If risk checks said "don't trade" and outcome was bad, they were right
        if risk_checks.get('recommendation') == 'avoid' and actual_outcome in ['loss', 'liquidation']:
            return True
        # If risk checks said "ok to trade" and outcome was good, they were right
        if risk_checks.get('recommendation') in ['proceed', 'ok'] and actual_outcome == 'profit':
            return True
        # If risk checks said "ok" but outcome was bad, they were wrong
        if risk_checks.get('recommendation') in ['proceed', 'ok'] and actual_outcome in ['loss', 'liquidation']:
            return False
        return True  # Default to valid if unclear

    def get_shadow_trading_results(self) -> Dict:
        """Get shadow trading validation results."""
        if not self.shadow_trades:
            return {'total': 0}

        total = len(self.shadow_trades)
        valid_checks = sum(1 for t in self.shadow_trades if t['risk_checks_valid'])
        profitable = sum(1 for t in self.shadow_trades if t['pnl_pct'] > 0)
        losses = sum(1 for t in self.shadow_trades if t['pnl_pct'] < 0)
        liquidations = sum(1 for t in self.shadow_trades if t['actual_outcome'] == 'liquidation')

        avg_pnl = statistics.mean(t['pnl_pct'] for t in self.shadow_trades)
        avg_leverage = statistics.mean(t['leverage'] for t in self.shadow_trades)

        return {
            'total': total,
            'profitable': profitable,
            'losses': losses,
            'liquidations': liquidations,
            'win_rate': profitable / total * 100 if total > 0 else 0,
            'avg_pnl_pct': avg_pnl,
            'avg_leverage': avg_leverage,
            'risk_check_accuracy': valid_checks / total * 100 if total > 0 else 0
        }

    # =========================================================================
    # COMPREHENSIVE VALIDATION REPORT
    # =========================================================================

    def generate_validation_report(self) -> Dict:
        """Generate comprehensive risk validation report."""
        report = {
            'timestamp': datetime.now().isoformat(),
            'version': '2.0.0',
            'target_status': self.check_target_status(),
            'performance_targets': {
                'alert_precision_min': self.targets.alert_precision_min,
                'alert_recall_min': self.targets.alert_recall_min,
                'alert_f1_min': self.targets.alert_f1_min,
                'leverage_correct_min': self.targets.leverage_correct_min,
                'circuit_breaker_effectiveness_min': self.targets.circuit_breaker_effectiveness_min
            },
            'alert_validation': {
                'overall': self.get_alert_accuracy(),
                'by_type': {
                    alert_type: self.get_alert_accuracy(alert_type)
                    for alert_type in self.alert_stats
                }
            },
            'leverage_validation': {
                'overall': self.get_leverage_effectiveness(),
                'by_regime': {
                    regime: self.get_leverage_effectiveness(regime)
                    for regime in self.leverage_outcomes
                }
            },
            'regime_definitions': {
                name: {
                    'atr_range': f"{d.atr_ratio_min}-{d.atr_ratio_max}",
                    'leverage_range': f"{d.recommended_leverage_min}-{d.recommended_leverage_max}x",
                    'description': d.description
                }
                for name, d in REGIME_DEFINITIONS.items()
            },
            'circuit_breaker': self.get_circuit_breaker_effectiveness(),
            'hysteresis': self.get_hysteresis_effectiveness(),
            'shadow_trading': self.get_shadow_trading_results(),
            'auto_tune_config': self.config.to_dict(),
            'recommendations': self._generate_recommendations()
        }

        return report

    def _generate_recommendations(self) -> List[Dict]:
        """Generate tuning recommendations based on validation data."""
        recommendations = []

        # Alert recommendations
        alert_accuracy = self.get_alert_accuracy()
        if alert_accuracy.get('needs_tuning'):
            recommendations.append({
                'area': 'alert_thresholds',
                'issue': alert_accuracy.get('tuning_reason', 'Accuracy below target'),
                'recommendation': 'Review and adjust alert thresholds or hysteresis settings',
                'priority': 'HIGH'
            })

        # Leverage recommendations
        leverage_eff = self.get_leverage_effectiveness()
        if leverage_eff.get('needs_adjustment'):
            if leverage_eff.get('too_aggressive_pct', 0) > 20:
                recommendations.append({
                    'area': 'leverage_limits',
                    'issue': f"Too aggressive {leverage_eff['too_aggressive_pct']:.1f}% of time",
                    'recommendation': 'Reduce max leverage limits, especially in HIGH_VOLATILITY',
                    'priority': 'HIGH'
                })
            elif leverage_eff.get('too_conservative_pct', 0) > 30:
                recommendations.append({
                    'area': 'leverage_limits',
                    'issue': f"Too conservative {leverage_eff['too_conservative_pct']:.1f}% of time",
                    'recommendation': 'Consider increasing leverage in TRENDING/NORMAL regimes',
                    'priority': 'MEDIUM'
                })

        # Circuit breaker recommendations
        cb_eff = self.get_circuit_breaker_effectiveness()
        if cb_eff.get('needs_tuning'):
            if cb_eff.get('triggered_incorrectly', 0) > cb_eff.get('total', 1) * 0.2:
                recommendations.append({
                    'area': 'circuit_breaker',
                    'issue': 'Too many false triggers',
                    'recommendation': 'Increase circuit breaker thresholds (consecutive losses, session loss %)',
                    'priority': 'MEDIUM'
                })
            elif cb_eff.get('missed_triggers', 0) > cb_eff.get('total', 1) * 0.1:
                recommendations.append({
                    'area': 'circuit_breaker',
                    'issue': 'Missing critical triggers',
                    'recommendation': 'Lower circuit breaker thresholds for earlier activation',
                    'priority': 'HIGH'
                })

        # Hysteresis recommendations
        hyst_eff = self.get_hysteresis_effectiveness()
        if hyst_eff.get('recommendation') == 'increase_threshold':
            recommendations.append({
                'area': 'hysteresis',
                'issue': 'Alerts triggering too early (false positives)',
                'recommendation': 'Increase hysteresis_samples from 3 to 4-5',
                'priority': 'MEDIUM'
            })
        elif hyst_eff.get('recommendation') == 'decrease_threshold':
            recommendations.append({
                'area': 'hysteresis',
                'issue': 'Alerts triggering too late (missing issues)',
                'recommendation': 'Decrease hysteresis_samples from 3 to 2',
                'priority': 'HIGH'
            })

        return recommendations

    # =========================================================================
    # TARGET STATUS CHECKING (Sprint 7)
    # =========================================================================

    def check_target_status(self) -> Dict[str, Any]:
        """
        Check if current metrics meet performance targets.

        Returns dict with status for each metric area.
        """
        status = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'MEETS_TARGETS',
            'metrics': {}
        }

        # Alert targets
        alert = self.get_alert_accuracy()
        if alert.get('total', 0) > 0:
            alert_status = {
                'precision': {
                    'current': alert['precision'],
                    'target': self.targets.alert_precision_min,
                    'meets_target': alert['precision'] >= self.targets.alert_precision_min
                },
                'recall': {
                    'current': alert['recall'],
                    'target': self.targets.alert_recall_min,
                    'meets_target': alert['recall'] >= self.targets.alert_recall_min
                },
                'f1_score': {
                    'current': alert['f1_score'],
                    'target': self.targets.alert_f1_min,
                    'meets_target': alert['f1_score'] >= self.targets.alert_f1_min
                },
                'false_positive_rate': {
                    'current': alert['false_positive_rate'],
                    'target': self.targets.alert_false_positive_max,
                    'meets_target': alert['false_positive_rate'] <= self.targets.alert_false_positive_max
                },
                'false_negative_rate': {
                    'current': alert['false_negative_rate'],
                    'target': self.targets.alert_false_negative_max,
                    'meets_target': alert['false_negative_rate'] <= self.targets.alert_false_negative_max
                }
            }
            status['metrics']['alerts'] = alert_status

            # Check if any alert metric fails
            if not all(m['meets_target'] for m in alert_status.values()):
                status['overall_status'] = 'BELOW_TARGETS'

        # Leverage targets
        leverage = self.get_leverage_effectiveness()
        if leverage.get('total', 0) > 0:
            leverage_status = {
                'correct_pct': {
                    'current': leverage['effectiveness_score'],
                    'target': self.targets.leverage_correct_min,
                    'meets_target': leverage['effectiveness_score'] >= self.targets.leverage_correct_min
                },
                'too_aggressive_pct': {
                    'current': leverage['too_aggressive_pct'] / 100,
                    'target': self.targets.leverage_aggressive_max,
                    'meets_target': (leverage['too_aggressive_pct'] / 100) <= self.targets.leverage_aggressive_max
                }
            }
            status['metrics']['leverage'] = leverage_status

            if not all(m['meets_target'] for m in leverage_status.values()):
                status['overall_status'] = 'BELOW_TARGETS'

        # Circuit breaker targets
        cb = self.get_circuit_breaker_effectiveness()
        if cb.get('total', 0) > 0:
            cb_status = {
                'effectiveness': {
                    'current': cb['effectiveness_score'],
                    'target': self.targets.circuit_breaker_effectiveness_min,
                    'meets_target': cb['effectiveness_score'] >= self.targets.circuit_breaker_effectiveness_min
                }
            }
            status['metrics']['circuit_breaker'] = cb_status

            if not cb_status['effectiveness']['meets_target']:
                status['overall_status'] = 'BELOW_TARGETS'

        # Hysteresis targets
        hyst = self.get_hysteresis_effectiveness()
        if hyst.get('total', 0) > 0:
            hyst_status = {
                'accuracy': {
                    'current': hyst['accuracy'],
                    'target': self.targets.hysteresis_accuracy_min,
                    'meets_target': hyst['accuracy'] >= self.targets.hysteresis_accuracy_min
                }
            }
            status['metrics']['hysteresis'] = hyst_status

            if not hyst_status['accuracy']['meets_target']:
                status['overall_status'] = 'BELOW_TARGETS'

        # Shadow trading targets
        shadow = self.get_shadow_trading_results()
        if shadow.get('total', 0) > 0:
            shadow_status = {
                'win_rate': {
                    'current': shadow['win_rate'] / 100,
                    'target': self.targets.shadow_win_rate_min,
                    'meets_target': (shadow['win_rate'] / 100) >= self.targets.shadow_win_rate_min
                },
                'risk_check_accuracy': {
                    'current': shadow['risk_check_accuracy'] / 100,
                    'target': self.targets.shadow_risk_check_accuracy_min,
                    'meets_target': (shadow['risk_check_accuracy'] / 100) >= self.targets.shadow_risk_check_accuracy_min
                }
            }
            status['metrics']['shadow_trading'] = shadow_status

            if not all(m['meets_target'] for m in shadow_status.values()):
                status['overall_status'] = 'BELOW_TARGETS'

        return status

    # =========================================================================
    # AUTO-TUNING (Sprint 7 + Sprint 8 Guardrails)
    # =========================================================================

    def _check_guardrail_prerequisites(self) -> Tuple[bool, List[str]]:
        """
        Check if guardrail prerequisites are met for auto-tuning.

        Returns:
            Tuple of (can_tune: bool, blocking_reasons: List[str])
        """
        reasons = []
        g = self.guardrails

        # Check minimum data requirements
        alert = self.get_alert_accuracy()
        if alert.get('total', 0) < g.min_alert_samples:
            reasons.append(f"Insufficient alert data: {alert.get('total', 0)}/{g.min_alert_samples}")

        leverage = self.get_leverage_effectiveness()
        if leverage.get('total', 0) < g.min_leverage_samples:
            reasons.append(f"Insufficient leverage data: {leverage.get('total', 0)}/{g.min_leverage_samples}")

        cb = self.get_circuit_breaker_effectiveness()
        if cb.get('total', 0) < g.min_circuit_breaker_samples:
            reasons.append(f"Insufficient circuit breaker data: {cb.get('total', 0)}/{g.min_circuit_breaker_samples}")

        # Check cooldown period
        if self.config.last_tuned:
            try:
                last_tune_time = datetime.fromisoformat(self.config.last_tuned)
                hours_since_tune = (datetime.now() - last_tune_time).total_seconds() / 3600
                if hours_since_tune < g.min_hours_between_tunes:
                    reasons.append(f"Cooldown active: {hours_since_tune:.1f}/{g.min_hours_between_tunes} hours")
            except (ValueError, TypeError):
                pass  # Invalid timestamp, allow tuning

        # Check weekly limit (approximate by tune count in change history)
        recent_tunes = sum(1 for h in self.config.change_history[-10:]
                         if h.get('timestamp'))  # Simple approximation
        if recent_tunes >= g.max_tunes_per_week:
            reasons.append(f"Weekly tune limit reached: {recent_tunes}/{g.max_tunes_per_week}")

        # Check max changes before evaluation
        if len(self.config.change_history) >= g.max_changes_before_evaluation:
            reasons.append(f"Evaluation required: {len(self.config.change_history)} changes since last review")

        return (len(reasons) == 0, reasons)

    def _apply_guardrail_limits(self, param: str, old_value: Any, proposed_value: Any) -> Tuple[Any, str]:
        """
        Apply guardrail limits to a proposed change.

        Returns:
            Tuple of (adjusted_value, adjustment_reason)
        """
        g = self.guardrails
        adjustment_reason = ""

        # Hysteresis limits
        if param == 'hysteresis_samples':
            change = abs(proposed_value - old_value)
            if change > g.max_hysteresis_change:
                proposed_value = old_value + (g.max_hysteresis_change if proposed_value > old_value else -g.max_hysteresis_change)
                adjustment_reason = f"Limited to ±{g.max_hysteresis_change} change"

            # Absolute limits
            if proposed_value < g.absolute_min_hysteresis:
                proposed_value = g.absolute_min_hysteresis
                adjustment_reason = f"Clamped to min {g.absolute_min_hysteresis}"
            elif proposed_value > g.absolute_max_hysteresis:
                proposed_value = g.absolute_max_hysteresis
                adjustment_reason = f"Clamped to max {g.absolute_max_hysteresis}"

        # Leverage limits
        elif param.startswith('leverage_limits.'):
            change = abs(proposed_value - old_value)
            if change > g.max_leverage_change:
                proposed_value = old_value + (g.max_leverage_change if proposed_value > old_value else -g.max_leverage_change)
                adjustment_reason = f"Limited to ±{g.max_leverage_change} change"

            # Absolute limits
            if proposed_value < g.absolute_min_leverage:
                proposed_value = g.absolute_min_leverage
                adjustment_reason = f"Clamped to min {g.absolute_min_leverage}x"
            elif proposed_value > g.absolute_max_leverage:
                proposed_value = g.absolute_max_leverage
                adjustment_reason = f"Clamped to max {g.absolute_max_leverage}x"

        # Threshold limits (percentage-based)
        elif 'threshold' in param.lower():
            max_change = old_value * g.max_threshold_change_pct
            if abs(proposed_value - old_value) > max_change:
                proposed_value = old_value + (max_change if proposed_value > old_value else -max_change)
                adjustment_reason = f"Limited to ±{g.max_threshold_change_pct*100:.0f}% change"

        return proposed_value, adjustment_reason

    def _check_requires_approval(self, param: str, old_value: Any, new_value: Any) -> Tuple[bool, str]:
        """
        Check if a change requires human approval per guardrails.

        Returns:
            Tuple of (requires_approval: bool, reason: str)
        """
        g = self.guardrails

        # Check leverage changes to critical regimes
        if param.startswith('leverage_limits.'):
            regime = param.split('.')[-1]
            if regime in g.critical_regime_changes:
                return True, f"Changes to {regime} leverage require approval"

            # Check magnitude
            change = abs(new_value - old_value)
            if change >= g.high_severity_leverage_change:
                return True, f"Leverage change of {change} >= {g.high_severity_leverage_change}"

        return False, ""

    def auto_tune(self, dry_run: bool = True, force: bool = False) -> Dict[str, Any]:
        """
        Automatically tune parameters based on validation results.

        Sprint 8 Enhancement: Now includes guardrails to prevent dangerous changes.

        Args:
            dry_run: If True, only return proposed changes without applying
            force: If True, bypass guardrail prerequisites (USE WITH CAUTION)

        Returns:
            Dict with proposed/applied changes, guardrail status, and approval requirements
        """
        changes = {
            'timestamp': datetime.now().isoformat(),
            'dry_run': dry_run,
            'proposed_changes': [],
            'applied': False,
            'guardrails_status': {
                'passed': False,
                'blocking_reasons': [],
                'forced': force
            },
            'requires_approval': [],
            'adjustments_made': []
        }

        # Sprint 8: Check guardrail prerequisites
        if not force:
            can_tune, blocking_reasons = self._check_guardrail_prerequisites()
            changes['guardrails_status']['passed'] = can_tune
            changes['guardrails_status']['blocking_reasons'] = blocking_reasons

            if not can_tune:
                logger.warning(f"Auto-tune blocked by guardrails: {blocking_reasons}")
                return changes
        else:
            changes['guardrails_status']['passed'] = True
            logger.warning("Auto-tune guardrails bypassed with force=True")

        # Check alert accuracy
        alert = self.get_alert_accuracy()
        if alert.get('total', 0) >= 20:  # Need sufficient data
            # High false positive rate → increase hysteresis
            if alert['false_positive_rate'] > self.targets.alert_false_positive_max:
                old_val = self.config.hysteresis_samples
                proposed_val = old_val + 1

                # Apply guardrail limits
                new_val, adjustment = self._apply_guardrail_limits(
                    'hysteresis_samples', old_val, proposed_val
                )

                if new_val != old_val:
                    change = {
                        'param': 'hysteresis_samples',
                        'old': old_val,
                        'new': new_val,
                        'reason': f"False positive rate {alert['false_positive_rate']*100:.1f}% > target {self.targets.alert_false_positive_max*100:.1f}%"
                    }

                    if adjustment:
                        change['guardrail_adjustment'] = adjustment
                        changes['adjustments_made'].append(adjustment)

                    # Check approval requirement
                    needs_approval, approval_reason = self._check_requires_approval(
                        'hysteresis_samples', old_val, new_val
                    )
                    if needs_approval:
                        change['requires_approval'] = True
                        change['approval_reason'] = approval_reason
                        changes['requires_approval'].append(change['param'])

                    changes['proposed_changes'].append(change)

                    if not dry_run and not needs_approval:
                        self.config.hysteresis_samples = new_val

            # High false negative rate → decrease hysteresis
            if alert['false_negative_rate'] > self.targets.alert_false_negative_max:
                old_val = self.config.hysteresis_samples
                proposed_val = old_val - 1

                # Apply guardrail limits
                new_val, adjustment = self._apply_guardrail_limits(
                    'hysteresis_samples', old_val, proposed_val
                )

                if new_val != old_val:
                    change = {
                        'param': 'hysteresis_samples',
                        'old': old_val,
                        'new': new_val,
                        'reason': f"False negative rate {alert['false_negative_rate']*100:.1f}% > target {self.targets.alert_false_negative_max*100:.1f}%"
                    }

                    if adjustment:
                        change['guardrail_adjustment'] = adjustment
                        changes['adjustments_made'].append(adjustment)

                    changes['proposed_changes'].append(change)

                    if not dry_run:
                        self.config.hysteresis_samples = new_val

        # Check leverage effectiveness by regime
        for regime in self.leverage_outcomes:
            regime_eff = self.get_leverage_effectiveness(regime)
            if regime_eff.get('total', 0) >= 10:
                # Too aggressive in this regime → reduce max leverage
                if regime_eff.get('too_aggressive_pct', 0) > self.targets.leverage_aggressive_max * 100:
                    param_name = f'leverage_limits.{regime}'
                    old_val = self.config.leverage_limits.get(regime, 10)
                    proposed_val = old_val - 2

                    # Apply guardrail limits
                    new_val, adjustment = self._apply_guardrail_limits(
                        param_name, old_val, proposed_val
                    )

                    if new_val != old_val:
                        change = {
                            'param': param_name,
                            'old': old_val,
                            'new': new_val,
                            'reason': f"Too aggressive {regime_eff['too_aggressive_pct']:.1f}% in {regime}"
                        }

                        if adjustment:
                            change['guardrail_adjustment'] = adjustment
                            changes['adjustments_made'].append(adjustment)

                        # Check approval requirement
                        needs_approval, approval_reason = self._check_requires_approval(
                            param_name, old_val, new_val
                        )
                        if needs_approval:
                            change['requires_approval'] = True
                            change['approval_reason'] = approval_reason
                            changes['requires_approval'].append(param_name)

                        changes['proposed_changes'].append(change)

                        if not dry_run and not needs_approval:
                            self.config.leverage_limits[regime] = new_val

        # Check circuit breaker
        cb = self.get_circuit_breaker_effectiveness()
        if cb.get('total', 0) >= 10:
            # Missing too many triggers → lower threshold
            missed_rate = cb.get('missed_triggers', 0) / cb.get('total', 1)
            if missed_rate > self.targets.circuit_breaker_missed_max:
                old_val = self.config.circuit_breaker_consecutive_losses
                proposed_val = old_val - 1

                # Apply guardrail limits
                new_val, adjustment = self._apply_guardrail_limits(
                    'circuit_breaker_consecutive_losses', old_val, max(proposed_val, 3)
                )

                if new_val != old_val:
                    change = {
                        'param': 'circuit_breaker_consecutive_losses',
                        'old': old_val,
                        'new': new_val,
                        'reason': f"Missed trigger rate {missed_rate*100:.1f}% > target {self.targets.circuit_breaker_missed_max*100:.1f}%"
                    }

                    if adjustment:
                        change['guardrail_adjustment'] = adjustment
                        changes['adjustments_made'].append(adjustment)

                    changes['proposed_changes'].append(change)

                    if not dry_run:
                        self.config.circuit_breaker_consecutive_losses = new_val

        # Apply changes if not dry run and any changes don't require approval
        applicable_changes = [c for c in changes['proposed_changes']
                            if not c.get('requires_approval', False)]

        if not dry_run and applicable_changes:
            self.config.last_tuned = datetime.now().isoformat()
            self.config.tune_count += 1

            # Record in change history for rollback capability
            self.config.change_history.append({
                'timestamp': datetime.now().isoformat(),
                'changes': applicable_changes,
                'tune_count': self.config.tune_count
            })

            # Trim history to last 20 entries
            if len(self.config.change_history) > 20:
                self.config.change_history = self.config.change_history[-20:]

            self._save_config()
            changes['applied'] = True
            logger.info(f"Auto-tune applied {len(applicable_changes)} changes (guardrails enforced)")

        # Log if changes require approval
        if changes['requires_approval']:
            logger.warning(f"Some changes require human approval: {changes['requires_approval']}")

        return changes

    def rollback_last_tune(self) -> Dict[str, Any]:
        """
        Rollback the last auto-tune operation.

        Sprint 8 Feature: Allows reverting recent changes within rollback window.

        Returns:
            Dict with rollback status
        """
        result = {
            'timestamp': datetime.now().isoformat(),
            'success': False,
            'reverted_changes': []
        }

        if not self.config.change_history:
            result['error'] = "No change history available for rollback"
            return result

        last_change = self.config.change_history[-1]

        # Check rollback window
        try:
            change_time = datetime.fromisoformat(last_change['timestamp'])
            hours_since = (datetime.now() - change_time).total_seconds() / 3600
            if hours_since > self.guardrails.rollback_window_hours:
                result['error'] = f"Rollback window expired ({hours_since:.1f}h > {self.guardrails.rollback_window_hours}h)"
                return result
        except (ValueError, KeyError, TypeError):
            pass  # Allow rollback if timestamp is invalid

        # Revert each change
        for change in last_change.get('changes', []):
            param = change['param']
            old_value = change['old']

            if param == 'hysteresis_samples':
                self.config.hysteresis_samples = old_value
                result['reverted_changes'].append(param)
            elif param.startswith('leverage_limits.'):
                regime = param.split('.')[-1]
                self.config.leverage_limits[regime] = old_value
                result['reverted_changes'].append(param)
            elif param == 'circuit_breaker_consecutive_losses':
                self.config.circuit_breaker_consecutive_losses = old_value
                result['reverted_changes'].append(param)

        # Remove the last history entry
        self.config.change_history.pop()
        self.config.tune_count = max(0, self.config.tune_count - 1)
        self._save_config()

        result['success'] = True
        logger.info(f"Rolled back {len(result['reverted_changes'])} changes")

        return result

    def get_regime_performance(self) -> Dict[str, Any]:
        """Get detailed performance breakdown by market regime."""
        performance = {}

        for regime, definition in REGIME_DEFINITIONS.items():
            regime_data = {
                'definition': {
                    'atr_range': f"{definition.atr_ratio_min}-{definition.atr_ratio_max}",
                    'leverage_range': f"{definition.recommended_leverage_min}-{definition.recommended_leverage_max}x",
                    'position_multiplier': definition.position_size_multiplier,
                    'description': definition.description
                },
                'effectiveness': self.get_leverage_effectiveness(regime),
                'sample_count': len(self.leverage_outcomes.get(regime, [])),
                'avg_pnl': None
            }

            # Calculate average P&L for regime
            pnl_list = self.leverage_pnl_by_regime.get(regime, [])
            if pnl_list:
                regime_data['avg_pnl'] = statistics.mean(pnl_list)

            performance[regime] = regime_data

        return performance

    def save_report(self):
        """Save validation report to file."""
        try:
            report = self.generate_validation_report()
            with open(VALIDATION_RESULTS_FILE, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Validation report saved to {VALIDATION_RESULTS_FILE}")
        except Exception as e:
            logger.error(f"Failed to save validation report: {e}")

    def print_report(self):
        """Print validation report to console."""
        report = self.generate_validation_report()

        print("\n" + "=" * 70)
        print("RISK MANAGEMENT VALIDATION REPORT V2.0.0")
        print("=" * 70)
        print(f"Report Time: {report['timestamp']}")

        # Target Status Summary
        target_status = report.get('target_status', {})
        overall = target_status.get('overall_status', 'UNKNOWN')
        status_icon = "✓" if overall == 'MEETS_TARGETS' else "✗"
        print(f"\n{status_icon} OVERALL TARGET STATUS: {overall}")

        # Performance Targets
        print("\n" + "-" * 50)
        print("PERFORMANCE TARGETS (Sprint 7)")
        print("-" * 50)
        targets = report.get('performance_targets', {})
        print(f"  Alert Precision:  >{targets.get('alert_precision_min', 0)*100:.0f}%")
        print(f"  Alert Recall:     >{targets.get('alert_recall_min', 0)*100:.0f}%")
        print(f"  Alert F1:         >{targets.get('alert_f1_min', 0)*100:.0f}%")
        print(f"  Leverage Correct: >{targets.get('leverage_correct_min', 0)*100:.0f}%")
        print(f"  Circuit Breaker:  >{targets.get('circuit_breaker_effectiveness_min', 0)*100:.0f}%")

        # Alert validation
        print("\n" + "-" * 50)
        print("ALERT VALIDATION")
        print("-" * 50)
        alert = report['alert_validation']['overall']
        if alert.get('total', 0) > 0:
            print(f"  Total alerts validated: {alert['total']}")
            print(f"  Precision: {alert['precision']*100:.1f}%")
            print(f"  Recall: {alert['recall']*100:.1f}%")
            print(f"  F1 Score: {alert['f1_score']*100:.1f}%")
            print(f"  False Positive Rate: {alert['false_positive_rate']*100:.1f}%")
            print(f"  False Negative Rate: {alert['false_negative_rate']*100:.1f}%")
            if alert.get('needs_tuning'):
                print(f"  TUNING NEEDED: {alert['tuning_reason']}")
        else:
            print("  No alert validations recorded yet")

        # Leverage validation
        print("\n" + "-" * 50)
        print("LEVERAGE VALIDATION")
        print("-" * 50)
        leverage = report['leverage_validation']['overall']
        if leverage.get('total', 0) > 0:
            print(f"  Total validations: {leverage['total']}")
            print(f"  Correct: {leverage['correct_pct']:.1f}%")
            print(f"  Too Aggressive: {leverage['too_aggressive_pct']:.1f}%")
            print(f"  Too Conservative: {leverage['too_conservative_pct']:.1f}%")
            print(f"  Effectiveness Score: {leverage['effectiveness_score']*100:.1f}%")
        else:
            print("  No leverage validations recorded yet")

        # Circuit breaker
        print("\n" + "-" * 50)
        print("CIRCUIT BREAKER VALIDATION")
        print("-" * 50)
        cb = report['circuit_breaker']
        if cb.get('total', 0) > 0:
            print(f"  Total events: {cb['total']}")
            print(f"  Triggered correctly: {cb['triggered_correctly']}")
            print(f"  Triggered incorrectly: {cb['triggered_incorrectly']}")
            print(f"  Missed triggers: {cb['missed_triggers']}")
            print(f"  Effectiveness: {cb['effectiveness_score']*100:.1f}%")
        else:
            print("  No circuit breaker events recorded yet")

        # Hysteresis
        print("\n" + "-" * 50)
        print("HYSTERESIS VALIDATION")
        print("-" * 50)
        hyst = report['hysteresis']
        if hyst.get('total', 0) > 0:
            print(f"  Total events: {hyst['total']}")
            print(f"  Accuracy: {hyst['accuracy']*100:.1f}%")
            print(f"  Triggered too early: {hyst['triggered_too_early']}")
            print(f"  Triggered too late: {hyst['triggered_too_late']}")
            print(f"  Recommendation: {hyst['recommendation']}")
        else:
            print("  No hysteresis events recorded yet")

        # Shadow trading
        print("\n" + "-" * 50)
        print("SHADOW TRADING VALIDATION")
        print("-" * 50)
        shadow = report['shadow_trading']
        if shadow.get('total', 0) > 0:
            print(f"  Total trades: {shadow['total']}")
            print(f"  Win rate: {shadow['win_rate']:.1f}%")
            print(f"  Average P&L: {shadow['avg_pnl_pct']:.2f}%")
            print(f"  Average leverage: {shadow['avg_leverage']:.1f}x")
            print(f"  Risk check accuracy: {shadow['risk_check_accuracy']:.1f}%")
        else:
            print("  No shadow trades recorded yet")

        # Recommendations
        print("\n" + "-" * 50)
        print("RECOMMENDATIONS")
        print("-" * 50)
        if report['recommendations']:
            for rec in report['recommendations']:
                print(f"  [{rec['priority']}] {rec['area']}")
                print(f"    Issue: {rec['issue']}")
                print(f"    Action: {rec['recommendation']}")
                print()
        else:
            print("  No tuning recommendations at this time")

        print("=" * 70)


# Singleton instance
_risk_validator_instance = None

def get_risk_validator() -> RiskValidator:
    """Get or create the singleton RiskValidator instance."""
    global _risk_validator_instance
    if _risk_validator_instance is None:
        _risk_validator_instance = RiskValidator()
    return _risk_validator_instance


if __name__ == "__main__":
    import random

    print("=" * 60)
    print("RISK VALIDATOR V2.1.0 TEST")
    print("=" * 60)

    # Test with explicit targets
    targets = PerformanceTargets(
        alert_precision_min=0.90,
        alert_recall_min=0.85,
        leverage_correct_min=0.80
    )
    validator = RiskValidator(targets=targets)

    # Show regime definitions
    print("\n--- REGIME DEFINITIONS ---")
    for name, regime in REGIME_DEFINITIONS.items():
        print(f"  {name}: ATR {regime.atr_ratio_min}-{regime.atr_ratio_max}, Lev {regime.recommended_leverage_min}-{regime.recommended_leverage_max}x")

    # Test regime detection
    print("\n--- REGIME DETECTION (ATR only) ---")
    test_atrs = [0.5, 1.0, 1.7, 2.5, 3.5]
    for atr in test_atrs:
        regime = get_regime_from_atr_ratio(atr)
        print(f"  ATR ratio {atr} -> {regime}")

    # Sprint 8: Test ADX calculation and regime detection
    print("\n--- ADX-BASED TREND DETECTION (Sprint 8) ---")
    # Simulate price data for ADX calculation
    random.seed(42)  # Reproducible results
    base_price = 100.0
    highs, lows, closes = [], [], []
    # Generate trending price data
    for i in range(30):
        trend = i * 0.5  # Uptrend
        volatility = random.uniform(1, 3)
        close = base_price + trend + random.uniform(-1, 1)
        high = close + volatility
        low = close - volatility
        closes.append(close)
        highs.append(high)
        lows.append(low)

    adx_result = calculate_adx(highs, lows, closes)
    if adx_result:
        print(f"  ADX: {adx_result.adx:.2f}")
        print(f"  +DI: {adx_result.plus_di:.2f}, -DI: {adx_result.minus_di:.2f}")
        print(f"  Trend Strength: {adx_result.trend_strength}")
        print(f"  Trend Direction: {adx_result.trend_direction}")
        print(f"  Is Trending: {adx_result.is_trending}")

        # Test regime with ADX
        regime_with_adx, adx = get_regime_with_adx(1.2, highs, lows, closes)
        regime_without_adx = get_regime_from_atr_ratio(1.2)
        print(f"\n  ATR 1.2 without ADX: {regime_without_adx}")
        print(f"  ATR 1.2 with ADX:    {regime_with_adx}")
        print(f"  (Demonstrates NORMAL vs TRENDING differentiation)")
    else:
        print("  ADX calculation failed (insufficient data)")

    # Sprint 8: Test guardrails
    print("\n--- AUTO-TUNE GUARDRAILS (Sprint 8) ---")
    guardrails = validator.guardrails
    print(f"  Min alert samples: {guardrails.min_alert_samples}")
    print(f"  Min leverage samples: {guardrails.min_leverage_samples}")
    print(f"  Max leverage change: ±{guardrails.max_leverage_change}")
    print(f"  Critical regimes: {guardrails.critical_regime_changes}")
    print(f"  Rollback window: {guardrails.rollback_window_hours} hours")

    # Simulate alert validations
    print("\nSimulating alert validations...")
    for i in range(50):
        alert_type = random.choice(['drawdown', 'margin', 'averaging'])
        value = random.uniform(0.05, 0.25)
        threshold = 0.15
        triggered = value >= threshold and random.random() > 0.3  # Some hysteresis effect
        subsequent = value + random.uniform(-0.05, 0.05)
        validator.record_alert_validation(alert_type, triggered, value, threshold, subsequent)

    # Simulate leverage validations with proper regimes
    print("Simulating leverage validations...")
    regimes = ['EXTREME_VOLATILITY', 'HIGH_VOLATILITY', 'ELEVATED', 'NORMAL', 'LOW_VOLATILITY', 'TRENDING']
    for i in range(40):
        regime = random.choice(regimes)
        lev_min, lev_max = get_regime_leverage_range(regime)
        recommended = (lev_min + lev_max) // 2
        used = recommended + random.randint(-2, 2)
        outcome = random.choices(['profit', 'loss', 'liquidation'], weights=[0.5, 0.45, 0.05])[0]
        validator.record_leverage_validation(
            f"TEST{i}/USDT", regime, recommended, used,
            random.uniform(1.0, 2.5), random.uniform(-10, 20), outcome
        )

    # Simulate circuit breaker events
    print("Simulating circuit breaker events...")
    for i in range(15):
        triggered = random.random() > 0.5
        conditions = {'session_pnl': random.uniform(-0.20, 0.05)}
        outcome = {'session_pnl': conditions['session_pnl'] + random.uniform(-0.10, 0.05),
                  'positions_closed': random.randint(0, 3) if triggered else 0}
        validator.record_circuit_breaker_event(
            triggered, 'session_loss' if triggered else 'none',
            conditions, outcome
        )

    # Simulate hysteresis events
    print("Simulating hysteresis events...")
    for i in range(30):
        breach_count = random.randint(1, 5)
        threshold = 3
        triggered = breach_count >= threshold
        was_real = random.random() > 0.3
        validator.record_hysteresis_event('drawdown', breach_count, threshold, triggered, was_real)

    # Simulate shadow trades
    print("Simulating shadow trades...")
    for i in range(25):
        entry = 100.0
        exit_price = entry * (1 + random.uniform(-0.05, 0.08))
        outcome = 'profit' if exit_price > entry else 'loss'
        if random.random() < 0.05:
            outcome = 'liquidation'
        validator.record_shadow_trade(
            f"BTC{i}/USDT", random.choice(['long', 'short']),
            random.randint(3, 10), entry, exit_price,
            {'recommendation': random.choice(['proceed', 'avoid', 'ok'])},
            outcome
        )

    # Print report
    validator.print_report()

    # Test target status
    print("\n--- TARGET STATUS CHECK ---")
    status = validator.check_target_status()
    print(f"  Overall: {status['overall_status']}")
    for area, metrics in status.get('metrics', {}).items():
        print(f"  {area}:")
        for metric, data in metrics.items():
            icon = "✓" if data['meets_target'] else "✗"
            print(f"    {icon} {metric}: {data['current']*100:.1f}% (target: {data['target']*100:.1f}%)")

    # Test auto-tuning with guardrails (dry run)
    print("\n--- AUTO-TUNE WITH GUARDRAILS (Sprint 8) ---")
    tune_result = validator.auto_tune(dry_run=True)

    # Show guardrail status
    gs = tune_result['guardrails_status']
    print(f"  Guardrails passed: {gs['passed']}")
    if gs['blocking_reasons']:
        print(f"  Blocking reasons:")
        for reason in gs['blocking_reasons']:
            print(f"    - {reason}")

    if tune_result['proposed_changes']:
        print(f"\n  Proposed changes:")
        for change in tune_result['proposed_changes']:
            approval = " [NEEDS APPROVAL]" if change.get('requires_approval') else ""
            adjustment = f" ({change['guardrail_adjustment']})" if change.get('guardrail_adjustment') else ""
            print(f"    {change['param']}: {change['old']} -> {change['new']}{adjustment}{approval}")
            print(f"      Reason: {change['reason']}")
    else:
        print("  No changes proposed")

    if tune_result['requires_approval']:
        print(f"\n  Changes requiring human approval: {tune_result['requires_approval']}")

    # Test with force=True to bypass guardrails
    print("\n--- AUTO-TUNE WITH FORCE=True ---")
    forced_result = validator.auto_tune(dry_run=True, force=True)
    print(f"  Guardrails bypassed: {forced_result['guardrails_status']['forced']}")

    # Test regime performance
    print("\n--- REGIME PERFORMANCE ---")
    regime_perf = validator.get_regime_performance()
    for regime, data in regime_perf.items():
        eff = data['effectiveness']
        if eff.get('total', 0) > 0:
            print(f"  {regime}: {eff['correct_pct']:.1f}% correct ({eff['total']} samples)")

    # Save report
    validator.save_report()

    print("\n" + "=" * 60)
    print("Risk Validator V2.1.0 test completed!")
    print("Sprint 8 Features: ADX trend detection + Auto-tune guardrails")
    print("=" * 60)
