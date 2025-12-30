"""
Position Sync Integration - V1.3.0
Integration layer to connect EnhancedPositionSync with the main trading system

This module provides:
1. Drop-in replacement for reconcile_with_exchange()
2. Automatic state synchronization for all tracking dictionaries
3. Backward compatibility with existing code
4. Real-time sync callbacks for position lifecycle events
"""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable, Any
import structlog

from enhanced_position_sync import EnhancedPositionSync, PositionLifecycleState, SyncStatus

logger = structlog.get_logger(__name__)


class PositionSyncIntegration:
    """
    Integration layer between EnhancedPositionSync and the trading system

    Provides backward-compatible interface while using the new sync system
    """

    def __init__(self, trading_system):
        """
        Initialize integration with trading system

        Args:
            trading_system: Reference to AIXYZContinuousProfitSystem instance
        """
        self.system = trading_system
        self.sync = EnhancedPositionSync(trading_system.exchange)

        # Callbacks for position events
        self._on_position_added: List[Callable] = []
        self._on_position_removed: List[Callable] = []
        self._on_position_updated: List[Callable] = []

        # Track last sync time for each position
        self._last_position_sync: Dict[str, float] = {}

        logger.info("PositionSyncIntegration initialized")

    def register_callbacks(self,
                          on_added: Callable = None,
                          on_removed: Callable = None,
                          on_updated: Callable = None):
        """Register callbacks for position lifecycle events"""
        if on_added:
            self._on_position_added.append(on_added)
        if on_removed:
            self._on_position_removed.append(on_removed)
        if on_updated:
            self._on_position_updated.append(on_updated)

    def reconcile_with_exchange(self) -> Dict[str, Any]:
        """
        Enhanced reconcile_with_exchange - drop-in replacement

        Syncs with exchange AND updates all tracking dictionaries

        Returns:
            Dict with sync results
        """
        try:
            # Perform sync with exchange
            sync_result = self.sync.sync_with_exchange_sync()

            if 'error' in sync_result:
                logger.error(f"Sync failed: {sync_result['error']}")
                return sync_result

            # Get all position states
            states = self.sync.get_all_position_states()

            # Update trading system dictionaries
            self._update_system_state(states)

            # Handle added positions
            for symbol in sync_result.get('added', []):
                state = states.get(symbol)
                if state:
                    self._handle_position_added(symbol, state)

            # Handle removed positions
            for symbol in sync_result.get('removed', []):
                self._handle_position_removed(symbol)

            # Handle updated positions
            for symbol in sync_result.get('synced', []):
                state = states.get(symbol)
                if state:
                    self._handle_position_updated(symbol, state)

            return sync_result

        except Exception as e:
            logger.error(f"Reconcile with exchange failed: {e}")
            return {'error': str(e)}

    def _update_system_state(self, states: Dict[str, PositionLifecycleState]):
        """Update all trading system tracking dictionaries from sync state"""

        # Build new dictionaries from sync state
        new_active_positions = {}
        new_position_zones = {}
        new_averaging_steps = {}
        new_peak_upnl = {}
        new_peak_upnl_timestamps = {}
        new_surplus_dump_stage = {}
        new_original_sizes = {}
        new_position_multipliers = {}

        for symbol, state in states.items():
            # Active positions
            new_active_positions[symbol] = {
                'entry_price': state.entry_price,
                'amount': state.amount,
                'side': state.side,
                'leverage': state.leverage,
                'opened_at': state.opened_at
            }

            # Position zones
            new_position_zones[symbol] = state.current_zone

            # Averaging steps
            new_averaging_steps[symbol] = state.averaging_steps

            # Peak UPNL
            new_peak_upnl[symbol] = state.peak_upnl
            new_peak_upnl_timestamps[symbol] = state.peak_upnl_timestamp

            # Surplus dump stage
            new_surplus_dump_stage[symbol] = state.surplus_dump_stage

            # Original sizes
            new_original_sizes[symbol] = state.original_size

            # Position multipliers
            new_position_multipliers[symbol] = state.averaging_multipliers

            # Fibonacci configs (if present)
            if state.fibonacci_config and hasattr(self.system, 'fibonacci_configs'):
                self.system.fibonacci_configs[symbol] = state.fibonacci_config

        # Update system dictionaries atomically
        self.system.active_positions = new_active_positions
        self.system.position_zones = new_position_zones
        self.system.averaging_steps = new_averaging_steps
        self.system.peak_upnl = new_peak_upnl
        self.system.peak_upnl_timestamps = new_peak_upnl_timestamps
        self.system.surplus_dump_stage = new_surplus_dump_stage
        self.system.original_sizes = new_original_sizes
        self.system.position_multipliers = new_position_multipliers

        # Sync partial closer state
        if hasattr(self.system, 'partial_closer'):
            for symbol, state in states.items():
                if state.partial_close_executed:
                    # Restore ladder state
                    self.system.partial_closer.initialize_ladder(symbol)
                    ladder = self.system.partial_closer.position_ladders.get(symbol, [])
                    for i, executed in enumerate(state.partial_close_executed):
                        if i < len(ladder):
                            ladder[i].executed = executed

        # Sync ATR trailing stop state
        if hasattr(self.system, 'trailing_atr_stop'):
            for symbol, state in states.items():
                if state.peak_price > 0:
                    self.system.trailing_atr_stop.peak_prices[symbol] = state.peak_price

        # Sync velocity profit taking state
        if hasattr(self.system, 'velocity_profit_taker'):
            for symbol, state in states.items():
                if state.position_open_time:
                    try:
                        open_time = datetime.fromisoformat(state.position_open_time.replace('Z', '+00:00'))
                        self.system.velocity_profit_taker.position_open_times[symbol] = open_time.timestamp()
                    except:
                        pass

    def _handle_position_added(self, symbol: str, state: PositionLifecycleState):
        """Handle newly detected position"""
        logger.info(f"New position detected: {symbol}")

        # Initialize partial closer ladder
        if hasattr(self.system, 'partial_closer'):
            self.system.partial_closer.initialize_ladder(symbol)

        # Initialize ATR trailing stop
        if hasattr(self.system, 'trailing_atr_stop'):
            self.system.trailing_atr_stop.peak_prices[symbol] = state.exchange_mark_price

        # Initialize velocity tracker
        if hasattr(self.system, 'velocity_profit_taker'):
            self.system.velocity_profit_taker.position_open_times[symbol] = time.time()

        # Calculate Fibonacci config if not present
        if not state.fibonacci_config and hasattr(self.system, 'get_fibonacci_parameters'):
            try:
                volatility = self.system.get_recent_volatility(symbol)
                direction = 'buy' if state.side == 'buy' else 'sell'
                fib_params = self.system.get_fibonacci_parameters(symbol, direction, volatility, 0.5)
                if fib_params and fib_params.get('safe_to_trade'):
                    self.sync.update_averaging_state(symbol,
                                                     state.averaging_steps,
                                                     fibonacci_config=fib_params)
                    self.system.fibonacci_configs[symbol] = fib_params
            except Exception as e:
                logger.warning(f"Failed to calculate Fibonacci config for {symbol}: {e}")

        # Fire callbacks
        for callback in self._on_position_added:
            try:
                callback(symbol, state)
            except Exception as e:
                logger.error(f"Position added callback error: {e}")

    def _handle_position_removed(self, symbol: str):
        """Handle position that was closed"""
        logger.info(f"Position closed: {symbol}")

        # Clean up partial closer
        if hasattr(self.system, 'partial_closer'):
            self.system.partial_closer.reset_ladder(symbol)

        # Clean up ATR trailing stop
        if hasattr(self.system, 'trailing_atr_stop'):
            self.system.trailing_atr_stop.reset_peak(symbol)

        # Clean up velocity tracker
        if hasattr(self.system, 'velocity_profit_taker'):
            self.system.velocity_profit_taker.position_open_times.pop(symbol, None)

        # Clean up Fibonacci config
        if hasattr(self.system, 'fibonacci_configs'):
            self.system.fibonacci_configs.pop(symbol, None)

        # Fire callbacks
        for callback in self._on_position_removed:
            try:
                callback(symbol)
            except Exception as e:
                logger.error(f"Position removed callback error: {e}")

    def _handle_position_updated(self, symbol: str, state: PositionLifecycleState):
        """Handle position update"""
        # Check for significant changes
        last_sync = self._last_position_sync.get(symbol, 0)
        if time.time() - last_sync < 1:
            return  # Skip if synced very recently

        self._last_position_sync[symbol] = time.time()

        # Fire callbacks
        for callback in self._on_position_updated:
            try:
                callback(symbol, state)
            except Exception as e:
                logger.error(f"Position updated callback error: {e}")

    # ==================== State Update Proxies ====================

    def update_averaging_state(self, symbol: str, steps: int,
                               multipliers: List[float] = None,
                               last_price: float = None,
                               fibonacci_config: Dict = None):
        """Update averaging state and sync to Redis"""
        # Update local system state
        self.system.averaging_steps[symbol] = steps
        if multipliers:
            self.system.position_multipliers[symbol] = multipliers
        if fibonacci_config:
            self.system.fibonacci_configs[symbol] = fibonacci_config

        # Sync to Redis
        return self.sync.update_averaging_state(symbol, steps, multipliers,
                                                last_price, fibonacci_config)

    def update_surplus_dump_state(self, symbol: str, stage: int,
                                  original_size: float = None):
        """Update surplus dump state and sync to Redis"""
        # Update local system state
        self.system.surplus_dump_stage[symbol] = stage
        if original_size is not None:
            self.system.original_sizes[symbol] = original_size

        # Sync to Redis
        return self.sync.update_surplus_dump_state(symbol, stage, original_size)

    def update_peak_upnl(self, symbol: str, peak: float):
        """Update peak UPNL and sync to Redis"""
        # Update local system state
        if peak > self.system.peak_upnl.get(symbol, 0):
            self.system.peak_upnl[symbol] = peak
            self.system.peak_upnl_timestamps[symbol] = datetime.now(timezone.utc).isoformat()

        # Sync to Redis
        return self.sync.update_peak_upnl(symbol, peak)

    def update_zone(self, symbol: str, zone: str):
        """Update position zone and sync to Redis"""
        # Update local system state
        self.system.position_zones[symbol] = zone

        # Sync to Redis
        return self.sync.update_zone(symbol, zone)

    def update_partial_close_state(self, symbol: str, stage: int,
                                   executed: List[bool] = None):
        """Update partial close state and sync to Redis"""
        # Sync to Redis
        return self.sync.update_partial_close_state(symbol, stage, executed)

    def update_atr_stop_state(self, symbol: str, stop_price: float,
                              atr_value: float, peak_price: float = None):
        """Update ATR stop state and sync to Redis"""
        # Update local system state
        if hasattr(self.system, 'trailing_atr_stop') and peak_price:
            self.system.trailing_atr_stop.peak_prices[symbol] = peak_price

        # Sync to Redis
        return self.sync.update_atr_stop_state(symbol, stop_price, atr_value, peak_price)

    # ==================== Cooldown Management ====================

    def is_in_cooldown(self, symbol: str) -> tuple:
        """Check if symbol is in cooldown period"""
        return self.sync.is_in_cooldown(symbol)

    def get_cooldown_symbols(self) -> Dict[str, float]:
        """Get all symbols in cooldown with remaining time"""
        result = {}
        for symbol in self.sync._cooldown_cache:
            in_cooldown, remaining = self.sync.is_in_cooldown(symbol)
            if in_cooldown:
                result[symbol] = remaining
        return result

    # ==================== Diagnostics ====================

    def get_sync_status(self) -> Dict:
        """Get sync status and diagnostics"""
        return self.sync.get_sync_status()

    def force_full_sync(self) -> Dict:
        """Force a full synchronization"""
        result = self.sync.force_full_sync()
        if 'error' not in result:
            states = self.sync.get_all_position_states()
            self._update_system_state(states)
        return result

    def export_state(self) -> Dict:
        """Export current state for debugging"""
        return {
            'sync_status': self.get_sync_status(),
            'active_positions': dict(self.system.active_positions),
            'position_zones': dict(self.system.position_zones),
            'averaging_steps': dict(self.system.averaging_steps),
            'peak_upnl': dict(self.system.peak_upnl),
            'surplus_dump_stage': dict(self.system.surplus_dump_stage),
            'original_sizes': dict(self.system.original_sizes),
            'cooldowns': self.get_cooldown_symbols()
        }


def patch_trading_system(trading_system) -> PositionSyncIntegration:
    """
    Patch the trading system to use enhanced position sync

    Usage:
        sync_integration = patch_trading_system(self)
        # Now use sync_integration.reconcile_with_exchange() instead of self.reconcile_with_exchange()

    Args:
        trading_system: AIXYZContinuousProfitSystem instance

    Returns:
        PositionSyncIntegration instance
    """
    integration = PositionSyncIntegration(trading_system)

    # Store reference on system
    trading_system._sync_integration = integration

    # Optionally replace reconcile method
    # trading_system.reconcile_with_exchange = integration.reconcile_with_exchange

    logger.info("Trading system patched with enhanced position sync")

    return integration
