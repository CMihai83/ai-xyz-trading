"""
Core Components for Cardinal Rules Compliant Trading System
"""

from .live_positions_registry import (
    LivePositionsRegistry,
    Position,
    PositionZone,
    PositionDirection,
    AveragingStep
)

from .exchange_reconciliation import (
    ExchangeReconciliationService,
    ReconciliationResult
)

from .zone_state_machine import (
    ZoneStateMachine,
    ZoneTransitionResult
)

from .surplus_dump_manager import (
    SurplusDumpManager
)

__all__ = [
    'LivePositionsRegistry',
    'Position',
    'PositionZone',
    'PositionDirection',
    'AveragingStep',
    'ExchangeReconciliationService',
    'ReconciliationResult',
    'ZoneStateMachine',
    'ZoneTransitionResult',
    'SurplusDumpManager'
]

# Version info
__version__ = '1.0.0'
__author__ = 'AI-XYZ Compliant Trading System'