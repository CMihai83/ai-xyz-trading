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
Version: 2.0.0
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
    GATE_OPEN_STEPS = [2, 4, 5]  # Averaging steps that open gates (added step 4 for mid-range protection)
    CLOSE_AT_STEP_2 = 0.25   # Close 25% of hedge at step 2 (was 30%)
    CLOSE_AT_STEP_4 = 0.25   # Close 25% of hedge at step 4 (NEW)
    CLOSE_AT_STEP_5 = 0.50   # Close 50% (remaining) at step 5 (was 70%)
    GATE_BUFFER_PCT = 10.0   # 10% buffer for reversion detection (was 5% - too tight)
    SURPLUS_DUMP_PCT = 0.85  # Close at 85% of peak profit (was 70% - too aggressive)

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
            'total_hedge_pnl': 0.0
        }

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
            'leverage': self.leverage  # Store leverage in state
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

    def on_main_position_closed(self, main_position_key: str) -> None:
        """
        Called when main position is closed - hedge becomes independent.

        The hedge is NOT closed automatically. Instead, it is released from
        hedge gateway tracking and becomes an independent position managed
        by the main trading system.

        Args:
            main_position_key: Key of the main position
        """
        if not self.enabled:
            return

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
        print(f"\n🛡️ Hedge Gateway Status:")
        print(f"   Active hedges: {stats['active_hedges']}")
        print(f"   Open gates: {stats['open_gates']}")
        print(f"   Total hedge P&L: ${stats['total_hedge_pnl']:.2f}")
        print(f"   Reversion closes: {stats['reversion_closes']}")
        print(f"   Surplus dumps: {stats['surplus_dumps']}")


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
