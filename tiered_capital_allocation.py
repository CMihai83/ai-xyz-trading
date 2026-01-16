#!/usr/bin/env python3
"""
Tiered Capital Allocation System
================================
Splits capital and positions into 3 tiers based on market conditions:

Tier 1: REGULAR_BUSINESS - Normal market conditions
Tier 2: MARKET_ADVERSITY - Adverse/difficult market conditions
Tier 3: BLACK_SWAN - Extreme market conditions

Each tier gets equal allocation:
- Positions: 10 each (30 total)
- Capital: $100 each ($300 total)

Market Condition Detection:
- BTC 24h change, volatility index, correlation breakdown
- Fear & Greed proxy via price action
- Liquidation cascade detection
"""

import os
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta

# Import Grok V2 HMM for regime-based tier detection
try:
    from grok_v2_volatility_regime_hmm import VolatilityRegime, get_volatility_hmm
    GROK_HMM_AVAILABLE = True
except ImportError:
    GROK_HMM_AVAILABLE = False


class MarketTier(Enum):
    """Market condition tiers"""
    REGULAR_BUSINESS = 1    # Normal conditions - use Tier 1 capital only (1/3)
    MARKET_ADVERSITY = 2    # Adverse conditions - use Tier 1 + Tier 2 (2/3)
    BLACK_SWAN = 3          # Extreme conditions - use all tiers (3/3)


@dataclass
class TierConfig:
    """Configuration for each tier"""
    name: str
    max_positions: int
    capital_allocated: float
    capital_per_position: float
    leverage_max: int
    entry_score_threshold: float
    averaging_steps_max: int
    description: str


class TieredCapitalAllocation:
    """
    3-Tier Capital Allocation System

    Splits total capital and positions into 3 equal parts:
    - Tier 1 (Regular): For normal market conditions
    - Tier 2 (Adversity): Reserved for adverse conditions (dips, corrections)
    - Tier 3 (Black Swan): Reserved for extreme events (crashes, cascades)

    Benefits:
    - Always have dry powder for opportunities
    - Better risk management across market regimes
    - Capitalize on black swan events instead of being liquidated
    """

    def __init__(
        self,
        total_capital: float = 300.0,
        max_positions: int = 30,
        tiers: int = 3
    ):
        """
        Initialize tiered allocation system.

        Args:
            total_capital: Total futures account capital (default $300)
            max_positions: Total max positions across all tiers (default 30)
            tiers: Number of tiers (fixed at 3)
        """
        self.total_capital = total_capital
        self.max_positions = max_positions
        self.num_tiers = tiers

        # Equal split across tiers
        self.capital_per_tier = total_capital / tiers
        self.positions_per_tier = max_positions // tiers

        # Track usage per tier
        self.tier_usage = {
            MarketTier.REGULAR_BUSINESS: {'positions': 0, 'capital_used': 0.0},
            MarketTier.MARKET_ADVERSITY: {'positions': 0, 'capital_used': 0.0},
            MarketTier.BLACK_SWAN: {'positions': 0, 'capital_used': 0.0}
        }

        # Current market tier (start with regular)
        self.current_tier = MarketTier.REGULAR_BUSINESS

        # Market metrics cache
        self.market_metrics = {
            'btc_24h_change': 0.0,
            'btc_7d_change': 0.0,
            'avg_volatility': 0.0,
            'correlation_breakdown': False,
            'liquidation_cascade': False,
            'last_update': None
        }

        # Initialize tier configurations
        self.tier_configs = self._init_tier_configs()

        print(f"📊 Tiered Capital Allocation Initialized")
        print(f"   Total Capital: ${total_capital:.2f}")
        print(f"   Max Positions: {max_positions}")
        print(f"   Per Tier: ${self.capital_per_tier:.2f} / {self.positions_per_tier} positions")

    def _init_tier_configs(self) -> Dict[MarketTier, TierConfig]:
        """Initialize configuration for each tier"""
        return {
            MarketTier.REGULAR_BUSINESS: TierConfig(
                name="Regular Business",
                max_positions=self.positions_per_tier,
                capital_allocated=self.capital_per_tier,
                capital_per_position=self.capital_per_tier / self.positions_per_tier,
                leverage_max=10,
                entry_score_threshold=0.70,  # Standard threshold
                averaging_steps_max=5,
                description="Normal market conditions - standard trading"
            ),
            MarketTier.MARKET_ADVERSITY: TierConfig(
                name="Market Adversity",
                max_positions=self.positions_per_tier,
                capital_allocated=self.capital_per_tier,
                capital_per_position=self.capital_per_tier / self.positions_per_tier,
                leverage_max=7,  # Lower leverage in adversity
                entry_score_threshold=0.40,  # Aggressive - capitalize on corrections
                averaging_steps_max=7,  # More averaging allowed
                description="Adverse conditions - corrections, high volatility"
            ),
            MarketTier.BLACK_SWAN: TierConfig(
                name="Black Swan",
                max_positions=self.positions_per_tier,
                capital_allocated=self.capital_per_tier,
                capital_per_position=self.capital_per_tier / self.positions_per_tier,
                leverage_max=5,  # Lowest leverage for extreme events
                entry_score_threshold=0.50,  # Aggressive buying in crashes
                averaging_steps_max=10,  # Maximum averaging for recovery
                description="Extreme conditions - crashes, cascades, black swans"
            )
        }

    def detect_market_tier(
        self,
        btc_24h_change: float = 0,
        btc_7d_change: float = 0,
        avg_volatility: float = 1.0,
        total_liquidations_24h: float = 0,
        alt_btc_correlation: float = 0.8,
        portfolio_drawdown_pct: float = 0,
        positions_in_loss_pct: float = 0,
        avg_position_pnl_pct: float = 0
    ) -> MarketTier:
        """
        Detect current market tier based on market AND portfolio conditions.

        KEY INSIGHT: When portfolio is in significant drawdown, this is an
        OPPORTUNITY to deploy reserved capital at better prices!

        Args:
            btc_24h_change: BTC price change in last 24h (%)
            btc_7d_change: BTC price change in last 7d (%)
            avg_volatility: Average market volatility (ATR ratio)
            total_liquidations_24h: Total market liquidations in 24h ($)
            alt_btc_correlation: Altcoin-BTC correlation (0-1)
            portfolio_drawdown_pct: Portfolio total UPNL as % of margin (e.g., -25)
            positions_in_loss_pct: % of positions currently in loss (e.g., 90)
            avg_position_pnl_pct: Average P&L% across all positions

        Returns:
            MarketTier based on conditions - use reserved capital for opportunities!
        """
        # Update metrics cache
        self.market_metrics.update({
            'btc_24h_change': btc_24h_change,
            'btc_7d_change': btc_7d_change,
            'avg_volatility': avg_volatility,
            'portfolio_drawdown_pct': portfolio_drawdown_pct,
            'positions_in_loss_pct': positions_in_loss_pct,
            'avg_position_pnl_pct': avg_position_pnl_pct,
            'last_update': datetime.now()
        })

        # =======================================================================
        # BLACK SWAN - EXTREME OPPORTUNITY
        # =======================================================================
        # Market crash OR portfolio in extreme drawdown = BUY THE DIP!
        # This is when we deploy Tier 3 reserved capital
        if (
            btc_24h_change <= -15 or                    # -15%+ daily crash
            btc_7d_change <= -30 or                     # -30%+ weekly crash
            avg_volatility >= 3.0 or                    # 3x normal volatility
            total_liquidations_24h >= 500_000_000 or   # $500M+ liquidations
            portfolio_drawdown_pct <= -50 or           # Portfolio down 50%+
            (positions_in_loss_pct >= 90 and avg_position_pnl_pct <= -40)  # 90% positions down 40%+ avg
        ):
            self.market_metrics['liquidation_cascade'] = total_liquidations_24h >= 500_000_000
            self.market_metrics['correlation_breakdown'] = alt_btc_correlation <= 0.3
            self.market_metrics['tier_reason'] = 'BLACK_SWAN_OPPORTUNITY'
            return MarketTier.BLACK_SWAN

        # =======================================================================
        # MARKET ADVERSITY - CORRECTION OPPORTUNITY
        # =======================================================================
        # Market dip OR portfolio in significant drawdown = opportunity to average in
        # This is when we deploy Tier 2 reserved capital
        if (
            btc_24h_change <= -5 or                     # -5%+ daily drop
            btc_7d_change <= -15 or                     # -15%+ weekly drop
            avg_volatility >= 1.8 or                    # 1.8x normal volatility
            total_liquidations_24h >= 100_000_000 or   # $100M+ liquidations
            portfolio_drawdown_pct <= -20 or           # Portfolio down 20%+
            (positions_in_loss_pct >= 70 and avg_position_pnl_pct <= -20)  # 70% positions down 20%+ avg
        ):
            self.market_metrics['tier_reason'] = 'ADVERSITY_OPPORTUNITY'
            return MarketTier.MARKET_ADVERSITY

        # =======================================================================
        # REGULAR BUSINESS - Normal trading
        # =======================================================================
        self.market_metrics['tier_reason'] = 'NORMAL_CONDITIONS'
        return MarketTier.REGULAR_BUSINESS

    def get_tier_from_hmm_regime(self, hmm_regime: str = None) -> MarketTier:
        """
        Map Grok V2 HMM volatility regime to market tier.

        HMM Regime -> Tier Mapping:
        - LOW_VOL / NORMAL_VOL -> REGULAR_BUSINESS (Tier 1 only = 1/3 positions)
        - HIGH_VOL -> MARKET_ADVERSITY (Tier 1 + 2 = 2/3 positions)
        - CRISIS -> BLACK_SWAN (All tiers = 3/3 positions)

        Args:
            hmm_regime: Current HMM regime string or None to auto-detect

        Returns:
            MarketTier based on HMM regime
        """
        # Auto-detect from HMM if not provided
        if hmm_regime is None and GROK_HMM_AVAILABLE:
            try:
                hmm = get_volatility_hmm()
                regime_state = hmm.get_regime()
                hmm_regime = regime_state.regime.value
            except Exception:
                hmm_regime = 'normal_vol'  # Default fallback
        elif hmm_regime is None:
            hmm_regime = 'normal_vol'

        # Normalize to lowercase
        regime = hmm_regime.lower() if hmm_regime else 'normal_vol'

        # Map HMM regime to tier
        if regime == 'crisis':
            self.market_metrics['tier_reason'] = 'HMM_CRISIS'
            return MarketTier.BLACK_SWAN
        elif regime == 'high_vol':
            self.market_metrics['tier_reason'] = 'HMM_HIGH_VOL'
            return MarketTier.MARKET_ADVERSITY
        else:  # low_vol or normal_vol
            self.market_metrics['tier_reason'] = 'HMM_NORMAL'
            return MarketTier.REGULAR_BUSINESS

    def get_max_positions_for_regime(self, hmm_regime: str = None) -> int:
        """
        Get maximum allowed positions based on current HMM regime.

        Position Allocation:
        - NORMAL_VOL / LOW_VOL: 1/3 of max (Tier 1 only)
        - HIGH_VOL: 2/3 of max (Tier 1 + Tier 2)
        - CRISIS: 3/3 of max (All tiers)

        Args:
            hmm_regime: Current HMM regime or None to auto-detect

        Returns:
            Maximum positions allowed for current regime
        """
        tier = self.get_tier_from_hmm_regime(hmm_regime)

        if tier == MarketTier.BLACK_SWAN:
            # CRISIS: Use all 3 tiers = 3/3 of max
            allowed = self.max_positions
            tiers_active = "1+2+3"
        elif tier == MarketTier.MARKET_ADVERSITY:
            # HIGH_VOL: Use Tier 1 + Tier 2 = 2/3 of max
            allowed = (self.max_positions * 2) // 3
            tiers_active = "1+2"
        else:
            # NORMAL_VOL/LOW_VOL: Use Tier 1 only = 1/3 of max
            allowed = self.max_positions // 3
            tiers_active = "1"

        self.market_metrics['tiers_active'] = tiers_active
        self.market_metrics['max_positions_allowed'] = allowed

        return allowed

    def should_block_new_position(self, current_positions: int, hmm_regime: str = None) -> Tuple[bool, str]:
        """
        Check if new positions should be blocked based on regime.

        Args:
            current_positions: Number of currently open positions
            hmm_regime: Current HMM regime or None to auto-detect

        Returns:
            Tuple of (should_block, reason)
        """
        max_allowed = self.get_max_positions_for_regime(hmm_regime)
        tier = self.get_tier_from_hmm_regime(hmm_regime)

        if current_positions >= max_allowed:
            return True, f"Position limit reached for {tier.name}: {current_positions}/{max_allowed}"

        return False, f"OK: {current_positions}/{max_allowed} positions for {tier.name}"

    def get_available_capital(self, tier: Optional[MarketTier] = None) -> Tuple[float, int]:
        """
        Get available capital and positions for a tier.

        Args:
            tier: Specific tier or None for current tier

        Returns:
            Tuple of (available_capital, available_positions)
        """
        if tier is None:
            tier = self.current_tier

        config = self.tier_configs[tier]
        usage = self.tier_usage[tier]

        available_capital = config.capital_allocated - usage['capital_used']
        available_positions = config.max_positions - usage['positions']

        return available_capital, available_positions

    def can_open_position(self, tier: Optional[MarketTier] = None, margin_required: float = 10.0) -> bool:
        """
        Check if we can open a position in the specified tier.

        Args:
            tier: Tier to check (None = current tier)
            margin_required: Margin needed for position

        Returns:
            True if position can be opened
        """
        available_capital, available_positions = self.get_available_capital(tier)
        return available_capital >= margin_required and available_positions > 0

    def allocate_position(
        self,
        symbol: str,
        margin: float,
        tier: Optional[MarketTier] = None
    ) -> Dict:
        """
        Allocate capital for a new position.

        Args:
            symbol: Trading symbol
            margin: Margin to allocate
            tier: Tier to allocate from (None = current tier)

        Returns:
            Allocation result dict
        """
        if tier is None:
            tier = self.current_tier

        config = self.tier_configs[tier]
        usage = self.tier_usage[tier]

        available_capital, available_positions = self.get_available_capital(tier)

        if available_positions <= 0:
            return {
                'success': False,
                'reason': f'No positions available in {config.name} tier (using {usage["positions"]}/{config.max_positions})'
            }

        if available_capital < margin:
            return {
                'success': False,
                'reason': f'Insufficient capital in {config.name} tier (${available_capital:.2f} < ${margin:.2f})'
            }

        # Allocate
        usage['positions'] += 1
        usage['capital_used'] += margin

        return {
            'success': True,
            'tier': tier.name,
            'tier_value': tier.value,
            'symbol': symbol,
            'margin_allocated': margin,
            'positions_used': usage['positions'],
            'positions_max': config.max_positions,
            'capital_used': usage['capital_used'],
            'capital_max': config.capital_allocated,
            'leverage_max': config.leverage_max
        }

    def release_position(
        self,
        symbol: str,
        margin: float,
        tier: MarketTier
    ) -> Dict:
        """
        Release capital when closing a position.

        Args:
            symbol: Trading symbol
            margin: Margin to release
            tier: Tier position was in

        Returns:
            Release result dict
        """
        usage = self.tier_usage[tier]

        usage['positions'] = max(0, usage['positions'] - 1)
        usage['capital_used'] = max(0.0, usage['capital_used'] - margin)

        return {
            'success': True,
            'tier': tier.name,
            'symbol': symbol,
            'margin_released': margin,
            'positions_remaining': usage['positions'],
            'capital_remaining': usage['capital_used']
        }

    def get_tier_for_position(self, symbol: str, position_data: Dict) -> MarketTier:
        """
        Determine which tier a position belongs to based on entry conditions.

        Args:
            symbol: Position symbol
            position_data: Position data with entry info

        Returns:
            MarketTier the position belongs to
        """
        # Check if position has tier info stored
        if 'tier' in position_data:
            tier_value = position_data['tier']
            if isinstance(tier_value, int):
                return MarketTier(tier_value)
            elif isinstance(tier_value, str):
                return MarketTier[tier_value]

        # Default to regular business for legacy positions
        return MarketTier.REGULAR_BUSINESS

    def update_from_exchange(self, positions: list, exchange_balance: float):
        """
        Sync tier usage from actual exchange positions.

        Args:
            positions: List of active positions
            exchange_balance: Current exchange balance
        """
        # Reset usage counters
        for tier in MarketTier:
            self.tier_usage[tier] = {'positions': 0, 'capital_used': 0.0}

        # Count positions per tier
        for pos in positions:
            tier = self.get_tier_for_position(pos.get('symbol', ''), pos)
            margin = abs(pos.get('initialMargin', 0)) or abs(pos.get('margin', 0))

            self.tier_usage[tier]['positions'] += 1
            self.tier_usage[tier]['capital_used'] += margin

        # Update total capital if different
        if exchange_balance != self.total_capital:
            self._recalculate_tiers(exchange_balance)

    def _recalculate_tiers(self, new_total: float):
        """Recalculate tier allocations based on new total capital"""
        self.total_capital = new_total
        self.capital_per_tier = new_total / self.num_tiers

        # Update tier configs
        for tier, config in self.tier_configs.items():
            config.capital_allocated = self.capital_per_tier
            config.capital_per_position = self.capital_per_tier / self.positions_per_tier

        print(f"📊 Recalculated tiers: ${self.capital_per_tier:.2f} per tier")

    def get_status(self) -> Dict:
        """Get current status of all tiers"""
        status = {
            'total_capital': self.total_capital,
            'max_positions': self.max_positions,
            'current_tier': self.current_tier.name,
            'market_metrics': self.market_metrics,
            'tiers': {}
        }

        for tier, config in self.tier_configs.items():
            usage = self.tier_usage[tier]
            available_cap, available_pos = self.get_available_capital(tier)

            status['tiers'][tier.name] = {
                'description': config.description,
                'positions': {
                    'used': usage['positions'],
                    'max': config.max_positions,
                    'available': available_pos
                },
                'capital': {
                    'used': usage['capital_used'],
                    'allocated': config.capital_allocated,
                    'available': available_cap
                },
                'settings': {
                    'leverage_max': config.leverage_max,
                    'entry_threshold': config.entry_score_threshold,
                    'averaging_steps_max': config.averaging_steps_max
                }
            }

        return status

    def print_status(self):
        """Print formatted status of all tiers"""
        status = self.get_status()

        print("\n" + "="*70)
        print("📊 TIERED CAPITAL ALLOCATION STATUS")
        print("="*70)
        print(f"Total Capital: ${status['total_capital']:.2f} | Max Positions: {status['max_positions']}")
        print(f"Current Market Tier: {status['current_tier']}")
        print("-"*70)

        for tier_name, tier_data in status['tiers'].items():
            pos = tier_data['positions']
            cap = tier_data['capital']
            settings = tier_data['settings']

            # Tier indicator
            if tier_name == status['current_tier']:
                indicator = "🟢 ACTIVE"
            else:
                indicator = "⚪ RESERVED"

            print(f"\n{indicator} TIER: {tier_name}")
            print(f"   {tier_data['description']}")
            print(f"   Positions: {pos['used']}/{pos['max']} ({pos['available']} available)")
            print(f"   Capital: ${cap['used']:.2f}/${cap['allocated']:.2f} (${cap['available']:.2f} available)")
            print(f"   Settings: Lev {settings['leverage_max']}x | Entry {settings['entry_threshold']} | Avg Steps {settings['averaging_steps_max']}")

        print("\n" + "="*70)


# Singleton instance
_tiered_allocation: Optional[TieredCapitalAllocation] = None


def get_tiered_allocation(
    total_capital: float = None,
    max_positions: int = None
) -> TieredCapitalAllocation:
    """
    Get or create the tiered allocation singleton.

    Args:
        total_capital: Total capital (uses env var or default $300)
        max_positions: Max positions (uses env var or default 30)

    Returns:
        TieredCapitalAllocation instance
    """
    global _tiered_allocation

    if _tiered_allocation is None:
        if total_capital is None:
            total_capital = float(os.getenv('TIERED_TOTAL_CAPITAL', 300.0))
        if max_positions is None:
            max_positions = int(os.getenv('TIERED_MAX_POSITIONS', 30))

        _tiered_allocation = TieredCapitalAllocation(
            total_capital=total_capital,
            max_positions=max_positions
        )

    return _tiered_allocation


# Example usage and testing
if __name__ == "__main__":
    # Initialize with $300 capital, 30 positions
    tiered = TieredCapitalAllocation(total_capital=300.0, max_positions=30)

    # Print initial status
    tiered.print_status()

    # Test market tier detection
    print("\n🔍 Testing Market Tier Detection:")

    # Normal conditions
    tier = tiered.detect_market_tier(btc_24h_change=2.0, btc_7d_change=5.0, avg_volatility=1.0)
    print(f"   Normal market (BTC +2%): {tier.name}")

    # Adverse conditions
    tier = tiered.detect_market_tier(btc_24h_change=-7.0, btc_7d_change=-12.0, avg_volatility=2.0)
    print(f"   Adverse market (BTC -7%): {tier.name}")

    # Black swan
    tier = tiered.detect_market_tier(btc_24h_change=-20.0, btc_7d_change=-35.0, avg_volatility=4.0)
    print(f"   Black swan (BTC -20%): {tier.name}")

    # Test allocation
    print("\n💰 Testing Position Allocation:")

    result = tiered.allocate_position("BTC/USDT:USDT", margin=10.0, tier=MarketTier.REGULAR_BUSINESS)
    print(f"   Allocated BTC: {result}")

    result = tiered.allocate_position("ETH/USDT:USDT", margin=10.0, tier=MarketTier.MARKET_ADVERSITY)
    print(f"   Allocated ETH: {result}")

    # Print updated status
    tiered.print_status()
