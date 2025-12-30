"""
Fibonacci Delta Calculator Service
Dynamic threshold calculation based on market conditions and multi-timeframe analysis
"""

import asyncio
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import structlog
import pandas as pd
import inspect

logger = structlog.get_logger(__name__)

@dataclass
class DynamicThreshold:
    """Dynamic threshold configuration for averaging"""
    level: int
    threshold_pct: float  # Percentage threshold (e.g., -5.0 for -5%)
    multiplier: float     # Position size multiplier
    confidence: float     # Confidence score (0-1)
    expected_bounce: float  # Expected bounce percentage
    fibonacci_level: float  # Fibonacci retracement level used

class FibonacciDeltaCalculator:
    """
    Calculates dynamic averaging thresholds based on:
    - Multi-timeframe analysis (15m, 1h, 4h)
    - Market regime detection
    - Fibonacci retracement levels
    - Volatility analysis
    """
    
    # Fibonacci retracement levels
    FIBONACCI_LEVELS = [0.236, 0.382, 0.500, 0.618, 0.786, 1.000]
    
    # Timeframes for analysis (in minutes)
    TIMEFRAMES = {
        '15m': 15,
        '1h': 60,
        '4h': 240
    }
    
    def __init__(self, exchange_client):
        """Initialize with exchange client for market data"""
        self.exchange = exchange_client
        self.cache = {}  # Cache for OHLCV data
        self.cache_ttl = 300  # 5 minutes
        
    async def calculate_dynamic_thresholds(
        self,
        symbol: str,
        entry_price: float,
        side: str,
        max_levels: int = 5
    ) -> List[DynamicThreshold]:
        """
        Calculate dynamic thresholds for averaging based on market conditions
        
        Args:
            symbol: Trading symbol
            entry_price: Position entry price
            side: 'long' or 'short'
            max_levels: Maximum averaging levels
            
        Returns:
            List of DynamicThreshold objects
        """
        try:
            # Get multi-timeframe market data
            market_data = await self._fetch_market_data(symbol)
            
            # Analyze market regime
            regime = self._analyze_market_regime(market_data)
            
            # Calculate volatility
            volatility = self._calculate_volatility(market_data)
            
            # Determine optimal delta based on market conditions
            optimal_delta = self._calculate_optimal_delta(
                entry_price, volatility, regime, side
            )
            
            # Generate thresholds using Fibonacci levels
            thresholds = self._generate_fibonacci_thresholds(
                entry_price, optimal_delta, side, max_levels, regime, volatility
            )
            
            logger.info(f"Calculated {len(thresholds)} dynamic thresholds for {symbol}",
                       regime=regime, volatility=f"{volatility:.2%}", 
                       optimal_delta=f"{optimal_delta:.2%}")
            
            return thresholds
            
        except Exception as e:
            logger.error(f"Failed to calculate dynamic thresholds: {e}")
            # Return fallback static thresholds
            return self._get_fallback_thresholds(entry_price, side, max_levels)
    
    async def _fetch_market_data(self, symbol: str) -> Dict:
        """Fetch OHLCV data for multiple timeframes"""
        market_data = {}
        
        for tf_name, tf_minutes in self.TIMEFRAMES.items():
            try:
                # Check cache
                cache_key = f"{symbol}_{tf_name}"
                if cache_key in self.cache:
                    cached_data, cache_time = self.cache[cache_key]
                    if (datetime.now() - cache_time).seconds < self.cache_ttl:
                        market_data[tf_name] = cached_data
                        continue
                
                # Fetch from exchange (handle both sync and async)
                if hasattr(self.exchange, 'fetch_ohlcv'):
                    # Check if it's an async exchange
                    import inspect
                    if inspect.iscoroutinefunction(self.exchange.fetch_ohlcv):
                        ohlcv = await self.exchange.fetch_ohlcv(
                            symbol, 
                            timeframe=tf_name,
                            limit=100
                        )
                    else:
                        # Synchronous exchange - call directly
                        ohlcv = self.exchange.fetch_ohlcv(
                            symbol, 
                            timeframe=tf_name,
                            limit=100
                        )
                else:
                    raise Exception("Exchange doesn't support fetch_ohlcv")
                
                # Convert to DataFrame for analysis
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                
                # Cache the data
                self.cache[cache_key] = (df, datetime.now())
                market_data[tf_name] = df
                
            except Exception as e:
                logger.warning(f"Failed to fetch {tf_name} data for {symbol}: {e}")
                
        return market_data
    
    def _analyze_market_regime(self, market_data: Dict) -> str:
        """
        Analyze market regime across timeframes
        Returns: 'strong_trend_up', 'trend_up', 'neutral', 'trend_down', 'strong_trend_down', 'high_volatility'
        """
        if not market_data:
            return 'neutral'
            
        regimes = []
        
        for tf_name, df in market_data.items():
            if df is None or df.empty:
                continue
                
            # Calculate indicators
            df['sma_20'] = df['close'].rolling(20).mean()
            df['sma_50'] = df['close'].rolling(50).mean()
            
            # Get latest values
            latest = df.iloc[-1]
            
            # Determine regime for this timeframe
            if pd.isna(latest['sma_20']) or pd.isna(latest['sma_50']):
                regime = 'neutral'
            elif latest['close'] > latest['sma_20'] * 1.02 and latest['sma_20'] > latest['sma_50'] * 1.01:
                regime = 'strong_trend_up'
            elif latest['close'] > latest['sma_20'] and latest['sma_20'] > latest['sma_50']:
                regime = 'trend_up'
            elif latest['close'] < latest['sma_20'] * 0.98 and latest['sma_20'] < latest['sma_50'] * 0.99:
                regime = 'strong_trend_down'
            elif latest['close'] < latest['sma_20'] and latest['sma_20'] < latest['sma_50']:
                regime = 'trend_down'
            else:
                regime = 'neutral'
                
            regimes.append(regime)
        
        # Combine regime assessments (majority vote)
        if not regimes:
            return 'neutral'
            
        from collections import Counter
        regime_counts = Counter(regimes)
        return regime_counts.most_common(1)[0][0]
    
    def _calculate_volatility(self, market_data: Dict) -> float:
        """Calculate average volatility across timeframes"""
        volatilities = []
        
        for tf_name, df in market_data.items():
            if df is None or df.empty:
                continue
                
            # Calculate ATR (Average True Range)
            df['high_low'] = df['high'] - df['low']
            df['high_close'] = abs(df['high'] - df['close'].shift())
            df['low_close'] = abs(df['low'] - df['close'].shift())
            df['true_range'] = df[['high_low', 'high_close', 'low_close']].max(axis=1)
            df['atr'] = df['true_range'].rolling(14).mean()
            
            # Volatility as percentage of price
            latest_atr = df['atr'].iloc[-1]
            latest_close = df['close'].iloc[-1]
            
            if pd.notna(latest_atr) and latest_close > 0:
                volatility = latest_atr / latest_close
                volatilities.append(volatility)
        
        return np.mean(volatilities) if volatilities else 0.02  # Default 2%
    
    def _calculate_optimal_delta(
        self, 
        entry_price: float,
        volatility: float,
        regime: str,
        side: str
    ) -> float:
        """
        Calculate optimal delta (max price movement to cover) based on market conditions
        
        Returns percentage (e.g., 0.30 for 30%)
        """
        # Base delta on volatility (cover 10-20x daily volatility)
        base_delta = volatility * 15
        
        # Adjust based on regime
        regime_multipliers = {
            'strong_trend_up': 1.5 if side == 'long' else 0.7,
            'trend_up': 1.2 if side == 'long' else 0.8,
            'neutral': 1.0,
            'trend_down': 0.8 if side == 'long' else 1.2,
            'strong_trend_down': 0.7 if side == 'long' else 1.5,
            'high_volatility': 1.3
        }
        
        multiplier = regime_multipliers.get(regime, 1.0)
        optimal_delta = base_delta * multiplier
        
        # Only apply a minimum (10%) and very high maximum (1000% = 10x)
        # Let the historical data determine the true maximum
        optimal_delta = max(0.10, min(10.00, optimal_delta))  # 1000% maximum
        
        return optimal_delta
    
    def _generate_fibonacci_thresholds(
        self,
        entry_price: float,
        delta: float,
        side: str,
        max_levels: int,
        regime: str,
        volatility: float
    ) -> List[DynamicThreshold]:
        """Generate thresholds using Fibonacci retracement levels"""
        thresholds = []
        
        # Use subset of Fibonacci levels based on max_levels
        fib_levels = self.FIBONACCI_LEVELS[:max_levels]
        
        for i, fib_level in enumerate(fib_levels):
            level = i + 1
            
            # Calculate threshold percentage based on Fibonacci level
            threshold_pct = -1 * fib_level * delta * 100  # Negative for losses
            
            # Calculate position multiplier (golden ratio based)
            base_multiplier = 1.618 ** (i * 0.5)  # Gradual increase
            
            # Adjust multiplier based on regime
            if regime in ['strong_trend_up', 'strong_trend_down']:
                base_multiplier *= 0.8  # More conservative in strong trends
            elif regime == 'high_volatility':
                base_multiplier *= 1.2  # More aggressive in volatile markets
                
            # Calculate confidence based on data quality and market clarity
            confidence = 0.9 - (i * 0.1)  # Decreasing confidence with depth
            if regime == 'neutral':
                confidence *= 0.8  # Lower confidence in unclear markets
                
            # Expected bounce calculation
            expected_bounce = fib_level * delta * 100 * 0.5  # 50% retracement of move
            
            threshold = DynamicThreshold(
                level=level,
                threshold_pct=threshold_pct,
                multiplier=round(base_multiplier, 2),
                confidence=round(confidence, 2),
                expected_bounce=round(expected_bounce, 2),
                fibonacci_level=fib_level
            )
            
            thresholds.append(threshold)
        
        return thresholds
    
    def _get_fallback_thresholds(
        self, 
        entry_price: float,
        side: str,
        max_levels: int
    ) -> List[DynamicThreshold]:
        """Return static fallback thresholds when dynamic calculation fails"""
        # Conservative static thresholds
        static_configs = [
            (-2.0, 1.0, 0.7),   # -2%, 1x multiplier
            (-4.0, 1.5, 0.6),   # -4%, 1.5x multiplier
            (-6.0, 2.0, 0.5),   # -6%, 2x multiplier
            (-9.0, 3.0, 0.4),   # -9%, 3x multiplier
            (-12.0, 4.0, 0.3),  # -12%, 4x multiplier
        ]
        
        thresholds = []
        for i in range(min(max_levels, len(static_configs))):
            threshold_pct, multiplier, confidence = static_configs[i]
            
            threshold = DynamicThreshold(
                level=i + 1,
                threshold_pct=threshold_pct,
                multiplier=multiplier,
                confidence=confidence,
                expected_bounce=abs(threshold_pct) * 0.5,
                fibonacci_level=self.FIBONACCI_LEVELS[i] if i < len(self.FIBONACCI_LEVELS) else 1.0
            )
            thresholds.append(threshold)
        
        logger.warning(f"Using fallback static thresholds for {side} position")
        return thresholds
    
    def get_threshold_summary(self, thresholds: List[DynamicThreshold]) -> Dict:
        """Get summary of calculated thresholds"""
        if not thresholds:
            return {}
            
        return {
            'levels': len(thresholds),
            'deepest_threshold': f"{thresholds[-1].threshold_pct:.1f}%",
            'max_multiplier': max(t.multiplier for t in thresholds),
            'avg_confidence': round(np.mean([t.confidence for t in thresholds]), 2)
        }