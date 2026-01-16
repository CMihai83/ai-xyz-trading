#!/usr/bin/env python3
"""
Symbol-Specific Threshold Calibrator V3.3.0

Calculates per-symbol averaging thresholds based on:
1. Historical volatility ratio vs BTC
2. BTC correlation coefficient
3. CSSI correction probability
4. Backtest historical drawdown

Author: Claude & Grok Collaboration
Date: January 16, 2026
"""

import os
import json
import numpy as np
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta

# Try to import exchange
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

# Try to import CSSI
try:
    from historical_correction_analyzer import HistoricalCorrectionAnalyzer, CSSI
    CSSI_AVAILABLE = True
except ImportError:
    CSSI_AVAILABLE = False


@dataclass
class SymbolCalibration:
    """Calibration data for a symbol"""
    symbol: str
    volatility_ratio: float      # vs BTC (1.0 = same as BTC)
    btc_correlation: float       # 0-1 correlation with BTC
    correction_probability: float # From CSSI (0-1)
    historical_max_drawdown: float  # From backtest (0-100%)
    base_threshold: float        # From HMM regime
    adjusted_threshold: float    # Final calibrated threshold
    calibration_time: datetime

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'volatility_ratio': self.volatility_ratio,
            'btc_correlation': self.btc_correlation,
            'correction_probability': self.correction_probability,
            'historical_max_drawdown': self.historical_max_drawdown,
            'base_threshold': self.base_threshold,
            'adjusted_threshold': self.adjusted_threshold,
            'calibration_time': self.calibration_time.isoformat()
        }


class SymbolThresholdCalibrator:
    """
    Calibrates averaging thresholds per symbol based on multiple factors.

    Formula:
    adjusted = base_threshold * (1 + vol_adj + corr_adj + cssi_adj + backtest_adj)

    Where:
    - vol_adj = (volatility_ratio - 1) * 0.5  (wider for high-vol coins)
    - corr_adj = (1 - btc_correlation) * 0.2  (wider for uncorrelated)
    - cssi_adj = -correction_probability * 0.1  (tighter if correction likely)
    - backtest_adj = historical_max_drawdown / 200  (based on historical DD)
    """

    # Default volatility ratios vs BTC (from historical data)
    DEFAULT_VOL_RATIOS = {
        'BTC/USDT:USDT': 1.0,
        'ETH/USDT:USDT': 1.2,
        'SOL/USDT:USDT': 1.5,
        'XRP/USDT:USDT': 1.4,
        'DOGE/USDT:USDT': 2.5,
        'AVAX/USDT:USDT': 1.6,
        'LINK/USDT:USDT': 1.5,
        'DOT/USDT:USDT': 1.4,
        'MATIC/USDT:USDT': 1.6,
        'POL/USDT:USDT': 1.8,
        'SHIB/USDT:USDT': 3.0,
        'PEPE/USDT:USDT': 3.5,
        'WIF/USDT:USDT': 3.0,
        'BONK/USDT:USDT': 3.2,
        'FLOKI/USDT:USDT': 2.8,
        'ARB/USDT:USDT': 1.7,
        'OP/USDT:USDT': 1.7,
        'INJ/USDT:USDT': 1.8,
        'SUI/USDT:USDT': 2.0,
        'SEI/USDT:USDT': 2.0,
        'APT/USDT:USDT': 1.8,
        'TIA/USDT:USDT': 2.2,
        'JUP/USDT:USDT': 2.0,
        'DYM/USDT:USDT': 2.2,
        'BLUR/USDT:USDT': 2.0,
        'ZEC/USDT:USDT': 1.5,
        'XMR/USDT:USDT': 1.3,
        'LTC/USDT:USDT': 1.2,
        'ETC/USDT:USDT': 1.4,
        'FIL/USDT:USDT': 1.8,
        'ATOM/USDT:USDT': 1.5,
        'UNI/USDT:USDT': 1.6,
        'AAVE/USDT:USDT': 1.7,
        'MKR/USDT:USDT': 1.5,
        'NEAR/USDT:USDT': 1.8,
        'FTM/USDT:USDT': 2.0,
        'SAND/USDT:USDT': 2.2,
        'MANA/USDT:USDT': 2.0,
        'AXS/USDT:USDT': 2.2,
        'GALA/USDT:USDT': 2.5,
        'IMX/USDT:USDT': 2.0,
        'RUNE/USDT:USDT': 2.0,
        'ENS/USDT:USDT': 1.8,
        'LDO/USDT:USDT': 1.9,
        'CRV/USDT:USDT': 2.0,
        'SNX/USDT:USDT': 2.0,
        'COMP/USDT:USDT': 1.8,
        'YFI/USDT:USDT': 1.7,
        'SUSHI/USDT:USDT': 2.2,
        '1INCH/USDT:USDT': 2.0,
    }

    # Default BTC correlations (from historical data)
    DEFAULT_BTC_CORRELATIONS = {
        'BTC/USDT:USDT': 1.0,
        'ETH/USDT:USDT': 0.85,
        'SOL/USDT:USDT': 0.75,
        'XRP/USDT:USDT': 0.70,
        'DOGE/USDT:USDT': 0.60,
        'AVAX/USDT:USDT': 0.72,
        'LINK/USDT:USDT': 0.75,
        'DOT/USDT:USDT': 0.73,
        'MATIC/USDT:USDT': 0.70,
        'POL/USDT:USDT': 0.65,
        'SHIB/USDT:USDT': 0.50,
        'PEPE/USDT:USDT': 0.45,
        'WIF/USDT:USDT': 0.40,
        'BONK/USDT:USDT': 0.42,
        'FLOKI/USDT:USDT': 0.48,
        'ARB/USDT:USDT': 0.68,
        'OP/USDT:USDT': 0.70,
        'INJ/USDT:USDT': 0.65,
        'SUI/USDT:USDT': 0.60,
        'SEI/USDT:USDT': 0.58,
        'APT/USDT:USDT': 0.65,
        'TIA/USDT:USDT': 0.55,
        'JUP/USDT:USDT': 0.55,
        'DYM/USDT:USDT': 0.50,
        'BLUR/USDT:USDT': 0.55,
        'ZEC/USDT:USDT': 0.72,
        'XMR/USDT:USDT': 0.68,
        'LTC/USDT:USDT': 0.80,
        'ETC/USDT:USDT': 0.78,
        'FIL/USDT:USDT': 0.65,
        'ATOM/USDT:USDT': 0.70,
        'UNI/USDT:USDT': 0.72,
        'AAVE/USDT:USDT': 0.70,
    }

    # Default max drawdowns from backtest (%)
    DEFAULT_MAX_DRAWDOWNS = {
        'BTC/USDT:USDT': 25.0,
        'ETH/USDT:USDT': 30.0,
        'SOL/USDT:USDT': 40.0,
        'DOGE/USDT:USDT': 50.0,
        'POL/USDT:USDT': 45.0,
        'DYM/USDT:USDT': 50.0,
        'BLUR/USDT:USDT': 45.0,
        'PEPE/USDT:USDT': 60.0,
        'WIF/USDT:USDT': 55.0,
    }

    def __init__(self, exchange=None, cache_file: str = 'threshold_calibration_cache.json'):
        self.exchange = exchange
        self.cache_file = cache_file
        self.calibration_cache: Dict[str, SymbolCalibration] = {}
        self.cache_ttl = timedelta(hours=4)  # Recalibrate every 4 hours

        # Load cache
        self._load_cache()

        # Try to initialize CSSI analyzer
        self.cssi_analyzer = None
        if CSSI_AVAILABLE and exchange:
            try:
                self.cssi_analyzer = HistoricalCorrectionAnalyzer(exchange)
            except Exception:
                pass

    def _load_cache(self):
        """Load calibration cache from file"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    data = json.load(f)
                    for symbol, cal_data in data.items():
                        self.calibration_cache[symbol] = SymbolCalibration(
                            symbol=cal_data['symbol'],
                            volatility_ratio=cal_data['volatility_ratio'],
                            btc_correlation=cal_data['btc_correlation'],
                            correction_probability=cal_data['correction_probability'],
                            historical_max_drawdown=cal_data['historical_max_drawdown'],
                            base_threshold=cal_data['base_threshold'],
                            adjusted_threshold=cal_data['adjusted_threshold'],
                            calibration_time=datetime.fromisoformat(cal_data['calibration_time'])
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

    def get_volatility_ratio(self, symbol: str) -> float:
        """Get symbol's volatility ratio vs BTC"""
        # Check default values first
        if symbol in self.DEFAULT_VOL_RATIOS:
            return self.DEFAULT_VOL_RATIOS[symbol]

        # Try to calculate from exchange data
        if self.exchange and CCXT_AVAILABLE:
            try:
                # Get recent volatility for symbol and BTC
                symbol_ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=24)
                btc_ohlcv = self.exchange.fetch_ohlcv('BTC/USDT:USDT', '1h', limit=24)

                if symbol_ohlcv and btc_ohlcv:
                    symbol_returns = np.diff([c[4] for c in symbol_ohlcv]) / [c[4] for c in symbol_ohlcv[:-1]]
                    btc_returns = np.diff([c[4] for c in btc_ohlcv]) / [c[4] for c in btc_ohlcv[:-1]]

                    symbol_vol = np.std(symbol_returns) if len(symbol_returns) > 0 else 0.02
                    btc_vol = np.std(btc_returns) if len(btc_returns) > 0 else 0.02

                    if btc_vol > 0:
                        return max(0.5, min(5.0, symbol_vol / btc_vol))
            except Exception:
                pass

        # Default for unknown symbols - assume moderate volatility
        return 1.5

    def get_btc_correlation(self, symbol: str) -> float:
        """Get symbol's correlation with BTC"""
        if symbol == 'BTC/USDT:USDT':
            return 1.0

        # Check default values first
        if symbol in self.DEFAULT_BTC_CORRELATIONS:
            return self.DEFAULT_BTC_CORRELATIONS[symbol]

        # Try to calculate from exchange data
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
                            return max(0.0, min(1.0, correlation))
            except Exception:
                pass

        # Default for unknown symbols
        return 0.6

    def get_correction_probability(self, symbol: str, current_drawdown: float = 0.0) -> float:
        """Get CSSI correction probability for symbol"""
        if self.cssi_analyzer and CSSI_AVAILABLE:
            try:
                cssi = self.cssi_analyzer.calculate_cssi(symbol)
                if cssi:
                    return cssi.correction_probability / 100.0  # Convert to 0-1
            except Exception:
                pass

        # Estimate based on drawdown depth using logistic function
        # P(correction) = 1 / (1 + exp(-(-1 + 20*depth)))
        depth = abs(current_drawdown) / 100.0
        prob = 1 / (1 + np.exp(-(-1 + 20 * depth)))
        return prob

    def get_historical_max_drawdown(self, symbol: str) -> float:
        """Get historical max drawdown from backtest data"""
        # Check defaults
        if symbol in self.DEFAULT_MAX_DRAWDOWNS:
            return self.DEFAULT_MAX_DRAWDOWNS[symbol]

        # Try to load from backtest results
        try:
            backtest_file = f'backtest_cache/{symbol.replace("/", "_").replace(":", "_")}_drawdown.json'
            if os.path.exists(backtest_file):
                with open(backtest_file, 'r') as f:
                    data = json.load(f)
                    return abs(data.get('max_drawdown', 40.0))
        except Exception:
            pass

        # Estimate based on volatility ratio
        vol_ratio = self.get_volatility_ratio(symbol)
        estimated_dd = 25.0 * vol_ratio  # Base 25% * volatility
        return min(60.0, estimated_dd)

    def calculate_adjusted_threshold(
        self,
        symbol: str,
        base_threshold: float,
        current_drawdown: float = 0.0
    ) -> Tuple[float, SymbolCalibration]:
        """
        Calculate symbol-specific adjusted threshold.

        Args:
            symbol: Trading symbol
            base_threshold: Base threshold from HMM regime (e.g., -30.0)
            current_drawdown: Current position drawdown for CSSI calculation

        Returns:
            Tuple of (adjusted_threshold, calibration_data)
        """
        # Check cache first
        if symbol in self.calibration_cache:
            cached = self.calibration_cache[symbol]
            if datetime.now() - cached.calibration_time < self.cache_ttl:
                # Update with current base threshold
                if cached.base_threshold == base_threshold:
                    return cached.adjusted_threshold, cached

        # Get calibration factors
        vol_ratio = self.get_volatility_ratio(symbol)
        btc_corr = self.get_btc_correlation(symbol)
        correction_prob = self.get_correction_probability(symbol, current_drawdown)
        max_dd = self.get_historical_max_drawdown(symbol)

        # Calculate adjustments
        # Volatility adjustment: higher vol = wider threshold (more negative)
        vol_adjustment = (vol_ratio - 1) * 0.5  # +50% for 2x volatility

        # Correlation adjustment: lower correlation = wider threshold
        corr_adjustment = (1 - btc_corr) * 0.2  # +20% for uncorrelated

        # CSSI adjustment: higher correction probability = tighter threshold
        cssi_adjustment = -correction_prob * 0.1  # -10% if correction likely

        # Backtest adjustment: historical drawdown informs threshold
        backtest_adjustment = max_dd / 200  # +25% for 50% historical DD

        # Calculate final adjusted threshold
        total_adjustment = 1 + vol_adjustment + corr_adjustment + cssi_adjustment + backtest_adjustment
        adjusted = base_threshold * total_adjustment

        # Clamp to reasonable range
        adjusted = max(-50.0, min(-20.0, adjusted))

        # Create calibration record
        calibration = SymbolCalibration(
            symbol=symbol,
            volatility_ratio=vol_ratio,
            btc_correlation=btc_corr,
            correction_probability=correction_prob,
            historical_max_drawdown=max_dd,
            base_threshold=base_threshold,
            adjusted_threshold=adjusted,
            calibration_time=datetime.now()
        )

        # Cache and save
        self.calibration_cache[symbol] = calibration
        self._save_cache()

        return adjusted, calibration

    def get_threshold_for_symbol(
        self,
        symbol: str,
        hmm_regime: str = 'normal_vol',
        current_drawdown: float = 0.0
    ) -> float:
        """
        Get the calibrated averaging threshold for a symbol.

        Args:
            symbol: Trading symbol
            hmm_regime: Current HMM volatility regime
            current_drawdown: Current position drawdown

        Returns:
            Calibrated threshold (e.g., -32.5)
        """
        # Base thresholds from HMM regime
        regime_thresholds = {
            'low_vol': -25.0,
            'normal_vol': -30.0,
            'high_vol': -35.0,
            'crisis': -45.0
        }

        base_threshold = regime_thresholds.get(hmm_regime, -30.0)
        adjusted, _ = self.calculate_adjusted_threshold(symbol, base_threshold, current_drawdown)

        return adjusted

    def get_calibration_summary(self, symbols: list = None) -> Dict:
        """Get calibration summary for multiple symbols"""
        if symbols is None:
            symbols = list(self.calibration_cache.keys())

        summary = {
            'total_symbols': len(symbols),
            'calibrations': {},
            'statistics': {
                'avg_vol_ratio': 0,
                'avg_btc_corr': 0,
                'avg_threshold_adjustment': 0
            }
        }

        vol_ratios = []
        btc_corrs = []
        adjustments = []

        for symbol in symbols:
            if symbol in self.calibration_cache:
                cal = self.calibration_cache[symbol]
                summary['calibrations'][symbol] = cal.to_dict()
                vol_ratios.append(cal.volatility_ratio)
                btc_corrs.append(cal.btc_correlation)
                adjustments.append(cal.adjusted_threshold - cal.base_threshold)

        if vol_ratios:
            summary['statistics']['avg_vol_ratio'] = np.mean(vol_ratios)
            summary['statistics']['avg_btc_corr'] = np.mean(btc_corrs)
            summary['statistics']['avg_threshold_adjustment'] = np.mean(adjustments)

        return summary


# Singleton instance
_calibrator_instance = None

def get_threshold_calibrator(exchange=None) -> SymbolThresholdCalibrator:
    """Get or create the threshold calibrator singleton"""
    global _calibrator_instance
    if _calibrator_instance is None:
        _calibrator_instance = SymbolThresholdCalibrator(exchange)
    return _calibrator_instance


def get_symbol_adjusted_threshold(
    symbol: str,
    hmm_regime: str = 'normal_vol',
    current_drawdown: float = 0.0,
    exchange=None
) -> float:
    """
    Convenience function to get calibrated threshold for a symbol.

    Args:
        symbol: Trading symbol
        hmm_regime: Current HMM volatility regime
        current_drawdown: Current position drawdown
        exchange: Exchange instance (optional)

    Returns:
        Calibrated threshold (e.g., -32.5)
    """
    calibrator = get_threshold_calibrator(exchange)
    return calibrator.get_threshold_for_symbol(symbol, hmm_regime, current_drawdown)


if __name__ == '__main__':
    # Test the calibrator
    print("=" * 60)
    print("Symbol Threshold Calibrator V3.3.0 Test")
    print("=" * 60)

    calibrator = SymbolThresholdCalibrator()

    test_symbols = [
        'BTC/USDT:USDT',
        'ETH/USDT:USDT',
        'SOL/USDT:USDT',
        'DOGE/USDT:USDT',
        'POL/USDT:USDT',
        'DYM/USDT:USDT',
        'PEPE/USDT:USDT',
    ]

    print("\nCalibrated Thresholds (NORMAL_VOL regime, base=-30%):")
    print("-" * 60)
    print(f"{'Symbol':<20} {'Vol Ratio':<10} {'BTC Corr':<10} {'Threshold':<10}")
    print("-" * 60)

    for symbol in test_symbols:
        threshold, cal = calibrator.calculate_adjusted_threshold(symbol, -30.0)
        print(f"{symbol:<20} {cal.volatility_ratio:<10.2f} {cal.btc_correlation:<10.2f} {threshold:<10.1f}%")

    print("-" * 60)
    print("\nCalibration complete!")
