#!/usr/bin/env python3
"""
Grok Recommendation #11: Online Learning for CSSI
Continuous model updating with new data using SGD.
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from collections import deque
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CSSIObservation:
    """Single CSSI observation for learning"""
    symbol: str
    drawdown_pct: float        # Drawdown depth
    volatility: float          # Market volatility
    btc_correlation: float     # Correlation with BTC
    support_proximity: float   # Distance to support (0-1)
    market_regime: str         # LOW_VOL, NORMAL_VOL, HIGH_VOL
    did_correct: bool          # Outcome: did price recover?
    correction_time_hours: float
    timestamp: str


class OnlineCSSILearner:
    """
    Online learning system for CSSI (Correction-Support Strength Index).

    Uses Stochastic Gradient Descent for continuous model updates.
    Features:
    - Incremental learning from each trade outcome
    - Adaptive learning rate
    - Feature normalization
    - Regularization to prevent overfitting
    """

    def __init__(
        self,
        learning_rate: float = 0.01,
        regularization: float = 0.001,
        state_file: str = '/app/online_cssi_state.json'
    ):
        self.initial_lr = learning_rate
        self.lr = learning_rate
        self.reg = regularization
        self.state_file = state_file

        # Model weights
        # Features: [drawdown, volatility, btc_corr, support_prox, vol_regime, bias]
        self.weights = np.array([
            0.5,    # drawdown (deeper = higher correction prob)
            -0.2,   # volatility (higher = lower correction prob)
            -0.1,   # btc_correlation (higher corr = harder to correct)
            0.3,    # support_proximity (closer to support = higher prob)
            -0.1,   # high_vol_regime (high vol = lower correction prob)
            0.0     # bias term
        ])

        # Feature normalization stats (running mean/std)
        self.feature_means = np.array([25.0, 40.0, 0.7, 0.5, 0.0, 1.0])
        self.feature_stds = np.array([15.0, 20.0, 0.2, 0.3, 1.0, 1.0])

        # Learning history
        self.observations: deque = deque(maxlen=1000)
        self.update_count = 0
        self.loss_history: deque = deque(maxlen=100)

        # Performance tracking
        self.correct_predictions = 0
        self.total_predictions = 0

        self._load_state()

    def _load_state(self):
        """Load saved model state"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.weights = np.array(data.get('weights', self.weights.tolist()))
                    self.feature_means = np.array(data.get('feature_means', self.feature_means.tolist()))
                    self.feature_stds = np.array(data.get('feature_stds', self.feature_stds.tolist()))
                    self.update_count = data.get('update_count', 0)
                    self.correct_predictions = data.get('correct_predictions', 0)
                    self.total_predictions = data.get('total_predictions', 0)

                logger.info(f"Loaded online CSSI model (updates: {self.update_count})")
        except Exception as e:
            logger.warning(f"Could not load CSSI state: {e}")

    def _save_state(self):
        """Save model state"""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'weights': self.weights.tolist(),
                'feature_means': self.feature_means.tolist(),
                'feature_stds': self.feature_stds.tolist(),
                'update_count': self.update_count,
                'correct_predictions': self.correct_predictions,
                'total_predictions': self.total_predictions,
                'accuracy': self.get_accuracy(),
                'recent_loss': float(np.mean(list(self.loss_history))) if self.loss_history else 0
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save CSSI state: {e}")

    def _extract_features(self, obs: Dict) -> np.ndarray:
        """Extract feature vector from observation"""
        features = np.array([
            abs(obs.get('drawdown_pct', 25)),
            obs.get('volatility', 40),
            obs.get('btc_correlation', 0.7),
            obs.get('support_proximity', 0.5),
            1.0 if obs.get('market_regime', 'NORMAL_VOL') == 'HIGH_VOL' else 0.0,
            1.0  # Bias term
        ])

        return features

    def _normalize_features(self, features: np.ndarray) -> np.ndarray:
        """Normalize features using running statistics"""
        return (features - self.feature_means) / (self.feature_stds + 1e-8)

    def _update_normalization(self, features: np.ndarray, alpha: float = 0.01):
        """Update running normalization statistics"""
        self.feature_means = (1 - alpha) * self.feature_means + alpha * features
        variance = (features - self.feature_means) ** 2
        self.feature_stds = np.sqrt(
            (1 - alpha) * (self.feature_stds ** 2) + alpha * variance
        )

    def _sigmoid(self, x: float) -> float:
        """Sigmoid activation"""
        return 1 / (1 + np.exp(-np.clip(x, -500, 500)))

    def _log_loss(self, y_true: int, y_pred: float) -> float:
        """Binary cross-entropy loss"""
        y_pred = np.clip(y_pred, 1e-7, 1 - 1e-7)
        return -(y_true * np.log(y_pred) + (1 - y_true) * np.log(1 - y_pred))

    def predict(self, observation: Dict) -> Tuple[float, float]:
        """
        Predict correction probability.

        Args:
            observation: Dict with features

        Returns:
            Tuple of (probability, confidence)
        """
        features = self._extract_features(observation)
        normalized = self._normalize_features(features)

        # Linear combination + sigmoid
        logit = np.dot(normalized, self.weights)
        probability = self._sigmoid(logit)

        # Confidence based on distance from decision boundary
        confidence = min(1.0, abs(logit) / 3)

        self.total_predictions += 1

        return probability, confidence

    def update(
        self,
        observation: Dict,
        did_correct: bool,
        correction_time_hours: float = 0
    ):
        """
        Update model with new observation.

        Args:
            observation: Feature dict
            did_correct: Whether price corrected (recovered)
            correction_time_hours: Time to correction
        """
        features = self._extract_features(observation)

        # Update normalization stats
        self._update_normalization(features)

        normalized = self._normalize_features(features)

        # Forward pass
        logit = np.dot(normalized, self.weights)
        prediction = self._sigmoid(logit)

        # Target
        target = 1.0 if did_correct else 0.0

        # Calculate loss
        loss = self._log_loss(target, prediction)
        self.loss_history.append(loss)

        # Track accuracy
        predicted_correct = prediction > 0.5
        if predicted_correct == did_correct:
            self.correct_predictions += 1

        # Gradient descent update
        # Gradient of log loss: (prediction - target) * features
        gradient = (prediction - target) * normalized

        # Add L2 regularization gradient
        gradient += self.reg * self.weights

        # Adaptive learning rate (decrease over time)
        adaptive_lr = self.initial_lr / (1 + 0.0001 * self.update_count)

        # Update weights
        self.weights -= adaptive_lr * gradient

        self.update_count += 1

        # Save periodically
        if self.update_count % 10 == 0:
            self._save_state()

        logger.debug(f"CSSI update #{self.update_count}: loss={loss:.4f}, pred={prediction:.2f}, actual={target}")

    def get_accuracy(self) -> float:
        """Get prediction accuracy"""
        if self.total_predictions == 0:
            return 0.0
        return self.correct_predictions / self.total_predictions

    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance based on weights"""
        feature_names = [
            'drawdown_depth', 'volatility', 'btc_correlation',
            'support_proximity', 'high_vol_regime', 'bias'
        ]

        # Normalize weights to sum to 1
        abs_weights = np.abs(self.weights)
        normalized = abs_weights / (abs_weights.sum() + 1e-8)

        importance = {}
        for name, weight, norm_weight in zip(feature_names, self.weights, normalized):
            importance[name] = {
                'raw_weight': float(weight),
                'importance': float(norm_weight),
                'direction': 'positive' if weight > 0 else 'negative'
            }

        return importance

    def get_recommended_cssi_threshold(self, risk_tolerance: str = 'moderate') -> float:
        """
        Get recommended CSSI threshold based on model performance.

        Args:
            risk_tolerance: 'conservative', 'moderate', 'aggressive'

        Returns:
            Recommended CSSI threshold for averaging decisions
        """
        base_thresholds = {
            'conservative': 0.70,
            'moderate': 0.60,
            'aggressive': 0.50
        }

        base = base_thresholds.get(risk_tolerance, 0.60)

        # Adjust based on model accuracy
        accuracy = self.get_accuracy()

        if accuracy > 0.7:
            # Model is accurate, can be more aggressive
            adjustment = -0.05
        elif accuracy < 0.5:
            # Model is not accurate, be more conservative
            adjustment = 0.10
        else:
            adjustment = 0.0

        return min(0.85, max(0.45, base + adjustment))

    def print_status(self):
        """Print model status"""
        print("\n" + "=" * 60)
        print("📊 ONLINE CSSI LEARNER STATUS")
        print("=" * 60)
        print(f"Total Updates: {self.update_count}")
        print(f"Accuracy: {self.get_accuracy():.1%}")
        print(f"Recent Loss: {np.mean(list(self.loss_history)):.4f}" if self.loss_history else "N/A")

        print("\nFeature Importance:")
        importance = self.get_feature_importance()
        for name, info in sorted(importance.items(), key=lambda x: x[1]['importance'], reverse=True):
            bar = "█" * int(info['importance'] * 30)
            direction = "↑" if info['direction'] == 'positive' else "↓"
            print(f"  {name:<20} {info['importance']:>5.1%} {bar} {direction}")

        print(f"\nRecommended CSSI Thresholds:")
        for risk in ['conservative', 'moderate', 'aggressive']:
            threshold = self.get_recommended_cssi_threshold(risk)
            print(f"  {risk.capitalize():<15} {threshold:.2f}")

        print("=" * 60)


# Singleton
_online_learner: Optional[OnlineCSSILearner] = None

def get_online_cssi_learner() -> OnlineCSSILearner:
    """Get singleton online CSSI learner"""
    global _online_learner
    if _online_learner is None:
        _online_learner = OnlineCSSILearner()
    return _online_learner


if __name__ == "__main__":
    # Demo
    print("=" * 60)
    print("ONLINE CSSI LEARNING DEMO")
    print("=" * 60)

    learner = OnlineCSSILearner('/tmp/test_cssi.json')

    # Simulate training data
    np.random.seed(42)

    print("\nSimulating 50 observations...")

    for i in range(50):
        # Generate random observation
        drawdown = np.random.uniform(10, 50)
        volatility = np.random.uniform(20, 80)
        btc_corr = np.random.uniform(0.3, 0.95)
        support_prox = np.random.uniform(0, 1)
        regime = np.random.choice(['LOW_VOL', 'NORMAL_VOL', 'HIGH_VOL'])

        obs = {
            'drawdown_pct': -drawdown,
            'volatility': volatility,
            'btc_correlation': btc_corr,
            'support_proximity': support_prox,
            'market_regime': regime
        }

        # Simulate outcome (deeper drawdown + closer to support = more likely to correct)
        correction_prob = 0.3 + 0.4 * (drawdown / 50) + 0.3 * support_prox - 0.2 * (volatility / 80)
        did_correct = np.random.random() < correction_prob

        # Update model
        learner.update(obs, did_correct)

        if (i + 1) % 10 == 0:
            prob, conf = learner.predict(obs)
            print(f"After {i+1} updates: accuracy={learner.get_accuracy():.1%}")

    # Test predictions
    print("\n" + "-" * 50)
    print("Testing predictions:")

    test_cases = [
        {'drawdown_pct': -15, 'volatility': 30, 'btc_correlation': 0.8, 'support_proximity': 0.2, 'market_regime': 'NORMAL_VOL'},
        {'drawdown_pct': -35, 'volatility': 40, 'btc_correlation': 0.6, 'support_proximity': 0.8, 'market_regime': 'NORMAL_VOL'},
        {'drawdown_pct': -50, 'volatility': 70, 'btc_correlation': 0.9, 'support_proximity': 0.9, 'market_regime': 'HIGH_VOL'},
    ]

    for obs in test_cases:
        prob, conf = learner.predict(obs)
        print(f"\nDrawdown: {obs['drawdown_pct']}%, Support: {obs['support_proximity']:.1f}")
        print(f"  Correction Prob: {prob:.1%}, Confidence: {conf:.1%}")

    learner.print_status()
