#!/usr/bin/env python3
"""
Tiered Balance Sync Service
============================
Automatically syncs tiered capital allocation with actual exchange balance.

Features:
- Periodic balance checks (configurable interval)
- Auto-adjusts tier capital allocation based on actual balance
- Dynamic position limits based on capital
- Redis state persistence
- Standalone service or integrated mode

Run standalone:
    python tiered_balance_sync_service.py

Or import and use in main trading system:
    from tiered_balance_sync_service import TieredBalanceSyncService
    sync_service = TieredBalanceSyncService(exchange, tiered_allocation)
    sync_service.sync_now()  # Manual sync
    sync_service.start_background_sync()  # Auto-sync every interval
"""

import os
import time
import json
import threading
from datetime import datetime
from typing import Optional, Dict
import redis

# Try to import ccxt for standalone mode
try:
    import ccxt
    CCXT_AVAILABLE = True
except ImportError:
    CCXT_AVAILABLE = False

# Import tiered allocation
from tiered_capital_allocation import TieredCapitalAllocation, MarketTier, get_tiered_allocation


class TieredBalanceSyncService:
    """
    Service to sync tiered allocation with actual exchange balance.

    Automatically adjusts:
    - Total capital per tier based on exchange balance
    - Max positions based on capital (configurable ratio)
    - Tier usage tracking from active positions
    """

    def __init__(
        self,
        exchange=None,
        tiered_allocation: TieredCapitalAllocation = None,
        sync_interval: int = 300,  # 5 minutes default
        min_capital_per_position: float = 10.0,  # Minimum $10 per position
        redis_host: str = None,
        redis_port: int = None
    ):
        """
        Initialize the balance sync service.

        Args:
            exchange: CCXT exchange instance (optional for standalone)
            tiered_allocation: TieredCapitalAllocation instance
            sync_interval: Seconds between auto-syncs (default 300 = 5 min)
            min_capital_per_position: Minimum capital per position for calculating max positions
            redis_host: Redis host for state persistence
            redis_port: Redis port
        """
        self.exchange = exchange
        self.tiered_allocation = tiered_allocation or get_tiered_allocation()
        self.sync_interval = sync_interval
        self.min_capital_per_position = min_capital_per_position

        # Redis for state persistence
        self.redis_host = redis_host or os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = redis_port or int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = None
        self._init_redis()

        # Background sync control
        self._sync_thread = None
        self._stop_sync = threading.Event()

        # Last sync info
        self.last_sync_time = None
        self.last_balance = 0.0
        self.sync_count = 0

        print(f"📊 TieredBalanceSyncService initialized")
        print(f"   Sync interval: {sync_interval}s")
        print(f"   Min capital/position: ${min_capital_per_position}")

    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=1,  # Use db=1 for tiered allocation state
                decode_responses=True
            )
            self.redis_client.ping()
            print(f"   Redis: {self.redis_host}:{self.redis_port}/1")
        except Exception as e:
            print(f"   ⚠️ Redis not available: {e}")
            self.redis_client = None

    def _init_exchange(self):
        """Initialize exchange if not provided (standalone mode)"""
        if self.exchange is None and CCXT_AVAILABLE:
            from dotenv import load_dotenv
            load_dotenv('/root/ai_xyz/.env')

            self.exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_API_SECRET'),
                'password': os.getenv('BITGET_API_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'defaultSubType': 'linear'
                }
            })
            self.exchange.load_markets()
            print("   Exchange: Bitget USDT-M Futures")

    def get_exchange_balance(self) -> float:
        """Get current futures account balance from exchange"""
        if self.exchange is None:
            self._init_exchange()

        try:
            balance = self.exchange.fetch_balance()
            total = balance.get('USDT', {}).get('total', 0)
            if total == 0:
                total = balance.get('total', {}).get('USDT', 0)
            return float(total) if total else 0.0
        except Exception as e:
            print(f"   ⚠️ Failed to fetch balance: {e}")
            return self.last_balance  # Return last known balance

    def get_active_positions(self) -> list:
        """Get list of active positions from exchange"""
        if self.exchange is None:
            self._init_exchange()

        try:
            positions = self.exchange.fetch_positions()
            active = [p for p in positions if abs(p.get('contracts', 0)) > 0]
            return active
        except Exception as e:
            print(f"   ⚠️ Failed to fetch positions: {e}")
            return []

    def calculate_max_positions(self, total_capital: float) -> int:
        """
        Calculate optimal max positions based on capital.

        Formula: max_positions = floor(total_capital / min_capital_per_position)
        Rounded to nearest multiple of 3 for even tier distribution.

        Args:
            total_capital: Total available capital

        Returns:
            Max positions (multiple of 3)
        """
        raw_max = int(total_capital / self.min_capital_per_position)

        # Round to nearest multiple of 3 (for even tier split)
        positions_per_tier = max(1, raw_max // 3)
        max_positions = positions_per_tier * 3

        # Minimum 3 positions (1 per tier), maximum 60
        return max(3, min(60, max_positions))

    def sync_now(self, force: bool = False) -> Dict:
        """
        Sync tiered allocation with current exchange balance.

        Args:
            force: Force sync even if balance unchanged

        Returns:
            Sync result dict
        """
        start_time = time.time()

        # Get current balance
        current_balance = self.get_exchange_balance()

        # Check if sync needed
        balance_changed = abs(current_balance - self.last_balance) > 1.0  # $1 threshold

        if not force and not balance_changed:
            return {
                'synced': False,
                'reason': 'Balance unchanged',
                'balance': current_balance
            }

        # Calculate new max positions
        new_max_positions = self.calculate_max_positions(current_balance)

        # Get active positions for tier usage tracking
        active_positions = self.get_active_positions()

        # Store old values for comparison
        old_capital = self.tiered_allocation.total_capital
        old_positions = self.tiered_allocation.max_positions

        # Update tiered allocation
        self.tiered_allocation.total_capital = current_balance
        self.tiered_allocation.max_positions = new_max_positions
        self.tiered_allocation.capital_per_tier = current_balance / 3
        self.tiered_allocation.positions_per_tier = new_max_positions // 3

        # Update tier configs
        for tier, config in self.tiered_allocation.tier_configs.items():
            config.capital_allocated = current_balance / 3
            config.max_positions = new_max_positions // 3
            config.capital_per_position = (current_balance / 3) / (new_max_positions // 3)

        # Sync tier usage from active positions
        self.tiered_allocation.update_from_exchange(active_positions, current_balance)

        # Update tracking
        self.last_balance = current_balance
        self.last_sync_time = datetime.now()
        self.sync_count += 1

        # Save to Redis
        self._save_state()

        sync_time = time.time() - start_time

        result = {
            'synced': True,
            'balance': {
                'old': old_capital,
                'new': current_balance,
                'change': current_balance - old_capital
            },
            'max_positions': {
                'old': old_positions,
                'new': new_max_positions
            },
            'per_tier': {
                'capital': current_balance / 3,
                'positions': new_max_positions // 3
            },
            'active_positions': len(active_positions),
            'sync_time_ms': int(sync_time * 1000),
            'sync_count': self.sync_count
        }

        # Print update
        if balance_changed or force:
            print(f"\n📊 TIERED ALLOCATION SYNCED")
            print(f"   Balance: ${old_capital:.2f} → ${current_balance:.2f} ({current_balance - old_capital:+.2f})")
            print(f"   Max Positions: {old_positions} → {new_max_positions}")
            print(f"   Per Tier: ${current_balance/3:.2f} / {new_max_positions//3} positions")
            print(f"   Active: {len(active_positions)} positions")

        return result

    def _save_state(self):
        """Save current state to Redis"""
        if self.redis_client is None:
            return

        try:
            state = {
                'total_capital': self.tiered_allocation.total_capital,
                'max_positions': self.tiered_allocation.max_positions,
                'capital_per_tier': self.tiered_allocation.capital_per_tier,
                'positions_per_tier': self.tiered_allocation.positions_per_tier,
                'current_tier': self.tiered_allocation.current_tier.name,
                'tier_usage': {
                    tier.name: usage for tier, usage in self.tiered_allocation.tier_usage.items()
                },
                'last_sync': self.last_sync_time.isoformat() if self.last_sync_time else None,
                'sync_count': self.sync_count
            }

            self.redis_client.set('tiered_allocation:state', json.dumps(state))
            self.redis_client.set('tiered_allocation:last_balance', str(self.last_balance))
        except Exception as e:
            print(f"   ⚠️ Failed to save state to Redis: {e}")

    def _load_state(self):
        """Load state from Redis"""
        if self.redis_client is None:
            return None

        try:
            state_json = self.redis_client.get('tiered_allocation:state')
            if state_json:
                return json.loads(state_json)
        except Exception as e:
            print(f"   ⚠️ Failed to load state from Redis: {e}")

        return None

    def start_background_sync(self):
        """Start background sync thread"""
        if self._sync_thread is not None and self._sync_thread.is_alive():
            print("   ⚠️ Background sync already running")
            return

        self._stop_sync.clear()
        self._sync_thread = threading.Thread(
            target=self._background_sync_loop,
            daemon=True,
            name="TieredBalanceSyncThread"
        )
        self._sync_thread.start()
        print(f"   ✅ Background sync started (every {self.sync_interval}s)")

    def stop_background_sync(self):
        """Stop background sync thread"""
        self._stop_sync.set()
        if self._sync_thread:
            self._sync_thread.join(timeout=5)
            print("   ✅ Background sync stopped")

    def _background_sync_loop(self):
        """Background sync loop"""
        while not self._stop_sync.is_set():
            try:
                self.sync_now()
            except Exception as e:
                print(f"   ⚠️ Background sync error: {e}")

            # Wait for next sync interval or stop signal
            self._stop_sync.wait(timeout=self.sync_interval)

    def get_status(self) -> Dict:
        """Get current service status"""
        return {
            'service': 'TieredBalanceSyncService',
            'running': self._sync_thread is not None and self._sync_thread.is_alive(),
            'sync_interval': self.sync_interval,
            'last_sync': self.last_sync_time.isoformat() if self.last_sync_time else None,
            'last_balance': self.last_balance,
            'sync_count': self.sync_count,
            'tiered_allocation': self.tiered_allocation.get_status() if self.tiered_allocation else None
        }

    def print_status(self):
        """Print formatted status"""
        status = self.get_status()

        print("\n" + "="*60)
        print("📊 TIERED BALANCE SYNC SERVICE STATUS")
        print("="*60)
        print(f"Running: {'✅ Yes' if status['running'] else '❌ No'}")
        print(f"Sync Interval: {status['sync_interval']}s")
        print(f"Last Sync: {status['last_sync'] or 'Never'}")
        print(f"Last Balance: ${status['last_balance']:.2f}")
        print(f"Sync Count: {status['sync_count']}")

        if self.tiered_allocation:
            self.tiered_allocation.print_status()


# Singleton instance
_sync_service: Optional[TieredBalanceSyncService] = None


def get_sync_service(
    exchange=None,
    tiered_allocation=None,
    sync_interval: int = 300
) -> TieredBalanceSyncService:
    """Get or create sync service singleton"""
    global _sync_service

    if _sync_service is None:
        _sync_service = TieredBalanceSyncService(
            exchange=exchange,
            tiered_allocation=tiered_allocation,
            sync_interval=sync_interval
        )

    return _sync_service


# Standalone execution
if __name__ == "__main__":
    print("="*60)
    print("TIERED BALANCE SYNC SERVICE - STANDALONE MODE")
    print("="*60)

    # Create service
    service = TieredBalanceSyncService(sync_interval=60)  # 1 minute for testing

    # Initial sync
    print("\n🔄 Performing initial sync...")
    result = service.sync_now(force=True)
    print(f"   Result: {result}")

    # Print status
    service.print_status()

    # Start background sync
    print("\n🚀 Starting background sync (Ctrl+C to stop)...")
    service.start_background_sync()

    try:
        while True:
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n\n⏹️ Stopping service...")
        service.stop_background_sync()
        print("Done.")
