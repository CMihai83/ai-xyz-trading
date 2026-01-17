#!/usr/bin/env python3
"""
AI-XYZ Quick Scalper V3.2.0 - Hybrid 1-Minute + Order Book + Averaging
=======================================================================

High-frequency scalping with 1-minute candles + order book confirmation.
Designed by Claude (Opus 4.5) + Grok Consortium.

V3.2.0: Added micro-averaging based on backtest results (+29% PnL, +6.2% WR)
V3.1.0: Integrated with Unified Order Router for cross-system coordination.

ARCHITECTURE:
- 1-minute candles for RSI signals
- Real-time order book for imbalance confirmation
- Combined scoring: RSI (40%) + OrderBook (40%) + Volume (10%) + Momentum (10%)
- Micro TP/SL: 0.15% / 0.08%
- MICRO-AVERAGING: At -0.05% UPNL, average with [0.5, 1.0, 1.5] multipliers
- UNIFIED ORDER ROUTER: Prevents conflicts with main trading system

SIGNAL FLOW:
1. RSI reaches extreme (<25 or >75 on 1m)
2. Order book imbalance confirms direction (>20% imbalance)
3. Check for conflicts with other systems via Order Router
4. Combined score > 70 triggers entry
5. Manage position: averaging at -0.05%, exit on TP/SL or max hold

BACKTEST RESULTS (384 trades):
- Win Rate: 57% vs 51% (no averaging)
- Total PnL: +$15.66 vs +$12.16 (+29%)
- SL Exits: 84 vs 123 (32% fewer stops)

DATE: January 17, 2026
"""

import ccxt
import time
import json
import os
import redis
import requests
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from dataclasses import dataclass, field

load_dotenv()

# Import Unified Order Router
try:
    from unified_order_router import (
        submit_order, get_position, get_all_positions,
        can_open_position, OrderResponse, SystemType
    )
    ORDER_ROUTER_AVAILABLE = True
    print("  ✓ Unified Order Router loaded")
except ImportError:
    ORDER_ROUTER_AVAILABLE = False
    print("  ⚠ Order Router not available - running standalone")


# ========== CONFIGURATION ==========

@dataclass
class HybridScalperConfig:
    """Configuration for V3.0.0 Hybrid Scalper"""

    # ===== TIMEFRAME =====
    TIMEFRAME: str = '1m'
    CANDLE_SECONDS: int = 60

    # ===== RSI PARAMETERS (tighter for 1m) =====
    RSI_PERIOD: int = 14
    RSI_OVERSOLD: float = 25.0      # More extreme for 1m noise
    RSI_OVERBOUGHT: float = 75.0

    # ===== ORDER BOOK PARAMETERS =====
    OB_DEPTH_LEVELS: int = 20       # Top 20 bid/ask levels
    OB_IMBALANCE_LONG: float = 0.20   # 20% more bids = bullish
    OB_IMBALANCE_SHORT: float = -0.20 # 20% more asks = bearish
    OB_REFRESH_SECONDS: int = 5     # Refresh orderbook every 5s

    # ===== MICRO TP/SL =====
    TAKE_PROFIT_PCT: float = 0.15   # 0.15% TP
    STOP_LOSS_PCT: float = 0.08     # 0.08% SL
    MAX_HOLD_SECONDS: int = 300     # 5 minutes max hold

    # ===== SCORING WEIGHTS =====
    WEIGHT_RSI: float = 0.40
    WEIGHT_ORDERBOOK: float = 0.40
    WEIGHT_VOLUME: float = 0.10
    WEIGHT_MOMENTUM: float = 0.10
    MIN_SCORE: float = 70.0

    # ===== POSITION MANAGEMENT =====
    POSITION_SIZE_USD: float = 20.0  # $20 per position
    MAX_POSITIONS: int = 6
    LEVERAGE: int = 10
    COOLDOWN_SECONDS: int = 60       # 1 minute cooldown

    # ===== MICRO-AVERAGING (V3.2.0) =====
    # Based on backtest: averaging converts 32% fewer SL exits
    AVG_ENABLED: bool = True
    AVG_THRESHOLD_PCT: float = -0.05   # Average at -0.05% UPNL
    AVG_MULTIPLIERS: List[float] = field(default_factory=lambda: [0.5, 1.0, 1.5])  # Small scalp multipliers
    AVG_MAX_STEPS: int = 3             # Max 3 averaging steps
    AVG_COOLDOWN_SECONDS: int = 30     # Min 30s between averaging steps

    # ===== SCAN SETTINGS =====
    SCAN_INTERVAL_SECONDS: int = 10  # Check every 10 seconds
    SYMBOL_REFRESH_MINUTES: int = 5

    # ===== SYMBOL SOURCES =====
    MIN_VOLATILITY: float = 60.0     # Lower threshold for 1m
    MAX_VOLATILITY: float = 400.0
    MIN_VOLUME_USD: float = 10_000_000  # $10M daily

    PREDICTION_API_URL: str = "http://prediction_service:8009"
    MIN_PREDICTION_CONFIDENCE: float = 65.0

    # Fallback symbols (high liquidity, good for scalping)
    FALLBACK_SYMBOLS: List[str] = field(default_factory=lambda: [
        'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT',
        'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'PEPE/USDT:USDT'
    ])


@dataclass
class OrderBookSnapshot:
    """Real-time order book data"""
    symbol: str
    timestamp: datetime
    bid_volume: float
    ask_volume: float
    imbalance: float  # -1 to +1 (negative = bearish, positive = bullish)
    best_bid: float
    best_ask: float
    spread_pct: float


@dataclass
class HybridSignal:
    """Combined signal from RSI + OrderBook"""
    symbol: str
    direction: str  # 'long' or 'short'
    score: float
    rsi: float
    rsi_score: float
    ob_imbalance: float
    ob_score: float
    volume_score: float
    momentum_score: float
    price: float
    tp_price: float
    sl_price: float


@dataclass
class ScalperPosition:
    """Active position tracking with averaging support (V3.2.0)"""
    symbol: str
    side: str
    entry_price: float
    size: float
    entry_time: datetime
    score: float
    tp_price: float
    sl_price: float
    # V3.2.0: Averaging tracking
    avg_entry_price: float = 0.0       # Weighted average entry
    original_size: float = 0.0         # Size before averaging
    averaging_steps: int = 0           # Steps taken
    last_avg_time: Optional[datetime] = None  # Last averaging time

    def __post_init__(self):
        """Initialize averaging fields if not set"""
        if self.avg_entry_price == 0.0:
            self.avg_entry_price = self.entry_price
        if self.original_size == 0.0:
            self.original_size = self.size

    def check_exit(self, current_price: float, config: HybridScalperConfig) -> Tuple[bool, str]:
        """Check if position should exit (V3.2.0: uses avg_entry for TP/SL after averaging)"""
        # Time-based exit
        hold_time = (datetime.now() - self.entry_time).total_seconds()
        if hold_time >= config.MAX_HOLD_SECONDS:
            return True, "MAX_HOLD"

        # V3.2.0: Use dynamic TP/SL based on average entry price
        # After averaging, TP/SL are recalculated from avg_entry_price
        if self.side == 'long':
            if current_price >= self.tp_price:
                return True, "TAKE_PROFIT"
            if current_price <= self.sl_price:
                return True, "STOP_LOSS"
        else:
            if current_price <= self.tp_price:
                return True, "TAKE_PROFIT"
            if current_price >= self.sl_price:
                return True, "STOP_LOSS"

        return False, ""

    def calculate_upnl_pct(self, current_price: float) -> float:
        """Calculate unrealized PnL percentage based on average entry"""
        if self.side == 'long':
            return (current_price - self.avg_entry_price) / self.avg_entry_price * 100
        else:
            return (self.avg_entry_price - current_price) / self.avg_entry_price * 100

    def can_average(self, current_price: float, config: HybridScalperConfig) -> bool:
        """Check if position can be averaged (V3.2.0)"""
        if not config.AVG_ENABLED:
            return False
        if self.averaging_steps >= config.AVG_MAX_STEPS:
            return False

        # Check cooldown
        if self.last_avg_time:
            elapsed = (datetime.now() - self.last_avg_time).total_seconds()
            if elapsed < config.AVG_COOLDOWN_SECONDS:
                return False

        # Check UPNL threshold
        upnl_pct = self.calculate_upnl_pct(current_price)
        return upnl_pct <= config.AVG_THRESHOLD_PCT


# ========== MAIN SCALPER CLASS ==========

class HybridScalper:
    """V3.0.0 Hybrid 1-Minute + Order Book Scalper"""

    def __init__(self):
        self.config = HybridScalperConfig()

        # Exchange setup
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {'defaultType': 'swap'}
        })

        # Redis connection
        try:
            self.redis = redis.Redis(
                host=os.getenv('REDIS_HOST', 'redis'),
                port=int(os.getenv('REDIS_PORT', 6379)),
                decode_responses=True
            )
            self.redis.ping()
        except:
            self.redis = None

        # State
        self.positions: Dict[str, ScalperPosition] = {}
        self.last_trade_time: Dict[str, datetime] = {}
        self.order_books: Dict[str, OrderBookSnapshot] = {}
        self.symbols_to_scan: List[str] = []
        self.last_symbol_refresh = datetime.min

        # Stats (V3.2.0: added averaging stats)
        self.stats = {
            'wins': 0, 'losses': 0, 'total_pnl': 0.0,
            'tp_exits': 0, 'sl_exits': 0, 'time_exits': 0,
            'avg_steps_total': 0, 'avg_trades': 0  # V3.2.0
        }

        # Load state
        self._load_state()

        print("=" * 65)
        print("Quick Scalper V3.2.0 - Hybrid 1m + OrderBook + Averaging")
        print("Designed by Claude (Opus 4.5) + Grok")
        print("=" * 65)
        print(f"  Timeframe: {self.config.TIMEFRAME}")
        print(f"  RSI: <{self.config.RSI_OVERSOLD} LONG, >{self.config.RSI_OVERBOUGHT} SHORT")
        print(f"  OrderBook Imbalance: >{self.config.OB_IMBALANCE_LONG*100:.0f}% confirmation")
        print(f"  TP/SL: {self.config.TAKE_PROFIT_PCT}% / {self.config.STOP_LOSS_PCT}%")
        print(f"  Max Hold: {self.config.MAX_HOLD_SECONDS}s")
        if self.config.AVG_ENABLED:
            print(f"  [V3.2.0] Averaging: ON at {self.config.AVG_THRESHOLD_PCT}% UPNL")
            print(f"           Multipliers: {self.config.AVG_MULTIPLIERS} (max {self.config.AVG_MAX_STEPS} steps)")
        else:
            print(f"  [V3.2.0] Averaging: OFF")
        print(f"  Scan Interval: {self.config.SCAN_INTERVAL_SECONDS}s")
        print(f"  Min Score: {self.config.MIN_SCORE}")
        print("=" * 65)

    # ========== STATE MANAGEMENT ==========

    def _load_state(self):
        """Load state from Redis or file"""
        try:
            if self.redis:
                state = self.redis.get('quick_scalper_v3:state')
                if state:
                    data = json.loads(state)
                    self.stats = data.get('stats', self.stats)
                    print(f"  Loaded state from Redis")
                    return

            # Fallback to file
            if os.path.exists('/app/quick_scalper_v3_state.json'):
                with open('/app/quick_scalper_v3_state.json', 'r') as f:
                    data = json.load(f)
                    self.stats = data.get('stats', self.stats)
                    print(f"  Loaded state from file")
        except Exception as e:
            print(f"  State load error: {e}")

    def _save_state(self):
        """Save state to Redis and file (V3.2.0: includes averaging fields)"""
        try:
            data = {
                'stats': self.stats,
                'positions': {k: {
                    'symbol': v.symbol, 'side': v.side,
                    'entry_price': v.entry_price, 'size': v.size,
                    'entry_time': v.entry_time.isoformat(),
                    'tp_price': v.tp_price, 'sl_price': v.sl_price,
                    # V3.2.0: Averaging fields
                    'avg_entry_price': v.avg_entry_price,
                    'original_size': v.original_size,
                    'averaging_steps': v.averaging_steps,
                    'last_avg_time': v.last_avg_time.isoformat() if v.last_avg_time else None
                } for k, v in self.positions.items()},
                'last_update': datetime.now().isoformat()
            }

            if self.redis:
                self.redis.set('quick_scalper_v3:state', json.dumps(data))

            with open('/app/quick_scalper_v3_state.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"  State save error: {e}")

    # ========== SYMBOL MANAGEMENT ==========

    def refresh_symbols(self):
        """Refresh symbol list from multiple sources"""
        elapsed = (datetime.now() - self.last_symbol_refresh).total_seconds()
        if elapsed < self.config.SYMBOL_REFRESH_MINUTES * 60 and self.symbols_to_scan:
            return

        symbols = set()

        # Source 1: Volatile symbols scan
        try:
            print("\n[SYMBOL SCAN] Scanning for volatile symbols...")
            markets = self.exchange.load_markets()
            futures = [s for s in markets if s.endswith('/USDT:USDT') and markets[s].get('swap')]

            for symbol in futures[:50]:  # Check top 50 by volume
                try:
                    ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=24)
                    if len(ohlcv) < 24:
                        continue

                    df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
                    returns = df['c'].pct_change().dropna()
                    volatility = returns.std() * np.sqrt(24 * 365) * 100
                    volume = df['v'].mean() * df['c'].iloc[-1]

                    if (self.config.MIN_VOLATILITY <= volatility <= self.config.MAX_VOLATILITY and
                        volume >= self.config.MIN_VOLUME_USD):
                        symbols.add(symbol)
                except:
                    continue

            print(f"  Found {len(symbols)} volatile symbols")
        except Exception as e:
            print(f"  Volatility scan error: {e}")

        # Source 2: Prediction API
        try:
            url = f"{self.config.PREDICTION_API_URL}/market/overview"
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for s in data.get('top_bullish', [])[:5]:
                    if s.get('confidence', 0) >= self.config.MIN_PREDICTION_CONFIDENCE:
                        symbols.add(s.get('symbol', ''))
                for s in data.get('top_bearish', [])[:5]:
                    if s.get('confidence', 0) >= self.config.MIN_PREDICTION_CONFIDENCE:
                        symbols.add(s.get('symbol', ''))
                print(f"  Added predictions: {len(data.get('top_bullish', []))} long, {len(data.get('top_bearish', []))} short")
        except Exception as e:
            print(f"  Prediction API error: {e}")

        # Fallback
        if len(symbols) < 3:
            symbols.update(self.config.FALLBACK_SYMBOLS)
            print(f"  Using fallback symbols")

        symbols.discard('')
        self.symbols_to_scan = list(symbols)[:15]  # Max 15 symbols
        self.last_symbol_refresh = datetime.now()

        syms = [s.replace('/USDT:USDT', '') for s in self.symbols_to_scan[:8]]
        print(f"  Scanning: {syms}{'...' if len(self.symbols_to_scan) > 8 else ''}")

    # ========== ORDER BOOK ANALYSIS ==========

    def fetch_order_book(self, symbol: str) -> Optional[OrderBookSnapshot]:
        """Fetch and analyze order book"""
        try:
            ob = self.exchange.fetch_order_book(symbol, limit=self.config.OB_DEPTH_LEVELS)

            # Calculate volumes
            bid_volume = sum(bid[1] for bid in ob['bids'][:self.config.OB_DEPTH_LEVELS])
            ask_volume = sum(ask[1] for ask in ob['asks'][:self.config.OB_DEPTH_LEVELS])
            total_volume = bid_volume + ask_volume

            # Imbalance: -1 (all asks) to +1 (all bids)
            imbalance = (bid_volume - ask_volume) / total_volume if total_volume > 0 else 0

            # Spread
            best_bid = ob['bids'][0][0] if ob['bids'] else 0
            best_ask = ob['asks'][0][0] if ob['asks'] else 0
            spread_pct = (best_ask - best_bid) / best_bid * 100 if best_bid > 0 else 0

            snapshot = OrderBookSnapshot(
                symbol=symbol,
                timestamp=datetime.now(),
                bid_volume=bid_volume,
                ask_volume=ask_volume,
                imbalance=imbalance,
                best_bid=best_bid,
                best_ask=best_ask,
                spread_pct=spread_pct
            )

            self.order_books[symbol] = snapshot
            return snapshot

        except Exception as e:
            return None

    # ========== SIGNAL GENERATION ==========

    def calculate_signal(self, symbol: str) -> Optional[HybridSignal]:
        """Calculate hybrid RSI + OrderBook signal"""
        try:
            # Fetch 1-minute candles
            ohlcv = self.exchange.fetch_ohlcv(symbol, self.config.TIMEFRAME, limit=50)
            df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

            price = df['c'].iloc[-1]

            # ===== RSI Calculation =====
            delta = df['c'].diff()
            gain = delta.where(delta > 0, 0).rolling(self.config.RSI_PERIOD).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(self.config.RSI_PERIOD).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]

            # ===== Order Book =====
            ob = self.fetch_order_book(symbol)
            if not ob:
                return None

            # ===== Determine Direction =====
            direction = None

            # RSI signal
            rsi_long = rsi < self.config.RSI_OVERSOLD
            rsi_short = rsi > self.config.RSI_OVERBOUGHT

            # OrderBook confirmation
            ob_long = ob.imbalance > self.config.OB_IMBALANCE_LONG
            ob_short = ob.imbalance < self.config.OB_IMBALANCE_SHORT

            # Need BOTH RSI and OrderBook to agree
            if rsi_long and ob_long:
                direction = 'long'
            elif rsi_short and ob_short:
                direction = 'short'
            else:
                return None  # No confirmed signal

            # ===== Calculate Component Scores =====

            # RSI Score (0-100)
            if direction == 'long':
                rsi_score = min(100, (self.config.RSI_OVERSOLD - rsi) / self.config.RSI_OVERSOLD * 150)
            else:
                rsi_score = min(100, (rsi - self.config.RSI_OVERBOUGHT) / (100 - self.config.RSI_OVERBOUGHT) * 150)

            # OrderBook Score (0-100)
            ob_score = min(100, abs(ob.imbalance) / 0.5 * 100)  # Max at 50% imbalance

            # Volume Score (current vs average)
            vol_avg = df['v'].rolling(10).mean().iloc[-1]
            vol_current = df['v'].iloc[-1]
            vol_spike = vol_current / vol_avg if vol_avg > 0 else 1
            vol_score = min(100, vol_spike / 2 * 100)  # Max at 2x average

            # Momentum Score
            sma3 = df['c'].rolling(3).mean().iloc[-1]
            sma7 = df['c'].rolling(7).mean().iloc[-1]
            if direction == 'long':
                mom_score = 100 if price < sma3 < sma7 else 50  # Oversold momentum
            else:
                mom_score = 100 if price > sma3 > sma7 else 50  # Overbought momentum

            # ===== Combined Score =====
            score = (
                self.config.WEIGHT_RSI * rsi_score +
                self.config.WEIGHT_ORDERBOOK * ob_score +
                self.config.WEIGHT_VOLUME * vol_score +
                self.config.WEIGHT_MOMENTUM * mom_score
            )

            # ===== Calculate TP/SL =====
            if direction == 'long':
                tp_price = price * (1 + self.config.TAKE_PROFIT_PCT / 100)
                sl_price = price * (1 - self.config.STOP_LOSS_PCT / 100)
            else:
                tp_price = price * (1 - self.config.TAKE_PROFIT_PCT / 100)
                sl_price = price * (1 + self.config.STOP_LOSS_PCT / 100)

            return HybridSignal(
                symbol=symbol,
                direction=direction,
                score=score,
                rsi=rsi,
                rsi_score=rsi_score,
                ob_imbalance=ob.imbalance,
                ob_score=ob_score,
                volume_score=vol_score,
                momentum_score=mom_score,
                price=price,
                tp_price=tp_price,
                sl_price=sl_price
            )

        except Exception as e:
            return None

    # ========== POSITION MANAGEMENT ==========

    def open_position(self, signal: HybridSignal) -> bool:
        """Open a new position via Unified Order Router"""
        try:
            symbol = signal.symbol
            sym = symbol.replace('/USDT:USDT', '')

            # ===== USE ORDER ROUTER IF AVAILABLE =====
            if ORDER_ROUTER_AVAILABLE:
                # Check for conflicts first
                can_open, conflict_msg = can_open_position(
                    system="quick_scalper",
                    symbol=symbol,
                    side=signal.direction
                )

                if not can_open:
                    print(f"  ⚠️ CONFLICT: {sym} - {conflict_msg}")
                    return False

                # Submit order via router
                response = submit_order(
                    system="quick_scalper",
                    symbol=symbol,
                    action="open",
                    side=signal.direction,
                    size_usd=self.config.POSITION_SIZE_USD,
                    leverage=self.config.LEVERAGE,
                    tp_pct=self.config.TAKE_PROFIT_PCT,
                    sl_pct=self.config.STOP_LOSS_PCT,
                    metadata={
                        'score': signal.score,
                        'rsi': signal.rsi,
                        'ob_imbalance': signal.ob_imbalance
                    }
                )

                if response.status != "accepted":
                    print(f"  ⚠️ REJECTED: {sym} - {response.message}")
                    return False

                fill_price = response.fill_price or signal.price
                amount = self.config.POSITION_SIZE_USD / fill_price

            else:
                # Fallback: Direct exchange access
                amount = self.config.POSITION_SIZE_USD / signal.price
                fill_price = signal.price

                try:
                    self.exchange.set_leverage(self.config.LEVERAGE, symbol)
                except:
                    pass

                side = 'buy' if signal.direction == 'long' else 'sell'
                order = self.exchange.create_market_order(
                    symbol, side, amount,
                    params={
                        'tradeSide': 'open',
                        'holdSide': signal.direction,
                        'productType': 'USDT-FUTURES'
                    }
                )

            # Track locally
            pos = ScalperPosition(
                symbol=symbol,
                side=signal.direction,
                entry_price=fill_price,
                size=amount,
                entry_time=datetime.now(),
                score=signal.score,
                tp_price=signal.tp_price,
                sl_price=signal.sl_price
            )

            self.positions[symbol] = pos
            self.last_trade_time[symbol] = datetime.now()
            self._save_state()

            router_tag = "[ROUTER] " if ORDER_ROUTER_AVAILABLE else ""
            print(f"\n{'='*50}")
            print(f"{router_tag}[OPEN] {signal.direction.upper()} {sym} @ ${fill_price:.4f}")
            print(f"  Score: {signal.score:.1f} (RSI:{signal.rsi_score:.0f} OB:{signal.ob_score:.0f} Vol:{signal.volume_score:.0f} Mom:{signal.momentum_score:.0f})")
            print(f"  RSI: {signal.rsi:.1f} | OB Imbalance: {signal.ob_imbalance*100:+.1f}%")
            print(f"  TP: ${signal.tp_price:.4f} | SL: ${signal.sl_price:.4f}")
            print(f"{'='*50}")

            return True

        except Exception as e:
            print(f"  Open error: {e}")
            return False

    def close_position(self, symbol: str, reason: str) -> bool:
        """Close a position via Unified Order Router"""
        try:
            pos = self.positions.get(symbol)
            if not pos:
                return False

            sym = symbol.replace('/USDT:USDT', '')

            # ===== USE ORDER ROUTER IF AVAILABLE =====
            if ORDER_ROUTER_AVAILABLE:
                response = submit_order(
                    system="quick_scalper",
                    symbol=symbol,
                    action="close",
                    side=pos.side,
                    size_usd=self.config.POSITION_SIZE_USD
                )

                if response.status != "accepted":
                    # Check if already closed
                    if "already closed" in response.message.lower():
                        del self.positions[symbol]
                        self._save_state()
                        print(f"  {sym} - Already closed externally")
                        return True
                    print(f"  ⚠️ Close rejected: {response.message}")
                    return False

                current_price = response.fill_price or self.exchange.fetch_ticker(symbol)['last']
            else:
                # Fallback: Direct exchange access
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']

                side = 'sell' if pos.side == 'long' else 'buy'
                order = self.exchange.create_market_order(
                    symbol, side, pos.size,
                    params={
                        'tradeSide': 'close',
                        'holdSide': pos.side,
                        'productType': 'USDT-FUTURES'
                    }
                )

            # Calculate PnL
            if pos.side == 'long':
                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
            else:
                pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100

            pnl_usd = pnl_pct / 100 * self.config.POSITION_SIZE_USD * self.config.LEVERAGE
            hold_time = (datetime.now() - pos.entry_time).total_seconds()

            # Update stats
            if pnl_usd > 0:
                self.stats['wins'] += 1
            else:
                self.stats['losses'] += 1
            self.stats['total_pnl'] += pnl_usd

            if reason == 'TAKE_PROFIT':
                self.stats['tp_exits'] += 1
            elif reason == 'STOP_LOSS':
                self.stats['sl_exits'] += 1
            else:
                self.stats['time_exits'] += 1

            # V3.2.0: Track averaging stats
            avg_steps = pos.averaging_steps
            if avg_steps > 0:
                self.stats['avg_trades'] += 1

            del self.positions[symbol]
            self._save_state()

            router_tag = "[ROUTER] " if ORDER_ROUTER_AVAILABLE else ""
            emoji = "+" if pnl_usd >= 0 else ""
            avg_tag = f" [AVG:{avg_steps}]" if avg_steps > 0 else ""
            print(f"\n{router_tag}[CLOSE] {sym} - {reason}{avg_tag}")
            print(f"  PnL: {emoji}${pnl_usd:.2f} ({emoji}{pnl_pct:.2f}%) | Hold: {hold_time:.0f}s")
            if avg_steps > 0:
                print(f"  Averaging: {avg_steps} steps | Entry: ${pos.entry_price:.4f} → Avg: ${pos.avg_entry_price:.4f}")

            total = self.stats['wins'] + self.stats['losses']
            wr = self.stats['wins'] / total * 100 if total > 0 else 0
            print(f"  Stats: {self.stats['wins']}W/{self.stats['losses']}L ({wr:.1f}%) | Total: ${self.stats['total_pnl']:.2f}")
            print(f"  Exits: TP:{self.stats['tp_exits']} SL:{self.stats['sl_exits']} Time:{self.stats['time_exits']} | Avg Trades: {self.stats['avg_trades']}")

            return True

        except Exception as e:
            error_str = str(e)
            # Handle "No position to close" - position already closed
            if '22002' in error_str or 'No position' in error_str:
                print(f"  {symbol.replace('/USDT:USDT', '')} - Already closed (TP/SL hit)")
                if symbol in self.positions:
                    del self.positions[symbol]
                    self._save_state()
                return True
            print(f"  Close error: {e}")
            return False

    def execute_averaging(self, pos: ScalperPosition, current_price: float) -> bool:
        """
        Execute averaging step for a position (V3.2.0)
        Returns True if averaging was executed successfully
        """
        symbol = pos.symbol
        sym = symbol.replace('/USDT:USDT', '')

        try:
            # Get multiplier for this step
            step = pos.averaging_steps
            if step >= len(self.config.AVG_MULTIPLIERS):
                return False

            multiplier = self.config.AVG_MULTIPLIERS[step]
            add_size_usd = self.config.POSITION_SIZE_USD * multiplier
            add_amount = add_size_usd / current_price

            # Execute averaging order
            if ORDER_ROUTER_AVAILABLE:
                response = submit_order(
                    system="quick_scalper",
                    symbol=symbol,
                    action="open",  # Add to position
                    side=pos.side,
                    size_usd=add_size_usd,
                    leverage=self.config.LEVERAGE,
                    metadata={'averaging_step': step + 1}
                )
                if response.status != "accepted":
                    print(f"  ⚠️ Averaging rejected: {response.message}")
                    return False
                fill_price = response.fill_price or current_price
            else:
                # Direct exchange order
                side = 'buy' if pos.side == 'long' else 'sell'
                order = self.exchange.create_market_order(
                    symbol, side, add_amount,
                    params={
                        'tradeSide': 'open',
                        'holdSide': pos.side,
                        'productType': 'USDT-FUTURES'
                    }
                )
                fill_price = current_price

            # Update position state
            old_size = pos.size
            new_size = old_size + add_amount

            # Calculate new weighted average entry
            new_avg_entry = (pos.avg_entry_price * old_size + fill_price * add_amount) / new_size

            # Update position
            pos.avg_entry_price = new_avg_entry
            pos.size = new_size
            pos.averaging_steps += 1
            pos.last_avg_time = datetime.now()

            # Recalculate TP/SL from new average entry
            if pos.side == 'long':
                pos.tp_price = new_avg_entry * (1 + self.config.TAKE_PROFIT_PCT / 100)
                pos.sl_price = new_avg_entry * (1 - self.config.STOP_LOSS_PCT / 100)
            else:
                pos.tp_price = new_avg_entry * (1 - self.config.TAKE_PROFIT_PCT / 100)
                pos.sl_price = new_avg_entry * (1 + self.config.STOP_LOSS_PCT / 100)

            # Update stats
            self.stats['avg_steps_total'] += 1

            self._save_state()

            upnl_pct = pos.calculate_upnl_pct(current_price)
            print(f"\n[AVG] {sym} Step {pos.averaging_steps}/{self.config.AVG_MAX_STEPS}")
            print(f"  Added {multiplier}x (${add_size_usd:.2f}) @ ${fill_price:.4f}")
            print(f"  Avg Entry: ${pos.entry_price:.4f} → ${new_avg_entry:.4f}")
            print(f"  New TP: ${pos.tp_price:.4f} | SL: ${pos.sl_price:.4f}")
            print(f"  UPNL: {upnl_pct:+.3f}% | Size: ${old_size * pos.entry_price:.2f} → ${new_size * new_avg_entry:.2f}")

            return True

        except Exception as e:
            print(f"  Averaging error for {sym}: {e}")
            return False

    def manage_positions(self):
        """Check and manage all open positions (V3.2.0: with averaging)"""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]

            try:
                # First check if position still exists on exchange
                try:
                    exchange_positions = self.exchange.fetch_positions([symbol])
                    has_position = any(
                        p['symbol'] == symbol and float(p['contracts']) > 0
                        for p in exchange_positions
                    )
                    if not has_position:
                        # Position was closed elsewhere (TP/SL hit, liquidation, etc.)
                        print(f"[{datetime.now().strftime('%H:%M:%S')}] {symbol.replace('/USDT:USDT', '')} - Position closed externally")
                        # Track averaging stats if this position had averaging
                        if pos.averaging_steps > 0:
                            self.stats['avg_trades'] += 1
                        del self.positions[symbol]
                        self._save_state()
                        continue
                except:
                    pass  # If check fails, continue with normal management

                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']

                # V3.2.0: Check for averaging opportunity BEFORE exit check
                if pos.can_average(current_price, self.config):
                    self.execute_averaging(pos, current_price)
                    # After averaging, don't immediately check exit - give it a chance
                    continue

                should_exit, reason = pos.check_exit(current_price, self.config)
                if should_exit:
                    self.close_position(symbol, reason)

            except Exception as e:
                continue

    # ========== MAIN LOOP ==========

    def find_best_opportunity(self) -> Optional[HybridSignal]:
        """Find the best trading opportunity"""
        opportunities = []

        for symbol in self.symbols_to_scan:
            # Skip if already in position
            if symbol in self.positions:
                continue

            # Skip if in cooldown
            if symbol in self.last_trade_time:
                elapsed = (datetime.now() - self.last_trade_time[symbol]).total_seconds()
                if elapsed < self.config.COOLDOWN_SECONDS:
                    continue

            signal = self.calculate_signal(symbol)
            if signal and signal.score >= self.config.MIN_SCORE:
                opportunities.append(signal)

        if not opportunities:
            return None

        # Return highest scoring opportunity
        opportunities.sort(key=lambda x: x.score, reverse=True)
        return opportunities[0]

    def run_cycle(self):
        """Run one scan cycle"""
        self.refresh_symbols()
        self.manage_positions()

        # Check position limit
        if len(self.positions) >= self.config.MAX_POSITIONS:
            return

        # Find opportunity
        signal = self.find_best_opportunity()

        if signal:
            self.open_position(signal)
        else:
            # Always show status each cycle
            now = datetime.now()
            active = len(self.positions)
            scanned = len(self.symbols_to_scan)
            print(f"[{now.strftime('%H:%M:%S')}] Scanned {scanned} | Active: {active}/{self.config.MAX_POSITIONS} | No RSI+OB signals")

    def run(self):
        """Main run loop"""
        print("\n" + "=" * 65)
        print("Starting Quick Scalper V3.2.0 with Micro-Averaging...")
        print("=" * 65 + "\n")

        while True:
            try:
                self.run_cycle()
                time.sleep(self.config.SCAN_INTERVAL_SECONDS)

            except KeyboardInterrupt:
                print("\nShutting down...")
                self._save_state()
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(10)


# ========== ENTRY POINT ==========

def main():
    scalper = HybridScalper()
    scalper.run()


if __name__ == '__main__':
    main()
