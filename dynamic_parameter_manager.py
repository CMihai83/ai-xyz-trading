#!/usr/bin/env python3
"""
Dynamic Parameter Manager for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Adjusts trading parameters in real-time based on market volatility:
- Averaging trigger threshold
- Surplus dump thresholds (stage 1 & 2)
- Hedge profit threshold

Uses ATR-based volatility detection with market regime classification.

Author: Claude + Grok Consortium
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Tuple, Optional
import json
import os
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DynamicParameterManager:
    """
    Manages dynamic adjustment of trading parameters based on market conditions.

    Market Regimes:
    - HIGH_VOLATILITY: ATR ratio > 2.0, aggressive parameters
    - TRENDING: Strong directional move, let profits run
    - RANGING: Low volatility sideways, conservative
    - NORMAL: Default parameters
    """

    # Base parameters (our optimized defaults)
    BASE_PARAMS = {
        'averaging_trigger': -0.35,      # -35% UPNL triggers averaging
        'surplus_dump_stage1': 0.85,     # 85% of peak
        'surplus_dump_stage2': 0.40,     # 40% of peak
        'hedge_profit_threshold': 5.0,   # $5 profit before hedging
        'stop_loss': -0.90               # -90% UPNL stop loss
    }

    # ATR periods for volatility detection
    ATR_FAST_PERIOD = 5
    ATR_SLOW_PERIOD = 14

    # Volatility thresholds
    HIGH_VOL_THRESHOLD = 2.0    # ATR ratio for high volatility
    LOW_VOL_THRESHOLD = 0.7     # ATR ratio for low volatility

    # Regime-specific parameter multipliers
    REGIME_PARAMS = {
        'HIGH_VOLATILITY': {
            'averaging_trigger': 0.70,    # More aggressive: -35% * 0.70 = -24.5%
            'surplus_dump_stage1': 0.94,  # Earlier exit: 85% * 0.94 = 80%
            'surplus_dump_stage2': 1.125, # Earlier final: 40% * 1.125 = 45%
            'hedge_profit_threshold': 0.0,# Immediate hedge in high vol (fallback)
            'stop_loss': 0.67             # Tighter stop: -90% * 0.67 = -60%
        },
        'TRENDING': {
            'averaging_trigger': 1.15,    # More patient: -35% * 1.15 = -40%
            'surplus_dump_stage1': 1.06,  # Let profits run: 85% * 1.06 = 90%
            'surplus_dump_stage2': 1.25,  # Later final: 40% * 1.25 = 50%
            'hedge_profit_threshold': 1.5,# Higher threshold in trends
            'stop_loss': 1.0              # Normal stop
        },
        'RANGING': {
            'averaging_trigger': 1.30,    # Very patient: -35% * 1.30 = -45%
            'surplus_dump_stage1': 1.0,   # Normal
            'surplus_dump_stage2': 0.875, # Quicker final: 40% * 0.875 = 35%
            'hedge_profit_threshold': 0.6,# Lower threshold in range
            'stop_loss': 1.1              # Wider stop in ranging
        },
        'NORMAL': {
            'averaging_trigger': 1.0,
            'surplus_dump_stage1': 1.0,
            'surplus_dump_stage2': 1.0,
            'hedge_profit_threshold': 1.0,
            'stop_loss': 1.0
        }
    }

    def __init__(self, exchange=None):
        """
        Initialize the Dynamic Parameter Manager.

        Args:
            exchange: CCXT exchange instance (optional, can set later)
        """
        self.exchange = exchange
        self.current_regime = 'NORMAL'
        self.current_params = self.BASE_PARAMS.copy()
        self.volatility_cache = {}  # symbol -> (timestamp, atr_ratio)
        self.cache_ttl = 60  # Cache volatility for 60 seconds
        self.last_update = {}
        self.regime_history = []

    def set_exchange(self, exchange):
        """Set the exchange instance for API calls."""
        self.exchange = exchange

    def calculate_atr_ratio(self, symbol: str, ohlcv_data: list = None) -> Tuple[float, str]:
        """
        Calculate ATR ratio (fast/slow) to detect volatility regime.

        Args:
            symbol: Trading symbol
            ohlcv_data: Pre-fetched OHLCV data (optional)

        Returns:
            Tuple of (atr_ratio, regime)
        """
        try:
            # Check cache first
            if symbol in self.volatility_cache:
                cached_time, cached_ratio = self.volatility_cache[symbol]
                if (datetime.now() - cached_time).total_seconds() < self.cache_ttl:
                    regime = self._ratio_to_regime(cached_ratio)
                    return cached_ratio, regime

            # Fetch OHLCV if not provided
            if ohlcv_data is None:
                if self.exchange is None:
                    return 1.0, 'NORMAL'
                ohlcv_data = self.exchange.fetch_ohlcv(
                    symbol, '5m',
                    limit=max(self.ATR_FAST_PERIOD, self.ATR_SLOW_PERIOD) + 5
                )

            if not ohlcv_data or len(ohlcv_data) < self.ATR_SLOW_PERIOD + 1:
                return 1.0, 'NORMAL'

            # Calculate True Range for each candle
            true_ranges = []
            for i in range(1, len(ohlcv_data)):
                high = ohlcv_data[i][2]
                low = ohlcv_data[i][3]
                prev_close = ohlcv_data[i-1][4]

                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)

            if len(true_ranges) < self.ATR_SLOW_PERIOD:
                return 1.0, 'NORMAL'

            # Calculate fast and slow ATR
            atr_fast = np.mean(true_ranges[-self.ATR_FAST_PERIOD:])
            atr_slow = np.mean(true_ranges[-self.ATR_SLOW_PERIOD:])

            if atr_slow <= 0:
                return 1.0, 'NORMAL'

            atr_ratio = atr_fast / atr_slow

            # Cache the result
            self.volatility_cache[symbol] = (datetime.now(), atr_ratio)

            # Determine regime
            regime = self._ratio_to_regime(atr_ratio)

            return atr_ratio, regime

        except Exception as e:
            logger.error(f"Error calculating ATR ratio for {symbol}: {e}")
            return 1.0, 'NORMAL'

    def _ratio_to_regime(self, atr_ratio: float) -> str:
        """Convert ATR ratio to market regime."""
        if atr_ratio >= self.HIGH_VOL_THRESHOLD:
            return 'HIGH_VOLATILITY'
        elif atr_ratio <= self.LOW_VOL_THRESHOLD:
            return 'RANGING'
        elif 1.3 <= atr_ratio < self.HIGH_VOL_THRESHOLD:
            return 'TRENDING'
        else:
            return 'NORMAL'

    def detect_trend_direction(self, ohlcv_data: list) -> Tuple[str, float]:
        """
        Detect trend direction and strength.

        Returns:
            Tuple of (direction: 'UP'/'DOWN'/'SIDEWAYS', strength: 0-1)
        """
        if not ohlcv_data or len(ohlcv_data) < 20:
            return 'SIDEWAYS', 0.0

        closes = [c[4] for c in ohlcv_data]

        # Simple trend detection using SMA crossover
        sma_short = np.mean(closes[-5:])
        sma_long = np.mean(closes[-20:])

        pct_diff = (sma_short - sma_long) / sma_long * 100

        if pct_diff > 2.0:
            return 'UP', min(abs(pct_diff) / 10, 1.0)
        elif pct_diff < -2.0:
            return 'DOWN', min(abs(pct_diff) / 10, 1.0)
        else:
            return 'SIDEWAYS', 0.0

    def calculate_dynamic_params(self, symbol: str, ohlcv_data: list = None) -> Dict:
        """
        Calculate dynamic parameters for a symbol based on current market conditions.

        Args:
            symbol: Trading symbol
            ohlcv_data: Pre-fetched OHLCV data (optional)

        Returns:
            Dict with adjusted parameters
        """
        # Get volatility regime
        atr_ratio, regime = self.calculate_atr_ratio(symbol, ohlcv_data)

        # Get regime multipliers
        multipliers = self.REGIME_PARAMS.get(regime, self.REGIME_PARAMS['NORMAL'])

        # Calculate adjusted parameters
        dynamic_params = {
            'averaging_trigger': self.BASE_PARAMS['averaging_trigger'] * multipliers['averaging_trigger'],
            'surplus_dump_stage1': self.BASE_PARAMS['surplus_dump_stage1'] * multipliers['surplus_dump_stage1'],
            'surplus_dump_stage2': self.BASE_PARAMS['surplus_dump_stage2'] * multipliers['surplus_dump_stage2'],
            'hedge_profit_threshold': self.BASE_PARAMS['hedge_profit_threshold'] * multipliers['hedge_profit_threshold'],
            'stop_loss': self.BASE_PARAMS['stop_loss'] * multipliers['stop_loss']
        }

        # Apply bounds
        dynamic_params['averaging_trigger'] = max(-0.50, min(-0.15, dynamic_params['averaging_trigger']))
        dynamic_params['surplus_dump_stage1'] = max(0.70, min(0.95, dynamic_params['surplus_dump_stage1']))
        dynamic_params['surplus_dump_stage2'] = max(0.30, min(0.60, dynamic_params['surplus_dump_stage2']))
        dynamic_params['hedge_profit_threshold'] = max(0.0, min(10.0, dynamic_params['hedge_profit_threshold']))
        dynamic_params['stop_loss'] = max(-0.95, min(-0.50, dynamic_params['stop_loss']))

        # Add metadata
        dynamic_params['regime'] = regime
        dynamic_params['atr_ratio'] = atr_ratio
        dynamic_params['symbol'] = symbol
        dynamic_params['timestamp'] = datetime.now().isoformat()

        # Track regime changes
        if regime != self.current_regime:
            self.regime_history.append({
                'from': self.current_regime,
                'to': regime,
                'timestamp': datetime.now().isoformat(),
                'symbol': symbol
            })
            self.current_regime = regime
            logger.info(f"[{symbol}] Regime changed: {self.regime_history[-1]['from']} -> {regime}")

        self.current_params = dynamic_params
        self.last_update[symbol] = datetime.now()

        return dynamic_params

    def get_params_for_position(self, symbol: str, position_data: Dict = None) -> Dict:
        """
        Get dynamic parameters optimized for a specific position.

        Args:
            symbol: Trading symbol
            position_data: Position information (optional)

        Returns:
            Dict with adjusted parameters
        """
        params = self.calculate_dynamic_params(symbol)

        # Additional position-specific adjustments
        if position_data:
            # If position is already in profit, be more conservative with stop
            upnl_pct = position_data.get('upnl_pct', 0)
            if upnl_pct > 5.0:
                params['stop_loss'] = max(params['stop_loss'], -0.60)

            # If position has many averaging steps, widen stop
            avg_steps = position_data.get('averaging_steps', 0)
            if avg_steps >= 3:
                params['stop_loss'] = min(params['stop_loss'] * 1.1, -0.50)

        return params

    def should_update_params(self, symbol: str, force: bool = False) -> bool:
        """Check if parameters should be recalculated."""
        if force:
            return True

        if symbol not in self.last_update:
            return True

        time_since_update = (datetime.now() - self.last_update[symbol]).total_seconds()
        return time_since_update >= self.cache_ttl

    def get_status_summary(self) -> Dict:
        """Get summary of current dynamic parameter state."""
        return {
            'current_regime': self.current_regime,
            'current_params': self.current_params,
            'cache_entries': len(self.volatility_cache),
            'regime_changes': len(self.regime_history),
            'recent_changes': self.regime_history[-5:] if self.regime_history else []
        }

    def format_params_log(self, params: Dict) -> str:
        """Format parameters for logging."""
        return (
            f"[{params.get('regime', 'N/A')}] "
            f"Avg:{params.get('averaging_trigger', 0)*100:.0f}% "
            f"SD1:{params.get('surplus_dump_stage1', 0)*100:.0f}% "
            f"SD2:{params.get('surplus_dump_stage2', 0)*100:.0f}% "
            f"Hedge:${params.get('hedge_profit_threshold', 0):.1f} "
            f"(ATR:{params.get('atr_ratio', 0):.2f}x)"
        )


# Singleton instance for easy import
_manager_instance = None

def get_dynamic_param_manager(exchange=None) -> DynamicParameterManager:
    """Get or create the singleton DynamicParameterManager instance."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = DynamicParameterManager(exchange)
    elif exchange is not None:
        _manager_instance.set_exchange(exchange)
    return _manager_instance


if __name__ == "__main__":
    # Test the dynamic parameter manager
    print("=" * 60)
    print("DYNAMIC PARAMETER MANAGER TEST")
    print("=" * 60)

    manager = DynamicParameterManager()

    # Test regime mappings
    print("\nRegime Parameter Mappings:")
    for regime, multipliers in manager.REGIME_PARAMS.items():
        print(f"\n{regime}:")
        for param, mult in multipliers.items():
            base = manager.BASE_PARAMS[param]
            adjusted = base * mult
            print(f"  {param}: {base} * {mult} = {adjusted:.3f}")

    # Test with mock data
    print("\n" + "=" * 60)
    print("Mock Test Results:")

    # Simulate different volatility scenarios
    scenarios = [
        ("LOW_VOL", 0.6),
        ("NORMAL", 1.0),
        ("MODERATE", 1.4),
        ("HIGH_VOL", 2.5)
    ]

    for name, ratio in scenarios:
        regime = manager._ratio_to_regime(ratio)
        manager.volatility_cache['TEST/USDT:USDT'] = (datetime.now(), ratio)
        params = manager.calculate_dynamic_params('TEST/USDT:USDT')
        print(f"\n{name} (ATR ratio: {ratio}):")
        print(f"  {manager.format_params_log(params)}")
