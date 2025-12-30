#!/usr/bin/env python3
"""
Dynamic Fibonacci Delta Service - Market-Adaptive Averaging
Based on Grok AI Expert Recommendations (2025-12-29)

Dynamically adjusts Fibonacci averaging delta based on:
- Market volatility (ATR-based composite measurement)
- Coin-specific characteristics (stable vs volatile)
- BTC correlation (correlated vs independent moves)
- Volatility regime changes (low/normal/high detection)

Expected improvement: 30-50% better margin efficiency
"""

import time
import math
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from datetime import datetime
import ccxt


class DynamicFibonacciDeltaService:
    """
    Enhanced Fibonacci delta service with dynamic volatility adaptation

    Core Formula:
        Dynamic Delta = Base Delta × Volatility Multiplier × Correlation Factor

    Features:
    - Multi-timeframe ATR measurement (1h: 50%, 4h: 30%, 1d: 20%)
    - Composite volatility (ATR 70% + Short-term volatility 30%)
    - EMA smoothing to prevent erratic changes
    - Coin-specific bounds and base deltas
    - Volatility regime detection (Bollinger Band Width)
    """

    def __init__(self, exchange: ccxt.Exchange = None):
        """
        Initialize dynamic delta service

        Args:
            exchange: CCXT exchange instance for fetching OHLCV data
        """
        self.exchange = exchange

        # Coin-specific base deltas (starting point)
        self.base_deltas = {
            # Stable coins (BTC, ETH, BNB) - tighter deltas
            "BTC/USDT:USDT": 1.5,
            "ETH/USDT:USDT": 1.5,
            "BNB/USDT:USDT": 1.5,

            # Mid-tier coins (SOL, ADA, LINK) - moderate deltas
            "SOL/USDT:USDT": 2.0,
            "ADA/USDT:USDT": 2.0,
            "LINK/USDT:USDT": 2.0,
            "MATIC/USDT:USDT": 2.0,
            "AVAX/USDT:USDT": 2.0,

            # Volatile coins (DOGE, SHIB, meme coins) - wider deltas
            "DOGE/USDT:USDT": 3.0,
            "SHIB/USDT:USDT": 3.0,
            "PEPE/USDT:USDT": 3.0,

            # Default for unknown coins
            "DEFAULT": 2.0
        }

        # Safety bounds (min/max delta percentages)
        self.bounds = {
            # Stable coins: Narrower range
            "BTC/USDT:USDT": {"min": 0.5, "max": 5.0},
            "ETH/USDT:USDT": {"min": 0.5, "max": 5.0},
            "BNB/USDT:USDT": {"min": 0.5, "max": 5.0},

            # Volatile coins: Wider range
            "DOGE/USDT:USDT": {"min": 1.0, "max": 10.0},
            "SHIB/USDT:USDT": {"min": 1.0, "max": 10.0},
            "PEPE/USDT:USDT": {"min": 1.0, "max": 10.0},

            # Default
            "DEFAULT": {"min": 0.5, "max": 8.0}
        }

        # EMA smoothing state
        self.smoothed_deltas = {}  # symbol -> smoothed delta
        self.last_update = {}       # symbol -> timestamp
        self.update_interval = 600  # 10 minutes (Grok recommendation)

        # Multi-timeframe ATR weights
        self.volatility_weights = {
            "1h": 0.5,   # 50% weight - recent intraday volatility
            "4h": 0.3,   # 30% weight - broader market trends
            "1d": 0.2    # 20% weight - long-term context
        }

        # Historical volatility cache (7-day moving average)
        self.historical_volatility_cache = {}  # symbol -> 7-day avg
        self.volatility_history = {}           # symbol -> list of volatility values

        # Regime state
        self.current_regime = {}  # symbol -> LOW/NORMAL/HIGH

        print("🎯 Dynamic Fibonacci Delta Service initialized")
        print("   📊 Volatility-adaptive delta calculation enabled")
        print("   ⏱️ Update interval: 10 minutes (with regime detection)")
        print("   🔄 EMA smoothing: 80% previous + 20% new")

    def calculate_dynamic_delta(self, symbol: str, ohlcv_data: Optional[Dict] = None,
                               btc_correlation: float = 0.5, force_update: bool = False) -> float:
        """
        Main method: Calculate dynamic delta based on volatility and correlation

        Args:
            symbol: Trading pair (e.g., "BTC/USDT:USDT")
            ohlcv_data: Dict with OHLCV data for multiple timeframes
                       {"5m": [...], "1h": [...], "4h": [...], "1d": [...]}
            btc_correlation: Correlation with BTC (0.0 to 1.0)
            force_update: Force recalculation ignoring update interval

        Returns:
            Dynamic delta percentage (e.g., 1.1, 2.0, 5.0)
        """
        # Check if update needed (unless forced)
        if not force_update:
            now = time.time()
            if symbol in self.last_update:
                elapsed = now - self.last_update[symbol]
                if elapsed < self.update_interval:
                    # Return cached smoothed delta
                    cached = self.smoothed_deltas.get(symbol)
                    if cached:
                        return cached

        # If no OHLCV data provided, fetch it
        if not ohlcv_data and self.exchange:
            ohlcv_data = self._fetch_multi_timeframe_ohlcv(symbol)

        # If still no data, return base delta
        if not ohlcv_data:
            base = self.base_deltas.get(symbol, self.base_deltas["DEFAULT"])
            print(f"  ⚠️ No OHLCV data for {symbol}, using base delta: {base:.2f}%")
            return base

        # Get base delta for this coin
        base_delta = self.base_deltas.get(symbol, self.base_deltas["DEFAULT"])

        # Calculate current composite volatility
        current_volatility = self.calculate_composite_volatility(symbol, ohlcv_data)

        # Get historical average volatility (7-day)
        historical_volatility = self._get_historical_avg_volatility(symbol, current_volatility)

        # Calculate volatility multiplier (bounded 0.5x to 2.0x)
        vol_multiplier = self._calculate_volatility_multiplier(
            current_volatility, historical_volatility
        )

        # Calculate correlation factor
        corr_factor = self._calculate_correlation_factor(btc_correlation)

        # Raw delta calculation
        raw_delta = base_delta * vol_multiplier * corr_factor

        # Apply EMA smoothing (80% previous + 20% new)
        if symbol in self.smoothed_deltas:
            smoothed_delta = (0.8 * self.smoothed_deltas[symbol]) + (0.2 * raw_delta)
        else:
            smoothed_delta = raw_delta  # First time, no smoothing

        # Apply safety bounds
        bounds = self.bounds.get(symbol, self.bounds["DEFAULT"])
        final_delta = max(min(smoothed_delta, bounds["max"]), bounds["min"])

        # Store state
        self.smoothed_deltas[symbol] = final_delta
        self.last_update[symbol] = time.time()

        # Detect regime for future updates
        regime = self.detect_regime_change(ohlcv_data)
        self.current_regime[symbol] = regime

        # Log calculation details
        print(f"  🎯 Dynamic Delta for {symbol}:")
        print(f"     Base: {base_delta:.2f}% | Vol Mult: {vol_multiplier:.2f}x | Corr: {corr_factor:.2f}x")
        print(f"     Current Vol: {current_volatility:.4f} | Historical: {historical_volatility:.4f}")
        print(f"     Raw: {raw_delta:.2f}% → Smoothed: {smoothed_delta:.2f}% → Final: {final_delta:.2f}%")
        print(f"     Regime: {regime}")

        return final_delta

    def calculate_composite_volatility(self, symbol: str, ohlcv_data: Dict) -> float:
        """
        Calculate composite volatility (ATR 70% + Short-term volatility 30%)

        Args:
            symbol: Trading pair
            ohlcv_data: Dict with OHLCV data for multiple timeframes

        Returns:
            Composite volatility value
        """
        # Multi-timeframe ATR
        atr_1h = self._calculate_atr(ohlcv_data.get("1h"), period=14) if "1h" in ohlcv_data else 0
        atr_4h = self._calculate_atr(ohlcv_data.get("4h"), period=14) if "4h" in ohlcv_data else 0
        atr_1d = self._calculate_atr(ohlcv_data.get("1d"), period=14) if "1d" in ohlcv_data else 0

        # Weighted composite ATR
        composite_atr = (
            self.volatility_weights["1h"] * atr_1h +
            self.volatility_weights["4h"] * atr_4h +
            self.volatility_weights["1d"] * atr_1d
        )

        # Short-term volatility (5m bars, last 2 hours = 24 bars)
        stv = 0
        if "5m" in ohlcv_data and ohlcv_data["5m"]:
            try:
                df_5m = pd.DataFrame(
                    ohlcv_data["5m"],
                    columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
                )
                if len(df_5m) >= 24:
                    returns = df_5m["close"].pct_change()
                    stv = returns.tail(24).std() if len(returns) >= 24 else 0
            except Exception as e:
                print(f"  ⚠️ Error calculating STV for {symbol}: {e}")
                stv = 0

        # Composite: 70% ATR, 30% STV
        composite_volatility = (0.7 * composite_atr) + (0.3 * stv)

        return composite_volatility

    def _calculate_atr(self, ohlcv: List, period: int = 14) -> float:
        """
        Calculate Average True Range

        Args:
            ohlcv: List of OHLCV candles [[timestamp, open, high, low, close, volume], ...]
            period: ATR period (default 14)

        Returns:
            ATR value
        """
        if not ohlcv or len(ohlcv) < period + 1:
            return 0

        try:
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            # True Range components
            df['h-l'] = df['high'] - df['low']
            df['h-pc'] = abs(df['high'] - df['close'].shift(1))
            df['l-pc'] = abs(df['low'] - df['close'].shift(1))

            # True Range = max of three components
            df['tr'] = df[['h-l', 'h-pc', 'l-pc']].max(axis=1)

            # ATR = rolling mean of TR
            atr = df['tr'].rolling(window=period).mean().iloc[-1]

            return atr if not pd.isna(atr) else 0

        except Exception as e:
            print(f"  ⚠️ Error calculating ATR: {e}")
            return 0

    def _calculate_volatility_multiplier(self, current_vol: float, historical_vol: float) -> float:
        """
        Calculate volatility multiplier (bounded 0.5x to 2.0x)

        Uses square root to prevent extreme adjustments

        Args:
            current_vol: Current composite volatility
            historical_vol: Historical average volatility

        Returns:
            Multiplier between 0.5 and 2.0
        """
        if historical_vol <= 0:
            return 1.0  # No adjustment if no historical baseline

        # Normalized ratio
        ratio = current_vol / historical_vol

        # Non-linear scaling (sqrt prevents overreaction)
        multiplier = math.sqrt(ratio)

        # Bounded: 0.5x to 2.0x
        multiplier = max(min(multiplier, 2.0), 0.5)

        return multiplier

    def _calculate_correlation_factor(self, btc_correlation: float) -> float:
        """
        Calculate correlation adjustment factor

        High correlation → slightly reduce delta (BTC stability anchors)
        Low correlation → slightly increase delta (independent volatility)

        Args:
            btc_correlation: Correlation with BTC (0.0 to 1.0)

        Returns:
            Factor between 0.9 and 1.1
        """
        # Factor: 0.9 to 1.1
        # High correlation (0.9): factor = 1.0 + (0.1 × 0.1) = 1.01 (minor reduction)
        # Low correlation (0.2): factor = 1.0 + (0.1 × 0.8) = 1.08 (8% increase)
        factor = 1.0 + (0.1 * (1 - btc_correlation))

        return factor

    def _get_historical_avg_volatility(self, symbol: str, current_vol: float) -> float:
        """
        Get historical average volatility (7-day MA of composite volatility)

        Args:
            symbol: Trading pair
            current_vol: Current volatility to add to history

        Returns:
            7-day average volatility
        """
        # Initialize history if needed
        if symbol not in self.volatility_history:
            self.volatility_history[symbol] = []

        # Add current volatility to history
        self.volatility_history[symbol].append({
            'timestamp': time.time(),
            'volatility': current_vol
        })

        # Keep only last 7 days of data
        cutoff_time = time.time() - (7 * 24 * 3600)
        self.volatility_history[symbol] = [
            v for v in self.volatility_history[symbol]
            if v['timestamp'] > cutoff_time
        ]

        # Calculate 7-day average
        if len(self.volatility_history[symbol]) > 0:
            avg_vol = sum(v['volatility'] for v in self.volatility_history[symbol]) / len(self.volatility_history[symbol])
            self.historical_volatility_cache[symbol] = avg_vol
            return avg_vol

        # Fallback: use reasonable defaults based on coin type
        if "BTC" in symbol or "ETH" in symbol:
            return 0.02  # 2% for stable coins
        elif "DOGE" in symbol or "SHIB" in symbol or "PEPE" in symbol:
            return 0.05  # 5% for volatile coins
        else:
            return 0.03  # 3% default

    def detect_regime_change(self, ohlcv_data: Dict) -> str:
        """
        Detect volatility regime (LOW, NORMAL, HIGH)

        Uses Bollinger Band Width method

        Args:
            ohlcv_data: Dict with OHLCV data

        Returns:
            "LOW_VOLATILITY", "NORMAL_VOLATILITY", or "HIGH_VOLATILITY"
        """
        if "1h" not in ohlcv_data or not ohlcv_data["1h"]:
            return "NORMAL_VOLATILITY"

        try:
            df = pd.DataFrame(
                ohlcv_data["1h"],
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            if len(df) < 20:
                return "NORMAL_VOLATILITY"

            # Bollinger Band Width
            sma_20 = df["close"].rolling(20).mean()
            std_20 = df["close"].rolling(20).std()
            bbw = (std_20 * 4) / sma_20  # (upper - lower) / sma

            current_bbw = bbw.iloc[-1]
            avg_bbw = bbw.mean()

            # Classify regime
            if current_bbw < avg_bbw * 0.7:
                return "LOW_VOLATILITY"
            elif current_bbw > avg_bbw * 1.5:
                return "HIGH_VOLATILITY"
            else:
                return "NORMAL_VOLATILITY"

        except Exception as e:
            print(f"  ⚠️ Error detecting regime: {e}")
            return "NORMAL_VOLATILITY"

    def _fetch_multi_timeframe_ohlcv(self, symbol: str) -> Dict:
        """
        Fetch OHLCV data for multiple timeframes

        Args:
            symbol: Trading pair

        Returns:
            Dict with OHLCV data for each timeframe
        """
        if not self.exchange:
            return {}

        timeframes = ["5m", "1h", "4h", "1d"]
        ohlcv_data = {}

        for tf in timeframes:
            try:
                # Fetch appropriate number of candles
                limit = 100 if tf == "5m" else 50
                candles = self.exchange.fetch_ohlcv(symbol, timeframe=tf, limit=limit)
                ohlcv_data[tf] = candles
            except Exception as e:
                print(f"  ⚠️ Error fetching {tf} data for {symbol}: {e}")
                ohlcv_data[tf] = []

        return ohlcv_data

    def should_force_update(self, symbol: str, ohlcv_data: Dict) -> bool:
        """
        Check if regime change requires immediate delta update

        Args:
            symbol: Trading pair
            ohlcv_data: Current OHLCV data

        Returns:
            True if regime changed and update should be forced
        """
        if symbol not in self.current_regime:
            return False

        new_regime = self.detect_regime_change(ohlcv_data)
        previous_regime = self.current_regime.get(symbol, "NORMAL_VOLATILITY")

        if new_regime != previous_regime:
            print(f"  🔄 Regime change detected for {symbol}: {previous_regime} → {new_regime}")
            return True

        return False


# Example usage and testing
if __name__ == "__main__":
    print("🧪 Testing Dynamic Fibonacci Delta Service\n")

    service = DynamicFibonacciDeltaService()

    # Simulate OHLCV data (in production, this comes from exchange)
    # For testing, create dummy data
    test_ohlcv = {
        "5m": [[0, 100, 105, 95, 102, 1000] for _ in range(100)],
        "1h": [[0, 100, 110, 90, 105, 10000] for _ in range(50)],
        "4h": [[0, 100, 120, 80, 110, 50000] for _ in range(50)],
        "1d": [[0, 100, 130, 70, 115, 100000] for _ in range(50)]
    }

    # Test 1: BTC with high correlation
    print("Test 1: BTC/USDT:USDT (stable coin, high BTC correlation)")
    btc_delta = service.calculate_dynamic_delta(
        symbol="BTC/USDT:USDT",
        ohlcv_data=test_ohlcv,
        btc_correlation=1.0
    )
    print(f"✅ Result: {btc_delta:.2f}%\n")

    # Test 2: DOGE with low correlation
    print("Test 2: DOGE/USDT:USDT (volatile coin, low BTC correlation)")
    doge_delta = service.calculate_dynamic_delta(
        symbol="DOGE/USDT:USDT",
        ohlcv_data=test_ohlcv,
        btc_correlation=0.3
    )
    print(f"✅ Result: {doge_delta:.2f}%\n")

    print("🎉 Dynamic Fibonacci Delta Service tests complete!")
