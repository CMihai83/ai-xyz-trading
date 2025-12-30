#!/usr/bin/env python3
"""
V3: Adaptive Threshold Engine
Dynamically calculates optimal averaging triggers based on market conditions
"""

import numpy as np
from datetime import datetime, timedelta
import json
import os

class AdaptiveThresholdEngine:
    """
    AI-powered threshold calculation that adapts to market conditions
    """

    def __init__(self, base_threshold=-0.25):
        self.base_threshold = base_threshold
        self.market_memory = {}
        self.performance_history = self.load_performance_history()

    def load_performance_history(self):
        """Load historical performance data"""
        try:
            with open('/root/ai_xyz/performance_history.json', 'r') as f:
                return json.load(f)
        except:
            return {}

    def calculate_optimal_trigger(self, symbol, market_context):
        """
        Calculate optimal averaging trigger using multiple factors

        Args:
            symbol: Trading symbol
            market_context: Dict with volatility, regime, sentiment, etc.

        Returns:
            float: Optimal trigger threshold
        """
        # Base threshold from historical optimization
        base_threshold = self.get_historical_optimal(symbol)

        # Market regime adjustment
        regime_multiplier = self.get_regime_multiplier(market_context.get('regime', 'neutral'))

        # Volatility adjustment (higher volatility = higher threshold)
        volatility = market_context.get('volatility', 0.5)
        volatility_multiplier = 1 + (volatility * 0.3)

        # Sentiment adjustment (negative sentiment = lower threshold)
        sentiment = market_context.get('sentiment', 0)
        sentiment_multiplier = 1 + (sentiment * 0.1)

        # Recent performance adjustment
        performance_multiplier = self.get_performance_multiplier(symbol)

        # Calculate final threshold
        optimal_threshold = (base_threshold *
                           regime_multiplier *
                           volatility_multiplier *
                           sentiment_multiplier *
                           performance_multiplier)

        # Constrain to reasonable bounds
        optimal_threshold = max(optimal_threshold, -0.50)  # Not too aggressive
        optimal_threshold = min(optimal_threshold, -0.05)  # Not too conservative

        return optimal_threshold

    def get_historical_optimal(self, symbol):
        """Get historically optimal threshold for symbol"""
        history = self.performance_history.get(symbol, [])
        if not history:
            return self.base_threshold

        # Simple optimization: threshold with best Sharpe ratio
        best_threshold = self.base_threshold
        best_sharpe = -1

        for threshold in [-0.05, -0.10, -0.15, -0.20, -0.25, -0.30]:
            threshold_history = [h for h in history if h.get('threshold', self.base_threshold) == threshold]
            if threshold_history:
                returns = [h['return'] for h in threshold_history]
                if returns:
                    sharpe = np.mean(returns) / (np.std(returns) + 1e-6)
                    if sharpe > best_sharpe:
                        best_sharpe = sharpe
                        best_threshold = threshold

        return best_threshold

    def get_regime_multiplier(self, regime):
        """Get multiplier based on market regime"""
        multipliers = {
            'bull': 0.8,    # More conservative in bull markets
            'bear': 1.2,    # More aggressive in bear markets
            'neutral': 1.0,
            'volatile': 1.1 # Slightly more aggressive in volatile markets
        }
        return multipliers.get(regime, 1.0)

    def get_performance_multiplier(self, symbol):
        """Adjust based on recent performance"""
        history = self.performance_history.get(symbol, [])
        if len(history) < 5:
            return 1.0

        recent = history[-5:]  # Last 5 trades
        win_rate = sum(1 for h in recent if h.get('return', 0) > 0) / len(recent)

        if win_rate > 0.7:
            return 0.9  # More conservative when winning
        elif win_rate < 0.3:
            return 1.1  # More aggressive when losing
        else:
            return 1.0

    def update_performance(self, symbol, trade_data):
        """Update performance history"""
        if symbol not in self.performance_history:
            self.performance_history[symbol] = []

        self.performance_history[symbol].append({
            'timestamp': datetime.now().isoformat(),
            'return': trade_data.get('return', 0),
            'threshold': trade_data.get('threshold', self.base_threshold),
            'duration': trade_data.get('duration', 0)
        })

        # Keep only last 100 trades
        self.performance_history[symbol] = self.performance_history[symbol][-100:]

        # Save to disk
        try:
            with open('/root/ai_xyz/performance_history.json', 'w') as f:
                json.dump(self.performance_history, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save performance history: {e}")