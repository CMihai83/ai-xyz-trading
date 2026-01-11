#!/usr/bin/env python3
"""
Historical Correction Analyzer Service
======================================
Analyzes historical price data to calculate optimal averaging parameters.

Key Concepts:
- ρ (rho): Percentage of price DROP that is retraced (not UPNL)
- Deeper drawdowns have HIGHER probability of correction (mean reversion)
- Step margins INCREASE with depth to capitalize on higher-probability reversals

Calculates per symbol:
- Initial margin (min $2, dynamically adjusted)
- Number of averaging steps
- Step margins (increasing with depth based on correction probability)
- Correction statistics from multiple timeframes

Author: AI-XYZ Trading System (Grok-assisted design)
Date: January 2026
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
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

        # Cache result
        if best_plan:
            self.cache[cache_key] = best_plan

            # Log the plan
            logger.info("Historical analysis complete",
                       symbol=symbol,
                       initial_margin=best_plan.initial_margin,
                       num_steps=best_plan.num_steps,
                       step_margins=best_plan.step_margins,
                       delta_worst=best_plan.delta_worst,
                       avg_correction=best_plan.avg_correction_pct)
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

        return {
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
            'timeframe': plan.timeframe_used
        }


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
