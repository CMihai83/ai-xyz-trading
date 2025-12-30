#!/usr/bin/env python3
"""
Kelly Criterion Position Sizing for AI-XYZ
Implements quarter-Kelly for conservative position sizing
Based on research: f* = μ / σ² where μ is mean excess returns and σ² is variance
"""

import numpy as np
import json
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta

class KellyCriterionSizer:
    """
    Kelly Criterion position sizing with safety adjustments
    Uses quarter-Kelly (25% of full Kelly) for crypto markets
    """

    def __init__(self, lookback_days: int = 30):
        self.lookback_days = lookback_days
        self.confidence_factor = 0.25  # Quarter Kelly for safety
        self.min_position_pct = 0.01   # Minimum 1% position
        self.max_position_pct = 0.30   # Maximum 30% position
        self.trade_history_file = '/app/trade_history.json'

    def calculate_kelly_fraction(self,
                                win_rate: float,
                                avg_win: float,
                                avg_loss: float,
                                confidence: float = 1.0) -> float:
        """
        Calculate Kelly fraction for position sizing

        Formula: f* = (p * b - q) / b
        where:
        - p = probability of win
        - q = probability of loss (1 - p)
        - b = ratio of win amount to loss amount
        """
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            return self.min_position_pct

        p = win_rate
        q = 1 - win_rate
        b = abs(avg_win / avg_loss) if avg_loss != 0 else 1.0

        # Full Kelly
        kelly_full = (p * b - q) / b if b > 0 else 0

        # Apply safety factors
        kelly_fraction = kelly_full * self.confidence_factor * confidence

        # Apply min/max constraints
        kelly_fraction = max(self.min_position_pct,
                           min(self.max_position_pct, kelly_fraction))

        return kelly_fraction

    def calculate_from_returns(self, returns: List[float]) -> float:
        """
        Calculate Kelly fraction from historical returns
        Using Sharpe ratio method: f* = μ / σ²
        """
        if len(returns) < 10:
            return self.min_position_pct

        returns_array = np.array(returns)

        # Calculate mean excess return and variance
        mean_return = np.mean(returns_array)
        variance = np.var(returns_array)

        if variance == 0:
            return self.min_position_pct

        # Kelly fraction using returns
        kelly_full = mean_return / variance

        # Apply quarter-Kelly and constraints
        kelly_fraction = kelly_full * self.confidence_factor
        kelly_fraction = max(self.min_position_pct,
                           min(self.max_position_pct, kelly_fraction))

        return kelly_fraction

    def get_position_size(self,
                         symbol: str,
                         total_capital: float,
                         market_volatility: float = 1.0) -> Dict:
        """
        Calculate position size for a symbol based on Kelly criterion
        """
        # Load trade history
        trade_stats = self._load_trade_history(symbol)

        if trade_stats['trade_count'] < 5:
            # Not enough history, use minimum size
            kelly_fraction = self.min_position_pct
        else:
            # Calculate Kelly fraction from trade statistics
            kelly_fraction = self.calculate_kelly_fraction(
                win_rate=trade_stats['win_rate'],
                avg_win=trade_stats['avg_win'],
                avg_loss=trade_stats['avg_loss'],
                confidence=trade_stats.get('confidence', 0.7)
            )

        # Adjust for market volatility (reduce size in high volatility)
        volatility_adjustment = 1 / (1 + market_volatility * 0.5)
        adjusted_fraction = kelly_fraction * volatility_adjustment

        # Calculate position size in USD
        position_size = total_capital * adjusted_fraction

        return {
            'symbol': symbol,
            'kelly_fraction': kelly_fraction,
            'adjusted_fraction': adjusted_fraction,
            'position_size': position_size,
            'volatility_adjustment': volatility_adjustment,
            'trade_stats': trade_stats
        }

    def _load_trade_history(self, symbol: str) -> Dict:
        """Load and analyze trade history for a symbol"""
        default_stats = {
            'trade_count': 0,
            'win_rate': 0.5,
            'avg_win': 0.02,   # 2% average win
            'avg_loss': 0.01,  # 1% average loss
            'confidence': 0.5
        }

        if not os.path.exists(self.trade_history_file):
            return default_stats

        try:
            with open(self.trade_history_file, 'r') as f:
                history = json.load(f)

            symbol_trades = history.get(symbol, [])
            if len(symbol_trades) < 5:
                return default_stats

            # Calculate statistics from recent trades
            recent_trades = symbol_trades[-50:]  # Last 50 trades

            wins = [t['pnl_pct'] for t in recent_trades if t['pnl_pct'] > 0]
            losses = [abs(t['pnl_pct']) for t in recent_trades if t['pnl_pct'] < 0]

            win_rate = len(wins) / len(recent_trades) if recent_trades else 0.5
            avg_win = np.mean(wins) if wins else 0.02
            avg_loss = np.mean(losses) if losses else 0.01

            # Calculate confidence based on consistency
            if len(recent_trades) >= 20:
                confidence = min(0.9, 0.5 + (win_rate - 0.5) * 2)
            else:
                confidence = 0.5 + (len(recent_trades) / 40)  # Scale up to 1.0

            return {
                'trade_count': len(recent_trades),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'confidence': confidence
            }

        except Exception as e:
            print(f"Error loading trade history: {e}")
            return default_stats

    def optimize_portfolio_allocation(self,
                                     symbols: List[str],
                                     total_capital: float,
                                     correlations: Optional[Dict] = None) -> Dict:
        """
        Optimize capital allocation across multiple symbols
        Considers correlations if provided
        """
        allocations = {}
        remaining_capital = total_capital

        # Get Kelly fraction for each symbol
        for symbol in symbols:
            kelly_data = self.get_position_size(symbol, total_capital)
            allocations[symbol] = {
                'kelly_fraction': kelly_data['kelly_fraction'],
                'raw_size': kelly_data['position_size']
            }

        # Normalize allocations if they exceed 100%
        total_fraction = sum(a['kelly_fraction'] for a in allocations.values())

        if total_fraction > 1.0:
            # Scale down proportionally
            scale_factor = 0.95 / total_fraction  # Leave 5% as reserve
            for symbol in allocations:
                allocations[symbol]['kelly_fraction'] *= scale_factor
                allocations[symbol]['allocated_size'] = (
                    total_capital * allocations[symbol]['kelly_fraction']
                )
        else:
            for symbol in allocations:
                allocations[symbol]['allocated_size'] = allocations[symbol]['raw_size']

        return allocations


if __name__ == "__main__":
    # Test Kelly Criterion sizing
    kelly = KellyCriterionSizer()

    # Test with sample data
    test_symbol = "BTC/USDT"
    total_capital = 1000.0

    result = kelly.get_position_size(test_symbol, total_capital, market_volatility=0.8)

    print("Kelly Criterion Position Sizing Test")
    print("=" * 40)
    print(f"Symbol: {result['symbol']}")
    print(f"Kelly Fraction: {result['kelly_fraction']:.4f}")
    print(f"Adjusted Fraction: {result['adjusted_fraction']:.4f}")
    print(f"Position Size: ${result['position_size']:.2f}")
    print(f"Volatility Adjustment: {result['volatility_adjustment']:.4f}")
    print(f"Trade Stats: {result['trade_stats']}")