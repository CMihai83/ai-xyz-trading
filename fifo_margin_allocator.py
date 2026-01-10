#!/usr/bin/env python3
"""
FIFO Margin Allocation System
Allocates additional capital to positions that NEED it first.
When total capital per position is increased (e.g., $25 → $40),
the first position that needs the capital gets it.

"Needs capital" = position has exhausted averaging capital and requires more
to continue averaging or for liquidation protection.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
import structlog
from position_sizing_config import PositionSizingConfig

logger = structlog.get_logger(__name__)


@dataclass
class PositionMarginState:
    """Tracks margin state for a single position"""
    symbol: str
    open_time: datetime
    current_margin: float  # Total margin used so far
    allocated_capital: float  # Total capital allocated to this position
    averaging_steps: int  # Number of averaging steps completed
    needs_additional: bool = False  # Flag if position needs more capital
    needed_since: datetime = None  # When position started needing capital (for FIFO priority)

    def margin_available(self) -> float:
        """Calculate remaining margin available for averaging"""
        return max(0, self.allocated_capital - self.current_margin)

    def can_add_margin(self, amount: float) -> bool:
        """Check if additional margin can be added"""
        return self.current_margin + amount <= self.allocated_capital

    def set_needs_capital(self, needs: bool):
        """Set whether position needs additional capital"""
        if needs and not self.needs_additional:
            # First time needing capital - record timestamp for FIFO
            self.needed_since = datetime.now()
        elif not needs:
            self.needed_since = None
        self.needs_additional = needs


@dataclass
class AllocationResult:
    """Result of FIFO allocation"""
    symbol: str
    previous_capital: float
    new_capital: float
    additional_margin: float
    priority_rank: int


class FIFOMarginAllocator:
    """
    Manages FIFO-based margin allocation across positions.

    When capital increases:
    1. Get all active positions sorted by open_time (oldest first)
    2. Allocate extra capital to oldest positions first
    3. Each position gets up to MAX_CAPITAL_PER_POSITION
    4. Track allocations for reporting
    """

    def __init__(self):
        self.positions: Dict[str, PositionMarginState] = {}
        self.base_capital = PositionSizingConfig.TOTAL_CAPITAL
        self.min_capital = PositionSizingConfig.MIN_CAPITAL_PER_POSITION
        self.max_capital = PositionSizingConfig.MAX_CAPITAL_PER_POSITION

        logger.info(
            "FIFO Margin Allocator initialized",
            base_capital=self.base_capital,
            min_capital=self.min_capital,
            max_capital=self.max_capital
        )

    def register_position(
        self,
        symbol: str,
        open_time: datetime,
        initial_margin: float
    ) -> PositionMarginState:
        """
        Register a new position for FIFO tracking.

        Args:
            symbol: Trading symbol
            open_time: Position open timestamp
            initial_margin: Initial margin used

        Returns:
            PositionMarginState for the new position
        """
        state = PositionMarginState(
            symbol=symbol,
            open_time=open_time,
            current_margin=initial_margin,
            allocated_capital=self.base_capital,
            averaging_steps=0,
            needs_additional=False
        )
        self.positions[symbol] = state

        logger.info(
            "Position registered for FIFO allocation",
            symbol=symbol,
            open_time=open_time.isoformat(),
            initial_margin=initial_margin,
            allocated_capital=self.base_capital
        )

        return state

    def update_margin_used(
        self,
        symbol: str,
        margin_used: float,
        averaging_step: int
    ) -> Optional[PositionMarginState]:
        """
        Update margin used for a position after averaging.

        Args:
            symbol: Trading symbol
            margin_used: New total margin used
            averaging_step: Current averaging step number

        Returns:
            Updated PositionMarginState or None if not found
        """
        if symbol not in self.positions:
            logger.warning("Position not found for margin update", symbol=symbol)
            return None

        state = self.positions[symbol]
        state.current_margin = margin_used
        state.averaging_steps = averaging_step

        # Check if position needs additional capital
        # Needs capital if remaining margin is less than one averaging step
        needs_more = state.margin_available() < PositionSizingConfig.BASE_MARGIN_SIZE
        state.set_needs_capital(needs_more)

        logger.debug(
            "Margin updated",
            symbol=symbol,
            margin_used=margin_used,
            remaining=state.margin_available(),
            needs_additional=state.needs_additional,
            needed_since=state.needed_since.isoformat() if state.needed_since else None
        )

        return state

    def remove_position(self, symbol: str) -> bool:
        """Remove a closed position from tracking"""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info("Position removed from FIFO tracking", symbol=symbol)
            return True
        return False

    def get_positions_by_priority(self) -> List[PositionMarginState]:
        """
        Get all positions sorted by FIFO priority.
        Priority: Positions that need capital first, sorted by when they started needing it.

        Returns:
            List of positions - those needing capital first (by needed_since), then others
        """
        # Separate positions that need capital from those that don't
        needs_capital = [p for p in self.positions.values() if p.needs_additional]
        has_enough = [p for p in self.positions.values() if not p.needs_additional]

        # Sort positions needing capital by when they started needing it (FIFO)
        needs_capital.sort(key=lambda p: p.needed_since or datetime.max)

        # Others sorted by open time (in case they need capital later)
        has_enough.sort(key=lambda p: p.open_time)

        return needs_capital + has_enough

    def allocate_additional_capital(
        self,
        new_total_capital: float
    ) -> List[AllocationResult]:
        """
        Allocate additional capital using FIFO priority.

        First position that NEEDS capital gets it first.
        "Needs" = position has exhausted its allocated capital for averaging.

        Args:
            new_total_capital: New total capital per position (e.g., $40)

        Returns:
            List of allocation results showing what each position received
        """
        if new_total_capital <= self.base_capital:
            logger.warning(
                "New capital must be greater than base",
                new_capital=new_total_capital,
                base_capital=self.base_capital
            )
            return []

        if new_total_capital > self.max_capital:
            logger.warning(
                "New capital exceeds maximum, capping",
                requested=new_total_capital,
                max_capital=self.max_capital
            )
            new_total_capital = self.max_capital

        results: List[AllocationResult] = []

        # Get positions in FIFO order (those needing capital first)
        sorted_positions = self.get_positions_by_priority()

        for rank, position in enumerate(sorted_positions, 1):
            # Only allocate to positions that NEED capital
            if not position.needs_additional:
                continue

            previous_capital = position.allocated_capital

            # Allocate additional capital
            new_capital = min(new_total_capital, self.max_capital)
            additional_margin = new_capital - previous_capital

            position.allocated_capital = new_capital
            position.set_needs_capital(False)  # Reset need flag

            result = AllocationResult(
                symbol=position.symbol,
                previous_capital=previous_capital,
                new_capital=new_capital,
                additional_margin=additional_margin,
                priority_rank=rank
            )
            results.append(result)

            logger.info(
                "FIFO capital allocated (position needed it)",
                symbol=position.symbol,
                rank=rank,
                previous=previous_capital,
                new=new_capital,
                additional=additional_margin
            )

        # Update the base capital for new positions
        self.base_capital = new_total_capital
        PositionSizingConfig.update_total_capital(new_total_capital)

        return results

    def get_allocation_for_symbol(self, symbol: str) -> Optional[float]:
        """Get current capital allocation for a symbol"""
        if symbol in self.positions:
            return self.positions[symbol].allocated_capital
        return None

    def get_available_margin(self, symbol: str) -> Optional[float]:
        """Get available margin for averaging for a symbol"""
        if symbol in self.positions:
            return self.positions[symbol].margin_available()
        return None

    def get_positions_needing_capital(self) -> List[PositionMarginState]:
        """Get list of positions that need additional capital"""
        return [
            p for p in self.get_positions_by_priority()
            if p.needs_additional
        ]

    def get_status_report(self) -> Dict:
        """Generate a status report of all allocations"""
        sorted_positions = self.get_positions_by_priority()

        return {
            'total_positions': len(sorted_positions),
            'base_capital': self.base_capital,
            'max_capital': self.max_capital,
            'positions_needing_capital': len([p for p in sorted_positions if p.needs_additional]),
            'positions': [
                {
                    'symbol': p.symbol,
                    'open_time': p.open_time.isoformat(),
                    'current_margin': p.current_margin,
                    'allocated_capital': p.allocated_capital,
                    'margin_available': p.margin_available(),
                    'averaging_steps': p.averaging_steps,
                    'needs_additional': p.needs_additional
                }
                for p in sorted_positions
            ]
        }


# Singleton instance
_fifo_allocator: Optional[FIFOMarginAllocator] = None

def get_fifo_allocator() -> FIFOMarginAllocator:
    """Get or create singleton FIFO allocator instance"""
    global _fifo_allocator
    if _fifo_allocator is None:
        _fifo_allocator = FIFOMarginAllocator()
    return _fifo_allocator


# Example usage
if __name__ == "__main__":
    from datetime import timedelta
    import time

    print("=" * 60)
    print("FIFO MARGIN ALLOCATION SYSTEM")
    print("First position that NEEDS capital gets it first")
    print("=" * 60)

    allocator = FIFOMarginAllocator()

    # Simulate registering positions at different times
    now = datetime.now()

    # Position 1 - Oldest
    allocator.register_position(
        symbol="BTCUSDT",
        open_time=now - timedelta(hours=5),
        initial_margin=5.0
    )

    # Position 2 - Middle
    allocator.register_position(
        symbol="ETHUSDT",
        open_time=now - timedelta(hours=3),
        initial_margin=5.0
    )

    # Position 3 - Newest
    allocator.register_position(
        symbol="SOLUSDT",
        open_time=now - timedelta(hours=1),
        initial_margin=5.0
    )

    # Simulate averaging steps - ETH exhausts capital first (needs it first)
    print("\nSimulating margin usage...")

    # ETH uses most of its capital first → needs capital first
    allocator.update_margin_used("ETHUSDT", 22.0, 4)  # Used $22 of $25 - needs more!
    time.sleep(0.1)  # Small delay to show FIFO ordering

    # BTC uses capital next → needs capital second
    allocator.update_margin_used("BTCUSDT", 23.0, 4)  # Used $23 of $25 - needs more!

    # SOL still has plenty
    allocator.update_margin_used("SOLUSDT", 10.0, 2)   # Used $10 of $25 - OK

    print("\nBefore capital increase:")
    status = allocator.get_status_report()
    for p in status['positions']:
        needed = p.get('needed_since', 'N/A')
        print(f"  {p['symbol']}: ${p['current_margin']:.2f} used, "
              f"${p['margin_available']:.2f} available, "
              f"needs_additional={p['needs_additional']}")

    # Show priority order
    print("\nPriority order (first to need capital → first to receive):")
    for i, p in enumerate(allocator.get_positions_by_priority(), 1):
        status = "NEEDS CAPITAL" if p.needs_additional else "OK"
        print(f"  {i}. {p.symbol}: {status}")

    # Increase capital from $25 to $40
    print("\n" + "-" * 60)
    print("Increasing capital from $25 to $40...")
    print("Only positions that NEED capital will receive it")
    print("-" * 60)

    results = allocator.allocate_additional_capital(40.0)

    print(f"\nAllocation Results ({len(results)} positions received capital):")
    for r in results:
        print(f"  Rank {r.priority_rank}: {r.symbol} - "
              f"${r.previous_capital:.2f} → ${r.new_capital:.2f} "
              f"(+${r.additional_margin:.2f})")

    if not results:
        print("  No positions needed additional capital")

    print("\nAfter capital increase:")
    status = allocator.get_status_report()
    for p in status['positions']:
        print(f"  {p['symbol']}: ${p['current_margin']:.2f} used, "
              f"${p['margin_available']:.2f} available, "
              f"allocated=${p['allocated_capital']:.2f}")
