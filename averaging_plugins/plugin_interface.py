#!/usr/bin/env python3
"""
Base Plugin Interface for Averaging Strategies
Allows modular integration of different averaging algorithms
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Optional, List
from datetime import datetime
from enum import Enum

class SignalAction(Enum):
    """Possible actions for averaging signals"""
    AVERAGE = "average"
    HOLD = "hold"
    REDUCE = "reduce"
    CLOSE = "close"

@dataclass
class Signal:
    """Signal returned by averaging plugins"""
    action: SignalAction
    confidence: float  # 0.0 to 1.0
    size: Optional[float] = None  # Position size if averaging
    reason: str = ""
    metadata: Dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}
        # Validate confidence is in range
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"Confidence must be between 0 and 1, got {self.confidence}")

@dataclass
class MarketData:
    """Market data structure for plugin analysis"""
    symbol: str
    current_price: float
    bid: float
    ask: float
    volume_24h: float
    high_24h: float
    low_24h: float
    timestamp: datetime
    candles: Optional[Dict[str, List]] = None  # Timeframe -> candle data
    indicators: Optional[Dict[str, float]] = None  # Indicator -> value

class AveragingPlugin(ABC):
    """Base class for all averaging strategy plugins"""

    def __init__(self, config: Dict = None):
        """Initialize plugin with optional configuration"""
        self.config = config or {}
        self.name = self.__class__.__name__
        self._performance_stats = {
            'signals_generated': 0,
            'successful_signals': 0,
            'total_profit': 0.0,
            'total_loss': 0.0
        }

    @abstractmethod
    def analyze(self, position: Dict, market_data: MarketData) -> Signal:
        """
        Analyze position and market data to generate averaging signal

        Args:
            position: Current position data from position_state.json
            market_data: Current market data including prices and indicators

        Returns:
            Signal object with action, confidence, and reasoning
        """
        pass

    @abstractmethod
    def get_priority(self) -> int:
        """
        Get plugin priority (higher number = higher priority)
        Used by orchestrator to resolve conflicts

        Returns:
            Integer priority value (typically 0-100)
        """
        pass

    def get_required_indicators(self) -> List[str]:
        """
        Optional: Return list of required technical indicators
        Helps orchestrator prepare data before calling analyze()

        Returns:
            List of indicator names (e.g., ['RSI', 'MACD', 'BB'])
        """
        return []

    def get_required_timeframes(self) -> List[str]:
        """
        Optional: Return list of required candle timeframes
        Helps orchestrator fetch necessary candle data

        Returns:
            List of timeframes (e.g., ['1m', '5m', '15m', '1h'])
        """
        return []

    def update_performance(self, signal: Signal, result: Dict):
        """
        Update plugin performance statistics after trade execution

        Args:
            signal: The signal that was generated
            result: Trade execution result with profit/loss info
        """
        self._performance_stats['signals_generated'] += 1

        if result.get('successful', False):
            self._performance_stats['successful_signals'] += 1

        profit = result.get('profit', 0.0)
        if profit > 0:
            self._performance_stats['total_profit'] += profit
        else:
            self._performance_stats['total_loss'] += abs(profit)

    def get_performance_stats(self) -> Dict:
        """
        Get plugin performance statistics

        Returns:
            Dictionary with performance metrics
        """
        stats = self._performance_stats.copy()

        # Calculate derived metrics
        if stats['signals_generated'] > 0:
            stats['success_rate'] = stats['successful_signals'] / stats['signals_generated']
        else:
            stats['success_rate'] = 0.0

        total_pnl = stats['total_profit'] - stats['total_loss']
        stats['total_pnl'] = total_pnl

        if stats['total_loss'] > 0:
            stats['profit_factor'] = stats['total_profit'] / stats['total_loss']
        else:
            stats['profit_factor'] = float('inf') if stats['total_profit'] > 0 else 0.0

        return stats

    def validate_position(self, position: Dict) -> bool:
        """
        Validate that position has required fields for analysis

        Args:
            position: Position data to validate

        Returns:
            True if position is valid for this plugin
        """
        required_fields = ['entry_price', 'amount', 'side', 'leverage']
        return all(field in position for field in required_fields)

    def __str__(self) -> str:
        """String representation of plugin"""
        return f"{self.name}(priority={self.get_priority()})"

    def __repr__(self) -> str:
        """Detailed representation of plugin"""
        stats = self.get_performance_stats()
        return (f"{self.name}(priority={self.get_priority()}, "
                f"signals={stats['signals_generated']}, "
                f"success_rate={stats['success_rate']:.2%})")

class PluginManager:
    """Manages loading and registration of averaging plugins"""

    def __init__(self):
        self.plugins: List[AveragingPlugin] = []
        self._plugin_registry = {}

    def register_plugin(self, plugin: AveragingPlugin):
        """Register a new averaging plugin"""
        plugin_name = plugin.__class__.__name__

        if plugin_name in self._plugin_registry:
            raise ValueError(f"Plugin {plugin_name} already registered")

        self.plugins.append(plugin)
        self._plugin_registry[plugin_name] = plugin

        print(f"✅ Registered plugin: {plugin}")

    def get_plugin(self, name: str) -> Optional[AveragingPlugin]:
        """Get plugin by name"""
        return self._plugin_registry.get(name)

    def get_sorted_plugins(self) -> List[AveragingPlugin]:
        """Get plugins sorted by priority (highest first)"""
        return sorted(self.plugins, key=lambda p: p.get_priority(), reverse=True)

    def get_plugin_stats(self) -> Dict:
        """Get performance stats for all plugins"""
        return {
            plugin.name: plugin.get_performance_stats()
            for plugin in self.plugins
        }