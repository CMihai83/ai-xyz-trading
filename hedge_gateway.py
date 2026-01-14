#!/usr/bin/env python3
"""
Hedge Gateway - Automatic Hedge Position Management
====================================================

Opens hedge positions automatically and closes them at averaging step gates.
Uses reversion detection to close immediately if profit reverts to gate level.

Strategy (Grok+Claude consortium optimized - Jan 2026):
- When LONG opens → auto-open SHORT hedge (same size)
- When SHORT opens → auto-open LONG hedge (same size)
- At averaging step 2: Open gate, close 25% of hedge
- At averaging step 4: Open gate, close 25% of hedge (NEW mid-range protection)
- At averaging step 5: Close remaining 50% of hedge
- If hedge reverts to gate level: Close immediately (cut losses on hedge)
- If hedge hits 85% of peak profit: Surplus dump (was 70% - too aggressive)

Gate Logic:
- Gate opens when main position hits averaging step 2, 4, or 5
- Tracks peak profit of hedge while gate is open
- Reversion = hedge profit drops back to gate level (with 10% buffer, was 5%)
- Surplus dump = hedge profit drops to 85% of peak (was 70%)

FIXES (Jan 2026 Consortium Review):
- CRITICAL: Use actual leverage instead of hardcoded 10x in profit calc
- CRITICAL: Validate entry price to prevent division by zero
- HIGH: Added step 4 gate for mid-range protection
- HIGH: Increased surplus dump from 70% to 85%
- HIGH: Cleanup hedges from dict when remaining=0
- HIGH: Added JSON file fallback if Redis fails
- MEDIUM: Increased reversion buffer from 5% to 10%

Author: Claude + Grok Consortium
Version: 2.3.0 (Profit-Only Hedging)

V2.3.0 Changes (Jan 14, 2026):
- DISABLED immediate hedge opening on position open
- Hedges now only open when main position is profitable
- Added IMMEDIATE_HEDGE_ENABLED flag (default: False)
- Added PROFIT_HEDGE_ONLY flag (default: True)
- Reduces drag on winning positions that don't need protection

V1.2.5 Changes (Jan 14, 2026):
- Added main_drop delay (30 min) to prevent premature exits during dead cat bounces
- Added stop_loss delay (30 min) to prevent premature stop losses during bounces
- DISABLED profit_taking and trailing_stop delays (caused regressions)
- Stress test results: 50% win rate, +11.4% overall improvement

V1.2.3 Changes (Jan 14, 2026):
- Added ultra-low volatility hedge disable (ATR% < 0.5% blocks all hedging)
- Disabled bounce detection (caused regressions)
"""

import time
from datetime import datetime
from typing import Dict, Optional, Tuple
import json
import os
import redis


class HedgeGateway:
    """
    Manages automatic hedge positions with gate-based closing.

    Designed to work with the AI-XYZ trading system.
    """

    # Configuration (Grok+Claude consortium optimized - Jan 2026)
    # V2.3.0: Delayed hedge opening - only open when main is profitable
    IMMEDIATE_HEDGE_ENABLED = False  # DISABLED: Don't open hedge immediately on position open
    PROFIT_HEDGE_ONLY = True         # Only open hedges when main position is profitable

    GATE_OPEN_STEPS = [2, 4, 5]  # Averaging steps that open gates (added step 4 for mid-range protection)
    CLOSE_AT_STEP_2 = 0.25   # Close 25% of hedge at step 2 (was 30%)
    CLOSE_AT_STEP_4 = 0.25   # Close 25% of hedge at step 4 (NEW)
    CLOSE_AT_STEP_5 = 0.50   # Close 50% (remaining) at step 5 (was 70%)
    GATE_BUFFER_PCT = 10.0   # 10% buffer for reversion detection (was 5% - too tight)
    SURPLUS_DUMP_PCT = 0.85  # Close at 85% of peak profit (was 70% - too aggressive)

    # Profit Protection Hedge Configuration (Grok consortium - Jan 14, 2026)
    # BACKTEST VALIDATED: Original config is optimal (+41.5% vs Traditional)
    # Opens hedge at 70% of peak to secure profits instead of closing position
    #
    # BACKTEST RESULTS (200 trades across 5 symbols):
    # - Original ($5 min, 50%, 10%, -5%): $291.98 PnL, 2% stop rate ✅ BEST
    # - $3 threshold configs: ~$200 PnL, 12% stop rate (too many stops)
    # - Traditional close: $206.33 PnL (baseline)
    #
    # STRESS TEST IMPROVEMENTS (Jan 14, 2026):
    # - Added momentum filter to avoid hedging during oversold bounces
    # - Added trailing stop for faster exit on V-shape recoveries
    # - Weak scenarios: low_volatility (-19%), dead_cat_bounce (-14%), v_shape (-5%)
    #
    # KEY INSIGHT: $5 threshold filters weak trends, preventing stop losses
    PROFIT_PROTECTION_HEDGE_SIZE = 0.50  # 50% of main position (Grok original)
    PROFIT_HEDGE_PROFIT_GATE = 0.10      # Close hedge at 10% profit
    PROFIT_HEDGE_MAIN_DROP_GATE = 0.50   # Close hedge if main drops to 50% of peak
    PROFIT_HEDGE_STOP_LOSS = -0.05       # Stop loss at -5% on profit hedge
    MIN_PROFIT_FOR_HEDGE = 5.00          # Minimum $5 UPNL (backtest validated)

    # Stress Test Improvements - Momentum Filter & Trailing Stop
    MOMENTUM_RSI_OVERSOLD = 30           # Don't hedge if RSI < 30 (bounce likely)
    MOMENTUM_RSI_OVERBOUGHT = 70         # Don't hedge if RSI > 70 (for shorts)
    TRAILING_STOP_ACTIVATION = 0.03      # Activate trailing stop at 3% profit
    TRAILING_STOP_DISTANCE = 0.02        # Trail 2% behind peak profit
    MOMENTUM_LOOKBACK = 14               # RSI period

    # V1.2.2: Volatility Spike Detector with ATR Regime Filter
    # Detects sudden volatility spikes to trigger emergency hedge actions
    # FIX V1.2.1: Increased threshold and widened stops to reduce false positives in high vol
    # FIX V1.2.2: Added ATR regime filter to disable spike mode in low volatility environments
    ATR_FAST_PERIOD = 5                  # Fast ATR for current volatility
    ATR_SLOW_PERIOD = 20                 # Slow ATR for baseline volatility
    VOLATILITY_SPIKE_MULTIPLIER = 2.5   # Spike threshold (was 2.0 - too sensitive)
    VOLATILITY_SPIKE_HEDGE_SIZE = 0.60  # Hedge size during spikes (was 0.75 - too large)
    VOLATILITY_SPIKE_MIN_PROFIT = 2.00  # Lower threshold ($2) during spikes for faster protection
    FAST_STOP_LOSS_ATR_MULT = 2.0       # Fast stop at 2.0x ATR (was 1.5 - too tight)
    SPIKE_CONFIRMATION_COUNT = 2        # Require 2 consecutive spike readings to confirm

    # V1.2.2: ATR Regime Filter - disable spike mode when baseline volatility is too low
    # This fixes low_volatility (-12.4%) and dead_cat_bounce (-12.0%) regressions
    # by preventing false spike triggers in calm market conditions
    MIN_BASELINE_ATR_PCT = 0.005        # Minimum baseline ATR as % of price (0.5%)
    ATR_REGIME_ENABLED = True            # Enable/disable regime filter

    # V1.2.3: Ultra-Low Volatility Hedge Disable
    # Completely disable hedging when volatility is extremely low (not profitable)
    # Fixes low_volatility scenario where small profits get eaten by hedge overhead
    # TUNED: Increased from 0.3% to 0.5% to better filter low volatility scenarios
    ULTRA_LOW_VOL_ATR_PCT = 0.005       # Disable hedging entirely below 0.5% ATR (was 0.3%)
    ULTRA_LOW_VOL_ENABLED = True         # Enable/disable ultra-low vol filter

    # V1.2.3: Bounce Detection - delay hedging during price bounces
    # DISABLED: Bounce detection caused more regressions than fixes (-84.7% in high_volatility)
    # The prior drop requirement interferes with legitimate hedging scenarios
    BOUNCE_DETECTION_ENABLED = False     # DISABLED - caused regressions
    BOUNCE_LOOKBACK_PERIODS = 20         # Look back 20 periods for bounce detection (was 10)
    BOUNCE_THRESHOLD_PCT = 0.03          # 3% bounce from recent low triggers detection
    BOUNCE_CONFIRMATION_PERIODS = 3      # Require 3 periods above bounce level to confirm
    BOUNCE_PRIOR_DROP_PCT = 0.05         # Require 5% prior drop before detecting bounce

    # V1.2.5: Gate Delays - prevent premature hedge exits during dead cat bounces
    # These delays allow the hedge to ride through temporary bounces before checking exit gates
    # Based on stress test results: 30 periods ≈ 30 minutes (1m candles)
    MAIN_DROP_DELAY_ENABLED = True       # Enable delay for main_drop gate (Gate 4)
    MAIN_DROP_DELAY_SECONDS = 1800       # 30 minutes delay before main_drop can trigger
    STOP_LOSS_DELAY_ENABLED = True       # Enable delay for stop_loss gate (Gate 5)
    STOP_LOSS_DELAY_SECONDS = 1800       # 30 minutes delay before stop_loss can trigger

    # V1.2.5: Profit Taking Delay - DISABLED (caused regressions in stress tests)
    # Testing showed profit taking delays caused -39.9% flash_crash regression
    PROFIT_TAKING_DELAY_ENABLED = False  # DISABLED - hurts flash_crash and black_swan_down
    PROFIT_TAKING_DELAY_SECONDS = 1800   # Not used when disabled

    # V1.2.5: Trailing Stop Delay - DISABLED (caused regressions in stress tests)
    TRAILING_STOP_DELAY_ENABLED = False  # DISABLED - caused overall -6.0% regression
    TRAILING_STOP_DELAY_SECONDS = 1800   # Not used when disabled

    def __init__(self, exchange, enabled: bool = True, leverage: int = 10):
        """
        Initialize HedgeGateway.

        Args:
            exchange: CCXT exchange instance
            enabled: Whether hedge gateway is active
            leverage: Leverage used for profit calculation (FIXED: was hardcoded 10x)
        """
        self.exchange = exchange
        self.enabled = enabled
        self.leverage = leverage  # FIXED: Store actual leverage for profit calc

        # Redis connection for persistence
        # CRITICAL: Use db=1 to match PositionPersistenceManager (not db=0!)
        # This ensures hedge state persists/restores correctly with position state
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.fallback_file = '/app/hedge_gateway_state.json'  # FIXED: JSON fallback if Redis fails

        try:
            self.redis = redis.Redis(host=redis_host, port=redis_port, db=1, decode_responses=True)
            self.redis.ping()
            print(f"  ✅ HedgeGateway connected to Redis db=1")
        except Exception as e:
            print(f"  ⚠️ HedgeGateway Redis connection failed: {e}")
            print(f"  📁 Using fallback file: {self.fallback_file}")
            self.redis = None

        # Track hedge positions: {main_position_key: hedge_info}
        self.hedges: Dict[str, Dict] = {}

        # Gate states: {main_position_key: gate_info}
        self.gates: Dict[str, Dict] = {}

        # Statistics
        self.stats = {
            'hedges_opened': 0,
            'hedges_closed': 0,
            'gate_opens': 0,
            'reversion_closes': 0,
            'surplus_dumps': 0,
            'total_hedge_pnl': 0.0,
            'momentum_filter_blocked': 0,  # Tracks blocked hedges by momentum
            'trailing_stop_closes': 0,      # Tracks trailing stop exits
            'volatility_spikes_detected': 0,  # V1.2.0: Volatility spike events
            'emergency_hedges_opened': 0,     # V1.2.0: Emergency hedges during spikes
            'fast_stop_triggers': 0,          # V1.2.0: Fast stop loss triggers
            'ultra_low_vol_blocked': 0,       # V1.2.3: Blocked by ultra-low volatility
            'bounce_detected_blocked': 0      # V1.2.3: Blocked by bounce detection
        }

        # Trailing stop state for profit protection hedges
        self.trailing_stops: Dict[str, Dict] = {}  # {hedge_key: {peak_profit_pct, activated}}

        # V1.2.0: Volatility spike state tracking
        self.volatility_state: Dict[str, Dict] = {}  # {symbol: {spike_active, atr_fast, atr_slow, detected_at}}

        # V1.2.3: Bounce detection state tracking
        self.bounce_state: Dict[str, Dict] = {}  # {symbol: {recent_low, bounce_start, periods_above}}

        # Load persisted state
        self._load_state()

        print(f"🛡️ HedgeGateway v2.0 initialized (enabled={enabled}, leverage={leverage}x)")
        print(f"   Gate steps: {self.GATE_OPEN_STEPS}")
        print(f"   Close at step 2: {self.CLOSE_AT_STEP_2*100}%")
        print(f"   Close at step 4: {self.CLOSE_AT_STEP_4*100}%")
        print(f"   Close at step 5: {self.CLOSE_AT_STEP_5*100}%")
        print(f"   Surplus dump: {self.SURPLUS_DUMP_PCT*100}% | Buffer: {self.GATE_BUFFER_PCT}%")
        if self.hedges:
            print(f"   📂 Restored {len(self.hedges)} hedges from state")

    def get_hedge_side(self, main_side: str) -> str:
        """Get opposite side for hedge."""
        if main_side.lower() in ['buy', 'long']:
            return 'sell'
        return 'buy'

    def get_position_side(self, side: str) -> str:
        """Convert order side to position side."""
        if side.lower() in ['buy', 'long']:
            return 'long'
        return 'short'

    def _save_state(self):
        """Persist hedge state to Redis (with JSON file fallback)."""
        state = {
            'hedges': self.hedges,
            'gates': self.gates,
            'stats': self.stats,
            'leverage': self.leverage,  # Store leverage in state
            'trailing_stops': self.trailing_stops,  # Trailing stop state for profit hedges
            'volatility_state': self.volatility_state  # V1.2.0: Volatility spike state
        }

        # Try Redis first
        if self.redis:
            try:
                self.redis.set('hedge_gateway:state', json.dumps(state))
                return  # Success, no fallback needed
            except Exception as e:
                print(f"  ⚠️ Redis save failed: {e}, using file fallback")

        # FIXED: Fallback to JSON file if Redis unavailable or failed
        try:
            with open(self.fallback_file, 'w') as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"  ❌ Failed to save hedge state (both Redis and file): {e}")

    def _load_state(self):
        """Load hedge state from Redis (with JSON file fallback)."""
        state = None

        # Try Redis first
        if self.redis:
            try:
                state_json = self.redis.get('hedge_gateway:state')
                if state_json:
                    state = json.loads(state_json)
            except Exception as e:
                print(f"  ⚠️ Redis load failed: {e}, trying file fallback")

        # FIXED: Fallback to JSON file if Redis unavailable or empty
        if state is None:
            try:
                if os.path.exists(self.fallback_file):
                    with open(self.fallback_file, 'r') as f:
                        state = json.load(f)
                    print(f"  📁 Loaded hedge state from fallback file")
            except Exception as e:
                print(f"  ⚠️ Failed to load hedge state from file: {e}")

        # Apply loaded state
        if state:
            self.hedges = state.get('hedges', {})
            self.gates = state.get('gates', {})
            self.stats = state.get('stats', self.stats)
            self.trailing_stops = state.get('trailing_stops', {})
            self.volatility_state = state.get('volatility_state', {})
            # Restore leverage if saved
            if 'leverage' in state:
                self.leverage = state['leverage']

    def open_hedge(self, symbol: str, main_side: str, size: float,
                   main_position_key: str, leverage: int = 10) -> Optional[Dict]:
        """
        Open a hedge position when main position opens.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')
            main_side: Side of main position ('buy'/'sell')
            size: Position size to hedge
            main_position_key: Key to track this hedge against
            leverage: Leverage to use

        Returns:
            Order result or None if failed
        """
        if not self.enabled:
            return None

        # V2.3.0: Check if immediate hedging is disabled
        if not self.IMMEDIATE_HEDGE_ENABLED:
            print(f"  ℹ️ Immediate hedge disabled - will open when profitable (PROFIT_HEDGE_ONLY={self.PROFIT_HEDGE_ONLY})")
            return None

        # Don't double hedge
        if main_position_key in self.hedges:
            print(f"  ⚠️ Hedge already exists for {main_position_key}")
            return None

        hedge_side = self.get_hedge_side(main_side)
        hedge_position_side = self.get_position_side(hedge_side)

        try:
            # Prepare hedge order params for hedge mode
            params = {
                'marginCoin': 'USDT',
                'tradeSide': 'open',
                'holdSide': hedge_position_side
            }

            print(f"  🛡️ Opening hedge: {symbol} {hedge_side.upper()} {size}")
            order = self.exchange.create_market_order(symbol, hedge_side, size, params=params)

            if order:
                # Get entry price with multiple fallbacks
                entry_price = order.get('average') or order.get('price') or order.get('info', {}).get('priceAvg') or 0
                entry_price = float(entry_price) if entry_price else 0.0

                # FIXED: Validate entry price to prevent division by zero in profit calc
                if entry_price <= 0:
                    print(f"  ⚠️ Invalid hedge entry price: {entry_price}, attempting ticker fetch")
                    try:
                        ticker = self.exchange.fetch_ticker(symbol)
                        entry_price = float(ticker.get('last', 0))
                        print(f"  ✅ Got entry price from ticker: {entry_price}")
                    except Exception as e:
                        print(f"  ❌ Could not get valid entry price: {e}")
                        return None

                self.hedges[main_position_key] = {
                    'symbol': symbol,
                    'side': hedge_side,
                    'position_side': hedge_position_side,
                    'position_type': 'hedge',  # EXPLICIT: Distinguishes from main positions
                    'entry_price': entry_price,
                    'size': size,
                    'remaining': 1.0,  # 100% of hedge remaining
                    'opened_at': datetime.now().isoformat(),
                    'order_id': order.get('id')
                }
                self.stats['hedges_opened'] += 1
                self._save_state()
                print(f"  ✅ Hedge opened: {symbol} {hedge_side.upper()} @ {self.hedges[main_position_key]['entry_price']}")
                return order

        except Exception as e:
            print(f"  ❌ Failed to open hedge: {e}")

        return None

    def open_gate(self, main_position_key: str, averaging_step: int,
                  current_hedge_profit: float) -> bool:
        """
        Open a gate when averaging step is reached.

        Args:
            main_position_key: Key of the main position
            averaging_step: Current averaging step (1-5)
            current_hedge_profit: Current hedge P&L in USD

        Returns:
            True if gate was opened
        """
        if not self.enabled:
            return False

        if main_position_key not in self.hedges:
            return False

        if averaging_step not in self.GATE_OPEN_STEPS:
            return False

        # Don't re-open gate if already open for this step
        if main_position_key in self.gates:
            existing_gate = self.gates[main_position_key]
            if existing_gate.get('step') == averaging_step:
                return False

        self.gates[main_position_key] = {
            'step': averaging_step,
            'gate_level': current_hedge_profit,
            'peak_profit': current_hedge_profit,
            'opened_at': datetime.now().isoformat(),
            'partial_closed': False
        }

        self.stats['gate_opens'] += 1
        self._save_state()
        print(f"  🚪 Gate opened at step {averaging_step}: profit=${current_hedge_profit:.2f}")

        return True

    def calculate_hedge_profit(self, main_position_key: str,
                               current_price: float) -> Optional[float]:
        """
        Calculate current hedge P&L.

        Args:
            main_position_key: Key of the main position
            current_price: Current market price

        Returns:
            Hedge profit in USD or None
        """
        if main_position_key not in self.hedges:
            return None

        hedge = self.hedges[main_position_key]
        entry = hedge['entry_price']
        size = hedge['size'] * hedge['remaining']

        if size <= 0:
            return 0.0

        if hedge['position_side'] == 'short':
            # Short profits when price goes down
            pnl_pct = (entry - current_price) / entry
        else:
            # Long profits when price goes up
            pnl_pct = (current_price - entry) / entry

        # FIXED: Use actual leverage instead of hardcoded 10x
        return size * pnl_pct * self.leverage

    def calculate_rsi(self, symbol: str, period: int = 14) -> Optional[float]:
        """
        Calculate RSI (Relative Strength Index) for a symbol.

        Args:
            symbol: Trading symbol
            period: RSI lookback period (default 14)

        Returns:
            RSI value (0-100) or None if calculation fails
        """
        try:
            # Fetch 1-hour candles for RSI calculation (more stable than 1m)
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=period + 1)
            if not ohlcv or len(ohlcv) < period + 1:
                return None

            # Extract closing prices
            closes = [candle[4] for candle in ohlcv]

            # Calculate price changes
            changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]

            # Separate gains and losses
            gains = [max(0, c) for c in changes]
            losses = [abs(min(0, c)) for c in changes]

            # Calculate average gain and loss
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period

            if avg_loss == 0:
                return 100.0  # All gains, no losses

            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))

            return rsi

        except Exception as e:
            print(f"  ⚠️ RSI calculation failed for {symbol}: {e}")
            return None

    def check_momentum_filter(self, symbol: str, main_side: str) -> Tuple[bool, str]:
        """
        Check if momentum conditions allow opening a profit protection hedge.

        Prevents hedging during oversold bounces (for longs) or overbought dips (for shorts).

        Args:
            symbol: Trading symbol
            main_side: Side of main position ('buy'/'sell')

        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        rsi = self.calculate_rsi(symbol, self.MOMENTUM_LOOKBACK)

        if rsi is None:
            # If RSI calc fails, allow hedge (be conservative)
            return (True, "rsi_unavailable")

        # For LONG main positions (hedge would be SHORT)
        # Don't open hedge if RSI is oversold - bounce likely
        if main_side.lower() in ['buy', 'long']:
            if rsi < self.MOMENTUM_RSI_OVERSOLD:
                self.stats['momentum_filter_blocked'] += 1
                return (False, f"rsi_oversold_{rsi:.1f}")
            return (True, f"rsi_ok_{rsi:.1f}")

        # For SHORT main positions (hedge would be LONG)
        # Don't open hedge if RSI is overbought - dip likely
        else:
            if rsi > self.MOMENTUM_RSI_OVERBOUGHT:
                self.stats['momentum_filter_blocked'] += 1
                return (False, f"rsi_overbought_{rsi:.1f}")
            return (True, f"rsi_ok_{rsi:.1f}")

    # ============================================================================
    # V1.2.0: VOLATILITY SPIKE DETECTOR (Grok recommendation)
    # ============================================================================
    # Detects sudden volatility spikes (flash crash, black swan events)
    # Uses ATR comparison: fast ATR vs slow ATR
    # When spike detected: use larger hedge size, lower profit threshold
    # ============================================================================

    def calculate_atr(self, symbol: str, period: int = 14) -> Optional[float]:
        """
        Calculate ATR (Average True Range) for a symbol.

        ATR measures market volatility by decomposing the entire range
        of an asset price for a given period.

        Args:
            symbol: Trading symbol
            period: ATR lookback period

        Returns:
            ATR value or None if calculation fails
        """
        try:
            # Fetch 1-hour candles for ATR calculation
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=period + 1)
            if not ohlcv or len(ohlcv) < period + 1:
                return None

            true_ranges = []
            for i in range(1, len(ohlcv)):
                high = ohlcv[i][2]
                low = ohlcv[i][3]
                prev_close = ohlcv[i-1][4]

                # True Range is max of:
                # 1. Current High - Current Low
                # 2. |Current High - Previous Close|
                # 3. |Current Low - Previous Close|
                tr = max(
                    high - low,
                    abs(high - prev_close),
                    abs(low - prev_close)
                )
                true_ranges.append(tr)

            # ATR is the average of true ranges
            atr = sum(true_ranges[-period:]) / period
            return atr

        except Exception as e:
            print(f"  ⚠️ ATR calculation failed for {symbol}: {e}")
            return None

    def detect_volatility_spike(self, symbol: str) -> Tuple[bool, Dict]:
        """
        Detect if there's a volatility spike (potential flash crash/black swan).

        V1.2.1 FIX: Now requires SPIKE_CONFIRMATION_COUNT consecutive spike readings
        to confirm a spike, reducing false positives in high volatility conditions.

        V1.2.2 FIX: Added ATR regime filter to disable spike mode when baseline
        volatility is too low (fixes low_volatility and dead_cat_bounce regressions).

        Compares fast ATR (5 periods) to slow ATR (20 periods).
        Spike detected when fast ATR > slow ATR * VOLATILITY_SPIKE_MULTIPLIER.

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (spike_detected: bool, spike_info: dict)
        """
        atr_fast = self.calculate_atr(symbol, self.ATR_FAST_PERIOD)
        atr_slow = self.calculate_atr(symbol, self.ATR_SLOW_PERIOD)

        if atr_fast is None or atr_slow is None:
            return (False, {"reason": "atr_unavailable"})

        if atr_slow == 0:
            return (False, {"reason": "atr_slow_zero"})

        # V1.2.2: ATR Regime Filter - check if baseline volatility is sufficient
        # Get current price for ATR percentage calculation
        regime_blocked = False
        atr_pct = 0.0
        try:
            if self.ATR_REGIME_ENABLED:
                ticker = self.exchange.fetch_ticker(symbol)
                current_price = ticker.get('last', 0) or ticker.get('close', 0)
                if current_price > 0:
                    # Calculate ATR as percentage of price
                    atr_pct = atr_slow / current_price
                    if atr_pct < self.MIN_BASELINE_ATR_PCT:
                        # Baseline volatility too low - disable spike mode
                        regime_blocked = True
        except Exception as e:
            # If we can't get price, don't block (fail open)
            pass

        # Calculate spike ratio
        spike_ratio = atr_fast / atr_slow
        ratio_exceeds_threshold = spike_ratio >= self.VOLATILITY_SPIKE_MULTIPLIER

        # V1.2.1: Spike confirmation logic - require consecutive readings
        # Initialize state if needed
        if symbol not in self.volatility_state:
            self.volatility_state[symbol] = {
                "spike_active": False,
                "consecutive_count": 0,
                "atr_fast": 0,
                "atr_slow": 0,
                "spike_ratio": 0,
                "detected_at": None,
                "regime_blocked": False,
                "atr_pct": 0
            }

        state = self.volatility_state[symbol]

        # Update consecutive count (only if not regime blocked)
        if ratio_exceeds_threshold and not regime_blocked:
            state["consecutive_count"] = state.get("consecutive_count", 0) + 1
        else:
            state["consecutive_count"] = 0  # Reset on non-spike reading or regime block

        # Only confirm spike if we have enough consecutive readings AND not regime blocked
        spike_confirmed = (state["consecutive_count"] >= self.SPIKE_CONFIRMATION_COUNT) and not regime_blocked

        spike_info = {
            "atr_fast": atr_fast,
            "atr_slow": atr_slow,
            "spike_ratio": spike_ratio,
            "threshold": self.VOLATILITY_SPIKE_MULTIPLIER,
            "consecutive_count": state["consecutive_count"],
            "confirmation_required": self.SPIKE_CONFIRMATION_COUNT,
            "spike_detected": spike_confirmed,
            "regime_blocked": regime_blocked,
            "atr_pct": atr_pct,
            "min_atr_pct": self.MIN_BASELINE_ATR_PCT
        }

        # Update volatility state for this symbol
        state["spike_active"] = spike_confirmed
        state["atr_fast"] = atr_fast
        state["atr_slow"] = atr_slow
        state["spike_ratio"] = spike_ratio
        state["regime_blocked"] = regime_blocked
        state["atr_pct"] = atr_pct
        if spike_confirmed and state.get("detected_at") is None:
            state["detected_at"] = datetime.now().isoformat()
        elif not spike_confirmed:
            state["detected_at"] = None

        if spike_confirmed and state["consecutive_count"] == self.SPIKE_CONFIRMATION_COUNT:
            # Only print on first confirmation
            self.stats['volatility_spikes_detected'] += 1
            print(f"\n  ⚡ VOLATILITY SPIKE CONFIRMED for {symbol}!")
            print(f"     ATR Fast: {atr_fast:.6f} | ATR Slow: {atr_slow:.6f}")
            print(f"     Spike Ratio: {spike_ratio:.2f}x (threshold: {self.VOLATILITY_SPIKE_MULTIPLIER}x)")
            print(f"     ATR%: {atr_pct*100:.3f}% (min: {self.MIN_BASELINE_ATR_PCT*100:.1f}%)")
            print(f"     Consecutive readings: {state['consecutive_count']}/{self.SPIKE_CONFIRMATION_COUNT}")
            self._save_state()
        elif regime_blocked and ratio_exceeds_threshold:
            # Log when regime filter blocks a would-be spike (once per symbol per session)
            if not state.get("regime_block_logged"):
                print(f"\n  🛡️ REGIME FILTER: Spike blocked for {symbol} (low baseline vol)")
                print(f"     ATR%: {atr_pct*100:.3f}% < min {self.MIN_BASELINE_ATR_PCT*100:.1f}%")
                state["regime_block_logged"] = True

        return (spike_confirmed, spike_info)

    def is_ultra_low_volatility(self, symbol: str) -> Tuple[bool, float]:
        """
        V1.2.3: Check if volatility is ultra-low (disable hedging entirely).

        Unlike the regime filter which only blocks spike mode, this completely
        disables hedging when volatility is so low that hedging isn't profitable.

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (is_ultra_low: bool, atr_pct: float)
        """
        if not self.ULTRA_LOW_VOL_ENABLED:
            return (False, 0.0)

        atr_slow = self.calculate_atr(symbol, self.ATR_SLOW_PERIOD)
        if atr_slow is None:
            return (False, 0.0)

        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker.get('last', 0) or ticker.get('close', 0)
            if current_price > 0:
                atr_pct = atr_slow / current_price
                is_ultra_low = atr_pct < self.ULTRA_LOW_VOL_ATR_PCT

                if is_ultra_low:
                    # Log first occurrence per symbol
                    if symbol not in self.volatility_state:
                        self.volatility_state[symbol] = {}
                    if not self.volatility_state[symbol].get("ultra_low_logged"):
                        print(f"\n  🔇 ULTRA-LOW VOLATILITY: Hedging disabled for {symbol}")
                        print(f"     ATR%: {atr_pct*100:.4f}% < threshold {self.ULTRA_LOW_VOL_ATR_PCT*100:.1f}%")
                        self.volatility_state[symbol]["ultra_low_logged"] = True
                        self.stats['ultra_low_vol_blocked'] += 1

                return (is_ultra_low, atr_pct)
        except Exception as e:
            pass

        return (False, 0.0)

    def detect_bounce(self, symbol: str) -> Tuple[bool, Dict]:
        """
        V1.2.3: Detect if price is bouncing from a recent low.

        Bounces are dangerous for hedging because:
        - Dead cat bounce: Price bounces briefly then continues down
        - V-shape recovery: Price drops then rapidly recovers

        During a bounce, the hedge (short) will hit stop loss while main profits.

        TUNED: Now requires a prior drop (BOUNCE_PRIOR_DROP_PCT) before detecting bounce.
        This prevents false triggers in sideways/low-volatility markets.

        Detection logic:
        1. Check for prior significant drop (BOUNCE_PRIOR_DROP_PCT)
        2. Track recent low price over BOUNCE_LOOKBACK_PERIODS
        3. If current price > recent_low * (1 + BOUNCE_THRESHOLD_PCT), bounce detected
        4. Require BOUNCE_CONFIRMATION_PERIODS above bounce level to confirm

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (bounce_detected: bool, bounce_info: dict)
        """
        if not self.BOUNCE_DETECTION_ENABLED:
            return (False, {"reason": "disabled"})

        try:
            # Fetch recent OHLCV data
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1m', limit=self.BOUNCE_LOOKBACK_PERIODS + 5)
            if not ohlcv or len(ohlcv) < self.BOUNCE_LOOKBACK_PERIODS:
                return (False, {"reason": "insufficient_data"})

            # Get recent highs and lows
            recent_candles = ohlcv[-self.BOUNCE_LOOKBACK_PERIODS:]
            recent_highs = [candle[2] for candle in recent_candles]  # High prices
            recent_lows = [candle[3] for candle in recent_candles]   # Low prices
            recent_high = max(recent_highs)
            recent_low = min(recent_lows)
            current_price = ohlcv[-1][4]  # Current close

            # V1.2.3 FIX: First check if there was a prior significant drop
            drop_from_high = (recent_high - recent_low) / recent_high if recent_high > 0 else 0
            had_prior_drop = drop_from_high >= self.BOUNCE_PRIOR_DROP_PCT

            # Initialize bounce state for symbol
            if symbol not in self.bounce_state:
                self.bounce_state[symbol] = {
                    "recent_low": recent_low,
                    "bounce_start_price": None,
                    "periods_above": 0,
                    "bounce_active": False
                }

            state = self.bounce_state[symbol]

            # If no prior drop, reset state and return
            if not had_prior_drop:
                state["periods_above"] = 0
                state["bounce_start_price"] = None
                state["bounce_active"] = False
                return (False, {
                    "reason": "no_prior_drop",
                    "drop_pct": drop_from_high * 100,
                    "required_drop_pct": self.BOUNCE_PRIOR_DROP_PCT * 100
                })

            # Calculate bounce threshold
            bounce_level = recent_low * (1 + self.BOUNCE_THRESHOLD_PCT)

            # Check if price is above bounce level
            if current_price > bounce_level:
                state["periods_above"] = state.get("periods_above", 0) + 1
                if state["bounce_start_price"] is None:
                    state["bounce_start_price"] = current_price
            else:
                # Reset if price drops back below bounce level
                state["periods_above"] = 0
                state["bounce_start_price"] = None

            # Confirm bounce if enough periods above bounce level
            bounce_confirmed = state["periods_above"] >= self.BOUNCE_CONFIRMATION_PERIODS

            bounce_info = {
                "recent_high": recent_high,
                "recent_low": recent_low,
                "current_price": current_price,
                "bounce_level": bounce_level,
                "prior_drop_pct": drop_from_high * 100,
                "bounce_pct": (current_price - recent_low) / recent_low * 100 if recent_low > 0 else 0,
                "periods_above": state["periods_above"],
                "confirmation_required": self.BOUNCE_CONFIRMATION_PERIODS,
                "bounce_detected": bounce_confirmed
            }

            # Update state
            state["recent_low"] = recent_low
            state["bounce_active"] = bounce_confirmed

            if bounce_confirmed and not state.get("bounce_logged"):
                print(f"\n  🔄 BOUNCE DETECTED for {symbol}!")
                print(f"     Prior drop: {drop_from_high*100:.2f}% (required: {self.BOUNCE_PRIOR_DROP_PCT*100:.1f}%)")
                print(f"     Recent low: ${recent_low:.4f} | Current: ${current_price:.4f}")
                print(f"     Bounce: {bounce_info['bounce_pct']:.2f}% (threshold: {self.BOUNCE_THRESHOLD_PCT*100:.1f}%)")
                print(f"     Periods above: {state['periods_above']}/{self.BOUNCE_CONFIRMATION_PERIODS}")
                state["bounce_logged"] = True
                self.stats['bounce_detected_blocked'] += 1
            elif not bounce_confirmed:
                state["bounce_logged"] = False

            return (bounce_confirmed, bounce_info)

        except Exception as e:
            return (False, {"reason": f"error: {str(e)}"})

    def should_block_hedge(self, symbol: str) -> Tuple[bool, str]:
        """
        V1.2.3: Master check for hedge blocking conditions.

        Combines all blocking conditions:
        1. Ultra-low volatility (disable hedging entirely)
        2. Bounce detection (delay hedging during bounces)

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (should_block: bool, reason: str)
        """
        # Check ultra-low volatility first
        is_ultra_low, atr_pct = self.is_ultra_low_volatility(symbol)
        if is_ultra_low:
            return (True, f"ultra_low_vol (ATR%={atr_pct*100:.4f}%)")

        # Check bounce detection
        bounce_detected, bounce_info = self.detect_bounce(symbol)
        if bounce_detected:
            return (True, f"bounce_detected ({bounce_info.get('bounce_pct', 0):.1f}% from low)")

        return (False, "")

    def get_adjusted_hedge_params(self, symbol: str, main_peak_upnl: float) -> Dict:
        """
        Get hedge parameters adjusted for current volatility conditions.

        During volatility spikes:
        - Use larger hedge size (75% instead of 50%)
        - Use lower profit threshold ($2 instead of $5)
        - Enable fast stop loss based on ATR

        Args:
            symbol: Trading symbol
            main_peak_upnl: Peak UPNL of main position

        Returns:
            Dict with adjusted parameters
        """
        # Check for volatility spike
        spike_detected, spike_info = self.detect_volatility_spike(symbol)

        if spike_detected:
            # Emergency mode: more aggressive protection
            return {
                "hedge_size_pct": self.VOLATILITY_SPIKE_HEDGE_SIZE,  # 75%
                "min_profit_threshold": self.VOLATILITY_SPIKE_MIN_PROFIT,  # $2
                "use_fast_stop": True,
                "fast_stop_atr_mult": self.FAST_STOP_LOSS_ATR_MULT,  # 1.5x ATR
                "atr_value": spike_info.get("atr_fast", 0),
                "spike_mode": True,
                "spike_ratio": spike_info.get("spike_ratio", 0)
            }
        else:
            # Normal mode: standard parameters
            return {
                "hedge_size_pct": self.PROFIT_PROTECTION_HEDGE_SIZE,  # 50%
                "min_profit_threshold": self.MIN_PROFIT_FOR_HEDGE,  # $5
                "use_fast_stop": False,
                "fast_stop_atr_mult": 0,
                "atr_value": spike_info.get("atr_fast", 0) if spike_info else 0,
                "spike_mode": False,
                "spike_ratio": spike_info.get("spike_ratio", 0) if spike_info else 0
            }

    def is_volatility_spike_active(self, symbol: str) -> bool:
        """Check if there's an active volatility spike for a symbol."""
        if symbol in self.volatility_state:
            return self.volatility_state[symbol].get("spike_active", False)
        return False

    def update_peak(self, main_position_key: str, current_hedge_profit: float):
        """Update peak profit tracking for gate."""
        if main_position_key not in self.gates:
            return

        gate = self.gates[main_position_key]
        if current_hedge_profit > gate['peak_profit']:
            gate['peak_profit'] = current_hedge_profit

    def should_close_on_reversion(self, main_position_key: str,
                                   current_hedge_profit: float) -> bool:
        """
        Check if hedge should close due to reversion to gate level.

        Args:
            main_position_key: Key of the main position
            current_hedge_profit: Current hedge P&L

        Returns:
            True if should close
        """
        if main_position_key not in self.gates:
            return False

        gate = self.gates[main_position_key]
        gate_level = gate['gate_level']

        # Reversion threshold (gate level minus buffer)
        buffer = abs(gate_level) * (self.GATE_BUFFER_PCT / 100)
        threshold = gate_level - buffer

        return current_hedge_profit <= threshold

    def should_surplus_dump(self, main_position_key: str,
                            current_hedge_profit: float) -> bool:
        """
        Check if hedge should close due to surplus dump (70% of peak).

        Args:
            main_position_key: Key of the main position
            current_hedge_profit: Current hedge P&L

        Returns:
            True if should close
        """
        if main_position_key not in self.gates:
            return False

        gate = self.gates[main_position_key]
        peak = gate['peak_profit']

        if peak <= 0:
            return False

        return current_hedge_profit <= peak * self.SURPLUS_DUMP_PCT

    def partial_close_hedge(self, main_position_key: str,
                            close_pct: float) -> Optional[Dict]:
        """
        Partially close hedge position.

        Args:
            main_position_key: Key of the main position
            close_pct: Percentage to close (0.0-1.0)

        Returns:
            Order result or None
        """
        if not self.enabled:
            return None

        if main_position_key not in self.hedges:
            return None

        hedge = self.hedges[main_position_key]

        if hedge['remaining'] <= 0:
            return None

        # FIX: Calculate close amount based on ORIGINAL size, not remaining
        # This fixes Zeno's paradox where remaining never reaches 0
        # Example: 30% at step 2 = 30% of original, 70% at step 5 = 70% of original
        close_amount = hedge['size'] * close_pct  # Based on original size

        # Clamp to actual remaining (can't close more than we have)
        actual_remaining_amount = hedge['size'] * hedge['remaining']
        if close_amount > actual_remaining_amount:
            close_amount = actual_remaining_amount
            close_pct = hedge['remaining']  # Adjust percentage to match

        if close_amount < 0.001:  # Minimum amount check
            print(f"  ⚠️ Close amount too small: {close_amount}")
            return None

        try:
            # Close side is same as hedge side in hedge mode
            close_side = hedge['side']
            position_side = hedge['position_side']

            params = {
                'marginCoin': 'USDT',
                'tradeSide': 'close',
                'holdSide': position_side
            }

            print(f"  🔻 Partial close hedge: {hedge['symbol']} {close_pct*100:.0f}% ({close_amount:.6f})")
            order = self.exchange.create_market_order(
                hedge['symbol'], close_side, close_amount, params=params
            )

            if order:
                # FIX: Track cumulative closed instead of fractional remaining
                # This ensures 25% + 25% + 50% = 100% (remaining = 0)
                cumulative_closed = hedge.get('cumulative_closed', 0) + close_pct
                hedge['cumulative_closed'] = min(1.0, cumulative_closed)
                hedge['remaining'] = max(0, 1.0 - hedge['cumulative_closed'])
                remaining_pct = hedge['remaining'] * 100  # Store before potential deletion

                realized_pnl = float(order.get('info', {}).get('realizedPnl', 0))
                self.stats['total_hedge_pnl'] += realized_pnl

                # FIXED: Cleanup hedge from dict when fully closed
                if hedge['remaining'] <= 0:
                    print(f"  🧹 Cleaning up fully closed hedge for {main_position_key}")
                    # Keep stats but remove from active tracking
                    del self.hedges[main_position_key]
                    if main_position_key in self.gates:
                        del self.gates[main_position_key]
                    self.stats['hedges_closed'] += 1

                self._save_state()
                print(f"  ✅ Partial close executed: realized=${realized_pnl:.2f}, remaining={remaining_pct:.1f}%")
                return order

        except Exception as e:
            print(f"  ❌ Failed partial close: {e}")

        return None

    def full_close_hedge(self, main_position_key: str,
                         reason: str = 'manual') -> Optional[Dict]:
        """
        Fully close remaining hedge position.

        Args:
            main_position_key: Key of the main position
            reason: Reason for closing

        Returns:
            Order result or None
        """
        if not self.enabled:
            return None

        if main_position_key not in self.hedges:
            return None

        hedge = self.hedges[main_position_key]

        if hedge['remaining'] <= 0:
            return None

        try:
            close_amount = hedge['size'] * hedge['remaining']
            close_side = hedge['side']
            position_side = hedge['position_side']

            params = {
                'marginCoin': 'USDT',
                'tradeSide': 'close',
                'holdSide': position_side
            }

            print(f"  🔻 Full close hedge ({reason}): {hedge['symbol']} {close_amount}")
            order = self.exchange.create_market_order(
                hedge['symbol'], close_side, close_amount, params=params
            )

            if order:
                realized_pnl = float(order.get('info', {}).get('realizedPnl', 0))
                self.stats['total_hedge_pnl'] += realized_pnl
                self.stats['hedges_closed'] += 1

                if reason == 'reversion':
                    self.stats['reversion_closes'] += 1
                elif reason == 'surplus_dump':
                    self.stats['surplus_dumps'] += 1

                # Clean up
                hedge['remaining'] = 0
                if main_position_key in self.gates:
                    del self.gates[main_position_key]

                self._save_state()
                print(f"  ✅ Hedge closed ({reason}): realized=${realized_pnl:.2f}")
                return order

        except Exception as e:
            print(f"  ❌ Failed to close hedge: {e}")

        return None

    def on_averaging_step(self, main_position_key: str, averaging_step: int,
                          current_price: float) -> None:
        """
        Called when main position takes an averaging step.

        Args:
            main_position_key: Key of the main position
            averaging_step: New averaging step (1-5)
            current_price: Current market price
        """
        if not self.enabled:
            return

        if main_position_key not in self.hedges:
            return

        hedge_profit = self.calculate_hedge_profit(main_position_key, current_price)
        if hedge_profit is None:
            return

        # Open gate at step 2 or 5
        if averaging_step in self.GATE_OPEN_STEPS:
            gate_opened = self.open_gate(main_position_key, averaging_step, hedge_profit)

            if gate_opened:
                # Partial close at gate open (consortium optimized: 25%/25%/50%)
                if averaging_step == 2:
                    self.partial_close_hedge(main_position_key, self.CLOSE_AT_STEP_2)
                elif averaging_step == 4:  # NEW: Mid-range protection
                    self.partial_close_hedge(main_position_key, self.CLOSE_AT_STEP_4)
                elif averaging_step == 5:
                    self.partial_close_hedge(main_position_key, self.CLOSE_AT_STEP_5)

    def check_gates(self, main_position_key: str, current_price: float) -> None:
        """
        Check gate conditions (reversion or surplus dump).

        Args:
            main_position_key: Key of the main position
            current_price: Current market price
        """
        if not self.enabled:
            return

        if main_position_key not in self.gates:
            return

        if main_position_key not in self.hedges:
            return

        hedge = self.hedges[main_position_key]
        if hedge['remaining'] <= 0:
            return

        hedge_profit = self.calculate_hedge_profit(main_position_key, current_price)
        if hedge_profit is None:
            return

        # Update peak tracking
        self.update_peak(main_position_key, hedge_profit)

        # Check reversion first (higher priority)
        if self.should_close_on_reversion(main_position_key, hedge_profit):
            print(f"  🔄 Hedge reverted to gate level")
            self.full_close_hedge(main_position_key, 'reversion')
            return

        # Check surplus dump
        if self.should_surplus_dump(main_position_key, hedge_profit):
            print(f"  📉 Hedge hit surplus dump threshold")
            self.full_close_hedge(main_position_key, 'surplus_dump')

    # ============================================================================
    # PROFIT PROTECTION HEDGE SYSTEM (Grok+Claude Consortium - Jan 14, 2026)
    # ============================================================================
    # Instead of closing at 70% of peak, open a hedge to secure profits while
    # keeping the original position open for potential recovery to peak.
    # ============================================================================

    def open_profit_protection_hedge(self, symbol: str, main_side: str, main_size: float,
                                     main_position_key: str, main_peak_upnl: float,
                                     leverage: int = 10) -> Optional[Dict]:
        """
        Open a profit-protection hedge when main position hits 70% of peak.

        This replaces the traditional "close at 70% of peak" with a hedge that:
        - Locks in profits while keeping main position open
        - Can profit if market reverses (hedge gains)
        - Allows main to recover to peak (main gains, hedge neutral)

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')
            main_side: Side of main position ('buy'/'sell')
            main_size: Current size of main position
            main_position_key: Key to track this hedge against
            main_peak_upnl: Peak UPNL achieved by main position
            leverage: Leverage to use

        Returns:
            Order result or None if failed
        """
        if not self.enabled:
            return None

        # V1.2.0: Get volatility-adjusted parameters
        adjusted_params = self.get_adjusted_hedge_params(symbol, main_peak_upnl)
        spike_mode = adjusted_params["spike_mode"]
        min_profit_threshold = adjusted_params["min_profit_threshold"]
        hedge_size_pct = adjusted_params["hedge_size_pct"]

        # Check minimum profit threshold (adjusted for volatility)
        if main_peak_upnl < min_profit_threshold:
            if spike_mode:
                print(f"  ⏸️ Emergency hedge skipped: peak ${main_peak_upnl:.2f} < spike min ${min_profit_threshold}")
            else:
                print(f"  ⏸️ Profit protection hedge skipped: peak ${main_peak_upnl:.2f} < min ${min_profit_threshold}")
            return None

        # V1.2.0: During volatility spikes, skip momentum filter (need fast protection)
        if not spike_mode:
            # Normal mode: Apply momentum filter to avoid hedging during oversold bounces
            momentum_ok, momentum_reason = self.check_momentum_filter(symbol, main_side)
            if not momentum_ok:
                print(f"  ⏸️ Profit protection hedge blocked by momentum filter: {momentum_reason}")
                return None
        else:
            print(f"  ⚡ SPIKE MODE: Bypassing momentum filter for emergency protection")

        profit_hedge_key = f"profit_hedge:{main_position_key}"

        # Don't double hedge
        if profit_hedge_key in self.hedges:
            print(f"  ⚠️ Profit protection hedge already exists for {main_position_key}")
            return None

        # Calculate hedge size (adjusted: 75% during spikes, 50% normal)
        hedge_size = main_size * hedge_size_pct
        hedge_side = self.get_hedge_side(main_side)
        hedge_position_side = self.get_position_side(hedge_side)

        try:
            params = {
                'marginCoin': 'USDT',
                'tradeSide': 'open',
                'holdSide': hedge_position_side
            }

            hedge_type = "EMERGENCY" if spike_mode else "PROFIT PROTECTION"
            size_pct_str = f"{hedge_size_pct*100:.0f}%"
            print(f"\n  {'⚡' if spike_mode else '🛡️'} Opening {hedge_type} hedge:")
            print(f"     Symbol: {symbol} {hedge_side.upper()}")
            print(f"     Size: {hedge_size:.6f} ({size_pct_str} of main {main_size:.6f})")
            print(f"     Reason: Main at 70% of peak ${main_peak_upnl:.2f}")
            if spike_mode:
                print(f"     ⚡ VOLATILITY SPIKE: ratio={adjusted_params['spike_ratio']:.2f}x")

            order = self.exchange.create_market_order(symbol, hedge_side, hedge_size, params=params)

            if order:
                entry_price = order.get('average') or order.get('price') or order.get('info', {}).get('priceAvg') or 0
                entry_price = float(entry_price) if entry_price else 0.0

                if entry_price <= 0:
                    try:
                        ticker = self.exchange.fetch_ticker(symbol)
                        entry_price = float(ticker.get('last', 0))
                    except Exception as e:
                        print(f"  ❌ Could not get valid entry price: {e}")
                        return None

                self.hedges[profit_hedge_key] = {
                    'symbol': symbol,
                    'side': hedge_side,
                    'position_side': hedge_position_side,
                    'position_type': 'emergency' if spike_mode else 'profit_protection',
                    'entry_price': entry_price,
                    'size': hedge_size,
                    'remaining': 1.0,
                    'opened_at': datetime.now().isoformat(),
                    'order_id': order.get('id'),
                    'main_position_key': main_position_key,  # Link to main position
                    'main_peak_upnl': main_peak_upnl,
                    'main_upnl_at_hedge_open': main_peak_upnl * 0.70,  # 70% of peak
                    # V1.2.0: Volatility spike metadata
                    'spike_mode': spike_mode,
                    'spike_ratio': adjusted_params.get('spike_ratio', 0),
                    'use_fast_stop': adjusted_params.get('use_fast_stop', False),
                    'fast_stop_atr_mult': adjusted_params.get('fast_stop_atr_mult', 0),
                    'atr_value': adjusted_params.get('atr_value', 0)
                }

                self.stats['hedges_opened'] += 1
                self.stats['profit_protection_hedges_opened'] = self.stats.get('profit_protection_hedges_opened', 0) + 1
                if spike_mode:
                    self.stats['emergency_hedges_opened'] += 1
                self._save_state()

                print(f"  ✅ {hedge_type} hedge opened @ ${entry_price:.6f}")
                return order

        except Exception as e:
            print(f"  ❌ Failed to open profit protection hedge: {e}")

        return None

    def check_profit_protection_gates(self, main_position_key: str, current_price: float,
                                      main_current_upnl: float, main_peak_upnl: float) -> Tuple[bool, str]:
        """
        Check if profit protection hedge should close.

        Gates (Grok recommendations + Stress Test Improvements):
        1. Hedge reaches 10% profit → Close hedge (lock in hedge gains)
        2. Main position drops to 50% of peak → Close hedge (protection no longer needed)
        3. Hedge hits -5% stop loss → Close hedge (cut losses)
        4. TRAILING STOP: Once hedge profits 3%, trail 2% behind peak (faster exits)

        Args:
            main_position_key: Key of the main position
            current_price: Current market price
            main_current_upnl: Current UPNL of main position
            main_peak_upnl: Peak UPNL of main position

        Returns:
            Tuple of (should_close: bool, reason: str)
        """
        profit_hedge_key = f"profit_hedge:{main_position_key}"

        if profit_hedge_key not in self.hedges:
            return (False, "no_hedge")

        hedge = self.hedges[profit_hedge_key]
        if hedge['remaining'] <= 0:
            return (False, "hedge_closed")

        # Calculate hedge P&L
        hedge_profit = self.calculate_hedge_profit(profit_hedge_key, current_price)
        if hedge_profit is None:
            return (False, "calc_error")

        # Calculate hedge profit percentage
        hedge_margin = (hedge['size'] * hedge['entry_price']) / self.leverage
        hedge_pnl_pct = (hedge_profit / hedge_margin) if hedge_margin > 0 else 0

        # ================================================================
        # STRESS TEST IMPROVEMENT: Trailing Stop Logic
        # ================================================================
        # Initialize trailing stop state if needed
        if profit_hedge_key not in self.trailing_stops:
            self.trailing_stops[profit_hedge_key] = {
                'peak_profit_pct': 0.0,
                'activated': False
            }

        trailing = self.trailing_stops[profit_hedge_key]

        # Update peak profit
        if hedge_pnl_pct > trailing['peak_profit_pct']:
            trailing['peak_profit_pct'] = hedge_pnl_pct
            self._save_state()

        # Activate trailing stop when profit reaches threshold
        if not trailing['activated'] and hedge_pnl_pct >= self.TRAILING_STOP_ACTIVATION:
            trailing['activated'] = True
            print(f"  📍 Trailing stop ACTIVATED at {hedge_pnl_pct*100:.2f}% profit")
            self._save_state()

        # Check trailing stop trigger (only if activated)
        trailing_stop_level = trailing['peak_profit_pct'] - self.TRAILING_STOP_DISTANCE
        trailing_triggered = trailing['activated'] and hedge_pnl_pct <= trailing_stop_level

        # V1.2.0: Check for spike mode and fast stop parameters
        spike_mode = hedge.get('spike_mode', False)
        use_fast_stop = hedge.get('use_fast_stop', False)
        atr_value = hedge.get('atr_value', 0)
        fast_stop_atr_mult = hedge.get('fast_stop_atr_mult', 1.5)

        print(f"  📊 Profit protection hedge check:")
        print(f"     Hedge PnL: ${hedge_profit:.4f} ({hedge_pnl_pct*100:.2f}%)")
        print(f"     Main UPNL: ${main_current_upnl:.4f} (peak: ${main_peak_upnl:.4f})")
        if spike_mode:
            print(f"     ⚡ SPIKE MODE: fast_stop={use_fast_stop}, ATR={atr_value:.6f}")
        if trailing['activated']:
            print(f"     Trailing: peak={trailing['peak_profit_pct']*100:.2f}%, stop={trailing_stop_level*100:.2f}%")

        # Gate 1: Hedge reaches 10% profit
        if hedge_pnl_pct >= self.PROFIT_HEDGE_PROFIT_GATE:
            print(f"  🎯 Gate 1: Hedge hit {self.PROFIT_HEDGE_PROFIT_GATE*100:.0f}% profit target!")
            self._cleanup_trailing_stop(profit_hedge_key)
            return (True, "hedge_profit_10pct")

        # Gate 2: TRAILING STOP (Stress Test Improvement - faster exits on V-recoveries)
        if trailing_triggered:
            print(f"  📉 Gate 2: Trailing stop triggered (dropped {self.TRAILING_STOP_DISTANCE*100:.0f}% from peak)")
            self.stats['trailing_stop_closes'] += 1
            self._cleanup_trailing_stop(profit_hedge_key)
            return (True, "trailing_stop")

        # V1.2.0 Gate 3: FAST STOP (ATR-based, only in spike mode)
        # During volatility spikes, use tighter ATR-based stop for faster protection
        if use_fast_stop and atr_value > 0:
            fast_stop_distance = atr_value * fast_stop_atr_mult
            entry_price = hedge['entry_price']
            # For short hedge, stop is above entry; for long hedge, stop is below entry
            if hedge['position_side'] == 'short':
                fast_stop_price = entry_price + fast_stop_distance
                fast_stop_hit = current_price >= fast_stop_price
            else:
                fast_stop_price = entry_price - fast_stop_distance
                fast_stop_hit = current_price <= fast_stop_price

            if fast_stop_hit:
                print(f"  ⚡ Gate 3: FAST STOP triggered (ATR-based)")
                print(f"     Entry: ${entry_price:.6f}, Stop: ${fast_stop_price:.6f}, Current: ${current_price:.6f}")
                self.stats['fast_stop_triggers'] += 1
                self._cleanup_trailing_stop(profit_hedge_key)
                return (True, "fast_stop_atr")

        # V1.2.5: Calculate time since hedge opened for delay checks
        seconds_since_hedge = 0
        if 'opened_at' in hedge:
            try:
                opened_at = datetime.fromisoformat(hedge['opened_at'])
                seconds_since_hedge = (datetime.now() - opened_at).total_seconds()
            except (ValueError, TypeError):
                seconds_since_hedge = float('inf')  # If parse fails, assume delay passed

        # Gate 4: Main drops to 50% of peak
        # V1.2.5: Add delay before main_drop can trigger (prevents dead cat bounce losses)
        main_drop_delay_passed = (not self.MAIN_DROP_DELAY_ENABLED or
                                  seconds_since_hedge >= self.MAIN_DROP_DELAY_SECONDS)
        if main_peak_upnl > 0:
            main_pct_of_peak = main_current_upnl / main_peak_upnl
            if main_pct_of_peak <= self.PROFIT_HEDGE_MAIN_DROP_GATE:
                if main_drop_delay_passed:
                    print(f"  📉 Gate 4: Main at {main_pct_of_peak*100:.0f}% of peak (threshold: {self.PROFIT_HEDGE_MAIN_DROP_GATE*100:.0f}%)")
                    self._cleanup_trailing_stop(profit_hedge_key)
                    return (True, "main_dropped")
                else:
                    # Log that we're delaying the gate
                    remaining = self.MAIN_DROP_DELAY_SECONDS - seconds_since_hedge
                    print(f"  ⏳ Gate 4: Main at {main_pct_of_peak*100:.0f}% but delay not passed ({remaining:.0f}s remaining)")

        # Gate 5: Stop loss at -5%
        # V1.2.5: Add delay before stop_loss can trigger (prevents dead cat bounce losses)
        stop_loss_delay_passed = (not self.STOP_LOSS_DELAY_ENABLED or
                                  seconds_since_hedge >= self.STOP_LOSS_DELAY_SECONDS)
        if hedge_pnl_pct <= self.PROFIT_HEDGE_STOP_LOSS:
            if stop_loss_delay_passed:
                print(f"  🛑 Gate 5: Hedge stop loss hit ({self.PROFIT_HEDGE_STOP_LOSS*100:.0f}%)")
                self._cleanup_trailing_stop(profit_hedge_key)
                return (True, "hedge_stop_loss")
            else:
                # Log that we're delaying the gate
                remaining = self.STOP_LOSS_DELAY_SECONDS - seconds_since_hedge
                print(f"  ⏳ Gate 5: Stop loss at {hedge_pnl_pct*100:.1f}% but delay not passed ({remaining:.0f}s remaining)")

        return (False, "hold")

    def _cleanup_trailing_stop(self, profit_hedge_key: str):
        """Clean up trailing stop state when hedge closes."""
        if profit_hedge_key in self.trailing_stops:
            del self.trailing_stops[profit_hedge_key]
            self._save_state()

    def close_profit_protection_hedge(self, main_position_key: str, reason: str) -> Optional[Dict]:
        """
        Close the profit protection hedge.

        Args:
            main_position_key: Key of the main position
            reason: Reason for closing (profit_target, main_dropped, stop_loss)

        Returns:
            Order result or None
        """
        profit_hedge_key = f"profit_hedge:{main_position_key}"

        if profit_hedge_key not in self.hedges:
            return None

        hedge = self.hedges[profit_hedge_key]
        if hedge['remaining'] <= 0:
            return None

        try:
            close_amount = hedge['size'] * hedge['remaining']
            close_side = hedge['side']
            position_side = hedge['position_side']

            params = {
                'marginCoin': 'USDT',
                'tradeSide': 'close',
                'holdSide': position_side
            }

            print(f"  🔻 Closing profit protection hedge ({reason}): {hedge['symbol']} {close_amount:.6f}")
            order = self.exchange.create_market_order(
                hedge['symbol'], close_side, close_amount, params=params
            )

            if order:
                realized_pnl = float(order.get('info', {}).get('realizedPnl', 0))
                self.stats['total_hedge_pnl'] += realized_pnl
                self.stats['hedges_closed'] += 1
                self.stats['profit_protection_hedges_closed'] = self.stats.get('profit_protection_hedges_closed', 0) + 1

                # Clean up
                del self.hedges[profit_hedge_key]
                self._save_state()

                print(f"  ✅ Profit protection hedge closed ({reason}): realized=${realized_pnl:.2f}")
                return order

        except Exception as e:
            print(f"  ❌ Failed to close profit protection hedge: {e}")

        return None

    def transition_profit_hedge_to_main(self, main_position_key: str) -> Optional[Dict]:
        """
        Transition profit protection hedge to become a main position.

        Called when the original main position closes. The hedge is released
        from hedge tracking and returned as position data for the main system
        to track as a new main position.

        Args:
            main_position_key: Key of the original main position

        Returns:
            Position data dict for the new main position, or None
        """
        profit_hedge_key = f"profit_hedge:{main_position_key}"

        if profit_hedge_key not in self.hedges:
            return None

        hedge = self.hedges[profit_hedge_key]
        if hedge['remaining'] <= 0:
            del self.hedges[profit_hedge_key]
            self._save_state()
            return None

        # Prepare position data for main system
        new_main_position = {
            'symbol': hedge['symbol'],
            'side': hedge['side'],
            'position_side': hedge['position_side'],
            'entry_price': hedge['entry_price'],
            'amount': hedge['size'] * hedge['remaining'],
            'size': hedge['size'] * hedge['remaining'],
            'opened_at': hedge['opened_at'],
            'transitioned_from': 'profit_protection_hedge',
            'original_main_key': main_position_key
        }

        print(f"\n  🔄 TRANSITIONING profit hedge to main position:")
        print(f"     Symbol: {hedge['symbol']}")
        print(f"     Side: {hedge['position_side'].upper()}")
        print(f"     Size: {new_main_position['amount']:.6f}")
        print(f"     Entry: ${hedge['entry_price']:.6f}")

        # Remove from hedge tracking
        del self.hedges[profit_hedge_key]
        self.stats['hedges_transitioned_to_main'] = self.stats.get('hedges_transitioned_to_main', 0) + 1
        self._save_state()

        return new_main_position

    def has_profit_protection_hedge(self, main_position_key: str) -> bool:
        """Check if main position has an active profit protection hedge."""
        profit_hedge_key = f"profit_hedge:{main_position_key}"
        if profit_hedge_key in self.hedges:
            return self.hedges[profit_hedge_key]['remaining'] > 0
        return False

    def on_main_position_closed(self, main_position_key: str) -> Optional[Dict]:
        """
        Called when main position is closed - handle hedge transition.

        For profit protection hedges: Transition to become new main position.
        For regular hedges: Release as independent position.

        Args:
            main_position_key: Key of the main position

        Returns:
            New main position data if profit hedge was transitioned, else None
        """
        if not self.enabled:
            return None

        # PRIORITY: Check for profit protection hedge first - transition to main
        new_main_position = self.transition_profit_hedge_to_main(main_position_key)
        if new_main_position:
            print(f"  ✅ Profit protection hedge transitioned to main position")
            # Also clean up any regular hedges
            if main_position_key in self.hedges:
                del self.hedges[main_position_key]
            if main_position_key in self.gates:
                del self.gates[main_position_key]
            self._save_state()
            return new_main_position

        # Handle regular entry hedges (release as independent)
        if main_position_key in self.hedges:
            hedge = self.hedges[main_position_key]
            if hedge['remaining'] > 0:
                # DON'T close the hedge - release it as independent position
                print(f"  🔓 Hedge released as independent: {hedge['symbol']} {hedge['position_side'].upper()}")
                print(f"     Size: {hedge['size'] * hedge['remaining']:.4f} contracts")
                print(f"     Entry: ${hedge['entry_price']:.6f}")
                self.stats['hedges_released'] = self.stats.get('hedges_released', 0) + 1

            # Clean up hedge gateway tracking (position continues independently)
            del self.hedges[main_position_key]

        if main_position_key in self.gates:
            del self.gates[main_position_key]

        self._save_state()
        return None

    def get_stats(self) -> Dict:
        """Get hedge gateway statistics."""
        return {
            **self.stats,
            'active_hedges': len([h for h in self.hedges.values() if h['remaining'] > 0]),
            'open_gates': len(self.gates)
        }

    def print_status(self):
        """Print current hedge status."""
        stats = self.get_stats()
        print(f"\n🛡️ Hedge Gateway Status (V1.2.0):")
        print(f"   Active hedges: {stats['active_hedges']}")
        print(f"   Open gates: {stats['open_gates']}")
        print(f"   Total hedge P&L: ${stats['total_hedge_pnl']:.2f}")
        print(f"   Reversion closes: {stats['reversion_closes']}")
        print(f"   Surplus dumps: {stats['surplus_dumps']}")
        print(f"   Profit protection hedges opened: {stats.get('profit_protection_hedges_opened', 0)}")
        print(f"   Profit protection hedges closed: {stats.get('profit_protection_hedges_closed', 0)}")
        print(f"   Hedges transitioned to main: {stats.get('hedges_transitioned_to_main', 0)}")
        print(f"   Momentum filter blocked: {stats.get('momentum_filter_blocked', 0)}")
        print(f"   Trailing stop closes: {stats.get('trailing_stop_closes', 0)}")
        print(f"   ⚡ Volatility spikes detected: {stats.get('volatility_spikes_detected', 0)}")
        print(f"   ⚡ Emergency hedges opened: {stats.get('emergency_hedges_opened', 0)}")
        print(f"   ⚡ Fast stop triggers: {stats.get('fast_stop_triggers', 0)}")


# Singleton instance
_hedge_gateway = None

def get_hedge_gateway(exchange=None, enabled=True, leverage=10):
    """Get or create HedgeGateway instance."""
    global _hedge_gateway
    if _hedge_gateway is None and exchange is not None:
        _hedge_gateway = HedgeGateway(exchange, enabled, leverage)
    return _hedge_gateway


if __name__ == "__main__":
    print("HedgeGateway module - import and use get_hedge_gateway(exchange)")
