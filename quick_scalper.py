#!/usr/bin/env python3
"""
AI-XYZ Quick Scalper Module V1.0.0
===================================

High-frequency RSI mean-reversion scalping strategy for predictable symbols.
Based on backtest validation: FIL (62.1% WR, 18min hold), ATOM (62.9% WR, 21min hold)

STRATEGY PARAMETERS (Backtest Validated):
- Entry: RSI < 25 (LONG), RSI > 75 (SHORT)
- Take Profit: 0.3%
- Stop Loss: 0.2%
- Max Hold: 4 candles (60 minutes on 15m TF)
- Position Size: $5 per position

DESIGN: Claude (Opus 4.5) + Grok Consortium
DATE: January 17, 2026
"""

import ccxt
import time
import json
import os
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from dotenv import load_dotenv

load_dotenv()


class QuickScalperConfig:
    """Configuration for Quick Scalper strategy"""

    # Symbols selected by backtest analysis (high predictability + volatility)
    SCALP_SYMBOLS = [
        'FIL/USDT:USDT',   # 62.1% WR, 2.45 PF, 18min avg hold
        'ATOM/USDT:USDT',  # 62.9% WR, 2.44 PF, 21min avg hold
    ]

    # RSI parameters (backtest validated)
    RSI_PERIOD = 14
    RSI_OVERSOLD = 25      # Long entry
    RSI_OVERBOUGHT = 75    # Short entry

    # Risk management (backtest validated)
    TAKE_PROFIT_PCT = 0.3  # 0.3% profit target
    STOP_LOSS_PCT = 0.2    # 0.2% stop loss
    MAX_HOLD_CANDLES = 4   # Max 4 candles (60 min on 15m TF)

    # Position sizing
    POSITION_SIZE_USD = 5.0
    MAX_CONCURRENT_SCALPS = 2  # One per symbol

    # Timeframe
    TIMEFRAME = '15m'
    CANDLE_MINUTES = 15

    # Leverage (moderate for scalping)
    LEVERAGE = 10

    # Cooldown between trades on same symbol
    COOLDOWN_SECONDS = 300  # 5 minutes


class QuickScalperPosition:
    """Represents an active scalp position"""

    def __init__(self, symbol: str, side: str, entry_price: float,
                 size: float, entry_time: datetime, candle_count: int = 0):
        self.symbol = symbol
        self.side = side  # 'long' or 'short'
        self.entry_price = entry_price
        self.size = size
        self.entry_time = entry_time
        self.candle_count = candle_count
        self.take_profit = self._calc_tp()
        self.stop_loss = self._calc_sl()

    def _calc_tp(self) -> float:
        """Calculate take profit price"""
        if self.side == 'long':
            return self.entry_price * (1 + QuickScalperConfig.TAKE_PROFIT_PCT / 100)
        else:
            return self.entry_price * (1 - QuickScalperConfig.TAKE_PROFIT_PCT / 100)

    def _calc_sl(self) -> float:
        """Calculate stop loss price"""
        if self.side == 'long':
            return self.entry_price * (1 - QuickScalperConfig.STOP_LOSS_PCT / 100)
        else:
            return self.entry_price * (1 + QuickScalperConfig.STOP_LOSS_PCT / 100)

    def check_exit(self, current_price: float) -> Tuple[bool, str]:
        """Check if position should be exited"""
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

        # Check max hold time
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
            'candle_count': self.candle_count,
            'take_profit': self.take_profit,
            'stop_loss': self.stop_loss
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'QuickScalperPosition':
        pos = cls(
            symbol=data['symbol'],
            side=data['side'],
            entry_price=data['entry_price'],
            size=data['size'],
            entry_time=datetime.fromisoformat(data['entry_time']),
            candle_count=data['candle_count']
        )
        return pos


class QuickScalper:
    """
    High-frequency RSI mean-reversion scalping strategy

    Runs alongside the main AI-XYZ system, targeting predictable symbols
    with quick profit turnover.
    """

    def __init__(self):
        # Exchange setup
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {
                'defaultType': 'swap',
                'defaultSubType': 'USDT'
            }
        })
        self.exchange.load_markets()

        # Redis connection for state persistence
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis = redis.Redis(host=redis_host, port=redis_port, db=2)  # Use db=2 for scalper

        # Active positions
        self.positions: Dict[str, QuickScalperPosition] = {}

        # Cooldown tracking
        self.last_trade_time: Dict[str, datetime] = {}

        # Statistics
        self.stats = {
            'total_trades': 0,
            'wins': 0,
            'losses': 0,
            'total_pnl': 0.0,
            'avg_hold_time': 0.0
        }

        # Load state from Redis
        self._load_state()

        print(f"QuickScalper V1.0.0 initialized")
        print(f"  Symbols: {QuickScalperConfig.SCALP_SYMBOLS}")
        print(f"  RSI: <{QuickScalperConfig.RSI_OVERSOLD} LONG, >{QuickScalperConfig.RSI_OVERBOUGHT} SHORT")
        print(f"  TP: {QuickScalperConfig.TAKE_PROFIT_PCT}%, SL: {QuickScalperConfig.STOP_LOSS_PCT}%")
        print(f"  Max hold: {QuickScalperConfig.MAX_HOLD_CANDLES} candles ({QuickScalperConfig.MAX_HOLD_CANDLES * QuickScalperConfig.CANDLE_MINUTES} min)")

    def _load_state(self):
        """Load state from Redis"""
        try:
            state_data = self.redis.get('quick_scalper:state')
            if state_data:
                state = json.loads(state_data)

                # Restore positions
                for sym, pos_data in state.get('positions', {}).items():
                    self.positions[sym] = QuickScalperPosition.from_dict(pos_data)

                # Restore cooldowns
                for sym, ts in state.get('last_trade_time', {}).items():
                    self.last_trade_time[sym] = datetime.fromisoformat(ts)

                # Restore stats
                self.stats = state.get('stats', self.stats)

                print(f"  Loaded state: {len(self.positions)} active positions")
        except Exception as e:
            print(f"  Failed to load state: {e}")

    def _save_state(self):
        """Save state to Redis"""
        try:
            state = {
                'positions': {s: p.to_dict() for s, p in self.positions.items()},
                'last_trade_time': {s: t.isoformat() for s, t in self.last_trade_time.items()},
                'stats': self.stats,
                'updated_at': datetime.now().isoformat()
            }
            self.redis.set('quick_scalper:state', json.dumps(state))
        except Exception as e:
            print(f"  Failed to save state: {e}")

    def calculate_rsi(self, symbol: str) -> Optional[float]:
        """Calculate RSI for symbol"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(
                symbol,
                QuickScalperConfig.TIMEFRAME,
                limit=QuickScalperConfig.RSI_PERIOD + 10
            )

            if len(ohlcv) < QuickScalperConfig.RSI_PERIOD + 1:
                return None

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # Calculate RSI
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=QuickScalperConfig.RSI_PERIOD).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=QuickScalperConfig.RSI_PERIOD).mean()

            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            return rsi.iloc[-1]
        except Exception as e:
            print(f"  RSI calculation error for {symbol}: {e}")
            return None

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for symbol"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return ticker['last']
        except Exception as e:
            print(f"  Price fetch error for {symbol}: {e}")
            return None

    def check_cooldown(self, symbol: str) -> bool:
        """Check if symbol is in cooldown"""
        if symbol not in self.last_trade_time:
            return False

        elapsed = (datetime.now() - self.last_trade_time[symbol]).total_seconds()
        return elapsed < QuickScalperConfig.COOLDOWN_SECONDS

    def open_position(self, symbol: str, side: str, price: float) -> bool:
        """Open a scalp position"""
        try:
            # Calculate position size in contracts
            amount = QuickScalperConfig.POSITION_SIZE_USD / price

            # Set leverage
            self.exchange.set_leverage(QuickScalperConfig.LEVERAGE, symbol)

            # Create market order
            order_side = 'buy' if side == 'long' else 'sell'
            order = self.exchange.create_market_order(
                symbol,
                order_side,
                amount,
                params={'posSide': 'long' if side == 'long' else 'short'}
            )

            # Create position object
            pos = QuickScalperPosition(
                symbol=symbol,
                side=side,
                entry_price=price,
                size=amount,
                entry_time=datetime.now()
            )

            self.positions[symbol] = pos
            self.last_trade_time[symbol] = datetime.now()
            self._save_state()

            print(f"  SCALP OPEN: {side.upper()} {symbol} @ ${price:.4f}")
            print(f"    TP: ${pos.take_profit:.4f} (+{QuickScalperConfig.TAKE_PROFIT_PCT}%)")
            print(f"    SL: ${pos.stop_loss:.4f} (-{QuickScalperConfig.STOP_LOSS_PCT}%)")

            return True
        except Exception as e:
            print(f"  Failed to open {side} on {symbol}: {e}")
            return False

    def close_position(self, symbol: str, reason: str) -> bool:
        """Close a scalp position"""
        try:
            pos = self.positions.get(symbol)
            if not pos:
                return False

            current_price = self.get_current_price(symbol)
            if not current_price:
                return False

            # Close the position
            close_side = 'sell' if pos.side == 'long' else 'buy'
            order = self.exchange.create_market_order(
                symbol,
                close_side,
                pos.size,
                params={
                    'posSide': 'long' if pos.side == 'long' else 'short',
                    'reduceOnly': True
                }
            )

            # Calculate P&L
            if pos.side == 'long':
                pnl_pct = (current_price - pos.entry_price) / pos.entry_price * 100
            else:
                pnl_pct = (pos.entry_price - current_price) / pos.entry_price * 100

            pnl_usd = pnl_pct / 100 * QuickScalperConfig.POSITION_SIZE_USD * QuickScalperConfig.LEVERAGE
            hold_time = (datetime.now() - pos.entry_time).total_seconds() / 60

            # Update stats
            self.stats['total_trades'] += 1
            self.stats['total_pnl'] += pnl_usd
            if pnl_usd > 0:
                self.stats['wins'] += 1
            else:
                self.stats['losses'] += 1

            # Update average hold time
            n = self.stats['total_trades']
            self.stats['avg_hold_time'] = (self.stats['avg_hold_time'] * (n-1) + hold_time) / n

            # Remove position
            del self.positions[symbol]
            self.last_trade_time[symbol] = datetime.now()
            self._save_state()

            win_rate = self.stats['wins'] / self.stats['total_trades'] * 100 if self.stats['total_trades'] > 0 else 0

            print(f"  SCALP CLOSE [{reason.upper()}]: {pos.side.upper()} {symbol}")
            print(f"    Entry: ${pos.entry_price:.4f} -> Exit: ${current_price:.4f}")
            print(f"    P&L: {pnl_pct:+.2f}% (${pnl_usd:+.2f})")
            print(f"    Hold time: {hold_time:.1f} min")
            print(f"    Stats: {self.stats['wins']}W/{self.stats['losses']}L ({win_rate:.1f}%), Total P&L: ${self.stats['total_pnl']:.2f}")

            return True
        except Exception as e:
            print(f"  Failed to close {symbol}: {e}")
            return False

    def increment_candle_counts(self):
        """Increment candle count for all positions (called every candle)"""
        for symbol, pos in self.positions.items():
            pos.candle_count += 1
        self._save_state()

    def scan_for_entries(self):
        """Scan for entry opportunities"""
        for symbol in QuickScalperConfig.SCALP_SYMBOLS:
            # Skip if already in position
            if symbol in self.positions:
                continue

            # Skip if in cooldown
            if self.check_cooldown(symbol):
                continue

            # Skip if max concurrent reached
            if len(self.positions) >= QuickScalperConfig.MAX_CONCURRENT_SCALPS:
                continue

            # Get RSI
            rsi = self.calculate_rsi(symbol)
            if rsi is None:
                continue

            # Get current price
            price = self.get_current_price(symbol)
            if price is None:
                continue

            # Check for entry signals
            if rsi < QuickScalperConfig.RSI_OVERSOLD:
                print(f"\n[SCALP] {symbol}: RSI={rsi:.1f} < {QuickScalperConfig.RSI_OVERSOLD} -> LONG SIGNAL")
                self.open_position(symbol, 'long', price)
            elif rsi > QuickScalperConfig.RSI_OVERBOUGHT:
                print(f"\n[SCALP] {symbol}: RSI={rsi:.1f} > {QuickScalperConfig.RSI_OVERBOUGHT} -> SHORT SIGNAL")
                self.open_position(symbol, 'short', price)

    def manage_positions(self):
        """Manage existing positions"""
        for symbol in list(self.positions.keys()):
            pos = self.positions[symbol]

            # Get current price
            price = self.get_current_price(symbol)
            if price is None:
                continue

            # Check exit conditions
            should_exit, reason = pos.check_exit(price)
            if should_exit:
                self.close_position(symbol, reason)

    def run_cycle(self):
        """Run one cycle of the scalper"""
        try:
            # Check and manage existing positions first
            self.manage_positions()

            # Scan for new entries
            self.scan_for_entries()

        except Exception as e:
            print(f"Cycle error: {e}")

    def run(self):
        """Main loop"""
        print(f"\n{'='*60}")
        print(f"QuickScalper V1.0.0 Starting")
        print(f"{'='*60}")

        last_candle_time = None
        cycle_interval = 30  # Check every 30 seconds

        while True:
            try:
                now = datetime.now()

                # Check if new candle started
                current_candle = now.minute // QuickScalperConfig.CANDLE_MINUTES
                if last_candle_time is None or current_candle != last_candle_time:
                    self.increment_candle_counts()
                    last_candle_time = current_candle

                # Run cycle
                self.run_cycle()

                # Status update
                if self.positions:
                    print(f"\n[{now.strftime('%H:%M:%S')}] Active scalps: {list(self.positions.keys())}")

                time.sleep(cycle_interval)

            except KeyboardInterrupt:
                print("\nShutting down QuickScalper...")
                self._save_state()
                break
            except Exception as e:
                print(f"Main loop error: {e}")
                time.sleep(10)


def main():
    """Entry point"""
    scalper = QuickScalper()
    scalper.run()


if __name__ == '__main__':
    main()
