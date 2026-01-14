#!/usr/bin/env python3
"""
Position Manager CLI - Sprint 9 Implementation
V1.0.0 - January 2026

Safe position closure and profit-taking utility for AI-XYZ trading system.
Can be run standalone or integrated with main system.

Usage:
    python3 position_manager_cli.py --list                    # List all positions
    python3 position_manager_cli.py --close PEOPLE           # Close specific position
    python3 position_manager_cli.py --take-profits            # Close all profitable positions
    python3 position_manager_cli.py --close-critical          # Close all CRITICAL (5-step) positions
    python3 position_manager_cli.py --dry-run --close PEOPLE  # Preview without executing
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

# Add project root to path
sys.path.insert(0, '/root/ai_xyz')
from dotenv import load_dotenv
load_dotenv('/root/ai_xyz/.env')

import ccxt
import redis


class RiskLevel(Enum):
    """Position risk levels based on averaging steps."""
    MINIMAL = "MINIMAL"      # 0 averaging steps
    LOW = "LOW"              # 1 averaging step
    MODERATE = "MODERATE"    # 2 averaging steps
    ELEVATED = "ELEVATED"    # 3 averaging steps
    HIGH = "HIGH"            # 4 averaging steps
    CRITICAL = "CRITICAL"    # 5 averaging steps (max)


@dataclass
class PositionInfo:
    """Enhanced position information."""
    symbol: str
    side: str
    position_side: str
    amount: float
    entry_price: float
    current_price: float
    upnl: float
    upnl_pct: float
    margin: float
    leverage: int
    averaging_steps: int
    risk_level: RiskLevel
    opened_at: Optional[str] = None


class PositionManagerCLI:
    """CLI tool for managing positions in AI-XYZ trading system."""

    VERSION = "1.0.0"

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

        # Initialize exchange
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {
                'defaultType': 'swap',
                'adjustForTimeDifference': True,
            }
        })
        self.exchange.load_markets()

        # Initialize Redis for state
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=1)

        # Load averaging steps from Redis
        self.averaging_steps = self._load_averaging_steps()

    def _load_averaging_steps(self) -> Dict[str, int]:
        """Load averaging steps from Redis state."""
        try:
            state_data = self.redis_client.get('aixyz:position_state')
            if state_data:
                state = json.loads(state_data)
                return state.get('averaging_steps', {})
        except Exception as e:
            print(f"⚠️ Warning: Could not load averaging steps from Redis: {e}")
        return {}

    def _get_risk_level(self, steps: int) -> RiskLevel:
        """Determine risk level from averaging steps."""
        levels = {
            0: RiskLevel.MINIMAL,
            1: RiskLevel.LOW,
            2: RiskLevel.MODERATE,
            3: RiskLevel.ELEVATED,
            4: RiskLevel.HIGH,
            5: RiskLevel.CRITICAL,
        }
        return levels.get(steps, RiskLevel.CRITICAL)

    def _format_symbol(self, symbol: str) -> str:
        """Normalize symbol format."""
        if not symbol.endswith('/USDT:USDT'):
            if '/' not in symbol:
                symbol = f"{symbol}/USDT:USDT"
            elif ':USDT' not in symbol:
                symbol = f"{symbol}:USDT"
        return symbol

    def get_positions(self) -> List[PositionInfo]:
        """Fetch all open positions with enhanced info."""
        positions = []

        try:
            raw_positions = self.exchange.fetch_positions()

            for pos in raw_positions:
                contracts = float(pos.get('contracts', 0) or 0)
                if contracts == 0:
                    continue

                symbol = pos['symbol']
                side = pos.get('side', 'long')
                position_side = 'long' if side == 'long' else 'short'
                entry_price = float(pos.get('entryPrice', 0) or 0)
                current_price = float(pos.get('markPrice', 0) or pos.get('liquidationPrice', 0) or 0)

                # Calculate UPNL
                upnl = float(pos.get('unrealizedPnl', 0) or 0)
                margin = float(pos.get('initialMargin', 0) or pos.get('collateral', 0) or 0)
                leverage = int(pos.get('leverage', 5) or 5)

                # Calculate UPNL percentage
                if margin > 0:
                    upnl_pct = (upnl / margin) * 100
                else:
                    upnl_pct = 0

                # Get averaging steps
                steps = self.averaging_steps.get(symbol, 0)
                risk_level = self._get_risk_level(steps)

                positions.append(PositionInfo(
                    symbol=symbol,
                    side=side,
                    position_side=position_side,
                    amount=contracts,
                    entry_price=entry_price,
                    current_price=current_price,
                    upnl=upnl,
                    upnl_pct=upnl_pct,
                    margin=margin,
                    leverage=leverage,
                    averaging_steps=steps,
                    risk_level=risk_level
                ))

        except Exception as e:
            print(f"❌ Error fetching positions: {e}")

        return positions

    def list_positions(self) -> None:
        """Display all positions with risk assessment."""
        positions = self.get_positions()

        if not positions:
            print("📭 No open positions found")
            return

        # Sort by risk level (CRITICAL first), then by UPNL
        positions.sort(key=lambda p: (-p.averaging_steps, -p.upnl))

        print(f"\n{'='*80}")
        print(f"📊 AI-XYZ Position Manager CLI v{self.VERSION}")
        print(f"{'='*80}")
        print(f"Total Positions: {len(positions)}")
        print(f"{'='*80}\n")

        # Summary stats
        total_upnl = sum(p.upnl for p in positions)
        profitable = [p for p in positions if p.upnl > 0]
        losing = [p for p in positions if p.upnl < 0]
        critical = [p for p in positions if p.risk_level == RiskLevel.CRITICAL]
        high_risk = [p for p in positions if p.risk_level == RiskLevel.HIGH]

        print(f"💰 Total UPNL: ${total_upnl:+.4f}")
        print(f"✅ Profitable: {len(profitable)} | ❌ Losing: {len(losing)}")
        print(f"🔴 CRITICAL: {len(critical)} | 🟠 HIGH: {len(high_risk)}")
        print()

        # Position table
        print(f"{'Symbol':<18} {'Side':<6} {'UPNL':>10} {'P&L%':>8} {'Steps':>6} {'Risk':<10} {'Margin':>10}")
        print("-" * 80)

        for pos in positions:
            risk_emoji = {
                RiskLevel.MINIMAL: "🟢",
                RiskLevel.LOW: "🟢",
                RiskLevel.MODERATE: "🟡",
                RiskLevel.ELEVATED: "🟠",
                RiskLevel.HIGH: "🔴",
                RiskLevel.CRITICAL: "⚫",
            }.get(pos.risk_level, "⚪")

            # Clean symbol for display
            display_symbol = pos.symbol.replace('/USDT:USDT', '').replace('/USDT', '')

            print(f"{display_symbol:<18} {pos.side:<6} ${pos.upnl:>+9.4f} {pos.upnl_pct:>+7.2f}% "
                  f"{pos.averaging_steps:>6} {risk_emoji}{pos.risk_level.value:<9} ${pos.margin:>9.2f}")

        print("-" * 80)
        print()

        # Recommendations
        if critical:
            print("⚠️  RECOMMENDATIONS:")
            for p in critical:
                action = "CLOSE" if p.upnl > 0 else "MONITOR"
                clean_sym = p.symbol.replace('/USDT:USDT', '')
                print(f"   🔴 {clean_sym}: CRITICAL ({p.averaging_steps} steps) - {action} "
                      f"(UPNL: ${p.upnl:+.4f})")

        if profitable:
            print("\n💡 PROFIT-TAKING OPPORTUNITIES:")
            for p in profitable:
                clean_sym = p.symbol.replace('/USDT:USDT', '')
                print(f"   💰 {clean_sym}: ${p.upnl:+.4f} ({p.upnl_pct:+.2f}%)")

    def close_position(self, symbol: str) -> Tuple[bool, str]:
        """Close a specific position."""
        symbol = self._format_symbol(symbol)

        positions = self.get_positions()
        target_pos = None

        for pos in positions:
            if pos.symbol == symbol or pos.symbol.startswith(symbol.split('/')[0]):
                target_pos = pos
                break

        if not target_pos:
            return False, f"Position not found: {symbol}"

        clean_sym = target_pos.symbol.replace('/USDT:USDT', '')

        if self.dry_run:
            return True, (f"[DRY RUN] Would close {clean_sym}: "
                         f"{target_pos.amount:.4f} contracts, UPNL: ${target_pos.upnl:+.4f}")

        try:
            # Determine close side
            # In hedge mode: Long uses 'buy' for both open/close, Short uses 'sell'
            # The tradeSide parameter determines open vs close
            position_side = target_pos.position_side

            # In Bitget hedge mode:
            # - LONG positions always use side='buy' (tradeSide='close' to close)
            # - SHORT positions always use side='sell' (tradeSide='close' to close)
            close_side = 'buy' if position_side == 'long' else 'sell'

            # Hedge mode params for closing
            close_params = {
                'marginCoin': 'USDT',
                'tradeSide': 'close',  # Critical for hedge mode
                'holdSide': position_side,
            }

            # Execute close order
            order = self.exchange.create_market_order(
                target_pos.symbol,
                close_side,
                target_pos.amount,
                params=close_params
            )

            # Update Redis state
            self._update_redis_after_close(target_pos.symbol)

            return True, (f"✅ Closed {clean_sym}: {target_pos.amount:.4f} contracts, "
                         f"Realized P&L: ${target_pos.upnl:+.4f}, Order ID: {order.get('id', 'N/A')}")

        except Exception as e:
            return False, f"❌ Failed to close {clean_sym}: {str(e)}"

    def _update_redis_after_close(self, symbol: str) -> None:
        """Update Redis state after closing a position."""
        try:
            state_data = self.redis_client.get('aixyz:position_state')
            if state_data:
                state = json.loads(state_data)

                # Remove from tracking
                if symbol in state.get('averaging_steps', {}):
                    del state['averaging_steps'][symbol]
                if symbol in state.get('active_positions', {}):
                    del state['active_positions'][symbol]
                if symbol in state.get('position_zones', {}):
                    del state['position_zones'][symbol]
                if symbol in state.get('peak_upnl', {}):
                    del state['peak_upnl'][symbol]
                if symbol in state.get('original_sizes', {}):
                    del state['original_sizes'][symbol]

                # Save back
                self.redis_client.set('aixyz:position_state', json.dumps(state))
                print(f"   📝 Redis state updated for {symbol}")

        except Exception as e:
            print(f"   ⚠️ Warning: Could not update Redis state: {e}")

    def take_profits(self, min_profit: float = 0.0) -> List[Tuple[bool, str]]:
        """Close all profitable positions above min_profit threshold."""
        positions = self.get_positions()
        profitable = [p for p in positions if p.upnl > min_profit]

        if not profitable:
            print(f"📭 No profitable positions above ${min_profit:.2f} threshold")
            return []

        results = []
        total_profit = 0

        for pos in profitable:
            success, msg = self.close_position(pos.symbol)
            results.append((success, msg))
            if success and not self.dry_run:
                total_profit += pos.upnl
            print(msg)

        if not self.dry_run:
            print(f"\n💰 Total Profit Realized: ${total_profit:+.4f}")

        return results

    def close_critical(self) -> List[Tuple[bool, str]]:
        """Close all CRITICAL (5-step) positions."""
        positions = self.get_positions()
        critical = [p for p in positions if p.risk_level == RiskLevel.CRITICAL]

        if not critical:
            print("📭 No CRITICAL positions to close")
            return []

        results = []

        for pos in critical:
            success, msg = self.close_position(pos.symbol)
            results.append((success, msg))
            print(msg)

        return results


def main():
    parser = argparse.ArgumentParser(description='AI-XYZ Position Manager CLI')
    parser.add_argument('--list', '-l', action='store_true', help='List all positions')
    parser.add_argument('--close', '-c', type=str, help='Close specific position (symbol)')
    parser.add_argument('--take-profits', '-t', action='store_true', help='Close all profitable positions')
    parser.add_argument('--close-critical', action='store_true', help='Close all CRITICAL positions')
    parser.add_argument('--min-profit', type=float, default=0.0, help='Minimum profit threshold for take-profits')
    parser.add_argument('--dry-run', '-d', action='store_true', help='Preview without executing')

    args = parser.parse_args()

    manager = PositionManagerCLI(dry_run=args.dry_run)

    if args.dry_run:
        print("🔍 DRY RUN MODE - No trades will be executed\n")

    if args.list:
        manager.list_positions()
    elif args.close:
        success, msg = manager.close_position(args.close)
        print(msg)
    elif args.take_profits:
        manager.take_profits(min_profit=args.min_profit)
    elif args.close_critical:
        manager.close_critical()
    else:
        # Default: show positions
        manager.list_positions()


if __name__ == '__main__':
    main()
