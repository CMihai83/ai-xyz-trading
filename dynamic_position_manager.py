#!/usr/bin/env python3
"""
Dynamic Position Manager V1.0.0 - Multi-Factor Position Sizing

Consortium Design: Claude + Grok
Date: January 16, 2026

Multi-factor position sizing based on:
1. Volatility (40% weight) - Historical volatility vs BTC
2. BTC Correlation (30% weight) - Rolling correlation with BTC
3. Trend Strength (20% weight) - ADX-based trend measurement
4. Funding Rate (10% weight) - Market sentiment indicator

Determines:
- base_margin: Starting position size
- total_allocation: Max capital per position (including averaging)
- max_averaging_steps: How many averaging steps allowed

Integrates with:
- TieredCapitalAllocation (market regimes)
- PositionSizingConfig (existing config)
- OpportunityCostCalibrator (exit timing)
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import os
import json

# Try to import exchange for live data
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

from dotenv import load_dotenv
load_dotenv()


class RiskTier(Enum):
    """Risk tier based on multi-factor score"""
    CONSERVATIVE = "CONSERVATIVE"  # Low risk, larger positions
    MODERATE = "MODERATE"          # Balanced approach
    AGGRESSIVE = "AGGRESSIVE"      # High risk, smaller positions, more averaging


@dataclass
class PositionTypeConfig:
    """Configuration for a position based on multi-factor analysis"""
    symbol: str
    risk_tier: RiskTier
    base_margin: float
    total_allocation: float
    max_averaging_steps: int
    leverage_max: int

    # Factor scores (0-1)
    volatility_score: float
    correlation_score: float
    trend_score: float
    funding_score: float
    position_type_score: float  # Combined PTS

    # Effective slots this position uses
    effective_slots: float

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'risk_tier': self.risk_tier.value,
            'base_margin': self.base_margin,
            'total_allocation': self.total_allocation,
            'max_averaging_steps': self.max_averaging_steps,
            'leverage_max': self.leverage_max,
            'volatility_score': self.volatility_score,
            'correlation_score': self.correlation_score,
            'trend_score': self.trend_score,
            'funding_score': self.funding_score,
            'position_type_score': self.position_type_score,
            'effective_slots': self.effective_slots
        }


class DynamicPositionManager:
    """
    Multi-Factor Dynamic Position Manager

    Calculates position parameters based on:
    - Volatility (40%): Higher vol = smaller positions, more averaging room
    - BTC Correlation (30%): High corr = reduce allocation (systemic risk)
    - Trend Strength (20%): Strong trend = larger positions, more averaging
    - Funding Rate (10%): Extreme funding = reduce exposure
    """

    # Factor weights (must sum to 1.0)
    WEIGHT_VOLATILITY = 0.40
    WEIGHT_CORRELATION = 0.30
    WEIGHT_TREND = 0.20
    WEIGHT_FUNDING = 0.10

    # Base parameters (scaled by equity)
    BASE_MARGIN_PCT = 0.005      # 0.5% of equity as max base margin
    TOTAL_ALLOCATION_PCT = 0.05  # 5% of equity as max allocation per position
    MAX_STEPS_BASE = 8           # Base max averaging steps

    # Thresholds for normalization
    VOL_THRESHOLD = 0.50         # 50% annualized vol = max score
    FUNDING_THRESHOLD = 0.001    # 0.1% funding = max score
    ADX_THRESHOLD = 50           # ADX 50 = max trend score

    # Risk tier thresholds (based on PTS)
    TIER_CONSERVATIVE = 0.35     # PTS < 0.35 = conservative
    TIER_MODERATE = 0.65         # 0.35 <= PTS < 0.65 = moderate

    # Capacity management
    BASE_ALLOCATION_REFERENCE = 25.0  # Reference for slot calculation
    HARD_CAP_POSITIONS = 30

    def __init__(self, equity: float = 400.0):
        """
        Initialize dynamic position manager.

        Args:
            equity: Current account equity in USD
        """
        self.equity = equity
        self.exchange = None
        self._init_exchange()

        # Cache for factor calculations
        self.factor_cache: Dict[str, Dict] = {}
        self.btc_data: Optional[pd.DataFrame] = None
        self.last_btc_update: Optional[datetime] = None

        # Position tracking
        self.active_positions: Dict[str, PositionTypeConfig] = {}

        print(f"DynamicPositionManager V1.0.0 initialized")
        print(f"   Equity: ${equity:.2f}")
        print(f"   Base margin max: ${equity * self.BASE_MARGIN_PCT:.2f}")
        print(f"   Total allocation max: ${equity * self.TOTAL_ALLOCATION_PCT:.2f}")

    def _init_exchange(self):
        """Initialize exchange connection for live data"""
        if not CCXT_AVAILABLE:
            print("   Warning: ccxt not available, using defaults")
            return

        try:
            self.exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY', ''),
                'secret': os.getenv('BITGET_API_SECRET', ''),
                'password': os.getenv('BITGET_API_PASSPHRASE', ''),
                'options': {'defaultType': 'swap'}
            })
            self.exchange.load_markets()
        except Exception as e:
            print(f"   Warning: Exchange init failed: {e}")
            self.exchange = None

    def update_equity(self, new_equity: float):
        """Update equity for dynamic calculations"""
        self.equity = new_equity

    def fetch_ohlcv(self, symbol: str, timeframe: str = '1h',
                    days: int = 14) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for factor calculation"""
        if not self.exchange:
            return None

        try:
            since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=500)

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['log_return'] = np.log(df['close'] / df['close'].shift(1))
            return df
        except Exception as e:
            return None

    def fetch_funding_rate(self, symbol: str) -> float:
        """Fetch current funding rate"""
        if not self.exchange:
            return 0.0

        try:
            # Bitget-specific funding rate fetch
            ticker = self.exchange.fetch_ticker(symbol)
            funding = ticker.get('info', {}).get('fundingRate', 0)
            return float(funding) if funding else 0.0
        except:
            return 0.0

    def get_btc_data(self) -> Optional[pd.DataFrame]:
        """Get BTC reference data (cached)"""
        now = datetime.now()

        # Refresh every hour
        if (self.btc_data is not None and
            self.last_btc_update and
            (now - self.last_btc_update).seconds < 3600):
            return self.btc_data

        self.btc_data = self.fetch_ohlcv('BTC/USDT:USDT')
        self.last_btc_update = now
        return self.btc_data

    # =========================================================================
    # FACTOR CALCULATIONS
    # =========================================================================

    def calculate_volatility_score(self, df: pd.DataFrame) -> float:
        """
        Calculate volatility score (0-1).
        Higher volatility = higher score = smaller position.
        """
        if df is None or df.empty or len(df) < 14:
            return 0.5  # Default moderate

        try:
            # Daily volatility (std of log returns)
            vol_daily = df['log_return'].std()

            # Annualize (assuming hourly data)
            vol_annual = vol_daily * np.sqrt(365 * 24)

            # Normalize to 0-1
            vol_score = min(vol_annual / self.VOL_THRESHOLD, 1.0)
            return max(0.0, vol_score)
        except:
            return 0.5

    def calculate_correlation_score(self, df: pd.DataFrame,
                                     btc_df: pd.DataFrame) -> float:
        """
        Calculate BTC correlation score (0-1).
        Higher correlation = higher score = reduce allocation.
        """
        if df is None or btc_df is None or len(df) < 14 or len(btc_df) < 14:
            return 0.5  # Default moderate

        try:
            # Align dataframes
            min_len = min(len(df), len(btc_df))
            asset_returns = df['log_return'].tail(min_len).dropna()
            btc_returns = btc_df['log_return'].tail(min_len).dropna()

            # Align lengths after dropna
            min_len = min(len(asset_returns), len(btc_returns))
            asset_returns = asset_returns.tail(min_len)
            btc_returns = btc_returns.tail(min_len)

            # Pearson correlation
            corr = np.corrcoef(asset_returns, btc_returns)[0, 1]

            if np.isnan(corr):
                return 0.5

            # Map -1 to 1 -> 0 to 1
            corr_score = (1 + corr) / 2
            return max(0.0, min(1.0, corr_score))
        except:
            return 0.5

    def calculate_trend_score(self, df: pd.DataFrame) -> float:
        """
        Calculate trend strength score (0-1) using ADX approximation.
        Higher trend = higher score = larger positions allowed.
        """
        if df is None or df.empty or len(df) < 14:
            return 0.5  # Default moderate

        try:
            high = df['high'].values
            low = df['low'].values
            close = df['close'].values

            # True Range
            tr = np.maximum(high[1:] - low[1:],
                           np.maximum(np.abs(high[1:] - close[:-1]),
                                     np.abs(low[1:] - close[:-1])))

            # Directional Movement
            plus_dm = np.where((high[1:] - high[:-1]) > (low[:-1] - low[1:]),
                               np.maximum(high[1:] - high[:-1], 0), 0)
            minus_dm = np.where((low[:-1] - low[1:]) > (high[1:] - high[:-1]),
                                np.maximum(low[:-1] - low[1:], 0), 0)

            # Smoothed averages (14 period)
            period = 14
            if len(tr) < period:
                return 0.5

            atr = pd.Series(tr).rolling(period).mean().iloc[-1]
            plus_di = 100 * pd.Series(plus_dm).rolling(period).mean().iloc[-1] / atr
            minus_di = 100 * pd.Series(minus_dm).rolling(period).mean().iloc[-1] / atr

            # DX and ADX approximation
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di + 0.001)

            # Normalize to 0-1
            trend_score = min(dx / self.ADX_THRESHOLD, 1.0)
            return max(0.0, trend_score)
        except:
            return 0.5

    def calculate_funding_score(self, symbol: str) -> float:
        """
        Calculate funding rate score (0-1).
        Extreme funding (positive or negative) = higher score = reduce exposure.
        """
        funding = self.fetch_funding_rate(symbol)

        # Absolute funding normalized
        funding_score = min(abs(funding) / self.FUNDING_THRESHOLD, 1.0)
        return max(0.0, funding_score)

    # =========================================================================
    # POSITION TYPE CALCULATION
    # =========================================================================

    def calculate_position_type_score(self, vol_score: float, corr_score: float,
                                       trend_score: float, funding_score: float) -> float:
        """
        Calculate combined Position Type Score (PTS).
        Higher PTS = higher risk = smaller position.

        Formula: PTS = 0.4*vol + 0.3*corr + 0.2*(1-trend) + 0.1*funding
        """
        # Note: trend_score is inverted (weak trend = higher risk)
        pts = (self.WEIGHT_VOLATILITY * vol_score +
               self.WEIGHT_CORRELATION * corr_score +
               self.WEIGHT_TREND * (1 - trend_score) +
               self.WEIGHT_FUNDING * funding_score)

        return max(0.0, min(1.0, pts))

    def get_risk_tier(self, pts: float) -> RiskTier:
        """Determine risk tier from PTS"""
        if pts < self.TIER_CONSERVATIVE:
            return RiskTier.CONSERVATIVE
        elif pts < self.TIER_MODERATE:
            return RiskTier.MODERATE
        else:
            return RiskTier.AGGRESSIVE

    def calculate_position_parameters(self, symbol: str,
                                        use_live_data: bool = True) -> PositionTypeConfig:
        """
        Calculate position parameters for a symbol using multi-factor analysis.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')
            use_live_data: Whether to fetch live data or use defaults

        Returns:
            PositionTypeConfig with all parameters
        """
        # Fetch data
        if use_live_data and self.exchange:
            df = self.fetch_ohlcv(symbol)
            btc_df = self.get_btc_data()
        else:
            df = None
            btc_df = None

        # Calculate factor scores
        vol_score = self.calculate_volatility_score(df)
        corr_score = self.calculate_correlation_score(df, btc_df)
        trend_score = self.calculate_trend_score(df)
        funding_score = self.calculate_funding_score(symbol) if use_live_data else 0.5

        # Combined PTS
        pts = self.calculate_position_type_score(vol_score, corr_score,
                                                  trend_score, funding_score)
        risk_tier = self.get_risk_tier(pts)

        # Calculate position parameters based on Grok's formulas
        base_margin_max = self.equity * self.BASE_MARGIN_PCT
        total_allocation_max = self.equity * self.TOTAL_ALLOCATION_PCT

        # base_margin: Reduced by high vol and corr, increased by trend
        base_margin = base_margin_max * (
            1 - 0.6 * vol_score - 0.3 * corr_score + 0.1 * trend_score
        )
        base_margin = max(0.30, min(base_margin_max, base_margin))  # Min $0.30

        # total_allocation: Reduced by high vol, corr, and funding
        total_allocation = total_allocation_max * (
            1 - 0.5 * vol_score - 0.3 * corr_score - 0.2 * funding_score
        )
        total_allocation = max(base_margin * 3, min(total_allocation_max, total_allocation))

        # max_averaging_steps: Increased by trend, reduced by vol and funding
        steps_multiplier = (
            0.5 * trend_score + 0.3 * (1 - vol_score) + 0.2 * (1 - funding_score)
        )
        max_steps = round(self.MAX_STEPS_BASE * steps_multiplier)
        max_steps = max(2, min(12, max_steps))  # Min 2, max 12

        # Leverage: Reduce for high risk
        if risk_tier == RiskTier.CONSERVATIVE:
            leverage_max = 10
        elif risk_tier == RiskTier.MODERATE:
            leverage_max = 7
        else:
            leverage_max = 5

        # Effective slots for capacity tracking
        effective_slots = total_allocation / self.BASE_ALLOCATION_REFERENCE

        config = PositionTypeConfig(
            symbol=symbol,
            risk_tier=risk_tier,
            base_margin=base_margin,
            total_allocation=total_allocation,
            max_averaging_steps=max_steps,
            leverage_max=leverage_max,
            volatility_score=vol_score,
            correlation_score=corr_score,
            trend_score=trend_score,
            funding_score=funding_score,
            position_type_score=pts,
            effective_slots=effective_slots
        )

        # Cache
        self.factor_cache[symbol] = config.to_dict()

        return config

    # =========================================================================
    # CAPACITY MANAGEMENT
    # =========================================================================

    def calculate_max_positions(self) -> int:
        """Calculate dynamic max positions based on equity and active positions"""
        # Base capacity: 25% of equity divided by reference allocation
        base_capacity = (self.equity * 0.25) / self.BASE_ALLOCATION_REFERENCE

        # Adjust for position mix if we have active positions
        if self.active_positions:
            total_alloc = sum(p.total_allocation for p in self.active_positions.values())
            avg_alloc = total_alloc / len(self.active_positions)
            weight_factor = self.BASE_ALLOCATION_REFERENCE / avg_alloc
            base_capacity *= weight_factor

        return min(int(base_capacity), self.HARD_CAP_POSITIONS)

    def calculate_effective_slots_used(self) -> float:
        """Calculate total effective slots used by active positions"""
        return sum(p.effective_slots for p in self.active_positions.values())

    def get_remaining_capacity(self) -> Dict:
        """Get remaining capacity for new positions"""
        max_pos = self.calculate_max_positions()
        slots_used = self.calculate_effective_slots_used()

        # Calculate remaining slots
        remaining_slots = max(0, max_pos - slots_used)

        # Calculate remaining capital
        total_allocated = sum(p.total_allocation for p in self.active_positions.values())
        remaining_capital = self.equity - total_allocated

        return {
            'max_positions': max_pos,
            'effective_slots_used': slots_used,
            'remaining_slots': remaining_slots,
            'remaining_capital': remaining_capital,
            'can_open_new': remaining_slots >= 0.5 and remaining_capital > 5.0
        }

    def can_open_position(self, symbol: str) -> Tuple[bool, str]:
        """Check if a new position can be opened"""
        capacity = self.get_remaining_capacity()

        if not capacity['can_open_new']:
            return False, f"No capacity: {capacity['remaining_slots']:.1f} slots, ${capacity['remaining_capital']:.2f} capital"

        # Get position parameters
        config = self.calculate_position_parameters(symbol)

        # Check if allocation fits
        if config.total_allocation > capacity['remaining_capital']:
            return False, f"Insufficient capital: need ${config.total_allocation:.2f}, have ${capacity['remaining_capital']:.2f}"

        return True, f"OK: {config.risk_tier.value} position, ${config.base_margin:.2f} base, ${config.total_allocation:.2f} allocation"

    # =========================================================================
    # POSITION TRACKING
    # =========================================================================

    def register_position(self, symbol: str, config: Optional[PositionTypeConfig] = None):
        """Register a new position"""
        if config is None:
            config = self.calculate_position_parameters(symbol)
        self.active_positions[symbol] = config

    def release_position(self, symbol: str):
        """Release a closed position"""
        if symbol in self.active_positions:
            del self.active_positions[symbol]

    def get_status(self) -> Dict:
        """Get current status of the position manager"""
        capacity = self.get_remaining_capacity()

        return {
            'equity': self.equity,
            'active_positions': len(self.active_positions),
            'max_positions': capacity['max_positions'],
            'effective_slots_used': capacity['effective_slots_used'],
            'remaining_slots': capacity['remaining_slots'],
            'remaining_capital': capacity['remaining_capital'],
            'can_open_new': capacity['can_open_new'],
            'positions': {
                symbol: config.to_dict()
                for symbol, config in self.active_positions.items()
            }
        }

    def print_status(self):
        """Print formatted status"""
        status = self.get_status()

        print("\n" + "=" * 70)
        print("DYNAMIC POSITION MANAGER STATUS")
        print("=" * 70)
        print(f"Equity: ${status['equity']:.2f}")
        print(f"Active Positions: {status['active_positions']}")
        print(f"Max Positions: {status['max_positions']}")
        print(f"Effective Slots: {status['effective_slots_used']:.1f} / {status['max_positions']}")
        print(f"Remaining Capital: ${status['remaining_capital']:.2f}")
        print(f"Can Open New: {status['can_open_new']}")

        if status['positions']:
            print("\n" + "-" * 70)
            print(f"{'Symbol':<20} {'Tier':<12} {'Base':<8} {'Alloc':<8} {'Steps':<6} {'PTS':<6}")
            print("-" * 70)

            for symbol, pos in status['positions'].items():
                print(f"{symbol:<20} {pos['risk_tier']:<12} "
                      f"${pos['base_margin']:<6.2f} ${pos['total_allocation']:<6.2f} "
                      f"{pos['max_averaging_steps']:<6} {pos['position_type_score']:.2f}")


# Singleton instance
_dynamic_manager: Optional[DynamicPositionManager] = None


def get_dynamic_position_manager(equity: float = None) -> DynamicPositionManager:
    """Get or create the dynamic position manager singleton"""
    global _dynamic_manager

    if _dynamic_manager is None:
        if equity is None:
            equity = float(os.getenv('INITIAL_BALANCE', 400.0))
        _dynamic_manager = DynamicPositionManager(equity)
    elif equity is not None:
        _dynamic_manager.update_equity(equity)

    return _dynamic_manager


if __name__ == '__main__':
    # Test the dynamic position manager
    print("Testing Dynamic Position Manager V1.0.0")
    print("=" * 70)

    manager = DynamicPositionManager(equity=404.0)

    # Test symbols
    test_symbols = [
        'BTC/USDT:USDT',
        'ETH/USDT:USDT',
        'SOL/USDT:USDT',
        'DOGE/USDT:USDT',
        'PEPE/USDT:USDT',
    ]

    print(f"\n{'Symbol':<20} {'Tier':<12} {'Base':<8} {'Alloc':<8} {'Steps':<6} {'Lev':<4} {'PTS':<6}")
    print("-" * 70)

    for symbol in test_symbols:
        config = manager.calculate_position_parameters(symbol, use_live_data=True)
        print(f"{symbol:<20} {config.risk_tier.value:<12} "
              f"${config.base_margin:<6.2f} ${config.total_allocation:<6.2f} "
              f"{config.max_averaging_steps:<6} {config.leverage_max:<4}x "
              f"{config.position_type_score:.2f}")

        # Show factor breakdown
        print(f"  Factors: Vol={config.volatility_score:.2f}, "
              f"Corr={config.correlation_score:.2f}, "
              f"Trend={config.trend_score:.2f}, "
              f"Fund={config.funding_score:.2f}")

    # Test capacity
    print("\n" + "=" * 70)
    print("CAPACITY TEST")
    print("=" * 70)

    # Register some positions
    for symbol in test_symbols[:3]:
        config = manager.calculate_position_parameters(symbol)
        manager.register_position(symbol, config)

    manager.print_status()
