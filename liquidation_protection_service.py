"""
Liquidation Protection Service

Prevents position liquidation by placing limit orders at critical price levels
when averaging has exhausted and position is in danger zone.

Key Features:
- Calculates liquidation price at configurable UPNL% (default -82.5%)
- Places LIMIT orders (not market) to add position size at calculated price
- Uses margin equal to margin used so far (via LIQUIDATION_ORDER_MARGIN_MULTIPLIER)
- Only triggers after last Fibonacci averaging steps (5+)
- Tracks placed orders to avoid duplicates
- Syncs entry price from exchange weighted average
- PERSISTS protection orders to disk to survive restarts
- SYNCS with exchange at startup to detect existing protection orders

Configuration (from PositionSizingConfig):
- LIQUIDATION_ORDER_UPNL_PERCENT: -82.5% (trigger for limit order)
- LIQUIDATION_ORDER_MARGIN_MULTIPLIER: 1.0x (matches margin used so far)

Author: AI-XYZ Trading System
Date: 2026-01-03
Updated: 2026-01-10 (Config-based values, FIFO integration)
Updated: 2026-01-11 (Persistence and startup sync)
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
import structlog
import json

# Unified liquidation calculator (single source of truth)
from liquidation_calculator import get_liquidation_calculator, LiquidationCalculator
import os
from position_sizing_config import PositionSizingConfig

logger = structlog.get_logger()


class LiquidationProtectionService:
    """
    Service to protect positions from liquidation by placing limit orders
    at calculated prices before liquidation occurs.

    Liquidation typically occurs at -90% to -95% UPNL with 10x leverage.
    We place protection orders at -82.5% UPNL to catch the position before liquidation.
    """

    # State file path for persistence
    STATE_FILE = 'protection_orders_state.json'

    def __init__(self, exchange, state_dir: str = '.'):
        """
        Initialize liquidation protection service

        Args:
            exchange: CCXT exchange instance
            state_dir: Directory to store state file (default: current dir)
        """
        self.exchange = exchange
        self.state_file_path = os.path.join(state_dir, self.STATE_FILE)
        self.protection_orders = {}  # {symbol: order_info}
        self.executed_protections = {}  # Track filled orders

        # Retry queue for failed protection orders
        # {symbol: {'position': pos, 'margin': margin, 'retry_count': n, 'last_attempt': timestamp}}
        self.retry_queue = {}
        self.MAX_RETRIES = 3
        self.RETRY_DELAY_SECONDS = 60  # Exponential backoff base

        # Load persisted state
        self._load_state()

        logger.info(
            "LiquidationProtectionService initialized",
            state_file=self.state_file_path,
            loaded_orders=len(self.protection_orders)
        )

    def _load_state(self) -> None:
        """Load protection orders state from disk."""
        try:
            if os.path.exists(self.state_file_path):
                with open(self.state_file_path, 'r') as f:
                    data = json.load(f)

                self.protection_orders = data.get('protection_orders', {})
                self.executed_protections = data.get('executed_protections', {})

                # Convert datetime strings back to datetime objects
                for symbol, order in self.protection_orders.items():
                    if 'placed_at' in order and isinstance(order['placed_at'], str):
                        order['placed_at'] = datetime.fromisoformat(order['placed_at'].replace('Z', '+00:00'))

                logger.info(
                    "Loaded protection orders state",
                    orders=len(self.protection_orders),
                    executed=len(self.executed_protections)
                )
        except Exception as e:
            logger.warning(f"Could not load protection state: {e}")
            self.protection_orders = {}
            self.executed_protections = {}

    def _save_state(self) -> None:
        """Save protection orders state to disk."""
        try:
            data = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'protection_orders': {},
                'executed_protections': self.executed_protections
            }

            # Convert datetime objects to strings for JSON serialization
            for symbol, order in self.protection_orders.items():
                order_copy = order.copy()
                if 'placed_at' in order_copy and isinstance(order_copy['placed_at'], datetime):
                    order_copy['placed_at'] = order_copy['placed_at'].isoformat()
                data['protection_orders'][symbol] = order_copy

            with open(self.state_file_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)

            logger.debug(
                "Saved protection orders state",
                orders=len(self.protection_orders)
            )
        except Exception as e:
            logger.error(f"Failed to save protection state: {e}")

    def sync_from_exchange(self, symbols: List[str]) -> Dict[str, int]:
        """
        Sync protection orders from exchange at startup.

        Checks all open orders for each symbol and identifies protection orders
        (limit orders below current price for longs).

        Args:
            symbols: List of symbols to check

        Returns:
            Dict with sync stats {synced: int, cancelled_duplicates: int}
        """
        stats = {'synced': 0, 'cancelled_duplicates': 0}

        print("\n🔄 Syncing protection orders from exchange...")

        for symbol in symbols:
            try:
                # Get all open orders for this symbol
                open_orders = self.exchange.fetch_open_orders(symbol)

                if not open_orders:
                    continue

                # Get current position info
                positions = self.exchange.fetch_positions([symbol])
                if not positions or positions[0].get('contracts', 0) <= 0:
                    continue

                pos = positions[0]
                entry_price = pos.get('entryPrice', 0)
                side = 'buy' if pos.get('side') == 'long' else 'sell'

                # Find protection orders (limit orders at or below protection level for longs)
                # Protection orders are placed at -82.5% UPNL = 91.75% of entry for 10x leverage
                # Use 95% threshold to detect any order near protection level
                protection_orders = []
                for order in open_orders:
                    if order['type'] == 'limit' and order['side'] == side:
                        # Check if price is at or below protection level (for longs)
                        # Orders below 95% of entry are likely protection orders
                        if side == 'buy' and order['price'] < entry_price * 0.95:
                            protection_orders.append(order)
                        elif side == 'sell' and order['price'] > entry_price * 1.05:
                            protection_orders.append(order)

                if not protection_orders:
                    continue

                # Handle duplicates - keep only the newest
                if len(protection_orders) > 1:
                    sorted_orders = sorted(protection_orders, key=lambda x: x['datetime'], reverse=True)
                    keep_order = sorted_orders[0]

                    print(f"  {symbol}: Found {len(protection_orders)} protection orders, keeping newest")

                    for order in sorted_orders[1:]:
                        try:
                            self.exchange.cancel_order(order['id'], symbol)
                            print(f"    ❌ Cancelled duplicate: {order['id']}")
                            stats['cancelled_duplicates'] += 1
                        except Exception as e:
                            print(f"    ⚠️ Could not cancel {order['id']}: {e}")

                    protection_orders = [keep_order]

                # Sync the remaining protection order
                order = protection_orders[0]

                # Only add if not already tracked
                if symbol not in self.protection_orders:
                    self.protection_orders[symbol] = {
                        'order_id': order['id'],
                        'symbol': symbol,
                        'side': order['side'],
                        'price': order['price'],
                        'amount': order['amount'],
                        'placed_at': datetime.fromisoformat(order['datetime'].replace('Z', '+00:00')),
                        'status': 'open',
                        'synced_from_exchange': True
                    }
                    stats['synced'] += 1
                    print(f"  ✅ {symbol}: Synced protection order {order['id']} @ ${order['price']}")

            except Exception as e:
                logger.warning(f"Failed to sync {symbol}: {e}")

        # Save state after sync
        self._save_state()

        print(f"  📊 Sync complete: {stats['synced']} synced, {stats['cancelled_duplicates']} duplicates cancelled")
        return stats

    def calculate_liquidation_price(
        self,
        entry_price: float,
        side: str,
        leverage: float,
        target_upnl_pct: float = None
    ) -> float:
        """
        Calculate price at which UPNL reaches target percentage

        UPNL% = (current_price - entry_price) / entry_price × leverage × 100

        Rearranging for current_price:
        current_price = entry_price × (1 + UPNL% / (leverage × 100))

        Args:
            entry_price: Weighted average entry price from exchange
            side: 'buy' for LONG, 'sell' for SHORT
            leverage: Position leverage (e.g., 10.0)
            target_upnl_pct: Target UPNL percentage (default -82.5%)

        Returns:
            Price at which to place limit order

        Example:
            LONG at $1.00 entry, 10x leverage, -82.5% UPNL target:
            Uses unified LiquidationCalculator for consistent results
        """
        # Use config default if not provided
        if target_upnl_pct is None:
            target_upnl_pct = PositionSizingConfig.LIQUIDATION_ORDER_UPNL_PERCENT

        # Use unified calculator for consistent liquidation price calculation
        calc = get_liquidation_calculator()
        liquidation_price = calc.calculate_price_at_upnl(
            entry_price=entry_price,
            target_upnl_pct=target_upnl_pct,
            side=side,
            leverage=leverage
        )

        return liquidation_price

    def should_place_protection_order(
        self,
        symbol: str,
        position: Dict,
        averaging_step: int,
        upnl_pct: float
    ) -> bool:
        """
        Check if liquidation protection order should be placed

        Conditions (ALL must be met):
        1. Last averaging step executed (step 5, 6, or 7)
        2. UPNL in danger zone (-70% to -82%)
        3. No protection order already placed for this symbol
        4. No protection order already executed (filled)

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT:USDT')
            position: Position dictionary with current state
            averaging_step: Current averaging step (0-indexed)
            upnl_pct: Current UPNL percentage (e.g., -75.5)

        Returns:
            True if protection order should be placed
        """
        # Check if already protected
        if symbol in self.protection_orders:
            logger.info(
                "Liquidation protection already placed",
                symbol=symbol,
                order_id=self.protection_orders[symbol]['order_id']
            )
            return False

        # Check if protection already executed
        if symbol in self.executed_protections:
            logger.info(
                "Liquidation protection already executed",
                symbol=symbol,
                executed_at=self.executed_protections[symbol]['executed_at']
            )
            return False

        # Wait for last averaging steps (5+)
        # 0-indexed: step 5 = 6th step, step 6 = 7th step
        if averaging_step < 5:
            logger.debug(
                "Too early for liquidation protection",
                symbol=symbol,
                current_step=averaging_step,
                min_required_step=5
            )
            return False

        # Check if in danger zone (-70% to -82%)
        if upnl_pct > -70:
            logger.debug(
                "Not in danger zone yet",
                symbol=symbol,
                upnl_pct=upnl_pct,
                danger_threshold=-70
            )
            return False

        if upnl_pct < -82:
            logger.warning(
                "Already past protection zone - too late",
                symbol=symbol,
                upnl_pct=upnl_pct,
                protection_threshold=-82
            )
            return False

        logger.info(
            "Liquidation protection conditions met",
            symbol=symbol,
            averaging_step=averaging_step,
            upnl_pct=upnl_pct
        )
        return True

    def place_protection_order(
        self,
        symbol: str,
        position: Dict,
        margin_used_so_far: float = None,
        additional_margin: float = None,
        target_upnl_pct: float = None
    ) -> bool:
        """
        Place limit order at liquidation price to prevent liquidation

        Process:
        1. Cancel any existing protection order for this symbol (prevent duplicates)
        2. Fetch current weighted average entry from exchange
        3. Calculate liquidation price at target UPNL% (from config)
        4. Calculate contracts for additional margin (based on margin used so far)
        5. Place LIMIT order (maker, not taker)
        6. Track order for monitoring

        Args:
            symbol: Trading pair
            position: Position dictionary
            margin_used_so_far: Total margin used for this position (for calculating protection margin)
            additional_margin: Override for additional margin to use (default: margin_used × multiplier)
            target_upnl_pct: Target UPNL for protection (default from config: -82.5%)

        Returns:
            True if order placed successfully
        """
        # CRITICAL: Cancel any existing protection order for this symbol first
        # This prevents duplicate orders when entry price changes
        if symbol in self.protection_orders:
            existing_order = self.protection_orders[symbol]
            logger.info(
                "Cancelling existing protection order before placing new one",
                symbol=symbol,
                existing_order_id=existing_order['order_id'],
                existing_price=existing_order['price']
            )
            print(f"\n  🔄 Replacing existing protection order for {symbol}")
            print(f"     Old order ID: {existing_order['order_id']} @ ${existing_order['price']:.6f}")
            try:
                self.exchange.cancel_order(existing_order['order_id'], symbol)
                print(f"     ✅ Old order cancelled")
                del self.protection_orders[symbol]
            except Exception as cancel_error:
                # Order might already be filled or cancelled
                print(f"     ⚠️ Could not cancel old order: {cancel_error}")
                # Still remove from tracking - will verify status later
                del self.protection_orders[symbol]

        # Use config values as defaults
        if target_upnl_pct is None:
            target_upnl_pct = PositionSizingConfig.LIQUIDATION_ORDER_UPNL_PERCENT

        # Calculate additional margin based on margin used and multiplier
        if additional_margin is None:
            if margin_used_so_far is not None:
                additional_margin = margin_used_so_far * PositionSizingConfig.LIQUIDATION_ORDER_MARGIN_MULTIPLIER
            else:
                # Fallback to full capital if margin used not provided
                additional_margin = PositionSizingConfig.TOTAL_CAPITAL
        try:
            print(f"\n🛡️ LIQUIDATION PROTECTION - {symbol}")
            print("=" * 80)

            # 1. Get current weighted average from exchange
            # CRITICAL: Use exchange entryPrice, not our calculated entry_price
            exchange_positions = self.exchange.fetch_positions([symbol])

            if not exchange_positions or len(exchange_positions) == 0:
                print(f"  ❌ No position found on exchange for {symbol}")
                return False

            ex_pos = exchange_positions[0]

            if ex_pos.get('contracts', 0) <= 0:
                print(f"  ❌ Position has no contracts: {symbol}")
                return False

            # Get weighted average entry from exchange
            entry_price = ex_pos.get('entryPrice', 0)
            if entry_price <= 0:
                print(f"  ❌ Invalid entry price from exchange: {entry_price}")
                return False

            side = position['side']
            leverage = position.get('leverage', 10.0)
            current_amount = ex_pos.get('contracts', 0)

            print(f"  📊 Current Position:")
            print(f"     Entry (weighted avg): ${entry_price:.6f}")
            print(f"     Amount: {current_amount:,.0f} contracts")
            print(f"     Leverage: {leverage}x")
            print(f"     Side: {side.upper()}")

            # 2. Calculate liquidation price at target UPNL%
            liquidation_price = self.calculate_liquidation_price(
                entry_price,
                side,
                leverage,
                target_upnl_pct
            )

            # Calculate price drop/rise percentage
            if side == 'buy':
                price_change_pct = ((liquidation_price - entry_price) / entry_price) * 100
            else:
                price_change_pct = ((entry_price - liquidation_price) / entry_price) * 100

            print(f"\n  🎯 Protection Calculation:")
            print(f"     Target UPNL: {target_upnl_pct}%")
            print(f"     Limit price: ${liquidation_price:.6f}")
            print(f"     Price change from entry: {price_change_pct:.2f}%")

            # 3. Check available balance and adjust protection margin
            # CRITICAL: Don't fail if insufficient balance - use what's available
            try:
                balance = self.exchange.fetch_balance()
                available_margin = balance['USDT']['free']

                print(f"\n  💰 Balance Check:")
                print(f"     Available margin: ${available_margin:.2f}")
                print(f"     Requested margin: ${additional_margin:.2f}")

                # Use available balance if less than requested
                if available_margin < additional_margin:
                    if available_margin < 1.0:
                        print(f"  ⚠️ Insufficient balance for protection (${available_margin:.2f} < $1.00)")
                        print(f"     Skipping protection order - need at least $1.00 margin")
                        return False
                    else:
                        print(f"  ⚠️ Reducing protection margin to available balance: ${available_margin:.2f}")
                        additional_margin = available_margin * 0.95  # Use 95% to leave buffer
                        print(f"     Using ${additional_margin:.2f} (95% of available)")
            except Exception as e:
                print(f"  ⚠️ Could not check balance: {e}")
                print(f"     Proceeding with requested margin ${additional_margin:.2f}")

            # Calculate contracts for additional margin
            # contracts = (margin × leverage) / price
            protection_contracts = (additional_margin * leverage) / liquidation_price

            # Round to exchange precision
            # Most perpetuals allow decimal contracts
            protection_contracts = round(protection_contracts, 0)

            if protection_contracts <= 0:
                print(f"  ❌ Calculated contracts <= 0: {protection_contracts}")
                return False

            # Calculate new position size and weighted average after fill
            total_contracts = current_amount + protection_contracts
            new_weighted_avg = (
                (entry_price * current_amount + liquidation_price * protection_contracts)
                / total_contracts
            )

            improvement_pct = ((entry_price - new_weighted_avg) / entry_price) * 100 if side == 'buy' else ((new_weighted_avg - entry_price) / entry_price) * 100

            print(f"\n  💰 Protection Order Details:")
            print(f"     Additional margin: ${additional_margin:.2f}")
            print(f"     Contracts to add: {protection_contracts:,.0f}")
            print(f"     New total size: {total_contracts:,.0f} contracts")
            print(f"     New weighted avg (after fill): ${new_weighted_avg:.6f}")
            print(f"     Entry improvement: {improvement_pct:.2f}%")

            # 4. Place LIMIT order
            # CRITICAL: Remove postOnly to ensure order WILL execute
            # If postOnly=True, order gets rejected if it would cross the spread
            # We NEED this order to execute for liquidation protection!

            # HEDGE MODE FIX: Must include holdSide for Bitget hedge mode
            # buy side = long position, sell side = short position
            position_side = 'long' if side == 'buy' else 'short'

            order_params = {
                'reduceOnly': False,  # We're adding to position
                'holdSide': position_side,  # REQUIRED for Bitget hedge mode
                'tradeSide': 'open',  # Opening/adding to position
                # postOnly removed - allow order to execute as taker if needed
            }

            print(f"\n  📋 Placing LIMIT {side.upper()} order (holdSide={position_side})...")

            order = self.exchange.create_order(
                symbol=symbol,
                type='limit',
                side=side,
                amount=protection_contracts,
                price=liquidation_price,
                params=order_params
            )

            # 5. Track order
            order_info = {
                'order_id': order['id'],
                'symbol': symbol,
                'side': side,
                'price': liquidation_price,
                'amount': protection_contracts,
                'margin': additional_margin,
                'entry_price_before': entry_price,
                'expected_weighted_avg': new_weighted_avg,
                'target_upnl_pct': target_upnl_pct,
                'placed_at': datetime.now(timezone.utc),
                'status': 'open'
            }

            self.protection_orders[symbol] = order_info

            # Persist to disk
            self._save_state()

            print(f"\n  ✅ LIQUIDATION PROTECTION ORDER PLACED")
            print(f"     Order ID: {order['id']}")
            print(f"     Status: {order.get('status', 'unknown')}")
            print(f"     Will execute if price reaches ${liquidation_price:.6f}")
            print(f"     Protects against liquidation at ~-90% UPNL")
            print("=" * 80)

            logger.info(
                "🔍 AUDIT [LIQUIDATION_PROTECTION_PLACED]",
                **order_info
            )

            return True

        except Exception as e:
            print(f"\n  ❌ Failed to place liquidation protection order: {e}")
            logger.error(
                "Liquidation protection order failed",
                symbol=symbol,
                error=str(e),
                exc_info=True
            )

            # Add to retry queue with exponential backoff
            import time
            if symbol not in self.retry_queue:
                self.retry_queue[symbol] = {
                    'position': position,
                    'margin': additional_margin,
                    'retry_count': 0,
                    'last_attempt': time.time(),
                    'error': str(e)
                }
                print(f"  📋 Added {symbol} to protection order retry queue")
                logger.info(
                    "Protection order queued for retry",
                    symbol=symbol,
                    retry_count=0
                )
            else:
                self.retry_queue[symbol]['retry_count'] += 1
                self.retry_queue[symbol]['last_attempt'] = time.time()
                self.retry_queue[symbol]['error'] = str(e)

            return False

    def check_protection_orders(self) -> None:
        """
        Check status of placed protection orders

        Updates:
        - Order status (filled, cancelled, open)
        - Moves filled orders to executed_protections
        - Cancels stale orders if position recovered
        """
        for symbol in list(self.protection_orders.keys()):
            order_info = self.protection_orders[symbol]

            try:
                # Fetch order status
                order = self.exchange.fetch_order(
                    order_info['order_id'],
                    symbol
                )

                status = order.get('status', 'unknown')
                order_info['status'] = status

                if status == 'closed' or status == 'filled':
                    # Order executed - protection triggered
                    print(f"\n  ✅ Liquidation protection EXECUTED for {symbol}")
                    print(f"     Order ID: {order_info['order_id']}")
                    print(f"     Filled at: ${order_info['price']:.6f}")
                    print(f"     Added: {order_info['amount']:,.0f} contracts")

                    # Move to executed protections
                    order_info['executed_at'] = datetime.now(timezone.utc)
                    order_info['filled_price'] = order.get('price', order_info['price'])
                    self.executed_protections[symbol] = order_info

                    # Remove from active orders
                    del self.protection_orders[symbol]

                    # Persist state change
                    self._save_state()

                    logger.info(
                        "🔍 AUDIT [LIQUIDATION_PROTECTION_EXECUTED]",
                        symbol=symbol,
                        order_id=order_info['order_id'],
                        filled_price=order_info['filled_price'],
                        contracts_added=order_info['amount']
                    )

                elif status == 'cancelled' or status == 'canceled':
                    # Order cancelled - remove from tracking
                    print(f"\n  ⚠️ Liquidation protection order cancelled for {symbol}")
                    del self.protection_orders[symbol]

                    # Persist state change
                    self._save_state()

            except Exception as e:
                logger.error(
                    "Failed to check protection order status",
                    symbol=symbol,
                    order_id=order_info['order_id'],
                    error=str(e)
                )

        # Process retry queue for failed orders
        self._process_retry_queue()

    def _process_retry_queue(self) -> None:
        """
        Process retry queue for failed protection orders.

        Uses exponential backoff: wait 60s, 120s, 240s between retries.
        Removes from queue after MAX_RETRIES (3) attempts.
        """
        import time

        if not self.retry_queue:
            return

        current_time = time.time()

        for symbol in list(self.retry_queue.keys()):
            retry_info = self.retry_queue[symbol]

            # Check if max retries exceeded
            if retry_info['retry_count'] >= self.MAX_RETRIES:
                print(f"  ⛔ {symbol}: Max retries ({self.MAX_RETRIES}) exceeded for protection order")
                logger.warning(
                    "Protection order retry exhausted",
                    symbol=symbol,
                    retry_count=retry_info['retry_count'],
                    last_error=retry_info.get('error', 'unknown')
                )
                del self.retry_queue[symbol]
                continue

            # Check if enough time has passed (exponential backoff)
            delay = self.RETRY_DELAY_SECONDS * (2 ** retry_info['retry_count'])
            time_since_last = current_time - retry_info['last_attempt']

            if time_since_last < delay:
                # Not ready for retry yet
                continue

            # Attempt retry
            print(f"\n  🔄 Retrying protection order for {symbol} (attempt {retry_info['retry_count'] + 1}/{self.MAX_RETRIES})")
            logger.info(
                "Retrying protection order",
                symbol=symbol,
                attempt=retry_info['retry_count'] + 1,
                delay_waited=time_since_last
            )

            # Try to place the order again
            success = self.place_protection_order(
                symbol=symbol,
                position=retry_info['position'],
                additional_margin=retry_info['margin']
            )

            if success:
                # Success - remove from retry queue
                print(f"  ✅ Protection order retry succeeded for {symbol}")
                del self.retry_queue[symbol]
            # If failed, the exception handler already updated retry_queue

    def get_protection_status(self, symbol: str) -> Optional[Dict]:
        """
        Get protection order status for a symbol

        Returns:
            Order info dict if exists, None otherwise
        """
        if symbol in self.protection_orders:
            return self.protection_orders[symbol]
        elif symbol in self.executed_protections:
            return self.executed_protections[symbol]
        return None

    def cancel_protection_order(self, symbol: str) -> bool:
        """
        Cancel protection order for a symbol

        Use when:
        - Position recovered above danger zone
        - Position was manually closed

        Args:
            symbol: Trading pair

        Returns:
            True if cancelled successfully
        """
        if symbol not in self.protection_orders:
            return False

        order_info = self.protection_orders[symbol]

        try:
            self.exchange.cancel_order(order_info['order_id'], symbol)
            print(f"  ✅ Cancelled liquidation protection order for {symbol}")
            del self.protection_orders[symbol]

            # Persist state change
            self._save_state()

            return True

        except Exception as e:
            print(f"  ❌ Failed to cancel protection order: {e}")
            return False
