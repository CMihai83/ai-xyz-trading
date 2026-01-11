#!/usr/bin/env python3
"""
Historical Correction Analyzer Service (v2.0 - Grok Enhanced)
==============================================================
Analyzes historical price data to calculate optimal averaging parameters.

Key Concepts:
- ρ (rho): Percentage of price DROP that is retraced (not UPNL)
- Deeper drawdowns have HIGHER probability of correction (mean reversion)
- Step margins INCREASE with depth to capitalize on higher-probability reversals

NEW in v2.0 (Grok Consortium Integration):
- Support Zone Detection (VWAP, Fibonacci retracement levels)
- CSSI (Correction-Support Strength Index) calculation
- Risk-adjusted position sizing based on delta_worst
- Dynamic step margin adjustments based on proximity to support

Calculates per symbol:
- Initial margin (min $2, dynamically adjusted)
- Number of averaging steps
- Step margins (increasing with depth based on correction probability)
- Correction statistics from multiple timeframes
- Support zone proximity and CSSI scores

Author: AI-XYZ Trading System (Grok-assisted design)
Date: January 2026
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import structlog
import json
import os

logger = structlog.get_logger(__name__)


@dataclass
class CorrectionStats:
    """Statistics for price corrections at a given drawdown level"""
    drawdown_bucket: str
    avg_retracement: float  # Average % of drop that is retraced
    correction_prob: float  # Probability of meaningful correction (>10%)
    sample_count: int


@dataclass
class SupportZone:
    """Support zone analysis result (Grok v2.0)"""
    symbol: str
    current_price: float
    # Fibonacci retracement levels (from recent swing high/low)
    fib_236: float  # 23.6% retracement
    fib_382: float  # 38.2% retracement
    fib_500: float  # 50% retracement
    fib_618: float  # 61.8% retracement (golden ratio)
    # VWAP levels
    vwap: float  # Current VWAP
    vwap_lower_1std: float  # VWAP - 1 std
    vwap_lower_2std: float  # VWAP - 2 std
    # Bollinger Bands
    bb_lower: float  # Lower Bollinger Band (20, 2)
    bb_lower_2std: float  # Lower BB at 2.5 std
    # Calculated support strength
    nearest_support: float  # Nearest support level
    proximity_to_support: float  # 0-1 (1 = at support)
    support_type: str  # 'fib_618', 'vwap', 'bb_lower', etc.


@dataclass
class CSSI:
    """Correction-Support Strength Index (Grok v2.0)"""
    symbol: str
    cssi_score: float  # Main CSSI score (higher = stronger reversal signal)
    correction_probability: float  # Historical correction probability
    support_proximity: float  # How close to support (0-1)
    risk_factor: float  # Risk adjustment based on delta_worst
    recommended_action: str  # 'AVERAGE_IN', 'HOLD', 'REDUCE'
    step_multiplier: float  # Multiplier for step margin (0.5-2.0)


@dataclass
class DynamicAveragingPlan:
    """Complete averaging plan for a position"""
    symbol: str
    initial_margin: float  # Starting margin ($2 minimum)
    num_steps: int  # Number of averaging steps
    step_margins: List[float]  # Margin for each step (increases with depth)
    step_thresholds: List[float]  # Drawdown % triggers for each step
    correction_probs: List[float]  # Probability of correction at each step
    avg_correction_pct: float  # Average expected correction %
    delta_worst: float  # Worst case drawdown from historical data
    timeframe_used: str  # Best timeframe for this symbol
    total_capital: float  # Total capital allocated
    confidence: float  # Confidence in the analysis (0-1)
    # NEW in v2.0 (Grok Integration)
    support_zone: Optional[SupportZone] = None  # Current support zone analysis
    cssi: Optional[CSSI] = None  # Current CSSI score
    risk_profile: str = "MEDIUM"  # LOW, MEDIUM, HIGH based on delta_worst
    cssi_adjusted_margins: List[float] = field(default_factory=list)  # Margins adjusted by CSSI


class HistoricalCorrectionAnalyzer:
    """
    Analyzes historical data to calculate optimal averaging parameters.

    Called when opening a position to determine:
    - Initial position size
    - Number and size of averaging steps
    - Correction probabilities at each level
    """

    # Timeframes to analyze (lower timeframes for correction patterns)
    TIMEFRAMES = ['1m', '5m', '15m']

    # Minimum data points required for reliable analysis
    MIN_DATA_POINTS = 500

    # Drawdown threshold to identify significant moves
    MIN_DRAWDOWN_THRESHOLD = 0.01  # 1%

    # Minimum retracement to count as "correction"
    MIN_CORRECTION_THRESHOLD = 0.10  # 10% of the drop

    # Capital constraints
    TOTAL_CAPITAL = 25.0  # Total capital per position
    MIN_INITIAL_MARGIN = 2.0  # Minimum initial margin
    MAX_INITIAL_MARGIN = 8.0  # Maximum initial margin
    AVERAGING_CAPITAL = 20.0  # Capital reserved for averaging

    def __init__(self, exchange, cache_dir: str = '/tmp/correction_cache'):
        """
        Initialize the analyzer.

        Args:
            exchange: CCXT exchange instance
            cache_dir: Directory to cache historical analysis
        """
        self.exchange = exchange
        self.cache_dir = cache_dir
        self.cache = {}  # In-memory cache
        self.cache_ttl = 3600  # Cache TTL in seconds (1 hour)

        # Create cache directory if needed
        os.makedirs(cache_dir, exist_ok=True)

        logger.info("HistoricalCorrectionAnalyzer initialized",
                   timeframes=self.TIMEFRAMES,
                   total_capital=self.TOTAL_CAPITAL)

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 1000) -> Optional[pd.DataFrame]:
        """
        Fetch historical OHLCV data for a symbol.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT:USDT')
            timeframe: Candle timeframe ('1m', '5m', '15m')
            limit: Number of candles to fetch

        Returns:
            DataFrame with OHLCV data or None if failed
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            if not ohlcv or len(ohlcv) < self.MIN_DATA_POINTS:
                logger.warning("Insufficient data", symbol=symbol,
                             timeframe=timeframe, count=len(ohlcv) if ohlcv else 0)
                return None

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df

        except Exception as e:
            logger.error("Failed to fetch OHLCV", symbol=symbol,
                        timeframe=timeframe, error=str(e))
            return None

    def calculate_drawdowns_retracements(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Identify drawdown events and their subsequent retracements.

        Args:
            df: OHLCV DataFrame

        Returns:
            DataFrame with drawdown events and retracement statistics
        """
        if df is None or len(df) < 10:
            return pd.DataFrame()

        # Calculate returns and cumulative returns
        df = df.copy()
        df['returns'] = df['close'].pct_change()
        df['cumulative_return'] = (1 + df['returns']).cumprod() - 1
        df['peak'] = df['cumulative_return'].cummax()
        df['drawdown'] = (df['cumulative_return'] - df['peak']) / (1 + df['peak'])

        # Identify drawdown events
        drawdown_events = []
        in_drawdown = False
        start_idx = 0
        max_drawdown_idx = 0
        max_drawdown_value = 0

        for i in range(1, len(df)):
            current_dd = df['drawdown'].iloc[i]

            # Start of new drawdown
            if current_dd <= -self.MIN_DRAWDOWN_THRESHOLD and not in_drawdown:
                in_drawdown = True
                start_idx = i
                max_drawdown_idx = i
                max_drawdown_value = current_dd

            # Track deepest point of drawdown
            elif in_drawdown and current_dd < max_drawdown_value:
                max_drawdown_idx = i
                max_drawdown_value = current_dd

            # End of drawdown (price recovering)
            elif in_drawdown and current_dd > max_drawdown_value + 0.005:  # 0.5% recovery threshold
                # Calculate retracement
                start_price = df['close'].iloc[start_idx]
                bottom_price = df['close'].iloc[max_drawdown_idx]
                current_price = df['close'].iloc[i]

                # Drawdown depth (as positive number)
                drawdown_depth = abs(max_drawdown_value)

                # Retracement as % of drop recovered
                drop_amount = start_price - bottom_price
                recovery_amount = current_price - bottom_price

                if drop_amount > 0:
                    retracement_pct = recovery_amount / drop_amount
                else:
                    retracement_pct = 0

                drawdown_events.append({
                    'depth': drawdown_depth,
                    'retracement': retracement_pct,
                    'duration_bars': i - start_idx,
                    'start_price': start_price,
                    'bottom_price': bottom_price,
                    'recovery_price': current_price
                })

                in_drawdown = False
                max_drawdown_value = 0

        return pd.DataFrame(drawdown_events)

    def calculate_correction_stats(self, drawdown_df: pd.DataFrame) -> List[CorrectionStats]:
        """
        Calculate correction statistics per drawdown bucket.

        Args:
            drawdown_df: DataFrame with drawdown events

        Returns:
            List of CorrectionStats per bucket
        """
        if drawdown_df.empty:
            return []

        # Define drawdown buckets (1%, 2%, 3%, ..., 10%+)
        bins = [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.08, 0.10, 0.15, 0.20, 1.0]
        labels = ['1-2%', '2-3%', '3-4%', '4-5%', '5-6%', '6-8%', '8-10%', '10-15%', '15-20%', '20%+']

        drawdown_df = drawdown_df.copy()
        drawdown_df['bucket'] = pd.cut(drawdown_df['depth'], bins=bins, labels=labels)

        stats = []
        for bucket in labels:
            bucket_data = drawdown_df[drawdown_df['bucket'] == bucket]
            if len(bucket_data) > 0:
                stats.append(CorrectionStats(
                    drawdown_bucket=bucket,
                    avg_retracement=bucket_data['retracement'].mean(),
                    correction_prob=(bucket_data['retracement'] > self.MIN_CORRECTION_THRESHOLD).mean(),
                    sample_count=len(bucket_data)
                ))

        return stats

    def fit_correction_model(self, drawdown_df: pd.DataFrame) -> Tuple[float, float, float]:
        """
        Fit logistic-style model for correction probability.

        P(correction | depth) = 1 / (1 + exp(-β0 - β1*depth - β2*depth²))

        We use a simpler approach: linear regression on log-odds when possible,
        otherwise use empirical probabilities.

        Args:
            drawdown_df: DataFrame with drawdown events

        Returns:
            Tuple of (β0, β1, β2) coefficients
        """
        if drawdown_df.empty or len(drawdown_df) < 20:
            # Default coefficients for insufficient data
            # These give ~50% prob at 5% drawdown, ~80% at 10%
            return (-1.0, 20.0, 0.0)

        try:
            # Calculate empirical probabilities per bucket
            drawdown_df = drawdown_df.copy()
            drawdown_df['corrected'] = (drawdown_df['retracement'] > self.MIN_CORRECTION_THRESHOLD).astype(int)

            # Group by depth and calculate probability
            drawdown_df['depth_bucket'] = (drawdown_df['depth'] * 100).round(0) / 100
            probs = drawdown_df.groupby('depth_bucket')['corrected'].mean()

            if len(probs) < 3:
                return (-1.0, 20.0, 0.0)

            # Fit simple linear model on depth vs probability
            X = np.array(list(probs.index)).reshape(-1, 1)
            y = np.array(list(probs.values))

            # Avoid log(0) issues
            y = np.clip(y, 0.01, 0.99)

            # Calculate log-odds for logistic regression
            log_odds = np.log(y / (1 - y))

            # Simple linear fit
            if len(X) >= 2:
                coeffs = np.polyfit(X.flatten(), log_odds, 1)
                β1 = coeffs[0]  # Slope
                β0 = coeffs[1]  # Intercept
                β2 = 0.0  # No quadratic term in simple model
            else:
                β0, β1, β2 = -1.0, 20.0, 0.0

            return (β0, β1, β2)

        except Exception as e:
            logger.warning("Failed to fit correction model", error=str(e))
            return (-1.0, 20.0, 0.0)

    def predict_correction_prob(self, depth: float, coeffs: Tuple[float, float, float]) -> float:
        """
        Predict correction probability at a given drawdown depth.

        Args:
            depth: Drawdown depth as decimal (e.g., 0.05 for 5%)
            coeffs: Model coefficients (β0, β1, β2)

        Returns:
            Probability of correction (0-1)
        """
        β0, β1, β2 = coeffs
        log_odds = β0 + β1 * depth + β2 * depth ** 2
        prob = 1 / (1 + np.exp(-log_odds))
        return min(max(prob, 0.1), 0.95)  # Clamp between 10% and 95%

    def calculate_averaging_plan(
        self,
        symbol: str,
        stats: List[CorrectionStats],
        coeffs: Tuple[float, float, float],
        delta_worst: float,
        avg_correction: float,
        timeframe: str
    ) -> DynamicAveragingPlan:
        """
        Calculate complete averaging plan based on historical analysis.

        Args:
            symbol: Trading pair
            stats: Correction statistics
            coeffs: Model coefficients
            delta_worst: Worst case drawdown
            avg_correction: Average correction percentage
            timeframe: Timeframe used for analysis

        Returns:
            Complete averaging plan
        """
        # Calculate number of steps based on delta and correction
        # More steps for larger deltas, fewer for smaller
        if delta_worst < 0.03:
            num_steps = 2
        elif delta_worst < 0.05:
            num_steps = 3
        elif delta_worst < 0.08:
            num_steps = 4
        elif delta_worst < 0.12:
            num_steps = 5
        else:
            num_steps = 6

        # Calculate step thresholds (Fibonacci-spaced from entry to worst case)
        # Deeper steps are closer together (more aggressive at depth)
        fib_ratios = [0.236, 0.382, 0.5, 0.618, 0.786, 0.9][:num_steps]
        step_thresholds = [delta_worst * r for r in fib_ratios]

        # Calculate correction probability at each step
        correction_probs = [self.predict_correction_prob(t, coeffs) for t in step_thresholds]

        # Calculate step margins - INCREASING with depth based on probability
        # Higher correction probability = deploy MORE capital
        base_margin = self.AVERAGING_CAPITAL / sum(correction_probs)
        step_margins_raw = [base_margin * p for p in correction_probs]

        # Normalize to ensure total = AVERAGING_CAPITAL
        total_raw = sum(step_margins_raw)
        step_margins = [m * self.AVERAGING_CAPITAL / total_raw for m in step_margins_raw]

        # Calculate initial margin based on number of steps
        # More steps = smaller initial (save for averaging)
        # Fewer steps = larger initial (fewer averaging opportunities)
        initial_margin_ratio = 1.0 - (num_steps / 10.0)  # 0.4 to 0.8
        initial_margin = self.MIN_INITIAL_MARGIN + (self.MAX_INITIAL_MARGIN - self.MIN_INITIAL_MARGIN) * initial_margin_ratio
        initial_margin = round(initial_margin, 2)

        # Ensure total capital doesn't exceed limit
        total_capital = initial_margin + sum(step_margins)
        if total_capital > self.TOTAL_CAPITAL:
            scale_factor = (self.TOTAL_CAPITAL - initial_margin) / sum(step_margins)
            step_margins = [m * scale_factor for m in step_margins]

        # Calculate confidence based on sample size
        total_samples = sum(s.sample_count for s in stats) if stats else 0
        confidence = min(1.0, total_samples / 100.0)

        return DynamicAveragingPlan(
            symbol=symbol,
            initial_margin=initial_margin,
            num_steps=num_steps,
            step_margins=[round(m, 2) for m in step_margins],
            step_thresholds=[round(t, 4) for t in step_thresholds],
            correction_probs=[round(p, 3) for p in correction_probs],
            avg_correction_pct=round(avg_correction, 3),
            delta_worst=round(delta_worst, 4),
            timeframe_used=timeframe,
            total_capital=round(initial_margin + sum(step_margins), 2),
            confidence=round(confidence, 2)
        )

    # =========================================================================
    # GROK v2.0: Support Zone and CSSI Methods
    # =========================================================================

    def calculate_vwap(self, df: pd.DataFrame) -> Tuple[float, float, float]:
        """
        Calculate VWAP and standard deviation bands.

        VWAP = Σ(Typical Price × Volume) / Σ(Volume)

        Args:
            df: OHLCV DataFrame

        Returns:
            Tuple of (vwap, vwap_lower_1std, vwap_lower_2std)
        """
        if df is None or len(df) < 20:
            return (0, 0, 0)

        df = df.copy()
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3
        df['tp_volume'] = df['typical_price'] * df['volume']
        df['cumulative_volume'] = df['volume'].cumsum()
        df['cumulative_tp_volume'] = df['tp_volume'].cumsum()

        # VWAP
        df['vwap'] = df['cumulative_tp_volume'] / df['cumulative_volume']

        # Standard deviation of price from VWAP
        df['vwap_diff'] = df['typical_price'] - df['vwap']
        df['vwap_diff_sq'] = df['vwap_diff'] ** 2
        vwap_std = np.sqrt(df['vwap_diff_sq'].rolling(window=20).mean())

        current_vwap = df['vwap'].iloc[-1]
        current_std = vwap_std.iloc[-1] if not np.isnan(vwap_std.iloc[-1]) else df['close'].std() * 0.1

        return (
            current_vwap,
            current_vwap - 1.5 * current_std,
            current_vwap - 2.5 * current_std
        )

    def calculate_fibonacci_levels(self, df: pd.DataFrame, lookback: int = 100) -> Dict[str, float]:
        """
        Calculate Fibonacci retracement levels from recent swing high/low.

        Args:
            df: OHLCV DataFrame
            lookback: Number of candles to find swing points

        Returns:
            Dict with Fib levels (23.6%, 38.2%, 50%, 61.8%)
        """
        if df is None or len(df) < lookback:
            return {}

        recent_data = df.iloc[-lookback:]
        swing_high = recent_data['high'].max()
        swing_low = recent_data['low'].min()

        range_size = swing_high - swing_low

        return {
            'swing_high': swing_high,
            'swing_low': swing_low,
            'fib_236': swing_low + 0.236 * range_size,
            'fib_382': swing_low + 0.382 * range_size,
            'fib_500': swing_low + 0.500 * range_size,
            'fib_618': swing_low + 0.618 * range_size,
            'fib_786': swing_low + 0.786 * range_size
        }

    def calculate_bollinger_bands(self, df: pd.DataFrame, period: int = 20) -> Tuple[float, float, float]:
        """
        Calculate Bollinger Bands.

        Args:
            df: OHLCV DataFrame
            period: MA period (default 20)

        Returns:
            Tuple of (middle, lower_2std, lower_2.5std)
        """
        if df is None or len(df) < period:
            return (0, 0, 0)

        df = df.copy()
        df['sma'] = df['close'].rolling(window=period).mean()
        df['std'] = df['close'].rolling(window=period).std()

        current_sma = df['sma'].iloc[-1]
        current_std = df['std'].iloc[-1]

        return (
            current_sma,
            current_sma - 2.0 * current_std,
            current_sma - 2.5 * current_std
        )

    def calculate_support_zones(self, symbol: str, df: pd.DataFrame) -> Optional[SupportZone]:
        """
        Calculate comprehensive support zone analysis.

        Combines VWAP, Fibonacci, and Bollinger Bands to identify
        key support levels and proximity.

        Args:
            symbol: Trading pair
            df: OHLCV DataFrame

        Returns:
            SupportZone object or None
        """
        if df is None or len(df) < 100:
            return None

        current_price = df['close'].iloc[-1]

        # Calculate all indicators
        vwap, vwap_1std, vwap_2std = self.calculate_vwap(df)
        fib_levels = self.calculate_fibonacci_levels(df)
        bb_mid, bb_lower, bb_lower_25 = self.calculate_bollinger_bands(df)

        if not fib_levels:
            return None

        # Collect all support levels with their types
        support_levels = [
            (fib_levels.get('fib_618', 0), 'fib_618'),
            (fib_levels.get('fib_500', 0), 'fib_500'),
            (fib_levels.get('fib_382', 0), 'fib_382'),
            (vwap_1std, 'vwap_1std'),
            (vwap_2std, 'vwap_2std'),
            (bb_lower, 'bb_lower'),
            (bb_lower_25, 'bb_lower_25'),
            (fib_levels.get('swing_low', 0), 'swing_low')
        ]

        # Filter valid supports below current price
        valid_supports = [(level, stype) for level, stype in support_levels
                         if 0 < level < current_price]

        if not valid_supports:
            # Price is at or below all supports
            nearest_support = fib_levels.get('swing_low', current_price * 0.95)
            support_type = 'swing_low'
            proximity = 0.95  # Already at support
        else:
            # Find nearest support
            nearest_support, support_type = max(valid_supports, key=lambda x: x[0])

            # Calculate proximity (0 = far, 1 = at support)
            distance_pct = (current_price - nearest_support) / current_price
            proximity = max(0, 1 - distance_pct * 10)  # 10% distance = 0 proximity

        return SupportZone(
            symbol=symbol,
            current_price=current_price,
            fib_236=fib_levels.get('fib_236', 0),
            fib_382=fib_levels.get('fib_382', 0),
            fib_500=fib_levels.get('fib_500', 0),
            fib_618=fib_levels.get('fib_618', 0),
            vwap=vwap,
            vwap_lower_1std=vwap_1std,
            vwap_lower_2std=vwap_2std,
            bb_lower=bb_lower,
            bb_lower_2std=bb_lower_25,
            nearest_support=nearest_support,
            proximity_to_support=round(proximity, 3),
            support_type=support_type
        )

    def calculate_multi_timeframe_confirmation(
        self,
        symbol: str,
        timeframes: List[str] = ['5m', '15m', '1h']
    ) -> Dict[str, any]:
        """
        Confirm support zones across multiple timeframes.

        Higher confirmation when multiple timeframes agree on support.

        Args:
            symbol: Trading pair
            timeframes: List of timeframes to analyze

        Returns:
            Dict with MTF confirmation data
        """
        confirmations = []
        support_zones = {}

        for tf in timeframes:
            try:
                df = self.fetch_ohlcv(symbol, tf, limit=500)
                if df is None:
                    continue

                support_zone = self.calculate_support_zones(symbol, df)
                if support_zone:
                    support_zones[tf] = support_zone

                    # Count as confirmation if proximity > 0.5
                    if support_zone.proximity_to_support > 0.5:
                        confirmations.append({
                            'timeframe': tf,
                            'support_type': support_zone.support_type,
                            'proximity': support_zone.proximity_to_support,
                            'nearest_support': support_zone.nearest_support
                        })
            except Exception as e:
                logger.warning(f"MTF analysis failed for {tf}", error=str(e))

        # Calculate MTF score
        mtf_score = len(confirmations) / len(timeframes) if timeframes else 0

        # Find consensus support level (average of confirmed supports)
        if confirmations:
            consensus_support = np.mean([c['nearest_support'] for c in confirmations])
            dominant_type = max(set(c['support_type'] for c in confirmations),
                               key=lambda x: [c['support_type'] for c in confirmations].count(x))
        else:
            consensus_support = 0
            dominant_type = 'none'

        return {
            'mtf_score': round(mtf_score, 2),
            'confirmations': confirmations,
            'num_confirmations': len(confirmations),
            'consensus_support': round(consensus_support, 6) if consensus_support else 0,
            'dominant_support_type': dominant_type,
            'support_zones': support_zones
        }

    def calculate_cssi(
        self,
        symbol: str,
        historical_correction_pct: float,
        support_zone: SupportZone,
        delta_worst: float,
        max_delta_in_portfolio: float = 0.20
    ) -> CSSI:
        """
        Calculate Correction-Support Strength Index.

        CSSI = (Historical_Correction% / 100) × Proximity_to_Support × Risk_Factor

        Args:
            symbol: Trading pair
            historical_correction_pct: Average historical correction %
            support_zone: Current support zone analysis
            delta_worst: Worst case drawdown for this symbol
            max_delta_in_portfolio: Maximum delta in portfolio for normalization

        Returns:
            CSSI object with score and recommendations
        """
        # Extract components
        correction_factor = historical_correction_pct / 100.0
        proximity = support_zone.proximity_to_support if support_zone else 0.5

        # Risk factor: Lower delta_worst = higher factor (safer to average)
        # Formula: 1 - (delta_worst / max_delta)
        risk_factor = max(0.3, 1 - (delta_worst / max_delta_in_portfolio))

        # Calculate CSSI
        cssi_score = correction_factor * proximity * risk_factor

        # Determine action and step multiplier
        if cssi_score >= 1.5:
            action = 'AVERAGE_IN_AGGRESSIVE'
            step_multiplier = min(2.0, 1.0 + cssi_score * 0.3)
        elif cssi_score >= 1.0:
            action = 'AVERAGE_IN'
            step_multiplier = min(1.5, 1.0 + cssi_score * 0.2)
        elif cssi_score >= 0.5:
            action = 'HOLD'
            step_multiplier = 1.0
        else:
            action = 'REDUCE'
            step_multiplier = max(0.5, cssi_score)

        return CSSI(
            symbol=symbol,
            cssi_score=round(cssi_score, 3),
            correction_probability=round(correction_factor, 3),
            support_proximity=round(proximity, 3),
            risk_factor=round(risk_factor, 3),
            recommended_action=action,
            step_multiplier=round(step_multiplier, 3)
        )

    def get_risk_profile(self, delta_worst: float) -> str:
        """
        Determine risk profile based on delta_worst.

        Args:
            delta_worst: Worst case drawdown

        Returns:
            Risk profile string ('LOW', 'MEDIUM', 'HIGH')
        """
        if delta_worst < 0.05:
            return 'LOW'
        elif delta_worst < 0.12:
            return 'MEDIUM'
        else:
            return 'HIGH'

    def _get_cssi_action(self, cssi_score: float) -> str:
        """
        Get recommended action based on CSSI score.

        Args:
            cssi_score: CSSI score value

        Returns:
            Action string ('AVERAGE_IN_AGGRESSIVE', 'AVERAGE_IN', 'HOLD', 'REDUCE')
        """
        if cssi_score >= 1.5:
            return 'AVERAGE_IN_AGGRESSIVE'
        elif cssi_score >= 1.0:
            return 'AVERAGE_IN'
        elif cssi_score >= 0.5:
            return 'HOLD'
        else:
            return 'REDUCE'

    def _get_cssi_multiplier(self, cssi_score: float) -> float:
        """
        Get step multiplier based on CSSI score.

        Args:
            cssi_score: CSSI score value

        Returns:
            Step multiplier (0.5 to 2.0)
        """
        if cssi_score >= 1.5:
            return round(min(2.0, 1.0 + cssi_score * 0.3), 3)
        elif cssi_score >= 1.0:
            return round(min(1.5, 1.0 + cssi_score * 0.2), 3)
        elif cssi_score >= 0.5:
            return 1.0
        else:
            return round(max(0.5, cssi_score), 3)

    def adjust_margins_by_cssi(
        self,
        step_margins: List[float],
        cssi: CSSI,
        total_capital: float = 20.0
    ) -> List[float]:
        """
        Adjust step margins based on CSSI score.

        Args:
            step_margins: Original step margins
            cssi: CSSI analysis result
            total_capital: Total averaging capital

        Returns:
            Adjusted step margins
        """
        multiplier = cssi.step_multiplier

        # Apply multiplier
        adjusted = [m * multiplier for m in step_margins]

        # Normalize to ensure total doesn't exceed capital
        total = sum(adjusted)
        if total > total_capital:
            scale = total_capital / total
            adjusted = [m * scale for m in adjusted]

        return [round(m, 2) for m in adjusted]

    # =========================================================================
    # End of Grok v2.0 Methods
    # =========================================================================

    def analyze_symbol(self, symbol: str, use_cache: bool = True) -> Optional[DynamicAveragingPlan]:
        """
        Perform complete historical analysis for a symbol.

        This is the main entry point - call when opening a position.

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT:USDT')
            use_cache: Whether to use cached results

        Returns:
            DynamicAveragingPlan or None if analysis fails
        """
        # Check cache first
        cache_key = f"{symbol}_{datetime.now().strftime('%Y%m%d%H')}"
        if use_cache and cache_key in self.cache:
            logger.info("Using cached analysis", symbol=symbol)
            return self.cache[cache_key]

        logger.info("Analyzing symbol for averaging plan", symbol=symbol)

        best_plan = None
        best_confidence = 0

        # Analyze each timeframe
        for timeframe in self.TIMEFRAMES:
            try:
                # Fetch historical data
                df = self.fetch_ohlcv(symbol, timeframe, limit=1000)
                if df is None:
                    continue

                # Calculate drawdowns and retracements
                drawdown_df = self.calculate_drawdowns_retracements(df)
                if drawdown_df.empty:
                    continue

                # Calculate correction statistics
                stats = self.calculate_correction_stats(drawdown_df)
                if not stats:
                    continue

                # Fit correction probability model
                coeffs = self.fit_correction_model(drawdown_df)

                # Calculate worst case delta (95th percentile)
                delta_worst = drawdown_df['depth'].quantile(0.95)

                # Calculate average correction
                avg_correction = drawdown_df['retracement'].mean()

                # Generate averaging plan
                plan = self.calculate_averaging_plan(
                    symbol=symbol,
                    stats=stats,
                    coeffs=coeffs,
                    delta_worst=delta_worst,
                    avg_correction=avg_correction,
                    timeframe=timeframe
                )

                # Keep best plan (highest confidence)
                if plan.confidence > best_confidence:
                    best_plan = plan
                    best_confidence = plan.confidence

                logger.info("Timeframe analysis complete",
                           symbol=symbol,
                           timeframe=timeframe,
                           confidence=plan.confidence,
                           num_steps=plan.num_steps)

            except Exception as e:
                logger.error("Failed to analyze timeframe",
                            symbol=symbol,
                            timeframe=timeframe,
                            error=str(e))

        # Cache result and enhance with Grok v2.0 features
        if best_plan:
            # =========================================================
            # GROK v2.0: Add Support Zone and CSSI Analysis
            # =========================================================
            try:
                # Fetch fresh data for support zone analysis
                df_support = self.fetch_ohlcv(symbol, '15m', limit=500)

                if df_support is not None:
                    # Calculate support zones
                    support_zone = self.calculate_support_zones(symbol, df_support)
                    best_plan.support_zone = support_zone

                    # Calculate CSSI
                    if support_zone:
                        cssi = self.calculate_cssi(
                            symbol=symbol,
                            historical_correction_pct=best_plan.avg_correction_pct * 100,
                            support_zone=support_zone,
                            delta_worst=best_plan.delta_worst
                        )
                        best_plan.cssi = cssi

                        # Adjust margins by CSSI
                        best_plan.cssi_adjusted_margins = self.adjust_margins_by_cssi(
                            best_plan.step_margins,
                            cssi,
                            self.AVERAGING_CAPITAL
                        )

                        logger.info("CSSI analysis complete",
                                   symbol=symbol,
                                   cssi_score=cssi.cssi_score,
                                   action=cssi.recommended_action,
                                   support_type=support_zone.support_type,
                                   proximity=support_zone.proximity_to_support)

                    # Determine risk profile
                    best_plan.risk_profile = self.get_risk_profile(best_plan.delta_worst)

                # Multi-timeframe confirmation - validates support across timeframes
                mtf_data = self.calculate_multi_timeframe_confirmation(
                    symbol,
                    timeframes=['5m', '15m', '1h']
                )

                if mtf_data and mtf_data.get('mtf_score', 0) > 0:
                    mtf_score = mtf_data['mtf_score']
                    num_confirms = mtf_data.get('num_confirmations', 0)
                    dominant_support = mtf_data.get('dominant_support_type', 'none')

                    logger.info("MTF confirmation complete",
                               symbol=symbol,
                               mtf_score=mtf_score,
                               num_confirmations=num_confirms,
                               dominant_support=dominant_support)

                    # Boost CSSI if multiple timeframes confirm support
                    if best_plan.cssi and mtf_score >= 0.67:  # 2/3 timeframes agree
                        mtf_boost = 1.0 + (mtf_score * 0.2)  # Up to 20% boost
                        original_cssi = best_plan.cssi.cssi_score
                        boosted_cssi = original_cssi * mtf_boost

                        # Update CSSI with MTF boost
                        best_plan.cssi = CSSI(
                            symbol=best_plan.cssi.symbol,
                            cssi_score=round(boosted_cssi, 3),
                            correction_probability=best_plan.cssi.correction_probability,
                            support_proximity=best_plan.cssi.support_proximity,
                            risk_factor=best_plan.cssi.risk_factor,
                            recommended_action=self._get_cssi_action(boosted_cssi),
                            step_multiplier=self._get_cssi_multiplier(boosted_cssi)
                        )

                        # Recalculate adjusted margins with boosted CSSI
                        best_plan.cssi_adjusted_margins = self.adjust_margins_by_cssi(
                            best_plan.step_margins,
                            best_plan.cssi,
                            self.AVERAGING_CAPITAL
                        )

                        logger.info("MTF boost applied to CSSI",
                                   symbol=symbol,
                                   original_cssi=original_cssi,
                                   boosted_cssi=boosted_cssi,
                                   mtf_boost=f"{(mtf_boost-1)*100:.0f}%")

            except Exception as e:
                logger.warning("Grok v2.0 analysis failed (using base plan)",
                             symbol=symbol, error=str(e))
            # =========================================================

            self.cache[cache_key] = best_plan

            # Log the plan
            logger.info("Historical analysis complete",
                       symbol=symbol,
                       initial_margin=best_plan.initial_margin,
                       num_steps=best_plan.num_steps,
                       step_margins=best_plan.step_margins,
                       delta_worst=best_plan.delta_worst,
                       avg_correction=best_plan.avg_correction_pct,
                       risk_profile=best_plan.risk_profile,
                       cssi_score=best_plan.cssi.cssi_score if best_plan.cssi else 'N/A')
        else:
            logger.warning("No valid analysis for symbol", symbol=symbol)

        return best_plan

    def get_averaging_params(self, symbol: str) -> Dict:
        """
        Get averaging parameters for integration with existing system.

        Returns dict compatible with current Fibonacci config format.

        Args:
            symbol: Trading pair

        Returns:
            Dict with averaging parameters or None if analysis fails
        """
        plan = self.analyze_symbol(symbol)

        if not plan:
            return None

        # Build base params
        params = {
            'symbol': symbol,
            'initial_margin': plan.initial_margin,
            'max_averaging_steps': plan.num_steps,
            'averaging_thresholds': [-t for t in plan.step_thresholds],  # Negative for drawdowns
            'position_multipliers': [m / plan.initial_margin for m in plan.step_margins],
            'step_margins': plan.step_margins,
            'correction_probs': plan.correction_probs,
            'avg_correction_pct': plan.avg_correction_pct,
            'delta_worst': plan.delta_worst,
            'total_capital': plan.total_capital,
            'confidence': plan.confidence,
            'source': 'historical_correction_analyzer',
            'timeframe': plan.timeframe_used,
            'risk_profile': plan.risk_profile
        }

        # Add Grok v2.0 CSSI data if available
        if plan.cssi:
            params['cssi'] = {
                'score': plan.cssi.cssi_score,
                'correction_probability': plan.cssi.correction_probability,
                'support_proximity': plan.cssi.support_proximity,
                'risk_factor': plan.cssi.risk_factor,
                'recommended_action': plan.cssi.recommended_action,
                'step_multiplier': plan.cssi.step_multiplier
            }
            # Use CSSI-adjusted margins if available
            if plan.cssi_adjusted_margins:
                params['cssi_adjusted_margins'] = plan.cssi_adjusted_margins

        # Add support zone data if available
        if plan.support_zone:
            params['support_zone'] = {
                'current_price': plan.support_zone.current_price,
                'nearest_support': plan.support_zone.nearest_support,
                'support_type': plan.support_zone.support_type,
                'proximity': plan.support_zone.proximity_to_support,
                'fib_618': plan.support_zone.fib_618,
                'vwap': plan.support_zone.vwap,
                'bb_lower': plan.support_zone.bb_lower
            }

        return params


# Singleton instance
_analyzer_instance = None


def get_correction_analyzer(exchange) -> HistoricalCorrectionAnalyzer:
    """Get or create singleton analyzer instance."""
    global _analyzer_instance
    if _analyzer_instance is None:
        _analyzer_instance = HistoricalCorrectionAnalyzer(exchange)
    return _analyzer_instance


# Test/example usage
if __name__ == "__main__":
    import ccxt

    print("=" * 70)
    print("HISTORICAL CORRECTION ANALYZER - TEST")
    print("=" * 70)

    # Initialize exchange
    exchange = ccxt.bitget({
        'options': {'defaultType': 'swap'}
    })

    analyzer = HistoricalCorrectionAnalyzer(exchange)

    # Test symbols
    test_symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']

    for symbol in test_symbols:
        print(f"\n{'='*50}")
        print(f"Analyzing: {symbol}")
        print('='*50)

        params = analyzer.get_averaging_params(symbol)

        if params:
            print(f"Initial Margin: ${params['initial_margin']:.2f}")
            print(f"Num Steps: {params['max_averaging_steps']}")
            print(f"Step Margins: {params['step_margins']}")
            print(f"Thresholds: {[f'{t*100:.1f}%' for t in params['averaging_thresholds']]}")
            print(f"Correction Probs: {[f'{p*100:.0f}%' for p in params['correction_probs']]}")
            print(f"Avg Correction: {params['avg_correction_pct']*100:.1f}%")
            print(f"Worst Delta: {params['delta_worst']*100:.1f}%")
            print(f"Confidence: {params['confidence']*100:.0f}%")
            print(f"Total Capital: ${params['total_capital']:.2f}")
        else:
            print("Analysis failed - would use Fibonacci fallback")
