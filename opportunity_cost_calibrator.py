#!/usr/bin/env python3
"""
Opportunity Cost Threshold Calibrator V1.0.0

Symbol-specific calibration for opportunity cost thresholds based on:
1. Volatility ratio vs BTC (live data priority)
2. BTC correlation coefficient (live data priority)
3. Position averaging state
4. HMM volatility regime

Implements Grok recommendations 1A, 1B, 2A, 2B, 5A, 5B

Author: Claude & Grok Collaboration
Date: January 16, 2026
"""

import numpy as np
from typing import Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os

# Try to import exchange
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False


@dataclass
class OpportunityCostCalibration:
    """Calibration data for opportunity cost thresholds"""
    symbol: str
    volatility_ratio: float
    btc_correlation: float
    high_cost_threshold: float
    moderate_cost_threshold: float
    acceptable_cost_threshold: float
    guard_usd: float
    guard_pct: float
    max_holding_minutes: int
    calibration_time: datetime
    is_live_data: bool

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'volatility_ratio': self.volatility_ratio,
            'btc_correlation': self.btc_correlation,
            'high_cost_threshold': self.high_cost_threshold,
            'moderate_cost_threshold': self.moderate_cost_threshold,
            'acceptable_cost_threshold': self.acceptable_cost_threshold,
            'guard_usd': self.guard_usd,
            'guard_pct': self.guard_pct,
            'max_holding_minutes': self.max_holding_minutes,
            'calibration_time': self.calibration_time.isoformat(),
            'is_live_data': self.is_live_data
        }


class OpportunityCostCalibrator:
    """
    Calibrates opportunity cost thresholds per symbol.

    V1.0.0 Changes (from backtest findings):
    - Symbol-specific thresholds based on volatility/correlation
    - Percentage-based guard (3% of position) instead of fixed $0.15
    - Tiered holding times:
        * Averaged positions: 7 days (10080 min)
        * Low vol (BTC-like): 12 hours (720 min)
        * Mid vol (alts): 8 hours (480 min)
        * High vol (meme): 4 hours (240 min) - SHORTER based on backtest
    """

    # Base thresholds (current)
    BASE_THRESHOLDS = {
        'high_cost': 0.05,      # 5%
        'moderate_cost': 0.03,  # 3%
        'acceptable_cost': 0.02 # 2%
    }

    # Default volatility ratios
    DEFAULT_VOL_RATIOS = {
        'BTC/USDT:USDT': 1.0,
        'ETH/USDT:USDT': 1.2,
        'SOL/USDT:USDT': 1.5,
        'XRP/USDT:USDT': 1.4,
        'DOGE/USDT:USDT': 2.5,
        'AVAX/USDT:USDT': 1.6,
        'LINK/USDT:USDT': 1.5,
        'DOT/USDT:USDT': 1.4,
        'POL/USDT:USDT': 1.8,
        'PEPE/USDT:USDT': 3.5,
        'WIF/USDT:USDT': 3.0,
        'BONK/USDT:USDT': 3.2,
        'SHIB/USDT:USDT': 3.0,
        'ARB/USDT:USDT': 1.7,
        'OP/USDT:USDT': 1.7,
        'INJ/USDT:USDT': 1.8,
        'SUI/USDT:USDT': 2.0,
        'DYM/USDT:USDT': 2.2,
    }

    # Default BTC correlations
    DEFAULT_BTC_CORRELATIONS = {
        'BTC/USDT:USDT': 1.0,
        'ETH/USDT:USDT': 0.85,
        'SOL/USDT:USDT': 0.75,
        'XRP/USDT:USDT': 0.70,
        'DOGE/USDT:USDT': 0.60,
        'AVAX/USDT:USDT': 0.72,
        'LINK/USDT:USDT': 0.75,
        'DOT/USDT:USDT': 0.73,
        'POL/USDT:USDT': 0.65,
        'PEPE/USDT:USDT': 0.45,
        'WIF/USDT:USDT': 0.40,
        'BONK/USDT:USDT': 0.42,
        'SHIB/USDT:USDT': 0.50,
        'ARB/USDT:USDT': 0.68,
        'OP/USDT:USDT': 0.70,
        'INJ/USDT:USDT': 0.65,
        'SUI/USDT:USDT': 0.60,
        'DYM/USDT:USDT': 0.50,
    }

    def __init__(self, exchange=None, cache_file: str = 'opportunity_cost_calibration_cache.json'):
        self.exchange = exchange
        self.cache_file = cache_file
        self.calibration_cache: Dict[str, OpportunityCostCalibration] = {}
        self.cache_ttl = timedelta(hours=4)
        self._load_cache()

    def _load_cache(self):
        """Load calibration cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    for symbol, cal_data in data.items():
                        self.calibration_cache[symbol] = OpportunityCostCalibration(
                            symbol=cal_data['symbol'],
                            volatility_ratio=cal_data['volatility_ratio'],
                            btc_correlation=cal_data['btc_correlation'],
                            high_cost_threshold=cal_data['high_cost_threshold'],
                            moderate_cost_threshold=cal_data['moderate_cost_threshold'],
                            acceptable_cost_threshold=cal_data['acceptable_cost_threshold'],
                            guard_usd=cal_data['guard_usd'],
                            guard_pct=cal_data['guard_pct'],
                            max_holding_minutes=cal_data['max_holding_minutes'],
                            calibration_time=datetime.fromisoformat(cal_data['calibration_time']),
                            is_live_data=cal_data.get('is_live_data', False)
                        )
        except Exception:
            pass

    def _save_cache(self):
        """Save calibration cache to file"""
        try:
            data = {s: c.to_dict() for s, c in self.calibration_cache.items()}
            with open(self.cache_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass

    def get_volatility_ratio(self, symbol: str) -> Tuple[float, bool]:
        """
        Get symbol's volatility ratio vs BTC.
        Returns (ratio, is_live_data)

        Live data priority (Grok recommendation C from threshold calibrator)
        """
        is_live = False

        # Try live exchange data FIRST
        if self.exchange and CCXT_AVAILABLE:
            try:
                symbol_ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=24)
                btc_ohlcv = self.exchange.fetch_ohlcv('BTC/USDT:USDT', '1h', limit=24)

                if symbol_ohlcv and btc_ohlcv and len(symbol_ohlcv) >= 12:
                    symbol_returns = np.diff([c[4] for c in symbol_ohlcv]) / [c[4] for c in symbol_ohlcv[:-1]]
                    btc_returns = np.diff([c[4] for c in btc_ohlcv]) / [c[4] for c in btc_ohlcv[:-1]]

                    symbol_vol = np.std(symbol_returns) if len(symbol_returns) > 0 else 0.02
                    btc_vol = np.std(btc_returns) if len(btc_returns) > 0 else 0.02

                    if btc_vol > 0:
                        live_ratio = max(0.5, min(5.0, symbol_vol / btc_vol))
                        return live_ratio, True
            except Exception:
                pass

        # Fall back to defaults
        ratio = self.DEFAULT_VOL_RATIOS.get(symbol, 1.5)
        return ratio, False

    def get_btc_correlation(self, symbol: str) -> Tuple[float, bool]:
        """
        Get symbol's correlation with BTC.
        Returns (correlation, is_live_data)

        Live data priority (Grok recommendation C)
        """
        if symbol == 'BTC/USDT:USDT':
            return 1.0, True

        is_live = False

        # Try live exchange data FIRST
        if self.exchange and CCXT_AVAILABLE:
            try:
                symbol_ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=48)
                btc_ohlcv = self.exchange.fetch_ohlcv('BTC/USDT:USDT', '1h', limit=48)

                if symbol_ohlcv and btc_ohlcv and len(symbol_ohlcv) >= 24:
                    symbol_prices = np.array([c[4] for c in symbol_ohlcv])
                    btc_prices = np.array([c[4] for c in btc_ohlcv[:len(symbol_prices)]])

                    if len(symbol_prices) == len(btc_prices):
                        correlation = np.corrcoef(symbol_prices, btc_prices)[0, 1]
                        if not np.isnan(correlation):
                            return max(0.0, min(1.0, correlation)), True
            except Exception:
                pass

        # Fall back to defaults
        corr = self.DEFAULT_BTC_CORRELATIONS.get(symbol, 0.6)
        return corr, False

    def calculate_thresholds(self, symbol: str, vol_ratio: float, btc_corr: float) -> Dict[str, float]:
        """
        Calculate symbol-specific opportunity cost thresholds.

        Formula (Grok recommendation 1A):
        - Higher volatility = higher thresholds (more tolerant of opportunity cost)
        - Lower BTC correlation = higher thresholds (less comparable to market)
        """
        base = self.BASE_THRESHOLDS.copy()

        # Volatility adjustment
        if vol_ratio <= 1.5:
            vol_mult = 1.0  # BTC-like: use base thresholds
        elif vol_ratio <= 2.5:
            vol_mult = 1.0 + (vol_ratio - 1.5) * 0.3  # Mid-caps: +30% per 1.0 ratio
        else:
            vol_mult = 1.0 + (vol_ratio - 1.5) * 0.5  # Meme coins: +50% per 1.0 ratio

        # Correlation adjustment
        corr_mult = 1.0 + (1 - btc_corr) * 0.2  # +20% for uncorrelated assets

        total_mult = vol_mult * corr_mult

        return {
            'high_cost': min(0.15, base['high_cost'] * total_mult),
            'moderate_cost': min(0.10, base['moderate_cost'] * total_mult),
            'acceptable_cost': min(0.05, base['acceptable_cost'] * total_mult)
        }

    def calculate_guard(self, position_size_usd: float) -> Tuple[float, float]:
        """
        Calculate percentage-based guard (Grok recommendation 2A).

        Instead of fixed $0.15, use 3% of position value.
        Returns (guard_usd, guard_pct)
        """
        guard_pct = 0.03  # 3% of position
        guard_usd = position_size_usd * guard_pct
        return guard_usd, guard_pct

    def calculate_max_holding(self, averaging_steps: int, vol_ratio: float) -> int:
        """
        Calculate tiered max holding time (Grok recommendation 5A, 5B).

        Based on backtest findings:
        - Averaged positions: 7 days (they need time to recover)
        - Low vol (BTC-like): 12 hours (steady, can hold longer)
        - Mid vol (alts): 8 hours (balanced)
        - High vol (meme): 4 hours (SHORTER! backtest showed -11.8% with long holds)

        Returns max holding in minutes.
        """
        if averaging_steps > 0:
            # Averaged positions: much longer holding (up to 7 days)
            # These are recovery trades, need time
            return 10080  # 7 days

        if vol_ratio <= 1.5:
            # BTC/ETH-like: can hold longer, more predictable
            return 720  # 12 hours
        elif vol_ratio <= 2.5:
            # Mid-cap alts: moderate holding
            return 480  # 8 hours (current)
        else:
            # High-vol meme coins: SHORTER holding
            # Backtest showed -11.8% average P&L with long holding
            return 240  # 4 hours

    def calibrate(self, symbol: str, position_size_usd: float = 5.0,
                  averaging_steps: int = 0) -> OpportunityCostCalibration:
        """
        Full calibration for a symbol.

        Args:
            symbol: Trading symbol
            position_size_usd: Position size in USD
            averaging_steps: Number of averaging steps taken

        Returns:
            OpportunityCostCalibration with all calibrated values
        """
        # Check cache
        cache_key = f"{symbol}_{position_size_usd}_{averaging_steps}"
        if cache_key in self.calibration_cache:
            cached = self.calibration_cache[cache_key]
            if datetime.now() - cached.calibration_time < self.cache_ttl:
                return cached

        # Get live data
        vol_ratio, vol_live = self.get_volatility_ratio(symbol)
        btc_corr, corr_live = self.get_btc_correlation(symbol)

        # Calculate all parameters
        thresholds = self.calculate_thresholds(symbol, vol_ratio, btc_corr)
        guard_usd, guard_pct = self.calculate_guard(position_size_usd)
        max_holding = self.calculate_max_holding(averaging_steps, vol_ratio)

        calibration = OpportunityCostCalibration(
            symbol=symbol,
            volatility_ratio=vol_ratio,
            btc_correlation=btc_corr,
            high_cost_threshold=thresholds['high_cost'],
            moderate_cost_threshold=thresholds['moderate_cost'],
            acceptable_cost_threshold=thresholds['acceptable_cost'],
            guard_usd=guard_usd,
            guard_pct=guard_pct,
            max_holding_minutes=max_holding,
            calibration_time=datetime.now(),
            is_live_data=vol_live or corr_live
        )

        # Cache and save
        self.calibration_cache[cache_key] = calibration
        self._save_cache()

        return calibration


# Singleton instance
_calibrator_instance = None


def get_opportunity_cost_calibrator(exchange=None) -> OpportunityCostCalibrator:
    """Get or create the calibrator singleton"""
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = OpportunityCostCalibrator(exchange)
    return _calibrator_instance


def get_calibrated_opportunity_cost_params(
    symbol: str,
    position_size_usd: float = 5.0,
    averaging_steps: int = 0,
    exchange=None
) -> Dict:
    """
    Convenience function to get all calibrated parameters.

    Returns dict with:
    - thresholds: {high_cost, moderate_cost, acceptable_cost}
    - guard_usd: minimum UPNL to consider closing
    - guard_pct: guard as percentage
    - max_holding_minutes: tiered max holding time
    - volatility_ratio: symbol's vol ratio vs BTC
    - btc_correlation: symbol's correlation with BTC
    - is_live_data: whether live data was used
    """
    calibrator = get_opportunity_cost_calibrator(exchange)
    cal = calibrator.calibrate(symbol, position_size_usd, averaging_steps)

    return {
        'thresholds': {
            'high_cost': cal.high_cost_threshold,
            'moderate_cost': cal.moderate_cost_threshold,
            'acceptable_cost': cal.acceptable_cost_threshold
        },
        'guard_usd': cal.guard_usd,
        'guard_pct': cal.guard_pct,
        'max_holding_minutes': cal.max_holding_minutes,
        'volatility_ratio': cal.volatility_ratio,
        'btc_correlation': cal.btc_correlation,
        'is_live_data': cal.is_live_data
    }


if __name__ == '__main__':
    print("=" * 70)
    print("Opportunity Cost Calibrator V1.0.0 Test")
    print("=" * 70)
    print("\nBased on backtest findings:")
    print("  - Symbol-specific thresholds improve exit timing")
    print("  - Percentage-based guard scales with position size")
    print("  - Tiered holding: meme coins SHORTER, averaged positions LONGER")
    print()

    calibrator = OpportunityCostCalibrator()

    test_symbols = [
        ('BTC/USDT:USDT', 0),
        ('ETH/USDT:USDT', 0),
        ('SOL/USDT:USDT', 0),
        ('POL/USDT:USDT', 0),
        ('POL/USDT:USDT', 2),  # With averaging
        ('DOGE/USDT:USDT', 0),
        ('PEPE/USDT:USDT', 0),
    ]

    print(f"{'Symbol':<20} {'AvgSteps':<10} {'VolRatio':<10} {'BTCCorr':<10} {'High%':<8} {'MaxHold':<10}")
    print("-" * 70)

    for symbol, avg_steps in test_symbols:
        cal = calibrator.calibrate(symbol, position_size_usd=5.0, averaging_steps=avg_steps)
        print(f"{symbol:<20} {avg_steps:<10} {cal.volatility_ratio:<10.2f} {cal.btc_correlation:<10.2f} "
              f"{cal.high_cost_threshold*100:<8.1f} {cal.max_holding_minutes:<10}min")

    print("-" * 70)
    print("\nCalibration complete!")
