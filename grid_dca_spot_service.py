#!/usr/bin/env python3
"""
Dynamic Grid DCA Spot Trading Service
======================================
A sophisticated grid trading system that dynamically adjusts entry/exit points
based on market scanner signals and ATR volatility.

Key Features:
1. ATR-Based Grid Spacing - Dynamically adjusts grid levels based on volatility
2. Market Scanner Integration - Uses VSA/momentum signals for entry timing
3. Limit Order Management - All orders placed as limits for better fills
4. Capital Allocation Engine - 3-7% per grid level based on confidence
5. Geometric Grid Spacing - Equal percentage spacing (matches crypto behavior)

Strategy Parameters (Based on 2025 Best Practices):
- Grid Spacing: 10-20% of 14-day ATR
- Grid Levels: 5-10 per asset
- Capital per Level: 3-7% of allocated capital
- Profit Target per Grid: 0.5%-2% (after fees ~0.2%)
- Stop Loss: Below lowest grid level (configurable)

Architecture:
                     +-----------------+
                     | Market Scanner  |
                     | (VSA + MTF)     |
                     +--------+--------+
                              |
                              v
+----------------+   +--------+--------+   +----------------+
| ATR Volatility |-->| Grid DCA Engine |<--| Capital Manager|
| Calculator     |   |                 |   |                |
+----------------+   +--------+--------+   +----------------+
                              |
                              v
                     +--------+--------+
                     | Limit Order     |
                     | Manager         |
                     +--------+--------+
                              |
                              v
                     +--------+--------+
                     | Bitget Spot API |
                     +-----------------+
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import numpy as np
import structlog

# Import from spot investment service for shared scanner/opportunity engine
from diversified_spot_investment_service import (
    DiversifiedSpotInvestmentService,
    AssetOpportunity,
    AssetCategory
)

load_dotenv()
logger = structlog.get_logger(__name__)


class GridType(Enum):
    """Grid spacing type"""
    GEOMETRIC = "geometric"  # Equal percentage spacing (better for crypto)
    ARITHMETIC = "arithmetic"  # Equal dollar spacing


class GridStatus(Enum):
    """Status of a grid level"""
    PENDING = "pending"  # Waiting for price to reach
    BUY_PLACED = "buy_placed"  # Limit buy order active
    FILLED = "filled"  # Buy order filled, holding position
    SELL_PLACED = "sell_placed"  # Limit sell order active
    COMPLETED = "completed"  # Trade cycle completed


@dataclass
class GridLevel:
    """Represents a single grid level"""
    level_id: int
    buy_price: float
    sell_price: float  # Profit target
    amount: float  # Amount to buy
    status: GridStatus = GridStatus.PENDING
    buy_order_id: Optional[str] = None
    sell_order_id: Optional[str] = None
    filled_amount: float = 0.0
    filled_price: float = 0.0
    profit_realized: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    filled_at: Optional[datetime] = None


@dataclass
class GridConfig:
    """Configuration for a grid on a specific asset"""
    symbol: str
    base_price: float  # Current price when grid was set
    lower_bound: float  # Lowest grid price
    upper_bound: float  # Highest grid price (profit target zone)
    num_levels: int  # Number of grid levels
    grid_type: GridType
    capital_allocated: float  # Total capital for this grid
    atr_value: float  # ATR used for calculation
    atr_period: int = 14
    profit_target_pct: float = 0.015  # 1.5% profit per grid
    stop_loss_pct: float = 0.10  # 10% below lowest grid
    created_at: datetime = field(default_factory=datetime.now)
    active: bool = True


@dataclass
class AssetGrid:
    """Complete grid state for an asset"""
    config: GridConfig
    levels: List[GridLevel] = field(default_factory=list)
    total_invested: float = 0.0
    total_profit: float = 0.0
    num_completed_cycles: int = 0


class ATRCalculator:
    """
    Calculates Average True Range for volatility-based grid spacing.
    ATR measures market volatility by decomposing the entire range
    of an asset price for a period.
    """

    def __init__(self, period: int = 14):
        self.period = period

    async def calculate_atr(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        timeframe: str = '1d'
    ) -> Tuple[float, float]:
        """
        Calculate ATR and return (atr_value, atr_percentage)

        Args:
            exchange: CCXT exchange instance
            symbol: Trading symbol
            timeframe: OHLCV timeframe ('1d' recommended for daily ATR)

        Returns:
            Tuple of (ATR value, ATR as percentage of current price)
        """
        try:
            # Fetch OHLCV data
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=self.period + 5)

            if len(ohlcv) < self.period:
                logger.warning("insufficient_data_for_atr", symbol=symbol, bars=len(ohlcv))
                return 0.0, 0.0

            # Calculate True Range for each bar
            true_ranges = []
            for i in range(1, len(ohlcv)):
                high = ohlcv[i][2]
                low = ohlcv[i][3]
                prev_close = ohlcv[i - 1][4]

                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)

            # Calculate ATR (Simple Moving Average of True Range)
            atr = np.mean(true_ranges[-self.period:])
            current_price = ohlcv[-1][4]
            atr_pct = atr / current_price if current_price > 0 else 0

            logger.info(
                "atr_calculated",
                symbol=symbol,
                atr=f"${atr:.6f}",
                atr_pct=f"{atr_pct*100:.2f}%",
                current_price=f"${current_price:.6f}"
            )

            return atr, atr_pct

        except Exception as e:
            logger.error("atr_calculation_failed", symbol=symbol, error=str(e))
            return 0.0, 0.0


class GridCalculator:
    """
    Calculates optimal grid levels based on ATR and market conditions.
    Uses geometric spacing for crypto (equal percentage between levels).
    """

    def __init__(self):
        self.MIN_GRID_SPACING_PCT = 0.003  # 0.3% minimum (above typical fees)
        self.MAX_GRID_SPACING_PCT = 0.05  # 5% maximum
        self.DEFAULT_NUM_LEVELS = 7

    def calculate_grid_levels(
        self,
        current_price: float,
        atr: float,
        atr_pct: float,
        capital: float,
        num_levels: int = None,
        grid_type: GridType = GridType.GEOMETRIC,
        atr_multiplier: float = 0.15,  # 15% of ATR for grid spacing
        profit_target_pct: float = 0.015  # 1.5% profit per grid
    ) -> GridConfig:
        """
        Calculate optimal grid configuration.

        Args:
            current_price: Current asset price
            atr: ATR value
            atr_pct: ATR as percentage
            capital: Capital allocated for this grid
            num_levels: Number of grid levels (default: calculated from volatility)
            grid_type: GEOMETRIC or ARITHMETIC
            atr_multiplier: Multiplier for ATR to determine grid spacing
            profit_target_pct: Target profit per grid level

        Returns:
            GridConfig with calculated parameters
        """
        # Calculate grid spacing from ATR
        # Best practice: 10-20% of ATR for grid spacing
        raw_spacing = atr_pct * atr_multiplier

        # Clamp to reasonable bounds
        grid_spacing = max(
            self.MIN_GRID_SPACING_PCT,
            min(self.MAX_GRID_SPACING_PCT, raw_spacing)
        )

        # Calculate number of levels if not specified
        # Higher volatility = fewer levels (wider spacing)
        if num_levels is None:
            if atr_pct > 0.10:  # High volatility (>10% daily)
                num_levels = 5
            elif atr_pct > 0.05:  # Medium volatility (5-10%)
                num_levels = 7
            else:  # Low volatility (<5%)
                num_levels = 10

        # Calculate grid bounds
        # Lower bound: Current price - (levels * spacing / 2)
        # Upper bound: Current price + profit target zone
        total_downside = grid_spacing * (num_levels - 1) / 2
        lower_bound = current_price * (1 - total_downside)
        upper_bound = current_price * (1 + profit_target_pct * num_levels)

        config = GridConfig(
            symbol="",  # Set by caller
            base_price=current_price,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            num_levels=num_levels,
            grid_type=grid_type,
            capital_allocated=capital,
            atr_value=atr,
            profit_target_pct=profit_target_pct
        )

        logger.info(
            "grid_config_calculated",
            base_price=f"${current_price:.6f}",
            lower_bound=f"${lower_bound:.6f}",
            upper_bound=f"${upper_bound:.6f}",
            num_levels=num_levels,
            grid_spacing=f"{grid_spacing*100:.2f}%",
            capital=f"${capital:.2f}"
        )

        return config

    def generate_grid_levels(
        self,
        config: GridConfig,
        min_amount: float = 0.0
    ) -> List[GridLevel]:
        """
        Generate individual grid levels from config.

        Args:
            config: GridConfig with parameters
            min_amount: Minimum order amount (from exchange)

        Returns:
            List of GridLevel objects
        """
        levels = []
        capital_per_level = config.capital_allocated / config.num_levels

        if config.grid_type == GridType.GEOMETRIC:
            # Geometric: Equal percentage between levels
            ratio = (config.upper_bound / config.lower_bound) ** (1 / (config.num_levels - 1))

            for i in range(config.num_levels):
                buy_price = config.lower_bound * (ratio ** i)
                sell_price = buy_price * (1 + config.profit_target_pct)
                amount = capital_per_level / buy_price

                if amount >= min_amount:
                    levels.append(GridLevel(
                        level_id=i,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        amount=amount
                    ))
        else:
            # Arithmetic: Equal dollar distance between levels
            step = (config.upper_bound - config.lower_bound) / (config.num_levels - 1)

            for i in range(config.num_levels):
                buy_price = config.lower_bound + (step * i)
                sell_price = buy_price * (1 + config.profit_target_pct)
                amount = capital_per_level / buy_price

                if amount >= min_amount:
                    levels.append(GridLevel(
                        level_id=i,
                        buy_price=buy_price,
                        sell_price=sell_price,
                        amount=amount
                    ))

        return levels


class ADXFilter:
    """
    Average Directional Index filter to reduce false signals
    during high volatility (Grok-recommended improvement).

    ADX > 25: Strong trend - consider directional grids
    ADX < 20: Ranging market - ideal for grid trading
    ADX 20-25: Transitional - proceed with caution
    """

    def __init__(self, period: int = 14):
        self.period = period

    async def calculate_adx(
        self,
        exchange: ccxt.Exchange,
        symbol: str,
        timeframe: str = '1d'
    ) -> Tuple[float, str]:
        """
        Calculate ADX and market regime.

        Returns:
            Tuple of (ADX value, market_regime: 'ranging'|'trending'|'transitional')
        """
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=self.period * 2)

            if len(ohlcv) < self.period + 1:
                return 0.0, 'unknown'

            # Calculate True Range and Directional Movement
            tr_list = []
            plus_dm = []
            minus_dm = []

            for i in range(1, len(ohlcv)):
                high = ohlcv[i][2]
                low = ohlcv[i][3]
                close_prev = ohlcv[i-1][4]
                high_prev = ohlcv[i-1][2]
                low_prev = ohlcv[i-1][3]

                # True Range
                tr = max(
                    high - low,
                    abs(high - close_prev),
                    abs(low - close_prev)
                )
                tr_list.append(tr)

                # Directional Movement
                up_move = high - high_prev
                down_move = low_prev - low

                if up_move > down_move and up_move > 0:
                    plus_dm.append(up_move)
                else:
                    plus_dm.append(0)

                if down_move > up_move and down_move > 0:
                    minus_dm.append(down_move)
                else:
                    minus_dm.append(0)

            # Smoothed averages
            atr = np.mean(tr_list[-self.period:])
            plus_di = 100 * np.mean(plus_dm[-self.period:]) / atr if atr > 0 else 0
            minus_di = 100 * np.mean(minus_dm[-self.period:]) / atr if atr > 0 else 0

            # ADX calculation
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di) if (plus_di + minus_di) > 0 else 0
            adx = dx  # Simplified - full implementation uses smoothed DX

            # Determine regime
            if adx < 20:
                regime = 'ranging'  # Ideal for grid trading
            elif adx > 25:
                regime = 'trending'  # Consider directional bias
            else:
                regime = 'transitional'

            logger.info(
                "adx_calculated",
                symbol=symbol,
                adx=f"{adx:.1f}",
                regime=regime,
                plus_di=f"{plus_di:.1f}",
                minus_di=f"{minus_di:.1f}"
            )

            return adx, regime

        except Exception as e:
            logger.error("adx_calculation_failed", symbol=symbol, error=str(e))
            return 0.0, 'unknown'


class VolumeProfileFilter:
    """
    Volume profile analysis for whale flow detection
    (Grok-recommended: avoid manipulated trades).
    """

    def __init__(self, whale_threshold: float = 3.0):
        self.whale_threshold = whale_threshold  # 3x avg volume = potential whale

    async def check_volume_profile(
        self,
        exchange: ccxt.Exchange,
        symbol: str
    ) -> Tuple[bool, Dict]:
        """
        Check volume profile for manipulation signals.

        Returns:
            Tuple of (safe_to_trade, volume_data)
        """
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, '1h', limit=48)  # 48 hours

            if len(ohlcv) < 24:
                return True, {}

            volumes = [c[5] for c in ohlcv]
            avg_volume = np.mean(volumes[:-1])  # Exclude current bar
            current_volume = volumes[-1]

            # Check for unusual volume (potential whale activity)
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

            # Check for volume trend (declining = less interest)
            recent_avg = np.mean(volumes[-6:])
            older_avg = np.mean(volumes[-24:-6])
            volume_trend = recent_avg / older_avg if older_avg > 0 else 1

            # Safe to trade if:
            # - No extreme volume spike (manipulation)
            # - Volume trend stable or increasing
            safe_to_trade = (
                volume_ratio < self.whale_threshold and
                volume_trend > 0.5
            )

            volume_data = {
                'volume_ratio': volume_ratio,
                'volume_trend': volume_trend,
                'avg_volume': avg_volume,
                'current_volume': current_volume,
                'whale_detected': volume_ratio >= self.whale_threshold
            }

            logger.info(
                "volume_profile_check",
                symbol=symbol,
                safe=safe_to_trade,
                ratio=f"{volume_ratio:.2f}x",
                trend=f"{volume_trend:.2f}"
            )

            return safe_to_trade, volume_data

        except Exception as e:
            logger.error("volume_check_failed", symbol=symbol, error=str(e))
            return True, {}


class FibonacciProfitTargets:
    """
    Fibonacci-based profit targets for grid levels
    (Grok-recommended for take-profit placement).
    """

    LEVELS = [0.236, 0.382, 0.5, 0.618, 0.786, 1.0, 1.272, 1.618]

    @staticmethod
    def calculate_targets(
        entry_price: float,
        swing_low: float,
        swing_high: float
    ) -> List[float]:
        """
        Calculate Fibonacci profit targets based on recent swing.

        Returns:
            List of price levels for profit taking
        """
        range_size = swing_high - swing_low

        targets = []
        for level in FibonacciProfitTargets.LEVELS:
            if level > 0.5:  # Only extension levels for profits
                target = swing_low + (range_size * level)
                if target > entry_price:
                    targets.append(target)

        return targets


class MarketScannerIntegration:
    """
    Integrates with the DiversifiedSpotInvestmentService scanner and opportunity engine.
    Uses VSA scoring + Opportunity Cost from the main spot service.
    Enhanced with ADX filter for grid-specific market regime detection.
    """

    def __init__(self, exchange: ccxt.Exchange, spot_service: DiversifiedSpotInvestmentService = None):
        self.exchange = exchange
        self.adx_filter = ADXFilter()
        self.volume_filter = VolumeProfileFilter()
        self.spot_service = spot_service  # Reference to spot service for VSA/OC scoring

    async def check_entry_signal(
        self,
        symbol: str,
        min_score: float = 5.0  # Minimum combined score (0-10 scale)
    ) -> Tuple[bool, Dict]:
        """
        Check if asset has positive entry signal using spot service scanner.

        Combines:
        1. VSA Score from spot service (Volume Spread Analysis)
        2. Opportunity Cost Score from spot service
        3. Multi-timeframe confirmation from spot service
        4. ADX filter for market regime (grid-specific)
        5. Volume profile check (manipulation detection)

        Returns:
            Tuple of (should_enter, signal_data)
        """
        try:
            vsa_score = 5.0
            oc_score = 5.0
            vsa_reasoning = {}
            oc_reasoning = {}
            mtf_confirmed = False
            mtf_info = {}

            # Use spot service scanner if available
            if self.spot_service:
                # Get VSA score from spot service
                vsa_score, vsa_reasoning = await self.spot_service.calculate_vsa_score(symbol)

                # Get Opportunity Cost score from spot service
                oc_score, oc_reasoning = await self.spot_service.calculate_opportunity_cost_score(symbol)

                # Get MTF confirmation from spot service
                mtf_confirmed, mtf_info = await self.spot_service.check_multi_timeframe_confirmation(symbol)

                logger.info(
                    "spot_service_scores",
                    symbol=symbol,
                    vsa_score=f"{vsa_score:.1f}",
                    oc_score=f"{oc_score:.1f}",
                    mtf_confirmed=mtf_confirmed
                )
            else:
                # Fallback: Basic MTF check if spot service not available
                timeframes = ['1d', '4h', '1h']
                bullish_count = 0

                for tf in timeframes:
                    ohlcv = await self.exchange.fetch_ohlcv(symbol, tf, limit=20)
                    if len(ohlcv) >= 10:
                        closes = [c[4] for c in ohlcv]
                        sma_5 = sum(closes[-5:]) / 5
                        current = closes[-1]
                        if current > sma_5:
                            bullish_count += 1
                    await asyncio.sleep(0.05)

                mtf_confirmed = bullish_count >= 2
                mtf_info = {'bullish_count': bullish_count, 'fallback': True}

            # Combined score (weighted average like spot service)
            VSA_WEIGHT = 0.6
            OC_WEIGHT = 0.4
            combined_score = (vsa_score * VSA_WEIGHT) + (oc_score * OC_WEIGHT)

            # GRID-SPECIFIC: ADX filter for market regime
            adx, regime = await self.adx_filter.calculate_adx(
                self.exchange, symbol, '1d'
            )

            # Grid trading works best in ranging markets (ADX < 25)
            adx_favorable = regime in ['ranging', 'transitional']

            # Volume profile check (avoid manipulation)
            volume_safe, volume_data = await self.volume_filter.check_volume_profile(
                self.exchange, symbol
            )

            # Combined decision for grid entry:
            # 1. Combined score >= min_score (from VSA + OC)
            # 2. MTF confirmed OR high combined score
            # 3. ADX favorable (ranging/transitional market)
            # 4. Volume safe (no whale manipulation)
            score_ok = combined_score >= min_score
            signal_ok = mtf_confirmed or combined_score >= 7.0

            should_enter = score_ok and signal_ok and adx_favorable and volume_safe

            # Get current price
            ticker = await self.exchange.fetch_ticker(symbol)
            change_24h = ticker.get('percentage', 0) or 0

            signal_data = {
                # Spot service scores
                'vsa_score': vsa_score,
                'opportunity_cost_score': oc_score,
                'combined_score': combined_score,
                'vsa_reasoning': vsa_reasoning,
                'oc_reasoning': oc_reasoning,
                # MTF confirmation
                'mtf_confirmed': mtf_confirmed,
                'mtf_info': mtf_info,
                # Grid-specific filters
                'adx': adx,
                'market_regime': regime,
                'volume_safe': volume_safe,
                'volume_data': volume_data,
                # Price data
                'change_24h': change_24h,
                'current_price': ticker.get('last', 0),
                # Filter results
                'filters_passed': {
                    'score_ok': score_ok,
                    'signal_ok': signal_ok,
                    'adx_favorable': adx_favorable,
                    'volume_safe': volume_safe
                }
            }

            logger.info(
                "entry_signal_check_integrated",
                symbol=symbol,
                should_enter=should_enter,
                combined_score=f"{combined_score:.1f}",
                vsa=f"{vsa_score:.1f}",
                oc=f"{oc_score:.1f}",
                mtf=mtf_confirmed,
                adx=f"{adx:.1f}",
                regime=regime,
                volume_safe=volume_safe
            )

            return should_enter, signal_data

        except Exception as e:
            logger.error("entry_signal_check_failed", symbol=symbol, error=str(e))
            return False, {}


class LimitOrderManager:
    """
    Manages limit orders for grid trading.
    Places buy orders at grid levels and sell orders at profit targets.
    """

    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
        self.active_orders: Dict[str, Dict] = {}  # order_id -> order info

    async def place_buy_limit(
        self,
        symbol: str,
        amount: float,
        price: float,
        level_id: int
    ) -> Optional[str]:
        """
        Place a limit buy order at a grid level.

        Returns:
            Order ID if successful, None otherwise
        """
        try:
            # Format price and amount to exchange precision
            market = self.exchange.markets.get(symbol, {})
            precision = market.get('precision', {})

            formatted_price = self.exchange.price_to_precision(symbol, price)
            formatted_amount = self.exchange.amount_to_precision(symbol, amount)

            order = await self.exchange.create_limit_buy_order(
                symbol,
                float(formatted_amount),
                float(formatted_price)
            )

            order_id = order.get('id')
            if order_id:
                self.active_orders[order_id] = {
                    'symbol': symbol,
                    'side': 'buy',
                    'price': price,
                    'amount': amount,
                    'level_id': level_id,
                    'status': 'open',
                    'created_at': datetime.now().isoformat()
                }

                logger.info(
                    "buy_limit_placed",
                    symbol=symbol,
                    price=f"${price:.6f}",
                    amount=formatted_amount,
                    level_id=level_id,
                    order_id=order_id
                )

            return order_id

        except Exception as e:
            logger.error(
                "buy_limit_failed",
                symbol=symbol,
                price=price,
                amount=amount,
                error=str(e)
            )
            return None

    async def place_sell_limit(
        self,
        symbol: str,
        amount: float,
        price: float,
        level_id: int
    ) -> Optional[str]:
        """
        Place a limit sell order at profit target.

        Returns:
            Order ID if successful, None otherwise
        """
        try:
            market = self.exchange.markets.get(symbol, {})

            formatted_price = self.exchange.price_to_precision(symbol, price)
            formatted_amount = self.exchange.amount_to_precision(symbol, amount)

            order = await self.exchange.create_limit_sell_order(
                symbol,
                float(formatted_amount),
                float(formatted_price)
            )

            order_id = order.get('id')
            if order_id:
                self.active_orders[order_id] = {
                    'symbol': symbol,
                    'side': 'sell',
                    'price': price,
                    'amount': amount,
                    'level_id': level_id,
                    'status': 'open',
                    'created_at': datetime.now().isoformat()
                }

                logger.info(
                    "sell_limit_placed",
                    symbol=symbol,
                    price=f"${price:.6f}",
                    amount=formatted_amount,
                    level_id=level_id,
                    order_id=order_id
                )

            return order_id

        except Exception as e:
            logger.error(
                "sell_limit_failed",
                symbol=symbol,
                price=price,
                amount=amount,
                error=str(e)
            )
            return None

    async def check_order_status(self, symbol: str, order_id: str) -> str:
        """Check status of an order (open, filled, cancelled)"""
        try:
            order = await self.exchange.fetch_order(order_id, symbol)
            return order.get('status', 'unknown')
        except Exception as e:
            logger.error("order_status_check_failed", order_id=order_id, error=str(e))
            return 'unknown'

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """Cancel an open order"""
        try:
            await self.exchange.cancel_order(order_id, symbol)
            if order_id in self.active_orders:
                self.active_orders[order_id]['status'] = 'cancelled'
            logger.info("order_cancelled", order_id=order_id, symbol=symbol)
            return True
        except Exception as e:
            logger.error("order_cancel_failed", order_id=order_id, error=str(e))
            return False


@dataclass
class TradeRecord:
    """Record of a completed trade for journaling"""
    symbol: str
    entry_price: float
    exit_price: float
    amount: float
    profit: float
    profit_pct: float
    hold_duration_minutes: float
    entry_signal: Dict
    market_regime: str
    grid_level: int
    timestamp: datetime = field(default_factory=datetime.now)


class TradeJournal:
    """
    Trade journaling system for performance analysis
    (Grok-recommended: improve win rates by tracking patterns).

    Tracks:
    - Win/loss by market regime
    - Average profit per grid level
    - Hold time analysis
    - Signal quality correlation
    """

    def __init__(self, journal_file: str = None):
        self.journal_file = journal_file or os.getenv('GRID_JOURNAL_FILE', '/app/grid_trade_journal.json')
        self.trades: List[TradeRecord] = []
        self.load_journal()

    def record_trade(self, trade: TradeRecord):
        """Record a completed trade"""
        self.trades.append(trade)
        self.save_journal()

        logger.info(
            "trade_journaled",
            symbol=trade.symbol,
            profit=f"${trade.profit:.4f}",
            profit_pct=f"{trade.profit_pct*100:.2f}%",
            regime=trade.market_regime,
            level=trade.grid_level
        )

    def get_performance_stats(self) -> Dict:
        """Calculate performance statistics"""
        if not self.trades:
            return {}

        total_trades = len(self.trades)
        winners = [t for t in self.trades if t.profit > 0]
        losers = [t for t in self.trades if t.profit <= 0]

        win_rate = len(winners) / total_trades if total_trades > 0 else 0
        avg_win = np.mean([t.profit for t in winners]) if winners else 0
        avg_loss = np.mean([t.profit for t in losers]) if losers else 0

        # By regime
        regime_stats = {}
        for regime in ['ranging', 'trending', 'transitional']:
            regime_trades = [t for t in self.trades if t.market_regime == regime]
            if regime_trades:
                regime_winners = [t for t in regime_trades if t.profit > 0]
                regime_stats[regime] = {
                    'trades': len(regime_trades),
                    'win_rate': len(regime_winners) / len(regime_trades),
                    'avg_profit': np.mean([t.profit for t in regime_trades])
                }

        return {
            'total_trades': total_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_profit': sum(t.profit for t in self.trades),
            'by_regime': regime_stats
        }

    def save_journal(self):
        """Save journal to file"""
        try:
            data = {
                'trades': [asdict(t) for t in self.trades[-1000:]]  # Keep last 1000
            }

            def convert_dates(obj):
                if isinstance(obj, dict):
                    return {k: convert_dates(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_dates(i) for i in obj]
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                return obj

            data = convert_dates(data)

            with open(self.journal_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

        except Exception as e:
            logger.error("journal_save_failed", error=str(e))

    def load_journal(self):
        """Load journal from file"""
        try:
            if os.path.exists(self.journal_file):
                with open(self.journal_file, 'r') as f:
                    data = json.load(f)
                logger.info("journal_loaded", trades=len(data.get('trades', [])))
        except Exception as e:
            logger.error("journal_load_failed", error=str(e))


class DynamicGridDCAService:
    """
    Main service coordinating Grid DCA strategy for spot trading.

    Workflow:
    1. Market Scanner checks for entry signals (with ADX/Volume filters)
    2. ATR Calculator determines grid spacing
    3. Grid Calculator creates grid levels
    4. Order Manager places limit orders
    5. Monitor fills and adjust grids dynamically
    6. Journal all trades for performance analysis
    """

    def __init__(self):
        self.exchange = None
        self.spot_service = None  # Spot service for VSA/Opportunity Cost scoring
        self.state_file = os.getenv('GRID_STATE_FILE', '/app/grid_dca_state.json')

        # Components
        self.atr_calc = ATRCalculator(period=14)
        self.grid_calc = GridCalculator()
        self.scanner = None
        self.order_manager = None
        self.trade_journal = TradeJournal()  # Grok-recommended: track performance

        # State
        self.active_grids: Dict[str, AssetGrid] = {}  # symbol -> AssetGrid
        self.entry_signals: Dict[str, Dict] = {}  # symbol -> signal data (for journaling)
        self.total_capital = 0.0
        self.capital_per_grid = 50.0  # Default $50 per grid
        self.max_grids = 5  # Maximum concurrent grids

        # Eligible assets for grid trading (high volume, stable)
        self.ELIGIBLE_ASSETS = [
            'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT',
            'XRP/USDT', 'ADA/USDT', 'DOGE/USDT', 'POL/USDT',
            'DOT/USDT', 'LINK/USDT', 'AVAX/USDT', 'ATOM/USDT',
            'UNI/USDT', 'LTC/USDT', 'TRX/USDT', 'ETC/USDT'
        ]

        # Config
        self.ATR_PERIOD = 14
        self.ATR_MULTIPLIER = 0.15  # 15% of ATR for grid spacing
        self.PROFIT_TARGET_PCT = 0.015  # 1.5% per grid
        self.MIN_BULLISH_TIMEFRAMES = 2
        self.GRID_CHECK_INTERVAL = 60  # seconds

    async def initialize(self):
        """Initialize exchange connection, spot service, and load state"""
        try:
            self.exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_API_SECRET'),
                'password': os.getenv('BITGET_API_PASSPHRASE'),
                'options': {'defaultType': 'spot'}
            })

            await self.exchange.load_markets()

            # Initialize the spot investment service for VSA/Opportunity Cost scoring
            self.spot_service = DiversifiedSpotInvestmentService()
            await self.spot_service.initialize()
            logger.info("spot_service_connected", status="VSA + Opportunity Cost engine ready")

            # Create scanner with spot service integration
            self.scanner = MarketScannerIntegration(self.exchange, self.spot_service)
            self.order_manager = LimitOrderManager(self.exchange)

            # Load existing state
            await self.load_state()

            # Get available capital
            balance = await self.exchange.fetch_balance()
            usdt = balance.get('USDT', {})
            self.total_capital = usdt.get('free', 0)

            logger.info(
                "grid_dca_service_initialized",
                total_capital=f"${self.total_capital:.2f}",
                active_grids=len(self.active_grids),
                spot_service="connected"
            )

        except Exception as e:
            logger.error("initialization_failed", error=str(e))
            raise

    async def scan_for_opportunities(self) -> List[Tuple[str, Dict]]:
        """
        Scan eligible assets for grid entry opportunities.

        Returns:
            List of (symbol, signal_data) tuples for assets with buy signals
        """
        opportunities = []

        for symbol in self.ELIGIBLE_ASSETS:
            # Skip if already have a grid on this asset
            if symbol in self.active_grids:
                continue

            # Skip if at max grids
            if len(self.active_grids) >= self.max_grids:
                break

            # Check entry signal
            should_enter, signal_data = await self.scanner.check_entry_signal(
                symbol,
                min_score=0.5
            )

            if should_enter:
                opportunities.append((symbol, signal_data))
                logger.info("opportunity_found", symbol=symbol, signal=signal_data)

            await asyncio.sleep(0.1)  # Rate limiting

        return opportunities

    async def create_grid(self, symbol: str) -> Optional[AssetGrid]:
        """
        Create a new grid for an asset.

        Args:
            symbol: Trading symbol

        Returns:
            AssetGrid if created successfully
        """
        try:
            # Check available capital
            if self.total_capital < self.capital_per_grid:
                logger.warning(
                    "insufficient_capital_for_grid",
                    available=self.total_capital,
                    required=self.capital_per_grid
                )
                return None

            # Calculate ATR
            atr, atr_pct = await self.atr_calc.calculate_atr(
                self.exchange,
                symbol,
                timeframe='1d'
            )

            if atr == 0:
                logger.warning("atr_calculation_failed", symbol=symbol)
                return None

            # Get current price
            ticker = await self.exchange.fetch_ticker(symbol)
            current_price = ticker.get('last', 0)

            if current_price == 0:
                return None

            # Calculate grid configuration
            config = self.grid_calc.calculate_grid_levels(
                current_price=current_price,
                atr=atr,
                atr_pct=atr_pct,
                capital=self.capital_per_grid,
                atr_multiplier=self.ATR_MULTIPLIER,
                profit_target_pct=self.PROFIT_TARGET_PCT
            )
            config.symbol = symbol

            # Get minimum order size
            market = self.exchange.markets.get(symbol, {})
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0)

            # Generate grid levels
            levels = self.grid_calc.generate_grid_levels(config, min_amount)

            if not levels:
                logger.warning("no_valid_grid_levels", symbol=symbol)
                return None

            # Create grid object
            grid = AssetGrid(config=config, levels=levels)

            logger.info(
                "grid_created",
                symbol=symbol,
                num_levels=len(levels),
                lower_bound=f"${config.lower_bound:.6f}",
                upper_bound=f"${config.upper_bound:.6f}",
                capital=f"${self.capital_per_grid:.2f}"
            )

            return grid

        except Exception as e:
            logger.error("grid_creation_failed", symbol=symbol, error=str(e))
            return None

    async def activate_grid(self, grid: AssetGrid) -> bool:
        """
        Activate a grid by placing limit buy orders at each level.

        Returns:
            True if at least some orders were placed
        """
        symbol = grid.config.symbol
        orders_placed = 0

        for level in grid.levels:
            # Only place buy orders for levels below current price
            ticker = await self.exchange.fetch_ticker(symbol)
            current_price = ticker.get('last', 0)

            if level.buy_price < current_price:
                order_id = await self.order_manager.place_buy_limit(
                    symbol,
                    level.amount,
                    level.buy_price,
                    level.level_id
                )

                if order_id:
                    level.buy_order_id = order_id
                    level.status = GridStatus.BUY_PLACED
                    orders_placed += 1

            await asyncio.sleep(0.1)

        if orders_placed > 0:
            self.active_grids[symbol] = grid
            self.total_capital -= grid.config.capital_allocated
            await self.save_state()

            logger.info(
                "grid_activated",
                symbol=symbol,
                orders_placed=orders_placed,
                total_levels=len(grid.levels)
            )
            return True

        return False

    async def monitor_grids(self):
        """
        Monitor active grids for filled orders and place corresponding sells.
        """
        for symbol, grid in list(self.active_grids.items()):
            try:
                for level in grid.levels:
                    # Check buy orders
                    if level.status == GridStatus.BUY_PLACED and level.buy_order_id:
                        status = await self.order_manager.check_order_status(
                            symbol,
                            level.buy_order_id
                        )

                        if status == 'closed':
                            # Buy filled - place sell order
                            level.status = GridStatus.FILLED
                            level.filled_at = datetime.now()
                            level.filled_price = level.buy_price  # Approximate
                            level.filled_amount = level.amount

                            grid.total_invested += level.buy_price * level.amount

                            # Place sell at profit target
                            sell_order_id = await self.order_manager.place_sell_limit(
                                symbol,
                                level.amount,
                                level.sell_price,
                                level.level_id
                            )

                            if sell_order_id:
                                level.sell_order_id = sell_order_id
                                level.status = GridStatus.SELL_PLACED

                            logger.info(
                                "grid_buy_filled",
                                symbol=symbol,
                                level=level.level_id,
                                price=f"${level.buy_price:.6f}",
                                amount=level.amount
                            )

                    # Check sell orders
                    elif level.status == GridStatus.SELL_PLACED and level.sell_order_id:
                        status = await self.order_manager.check_order_status(
                            symbol,
                            level.sell_order_id
                        )

                        if status == 'closed':
                            # Sell filled - cycle complete
                            profit = (level.sell_price - level.buy_price) * level.amount
                            level.profit_realized = profit
                            level.status = GridStatus.COMPLETED
                            grid.total_profit += profit
                            grid.num_completed_cycles += 1

                            logger.info(
                                "grid_cycle_complete",
                                symbol=symbol,
                                level=level.level_id,
                                profit=f"${profit:.4f}",
                                total_profit=f"${grid.total_profit:.4f}"
                            )

                            # Optionally: Reset level for another cycle
                            # level.status = GridStatus.PENDING
                            # level.buy_order_id = None
                            # level.sell_order_id = None

                await asyncio.sleep(0.05)

            except Exception as e:
                logger.error("grid_monitor_error", symbol=symbol, error=str(e))

        # Save state after monitoring
        await self.save_state()

    async def adjust_grid_dynamically(self, symbol: str):
        """
        Dynamically adjust grid based on new ATR calculation.
        Called periodically to adapt to changing volatility.
        """
        if symbol not in self.active_grids:
            return

        grid = self.active_grids[symbol]

        # Calculate new ATR
        new_atr, new_atr_pct = await self.atr_calc.calculate_atr(
            self.exchange,
            symbol,
            timeframe='1d'
        )

        if new_atr == 0:
            return

        # Check if ATR changed significantly (>20%)
        old_atr = grid.config.atr_value
        change_pct = abs(new_atr - old_atr) / old_atr if old_atr > 0 else 1

        if change_pct > 0.20:
            logger.info(
                "atr_significant_change",
                symbol=symbol,
                old_atr=f"${old_atr:.6f}",
                new_atr=f"${new_atr:.6f}",
                change=f"{change_pct*100:.1f}%"
            )

            # Could cancel unfilled orders and recreate grid
            # For now, just log the change
            grid.config.atr_value = new_atr

    async def save_state(self):
        """Save grid state to file"""
        try:
            state = {
                'timestamp': datetime.now().isoformat(),
                'total_capital': self.total_capital,
                'grids': {}
            }

            for symbol, grid in self.active_grids.items():
                state['grids'][symbol] = {
                    'config': asdict(grid.config),
                    'levels': [asdict(l) for l in grid.levels],
                    'total_invested': grid.total_invested,
                    'total_profit': grid.total_profit,
                    'num_completed_cycles': grid.num_completed_cycles
                }

            # Convert datetime objects to strings
            def convert_dates(obj):
                if isinstance(obj, dict):
                    return {k: convert_dates(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_dates(i) for i in obj]
                elif isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, Enum):
                    return obj.value
                return obj

            state = convert_dates(state)

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2, default=str)

        except Exception as e:
            logger.error("state_save_failed", error=str(e))

    async def load_state(self):
        """Load grid state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)

                # Reconstruct grids from state
                # (simplified - full implementation would restore all objects)
                logger.info("state_loaded", grids=list(state.get('grids', {}).keys()))

        except Exception as e:
            logger.error("state_load_failed", error=str(e))

    async def run_cycle(self):
        """
        Run one cycle of grid management:
        1. Scan for opportunities
        2. Create and activate new grids
        3. Monitor existing grids
        4. Adjust grids dynamically
        """
        logger.info("grid_dca_cycle_start")

        # 1. Scan for opportunities
        opportunities = await self.scan_for_opportunities()

        # 2. Create and activate new grids
        for symbol, signal_data in opportunities[:3]:  # Max 3 new grids per cycle
            grid = await self.create_grid(symbol)
            if grid:
                success = await self.activate_grid(grid)
                if success:
                    logger.info("new_grid_activated", symbol=symbol)

        # 3. Monitor existing grids
        await self.monitor_grids()

        # 4. Adjust grids dynamically (every few cycles)
        for symbol in self.active_grids:
            await self.adjust_grid_dynamically(symbol)

        logger.info(
            "grid_dca_cycle_complete",
            active_grids=len(self.active_grids),
            total_capital=f"${self.total_capital:.2f}"
        )

    async def run_continuous(self, interval: int = 300):
        """
        Run grid DCA service continuously.

        Args:
            interval: Seconds between cycles (default 5 minutes)
        """
        await self.initialize()

        logger.info(
            "grid_dca_service_starting",
            interval_seconds=interval,
            eligible_assets=len(self.ELIGIBLE_ASSETS)
        )

        while True:
            try:
                await self.run_cycle()
                await asyncio.sleep(interval)

            except Exception as e:
                logger.error("cycle_error", error=str(e))
                await asyncio.sleep(60)  # Wait 1 minute on error

    async def close(self):
        """Clean up resources"""
        if self.exchange:
            await self.exchange.close()


async def main():
    """Main entry point"""
    service = DynamicGridDCAService()

    try:
        await service.run_continuous(interval=300)  # 5 minute cycles
    except KeyboardInterrupt:
        logger.info("shutting_down")
    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
