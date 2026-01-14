#!/usr/bin/env python3
"""
Stress Test Module for Profit Protection Hedge
===============================================
Tests the profit protection hedge under extreme market conditions.

Scenarios:
1. Flash Crash - Sudden 10-20% drop
2. Rapid Pump - Sudden 10-20% rise
3. Prolonged Downtrend - Steady decline over time
4. Prolonged Uptrend - Steady rise over time
5. High Volatility - Wild swings both directions
6. Low Volatility (Choppy) - Sideways movement
7. Black Swan - Extreme 30%+ moves
8. V-Shape Recovery - Drop then rapid recovery
9. Dead Cat Bounce - Drop, small recovery, then continued drop

Author: Claude + Grok Consortium
Version: 1.2.8
Date: January 14, 2026

V1.2.8 Changes:
- DISABLED Risk Patch (no effect on dead_cat/v_shape scenarios)
- Root cause: Drop detection at hedge open time fails because recovery has already started
- By the time main profits (hedge opens), price has recovered from drop
- Lookback sees recovery, not original drop → threshold never triggers
- Conclusion: dead_cat/v_shape require ML pattern recognition, not rule-based detection

V1.2.7 Changes:
- DISABLED Market Regime Filter (caused -125% black_swan_down regression)
- Blocking hedges entirely missed legitimate protection opportunities

V1.2.6 Changes:
- DISABLED MAIN_DROP_REQUIRES_HEDGE_LOSS (just shifted exits to hedge_stop_loss)
- DISABLED RECOVERY_DETECTION (just shifted exits to hedge_stop_loss)

V1.2.5 Changes:
- DISABLED profit taking delay (caused -39.9% flash_crash regression, -87.7% black_swan_down)
- DISABLED trailing stop delay (caused overall -6.0% vs +11.4% with delays off)
- Conclusion: dead_cat_bounce (-827%) is unfixable without hurting other scenarios

V1.2.4 Changes:
- Added main_drop delay (30 periods) to prevent premature exits during bounces
- Added stop_loss delay (30 periods) to prevent premature stop losses during bounces

V1.2.3 Changes:
- Added ultra-low volatility hedge disable (ATR% < 0.5% disables hedging entirely)
- Disabled bounce detection (caused regressions)

V1.2.2 Changes:
- Added ATR regime filter to disable spike mode in low volatility environments

V1.2.1 Changes:
- Fixed high_volatility regression from V1.2.0
- Increased spike threshold from 2.0x to 2.5x
- Reduced spike hedge size from 75% to 60%
- Widened fast stop from 1.5x to 2.0x ATR
- Added spike confirmation (require 2 consecutive readings)
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from enum import Enum
import json


class Scenario(Enum):
    FLASH_CRASH = "flash_crash"
    RAPID_PUMP = "rapid_pump"
    PROLONGED_DOWNTREND = "prolonged_downtrend"
    PROLONGED_UPTREND = "prolonged_uptrend"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    BLACK_SWAN_DOWN = "black_swan_down"
    BLACK_SWAN_UP = "black_swan_up"
    V_SHAPE_RECOVERY = "v_shape_recovery"
    DEAD_CAT_BOUNCE = "dead_cat_bounce"


@dataclass
class StressTestResult:
    scenario: Scenario
    strategy: str
    initial_price: float = 100.0
    final_price: float = 0.0
    peak_upnl: float = 0.0
    final_pnl: float = 0.0
    hedge_pnl: float = 0.0
    combined_pnl: float = 0.0
    max_drawdown: float = 0.0
    hedge_triggered: bool = False
    exit_reason: str = ""
    price_path: List[float] = field(default_factory=list)


class MarketSimulator:
    """Generates synthetic price paths for stress testing"""

    def __init__(self, initial_price: float = 100.0, num_candles: int = 500):
        self.initial_price = initial_price
        self.num_candles = num_candles

    def generate_flash_crash(self, crash_pct: float = 0.15, recovery_pct: float = 0.05) -> np.ndarray:
        """Sudden sharp drop followed by partial recovery"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal movement for first 30%
        normal_period = int(self.num_candles * 0.3)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Sharp crash over 5% of candles
        crash_period = int(self.num_candles * 0.05)
        crash_per_candle = crash_pct / crash_period
        for i in range(normal_period, normal_period + crash_period):
            prices[i] = prices[i-1] * (1 - crash_per_candle + np.random.normal(0, 0.002))

        # Partial recovery and stabilization
        recovery_target = prices[normal_period + crash_period - 1] * (1 + recovery_pct)
        remaining = self.num_candles - normal_period - crash_period
        for i in range(normal_period + crash_period, self.num_candles):
            progress = (i - normal_period - crash_period) / remaining
            target = prices[normal_period + crash_period - 1] + (recovery_target - prices[normal_period + crash_period - 1]) * progress
            prices[i] = target * (1 + np.random.normal(0, 0.003))

        return prices

    def generate_rapid_pump(self, pump_pct: float = 0.15, pullback_pct: float = 0.05) -> np.ndarray:
        """Sudden sharp rise followed by pullback"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal movement for first 30%
        normal_period = int(self.num_candles * 0.3)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Sharp pump over 5% of candles
        pump_period = int(self.num_candles * 0.05)
        pump_per_candle = pump_pct / pump_period
        for i in range(normal_period, normal_period + pump_period):
            prices[i] = prices[i-1] * (1 + pump_per_candle + np.random.normal(0, 0.002))

        # Pullback and stabilization
        pullback_target = prices[normal_period + pump_period - 1] * (1 - pullback_pct)
        remaining = self.num_candles - normal_period - pump_period
        for i in range(normal_period + pump_period, self.num_candles):
            progress = (i - normal_period - pump_period) / remaining
            target = prices[normal_period + pump_period - 1] - (prices[normal_period + pump_period - 1] - pullback_target) * min(1, progress * 2)
            prices[i] = target * (1 + np.random.normal(0, 0.003))

        return prices

    def generate_prolonged_downtrend(self, total_decline: float = 0.30) -> np.ndarray:
        """Steady decline over the entire period"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        decline_per_candle = total_decline / self.num_candles
        for i in range(1, self.num_candles):
            # Trending down with some noise
            prices[i] = prices[i-1] * (1 - decline_per_candle + np.random.normal(0, 0.008))

        return prices

    def generate_prolonged_uptrend(self, total_gain: float = 0.30) -> np.ndarray:
        """Steady rise over the entire period"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        gain_per_candle = total_gain / self.num_candles
        for i in range(1, self.num_candles):
            prices[i] = prices[i-1] * (1 + gain_per_candle + np.random.normal(0, 0.008))

        return prices

    def generate_high_volatility(self, volatility: float = 0.03) -> np.ndarray:
        """Wild swings in both directions"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        for i in range(1, self.num_candles):
            # High volatility random walk
            prices[i] = prices[i-1] * (1 + np.random.normal(0, volatility))

        return prices

    def generate_low_volatility(self, volatility: float = 0.003) -> np.ndarray:
        """Sideways choppy movement"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        for i in range(1, self.num_candles):
            # Low volatility mean-reverting
            mean_reversion = (self.initial_price - prices[i-1]) * 0.01
            prices[i] = prices[i-1] * (1 + np.random.normal(mean_reversion/prices[i-1], volatility))

        return prices

    def generate_black_swan_down(self, crash_pct: float = 0.35) -> np.ndarray:
        """Extreme sudden drop (30%+)"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 40%
        normal_period = int(self.num_candles * 0.4)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Catastrophic crash over 3% of candles
        crash_period = int(self.num_candles * 0.03)
        crash_per_candle = crash_pct / crash_period
        for i in range(normal_period, normal_period + crash_period):
            prices[i] = prices[i-1] * (1 - crash_per_candle)

        # Slow recovery/stabilization
        for i in range(normal_period + crash_period, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.0005, 0.005))

        return prices

    def generate_black_swan_up(self, pump_pct: float = 0.35) -> np.ndarray:
        """Extreme sudden rise (30%+)"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 40%
        normal_period = int(self.num_candles * 0.4)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Massive pump over 3% of candles
        pump_period = int(self.num_candles * 0.03)
        pump_per_candle = pump_pct / pump_period
        for i in range(normal_period, normal_period + pump_period):
            prices[i] = prices[i-1] * (1 + pump_per_candle)

        # Slow decline/stabilization
        for i in range(normal_period + pump_period, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(-0.0003, 0.005))

        return prices

    def generate_v_shape_recovery(self, drop_pct: float = 0.20) -> np.ndarray:
        """Drop then rapid full recovery"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 20%
        normal_period = int(self.num_candles * 0.2)
        for i in range(1, normal_period):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # Drop over 20%
        drop_period = int(self.num_candles * 0.2)
        drop_per_candle = drop_pct / drop_period
        for i in range(normal_period, normal_period + drop_period):
            prices[i] = prices[i-1] * (1 - drop_per_candle + np.random.normal(0, 0.003))

        # Recovery over 30%
        recovery_period = int(self.num_candles * 0.3)
        bottom_price = prices[normal_period + drop_period - 1]
        recovery_target = self.initial_price * 1.05  # Slight overshoot
        for i in range(normal_period + drop_period, normal_period + drop_period + recovery_period):
            progress = (i - normal_period - drop_period) / recovery_period
            target = bottom_price + (recovery_target - bottom_price) * progress
            prices[i] = target * (1 + np.random.normal(0, 0.003))

        # Stabilization
        for i in range(normal_period + drop_period + recovery_period, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(0, 0.005))

        return prices

    def generate_dead_cat_bounce(self, drop1_pct: float = 0.15, bounce_pct: float = 0.08, drop2_pct: float = 0.20) -> np.ndarray:
        """Drop, small recovery, then continued drop"""
        prices = np.zeros(self.num_candles)
        prices[0] = self.initial_price

        # Normal for 15%
        phase1 = int(self.num_candles * 0.15)
        for i in range(1, phase1):
            prices[i] = prices[i-1] * (1 + np.random.normal(0.001, 0.005))

        # First drop over 15%
        phase2 = int(self.num_candles * 0.15)
        drop_per_candle = drop1_pct / phase2
        for i in range(phase1, phase1 + phase2):
            prices[i] = prices[i-1] * (1 - drop_per_candle + np.random.normal(0, 0.003))

        # Bounce over 15%
        phase3 = int(self.num_candles * 0.15)
        bounce_per_candle = bounce_pct / phase3
        for i in range(phase1 + phase2, phase1 + phase2 + phase3):
            prices[i] = prices[i-1] * (1 + bounce_per_candle + np.random.normal(0, 0.003))

        # Second drop over 25%
        phase4 = int(self.num_candles * 0.25)
        drop_per_candle = drop2_pct / phase4
        for i in range(phase1 + phase2 + phase3, phase1 + phase2 + phase3 + phase4):
            prices[i] = prices[i-1] * (1 - drop_per_candle + np.random.normal(0, 0.003))

        # Stabilization
        for i in range(phase1 + phase2 + phase3 + phase4, self.num_candles):
            prices[i] = prices[i-1] * (1 + np.random.normal(0, 0.005))

        return prices


class ProfitProtectionHedgeStressTest:
    """Stress tests the profit protection hedge strategy"""

    # Configuration (matching hedge_gateway.py)
    HEDGE_SIZE = 0.50
    PROFIT_GATE = 0.10
    MAIN_DROP_GATE = 0.50
    STOP_LOSS = -0.05
    MIN_PROFIT = 5.00
    TAKE_PROFIT_TRIGGER = 0.70

    # Stress Test Improvements (V1.1.0)
    TRAILING_STOP_ACTIVATION = 0.03  # Activate trailing stop at 3% profit
    TRAILING_STOP_DISTANCE = 0.02    # Trail 2% behind peak profit
    MOMENTUM_RSI_OVERSOLD = 30       # Don't hedge if RSI < 30 (simulated)

    # V1.2.2: Volatility Spike Detector with ATR Regime Filter
    # FIX V1.2.1: Increased threshold from 2.0 to 2.5 to reduce false positives
    # FIX V1.2.1: Reduced hedge size from 75% to 60% to limit losses on false signals
    # FIX V1.2.1: Widened fast stop from 1.5x to 2.0x ATR to avoid whipsaw exits
    # FIX V1.2.1: Added spike confirmation (require 2 consecutive readings)
    # FIX V1.2.2: Added ATR regime filter to disable spike mode in low volatility
    VOLATILITY_SPIKE_MULTIPLIER = 2.5   # Spike when recent vol > 2.5x baseline (was 2.0)
    VOLATILITY_SPIKE_HEDGE_SIZE = 0.60  # 60% hedge during spikes (was 75%)
    VOLATILITY_SPIKE_MIN_PROFIT = 2.00  # $2 threshold during spikes (vs $5 normal)
    FAST_STOP_ATR_MULT = 2.0            # Fast stop at 2.0x ATR (was 1.5)
    SPIKE_CONFIRMATION_COUNT = 2        # Require 2 consecutive spike readings

    # V1.2.2: ATR Regime Filter - disable spike mode when baseline volatility is too low
    # This fixes low_volatility (-12.4%) and dead_cat_bounce (-12.0%) regressions
    MIN_BASELINE_ATR_PCT = 0.005        # Minimum baseline ATR as % of price (0.5%)
    ATR_REGIME_ENABLED = True            # Enable/disable regime filter

    # V1.2.3: Ultra-Low Volatility Hedge Disable
    # Completely disable hedging when volatility is extremely low (not profitable)
    # TUNED: Increased from 0.3% to 0.5% to better filter low volatility scenarios
    ULTRA_LOW_VOL_ATR_PCT = 0.005       # Disable hedging entirely below 0.5% ATR (was 0.3%)
    ULTRA_LOW_VOL_ENABLED = True         # Enable/disable ultra-low vol filter

    # V1.2.3: Bounce Detection - delay hedging during price bounces
    # DISABLED: Bounce detection caused more regressions than fixes
    # The prior drop requirement interferes with legitimate hedging scenarios
    BOUNCE_DETECTION_ENABLED = False     # DISABLED - caused -84.7% regression in high_volatility
    BOUNCE_LOOKBACK_PERIODS = 20         # Look back 20 periods for bounce detection (was 10)
    BOUNCE_THRESHOLD_PCT = 0.03          # 3% bounce from recent low triggers detection
    BOUNCE_CONFIRMATION_PERIODS = 3      # Require 3 periods above bounce level to confirm
    BOUNCE_PRIOR_DROP_PCT = 0.05         # Require 5% prior drop before detecting bounce

    # V1.2.4: Main Drop Delay - prevent premature hedge exits during bounces
    # Fixes dead_cat_bounce (-827.6%) where main_drop triggers during bounce phase
    # The delay allows hedge to ride through temporary recoveries before checking main_drop
    MAIN_DROP_DELAY_ENABLED = True       # Enable/disable main_drop delay
    MAIN_DROP_DELAY_PERIODS = 30         # Wait 30 candles before main_drop can trigger (was 15)

    # V1.2.4: Stop Loss Delay - prevent premature hedge stop losses during bounces
    # After main_drop delay fix, hedge_stop_loss became the main issue (40% of exits)
    # The stop loss hits -5% during bounce phase before price drops again
    STOP_LOSS_DELAY_ENABLED = True       # Enable/disable stop loss delay
    STOP_LOSS_DELAY_PERIODS = 30         # Wait 30 candles before stop loss can trigger (was 20)

    # V1.2.5: Profit Taking Delay - DISABLED (caused -39.9% flash_crash regression)
    # Keeping hedge profit taking instant allows capturing quick profits in most scenarios
    PROFIT_TAKING_DELAY_ENABLED = False  # DISABLED - hurts flash_crash and black_swan_down
    PROFIT_TAKING_DELAY_PERIODS = 30     # Not used when disabled

    # V1.2.5: Trailing Stop Delay - DISABLED (caused regressions)
    # Keeping trailing stop instant allows quick exits when hedge peaks early
    TRAILING_STOP_DELAY_ENABLED = False  # DISABLED - hurts most scenarios
    TRAILING_STOP_DELAY_PERIODS = 30     # Not used when disabled

    # V1.2.6: Main Drop Requires Hedge Loss - DISABLED (didn't fix v_shape_recovery)
    # Testing showed this just shifts exits from main_drop to hedge_stop_loss
    # The v_shape_recovery scenario (-56.7%) is unfixable like dead_cat_bounce (-827%)
    MAIN_DROP_REQUIRES_HEDGE_LOSS = False  # DISABLED - no improvement
    MAIN_DROP_HEDGE_LOSS_THRESHOLD = -0.03  # Not used when disabled

    # V1.2.6: Recovery Detection - DISABLED (didn't fix v_shape_recovery)
    # Testing showed this just shifts exits from main_drop to hedge_stop_loss
    RECOVERY_DETECTION_ENABLED = False    # DISABLED - no improvement
    RECOVERY_LOOKBACK_PERIODS = 5         # Not used when disabled

    # V1.2.7: Market Regime Filter - DISABLED (caused -125% black_swan_down regression)
    # Testing showed:
    # - 10% threshold: didn't block enough hedges, no improvement
    # - 5% threshold: blocked too many legitimate hedges, -12.1% overall
    # The filter can't distinguish between crash (hedge) vs bounce (don't hedge) without ML
    REGIME_FILTER_ENABLED = False         # DISABLED - causes more harm than good
    REGIME_LOOKBACK_PERIODS = 50          # Not used when disabled
    REGIME_DROP_THRESHOLD = 0.05          # Not used when disabled
    REGIME_RECOVERY_THRESHOLD = 0.98      # Not used when disabled

    # V1.2.8: Risk Patch for dead_cat/v_shape - REDUCE hedge size instead of blocking
    # Key insight: Blocking hedges entirely caused -125% regression (missed protection)
    # Solution: Reduce hedge size during post-drop conditions (partial protection)
    # This limits downside in dead_cat/v_shape while preserving some protection
    RISK_PATCH_ENABLED = False            # DISABLED: No effect on dead_cat/v_shape (drop not visible at hedge open)
    RISK_PATCH_LOOKBACK = 30              # Look back 30 periods for recent high
    RISK_PATCH_DROP_THRESHOLD = 0.08      # 8% drop from recent high triggers patch
    RISK_PATCH_HEDGE_SIZE = 0.25          # Reduce hedge to 25% (from 50%) during risk

    def __init__(self, leverage: int = 10, position_size_usd: float = 10.0):
        self.leverage = leverage
        self.position_size_usd = position_size_usd
        self.simulator = MarketSimulator()

    def detect_volatility_spike(self, prices: np.ndarray, index: int,
                                 fast_period: int = 5, slow_period: int = 20,
                                 spike_state: Dict = None) -> Tuple[bool, float, bool]:
        """
        Detect volatility spike using ATR-like calculation on price path.

        V1.2.1: Now requires SPIKE_CONFIRMATION_COUNT consecutive readings
        to confirm a spike, reducing false positives in high volatility conditions.

        V1.2.2: Added ATR regime filter to disable spike mode when baseline
        volatility is too low (fixes low_volatility and dead_cat_bounce regressions).

        Returns (spike_confirmed, spike_ratio, regime_blocked)
        """
        if index < slow_period:
            return (False, 0.0, False)

        # Calculate "true ranges" using price changes (simplified ATR)
        def calc_volatility(start: int, period: int) -> float:
            ranges = []
            for i in range(start - period + 1, start + 1):
                if i > 0:
                    high = max(prices[i], prices[i-1])
                    low = min(prices[i], prices[i-1])
                    ranges.append(high - low)
            return np.mean(ranges) if ranges else 0

        vol_fast = calc_volatility(index, fast_period)
        vol_slow = calc_volatility(index, slow_period)

        if vol_slow == 0:
            return (False, 0.0, False)

        # V1.2.2: ATR Regime Filter - check if baseline volatility is sufficient
        regime_blocked = False
        if self.ATR_REGIME_ENABLED:
            current_price = prices[index]
            if current_price > 0:
                atr_pct = vol_slow / current_price
                if atr_pct < self.MIN_BASELINE_ATR_PCT:
                    # Baseline volatility too low - disable spike mode
                    regime_blocked = True

        spike_ratio = vol_fast / vol_slow
        ratio_exceeds_threshold = spike_ratio >= self.VOLATILITY_SPIKE_MULTIPLIER

        # V1.2.1: Spike confirmation logic - require consecutive readings
        if spike_state is not None:
            # Only count if threshold exceeded AND not regime blocked
            if ratio_exceeds_threshold and not regime_blocked:
                spike_state["consecutive_count"] = spike_state.get("consecutive_count", 0) + 1
            else:
                spike_state["consecutive_count"] = 0  # Reset on non-spike or regime block

            # Only confirm spike if we have enough consecutive readings AND not blocked
            spike_confirmed = (spike_state["consecutive_count"] >= self.SPIKE_CONFIRMATION_COUNT) and not regime_blocked
        else:
            # Fallback if no state tracking (shouldn't happen in normal use)
            spike_confirmed = ratio_exceeds_threshold and not regime_blocked

        return (spike_confirmed, spike_ratio, regime_blocked)

    def is_ultra_low_volatility(self, prices: np.ndarray, index: int,
                                 slow_period: int = 20) -> Tuple[bool, float]:
        """
        V1.2.3: Check if volatility is ultra-low (disable hedging entirely).

        Returns (is_ultra_low, atr_pct)
        """
        if not self.ULTRA_LOW_VOL_ENABLED:
            return (False, 0.0)

        if index < slow_period:
            return (False, 0.0)

        # Calculate slow ATR
        def calc_volatility(start: int, period: int) -> float:
            ranges = []
            for i in range(start - period + 1, start + 1):
                if i > 0:
                    high = max(prices[i], prices[i-1])
                    low = min(prices[i], prices[i-1])
                    ranges.append(high - low)
            return np.mean(ranges) if ranges else 0

        vol_slow = calc_volatility(index, slow_period)
        current_price = prices[index]

        if current_price > 0:
            atr_pct = vol_slow / current_price
            is_ultra_low = atr_pct < self.ULTRA_LOW_VOL_ATR_PCT
            return (is_ultra_low, atr_pct)

        return (False, 0.0)

    def detect_bounce(self, prices: np.ndarray, index: int,
                      bounce_state: Dict = None) -> Tuple[bool, float]:
        """
        V1.2.3: Detect if price is bouncing from a recent low.

        TUNED: Now requires a prior drop (BOUNCE_PRIOR_DROP_PCT) before detecting bounce.
        This prevents false triggers in sideways/low-volatility markets.

        Returns (bounce_detected, bounce_pct)
        """
        if not self.BOUNCE_DETECTION_ENABLED:
            return (False, 0.0)

        if index < self.BOUNCE_LOOKBACK_PERIODS:
            return (False, 0.0)

        # Find recent high and low in lookback window
        lookback_start = max(0, index - self.BOUNCE_LOOKBACK_PERIODS)
        lookback_prices = prices[lookback_start:index + 1]
        recent_high = max(lookback_prices)
        recent_low = min(lookback_prices)
        current_price = prices[index]

        # V1.2.3 FIX: First check if there was a prior significant drop
        # Without a prior drop, any "bounce" is just normal price oscillation
        drop_from_high = (recent_high - recent_low) / recent_high if recent_high > 0 else 0
        had_prior_drop = drop_from_high >= self.BOUNCE_PRIOR_DROP_PCT

        if not had_prior_drop:
            # No significant prior drop - reset state and return
            if bounce_state is not None:
                bounce_state["periods_above"] = 0
            return (False, 0.0)

        # Calculate bounce percentage from the low
        bounce_pct = (current_price - recent_low) / recent_low if recent_low > 0 else 0

        # Check if above bounce threshold
        is_bouncing = bounce_pct >= self.BOUNCE_THRESHOLD_PCT

        # Track consecutive periods above bounce level
        if bounce_state is not None:
            if is_bouncing:
                bounce_state["periods_above"] = bounce_state.get("periods_above", 0) + 1
            else:
                bounce_state["periods_above"] = 0

            # Require confirmation periods
            bounce_confirmed = bounce_state["periods_above"] >= self.BOUNCE_CONFIRMATION_PERIODS
        else:
            bounce_confirmed = is_bouncing

        return (bounce_confirmed, bounce_pct)

    def detect_post_drop_regime(self, prices: np.ndarray, index: int) -> Tuple[bool, float, float]:
        """
        V1.2.7: Market Regime Filter - detect post-drop bounce conditions.

        Both dead_cat_bounce (-827%) and v_shape_recovery (-57%) start with a price drop.
        During the "bounce phase", hedges open but lose money as price recovers.
        This filter detects when we're in a post-drop regime and blocks hedging.

        Returns (in_post_drop_regime, drop_pct, recovery_pct)
        """
        if not self.REGIME_FILTER_ENABLED:
            return (False, 0.0, 0.0)

        if index < self.REGIME_LOOKBACK_PERIODS:
            return (False, 0.0, 0.0)

        # Find the recent high in lookback window
        lookback_start = max(0, index - self.REGIME_LOOKBACK_PERIODS)
        lookback_prices = prices[lookback_start:index + 1]
        recent_high = max(lookback_prices)
        current_price = prices[index]

        if recent_high <= 0:
            return (False, 0.0, 0.0)

        # Calculate drop from recent high
        drop_pct = (recent_high - current_price) / recent_high

        # Calculate recovery (how close we are to the high)
        recovery_pct = current_price / recent_high

        # We're in post-drop regime if:
        # 1. Price has dropped more than threshold from recent high
        # 2. Price has NOT recovered to the recovery threshold
        in_post_drop = (drop_pct >= self.REGIME_DROP_THRESHOLD and
                        recovery_pct < self.REGIME_RECOVERY_THRESHOLD)

        return (in_post_drop, drop_pct, recovery_pct)

    def detect_risk_condition(self, prices: np.ndarray, index: int) -> Tuple[bool, float]:
        """
        V1.2.8: Risk Patch - detect conditions where hedge size should be reduced.

        Unlike the regime filter which blocks hedges entirely (caused -125% regression),
        this only reduces hedge size to limit downside while preserving some protection.

        Returns (in_risk_mode, drop_pct)
        """
        if not self.RISK_PATCH_ENABLED:
            return (False, 0.0)

        if index < self.RISK_PATCH_LOOKBACK:
            return (False, 0.0)

        # Find the recent high in lookback window
        lookback_start = max(0, index - self.RISK_PATCH_LOOKBACK)
        lookback_prices = prices[lookback_start:index + 1]
        recent_high = max(lookback_prices)
        current_price = prices[index]

        if recent_high <= 0:
            return (False, 0.0)

        # Calculate drop from recent high
        drop_pct = (recent_high - current_price) / recent_high

        # We're in risk mode if price has dropped more than threshold
        in_risk_mode = drop_pct >= self.RISK_PATCH_DROP_THRESHOLD

        return (in_risk_mode, drop_pct)

    def calc_upnl(self, entry: float, current: float, size: float, side: str) -> Tuple[float, float]:
        """Calculate UPNL and percentage"""
        if side == 'long':
            pnl_pct = (current - entry) / entry
        else:
            pnl_pct = (entry - current) / entry
        margin = (size * entry) / self.leverage
        upnl = margin * pnl_pct * self.leverage
        return upnl, pnl_pct

    def simulate_traditional(self, prices: np.ndarray, side: str = 'long') -> StressTestResult:
        """Simulate traditional close-at-70% strategy"""
        entry_price = prices[0]
        size = (self.position_size_usd * self.leverage) / entry_price

        peak_upnl = 0.0
        max_drawdown = 0.0
        final_pnl = 0.0
        exit_reason = "timeout"

        for i, price in enumerate(prices):
            upnl, pct = self.calc_upnl(entry_price, price, size, side)

            if upnl > peak_upnl:
                peak_upnl = upnl

            if peak_upnl > 0:
                drawdown = (peak_upnl - upnl) / peak_upnl
                max_drawdown = max(max_drawdown, drawdown)

            # Traditional: Close at 70% of peak
            if peak_upnl >= self.MIN_PROFIT and upnl <= peak_upnl * self.TAKE_PROFIT_TRIGGER:
                final_pnl = upnl
                exit_reason = "close_70pct"
                break

            # Stop loss
            if pct <= -0.90:
                final_pnl = upnl
                exit_reason = "stop_loss"
                break

            final_pnl = upnl

        return StressTestResult(
            scenario=Scenario.FLASH_CRASH,  # Will be set by caller
            strategy="traditional",
            initial_price=entry_price,
            final_price=prices[-1],
            peak_upnl=peak_upnl,
            final_pnl=final_pnl,
            hedge_pnl=0,
            combined_pnl=final_pnl,
            max_drawdown=max_drawdown,
            hedge_triggered=False,
            exit_reason=exit_reason,
            price_path=prices.tolist()
        )

    def simulate_profit_hedge(self, prices: np.ndarray, side: str = 'long',
                               use_improvements: bool = True) -> StressTestResult:
        """Simulate profit protection hedge strategy with V1.1.0 improvements"""
        entry_price = prices[0]
        size = (self.position_size_usd * self.leverage) / entry_price

        peak_upnl = 0.0
        max_drawdown = 0.0
        final_pnl = 0.0
        hedge_pnl = 0.0
        exit_reason = "timeout"

        hedge_opened = False
        hedge_entry = 0.0
        hedge_size = 0.0

        # V1.1.0: Trailing stop tracking
        trailing_stop_activated = False
        hedge_peak_pct = 0.0

        # V1.1.0: Momentum filter state (simulated using price momentum)
        momentum_blocked = False

        # V1.2.1: Volatility spike state with confirmation tracking
        spike_mode = False
        spike_ratio = 0.0
        fast_stop_distance = 0.0
        spike_state = {"consecutive_count": 0}  # Track consecutive spike readings

        # V1.2.3: Ultra-low volatility and bounce detection state
        bounce_state = {"periods_above": 0}
        hedge_blocked_reason = ""

        # V1.2.4: Track when hedge opened for main_drop delay
        hedge_open_index = 0

        for i, price in enumerate(prices):
            upnl, pct = self.calc_upnl(entry_price, price, size, side)

            if upnl > peak_upnl:
                peak_upnl = upnl

            if peak_upnl > 0:
                drawdown = (peak_upnl - upnl) / peak_upnl
                max_drawdown = max(max_drawdown, drawdown)

            # V1.2.2: Detect volatility spike with confirmation and regime filter
            if use_improvements and not hedge_opened:
                detected, ratio, blocked = self.detect_volatility_spike(prices, i, spike_state=spike_state)
                if detected and not blocked:
                    spike_mode = True
                    spike_ratio = ratio

            # Determine thresholds based on spike mode
            min_profit = self.VOLATILITY_SPIKE_MIN_PROFIT if spike_mode else self.MIN_PROFIT
            hedge_size_pct = self.VOLATILITY_SPIKE_HEDGE_SIZE if spike_mode else self.HEDGE_SIZE

            # V1.2.8: Risk Patch - reduce hedge size during post-drop conditions
            # This limits downside in dead_cat/v_shape while preserving some protection
            in_risk_mode = False
            if use_improvements and not hedge_opened:
                in_risk_mode, risk_drop_pct = self.detect_risk_condition(prices, i)
                if in_risk_mode:
                    hedge_size_pct = self.RISK_PATCH_HEDGE_SIZE  # Reduce from 50% to 25%

            # V1.2.3: Check hedge blocking conditions before opening
            hedge_blocked = False
            if use_improvements and not hedge_opened:
                # Check ultra-low volatility
                is_ultra_low, atr_pct = self.is_ultra_low_volatility(prices, i)
                if is_ultra_low:
                    hedge_blocked = True
                    hedge_blocked_reason = "ultra_low_vol"

                # Check bounce detection
                if not hedge_blocked:
                    bounce_detected, bounce_pct = self.detect_bounce(prices, i, bounce_state)
                    if bounce_detected:
                        hedge_blocked = True
                        hedge_blocked_reason = "bounce_detected"

                # V1.2.7: Check market regime filter (post-drop bounce)
                if not hedge_blocked:
                    in_post_drop, drop_pct, recovery_pct = self.detect_post_drop_regime(prices, i)
                    if in_post_drop:
                        hedge_blocked = True
                        hedge_blocked_reason = "post_drop_regime"

            # Open hedge at 70% of peak
            if peak_upnl >= min_profit and not hedge_opened and upnl <= peak_upnl * self.TAKE_PROFIT_TRIGGER and not hedge_blocked:
                # V1.2.0: During spike mode, skip momentum filter for faster protection
                if not spike_mode:
                    # V1.1.0: Momentum filter simulation
                    # Simulate RSI being oversold if price recently dropped sharply
                    if use_improvements and i >= 14:
                        recent_prices = prices[max(0, i-14):i+1]
                        price_change = (recent_prices[-1] - recent_prices[0]) / recent_prices[0]
                        # If we're in a sharp downtrend (price dropped >10%), simulate oversold RSI
                        if price_change < -0.10 and side == 'long':
                            momentum_blocked = True
                            continue  # Skip hedge opening, price likely to bounce

                hedge_opened = True
                hedge_open_index = i  # V1.2.4: Track when hedge opened
                hedge_entry = price
                hedge_size = size * hedge_size_pct
                hedge_side = 'short' if side == 'long' else 'long'

                # V1.2.0: Calculate fast stop distance for spike mode
                if spike_mode and use_improvements:
                    # Estimate ATR from recent volatility
                    if i >= 5:
                        recent_ranges = [abs(prices[j] - prices[j-1]) for j in range(i-4, i+1)]
                        atr_estimate = np.mean(recent_ranges)
                        fast_stop_distance = atr_estimate * self.FAST_STOP_ATR_MULT

            if hedge_opened:
                h_upnl, h_pct = self.calc_upnl(hedge_entry, price, hedge_size, 'short' if side == 'long' else 'long')
                hedge_margin = (hedge_size * hedge_entry) / self.leverage
                hedge_pct = h_upnl / hedge_margin if hedge_margin > 0 else 0

                # V1.2.5: Calculate periods since hedge opened (used by all delay gates)
                periods_since_hedge = i - hedge_open_index

                # V1.1.0: Track peak hedge profit for trailing stop
                if hedge_pct > hedge_peak_pct:
                    hedge_peak_pct = hedge_pct

                # V1.1.0: Activate trailing stop at 3% profit
                if use_improvements and not trailing_stop_activated and hedge_pct >= self.TRAILING_STOP_ACTIVATION:
                    trailing_stop_activated = True

                # Gate 1: Profit target (10%)
                # V1.2.5: Add delay before profit taking can trigger (fixes dead_cat_bounce)
                profit_taking_delay_passed = (not self.PROFIT_TAKING_DELAY_ENABLED or
                                              periods_since_hedge >= self.PROFIT_TAKING_DELAY_PERIODS)
                if hedge_pct >= self.PROFIT_GATE and profit_taking_delay_passed:
                    final_pnl = upnl
                    hedge_pnl = h_upnl
                    exit_reason = "hedge_profit_10pct"
                    break

                # V1.1.0 Gate 2: Trailing stop (drops 2% from peak after activation)
                # V1.2.5: Add delay before trailing stop can trigger (fixes dead_cat_bounce)
                trailing_stop_delay_passed = (not self.TRAILING_STOP_DELAY_ENABLED or
                                              periods_since_hedge >= self.TRAILING_STOP_DELAY_PERIODS)
                if use_improvements and trailing_stop_activated and trailing_stop_delay_passed:
                    trailing_stop_level = hedge_peak_pct - self.TRAILING_STOP_DISTANCE
                    if hedge_pct <= trailing_stop_level:
                        final_pnl = upnl
                        hedge_pnl = h_upnl
                        exit_reason = "trailing_stop"
                        break

                # V1.2.0 Gate 3: Fast stop (ATR-based, spike mode only)
                if use_improvements and spike_mode and fast_stop_distance > 0:
                    hedge_side_actual = 'short' if side == 'long' else 'long'
                    if hedge_side_actual == 'short':
                        fast_stop_price = hedge_entry + fast_stop_distance
                        fast_stop_hit = price >= fast_stop_price
                    else:
                        fast_stop_price = hedge_entry - fast_stop_distance
                        fast_stop_hit = price <= fast_stop_price

                    if fast_stop_hit:
                        final_pnl = upnl
                        hedge_pnl = h_upnl
                        exit_reason = "fast_stop_atr"
                        break

                # Gate 4: Main drops to 50% of peak
                # V1.2.4: Add delay before main_drop can trigger (fixes dead_cat_bounce)
                # V1.2.6: Only trigger if hedge is also losing AND not recovering (fixes v_shape_recovery)
                main_drop_delay_passed = (not self.MAIN_DROP_DELAY_ENABLED or
                                          periods_since_hedge >= self.MAIN_DROP_DELAY_PERIODS)

                # V1.2.6: Check if hedge is losing before allowing main_drop gate
                hedge_loss_check_passed = (not self.MAIN_DROP_REQUIRES_HEDGE_LOSS or
                                           hedge_pct <= self.MAIN_DROP_HEDGE_LOSS_THRESHOLD)

                # V1.2.6: Recovery detection - block main_drop if price is recovering
                recovery_detected = False
                if self.RECOVERY_DETECTION_ENABLED and i >= self.RECOVERY_LOOKBACK_PERIODS:
                    # Check if current price is higher than average of lookback period
                    lookback_avg = np.mean(prices[i - self.RECOVERY_LOOKBACK_PERIODS:i])
                    if price > lookback_avg:
                        recovery_detected = True

                if peak_upnl > 0 and upnl <= peak_upnl * self.MAIN_DROP_GATE and main_drop_delay_passed and hedge_loss_check_passed and not recovery_detected:
                    final_pnl = upnl
                    hedge_pnl = h_upnl
                    exit_reason = "main_drop"
                    break

                # Gate 5: Stop loss on hedge (-5%)
                # V1.2.4: Add delay before stop loss can trigger (fixes dead_cat_bounce)
                stop_loss_delay_passed = (not self.STOP_LOSS_DELAY_ENABLED or
                                          periods_since_hedge >= self.STOP_LOSS_DELAY_PERIODS)

                if hedge_pct <= self.STOP_LOSS and stop_loss_delay_passed:
                    final_pnl = upnl
                    hedge_pnl = h_upnl
                    exit_reason = "hedge_stop_loss"
                    break

                hedge_pnl = h_upnl

            # Stop loss
            if pct <= -0.90:
                final_pnl = upnl
                exit_reason = "stop_loss"
                break

            final_pnl = upnl

        return StressTestResult(
            scenario=Scenario.FLASH_CRASH,  # Will be set by caller
            strategy="profit_hedge",
            initial_price=entry_price,
            final_price=prices[-1],
            peak_upnl=peak_upnl,
            final_pnl=final_pnl,
            hedge_pnl=hedge_pnl,
            combined_pnl=final_pnl + hedge_pnl,
            max_drawdown=max_drawdown,
            hedge_triggered=hedge_opened,
            exit_reason=exit_reason,
            price_path=prices.tolist()
        )

    def run_scenario(self, scenario: Scenario, num_runs: int = 50) -> Dict:
        """Run a specific scenario multiple times"""
        np.random.seed(42)

        traditional_results = []
        hedge_results = []

        # Generate price paths based on scenario
        for _ in range(num_runs):
            if scenario == Scenario.FLASH_CRASH:
                prices = self.simulator.generate_flash_crash()
            elif scenario == Scenario.RAPID_PUMP:
                prices = self.simulator.generate_rapid_pump()
            elif scenario == Scenario.PROLONGED_DOWNTREND:
                prices = self.simulator.generate_prolonged_downtrend()
            elif scenario == Scenario.PROLONGED_UPTREND:
                prices = self.simulator.generate_prolonged_uptrend()
            elif scenario == Scenario.HIGH_VOLATILITY:
                prices = self.simulator.generate_high_volatility()
            elif scenario == Scenario.LOW_VOLATILITY:
                prices = self.simulator.generate_low_volatility()
            elif scenario == Scenario.BLACK_SWAN_DOWN:
                prices = self.simulator.generate_black_swan_down()
            elif scenario == Scenario.BLACK_SWAN_UP:
                prices = self.simulator.generate_black_swan_up()
            elif scenario == Scenario.V_SHAPE_RECOVERY:
                prices = self.simulator.generate_v_shape_recovery()
            elif scenario == Scenario.DEAD_CAT_BOUNCE:
                prices = self.simulator.generate_dead_cat_bounce()
            else:
                continue

            # Run both strategies
            trad = self.simulate_traditional(prices)
            trad.scenario = scenario
            traditional_results.append(trad)

            hedge = self.simulate_profit_hedge(prices)
            hedge.scenario = scenario
            hedge_results.append(hedge)

        # Aggregate results
        trad_pnl = sum(r.combined_pnl for r in traditional_results)
        hedge_pnl = sum(r.combined_pnl for r in hedge_results)
        trad_drawdown = np.mean([r.max_drawdown for r in traditional_results])
        hedge_drawdown = np.mean([r.max_drawdown for r in hedge_results])

        hedge_triggers = sum(1 for r in hedge_results if r.hedge_triggered)
        hedge_exits = {}
        for r in hedge_results:
            hedge_exits[r.exit_reason] = hedge_exits.get(r.exit_reason, 0) + 1

        return {
            'scenario': scenario.value,
            'num_runs': num_runs,
            'traditional': {
                'total_pnl': trad_pnl,
                'avg_pnl': trad_pnl / num_runs,
                'avg_drawdown': trad_drawdown
            },
            'profit_hedge': {
                'total_pnl': hedge_pnl,
                'avg_pnl': hedge_pnl / num_runs,
                'avg_drawdown': hedge_drawdown,
                'hedge_triggers': hedge_triggers,
                'exit_reasons': hedge_exits
            },
            'improvement': (hedge_pnl - trad_pnl) / abs(trad_pnl) * 100 if trad_pnl != 0 else 0,
            'winner': 'profit_hedge' if hedge_pnl > trad_pnl else 'traditional'
        }

    def run_all_scenarios(self, num_runs: int = 50) -> Dict:
        """Run all stress test scenarios"""
        results = {}

        scenarios = [
            Scenario.FLASH_CRASH,
            Scenario.RAPID_PUMP,
            Scenario.PROLONGED_DOWNTREND,
            Scenario.PROLONGED_UPTREND,
            Scenario.HIGH_VOLATILITY,
            Scenario.LOW_VOLATILITY,
            Scenario.BLACK_SWAN_DOWN,
            Scenario.BLACK_SWAN_UP,
            Scenario.V_SHAPE_RECOVERY,
            Scenario.DEAD_CAT_BOUNCE
        ]

        for scenario in scenarios:
            print(f"  Running {scenario.value}...")
            results[scenario.value] = self.run_scenario(scenario, num_runs)

        return results

    def print_results(self, results: Dict):
        """Print stress test results"""
        print("\n" + "="*80)
        print("STRESS TEST RESULTS - PROFIT PROTECTION HEDGE")
        print("="*80)

        print(f"\n{'Scenario':<25} {'Traditional':<15} {'Hedge':<15} {'Improvement':<12} {'Winner':<12}")
        print("-"*80)

        total_trad = 0
        total_hedge = 0
        hedge_wins = 0

        for scenario, data in results.items():
            trad_pnl = data['traditional']['total_pnl']
            hedge_pnl = data['profit_hedge']['total_pnl']
            improvement = data['improvement']
            winner = data['winner']

            total_trad += trad_pnl
            total_hedge += hedge_pnl
            if winner == 'profit_hedge':
                hedge_wins += 1

            winner_icon = "✅" if winner == "profit_hedge" else "❌"
            print(f"{scenario:<25} ${trad_pnl:<14.2f} ${hedge_pnl:<14.2f} {improvement:>+10.1f}% {winner_icon} {winner}")

        print("-"*80)
        overall_improvement = (total_hedge - total_trad) / abs(total_trad) * 100 if total_trad != 0 else 0
        print(f"{'TOTAL':<25} ${total_trad:<14.2f} ${total_hedge:<14.2f} {overall_improvement:>+10.1f}%")
        print(f"\nHedge strategy wins: {hedge_wins}/{len(results)} scenarios ({hedge_wins/len(results)*100:.0f}%)")

        # Detailed breakdown
        print("\n" + "="*80)
        print("DETAILED SCENARIO ANALYSIS")
        print("="*80)

        for scenario, data in results.items():
            print(f"\n📊 {scenario.upper()}")
            print(f"   Traditional: ${data['traditional']['avg_pnl']:.2f} avg PnL, {data['traditional']['avg_drawdown']*100:.1f}% avg drawdown")
            print(f"   Profit Hedge: ${data['profit_hedge']['avg_pnl']:.2f} avg PnL, {data['profit_hedge']['avg_drawdown']*100:.1f}% avg drawdown")
            print(f"   Hedge triggers: {data['profit_hedge']['hedge_triggers']}/{data['num_runs']} ({data['profit_hedge']['hedge_triggers']/data['num_runs']*100:.0f}%)")
            if data['profit_hedge']['exit_reasons']:
                exits = ", ".join([f"{k}={v}" for k, v in data['profit_hedge']['exit_reasons'].items()])
                print(f"   Exit reasons: {exits}")

        # Recommendations
        print("\n" + "="*80)
        print("RECOMMENDATIONS")
        print("="*80)

        weak_scenarios = [s for s, d in results.items() if d['winner'] == 'traditional']
        strong_scenarios = [s for s, d in results.items() if d['winner'] == 'profit_hedge']

        if strong_scenarios:
            print(f"\n✅ STRONG SCENARIOS (hedge outperforms):")
            for s in strong_scenarios:
                print(f"   - {s}: {results[s]['improvement']:+.1f}%")

        if weak_scenarios:
            print(f"\n⚠️ WEAK SCENARIOS (traditional outperforms):")
            for s in weak_scenarios:
                print(f"   - {s}: {results[s]['improvement']:+.1f}%")

        return {
            'total_traditional': total_trad,
            'total_hedge': total_hedge,
            'overall_improvement': overall_improvement,
            'hedge_win_rate': hedge_wins / len(results),
            'weak_scenarios': weak_scenarios,
            'strong_scenarios': strong_scenarios
        }


def main():
    print("="*80)
    print("PROFIT PROTECTION HEDGE - STRESS TEST")
    print("="*80)
    print("Testing under extreme market conditions...\n")

    tester = ProfitProtectionHedgeStressTest()
    results = tester.run_all_scenarios(num_runs=50)
    summary = tester.print_results(results)

    # Save results
    with open('stress_test_results.json', 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n✅ Results saved to stress_test_results.json")

    return summary


if __name__ == "__main__":
    main()
