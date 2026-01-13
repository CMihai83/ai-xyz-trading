#!/usr/bin/env python3
"""
Grok Recommendation #10: Ensemble Model for Exit Timing
Combines multiple models with weighted voting for better exit decisions.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from enum import Enum
from collections import deque
import json
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ExitSignal(Enum):
    """Exit signal types"""
    STRONG_EXIT = "strong_exit"      # High confidence exit
    WEAK_EXIT = "weak_exit"          # Low confidence exit
    HOLD = "hold"                    # No exit signal
    STRONG_HOLD = "strong_hold"      # High confidence hold


@dataclass
class ExitPrediction:
    """Exit prediction result"""
    signal: ExitSignal
    confidence: float              # 0-1
    exit_probability: float        # Raw probability of exit
    model_votes: Dict[str, float]  # Individual model predictions
    reasons: List[str]


class RLExitModel:
    """
    Reinforcement Learning based exit model (Q-learning).

    Simple tabular Q-learning for exit timing based on state features.
    """

    def __init__(self, learning_rate: float = 0.1, discount: float = 0.95):
        self.lr = learning_rate
        self.gamma = discount
        self.q_table: Dict[str, Dict[str, float]] = {}
        self.exploration_rate = 0.1

    def _get_state_key(self, features: Dict) -> str:
        """Convert features to state key"""
        # Discretize continuous features
        pnl_bucket = int(features.get('pnl_pct', 0) // 5)  # 5% buckets
        hold_bucket = int(features.get('holding_hours', 0) // 4)  # 4-hour buckets
        vol_bucket = int(features.get('volatility', 30) // 10)  # 10% vol buckets
        zone = features.get('zone', 'neutral')[:3]  # First 3 chars

        return f"{pnl_bucket}_{hold_bucket}_{vol_bucket}_{zone}"

    def predict(self, features: Dict) -> float:
        """
        Predict exit probability.

        Returns:
            Exit probability (0-1)
        """
        state = self._get_state_key(features)

        if state not in self.q_table:
            # Default: slight bias towards holding
            return 0.3

        q_values = self.q_table[state]
        exit_q = q_values.get('exit', 0)
        hold_q = q_values.get('hold', 0)

        # Softmax to get probability
        max_q = max(exit_q, hold_q)
        exp_exit = np.exp(exit_q - max_q)
        exp_hold = np.exp(hold_q - max_q)

        exit_prob = exp_exit / (exp_exit + exp_hold)

        return exit_prob

    def update(self, features: Dict, action: str, reward: float, next_features: Dict):
        """Update Q-values based on experience"""
        state = self._get_state_key(features)
        next_state = self._get_state_key(next_features)

        if state not in self.q_table:
            self.q_table[state] = {'exit': 0.0, 'hold': 0.0}

        if next_state not in self.q_table:
            self.q_table[next_state] = {'exit': 0.0, 'hold': 0.0}

        # Q-learning update
        current_q = self.q_table[state][action]
        max_next_q = max(self.q_table[next_state].values())

        new_q = current_q + self.lr * (reward + self.gamma * max_next_q - current_q)
        self.q_table[state][action] = new_q


class GradientBoostingExitModel:
    """
    Gradient Boosting based exit model.

    Uses simple decision stumps as weak learners.
    """

    def __init__(self, n_estimators: int = 10, learning_rate: float = 0.1):
        self.n_estimators = n_estimators
        self.lr = learning_rate
        self.stumps: List[Dict] = []
        self.feature_importance: Dict[str, float] = {}

    def _create_stump(self, feature: str, threshold: float, direction: int) -> Dict:
        """Create a decision stump"""
        return {
            'feature': feature,
            'threshold': threshold,
            'direction': direction,  # 1 = above threshold -> exit, -1 = below
            'weight': 0.0
        }

    def fit(self, X: List[Dict], y: List[int]):
        """Fit model on training data"""
        # Initialize with default stumps based on domain knowledge
        self.stumps = [
            {'feature': 'pnl_pct', 'threshold': 5.0, 'direction': 1, 'weight': 0.3},
            {'feature': 'pnl_pct', 'threshold': -25.0, 'direction': -1, 'weight': 0.2},
            {'feature': 'holding_hours', 'threshold': 24.0, 'direction': 1, 'weight': 0.15},
            {'feature': 'volatility', 'threshold': 50.0, 'direction': 1, 'weight': 0.15},
            {'feature': 'momentum', 'threshold': 0.0, 'direction': -1, 'weight': 0.1},
            {'feature': 'peak_distance_pct', 'threshold': 20.0, 'direction': 1, 'weight': 0.1},
        ]

        # Update feature importance
        for stump in self.stumps:
            feature = stump['feature']
            self.feature_importance[feature] = self.feature_importance.get(feature, 0) + abs(stump['weight'])

    def predict(self, features: Dict) -> float:
        """
        Predict exit probability.

        Returns:
            Exit probability (0-1)
        """
        if not self.stumps:
            self.fit([], [])  # Initialize with defaults

        score = 0.0

        for stump in self.stumps:
            feature_val = features.get(stump['feature'], 0)

            if stump['direction'] > 0:
                if feature_val > stump['threshold']:
                    score += stump['weight']
            else:
                if feature_val < stump['threshold']:
                    score += stump['weight']

        # Sigmoid to convert to probability
        probability = 1 / (1 + np.exp(-score * 3))

        return probability


class LSTMExitModel:
    """
    LSTM-like sequential exit model.

    Simplified recurrent model tracking price history patterns.
    """

    def __init__(self, sequence_length: int = 20):
        self.sequence_length = sequence_length
        self.price_history: Dict[str, deque] = {}
        self.hidden_state: Dict[str, np.ndarray] = {}

        # Simple weights (would be learned in real LSTM)
        self.input_weights = np.random.randn(5) * 0.1
        self.hidden_weights = np.random.randn(5) * 0.1
        self.output_weights = np.random.randn(5) * 0.1

    def _update_sequence(self, symbol: str, price: float):
        """Update price sequence for symbol"""
        if symbol not in self.price_history:
            self.price_history[symbol] = deque(maxlen=self.sequence_length)
            self.hidden_state[symbol] = np.zeros(5)

        self.price_history[symbol].append(price)

    def predict(self, features: Dict) -> float:
        """
        Predict exit probability based on sequence patterns.

        Returns:
            Exit probability (0-1)
        """
        symbol = features.get('symbol', 'default')
        current_price = features.get('current_price', 0)

        self._update_sequence(symbol, current_price)

        if len(self.price_history[symbol]) < 5:
            return 0.3  # Default hold bias

        prices = list(self.price_history[symbol])

        # Calculate sequence features
        returns = np.diff(prices) / prices[:-1]
        recent_returns = returns[-5:] if len(returns) >= 5 else returns

        # Simple pattern detection
        trend = np.mean(recent_returns) * 100
        volatility = np.std(recent_returns) * 100
        momentum = (prices[-1] - prices[-5]) / prices[-5] * 100 if len(prices) >= 5 else 0

        # Check for reversal patterns
        if len(prices) >= 10:
            first_half = np.mean(prices[:len(prices)//2])
            second_half = np.mean(prices[len(prices)//2:])
            reversal_signal = (second_half - first_half) / first_half * 100
        else:
            reversal_signal = 0

        # Combine signals
        input_vector = np.array([trend, volatility, momentum, reversal_signal, features.get('pnl_pct', 0)])

        # Simple "recurrent" computation
        hidden = np.tanh(input_vector * self.input_weights + self.hidden_state[symbol] * self.hidden_weights)
        self.hidden_state[symbol] = hidden

        output = np.sum(hidden * self.output_weights)

        # Exit signals: negative momentum, reversal from peak, high volatility
        exit_score = 0.0
        if momentum < -2:  # Negative momentum
            exit_score += 0.2
        if reversal_signal < -5:  # Reversal from peak
            exit_score += 0.3
        if volatility > 5:  # High volatility
            exit_score += 0.1
        if features.get('pnl_pct', 0) > 5:  # In profit
            exit_score += 0.15

        # Combine with neural output
        probability = (exit_score + (1 / (1 + np.exp(-output)))) / 2

        return min(1.0, max(0.0, probability))


class ExitEnsemble:
    """
    Ensemble of exit timing models with weighted voting.

    Combines:
    - RL-based Q-learning model
    - Gradient Boosting model
    - LSTM-like sequential model
    """

    def __init__(self):
        self.rl_model = RLExitModel()
        self.gbm_model = GradientBoostingExitModel()
        self.lstm_model = LSTMExitModel()

        # Model weights (can be tuned based on backtesting)
        self.weights = {
            'rl': 0.35,
            'gbm': 0.40,
            'lstm': 0.25
        }

        # Confidence thresholds
        self.strong_exit_threshold = 0.75
        self.weak_exit_threshold = 0.55
        self.strong_hold_threshold = 0.25

        # Performance tracking
        self.predictions_made = 0
        self.correct_predictions = 0

    def predict(self, features: Dict) -> ExitPrediction:
        """
        Make ensemble exit prediction.

        Args:
            features: Dict containing:
                - symbol: Trading pair
                - pnl_pct: Current P&L percentage
                - holding_hours: Hours in position
                - volatility: Current volatility
                - momentum: Price momentum
                - current_price: Current price
                - entry_price: Entry price
                - zone: Current zone (NEUTRAL, AVERAGING, etc.)
                - peak_distance_pct: Distance from peak UPNL

        Returns:
            ExitPrediction with signal and confidence
        """
        # Get individual model predictions
        rl_prob = self.rl_model.predict(features)
        gbm_prob = self.gbm_model.predict(features)
        lstm_prob = self.lstm_model.predict(features)

        model_votes = {
            'rl': rl_prob,
            'gbm': gbm_prob,
            'lstm': lstm_prob
        }

        # Weighted ensemble
        exit_probability = (
            self.weights['rl'] * rl_prob +
            self.weights['gbm'] * gbm_prob +
            self.weights['lstm'] * lstm_prob
        )

        # Determine signal and confidence
        if exit_probability >= self.strong_exit_threshold:
            signal = ExitSignal.STRONG_EXIT
            confidence = exit_probability
        elif exit_probability >= self.weak_exit_threshold:
            signal = ExitSignal.WEAK_EXIT
            confidence = exit_probability
        elif exit_probability <= self.strong_hold_threshold:
            signal = ExitSignal.STRONG_HOLD
            confidence = 1 - exit_probability
        else:
            signal = ExitSignal.HOLD
            confidence = 1 - exit_probability

        # Generate reasons
        reasons = self._generate_reasons(features, model_votes)

        self.predictions_made += 1

        return ExitPrediction(
            signal=signal,
            confidence=confidence,
            exit_probability=exit_probability,
            model_votes=model_votes,
            reasons=reasons
        )

    def _generate_reasons(self, features: Dict, votes: Dict[str, float]) -> List[str]:
        """Generate human-readable reasons for the prediction"""
        reasons = []

        pnl = features.get('pnl_pct', 0)
        holding = features.get('holding_hours', 0)
        vol = features.get('volatility', 30)

        if pnl > 5:
            reasons.append(f"In profit ({pnl:.1f}%)")
        elif pnl < -25:
            reasons.append(f"Deep drawdown ({pnl:.1f}%)")

        if holding > 24:
            reasons.append(f"Long holding time ({holding:.0f}h)")

        if vol > 50:
            reasons.append(f"High volatility ({vol:.0f}%)")

        # Model agreement
        exit_votes = sum(1 for v in votes.values() if v > 0.5)
        if exit_votes >= 2:
            reasons.append(f"{exit_votes}/3 models vote exit")
        elif exit_votes == 0:
            reasons.append("All models vote hold")

        return reasons

    def update(self, features: Dict, action: str, outcome: float):
        """
        Update models based on actual outcome.

        Args:
            features: State features at decision time
            action: 'exit' or 'hold'
            outcome: Actual P&L outcome (positive if good decision)
        """
        # Update RL model
        reward = outcome if action == 'exit' else -outcome
        next_features = features.copy()
        next_features['pnl_pct'] = features.get('pnl_pct', 0) + outcome
        self.rl_model.update(features, action, reward, next_features)

        # Track accuracy (simplified)
        if (action == 'exit' and outcome > 0) or (action == 'hold' and outcome < 0):
            self.correct_predictions += 1

    def get_accuracy(self) -> float:
        """Get model accuracy"""
        if self.predictions_made == 0:
            return 0.0
        return self.correct_predictions / self.predictions_made

    def adjust_weights(self, model_performances: Dict[str, float]):
        """Adjust model weights based on individual performance"""
        total_perf = sum(model_performances.values())
        if total_perf > 0:
            for model, perf in model_performances.items():
                self.weights[model] = perf / total_perf

        logger.info(f"Updated ensemble weights: {self.weights}")


# Singleton
_ensemble: Optional[ExitEnsemble] = None

def get_exit_ensemble() -> ExitEnsemble:
    """Get singleton exit ensemble"""
    global _ensemble
    if _ensemble is None:
        _ensemble = ExitEnsemble()
    return _ensemble


if __name__ == "__main__":
    # Demo
    print("=" * 60)
    print("ENSEMBLE EXIT MODEL DEMO")
    print("=" * 60)

    ensemble = ExitEnsemble()

    # Test scenarios
    scenarios = [
        {
            'name': 'Profitable position',
            'features': {
                'symbol': 'BTC/USDT:USDT',
                'pnl_pct': 8.5,
                'holding_hours': 12,
                'volatility': 35,
                'momentum': 0.02,
                'current_price': 43500,
                'entry_price': 40000,
                'zone': 'PROFIT_TAKING',
                'peak_distance_pct': 5
            }
        },
        {
            'name': 'Deep drawdown',
            'features': {
                'symbol': 'SOL/USDT:USDT',
                'pnl_pct': -28.0,
                'holding_hours': 48,
                'volatility': 55,
                'momentum': -0.03,
                'current_price': 85,
                'entry_price': 100,
                'zone': 'AVERAGING',
                'peak_distance_pct': 35
            }
        },
        {
            'name': 'Neutral position',
            'features': {
                'symbol': 'ETH/USDT:USDT',
                'pnl_pct': 1.2,
                'holding_hours': 6,
                'volatility': 30,
                'momentum': 0.005,
                'current_price': 2220,
                'entry_price': 2200,
                'zone': 'NEUTRAL',
                'peak_distance_pct': 2
            }
        },
    ]

    for scenario in scenarios:
        print(f"\n📊 {scenario['name']}")
        print("-" * 50)

        prediction = ensemble.predict(scenario['features'])

        print(f"Signal: {prediction.signal.value}")
        print(f"Confidence: {prediction.confidence:.1%}")
        print(f"Exit Probability: {prediction.exit_probability:.1%}")
        print(f"Model Votes:")
        for model, vote in prediction.model_votes.items():
            vote_emoji = "🔴 EXIT" if vote > 0.5 else "🟢 HOLD"
            print(f"  {model.upper()}: {vote:.1%} {vote_emoji}")
        print(f"Reasons: {', '.join(prediction.reasons)}")
