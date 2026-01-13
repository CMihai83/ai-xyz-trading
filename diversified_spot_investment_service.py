#!/usr/bin/env python3
"""
Diversified Spot Investment Service
=====================================
Manages excess futures margin by investing in diversified spot portfolio.

Architecture (Based on Grok Consultation):
1. Margin Management Module (MMM) - Transfers excess margin >$400 in $15 increments
2. Capital Allocation Engine (CAE) - Equal split: Crypto/Gold/Stocks (33.33% each)
3. Category Optimization Module (COM) - VSA scanner + opportunity cost allocation
4. Risk Management Framework (RMF) - Position limits, stop-loss, diversification

Asset Categories:
- Crypto: BTC, ETH, SOL, EGLD, etc. (60+ spot trading pairs)
- Gold: XAUT, PAXG (tokenized gold backed by physical reserves)
  NOTE: XAU/XAG are perpetual futures only, not available on spot API
- Stocks/RWA: High-correlation crypto proxies for stock market exposure
  ONDO (RWA protocol), RENDER (GPU/NVIDIA proxy), FET/TAO/AGIX (AI sector),
  LINK (Oracle/TradFi bridge), MKR/AAVE (DeFi/finance), SNX (derivatives)
  NOTE: Actual tokenized stocks (NVDAX, TSLAx) are on Bitget Onchain platform,
        not available via main spot API. Using crypto proxies for stock exposure.

Market Hours Awareness:
- US Stock Market: 9:30 AM - 4:00 PM ET (Mon-Fri)
- During market hours: Stock-correlated assets have higher correlation
- Off hours: Lower liquidity for stock proxies, adjust allocation weights
"""

import asyncio
import json
import os
import structlog
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import numpy as np
import pytz  # For timezone handling

load_dotenv()
logger = structlog.get_logger(__name__)


class AssetCategory(Enum):
    CRYPTO = "crypto"
    GOLD = "gold"
    STOCKS = "stocks"
    USDT = "usdt"  # Unallocated capital


@dataclass
class AssetOpportunity:
    """Represents a trading opportunity in an asset"""
    symbol: str
    category: AssetCategory
    vsa_score: float  # 0-10
    opportunity_cost_score: float  # 0-10
    combined_score: float  # Weighted average
    expected_return: float
    volatility: float
    volume_24h: float
    current_price: float
    signal: str  # 'buy', 'hold', 'sell'
    reasoning: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class CategoryAllocation:
    """Allocation for a category"""
    category: AssetCategory
    target_allocation_pct: float  # 33.33%
    current_value_usd: float
    positions: Dict[str, float] = field(default_factory=dict)  # symbol -> value
    usdt_balance: float = 0.0


@dataclass
class PortfolioState:
    """Current portfolio state"""
    total_spot_capital: float
    category_allocations: Dict[str, CategoryAllocation] = field(default_factory=dict)
    last_rebalance: datetime = None
    last_margin_transfer: datetime = None
    total_transferred: float = 0.0


class DiversifiedSpotInvestmentService:
    """
    Main service for diversified spot investments
    Grok Architecture: MMM + CAE + COM + RMF
    """

    def __init__(self):
        self.exchange = None
        self.state_file = os.getenv('STATE_FILE', '/app/diversified_spot_state.json')

        # Margin Management Module (MMM) Config
        self.MARGIN_THRESHOLD = 400.0  # Excess margin threshold
        self.TRANSFER_INCREMENT = 15.0  # Transfer in $15 increments
        self.MARGIN_BUFFER = 0.10  # 10% buffer above maintenance

        # Capital Allocation Engine (CAE) Config
        self.CATEGORY_ALLOCATION = {
            AssetCategory.CRYPTO: 0.3333,
            AssetCategory.GOLD: 0.3333,
            AssetCategory.STOCKS: 0.3334,
        }

        # Category Optimization Module (COM) Config
        self.VSA_WEIGHT = 0.50  # VSA score weight
        self.OC_WEIGHT = 0.50   # Opportunity cost weight
        self.TOP_ASSETS_PER_CATEGORY = 5
        self.MIN_VOLUME_24H = 100000  # $100K minimum volume

        # Risk Management Framework (RMF) Config
        self.MAX_POSITION_PCT = 0.10  # Max 10% in single asset
        self.STOP_LOSS_CRYPTO = 0.05  # 5% stop-loss for crypto
        self.STOP_LOSS_GOLD = 0.03    # 3% stop-loss for gold
        self.STOP_LOSS_STOCKS = 0.03  # 3% stop-loss for stocks
        self.REBALANCE_THRESHOLD = 0.05  # 5% deviation triggers rebalance
        self.MAX_DRAWDOWN = 0.15  # 15% max drawdown
        self.CASH_BUFFER = 0.05  # 5% cash buffer

        # Asset universe by category - Expanded to 60+ crypto assets
        self.CRYPTO_UNIVERSE = [
            # Top 10 by Market Cap
            'BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'SOL/USDT', 'BNB/USDT',
            'DOGE/USDT', 'ADA/USDT', 'TRX/USDT', 'AVAX/USDT', 'LINK/USDT',
            # Top 11-25
            'TON/USDT', 'SHIB/USDT', 'DOT/USDT', 'XLM/USDT', 'HBAR/USDT',
            'BCH/USDT', 'UNI/USDT', 'LTC/USDT', 'PEPE/USDT', 'NEAR/USDT',
            'ATOM/USDT', 'ICP/USDT', 'APT/USDT', 'ETC/USDT', 'MATIC/USDT',
            # Top 26-40
            'FIL/USDT', 'IMX/USDT', 'STX/USDT', 'RENDER/USDT', 'ARB/USDT',
            'OP/USDT', 'INJ/USDT', 'VET/USDT', 'FTM/USDT', 'THETA/USDT',
            'ALGO/USDT', 'GRT/USDT', 'SAND/USDT', 'MANA/USDT', 'SEI/USDT',
            # Top 41-60 + DeFi/Gaming/AI
            'SUI/USDT', 'TIA/USDT', 'EGLD/USDT', 'AAVE/USDT', 'MKR/USDT',
            'RUNE/USDT', 'LDO/USDT', 'FET/USDT', 'AGIX/USDT', 'OCEAN/USDT',
            'AXS/USDT', 'GALA/USDT', 'ENJ/USDT', 'CHZ/USDT', 'FLOW/USDT',
            'KCS/USDT', 'CRV/USDT', 'SNX/USDT', 'COMP/USDT', '1INCH/USDT',
            # L2s and Infrastructure
            'STRK/USDT', 'ZK/USDT', 'BLUR/USDT', 'WLD/USDT', 'JUP/USDT',
            'PYTH/USDT', 'JTO/USDT', 'BONK/USDT', 'WIF/USDT', 'ORDI/USDT',
        ]

        # Gold/Silver/Precious Metals Universe - Available on Bitget Spot
        # XAUT and PAXG are the only tokenized gold available on spot API
        # NOTE: XAU/XAG are perpetual futures only, not spot
        self.GOLD_UNIVERSE = [
            'XAUT/USDT',       # Tether Gold (backed by 1:1 physical gold in Swiss vaults)
            'PAXG/USDT',       # Pax Gold (backed by 1:1 physical gold in London vaults)
        ]

        # Stock Exposure via Crypto Proxies (Spot Market)
        # NOTE: Tokenized stocks (NVDAX, TSLAx, AAPLx) are on Bitget Onchain/Wallet platform,
        #       NOT the main spot API. NVDA/USDT:USDT etc are perpetual futures, not spot.
        # Using high-correlation crypto proxies for stock market exposure:
        # - ONDO: RWA protocol (tokenizes real-world assets including stocks/bonds)
        # - RENDER: GPU compute (high correlation with NVIDIA/AI sector)
        # - FET: AI/compute (correlates with tech stocks)
        # - TAO: AI/ML network (correlates with AI sector)
        # - LINK: Oracle infrastructure (DeFi/TradFi bridge)
        # - MKR: DeFi governance (finance sector proxy)
        # - AAVE: DeFi lending (banking proxy)
        # - COIN: Coinbase stock (actual crypto-native stock proxy)
        self.STOCKS_UNIVERSE = [
            'ONDO/USDT',       # Ondo Finance - RWA protocol (primary stock exposure)
            'RENDER/USDT',     # GPU compute - NVIDIA/AI correlation
            'FET/USDT',        # AI/compute - tech sector proxy
            'TAO/USDT',        # AI/ML network - AI sector proxy
            'LINK/USDT',       # Oracle infrastructure - TradFi bridge
            'MKR/USDT',        # DeFi governance - finance sector proxy
            'AAVE/USDT',       # DeFi lending - banking proxy
            'SNX/USDT',        # Synthetic assets - derivatives proxy
            'PENDLE/USDT',     # Yield tokenization - finance proxy
            'AGIX/USDT',       # AI - SingularityNET (AI sector)
            'OCEAN/USDT',      # AI data marketplace (AI sector)
        ]

        # US Market hours configuration
        self.US_MARKET_TZ = pytz.timezone('America/New_York')
        self.MARKET_OPEN_HOUR = 9
        self.MARKET_OPEN_MINUTE = 30
        self.MARKET_CLOSE_HOUR = 16
        self.MARKET_CLOSE_MINUTE = 0

        # Portfolio state
        self.portfolio_state: Optional[PortfolioState] = None

        logger.info("DiversifiedSpotInvestmentService initialized")

    async def initialize(self):
        """Initialize exchange connection and load state"""
        try:
            self.exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_API_SECRET'),
                'password': os.getenv('BITGET_API_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'spot',  # SPOT for this service
                }
            })

            await self.exchange.load_markets()

            # Filter available assets
            await self._filter_available_assets()

            # Load or create portfolio state
            self._load_state()

            logger.info("Service initialized",
                       crypto_assets=len(self.CRYPTO_UNIVERSE),
                       gold_assets=len(self.GOLD_UNIVERSE),
                       stock_assets=len(self.STOCKS_UNIVERSE))

            return True

        except Exception as e:
            logger.error("Failed to initialize service", error=str(e))
            return False

    async def _filter_available_assets(self):
        """Filter asset universes to only include available symbols"""
        available_symbols = set(self.exchange.markets.keys())

        self.CRYPTO_UNIVERSE = [s for s in self.CRYPTO_UNIVERSE if s in available_symbols]
        self.GOLD_UNIVERSE = [s for s in self.GOLD_UNIVERSE if s in available_symbols]
        self.STOCKS_UNIVERSE = [s for s in self.STOCKS_UNIVERSE if s in available_symbols]

        logger.info("Filtered available assets",
                   crypto=len(self.CRYPTO_UNIVERSE),
                   gold=len(self.GOLD_UNIVERSE),
                   stocks=len(self.STOCKS_UNIVERSE))

    # =========================================================================
    # MARKET HOURS AWARENESS
    # =========================================================================

    def is_us_market_open(self) -> bool:
        """
        Check if US stock market is currently open.
        Market hours: 9:30 AM - 4:00 PM ET, Monday-Friday
        """
        try:
            current_time_et = datetime.now(self.US_MARKET_TZ)

            # Check if weekday (0=Monday, 4=Friday)
            if current_time_et.weekday() > 4:  # Saturday or Sunday
                return False

            # Check if within market hours
            market_open = current_time_et.replace(
                hour=self.MARKET_OPEN_HOUR,
                minute=self.MARKET_OPEN_MINUTE,
                second=0, microsecond=0
            )
            market_close = current_time_et.replace(
                hour=self.MARKET_CLOSE_HOUR,
                minute=self.MARKET_CLOSE_MINUTE,
                second=0, microsecond=0
            )

            return market_open <= current_time_et <= market_close

        except Exception as e:
            logger.warning("Market hours check failed", error=str(e))
            return False

    def get_market_status(self) -> Dict:
        """Get detailed US market status"""
        try:
            current_time_et = datetime.now(self.US_MARKET_TZ)
            is_open = self.is_us_market_open()

            # Calculate time to open/close
            market_open = current_time_et.replace(
                hour=self.MARKET_OPEN_HOUR,
                minute=self.MARKET_OPEN_MINUTE,
                second=0, microsecond=0
            )
            market_close = current_time_et.replace(
                hour=self.MARKET_CLOSE_HOUR,
                minute=self.MARKET_CLOSE_MINUTE,
                second=0, microsecond=0
            )

            if is_open:
                time_to_close = (market_close - current_time_et).total_seconds() / 3600
                status = "OPEN"
            else:
                # Calculate time to next open
                if current_time_et.weekday() >= 4:  # Friday after close or weekend
                    days_to_monday = (7 - current_time_et.weekday()) % 7
                    if days_to_monday == 0:
                        days_to_monday = 7
                    next_open = market_open + timedelta(days=days_to_monday)
                elif current_time_et < market_open:
                    next_open = market_open
                else:
                    next_open = market_open + timedelta(days=1)
                time_to_close = (next_open - current_time_et).total_seconds() / 3600
                status = "CLOSED"

            return {
                'status': status,
                'is_open': is_open,
                'current_time_et': current_time_et.strftime('%Y-%m-%d %H:%M:%S ET'),
                'weekday': current_time_et.strftime('%A'),
                'hours_to_next_event': round(time_to_close, 2),
                'note': 'Stock-correlated assets (ONDO, RENDER, etc.) have higher correlation during market hours'
            }

        except Exception as e:
            logger.warning("Market status check failed", error=str(e))
            return {'status': 'UNKNOWN', 'is_open': False, 'error': str(e)}

    # =========================================================================
    # MARGIN MANAGEMENT MODULE (MMM)
    # =========================================================================

    async def check_and_transfer_margin(self) -> Dict:
        """
        MMM: Check futures margin and transfer excess to spot
        Grok Algorithm: Transfer in $15 increments when excess > $400
        """
        try:
            # Get futures account balance
            futures_exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_API_SECRET'),
                'password': os.getenv('BITGET_API_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {'defaultType': 'swap'}
            })

            await futures_exchange.load_markets()
            futures_balance = await futures_exchange.fetch_balance()

            # Get available margin (free balance)
            usdt_free = futures_balance.get('USDT', {}).get('free', 0)
            usdt_total = futures_balance.get('USDT', {}).get('total', 0)

            logger.info("Futures balance check",
                       free=usdt_free, total=usdt_total)

            # Calculate excess margin
            excess_margin = usdt_free - self.MARGIN_THRESHOLD

            result = {
                'futures_free': usdt_free,
                'futures_total': usdt_total,
                'excess_margin': excess_margin,
                'transferred': 0,
                'transfers_made': 0
            }

            if excess_margin > self.TRANSFER_INCREMENT:
                # Calculate number of $15 increments
                num_transfers = int(excess_margin // self.TRANSFER_INCREMENT)
                transfer_amount = num_transfers * self.TRANSFER_INCREMENT

                if transfer_amount > 0:
                    # Execute transfer from futures to spot
                    try:
                        # Bitget internal transfer
                        transfer_result = await futures_exchange.transfer(
                            code='USDT',
                            amount=transfer_amount,
                            fromAccount='swap',  # From futures
                            toAccount='spot'     # To spot
                        )

                        result['transferred'] = transfer_amount
                        result['transfers_made'] = num_transfers
                        result['transfer_result'] = transfer_result

                        # Update state
                        if self.portfolio_state:
                            self.portfolio_state.total_transferred += transfer_amount
                            self.portfolio_state.last_margin_transfer = datetime.now()
                            self.portfolio_state.total_spot_capital += transfer_amount
                            self._save_state()

                        logger.info("Margin transferred to spot",
                                   amount=transfer_amount,
                                   increments=num_transfers)

                    except Exception as transfer_error:
                        logger.error("Transfer failed", error=str(transfer_error))
                        result['error'] = str(transfer_error)
            else:
                logger.info("No excess margin to transfer",
                           excess=excess_margin,
                           threshold=self.MARGIN_THRESHOLD)

            await futures_exchange.close()
            return result

        except Exception as e:
            logger.error("Margin check failed", error=str(e))
            return {'error': str(e)}

    # =========================================================================
    # VSA SCANNER (Volume Spread Analysis)
    # =========================================================================

    async def calculate_vsa_score(self, symbol: str) -> Tuple[float, Dict]:
        """
        Calculate VSA (Volume Spread Analysis) score for an asset
        Grok Algorithm: Volume spikes + price spread analysis
        """
        try:
            # Fetch OHLCV data
            ohlcv = await self.exchange.fetch_ohlcv(symbol, '1h', limit=50)

            if len(ohlcv) < 20:
                return 5.0, {'reason': 'Insufficient data'}

            # Extract data
            closes = np.array([c[4] for c in ohlcv])
            volumes = np.array([c[5] for c in ohlcv])
            highs = np.array([c[2] for c in ohlcv])
            lows = np.array([c[3] for c in ohlcv])

            # Calculate spreads (high - low)
            spreads = highs - lows

            # Recent vs average calculations
            recent_volume = np.mean(volumes[-5:])
            avg_volume = np.mean(volumes[:-5])
            recent_spread = np.mean(spreads[-5:])
            avg_spread = np.mean(spreads[:-5])

            # VSA indicators
            volume_spike = recent_volume > avg_volume * 1.5
            spread_narrow = recent_spread < avg_spread * 0.7
            spread_wide = recent_spread > avg_spread * 1.3

            # Price position relative to range
            current_price = closes[-1]
            recent_high = np.max(highs[-20:])
            recent_low = np.min(lows[-20:])
            price_position = (current_price - recent_low) / (recent_high - recent_low + 1e-8)

            # Near support/resistance
            near_support = price_position < 0.3
            near_resistance = price_position > 0.7

            # Calculate VSA score (0-10)
            score = 5.0  # Neutral baseline
            reasoning = {}

            # Accumulation pattern: Volume spike + narrow spread + near support
            if volume_spike and spread_narrow and near_support:
                score = 8.0
                reasoning['pattern'] = 'ACCUMULATION'
                reasoning['signal'] = 'Strong buy signal'

            # Distribution pattern: Volume spike + narrow spread + near resistance
            elif volume_spike and spread_narrow and near_resistance:
                score = 3.0
                reasoning['pattern'] = 'DISTRIBUTION'
                reasoning['signal'] = 'Potential sell signal'

            # Effort vs Result: High volume but little movement
            elif volume_spike and spread_narrow:
                score = 7.0
                reasoning['pattern'] = 'EFFORT_VS_RESULT'
                reasoning['signal'] = 'Potential reversal'

            # Breakout: Wide spread with volume
            elif volume_spike and spread_wide:
                score = 6.5 if price_position > 0.5 else 4.5
                reasoning['pattern'] = 'BREAKOUT'
                reasoning['signal'] = 'Trend continuation'

            # Low volume consolidation
            elif recent_volume < avg_volume * 0.5:
                score = 5.0
                reasoning['pattern'] = 'CONSOLIDATION'
                reasoning['signal'] = 'Wait for breakout'

            reasoning['volume_ratio'] = float(recent_volume / (avg_volume + 1e-8))
            reasoning['spread_ratio'] = float(recent_spread / (avg_spread + 1e-8))
            reasoning['price_position'] = float(price_position)

            return score, reasoning

        except Exception as e:
            logger.warning(f"VSA calculation failed for {symbol}", error=str(e))
            return 5.0, {'error': str(e)}

    async def check_multi_timeframe_confirmation(self, symbol: str) -> Tuple[bool, Dict]:
        """
        Check momentum confirmation across multiple timeframes
        Returns True if momentum is positive across all timeframes
        """
        try:
            timeframes = ['1d', '4h', '1h']
            confirmations = {}
            bullish_count = 0

            for tf in timeframes:
                ohlcv = await self.exchange.fetch_ohlcv(symbol, tf, limit=10)
                if len(ohlcv) < 5:
                    confirmations[tf] = 'insufficient_data'
                    continue

                closes = [c[4] for c in ohlcv]
                # Check if price is trending up (last close > 5-period SMA)
                sma_5 = sum(closes[-5:]) / 5
                current_price = closes[-1]
                is_bullish = current_price > sma_5

                # Also check momentum (current > previous)
                momentum = closes[-1] > closes[-2]

                confirmations[tf] = 'bullish' if (is_bullish and momentum) else 'bearish'
                if is_bullish and momentum:
                    bullish_count += 1

                await asyncio.sleep(0.05)  # Rate limiting

            # Require at least 2 out of 3 timeframes to be bullish
            confirmed = bullish_count >= 2

            return confirmed, {
                'confirmations': confirmations,
                'bullish_count': bullish_count,
                'total_timeframes': len(timeframes)
            }

        except Exception as e:
            logger.warning(f"MTF check failed for {symbol}", error=str(e))
            return False, {'error': str(e)}

    # =========================================================================
    # OPPORTUNITY COST ANALYSIS
    # =========================================================================

    async def calculate_opportunity_cost_score(self, symbol: str) -> Tuple[float, Dict]:
        """
        Calculate opportunity cost score for an asset
        Grok Algorithm: Expected return + volatility adjustment + liquidity
        """
        try:
            # Fetch ticker for 24h data
            ticker = await self.exchange.fetch_ticker(symbol)

            # Fetch OHLCV for calculations
            ohlcv = await self.exchange.fetch_ohlcv(symbol, '1d', limit=30)

            if len(ohlcv) < 7:
                return 5.0, {'reason': 'Insufficient data'}

            closes = np.array([c[4] for c in ohlcv])

            # Calculate metrics
            # Expected return (7-day momentum)
            returns_7d = (closes[-1] - closes[-7]) / closes[-7] if closes[-7] > 0 else 0

            # 30-day return
            returns_30d = (closes[-1] - closes[0]) / closes[0] if closes[0] > 0 else 0

            # Daily returns for volatility
            daily_returns = np.diff(closes) / closes[:-1]
            volatility = np.std(daily_returns) if len(daily_returns) > 0 else 0.05

            # Sharpe-like ratio (simplified)
            sharpe = returns_7d / (volatility + 0.01)

            # Liquidity score (based on 24h volume)
            volume_24h = ticker.get('quoteVolume', 0) or 0
            liquidity_score = min(10, volume_24h / 1e6)  # Normalized to millions

            # Grok formula: Expected Return * 0.6 + Volatility Adjustment * 0.3 + Liquidity * 0.1
            vol_adjustment = 1 / (volatility + 0.01)  # Lower volatility = higher score
            vol_adjustment_normalized = min(10, vol_adjustment / 10)

            # Normalize expected return to 0-10 scale
            return_normalized = min(10, max(0, (returns_7d + 0.1) * 50))  # -10% to +10% -> 0 to 10

            # Calculate final score
            score = (return_normalized * 0.6) + (vol_adjustment_normalized * 0.3) + (liquidity_score * 0.1)
            score = min(10, max(0, score))

            reasoning = {
                'expected_return_7d': float(returns_7d),
                'expected_return_30d': float(returns_30d),
                'volatility': float(volatility),
                'sharpe_ratio': float(sharpe),
                'volume_24h': float(volume_24h),
                'liquidity_score': float(liquidity_score),
                'return_normalized': float(return_normalized),
                'vol_adjustment_normalized': float(vol_adjustment_normalized)
            }

            return score, reasoning

        except Exception as e:
            logger.warning(f"Opportunity cost calculation failed for {symbol}", error=str(e))
            return 5.0, {'error': str(e)}

    # =========================================================================
    # MULTI-ASSET SCANNER
    # =========================================================================

    async def scan_category(self, category: AssetCategory) -> List[AssetOpportunity]:
        """
        Scan a category for opportunities
        Grok COM: Combine VSA + Opportunity Cost scores
        """
        if category == AssetCategory.CRYPTO:
            universe = self.CRYPTO_UNIVERSE
        elif category == AssetCategory.GOLD:
            universe = self.GOLD_UNIVERSE
        elif category == AssetCategory.STOCKS:
            universe = self.STOCKS_UNIVERSE
        else:
            return []

        opportunities = []

        for symbol in universe:
            try:
                # Calculate VSA score
                vsa_score, vsa_reasoning = await self.calculate_vsa_score(symbol)

                # Calculate opportunity cost score
                oc_score, oc_reasoning = await self.calculate_opportunity_cost_score(symbol)

                # Combined score (50-50 weight as per Grok)
                combined_score = (vsa_score * self.VSA_WEIGHT) + (oc_score * self.OC_WEIGHT)

                # Get momentum metrics for signal determination
                expected_return_7d = oc_reasoning.get('expected_return_7d', 0)
                expected_return_30d = oc_reasoning.get('expected_return_30d', 0)
                sharpe_ratio = oc_reasoning.get('sharpe_ratio', 0)

                # Determine signal with momentum-based entries + breakout detection + MTF confirmation
                signal = 'hold'  # Default
                buy_reason = None
                preliminary_buy = False

                # Get VSA pattern for breakout detection
                vsa_pattern = vsa_reasoning.get('pattern', '')
                is_breakout = vsa_pattern == 'BREAKOUT' and vsa_reasoning.get('price_position', 0) > 0.5
                is_accumulation = vsa_pattern == 'ACCUMULATION'

                # 1. Strong buy: High combined score (original logic)
                if combined_score >= 7:
                    preliminary_buy = True
                    buy_reason = 'strong_score'

                # 2. Momentum buy: Positive 7d return + decent score + good risk-adjusted return
                elif expected_return_7d > 0.02 and combined_score >= 5.0 and sharpe_ratio > 0.5:
                    preliminary_buy = True
                    buy_reason = f'momentum_7d:{expected_return_7d*100:.1f}%_sharpe:{sharpe_ratio:.2f}'

                # 3. Trend buy: Strong 30d trend + positive 7d momentum
                elif expected_return_30d > 0.05 and expected_return_7d > 0 and combined_score >= 4.5:
                    preliminary_buy = True
                    buy_reason = f'trend_30d:{expected_return_30d*100:.1f}%_7d:{expected_return_7d*100:.1f}%'

                # 4. Breakout buy: VSA breakout pattern + positive momentum
                elif is_breakout and expected_return_7d > 0 and combined_score >= 4.0:
                    preliminary_buy = True
                    buy_reason = f'breakout_volume:{vsa_reasoning.get("volume_ratio", 0):.1f}x'

                # 5. Accumulation buy: VSA accumulation pattern (strong buy signal)
                elif is_accumulation and combined_score >= 4.0:
                    preliminary_buy = True
                    buy_reason = 'accumulation_pattern'

                # 6. Sell signal
                elif combined_score <= 3:
                    signal = 'sell'

                # Multi-timeframe confirmation for buy signals
                mtf_info = {}
                if preliminary_buy:
                    mtf_confirmed, mtf_info = await self.check_multi_timeframe_confirmation(symbol)
                    if mtf_confirmed:
                        signal = 'buy'
                        buy_reason = f'{buy_reason}|MTF:{mtf_info.get("bullish_count", 0)}/3'
                    else:
                        logger.debug(f"MTF rejected: {symbol}", mtf=mtf_info)

                # Log buy signals with reason
                if signal == 'buy':
                    logger.info(f"Buy signal: {symbol}", reason=buy_reason,
                               combined=f"{combined_score:.1f}", ret_7d=f"{expected_return_7d*100:.1f}%",
                               pattern=vsa_pattern, mtf=mtf_info.get('confirmations', {}))

                # Get current price
                ticker = await self.exchange.fetch_ticker(symbol)

                opportunity = AssetOpportunity(
                    symbol=symbol,
                    category=category,
                    vsa_score=vsa_score,
                    opportunity_cost_score=oc_score,
                    combined_score=combined_score,
                    expected_return=oc_reasoning.get('expected_return_7d', 0),
                    volatility=oc_reasoning.get('volatility', 0),
                    volume_24h=oc_reasoning.get('volume_24h', 0),
                    current_price=ticker.get('last', 0),
                    signal=signal,
                    reasoning={
                        'vsa': vsa_reasoning,
                        'opportunity_cost': oc_reasoning
                    }
                )

                opportunities.append(opportunity)

                # Rate limiting
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.warning(f"Failed to scan {symbol}", error=str(e))
                continue

        # Sort by combined score (descending)
        opportunities.sort(key=lambda x: x.combined_score, reverse=True)

        logger.info(f"Scanned {category.value}",
                   total=len(opportunities),
                   buy_signals=len([o for o in opportunities if o.signal == 'buy']))

        return opportunities

    async def scan_all_categories(self) -> Dict[AssetCategory, List[AssetOpportunity]]:
        """Scan all asset categories for opportunities"""
        results = {}

        for category in [AssetCategory.CRYPTO, AssetCategory.GOLD, AssetCategory.STOCKS]:
            logger.info(f"Scanning {category.value}...")
            results[category] = await self.scan_category(category)

        return results

    # =========================================================================
    # CAPITAL ALLOCATION ENGINE (CAE)
    # =========================================================================

    async def get_spot_balance(self) -> Dict:
        """Get current spot account balance"""
        try:
            balance = await self.exchange.fetch_balance()

            usdt_balance = balance.get('USDT', {}).get('free', 0)
            total_value = usdt_balance

            # Get value of held positions
            positions = {}
            for symbol in (self.CRYPTO_UNIVERSE + self.GOLD_UNIVERSE + self.STOCKS_UNIVERSE):
                base = symbol.split('/')[0]
                asset_balance = balance.get(base, {}).get('free', 0)

                if asset_balance > 0:
                    try:
                        ticker = await self.exchange.fetch_ticker(symbol)
                        value = asset_balance * ticker.get('last', 0)
                        if value > 0.1:  # Ignore dust
                            positions[symbol] = {
                                'amount': asset_balance,
                                'value_usd': value
                            }
                            total_value += value
                    except:
                        continue

            return {
                'usdt_free': usdt_balance,
                'total_value': total_value,
                'positions': positions
            }

        except Exception as e:
            logger.error("Failed to get spot balance", error=str(e))
            return {'usdt_free': 0, 'total_value': 0, 'positions': {}}

    def allocate_capital_to_categories(self, total_capital: float) -> Dict[AssetCategory, float]:
        """
        CAE: Divide capital equally between categories
        Grok Formula: 33.33% each for Crypto/Gold/Stocks
        """
        # Reserve cash buffer
        investable = total_capital * (1 - self.CASH_BUFFER)

        allocations = {}
        for category, pct in self.CATEGORY_ALLOCATION.items():
            allocations[category] = investable * pct

        return allocations

    async def allocate_within_category(
        self,
        category: AssetCategory,
        category_capital: float,
        opportunities: List[AssetOpportunity]
    ) -> Dict[str, float]:
        """
        COM: Allocate capital within a category based on opportunities
        Grok Algorithm: Proportional to combined scores for top assets
        """
        if not opportunities or category_capital <= 0:
            return {}

        # Filter to buy signals only
        buy_opportunities = [o for o in opportunities if o.signal == 'buy']

        if not buy_opportunities:
            # If no buy signals, hold in USDT
            logger.info(f"No buy signals in {category.value}, holding USDT")
            return {}

        # Take top N assets
        top_opportunities = buy_opportunities[:self.TOP_ASSETS_PER_CATEGORY]

        # Calculate total score
        total_score = sum(o.combined_score for o in top_opportunities)

        if total_score <= 0:
            return {}

        # Allocate proportionally
        allocations = {}
        for opp in top_opportunities:
            allocation_pct = opp.combined_score / total_score
            allocation_usd = category_capital * allocation_pct

            # Apply max position limit
            max_allocation = category_capital * self.MAX_POSITION_PCT * 3  # Per category limit
            allocation_usd = min(allocation_usd, max_allocation)

            if allocation_usd > 1.0:  # Minimum $1 allocation
                allocations[opp.symbol] = allocation_usd

        return allocations

    # =========================================================================
    # EXECUTION ENGINE
    # =========================================================================

    async def execute_allocation(
        self,
        target_allocations: Dict[str, float],
        current_positions: Dict
    ) -> Dict:
        """Execute buy/sell orders to reach target allocation"""
        results = {
            'buys': [],
            'sells': [],
            'errors': []
        }

        for symbol, target_value in target_allocations.items():
            try:
                current_value = current_positions.get(symbol, {}).get('value_usd', 0)
                diff = target_value - current_value

                ticker = await self.exchange.fetch_ticker(symbol)
                current_price = ticker.get('last', 0)

                if current_price <= 0:
                    continue

                if diff > 1.0:  # Buy $1+ worth
                    # For Bitget spot market buy, use limit order with current price
                    cost = diff  # Amount in USDT to spend
                    amount = cost / current_price  # Calculate amount to buy

                    # Check minimum order amount
                    market = self.exchange.markets.get(symbol, {})
                    min_amount = market.get('limits', {}).get('amount', {}).get('min', 0.0001)

                    if amount >= min_amount:
                        # Use limit order at market price (more reliable than market order on Bitget spot)
                        ticker = await self.exchange.fetch_ticker(symbol)
                        buy_price = ticker.get('ask') or ticker.get('last') or current_price
                        buy_price = buy_price * 1.001  # Slightly above ask

                        order = await self.exchange.create_limit_buy_order(
                            symbol, amount, buy_price
                        )
                        bought_amount = order.get('filled') or order.get('amount') or amount
                        results['buys'].append({
                            'symbol': symbol,
                            'amount': float(bought_amount) if bought_amount else amount,
                            'value': diff,
                            'order_id': order.get('id')
                        })
                        logger.info(f"Bought {float(bought_amount or amount):.4f} {symbol} for ${diff:.2f}")

                elif diff < -1.0:  # Sell $1+ worth
                    amount = abs(diff) / current_price
                    current_amount = current_positions.get(symbol, {}).get('amount', 0)
                    amount = min(amount, current_amount)  # Can't sell more than we have

                    if amount > 0:
                        order = await self.exchange.create_market_sell_order(symbol, amount)
                        results['sells'].append({
                            'symbol': symbol,
                            'amount': amount,
                            'value': abs(diff),
                            'order_id': order.get('id')
                        })
                        logger.info(f"Sold {amount} {symbol} for ${abs(diff):.2f}")

                await asyncio.sleep(0.2)  # Rate limiting

            except Exception as e:
                results['errors'].append({
                    'symbol': symbol,
                    'error': str(e)
                })
                logger.error(f"Order execution failed for {symbol}", error=str(e))

        return results

    # =========================================================================
    # REBALANCING
    # =========================================================================

    async def check_rebalance_needed(self) -> Tuple[bool, Dict]:
        """Check if portfolio rebalancing is needed"""
        balance = await self.get_spot_balance()
        total_value = balance['total_value']

        if total_value <= 0:
            return False, {'reason': 'No capital'}

        # Calculate current category allocations
        current_allocations = {
            AssetCategory.CRYPTO: 0,
            AssetCategory.GOLD: 0,
            AssetCategory.STOCKS: 0,
        }

        for symbol, pos_data in balance['positions'].items():
            value = pos_data['value_usd']

            if symbol in self.CRYPTO_UNIVERSE:
                current_allocations[AssetCategory.CRYPTO] += value
            elif symbol in self.GOLD_UNIVERSE:
                current_allocations[AssetCategory.GOLD] += value
            elif symbol in self.STOCKS_UNIVERSE:
                current_allocations[AssetCategory.STOCKS] += value

        # Calculate deviations
        deviations = {}
        max_deviation = 0

        for category, target_pct in self.CATEGORY_ALLOCATION.items():
            current_pct = current_allocations[category] / total_value if total_value > 0 else 0
            deviation = abs(current_pct - target_pct)
            deviations[category.value] = {
                'target': target_pct,
                'current': current_pct,
                'deviation': deviation
            }
            max_deviation = max(max_deviation, deviation)

        needs_rebalance = max_deviation > self.REBALANCE_THRESHOLD

        return needs_rebalance, {
            'max_deviation': max_deviation,
            'threshold': self.REBALANCE_THRESHOLD,
            'deviations': deviations
        }

    # =========================================================================
    # MAIN LOOP
    # =========================================================================

    async def run_cycle(self) -> Dict:
        """Run one investment cycle"""
        cycle_result = {
            'timestamp': datetime.now().isoformat(),
            'margin_transfer': None,
            'scan_results': None,
            'allocations': None,
            'execution': None,
            'rebalance': None
        }

        try:
            # Step 1: Check and transfer margin
            logger.info("Step 1: Checking margin transfer...")
            cycle_result['margin_transfer'] = await self.check_and_transfer_margin()

            # Step 2: Get spot balance
            logger.info("Step 2: Getting spot balance...")
            balance = await self.get_spot_balance()
            total_capital = balance['total_value']

            if total_capital < 10:  # Minimum $10 to operate
                logger.info("Insufficient capital", capital=total_capital)
                cycle_result['skip_reason'] = 'Insufficient capital'
                return cycle_result

            # Step 3: Scan all categories
            logger.info("Step 3: Scanning markets...")
            scan_results = await self.scan_all_categories()
            cycle_result['scan_results'] = {
                cat.value: len(opps) for cat, opps in scan_results.items()
            }

            # Step 4: Calculate category allocations
            logger.info("Step 4: Calculating allocations...")
            category_allocations = self.allocate_capital_to_categories(total_capital)

            # Step 5: Allocate within each category
            all_allocations = {}
            for category, opportunities in scan_results.items():
                category_capital = category_allocations.get(category, 0)
                within_allocations = await self.allocate_within_category(
                    category, category_capital, opportunities
                )
                all_allocations.update(within_allocations)

            cycle_result['allocations'] = all_allocations

            # Step 6: Execute allocations
            logger.info("Step 5: Executing allocations...")
            cycle_result['execution'] = await self.execute_allocation(
                all_allocations,
                balance['positions']
            )

            # Step 7: Check rebalancing
            needs_rebalance, rebalance_info = await self.check_rebalance_needed()
            cycle_result['rebalance'] = {
                'needed': needs_rebalance,
                'info': rebalance_info
            }

            # Save state
            self._save_state()

            logger.info("Cycle completed successfully")

        except Exception as e:
            logger.error("Cycle failed", error=str(e))
            cycle_result['error'] = str(e)

        return cycle_result

    async def run_continuous(self, interval_hours: int = 4):
        """Run continuous investment cycles"""
        logger.info(f"Starting continuous operation, interval: {interval_hours}h")

        while True:
            try:
                result = await self.run_cycle()
                logger.info("Cycle result",
                           transferred=result.get('margin_transfer', {}).get('transferred', 0))

                # Wait for next cycle
                await asyncio.sleep(interval_hours * 3600)

            except Exception as e:
                logger.error("Continuous run error", error=str(e))
                await asyncio.sleep(300)  # Wait 5 min on error

    # =========================================================================
    # STATE MANAGEMENT
    # =========================================================================

    def _load_state(self):
        """Load portfolio state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.portfolio_state = PortfolioState(
                        total_spot_capital=data.get('total_spot_capital', 0),
                        total_transferred=data.get('total_transferred', 0)
                    )
            else:
                self.portfolio_state = PortfolioState(total_spot_capital=0)
        except Exception as e:
            logger.error("Failed to load state", error=str(e))
            self.portfolio_state = PortfolioState(total_spot_capital=0)

    def _save_state(self):
        """Save portfolio state to file"""
        try:
            data = {
                'total_spot_capital': self.portfolio_state.total_spot_capital,
                'total_transferred': self.portfolio_state.total_transferred,
                'last_margin_transfer': self.portfolio_state.last_margin_transfer.isoformat()
                    if self.portfolio_state.last_margin_transfer else None,
                'last_rebalance': self.portfolio_state.last_rebalance.isoformat()
                    if self.portfolio_state.last_rebalance else None,
                'updated_at': datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)

        except Exception as e:
            logger.error("Failed to save state", error=str(e))

    async def close(self):
        """Close exchange connection"""
        if self.exchange:
            await self.exchange.close()


# =========================================================================
# CLI INTERFACE
# =========================================================================

async def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Diversified Spot Investment Service')
    parser.add_argument('--scan', action='store_true', help='Run market scan only')
    parser.add_argument('--cycle', action='store_true', help='Run one investment cycle')
    parser.add_argument('--continuous', action='store_true', help='Run continuously')
    parser.add_argument('--interval', type=int, default=4, help='Cycle interval in hours')
    parser.add_argument('--check-margin', action='store_true', help='Check and transfer margin only')

    args = parser.parse_args()

    service = DiversifiedSpotInvestmentService()

    if not await service.initialize():
        print("Failed to initialize service")
        return

    try:
        if args.check_margin:
            result = await service.check_and_transfer_margin()
            print(json.dumps(result, indent=2, default=str))

        elif args.scan:
            print("\n" + "="*70)
            print("MULTI-ASSET MARKET SCAN")
            print("="*70)

            # Show market status
            market_status = service.get_market_status()
            print(f"\nUS Market Status: {market_status['status']}")
            print(f"Current Time: {market_status.get('current_time_et', 'N/A')} ({market_status.get('weekday', 'N/A')})")
            if market_status['is_open']:
                print(f"Hours to close: {market_status.get('hours_to_next_event', 'N/A')}")
            else:
                print(f"Hours to open: {market_status.get('hours_to_next_event', 'N/A')}")
            print(f"Note: {market_status.get('note', '')}")
            print("-" * 70)

            results = await service.scan_all_categories()

            for category, opportunities in results.items():
                category_note = ""
                if category == AssetCategory.STOCKS:
                    category_note = " (RWA/Stock Proxies)"
                print(f"\n{category.value.upper()}{category_note} ({len(opportunities)} assets):")
                print("-" * 50)

                for opp in opportunities[:5]:
                    signal_emoji = {'buy': '', 'sell': '', 'hold': ''}
                    print(f"  {signal_emoji[opp.signal]} {opp.symbol}")
                    print(f"     VSA: {opp.vsa_score:.1f} | OC: {opp.opportunity_cost_score:.1f} | Combined: {opp.combined_score:.1f}")
                    print(f"     Signal: {opp.signal.upper()} | Return: {opp.expected_return*100:.2f}%")

        elif args.cycle:
            result = await service.run_cycle()
            print(json.dumps(result, indent=2, default=str))

        elif args.continuous:
            await service.run_continuous(interval_hours=args.interval)

        else:
            # Default: show status
            balance = await service.get_spot_balance()
            print("\n" + "="*70)
            print("DIVERSIFIED SPOT INVESTMENT SERVICE STATUS")
            print("="*70)
            print(f"USDT Free: ${balance['usdt_free']:.2f}")
            print(f"Total Value: ${balance['total_value']:.2f}")
            print(f"\nPositions:")
            for symbol, pos in balance['positions'].items():
                print(f"  {symbol}: {pos['amount']:.4f} (${pos['value_usd']:.2f})")

    finally:
        await service.close()


if __name__ == "__main__":
    asyncio.run(main())
