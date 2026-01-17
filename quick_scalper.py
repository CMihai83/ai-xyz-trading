#!/usr/bin/env python3
"""
AI-XYZ Quick Scalper V2.0.0 - Integrated Opportunity Discovery
===============================================================

Combines RSI mean-reversion with multi-factor opportunity scoring.
Integrates prediction API signals with volatility-based symbol selection.

FEATURES:
- Dynamic volatile symbol scanning (>100% ann. volatility)
- Multi-factor scoring: RSI + Volume + Momentum + Volatility + Predictions
- ATR-based dynamic TP/SL
- Prediction API integration for directional bias

BACKTEST RESULTS:
- DASH: 72.1% WR, 3.41 PF (high volatility)
- FIL/ATOM/APT: ~62% WR (prediction-based)

DESIGN: Claude (Opus 4.5) + Grok Consortium
DATE: January 17, 2026
"""

import ccxt
import time
import json
import os
import redis
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()


@dataclass
class OpportunitySignal:
    """Represents a scored trading opportunity"""
    symbol: str
    direction: str
    score: float
    rsi: float
    vol_spike: float
    momentum: bool
    volatility: float
    atr_pct: float
    prediction_conf: float
    tp_pct: float
    sl_pct: float
    price: float


class QuickScalperConfig:
    """Configuration for integrated Quick Scalper + Opportunity Engine"""

    # ========== SYMBOL SOURCES ==========
    # Prediction API
    PREDICTION_API_URL = "http://prediction_service:8009"
    MIN_PREDICTION_CONFIDENCE = 70

    # Volatility scanning
    MIN_VOLATILITY = 80.0      # Minimum annualized volatility %
    MAX_VOLATILITY = 500.0     # Maximum (avoid illiquid)
    MIN_VOLUME_USD = 5_000_000  # $5M daily volume

    # Fallback symbols
    FALLBACK_SYMBOLS = [
        'FIL/USDT:USDT',
        'ATOM/USDT:USDT',
        'APT/USDT:USDT',
        'DASH/USDT:USDT',
    ]

    # ========== OPPORTUNITY SCORING ==========
    # Score thresholds
    MIN_SCORE = 65             # Minimum score to enter
    HIGH_SCORE = 80            # High confidence entry

    # Scoring weights (total = 100%)
    WEIGHT_RSI = 0.30          # RSI signal strength
    WEIGHT_VOLUME = 0.20       # Volume spike
    WEIGHT_MOMENTUM = 0.20     # Price momentum
    WEIGHT_VOLATILITY = 0.15   # Volatility bonus
    WEIGHT_PREDICTION = 0.15   # Prediction API confidence

    # ========== ENTRY THRESHOLDS ==========
    RSI_OVERSOLD = 30          # Long entry (relaxed for volatile)
    RSI_OVERBOUGHT = 70        # Short entry
    RSI_EXTREME_OVERSOLD = 20  # Strong long signal
    RSI_EXTREME_OVERBOUGHT = 80  # Strong short signal

    # ========== RISK MANAGEMENT ==========
    # Base TP/SL (adjusted by ATR)
    BASE_TP_PCT = 0.4          # 0.4% base take profit
    BASE_SL_PCT = 0.25         # 0.25% base stop loss
    ATR_MULTIPLIER = 0.12      # ATR adjustment factor

    # Position limits
    POSITION_SIZE_USD = 50.0
    MAX_POSITIONS = 4
    LEVERAGE = 10

    # Timing
    MAX_HOLD_CANDLES = 6       # Max hold time
    COOLDOWN_SECONDS = 180     # 3 min cooldown

    # ========== SCAN INTERVALS ==========
    TIMEFRAME = '15m'
    CANDLE_MINUTES = 15
    SYMBOL_SCAN_INTERVAL = 300     # 5 min
    OPPORTUNITY_SCAN_INTERVAL = 30  # 30 sec


class QuickScalperPosition:
    """Represents an active scalp position"""

    def __init__(self, symbol: str, side: str, entry_price: float,
                 size: float, entry_time: datetime, score: float,
                 tp_pct: float, sl_pct: float, candle_count: int = 0):
        self.symbol = symbol
        self.side = side
        self.entry_price = entry_price
        self.size = size
        self.entry_time = entry_time
        self.score = score
        self.candle_count = candle_count
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.take_profit = self._calc_tp()
        self.stop_loss = self._calc_sl()

    def _calc_tp(self) -> float:
        if self.side == 'long':
            return self.entry_price * (1 + self.tp_pct / 100)
        else:
            return self.entry_price * (1 - self.tp_pct / 100)

    def _calc_sl(self) -> float:
        if self.side == 'long':
            return self.entry_price * (1 - self.sl_pct / 100)
        else:
            return self.entry_price * (1 + self.sl_pct / 100)

    def check_exit(self, current_price: float) -> Tuple[bool, str]:
        if self.side == 'long':
            if current_price >= self.take_profit:
                return True, 'take_profit'
            if current_price <= self.stop_loss:
                return True, 'stop_loss'
        else:
            if current_price <= self.take_profit:
                return True, 'take_profit'
            if current_price >= self.stop_loss:
                return True, 'stop_loss'

        if self.candle_count >= QuickScalperConfig.MAX_HOLD_CANDLES:
            return True, 'max_hold'

        return False, ''

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'side': self.side,
            'entry_price': self.entry_price,
            'size': self.size,
            'entry_time': self.entry_time.isoformat(),
            'score': self.score,
            'candle_count': self.candle_count,
            'tp_pct': self.tp_pct,
            'sl_pct': self.sl_pct,
            'take_profit': self.take_profit,
            'stop_loss': self.stop_loss
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'QuickScalperPosition':
        return cls(
            symbol=data['symbol'],
            side=data['side'],
            entry_price=data['entry_price'],
            size=data['size'],
            entry_time=datetime.fromisoformat(data['entry_time']),
            score=data.get('score', 70),
            tp_pct=data.get('tp_pct', 0.4),
            sl_pct=data.get('sl_pct', 0.25),
            candle_count=data['candle_count']
        )


class QuickScalper:
    """
    Integrated Quick Scalper with Opportunity Discovery Engine.

    Combines:
    - Volatility-based symbol scanning
    - Multi-factor opportunity scoring
    - Prediction API directional bias
    - Dynamic ATR-based TP/SL
    """

    def __init__(self):
        # Exchange setup
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
        })
        self.exchange.load_markets()

        # Redis for state
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=2)

        # Symbol pools
        self.volatile_symbols: List[dict] = []
        self.prediction_long: List[dict] = []
        self.prediction_short: List[dict] = []
        self.last_symbol_scan: datetime = datetime.min
        self.last_prediction_fetch: datetime = datetime.min

        # Active positions
        self.positions: Dict[str, QuickScalperPosition] = {}
        self.last_trade_time: Dict[str, datetime] = {}

        # Statistics
        self.stats = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'avg_score': 0.0
        }

        self._load_state()

        print("=" * 65)
        print("Quick Scalper V2.0.0 - Integrated Opportunity Discovery")
        print("Designed by Claude (Opus 4.5) + Grok")
        print("=" * 65)
        print(f"  Min Volatility: {QuickScalperConfig.MIN_VOLATILITY}%")
        print(f"  Min Score: {QuickScalperConfig.MIN_SCORE}")
        print(f"  RSI: <{QuickScalperConfig.RSI_OVERSOLD} LONG, >{QuickScalperConfig.RSI_OVERBOUGHT} SHORT")
        print(f"  Base TP/SL: {QuickScalperConfig.BASE_TP_PCT}% / {QuickScalperConfig.BASE_SL_PCT}%")
        print(f"  Max Positions: {QuickScalperConfig.MAX_POSITIONS}")

    def _load_state(self):
        try:
            state_data = self.redis.get('quick_scalper:state')
            if state_data:
                state = json.loads(state_data)
                for sym, pos_data in state.get('positions', {}).items():
                    self.positions[sym] = QuickScalperPosition.from_dict(pos_data)
                for sym, ts in state.get('last_trade_time', {}).items():
                    self.last_trade_time[sym] = datetime.fromisoformat(ts)
                self.stats = state.get('stats', self.stats)
                print(f"  Loaded state: {len(self.positions)} positions")
        except Exception as e:
            print(f"  State load error: {e}")

    def _save_state(self):
        try:
            state = {
                'positions': {s: p.to_dict() for s, p in self.positions.items()},
                'last_trade_time': {s: t.isoformat() for s, t in self.last_trade_time.items()},
                'stats': self.stats,
                'updated_at': datetime.now().isoformat()
            }
            self.redis.set('quick_scalper:state', json.dumps(state))
        except Exception as e:
            print(f"  State save error: {e}")

    # ========== SYMBOL SCANNING ==========

    def scan_volatile_symbols(self):
        """Scan for high-volatility symbols"""
        print("\n[VOLATILITY SCAN] Searching for volatile symbols...")

        try:
            markets = self.exchange.load_markets()
            usdt_futures = [s for s in markets if s.endswith('/USDT:USDT') and markets[s]['active']]

            volatile = []
            for symbol in usdt_futures[:120]:
                try:
                    ohlcv = self.exchange.fetch_ohlcv(symbol, '4h', limit=50)
                    if len(ohlcv) < 20:
                        continue

                    df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

                    # Volatility
                    returns = df['c'].pct_change().dropna()
                    volatility = returns.std() * np.sqrt(6 * 365) * 100

                    # Volume
                    avg_volume = df['v'].mean() * df['c'].iloc[-1]

                    # ATR
                    df['tr'] = np.maximum(
                        df['h'] - df['l'],
                        np.maximum(abs(df['h'] - df['c'].shift()), abs(df['l'] - df['c'].shift()))
                    )
                    atr_pct = df['tr'].rolling(14).mean().iloc[-1] / df['c'].iloc[-1] * 100

                    if (QuickScalperConfig.MIN_VOLATILITY <= volatility <= QuickScalperConfig.MAX_VOLATILITY and
                        avg_volume >= QuickScalperConfig.MIN_VOLUME_USD):
                        volatile.append({
                            'symbol': symbol,
                            'volatility': volatility,
                            'atr_pct': atr_pct,
                            'volume_usd': avg_volume
                        })
                except:
                    continue

            volatile.sort(key=lambda x: x['volatility'], reverse=True)
            self.volatile_symbols = volatile[:15]

            syms = [s['symbol'].replace('/USDT:USDT', '') for s in self.volatile_symbols[:5]]
            print(f"  Found {len(self.volatile_symbols)} volatile: {syms}")

        except Exception as e:
            print(f"  Volatility scan error: {e}")
            self._use_fallback()

    def fetch_predictions(self):
        """Fetch predictions from API"""
        try:
            url = f"{QuickScalperConfig.PREDICTION_API_URL}/market/overview"
            response = requests.get(url, timeout=30)

            if response.status_code == 200:
                data = response.json()

                self.prediction_long = [
                    s for s in data.get('top_bullish', [])
                    if s.get('confidence', 0) >= QuickScalperConfig.MIN_PREDICTION_CONFIDENCE
                ][:5]

                self.prediction_short = [
                    s for s in data.get('top_bearish', [])
                    if s.get('confidence', 0) >= QuickScalperConfig.MIN_PREDICTION_CONFIDENCE
                ][:5]

                self.last_prediction_fetch = datetime.now()

                long_syms = [s['symbol'].replace('/USDT:USDT', '') for s in self.prediction_long]
                short_syms = [s['symbol'].replace('/USDT:USDT', '') for s in self.prediction_short]
                print(f"\n[PREDICTIONS] Long: {long_syms} | Short: {short_syms}")

        except Exception as e:
            print(f"  Prediction fetch error: {e}")

    def _use_fallback(self):
        """Use fallback symbols"""
        self.volatile_symbols = [
            {'symbol': s, 'volatility': 100, 'atr_pct': 2.0}
            for s in QuickScalperConfig.FALLBACK_SYMBOLS
        ]

    def refresh_symbols(self):
        """Refresh all symbol sources"""
        elapsed = (datetime.now() - self.last_symbol_scan).total_seconds()
        if elapsed >= QuickScalperConfig.SYMBOL_SCAN_INTERVAL or not self.volatile_symbols:
            self.scan_volatile_symbols()
            self.fetch_predictions()
            self.last_symbol_scan = datetime.now()

    # ========== OPPORTUNITY SCORING ==========

    def calculate_opportunity(self, symbol: str) -> Optional[OpportunitySignal]:
        """Calculate multi-factor opportunity score"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, QuickScalperConfig.TIMEFRAME, limit=50)
            df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])

            price = df['c'].iloc[-1]

            # RSI
            delta = df['c'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            rsi = (100 - (100 / (1 + rs))).iloc[-1]

            # Volume spike
            vol_avg = df['v'].rolling(10).mean().iloc[-1]
            vol_spike = df['v'].iloc[-1] / vol_avg if vol_avg > 0 else 1

            # Momentum
            sma5 = df['c'].rolling(5).mean().iloc[-1]
            sma10 = df['c'].rolling(10).mean().iloc[-1]
            momentum_up = price > sma5 and sma5 > sma10
            momentum_down = price < sma5 and sma5 < sma10

            # ATR
            df['tr'] = np.maximum(
                df['h'] - df['l'],
                np.maximum(abs(df['h'] - df['c'].shift()), abs(df['l'] - df['c'].shift()))
            )
            atr_pct = df['tr'].rolling(14).mean().iloc[-1] / price * 100

            # Get volatility
            sym_data = next((s for s in self.volatile_symbols if s['symbol'] == symbol), None)
            volatility = sym_data['volatility'] if sym_data else 80

            # Get prediction confidence
            pred_long = next((p for p in self.prediction_long if p.get('symbol') == symbol), None)
            pred_short = next((p for p in self.prediction_short if p.get('symbol') == symbol), None)

            # Determine direction
            direction = None
            if rsi < QuickScalperConfig.RSI_OVERSOLD:
                direction = 'long'
            elif rsi > QuickScalperConfig.RSI_OVERBOUGHT:
                direction = 'short'
            else:
                return None

            # Calculate component scores
            if direction == 'long':
                rsi_score = min(100, (QuickScalperConfig.RSI_OVERSOLD - rsi) / QuickScalperConfig.RSI_OVERSOLD * 150)
                mom_score = 100 if momentum_up else 40
                pred_conf = pred_long.get('confidence', 0) if pred_long else 0
            else:
                rsi_score = min(100, (rsi - QuickScalperConfig.RSI_OVERBOUGHT) / (100 - QuickScalperConfig.RSI_OVERBOUGHT) * 150)
                mom_score = 100 if momentum_down else 40
                pred_conf = pred_short.get('confidence', 0) if pred_short else 0

            vol_score = min(100, vol_spike / 2 * 100)
            volatility_score = min(100, (volatility - 50) / 150 * 100)
            pred_score = pred_conf

            # Combined score
            score = (
                QuickScalperConfig.WEIGHT_RSI * rsi_score +
                QuickScalperConfig.WEIGHT_VOLUME * vol_score +
                QuickScalperConfig.WEIGHT_MOMENTUM * mom_score +
                QuickScalperConfig.WEIGHT_VOLATILITY * volatility_score +
                QuickScalperConfig.WEIGHT_PREDICTION * pred_score
            )

            # Dynamic TP/SL
            atr_adj = min(atr_pct * QuickScalperConfig.ATR_MULTIPLIER, 0.4)
            tp_pct = QuickScalperConfig.BASE_TP_PCT + atr_adj
            sl_pct = QuickScalperConfig.BASE_SL_PCT + atr_adj

            return OpportunitySignal(
                symbol=symbol,
                direction=direction,
                score=score,
                rsi=rsi,
                vol_spike=vol_spike,
                momentum=momentum_up if direction == 'long' else momentum_down,
                volatility=volatility,
                atr_pct=atr_pct,
                prediction_conf=pred_conf,
                tp_pct=tp_pct,
                sl_pct=sl_pct,
                price=price
            )

        except Exception as e:
            return None

    def find_opportunities(self) -> List[OpportunitySignal]:
        """Find all trading opportunities"""
        opportunities = []

        # Combine volatile symbols + prediction symbols
        all_symbols = set()

        for s in self.volatile_symbols:
            all_symbols.add(s['symbol'])
        for s in self.prediction_long:
            all_symbols.add(s.get('symbol', ''))
        for s in self.prediction_short:
            all_symbols.add(s.get('symbol', ''))

        for symbol in all_symbols:
            if not symbol:
                continue

            # Skip if in position or cooldown
            if symbol in self.positions:
                continue
            if symbol in self.last_trade_time:
                elapsed = (datetime.now() - self.last_trade_time[symbol]).total_seconds()
                if elapsed < QuickScalperConfig.COOLDOWN_SECONDS:
                    continue

            signal = self.calculate_opportunity(symbol)
            if signal and signal.score >= QuickScalperConfig.MIN_SCORE:
                opportunities.append(signal)

        opportunities.sort(key=lambda x: x.score, reverse=True)
        return opportunities

    # ========== POSITION MANAGEMENT ==========

    def open_position(self, signal: OpportunitySignal) -> bool:
        try:
            symbol = signal.symbol
            amount = QuickScalperConfig.POSITION_SIZE_USD / signal.price

            try:
                self.exchange.set_leverage(QuickScalperConfig.LEVERAGE, symbol)
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

            pos = QuickScalperPosition(
                symbol=symbol,
                side=signal.direction,
                entry_price=signal.price,
                size=amount,
                entry_time=datetime.now(),
                score=signal.score,
                tp_pct=signal.tp_pct,
                sl_pct=signal.sl_pct
            )

            self.positions[symbol] = pos
            self.last_trade_time[symbol] = datetime.now()
            self._save_state()

            sym = symbol.replace('/USDT:USDT', '')
            print(f"\n[OPEN] {signal.direction.upper()} {sym} @ ${signal.price:.4f}")
            print(f"  Score: {signal.score:.1f} | RSI: {signal.rsi:.1f} | Vol: {signal.volatility:.0f}%")
            print(f"  TP: ${pos.take_profit:.4f} (+{signal.tp_pct:.2f}%) | SL: ${pos.stop_loss:.4f} (-{signal.sl_pct:.2f}%)")

            return True

        except Exception as e:
            print(f"  Open error: {e}")
            return False

    def close_position(self, symbol: str, reason: str) -> bool:
        try:
            pos = self.positions.get(symbol)
            if not pos:
                return False

            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']

            close_side = 'sell' if pos.side == 'long' else 'buy'
            order = self.exchange.create_market_order(
                symbol, close_side, pos.size,
                params={
                    'tradeSide': 'close',
                    'holdSide': pos.side,
                    'productType': 'USDT-FUTURES'
                }
            )

            if pos.side == 'long':
                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
            else:
                pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100

            pnl_usd = pnl_pct / 100 * QuickScalperConfig.POSITION_SIZE_USD * QuickScalperConfig.LEVERAGE
            hold_min = (datetime.now() - pos.entry_time).total_seconds() / 60

            # Update stats
            self.stats['total_trades'] += 1
            self.stats['total_pnl'] += pnl_usd
            if pnl_usd > 0:
                self.stats['wins'] += 1
            else:
                self.stats['losses'] += 1

            n = self.stats['total_trades']
            self.stats['avg_score'] = (self.stats['avg_score'] * (n-1) + pos.score) / n

            del self.positions[symbol]
            self.last_trade_time[symbol] = datetime.now()
            self._save_state()

            wr = self.stats['wins'] / n * 100 if n > 0 else 0
            sym = symbol.replace('/USDT:USDT', '')

            print(f"\n[CLOSE] {pos.side.upper()} {sym} [{reason}]")
            print(f"  Entry: ${pos.entry_price:.4f} -> Exit: ${current_price:.4f}")
            print(f"  P&L: {pnl_pct:+.2f}% (${pnl_usd:+.2f}) | Hold: {hold_min:.1f}min")
            print(f"  Stats: {self.stats['wins']}W/{self.stats['losses']}L ({wr:.1f}%) | Total: ${self.stats['total_pnl']:.2f}")

            return True

        except Exception as e:
            print(f"  Close error: {e}")
            return False

    def manage_positions(self):
        """Check and manage all positions"""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]

            try:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker['last']

                should_exit, reason = pos.check_exit(current_price)
                if should_exit:
                    self.close_position(symbol, reason)

            except Exception as e:
                continue

    def increment_candle_counts(self):
        for pos in self.positions.values():
            pos.candle_count += 1
        self._save_state()

    # ========== MAIN LOOP ==========

    def run_cycle(self):
        self.refresh_symbols()
        self.manage_positions()

        if len(self.positions) >= QuickScalperConfig.MAX_POSITIONS:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Max positions ({QuickScalperConfig.MAX_POSITIONS}) reached")
            return

        opportunities = self.find_opportunities()

        if opportunities:
            best = opportunities[0]
            sym = best.symbol.replace('/USDT:USDT', '')
            print(f"\n[OPPORTUNITY] {sym}: Score={best.score:.1f} RSI={best.rsi:.1f} {best.direction.upper()}")
            self.open_position(best)
        else:
            # Show periodic status
            all_symbols = set(s['symbol'] for s in self.volatile_symbols)
            for s in self.prediction_long:
                all_symbols.add(s.get('symbol', ''))
            for s in self.prediction_short:
                all_symbols.add(s.get('symbol', ''))
            all_symbols.discard('')
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Scanned {len(all_symbols)} symbols - No RSI extremes (<30 or >70)")

    def run(self):
        print("\n" + "=" * 65)
        print("Starting Quick Scalper V2.0.0...")
        print("=" * 65)

        last_candle = None

        while True:
            try:
                now = datetime.now()
                current_candle = now.minute // QuickScalperConfig.CANDLE_MINUTES

                if last_candle is None or current_candle != last_candle:
                    self.increment_candle_counts()
                    last_candle = current_candle

                self.run_cycle()

                if self.positions:
                    active = [s.replace('/USDT:USDT', '') for s in self.positions.keys()]
                    print(f"\n[{now.strftime('%H:%M:%S')}] Active: {active}")

                time.sleep(QuickScalperConfig.OPPORTUNITY_SCAN_INTERVAL)

            except KeyboardInterrupt:
                print("\nShutting down...")
                self._save_state()
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(10)


def main():
    scalper = QuickScalper()
    scalper.run()


if __name__ == '__main__':
    main()
