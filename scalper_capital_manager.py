#!/usr/bin/env python3
"""
Scalper Capital Manager V1.1.0 - Unified Capital Allocation for Quick Scalper
==============================================================================

Consortium Design: Claude (Opus 4.5) + Grok (grok-2-latest)
Date: January 17, 2026

V1.1.0: Now uses UnifiedCapitalCoordinator for correlated allocation with Main Engine

Aligns Quick Scalper V3 with Main Engine's capital allocation system:
- Dynamic capital split by HMM regime (shared via Redis)
- Dynamic max positions based on regime + equity
- Dynamic position sizing based on equity + risk
- Conflict resolution with Main Engine (checks Main's positions)

Integration with:
- UnifiedCapitalCoordinator (Shared capital state via Redis)
- TieredCapitalAllocation (Main Engine)
- VolatilityRegimeHMM (Shared)
"""

import os
import redis
from typing import Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Import UnifiedCapitalCoordinator
try:
    from unified_capital_coordinator import (
        UnifiedCapitalCoordinator, get_capital_coordinator, REGIME_ALLOCATION
    )
    COORDINATOR_AVAILABLE = True
except ImportError:
    COORDINATOR_AVAILABLE = False
    print("  ⚠ UnifiedCapitalCoordinator not available - using standalone mode")


# ========== DYNAMIC CAPITAL ALLOCATION (Grok Recommendation) ==========
# Split between Scalper and Main Engine by HMM regime

DYNAMIC_CAPITAL_ALLOCATION = {
    'low_vol': {'scalper': 0.10, 'main': 0.90},    # Conservative - scalper gets 10%
    'normal_vol': {'scalper': 0.20, 'main': 0.80},  # Balanced - scalper gets 20%
    'high_vol': {'scalper': 0.30, 'main': 0.70},    # Aggressive - scalper gets 30%
    'crisis': {'scalper': 0.05, 'main': 0.95}       # Minimal - scalper gets 5%
}

# Regime factors for position calculations
REGIME_FACTORS = {
    'low_vol': 1.0,
    'normal_vol': 1.5,
    'high_vol': 2.0,
    'crisis': 0.5
}

# Regime adjustments for position sizing
REGIME_SIZE_ADJUSTMENTS = {
    'low_vol': 0.8,
    'normal_vol': 1.0,
    'high_vol': 1.2,
    'crisis': 0.5
}

# Tier factors (aligned with Main Engine's 3-tier system)
TIER_FACTORS = {
    1: 1.0,   # REGULAR_BUSINESS
    2: 1.2,   # MARKET_ADVERSITY
    3: 1.5    # BLACK_SWAN
}


@dataclass
class ScalperCapitalConfig:
    """Configuration for scalper capital at current regime"""
    regime: str
    total_equity: float
    allocated_capital: float
    available_capital: float
    max_positions: int
    position_size: float
    main_tier: int
    allocation_pct: float


def calculate_scalper_max_positions(
    total_capital: float,
    regime: str,
    current_equity: float,
    main_tier: int = 1
) -> int:
    """
    Calculate dynamic max positions for scalper.

    Formula: base * regime_factor * tier_factor * equity_ratio * 10

    Args:
        total_capital: Total account capital
        regime: Current HMM regime (low_vol, normal_vol, high_vol, crisis)
        current_equity: Current account equity
        main_tier: Main Engine's current tier (1, 2, or 3)

    Returns:
        Max positions allowed (1-5)
    """
    base = 1
    regime_factor = REGIME_FACTORS.get(regime, 1.5)
    tier_factor = TIER_FACTORS.get(main_tier, 1.0)

    # Equity ratio (how much equity we have vs initial capital)
    equity_ratio = current_equity / total_capital if total_capital > 0 else 1.0

    # Calculate max positions
    max_pos = int(base * regime_factor * tier_factor * equity_ratio * 10)

    # Clamp between 1 and 5
    return max(1, min(5, max_pos))


def calculate_position_size(
    current_equity: float,
    regime: str,
    risk_factor: float = 0.01
) -> float:
    """
    Calculate dynamic position size based on equity and regime.

    Formula: equity * risk_factor * regime_adjustment

    Args:
        current_equity: Current account equity
        regime: Current HMM regime
        risk_factor: Percentage of equity to risk (default 1%)

    Returns:
        Position size in USD (clamped between $10 and $100)
    """
    # Base risk amount (1% of equity)
    risk_amount = current_equity * risk_factor

    # Regime adjustment
    regime_adj = REGIME_SIZE_ADJUSTMENTS.get(regime, 1.0)

    # Calculate size
    size = risk_amount * regime_adj

    # Clamp between $10 and $100
    return max(10.0, min(size, 100.0))


class ScalperCapitalManager:
    """
    Dynamic Capital Manager for Quick Scalper V3

    V1.1.0: Uses UnifiedCapitalCoordinator for correlated allocation with Main Engine

    Manages:
    - Capital allocation between Scalper and Main Engine (via shared Redis state)
    - Dynamic position limits by HMM regime
    - Dynamic position sizing
    - Conflict resolution with Main Engine
    """

    def __init__(
        self,
        total_capital: float = None,
        redis_host: str = None,
        redis_port: int = None
    ):
        """
        Initialize ScalperCapitalManager.

        Args:
            total_capital: Total account capital (from env if None)
            redis_host: Redis host for state sharing
            redis_port: Redis port
        """
        # Capital setup
        self.total_capital = total_capital or float(os.getenv('INITIAL_BALANCE', 400.0))
        self.current_equity = self.total_capital

        # Regime state
        self.current_regime = 'normal_vol'
        self.main_tier = 1  # Default to REGULAR_BUSINESS

        # V1.1.0: Use UnifiedCapitalCoordinator if available
        self.coordinator = None
        if COORDINATOR_AVAILABLE:
            try:
                self.coordinator = get_capital_coordinator(
                    total_equity=self.total_capital,
                    max_main_positions=30
                )
                print("  ✓ Using UnifiedCapitalCoordinator (correlated with Main Engine)")
            except Exception as e:
                print(f"  ⚠ Coordinator init failed: {e}")

        # Position tracking (fallback if coordinator not available)
        self.used_capital = 0.0
        self.active_positions: Dict[str, float] = {}  # symbol -> margin used

        # Redis for state sharing with Main Engine
        self.redis_host = redis_host or os.getenv('REDIS_HOST', 'redis')
        self.redis_port = redis_port or int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = None
        self._init_redis()

        print(f"ScalperCapitalManager V1.0.0 initialized")
        print(f"   Total Capital: ${self.total_capital:.2f}")
        print(f"   Initial Regime: {self.current_regime}")
        print(f"   Scalper Allocation: {DYNAMIC_CAPITAL_ALLOCATION[self.current_regime]['scalper']*100:.0f}%")

    def _init_redis(self):
        """Initialize Redis connection"""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=0,
                decode_responses=True
            )
            self.redis_client.ping()
        except Exception as e:
            print(f"   Warning: Redis connection failed: {e}")
            self.redis_client = None

    def update_state(
        self,
        regime: str = None,
        equity: float = None,
        main_tier: int = None
    ):
        """
        Update manager state from external sources.

        Args:
            regime: Current HMM regime
            equity: Current account equity
            main_tier: Main Engine's current tier (1-3)
        """
        if regime:
            self.current_regime = regime.lower()
        if equity:
            self.current_equity = equity
        if main_tier:
            self.main_tier = main_tier

        # V1.1.0: Sync with UnifiedCapitalCoordinator
        if self.coordinator:
            if regime:
                self.coordinator.update_regime(regime)
            if equity:
                self.coordinator.update_equity(equity)

    def get_allocated_capital(self) -> float:
        """
        Get capital allocated to scalper for current regime.

        Returns:
            Allocated capital in USD
        """
        # V1.1.0: Use coordinator if available
        if self.coordinator:
            alloc = self.coordinator.get_scalper_allocation()
            return alloc['allocated']

        # Fallback
        allocation = DYNAMIC_CAPITAL_ALLOCATION.get(
            self.current_regime,
            DYNAMIC_CAPITAL_ALLOCATION['normal_vol']
        )
        return self.current_equity * allocation['scalper']

    def get_available_capital(self) -> float:
        """
        Get available capital (allocated - used).

        Returns:
            Available capital in USD
        """
        # V1.1.0: Use coordinator if available
        if self.coordinator:
            alloc = self.coordinator.get_scalper_allocation()
            return alloc['available']

        # Fallback
        allocated = self.get_allocated_capital()
        return max(0.0, allocated - self.used_capital)

    def get_max_positions(self) -> int:
        """
        Get dynamic max positions for current state.

        Returns:
            Max positions allowed
        """
        # V1.1.0: Use coordinator if available
        if self.coordinator:
            alloc = self.coordinator.get_scalper_allocation()
            return alloc['max_positions']

        # Fallback
        return calculate_scalper_max_positions(
            self.total_capital,
            self.current_regime,
            self.current_equity,
            self.main_tier
        )

    def get_position_size(self, risk_factor: float = 0.01) -> float:
        """
        Get dynamic position size for current state.

        Args:
            risk_factor: Risk percentage (default 1%)

        Returns:
            Position size in USD
        """
        return calculate_position_size(
            self.current_equity,
            self.current_regime,
            risk_factor
        )

    def get_config(self) -> ScalperCapitalConfig:
        """
        Get full configuration for current state.

        Returns:
            ScalperCapitalConfig dataclass
        """
        allocation = DYNAMIC_CAPITAL_ALLOCATION.get(
            self.current_regime,
            DYNAMIC_CAPITAL_ALLOCATION['normal_vol']
        )

        return ScalperCapitalConfig(
            regime=self.current_regime,
            total_equity=self.current_equity,
            allocated_capital=self.get_allocated_capital(),
            available_capital=self.get_available_capital(),
            max_positions=self.get_max_positions(),
            position_size=self.get_position_size(),
            main_tier=self.main_tier,
            allocation_pct=allocation['scalper']
        )

    def can_open_position(self, margin_required: float = None) -> Tuple[bool, str]:
        """
        Check if a new position can be opened.

        Args:
            margin_required: Required margin (uses dynamic size if None)

        Returns:
            Tuple of (can_open, reason)
        """
        # Check position limit
        current_count = len(self.active_positions)
        max_pos = self.get_max_positions()

        if current_count >= max_pos:
            return False, f"Position limit reached: {current_count}/{max_pos} for {self.current_regime}"

        # Check capital
        margin = margin_required or self.get_position_size()
        available = self.get_available_capital()

        if margin > available:
            return False, f"Insufficient capital: need ${margin:.2f}, have ${available:.2f}"

        return True, f"OK: {current_count}/{max_pos} positions, ${available:.2f} available"

    def check_main_engine_conflict(self, symbol: str) -> Tuple[bool, str]:
        """
        Check if Main Engine has position in symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Tuple of (has_conflict, reason)
        """
        # V1.1.0: Use coordinator's main positions tracking
        if self.coordinator and self.coordinator.redis:
            try:
                main_has = self.coordinator.redis.hexists(
                    self.coordinator.REDIS_KEY_MAIN_POSITIONS,
                    symbol
                )
                if main_has:
                    return True, f"Main Engine has position in {symbol}"
                return False, "No conflict"
            except Exception as e:
                pass  # Fall through to legacy check

        # Fallback: Check legacy position key
        if not self.redis_client:
            return False, "No Redis - cannot check conflicts"

        try:
            key = f"position:{symbol}"
            exists = self.redis_client.exists(key)
            if exists:
                return True, f"Main Engine has position in {symbol}"
            return False, "No conflict"
        except Exception as e:
            return False, f"Conflict check error: {e}"

    def allocate_position(self, symbol: str, margin: float = None) -> Dict:
        """
        Allocate capital for a new position.

        Args:
            symbol: Trading symbol
            margin: Margin to allocate (uses dynamic size if None)

        Returns:
            Allocation result dict
        """
        margin = margin or self.get_position_size()

        # V1.1.0: Use coordinator if available
        if self.coordinator:
            success, msg = self.coordinator.scalper_allocate(symbol, margin)
            if success:
                # Also track locally for fallback
                self.active_positions[symbol] = margin
                self.used_capital += margin
                alloc = self.coordinator.get_scalper_allocation()
                return {
                    'success': True,
                    'symbol': symbol,
                    'margin': margin,
                    'positions': alloc['positions'],
                    'max_positions': alloc['max_positions'],
                    'used_capital': alloc['used'],
                    'available_capital': alloc['available'],
                    'coordinated': True
                }
            return {'success': False, 'reason': msg, 'coordinated': True}

        # Fallback: standalone mode
        can_open, reason = self.can_open_position(margin)
        if not can_open:
            return {'success': False, 'reason': reason}

        has_conflict, conflict_reason = self.check_main_engine_conflict(symbol)
        if has_conflict:
            return {'success': False, 'reason': conflict_reason}

        self.active_positions[symbol] = margin
        self.used_capital += margin

        return {
            'success': True,
            'symbol': symbol,
            'margin': margin,
            'positions': len(self.active_positions),
            'max_positions': self.get_max_positions(),
            'used_capital': self.used_capital,
            'available_capital': self.get_available_capital(),
            'coordinated': False
        }

    def release_position(self, symbol: str) -> Dict:
        """
        Release capital when closing a position.

        Args:
            symbol: Trading symbol

        Returns:
            Release result dict
        """
        # V1.1.0: Release from coordinator first
        if self.coordinator:
            self.coordinator.scalper_release(symbol)

        if symbol not in self.active_positions:
            return {'success': False, 'reason': f'No position found for {symbol}'}

        margin = self.active_positions.pop(symbol)
        self.used_capital = max(0.0, self.used_capital - margin)

        return {
            'success': True,
            'symbol': symbol,
            'margin_released': margin,
            'positions_remaining': len(self.active_positions),
            'available_capital': self.get_available_capital()
        }

    def sync_from_exchange(self, positions: list, equity: float):
        """
        Sync state from exchange positions.

        Args:
            positions: List of position dicts from exchange
            equity: Current equity
        """
        self.current_equity = equity
        self.active_positions.clear()
        self.used_capital = 0.0

        for pos in positions:
            symbol = pos.get('symbol', '')
            margin = abs(pos.get('initialMargin', 0)) or abs(pos.get('margin', 0))

            # Only track if this is a scalper position (check by source/tag if available)
            # For now, track all positions
            self.active_positions[symbol] = margin
            self.used_capital += margin

    def print_status(self):
        """Print formatted status"""
        config = self.get_config()

        print("\n" + "=" * 60)
        print("SCALPER CAPITAL MANAGER STATUS")
        print("=" * 60)
        print(f"Regime: {config.regime.upper()}")
        print(f"Total Equity: ${config.total_equity:.2f}")
        print(f"Allocation: {config.allocation_pct*100:.0f}% = ${config.allocated_capital:.2f}")
        print(f"Available: ${config.available_capital:.2f}")
        print(f"Positions: {len(self.active_positions)}/{config.max_positions}")
        print(f"Position Size: ${config.position_size:.2f}")
        print(f"Main Tier: {config.main_tier}")
        print("=" * 60)


# Singleton instance
_capital_manager: Optional[ScalperCapitalManager] = None


def get_scalper_capital_manager(
    total_capital: float = None
) -> ScalperCapitalManager:
    """
    Get or create the scalper capital manager singleton.

    Args:
        total_capital: Total capital (uses env if None)

    Returns:
        ScalperCapitalManager instance
    """
    global _capital_manager

    if _capital_manager is None:
        _capital_manager = ScalperCapitalManager(total_capital)

    return _capital_manager


# ========== TESTING ==========
if __name__ == '__main__':
    print("Testing ScalperCapitalManager V1.0.0")
    print("=" * 60)

    # Create manager
    manager = ScalperCapitalManager(total_capital=400.0)

    # Test different regimes
    for regime in ['low_vol', 'normal_vol', 'high_vol', 'crisis']:
        print(f"\n--- Regime: {regime.upper()} ---")
        manager.update_state(regime=regime)
        config = manager.get_config()
        print(f"  Allocation: {config.allocation_pct*100:.0f}% = ${config.allocated_capital:.2f}")
        print(f"  Max Positions: {config.max_positions}")
        print(f"  Position Size: ${config.position_size:.2f}")

    # Test position allocation
    print("\n--- Position Allocation Test ---")
    manager.update_state(regime='normal_vol')

    result = manager.allocate_position('BTC/USDT:USDT')
    print(f"Allocate BTC: {result}")

    result = manager.allocate_position('ETH/USDT:USDT')
    print(f"Allocate ETH: {result}")

    manager.print_status()

    # Release
    result = manager.release_position('BTC/USDT:USDT')
    print(f"Release BTC: {result}")

    manager.print_status()
