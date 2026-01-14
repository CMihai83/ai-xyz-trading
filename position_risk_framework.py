#!/usr/bin/env python3
"""
Position Risk Framework for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Sprint 8 - Grok Recommendation:
"Document closure criteria (e.g., max averaging steps, position age, drawdown thresholds)
and position risk profiles for the 20 active positions."

Provides:
- Position risk level assessment
- Closure criteria evaluation
- Risk profile generation
- Position health monitoring
- Automated risk alerts

Author: Claude + Grok Consortium
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field, asdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# State files
POSITION_STATE_FILE = '/root/ai_xyz/position_state.json'
RISK_PROFILE_FILE = '/root/ai_xyz/position_risk_profiles.json'


# =============================================================================
# RISK LEVEL DEFINITIONS
# =============================================================================

class RiskLevel(Enum):
    """Position risk level classification."""
    MINIMAL = "MINIMAL"       # 0 averaging steps, healthy
    LOW = "LOW"               # 1 averaging step
    MODERATE = "MODERATE"     # 2 averaging steps
    ELEVATED = "ELEVATED"     # 3 averaging steps
    HIGH = "HIGH"             # 4 averaging steps
    CRITICAL = "CRITICAL"     # 5 averaging steps (max)
    EXTREME = "EXTREME"       # Beyond normal parameters


class ClosureReason(Enum):
    """Reasons for position closure."""
    PROFIT_TARGET = "PROFIT_TARGET"
    STOP_LOSS = "STOP_LOSS"
    MAX_AVERAGING = "MAX_AVERAGING"
    MAX_AGE = "MAX_AGE"
    DRAWDOWN_LIMIT = "DRAWDOWN_LIMIT"
    MARGIN_RISK = "MARGIN_RISK"
    CORRELATION_RISK = "CORRELATION_RISK"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    HEALTHY = "HEALTHY"  # No closure needed


# =============================================================================
# CLOSURE CRITERIA CONFIGURATION
# =============================================================================

@dataclass
class ClosureCriteria:
    """
    Defines criteria for when a position should be closed.

    Based on Grok Sprint 8 recommendation for explicit closure criteria.
    """
    # Averaging-based criteria
    max_averaging_steps: int = 5          # Close at 5 steps (critical)
    warning_averaging_steps: int = 4      # Alert at 4 steps (high risk)

    # Age-based criteria (hours)
    max_position_age_hours: int = 168     # 7 days max
    stale_position_hours: int = 72        # 3 days = stale, needs review

    # P&L based criteria (percentage)
    profit_target_pct: float = 5.0        # Take profit at +5%
    stop_loss_pct: float = -90.0          # Stop loss at -90%
    drawdown_alert_pct: float = -25.0     # Alert at -25%

    # Zone-based criteria
    force_close_zones: List[str] = field(default_factory=lambda: [])
    profit_take_zones: List[str] = field(default_factory=lambda: [
        'PROFIT_TAKING', 'SURPLUS_DUMP'
    ])

    # Leverage-based criteria
    max_leverage_for_hold: int = 20       # Max leverage to continue holding
    reduce_leverage_threshold: int = 15   # Suggest leverage reduction above this

    # Hedge criteria
    hedge_max_age_hours: int = 48         # Hedges should be shorter-lived
    hedge_profit_target_pct: float = 2.0  # Lower profit target for hedges

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# POSITION RISK PROFILE
# =============================================================================

@dataclass
class PositionRiskProfile:
    """
    Comprehensive risk profile for a single position.
    """
    symbol: str
    timestamp: str

    # Position details
    entry_price: float
    current_amount: float
    original_amount: float
    side: str
    leverage: float
    is_hedge: bool
    opened_at: str

    # Risk metrics
    risk_level: str
    averaging_steps: int
    current_zone: str
    peak_upnl: float
    surplus_dump_stage: int

    # Calculated metrics
    position_age_hours: float
    size_multiplier: float  # current/original

    # Closure analysis
    closure_recommendation: str
    closure_reasons: List[str]
    closure_urgency: str  # IMMEDIATE, SOON, MONITOR, NONE

    # Additional context
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return asdict(self)


# =============================================================================
# POSITION RISK FRAMEWORK
# =============================================================================

class PositionRiskFramework:
    """
    Framework for assessing and managing position risk.

    Provides:
    - Risk level assessment based on averaging steps and other factors
    - Closure criteria evaluation
    - Risk profile generation for all positions
    """

    def __init__(self, criteria: Optional[ClosureCriteria] = None):
        self.criteria = criteria or ClosureCriteria()
        self.position_state: Dict = {}
        self.risk_profiles: Dict[str, PositionRiskProfile] = {}

    def load_position_state(self, state_file: str = POSITION_STATE_FILE) -> bool:
        """Load current position state from file."""
        try:
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    self.position_state = json.load(f)
                logger.info(f"Loaded position state from {state_file}")
                return True
        except Exception as e:
            logger.error(f"Failed to load position state: {e}")
        return False

    def get_risk_level(self, averaging_steps: int, is_hedge: bool = False) -> RiskLevel:
        """
        Determine risk level based on averaging steps.

        Risk escalates with each averaging step:
        - 0 steps: MINIMAL (position at or near entry)
        - 1 step:  LOW (one averaging executed)
        - 2 steps: MODERATE (position underwater, recovering)
        - 3 steps: ELEVATED (significant drawdown)
        - 4 steps: HIGH (approaching limits)
        - 5 steps: CRITICAL (at max, needs immediate attention)
        - >5:      EXTREME (beyond normal parameters)
        """
        if averaging_steps > 5:
            return RiskLevel.EXTREME
        elif averaging_steps == 5:
            return RiskLevel.CRITICAL
        elif averaging_steps == 4:
            return RiskLevel.HIGH
        elif averaging_steps == 3:
            return RiskLevel.ELEVATED
        elif averaging_steps == 2:
            return RiskLevel.MODERATE
        elif averaging_steps == 1:
            return RiskLevel.LOW
        else:
            return RiskLevel.MINIMAL

    def calculate_position_age(self, opened_at: str) -> float:
        """Calculate position age in hours."""
        try:
            # Handle timezone-aware datetime
            if '+' in opened_at or opened_at.endswith('Z'):
                opened_time = datetime.fromisoformat(opened_at.replace('Z', '+00:00'))
                now = datetime.now(timezone.utc)
            else:
                opened_time = datetime.fromisoformat(opened_at)
                now = datetime.now()

            age_delta = now - opened_time
            return age_delta.total_seconds() / 3600
        except Exception as e:
            logger.warning(f"Failed to parse date {opened_at}: {e}")
            return 0.0

    def evaluate_closure_criteria(self, symbol: str, position: Dict,
                                  averaging_steps: int, zone: str,
                                  peak_upnl: float, is_hedge: bool) -> Tuple[str, List[str], str]:
        """
        Evaluate if a position should be closed based on criteria.

        Returns:
            Tuple of (recommendation, reasons, urgency)
        """
        reasons = []
        urgency = "NONE"
        recommendation = "HOLD"

        # Get position age
        position_age = self.calculate_position_age(position.get('opened_at', ''))
        leverage = position.get('leverage', 10)

        # Check averaging steps
        if averaging_steps >= self.criteria.max_averaging_steps:
            reasons.append(f"Max averaging steps ({averaging_steps}/{self.criteria.max_averaging_steps})")
            urgency = "IMMEDIATE"
            recommendation = "CLOSE"
        elif averaging_steps >= self.criteria.warning_averaging_steps:
            reasons.append(f"High averaging steps ({averaging_steps})")
            urgency = max(urgency, "SOON", key=lambda x: ["NONE", "MONITOR", "SOON", "IMMEDIATE"].index(x))
            recommendation = "REVIEW"

        # Check position age
        max_age = self.criteria.hedge_max_age_hours if is_hedge else self.criteria.max_position_age_hours
        if position_age > max_age:
            reasons.append(f"Position age ({position_age:.1f}h) exceeds max ({max_age}h)")
            urgency = "SOON" if urgency == "NONE" else urgency
            recommendation = "CLOSE" if recommendation != "CLOSE" else recommendation
        elif position_age > self.criteria.stale_position_hours:
            reasons.append(f"Position stale ({position_age:.1f}h)")
            recommendation = "REVIEW" if recommendation == "HOLD" else recommendation

        # Check zone
        if zone in self.criteria.profit_take_zones:
            reasons.append(f"In {zone} zone - profit taking opportunity")
            if recommendation == "HOLD":
                recommendation = "TAKE_PROFIT"
                urgency = "MONITOR"

        # Check leverage
        if leverage > self.criteria.max_leverage_for_hold:
            reasons.append(f"Leverage ({leverage}x) too high")
            urgency = "IMMEDIATE"
            recommendation = "CLOSE"
        elif leverage > self.criteria.reduce_leverage_threshold:
            reasons.append(f"Consider reducing leverage ({leverage}x)")

        # If no issues found
        if not reasons:
            reasons.append("Position healthy")
            recommendation = "HOLD"

        return recommendation, reasons, urgency

    def generate_risk_profile(self, symbol: str) -> Optional[PositionRiskProfile]:
        """Generate risk profile for a single position."""
        if not self.position_state:
            return None

        positions = self.position_state.get('active_positions', {})
        zones = self.position_state.get('position_zones', {})
        avg_steps = self.position_state.get('averaging_steps', {})
        peak_upnl = self.position_state.get('peak_upnl', {})
        surplus_stage = self.position_state.get('surplus_dump_stage', {})
        original_sizes = self.position_state.get('original_sizes', {})

        if symbol not in positions:
            return None

        position = positions[symbol]
        is_hedge = position.get('is_hedge', False)
        averaging = avg_steps.get(symbol, 0)
        zone = zones.get(symbol, 'NEUTRAL')

        # Calculate metrics
        risk_level = self.get_risk_level(averaging, is_hedge)
        position_age = self.calculate_position_age(position.get('opened_at', ''))
        current_amount = position.get('amount', 0)
        original = original_sizes.get(symbol, current_amount)
        size_multiplier = current_amount / original if original > 0 else 1.0

        # Evaluate closure
        recommendation, reasons, urgency = self.evaluate_closure_criteria(
            symbol, position, averaging, zone, peak_upnl.get(symbol, 0), is_hedge
        )

        # Generate notes
        notes = []
        if is_hedge:
            notes.append("Hedge position - shorter lifecycle expected")
        if averaging >= 3:
            notes.append(f"Position has averaged {averaging} times - monitor closely")
        if size_multiplier > 2.0:
            notes.append(f"Position size {size_multiplier:.1f}x original")
        if zone == 'AVERAGING':
            notes.append("Currently in averaging zone - underwater")
        if zone in ['PROFIT_TAKING', 'SURPLUS_DUMP']:
            notes.append("In profit zone - consider taking profits")

        profile = PositionRiskProfile(
            symbol=symbol,
            timestamp=datetime.now().isoformat(),
            entry_price=position.get('entry_price', 0),
            current_amount=current_amount,
            original_amount=original,
            side=position.get('side', 'unknown'),
            leverage=position.get('leverage', 10),
            is_hedge=is_hedge,
            opened_at=position.get('opened_at', ''),
            risk_level=risk_level.value,
            averaging_steps=averaging,
            current_zone=zone,
            peak_upnl=peak_upnl.get(symbol, 0),
            surplus_dump_stage=surplus_stage.get(symbol, 0),
            position_age_hours=position_age,
            size_multiplier=size_multiplier,
            closure_recommendation=recommendation,
            closure_reasons=reasons,
            closure_urgency=urgency,
            notes=notes
        )

        return profile

    def generate_all_risk_profiles(self) -> Dict[str, PositionRiskProfile]:
        """Generate risk profiles for all positions."""
        self.risk_profiles = {}

        if not self.position_state:
            self.load_position_state()

        positions = self.position_state.get('active_positions', {})

        for symbol in positions:
            profile = self.generate_risk_profile(symbol)
            if profile:
                self.risk_profiles[symbol] = profile

        logger.info(f"Generated {len(self.risk_profiles)} risk profiles")
        return self.risk_profiles

    def get_positions_by_risk_level(self) -> Dict[str, List[str]]:
        """Group positions by risk level."""
        by_level = {level.value: [] for level in RiskLevel}

        for symbol, profile in self.risk_profiles.items():
            by_level[profile.risk_level].append(symbol)

        return by_level

    def get_positions_requiring_action(self) -> Dict[str, List[Tuple[str, str, str]]]:
        """
        Get positions requiring action.

        Returns:
            Dict keyed by urgency with list of (symbol, recommendation, reasons)
        """
        by_urgency = {
            'IMMEDIATE': [],
            'SOON': [],
            'MONITOR': []
        }

        for symbol, profile in self.risk_profiles.items():
            if profile.closure_urgency != 'NONE':
                by_urgency[profile.closure_urgency].append((
                    symbol,
                    profile.closure_recommendation,
                    ', '.join(profile.closure_reasons)
                ))

        return by_urgency

    def generate_summary_report(self) -> Dict[str, Any]:
        """Generate summary report of all position risks."""
        if not self.risk_profiles:
            self.generate_all_risk_profiles()

        by_risk = self.get_positions_by_risk_level()
        by_urgency = self.get_positions_requiring_action()

        # Count statistics
        total = len(self.risk_profiles)
        hedges = sum(1 for p in self.risk_profiles.values() if p.is_hedge)
        avg_leverage = sum(p.leverage for p in self.risk_profiles.values()) / total if total > 0 else 0
        avg_age = sum(p.position_age_hours for p in self.risk_profiles.values()) / total if total > 0 else 0

        # Calculate risk distribution
        risk_distribution = {level: len(symbols) for level, symbols in by_risk.items()}

        # Action summary
        immediate_count = len(by_urgency['IMMEDIATE'])
        soon_count = len(by_urgency['SOON'])
        monitor_count = len(by_urgency['MONITOR'])

        report = {
            'timestamp': datetime.now().isoformat(),
            'version': '1.0.0',
            'summary': {
                'total_positions': total,
                'hedge_positions': hedges,
                'main_positions': total - hedges,
                'average_leverage': avg_leverage,
                'average_age_hours': avg_age
            },
            'risk_distribution': risk_distribution,
            'action_required': {
                'immediate': immediate_count,
                'soon': soon_count,
                'monitor': monitor_count,
                'healthy': total - immediate_count - soon_count - monitor_count
            },
            'positions_by_risk': by_risk,
            'positions_requiring_action': {
                urgency: [
                    {'symbol': s, 'recommendation': r, 'reasons': reasons}
                    for s, r, reasons in items
                ]
                for urgency, items in by_urgency.items()
            },
            'closure_criteria': self.criteria.to_dict()
        }

        return report

    def save_profiles(self, output_file: str = RISK_PROFILE_FILE):
        """Save risk profiles to file."""
        try:
            report = self.generate_summary_report()
            report['individual_profiles'] = {
                symbol: profile.to_dict()
                for symbol, profile in self.risk_profiles.items()
            }

            with open(output_file, 'w') as f:
                json.dump(report, f, indent=2, default=str)

            logger.info(f"Risk profiles saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save risk profiles: {e}")

    def print_report(self):
        """Print risk report to console."""
        if not self.risk_profiles:
            self.generate_all_risk_profiles()

        report = self.generate_summary_report()

        print("\n" + "=" * 70)
        print("POSITION RISK FRAMEWORK REPORT V1.0.0")
        print("=" * 70)
        print(f"Report Time: {report['timestamp']}")

        # Summary
        summary = report['summary']
        print(f"\n{'=' * 50}")
        print("PORTFOLIO SUMMARY")
        print(f"{'=' * 50}")
        print(f"  Total Positions:   {summary['total_positions']}")
        print(f"  Main Positions:    {summary['main_positions']}")
        print(f"  Hedge Positions:   {summary['hedge_positions']}")
        print(f"  Average Leverage:  {summary['average_leverage']:.1f}x")
        print(f"  Average Age:       {summary['average_age_hours']:.1f} hours")

        # Risk Distribution
        print(f"\n{'-' * 50}")
        print("RISK DISTRIBUTION")
        print(f"{'-' * 50}")
        for level, count in report['risk_distribution'].items():
            if count > 0:
                bar = '█' * count
                print(f"  {level:15s} [{count:2d}] {bar}")

        # Action Required
        print(f"\n{'-' * 50}")
        print("ACTION REQUIRED")
        print(f"{'-' * 50}")
        action = report['action_required']
        print(f"  IMMEDIATE:  {action['immediate']} positions")
        print(f"  SOON:       {action['soon']} positions")
        print(f"  MONITOR:    {action['monitor']} positions")
        print(f"  HEALTHY:    {action['healthy']} positions")

        # Positions requiring action
        for urgency in ['IMMEDIATE', 'SOON', 'MONITOR']:
            positions = report['positions_requiring_action'].get(urgency, [])
            if positions:
                print(f"\n{'-' * 50}")
                print(f"{urgency} ACTION NEEDED")
                print(f"{'-' * 50}")
                for item in positions:
                    print(f"  {item['symbol']}")
                    print(f"    Recommendation: {item['recommendation']}")
                    print(f"    Reasons: {item['reasons']}")

        # Individual profiles (high risk only)
        high_risk_levels = ['CRITICAL', 'EXTREME', 'HIGH']
        high_risk_positions = [
            (symbol, profile) for symbol, profile in self.risk_profiles.items()
            if profile.risk_level in high_risk_levels
        ]

        if high_risk_positions:
            print(f"\n{'-' * 50}")
            print("HIGH RISK POSITION DETAILS")
            print(f"{'-' * 50}")
            for symbol, profile in sorted(high_risk_positions,
                                         key=lambda x: ['HIGH', 'CRITICAL', 'EXTREME'].index(x[1].risk_level)
                                         if x[1].risk_level in ['HIGH', 'CRITICAL', 'EXTREME'] else 0,
                                         reverse=True):
                print(f"\n  {symbol}")
                print(f"    Risk Level: {profile.risk_level}")
                print(f"    Averaging Steps: {profile.averaging_steps}/5")
                print(f"    Zone: {profile.current_zone}")
                print(f"    Leverage: {profile.leverage}x")
                print(f"    Age: {profile.position_age_hours:.1f} hours")
                print(f"    Size Multiplier: {profile.size_multiplier:.2f}x")
                print(f"    Recommendation: {profile.closure_recommendation}")
                if profile.notes:
                    for note in profile.notes:
                        print(f"    Note: {note}")

        print("\n" + "=" * 70)


# =============================================================================
# STANDALONE EXECUTION
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("POSITION RISK FRAMEWORK V1.0.0 TEST")
    print("=" * 60)

    # Initialize framework
    framework = PositionRiskFramework()

    # Load position state
    if framework.load_position_state():
        # Generate all profiles
        profiles = framework.generate_all_risk_profiles()

        # Print report
        framework.print_report()

        # Save profiles
        framework.save_profiles()

        print("\nRisk profiles saved to:", RISK_PROFILE_FILE)
    else:
        print("ERROR: Could not load position state")

    print("\n" + "=" * 60)
    print("Position Risk Framework V1.0.0 test completed!")
    print("=" * 60)
