#!/usr/bin/env python3
"""
Backtesting Service Integration
Provides historical analysis and optimal parameter estimation

FIXED (Jan 2026): Replaced mock random data with REAL historical analysis
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import json
import os
import ccxt
from dotenv import load_dotenv

load_dotenv()

# Initialize exchange for real data fetching
_exchange = None

def get_exchange():
    """Get or create exchange instance"""
    global _exchange
    if _exchange is None:
        _exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {'defaultType': 'swap'}
        })
    return _exchange


class BacktestingService:
    """
    Analyzes historical data to optimize trading parameters

    FIXED: Now uses REAL historical data instead of random mock values
    """

    # Timeframe to minutes mapping
    TIMEFRAME_MINUTES = {
        '1m': 1, '5m': 5, '15m': 15, '30m': 30,
        '1h': 60, '4h': 240, '1d': 1440
    }

    def __init__(self):
        self.historical_data = {}
        self.performance_metrics = {}
        self.analysis_cache = {}  # Cache to avoid repeated API calls
        self.cache_ttl = 300  # 5 minute cache TTL

    def _fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data from exchange"""
        try:
            exchange = get_exchange()
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"  ⚠️ Failed to fetch OHLCV for {symbol}: {e}")
            return None

    def _get_cache_key(self, symbol: str, timeframe: str, days: int) -> str:
        """Generate cache key"""
        return f"{symbol}:{timeframe}:{days}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid"""
        if cache_key not in self.analysis_cache:
            return False
        cached = self.analysis_cache[cache_key]
        age = (datetime.now() - cached['timestamp']).total_seconds()
        return age < self.cache_ttl

    def analyze_coin_performance(self, symbol: str, timeframe: str = '1d', days: int = 30) -> Dict:
        """
        Analyze historical performance of a coin using REAL data

        FIXED: No longer uses random mock data - fetches actual OHLCV and calculates:
        - Real volatility from price returns
        - Real trend strength from price movement
        - Real support/resistance from historical prices
        """
        cache_key = self._get_cache_key(symbol, timeframe, days)

        # Check cache first
        if self._is_cache_valid(cache_key):
            return self.analysis_cache[cache_key]['data']

        # Calculate candles needed based on timeframe
        tf_minutes = self.TIMEFRAME_MINUTES.get(timeframe, 60)
        candles_per_day = 1440 / tf_minutes
        limit = int(days * candles_per_day)

        # Fetch real data
        df = self._fetch_ohlcv(symbol, timeframe, limit)

        if df is None or len(df) < 20:
            # Fallback to conservative defaults if data fetch fails
            return self._get_fallback_analysis(symbol)

        # Calculate REAL volatility (annualized standard deviation of returns)
        returns = df['close'].pct_change().dropna()
        daily_volatility = returns.std() * np.sqrt(candles_per_day)  # Daily volatility
        annualized_volatility = daily_volatility * np.sqrt(365)  # Annualized

        # Calculate REAL trend strength (normalized price change over period)
        price_change = (df['close'].iloc[-1] - df['close'].iloc[0]) / df['close'].iloc[0]
        trend_strength = min(1.0, abs(price_change) / (daily_volatility * np.sqrt(len(df)) + 0.001))

        # Calculate REAL average daily range
        df['daily_range'] = (df['high'] - df['low']) / df['close'] * 100
        avg_daily_range = df['daily_range'].mean()

        # Calculate REAL support/resistance levels from historical data
        rolling_low = df['low'].rolling(window=20).min()
        rolling_high = df['high'].rolling(window=20).max()
        current_price = df['close'].iloc[-1]

        # Support levels as percentage below current price
        support_levels = []
        for pct in [0.05, 0.10, 0.15]:  # 5%, 10%, 15% below
            support_price = current_price * (1 - pct)
            # Check if there's historical support near this level
            nearby_lows = df[df['low'] <= support_price * 1.02]['low']
            if len(nearby_lows) > 0:
                support_levels.append(1 - pct)
            else:
                support_levels.append(1 - pct * 1.2)  # Weaker support

        # Resistance levels as percentage above current price
        resistance_levels = []
        for pct in [0.05, 0.10, 0.15]:
            resistance_price = current_price * (1 + pct)
            nearby_highs = df[df['high'] >= resistance_price * 0.98]['high']
            if len(nearby_highs) > 0:
                resistance_levels.append(1 + pct)
            else:
                resistance_levels.append(1 + pct * 1.2)

        # Calculate reversal probability from mean reversion analysis
        # Higher volatility + lower trend = higher reversal probability
        reversal_probability = 0.3 + (daily_volatility * 2) - (trend_strength * 0.2)
        reversal_probability = max(0.2, min(0.8, reversal_probability))

        # Determine best timeframe based on volatility
        if daily_volatility > 0.08:  # >8% daily vol
            best_timeframe = '1h'
        elif daily_volatility > 0.04:  # 4-8% daily vol
            best_timeframe = '4h'
        else:
            best_timeframe = '1d'

        result = {
            'volatility_pct': float(daily_volatility * 100),
            'annualized_volatility_pct': float(annualized_volatility * 100),
            'trend_strength': float(trend_strength),
            'trend_direction': 'bullish' if price_change > 0 else 'bearish',
            'avg_daily_range': float(avg_daily_range),
            'reversal_probability': float(reversal_probability),
            'support_levels': support_levels,
            'resistance_levels': resistance_levels,
            'avg_hold_time': int(24 * (1 + trend_strength)),
            'best_timeframe': best_timeframe,
            'data_points': len(df),
            'data_source': 'real_ohlcv'
        }

        # Cache the result
        self.analysis_cache[cache_key] = {
            'data': result,
            'timestamp': datetime.now()
        }

        return result

    def _get_fallback_analysis(self, symbol: str) -> Dict:
        """Conservative fallback when real data unavailable"""
        base_symbol = symbol.split('/')[0]

        # Use conservative estimates based on asset class
        if base_symbol in ['BTC', 'ETH']:
            volatility = 0.04  # 4% daily
            trend_strength = 0.3
        elif base_symbol in ['SOL', 'AVAX', 'LINK', 'DOT']:
            volatility = 0.06  # 6% daily
            trend_strength = 0.4
        else:
            volatility = 0.08  # 8% daily for altcoins
            trend_strength = 0.5

        return {
            'volatility_pct': volatility * 100,
            'annualized_volatility_pct': volatility * 100 * np.sqrt(365),
            'trend_strength': trend_strength,
            'trend_direction': 'unknown',
            'avg_daily_range': volatility * 100 * 1.5,
            'reversal_probability': 0.5,
            'support_levels': [0.95, 0.90, 0.85],
            'resistance_levels': [1.05, 1.10, 1.15],
            'avg_hold_time': 24,
            'best_timeframe': '4h',
            'data_points': 0,
            'data_source': 'fallback_estimate'
        }

    def calculate_optimal_delta(self, symbol: str, current_price: float, leverage: int) -> Dict:
        """
        Calculate optimal delta based on historical analysis

        FIXED: Now uses unified LiquidationCalculator for consistent liquidation math
        """
        from liquidation_calculator import get_liquidation_calculator

        analysis = self.analyze_coin_performance(symbol)

        # Base delta calculation from REAL volatility
        base_delta_pct = analysis['volatility_pct'] * 0.1  # 10% of volatility

        # Adjust for leverage (higher leverage needs smaller delta)
        leverage_factor = 1 / np.sqrt(leverage / 5)  # 5x leverage = factor 1
        adjusted_delta_pct = base_delta_pct * leverage_factor

        # Adjust for trend strength
        trend_factor = 1 + (analysis['trend_strength'] - 0.5) * 0.5
        final_delta_pct = adjusted_delta_pct * trend_factor

        # Calculate absolute delta
        delta_absolute = current_price * (final_delta_pct / 100)

        # FIXED: Use unified LiquidationCalculator for consistent liquidation distance
        calc = get_liquidation_calculator()
        liq_price = calc.calculate_liquidation_price(current_price, 'long', leverage)
        liquidation_distance_pct = abs(current_price - liq_price) / current_price

        return {
            'delta_percentage': final_delta_pct,
            'delta_absolute': delta_absolute,
            'liquidation_distance_pct': liquidation_distance_pct,
            'liquidation_price': liq_price,
            'safe_averaging_range': liquidation_distance_pct * 0.8,  # 80% of liquidation distance
            'volatility_factor': analysis['volatility_pct'] / 100,
            'trend_factor': trend_factor,
            'recommended_timeframe': analysis['best_timeframe'],
            'confidence_score': min(1.0, analysis['reversal_probability'] + 0.2),
            'data_source': analysis.get('data_source', 'unknown')
        }

class DynamicDeltaEngine:
    """
    Dynamic delta adjustment based on real-time market conditions
    """

    def __init__(self, backtesting_service: BacktestingService):
        self.backtesting = backtesting_service
        self.market_memory = {}
        self.volatility_windows = {}

    def calculate_adaptive_delta(self, symbol: str, market_context: Dict, position_data: Dict) -> Dict:
        """
        Calculate adaptive delta based on current market conditions
        """
        current_price = position_data.get('current_price', 0)
        leverage = position_data.get('leverage', 8)

        # Get base delta from backtesting
        base_delta = self.backtesting.calculate_optimal_delta(symbol, current_price, leverage)

        # Adjust for real-time conditions
        volatility = market_context.get('volatility', base_delta['volatility_factor'])
        volume = market_context.get('volume_ratio', 1.0)
        spread = market_context.get('spread_pct', 0.1)

        # Volatility adjustment
        if volatility > 1.5:  # High volatility
            delta_multiplier = 1.5
        elif volatility < 0.7:  # Low volatility
            delta_multiplier = 0.7
        else:
            delta_multiplier = 1.0

        # Volume adjustment
        if volume > 2.0:  # High volume
            delta_multiplier *= 1.2
        elif volume < 0.5:  # Low volume
            delta_multiplier *= 0.8

        # Apply adjustments
        adaptive_delta_pct = base_delta['delta_percentage'] * delta_multiplier
        adaptive_delta_abs = current_price * (adaptive_delta_pct / 100)

        return {
            'delta_percentage': adaptive_delta_pct,
            'delta_absolute': adaptive_delta_abs,
            'volatility_factor': base_delta.get('volatility_factor', volatility),  # Include volatility factor
            'adjustment_factors': {
                'volatility': delta_multiplier,
                'volume': volume,
                'spread': spread
            },
            'market_conditions': market_context,
            'confidence_score': base_delta['confidence_score'] * (1 + (1 - volatility) * 0.2)
        }

class FibonacciAveragingOptimizer:
    """
    Optimizes Fibonacci averaging steps with dynamic delta allocation
    """

    def __init__(self, backtesting_service: BacktestingService):
        self.backtesting = backtesting_service
        self.delta_engine = DynamicDeltaEngine(backtesting_service)

    def generate_optimal_averaging_plan(self, symbol: str, position_data: Dict, market_context: Dict) -> Dict:
        """
        Generate optimal averaging plan with steps allocated along delta range
        """
        current_price = position_data.get('current_price', 0)
        entry_price = position_data.get('entry_price', current_price)
        leverage = position_data.get('leverage', 8)

        # Get adaptive delta
        delta_info = self.delta_engine.calculate_adaptive_delta(symbol, market_context, position_data)
        delta_pct = delta_info['delta_percentage']

        # Calculate liquidation distance
        liquidation_distance = (1.0 / leverage) - 0.005  # 0.5% maintenance margin

        # Safe averaging range (80% of distance to liquidation)
        safe_range_pct = liquidation_distance * 0.8
        safe_range_absolute = current_price * (safe_range_pct / 100)

        # Calculate number of averaging steps
        # More steps for higher volatility coins
        volatility = delta_info['volatility_factor']
        if volatility > 1.2:  # High volatility
            max_steps = 5
        elif volatility > 0.8:  # Medium volatility
            max_steps = 4
        else:  # Low volatility
            max_steps = 3

        # Allocate steps along the delta range with Fibonacci logic
        # Bigger multipliers towards the end where reversal probability is higher
        base_multipliers = [1, 1, 2, 3, 5, 8, 13][:max_steps]

        # Calculate step positions along the safe range
        step_positions = []
        thresholds = []

        for i in range(max_steps):
            # Position steps with more spacing towards the end
            position_pct = safe_range_pct * (i + 1) / max_steps
            position_pct *= (1 + i * 0.2)  # Extra spacing for later steps

            threshold_pct = -position_pct  # Negative for averaging down
            threshold_price = entry_price * (1 + threshold_pct / 100)

            step_positions.append({
                'step': i + 1,
                'threshold_pct': threshold_pct,
                'threshold_price': threshold_price,
                'multiplier': base_multipliers[i],
                'position_in_range': position_pct / safe_range_pct
            })

            thresholds.append(abs(threshold_pct) / 100)  # Convert to decimal for config

        return {
            'max_averaging_steps': max_steps,
            'step_positions': step_positions,
            'thresholds': thresholds,
            'fibonacci_multipliers': base_multipliers[:max_steps],
            'safe_averaging_range_pct': safe_range_pct,
            'safe_averaging_range_absolute': safe_range_absolute,
            'liquidation_distance_pct': liquidation_distance,
            'delta_info': delta_info,
            'volatility_adjustment': volatility > 1.0,
            'market_adapted': True
        }