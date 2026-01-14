#!/usr/bin/env python3
"""
Position Recovery Optimizer for AI-XYZ Trading System
V1.0.0 - January 2026 (Sprint 10)

Analyzes losing positions and recommends recovery strategies.

Strategies:
1. WAIT - Position likely to recover, hold and wait
2. AVERAGE_DOWN - Good opportunity to lower entry price
3. PARTIAL_CLOSE - Reduce exposure while keeping upside potential
4. FULL_CLOSE - Cut losses, position unlikely to recover
5. HEDGE - Add opposite position to limit further losses

Based on:
- Current loss percentage
- Averaging steps used (risk level)
- Market trend (trending vs ranging)
- Position age
- Historical recovery patterns

Author: Claude + Grok Consortium
"""

import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class RecoveryStrategy(Enum):
    """Recovery strategies for losing positions."""
    WAIT = "WAIT"                    # Hold and wait for recovery
    AVERAGE_DOWN = "AVERAGE_DOWN"    # Add to position at lower price
    PARTIAL_CLOSE = "PARTIAL_CLOSE"  # Close portion to reduce exposure
    FULL_CLOSE = "FULL_CLOSE"        # Close entire position (cut losses)
    HEDGE = "HEDGE"                  # Add opposite position


class RiskLevel(Enum):
    """Position risk levels based on averaging steps."""
    MINIMAL = "MINIMAL"      # 0 steps
    LOW = "LOW"              # 1 step
    MODERATE = "MODERATE"    # 2 steps
    ELEVATED = "ELEVATED"    # 3 steps
    HIGH = "HIGH"            # 4 steps
    CRITICAL = "CRITICAL"    # 5 steps


@dataclass
class RecoveryRecommendation:
    """Recommendation for a specific position."""
    symbol: str
    strategy: RecoveryStrategy
    confidence: float           # 0-1 confidence in recommendation
    rationale: str
    expected_outcome: str
    risk_if_followed: str
    risk_if_ignored: str
    priority: int               # 1 = highest priority
    actions: List[str] = field(default_factory=list)


@dataclass
class PositionAnalysis:
    """Detailed analysis of a position."""
    symbol: str
    side: str
    current_upnl: float
    current_upnl_pct: float
    margin: float
    leverage: int
    averaging_steps: int
    risk_level: RiskLevel
    is_hedged: bool
    position_age_hours: float
    entry_price: float
    current_price: float
    distance_to_entry_pct: float


class PositionRecoveryOptimizer:
    """
    Analyzes positions and recommends recovery strategies.

    Sprint 10: Focus on recovering from -30%+ losses on AXS, BLUR, PIXEL.
    """

    VERSION = "1.0.0"

    # Loss thresholds for strategy decisions
    LOSS_THRESHOLDS = {
        'minor': -0.10,       # -10%: Minor loss, likely to recover
        'moderate': -0.20,    # -20%: Moderate loss, needs attention
        'significant': -0.30, # -30%: Significant loss, consider reducing
        'severe': -0.50,      # -50%: Severe loss, strongly consider closing
        'critical': -0.75     # -75%: Critical loss, close immediately
    }

    # Maximum averaging steps before forced close recommendation
    MAX_SAFE_STEPS = 3

    # Time-based recovery patterns (hours to likely recovery)
    RECOVERY_TIME_ESTIMATES = {
        'minor': 24,          # Minor losses typically recover in 1 day
        'moderate': 72,       # Moderate losses: 3 days
        'significant': 168,   # Significant losses: 1 week
        'severe': 336,        # Severe losses: 2 weeks
        'critical': float('inf')  # Critical losses rarely recover
    }

    def __init__(self, exchange=None):
        self.exchange = exchange
        self.recommendations: List[RecoveryRecommendation] = []

    def _get_risk_level(self, steps: int) -> RiskLevel:
        """Get risk level from averaging steps."""
        levels = {
            0: RiskLevel.MINIMAL,
            1: RiskLevel.LOW,
            2: RiskLevel.MODERATE,
            3: RiskLevel.ELEVATED,
            4: RiskLevel.HIGH,
            5: RiskLevel.CRITICAL,
        }
        return levels.get(min(steps, 5), RiskLevel.CRITICAL)

    def _classify_loss(self, upnl_pct: float) -> str:
        """Classify loss severity."""
        if upnl_pct >= self.LOSS_THRESHOLDS['minor']:
            return 'minor'
        elif upnl_pct >= self.LOSS_THRESHOLDS['moderate']:
            return 'moderate'
        elif upnl_pct >= self.LOSS_THRESHOLDS['significant']:
            return 'significant'
        elif upnl_pct >= self.LOSS_THRESHOLDS['severe']:
            return 'severe'
        else:
            return 'critical'

    def analyze_position(self, pos_data: Dict, averaging_steps: int = 0,
                        is_hedged: bool = False) -> PositionAnalysis:
        """Analyze a single position."""
        symbol = pos_data.get('symbol', 'UNKNOWN')
        side = pos_data.get('side', 'long')
        upnl = float(pos_data.get('unrealizedPnl', 0) or 0)
        margin = float(pos_data.get('initialMargin', 0) or pos_data.get('collateral', 0) or 0)
        leverage = int(pos_data.get('leverage', 5) or 5)
        entry_price = float(pos_data.get('entryPrice', 0) or 0)
        current_price = float(pos_data.get('markPrice', 0) or 0)

        # Calculate UPNL percentage
        upnl_pct = (upnl / margin) if margin > 0 else 0

        # Calculate distance to entry
        if entry_price > 0:
            distance_pct = (current_price - entry_price) / entry_price
        else:
            distance_pct = 0

        # Estimate position age (default 24h if unknown)
        position_age = 24.0

        return PositionAnalysis(
            symbol=symbol,
            side=side,
            current_upnl=upnl,
            current_upnl_pct=upnl_pct,
            margin=margin,
            leverage=leverage,
            averaging_steps=averaging_steps,
            risk_level=self._get_risk_level(averaging_steps),
            is_hedged=is_hedged,
            position_age_hours=position_age,
            entry_price=entry_price,
            current_price=current_price,
            distance_to_entry_pct=distance_pct
        )

    def recommend_strategy(self, analysis: PositionAnalysis) -> RecoveryRecommendation:
        """Generate recovery recommendation for a position."""
        loss_severity = self._classify_loss(analysis.current_upnl_pct)

        # Default values
        strategy = RecoveryStrategy.WAIT
        confidence = 0.5
        rationale = ""
        expected_outcome = ""
        risk_if_followed = ""
        risk_if_ignored = ""
        priority = 5
        actions = []

        # Decision tree for strategy selection

        # CRITICAL risk level (5 steps) - always recommend close
        if analysis.risk_level == RiskLevel.CRITICAL:
            strategy = RecoveryStrategy.FULL_CLOSE
            confidence = 0.95
            rationale = "Position at maximum averaging steps (5). No more averaging possible."
            expected_outcome = "Stop loss, free up capital for better opportunities"
            risk_if_followed = "Lock in current loss"
            risk_if_ignored = "Risk of liquidation if market continues against position"
            priority = 1
            actions = ["Close position immediately", "Wait for profit zone if possible"]

        # HIGH risk level (4 steps) with significant loss
        elif analysis.risk_level == RiskLevel.HIGH and loss_severity in ['significant', 'severe', 'critical']:
            strategy = RecoveryStrategy.PARTIAL_CLOSE
            confidence = 0.85
            rationale = f"HIGH risk (4 steps) with {loss_severity} loss ({analysis.current_upnl_pct:.1%}). One step from max."
            expected_outcome = "Reduce exposure by 50%, preserve some upside"
            risk_if_followed = "Miss potential recovery on closed portion"
            risk_if_ignored = "Could reach CRITICAL level with further losses"
            priority = 2
            actions = ["Close 50% of position", "Set tighter stop-loss on remainder"]

        # ELEVATED risk (3 steps) with severe loss
        elif analysis.risk_level == RiskLevel.ELEVATED and loss_severity in ['severe', 'critical']:
            strategy = RecoveryStrategy.HEDGE
            confidence = 0.75
            rationale = f"ELEVATED risk with {loss_severity} loss. Hedge to limit downside."
            expected_outcome = "Cap maximum loss, maintain some recovery potential"
            risk_if_followed = "Hedge cost, reduced profit if recovery occurs"
            risk_if_ignored = "Unrestricted downside risk"
            priority = 3
            actions = ["Open small opposite position as hedge", "Monitor for trend reversal"]

        # Moderate loss with room to average
        elif loss_severity == 'moderate' and analysis.averaging_steps < 3:
            if analysis.is_hedged:
                strategy = RecoveryStrategy.WAIT
                confidence = 0.70
                rationale = "Moderate loss but position is hedged. Let the system manage recovery."
                expected_outcome = "Hedged recovery with limited downside"
                risk_if_followed = "Slower recovery due to hedge"
                risk_if_ignored = "N/A - wait is passive"
            else:
                strategy = RecoveryStrategy.AVERAGE_DOWN
                confidence = 0.65
                rationale = f"Moderate loss with room to average (step {analysis.averaging_steps} of 5)."
                expected_outcome = "Lower average entry, faster recovery"
                risk_if_followed = "More capital at risk if market continues down"
                risk_if_ignored = "Slower recovery from current entry"
            priority = 4
            actions = ["Wait for support level", "Add position to lower average entry"]

        # Minor loss - wait
        elif loss_severity == 'minor':
            strategy = RecoveryStrategy.WAIT
            confidence = 0.80
            rationale = "Minor loss, high probability of natural recovery."
            expected_outcome = "Position recovers to profit within 24-48h"
            risk_if_followed = "Market could worsen"
            risk_if_ignored = "N/A - patience usually rewarded"
            priority = 5
            actions = ["Monitor position", "No action needed"]

        # Significant or severe loss but low risk level - partial close
        elif loss_severity in ['significant', 'severe'] and analysis.averaging_steps <= 2:
            close_pct = "50%" if loss_severity == 'severe' else "30%"
            strategy = RecoveryStrategy.PARTIAL_CLOSE
            confidence = 0.75 if loss_severity == 'severe' else 0.70
            rationale = f"{loss_severity.capitalize()} loss ({analysis.current_upnl_pct:.1%}) with low averaging steps ({analysis.averaging_steps})."
            expected_outcome = "Reduce risk while maintaining exposure"
            risk_if_followed = "Miss potential recovery"
            risk_if_ignored = "Could worsen further, increasing losses"
            priority = 2 if loss_severity == 'severe' else 3
            actions = [f"Close {close_pct} of position", "Set stop-loss on remainder", "Monitor for recovery"]

        # Severe loss at ELEVATED risk - stronger action needed
        elif loss_severity in ['severe', 'critical'] and analysis.risk_level == RiskLevel.ELEVATED:
            strategy = RecoveryStrategy.PARTIAL_CLOSE
            confidence = 0.80
            rationale = f"{loss_severity.capitalize()} loss ({analysis.current_upnl_pct:.1%}) at ELEVATED risk ({analysis.averaging_steps} steps)."
            expected_outcome = "Significantly reduce exposure to limit further losses"
            risk_if_followed = "Lock in partial loss"
            risk_if_ignored = "Risk of reaching HIGH/CRITICAL risk levels"
            priority = 2
            actions = ["Close 50% of position immediately", "Consider hedging remainder"]

        # Default: Wait
        else:
            strategy = RecoveryStrategy.WAIT
            confidence = 0.50
            rationale = "No clear action needed. Monitor position."
            expected_outcome = "Position may recover or require action later"
            risk_if_followed = "Market conditions could change"
            risk_if_ignored = "N/A"
            priority = 5
            actions = ["Monitor closely"]

        return RecoveryRecommendation(
            symbol=analysis.symbol,
            strategy=strategy,
            confidence=confidence,
            rationale=rationale,
            expected_outcome=expected_outcome,
            risk_if_followed=risk_if_followed,
            risk_if_ignored=risk_if_ignored,
            priority=priority,
            actions=actions
        )

    def analyze_portfolio(self, positions: List[Dict],
                         averaging_steps: Dict[str, int] = None,
                         hedged_symbols: List[str] = None) -> List[RecoveryRecommendation]:
        """Analyze all positions and generate recommendations."""
        self.recommendations = []
        averaging_steps = averaging_steps or {}
        hedged_symbols = hedged_symbols or []

        for pos in positions:
            symbol = pos.get('symbol', '')
            contracts = float(pos.get('contracts', 0) or 0)

            if contracts == 0:
                continue

            # Get averaging steps for this position
            steps = averaging_steps.get(symbol, 0)

            # Check if position is hedged
            is_hedged = symbol in hedged_symbols

            # Analyze position
            analysis = self.analyze_position(pos, steps, is_hedged)

            # Only generate recommendations for losing positions
            if analysis.current_upnl < 0:
                recommendation = self.recommend_strategy(analysis)
                self.recommendations.append(recommendation)

        # Sort by priority (1 = highest)
        self.recommendations.sort(key=lambda r: (r.priority, -r.confidence))

        return self.recommendations

    def print_recommendations(self):
        """Print all recommendations in a formatted way."""
        print("\n" + "=" * 80)
        print("POSITION RECOVERY OPTIMIZER - RECOMMENDATIONS")
        print("=" * 80)

        if not self.recommendations:
            print("\n✅ No losing positions requiring action.")
            return

        strategy_emoji = {
            RecoveryStrategy.WAIT: "⏳",
            RecoveryStrategy.AVERAGE_DOWN: "📉",
            RecoveryStrategy.PARTIAL_CLOSE: "✂️",
            RecoveryStrategy.FULL_CLOSE: "🛑",
            RecoveryStrategy.HEDGE: "🛡️"
        }

        for i, rec in enumerate(self.recommendations, 1):
            emoji = strategy_emoji.get(rec.strategy, "❓")
            clean_symbol = rec.symbol.replace('/USDT:USDT', '').replace('/USDT', '')

            print(f"\n{i}. {emoji} {clean_symbol} - {rec.strategy.value} (Priority: {rec.priority}, Confidence: {rec.confidence:.0%})")
            print(f"   Rationale: {rec.rationale}")
            print(f"   Expected: {rec.expected_outcome}")
            print(f"   Actions:")
            for action in rec.actions:
                print(f"     • {action}")

        print("\n" + "=" * 80)

        # Summary
        by_strategy = {}
        for rec in self.recommendations:
            by_strategy[rec.strategy] = by_strategy.get(rec.strategy, 0) + 1

        print("SUMMARY:")
        for strategy, count in by_strategy.items():
            emoji = strategy_emoji.get(strategy, "❓")
            print(f"  {emoji} {strategy.value}: {count} positions")

        print("=" * 80)

    def get_priority_actions(self, max_priority: int = 3) -> List[RecoveryRecommendation]:
        """Get high-priority recommendations only."""
        return [r for r in self.recommendations if r.priority <= max_priority]


def test_recovery_optimizer():
    """Test the position recovery optimizer."""
    print("=" * 60)
    print("Testing Position Recovery Optimizer V1.0.0")
    print("=" * 60)

    optimizer = PositionRecoveryOptimizer()

    # Mock position data
    test_positions = [
        {
            'symbol': 'AXS/USDT:USDT',
            'side': 'long',
            'contracts': 163.3,
            'unrealizedPnl': -3.72,
            'initialMargin': 14.78,
            'leverage': 10,
            'entryPrice': 1.25,
            'markPrice': 1.02
        },
        {
            'symbol': 'BLUR/USDT:USDT',
            'side': 'long',
            'contracts': 2844.2,
            'unrealizedPnl': -4.10,
            'initialMargin': 10.87,
            'leverage': 10,
            'entryPrice': 0.038,
            'markPrice': 0.028
        },
        {
            'symbol': 'PIXEL/USDT:USDT',
            'side': 'long',
            'contracts': 10211.0,
            'unrealizedPnl': -3.92,
            'initialMargin': 10.17,
            'leverage': 10,
            'entryPrice': 0.010,
            'markPrice': 0.0065
        },
        {
            'symbol': 'DYM/USDT:USDT',
            'side': 'long',
            'contracts': 458.4,
            'unrealizedPnl': -1.48,
            'initialMargin': 3.56,
            'leverage': 10,
            'entryPrice': 0.078,
            'markPrice': 0.055
        }
    ]

    # Mock averaging steps
    averaging_steps = {
        'AXS/USDT:USDT': 3,    # ELEVATED
        'BLUR/USDT:USDT': 2,   # MODERATE
        'PIXEL/USDT:USDT': 2,  # MODERATE
        'DYM/USDT:USDT': 4     # HIGH
    }

    # DYM is hedged
    hedged = ['DYM/USDT:USDT']

    # Analyze
    recommendations = optimizer.analyze_portfolio(test_positions, averaging_steps, hedged)

    # Print results
    optimizer.print_recommendations()

    # Get priority actions
    print("\nPRIORITY ACTIONS (Priority 1-3):")
    priority_actions = optimizer.get_priority_actions(3)
    for rec in priority_actions:
        clean_symbol = rec.symbol.replace('/USDT:USDT', '')
        print(f"  • {clean_symbol}: {rec.strategy.value} - {rec.actions[0] if rec.actions else 'No action'}")

    print("\n✅ Position Recovery Optimizer Test Complete")


if __name__ == '__main__':
    test_recovery_optimizer()
