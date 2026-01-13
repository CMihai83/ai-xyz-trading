#!/usr/bin/env python3
"""
Grok Recommendation #1: Bayesian Correction Probability Model
Per-symbol coefficient fitting with Bayesian updating.

Replaces the generic logistic regression with symbol-specific models
that learn from actual correction outcomes.
"""
import json
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
from scipy.optimize import minimize
from scipy.special import expit  # Logistic function
import os
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class CorrectionEvent:
    """Record of a drawdown and whether it corrected"""
    symbol: str
    drawdown_pct: float  # Negative percentage (e.g., -25%)
    did_correct: bool    # Did price recover?
    correction_time_hours: float  # Time to correction (0 if didn't correct)
    timestamp: str


@dataclass
class BayesianPrior:
    """Prior distribution parameters for logistic regression coefficients"""
    beta0_mean: float = -1.0    # Intercept prior mean
    beta0_std: float = 0.5      # Intercept prior std
    beta1_mean: float = 20.0    # Slope prior mean
    beta1_std: float = 5.0      # Slope prior std
    beta2_mean: float = 0.0     # Quadratic prior mean
    beta2_std: float = 2.0      # Quadratic prior std


class BayesianCorrectionModel:
    """
    Bayesian logistic regression for correction probability.

    P(correction | depth) = sigmoid(β₀ + β₁×d + β₂×d²)

    where:
    - d = drawdown depth (positive value, e.g., 0.25 for -25%)
    - β₀, β₁, β₂ are learned coefficients

    Uses Maximum A Posteriori (MAP) estimation with Gaussian priors.
    """

    def __init__(self, state_file: str = '/app/bayesian_correction_state.json'):
        self.state_file = state_file
        self.prior = BayesianPrior()

        # Global coefficients (used as prior for new symbols)
        self.global_coeffs = np.array([
            self.prior.beta0_mean,
            self.prior.beta1_mean,
            self.prior.beta2_mean
        ])

        # Per-symbol posterior coefficients
        self.symbol_coeffs: Dict[str, np.ndarray] = {}

        # Per-symbol correction history
        self.symbol_history: Dict[str, List[CorrectionEvent]] = {}

        # Confidence scores (based on sample size)
        self.symbol_confidence: Dict[str, float] = {}

        self._load_state()

    def _load_state(self):
        """Load saved state from file"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                self.global_coeffs = np.array(data.get('global_coeffs', self.global_coeffs.tolist()))

                for symbol, coeffs in data.get('symbol_coeffs', {}).items():
                    self.symbol_coeffs[symbol] = np.array(coeffs)

                for symbol, history in data.get('symbol_history', {}).items():
                    self.symbol_history[symbol] = [CorrectionEvent(**h) for h in history]

                self.symbol_confidence = data.get('symbol_confidence', {})

                logger.info(f"Loaded Bayesian model state for {len(self.symbol_coeffs)} symbols")
        except Exception as e:
            logger.warning(f"Could not load Bayesian state: {e}")

    def _save_state(self):
        """Save state to file"""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'global_coeffs': self.global_coeffs.tolist(),
                'symbol_coeffs': {s: c.tolist() for s, c in self.symbol_coeffs.items()},
                'symbol_history': {
                    s: [asdict(e) for e in events[-100:]]  # Keep last 100 per symbol
                    for s, events in self.symbol_history.items()
                },
                'symbol_confidence': self.symbol_confidence
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save Bayesian state: {e}")

    def _logistic_probability(self, depth: float, coeffs: np.ndarray) -> float:
        """
        Calculate correction probability using logistic function.

        Args:
            depth: Positive drawdown value (e.g., 0.25 for -25%)
            coeffs: [β₀, β₁, β₂] coefficients

        Returns:
            Probability of correction (0 to 1)
        """
        linear = coeffs[0] + coeffs[1] * depth + coeffs[2] * (depth ** 2)
        return float(expit(linear))

    def _negative_log_posterior(self, coeffs: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
        """
        Negative log posterior for MAP estimation.

        Combines likelihood (logistic regression) with Gaussian priors.
        """
        # Log likelihood
        probs = expit(X @ coeffs)
        probs = np.clip(probs, 1e-10, 1 - 1e-10)  # Numerical stability

        log_likelihood = np.sum(y * np.log(probs) + (1 - y) * np.log(1 - probs))

        # Log prior (Gaussian)
        log_prior = (
            -0.5 * ((coeffs[0] - self.prior.beta0_mean) / self.prior.beta0_std) ** 2
            - 0.5 * ((coeffs[1] - self.prior.beta1_mean) / self.prior.beta1_std) ** 2
            - 0.5 * ((coeffs[2] - self.prior.beta2_mean) / self.prior.beta2_std) ** 2
        )

        return -(log_likelihood + log_prior)

    def update_symbol(self, symbol: str):
        """
        Update coefficients for a symbol using its correction history.

        Uses MAP estimation with the current prior.
        """
        if symbol not in self.symbol_history or len(self.symbol_history[symbol]) < 5:
            # Not enough data, use global coefficients
            self.symbol_coeffs[symbol] = self.global_coeffs.copy()
            self.symbol_confidence[symbol] = 0.0
            return

        history = self.symbol_history[symbol]

        # Prepare data
        depths = np.array([abs(e.drawdown_pct) / 100 for e in history])  # Convert to positive decimals
        corrections = np.array([1.0 if e.did_correct else 0.0 for e in history])

        # Design matrix [1, depth, depth²]
        X = np.column_stack([np.ones(len(depths)), depths, depths ** 2])

        # MAP estimation
        try:
            result = minimize(
                self._negative_log_posterior,
                x0=self.global_coeffs,
                args=(X, corrections),
                method='L-BFGS-B',
                bounds=[(-5, 5), (0, 50), (-10, 10)]  # Constrain to reasonable ranges
            )

            if result.success:
                self.symbol_coeffs[symbol] = result.x

                # Confidence based on sample size (saturates at 1.0 around 50 samples)
                n = len(history)
                self.symbol_confidence[symbol] = min(1.0, n / 50)

                logger.info(f"Updated Bayesian coeffs for {symbol}: {result.x}, confidence={self.symbol_confidence[symbol]:.2f}")
            else:
                logger.warning(f"MAP optimization failed for {symbol}, using global")
                self.symbol_coeffs[symbol] = self.global_coeffs.copy()
                self.symbol_confidence[symbol] = 0.0

        except Exception as e:
            logger.error(f"Error updating {symbol}: {e}")
            self.symbol_coeffs[symbol] = self.global_coeffs.copy()

        self._save_state()

    def record_correction_event(
        self,
        symbol: str,
        drawdown_pct: float,
        did_correct: bool,
        correction_time_hours: float = 0.0
    ):
        """
        Record a correction event for learning.

        Args:
            symbol: Trading pair
            drawdown_pct: Drawdown percentage (negative, e.g., -25.0)
            did_correct: Whether price recovered
            correction_time_hours: Time to recovery (0 if didn't correct)
        """
        event = CorrectionEvent(
            symbol=symbol,
            drawdown_pct=drawdown_pct,
            did_correct=did_correct,
            correction_time_hours=correction_time_hours,
            timestamp=datetime.now().isoformat()
        )

        if symbol not in self.symbol_history:
            self.symbol_history[symbol] = []

        self.symbol_history[symbol].append(event)

        # Update model if we have enough new data
        if len(self.symbol_history[symbol]) % 5 == 0:
            self.update_symbol(symbol)

        # Also update global model periodically
        total_events = sum(len(h) for h in self.symbol_history.values())
        if total_events % 50 == 0:
            self._update_global_model()

        self._save_state()

    def _update_global_model(self):
        """Update global coefficients from all symbol data"""
        all_events = []
        for events in self.symbol_history.values():
            all_events.extend(events)

        if len(all_events) < 20:
            return

        depths = np.array([abs(e.drawdown_pct) / 100 for e in all_events])
        corrections = np.array([1.0 if e.did_correct else 0.0 for e in all_events])

        X = np.column_stack([np.ones(len(depths)), depths, depths ** 2])

        try:
            # Simple MLE for global (no prior, or very weak prior)
            from sklearn.linear_model import LogisticRegression
            model = LogisticRegression(penalty=None, max_iter=1000)

            # Reshape for sklearn
            X_sklearn = depths.reshape(-1, 1)
            X_poly = np.column_stack([X_sklearn, X_sklearn ** 2])

            model.fit(X_poly, corrections)

            self.global_coeffs = np.array([
                model.intercept_[0],
                model.coef_[0][0],
                model.coef_[0][1]
            ])

            logger.info(f"Updated global coefficients: {self.global_coeffs}")

        except Exception as e:
            logger.warning(f"Could not update global model: {e}")

    def get_correction_probability(self, symbol: str, drawdown_pct: float) -> Tuple[float, float]:
        """
        Get correction probability for a symbol at a given drawdown.

        Args:
            symbol: Trading pair
            drawdown_pct: Current drawdown (negative, e.g., -25.0)

        Returns:
            Tuple of (probability, confidence)
        """
        depth = abs(drawdown_pct) / 100  # Convert to positive decimal

        # Use symbol-specific coefficients if available with good confidence
        if symbol in self.symbol_coeffs and self.symbol_confidence.get(symbol, 0) > 0.3:
            coeffs = self.symbol_coeffs[symbol]
            confidence = self.symbol_confidence[symbol]

            # Blend with global based on confidence
            global_prob = self._logistic_probability(depth, self.global_coeffs)
            symbol_prob = self._logistic_probability(depth, coeffs)

            # Weighted average
            prob = confidence * symbol_prob + (1 - confidence) * global_prob

            return prob, confidence
        else:
            # Use global coefficients
            prob = self._logistic_probability(depth, self.global_coeffs)
            return prob, 0.0

    def get_recommended_averaging_depth(self, symbol: str, target_prob: float = 0.75) -> float:
        """
        Get recommended drawdown depth for averaging with target correction probability.

        Args:
            symbol: Trading pair
            target_prob: Desired correction probability (default 75%)

        Returns:
            Recommended drawdown percentage (negative)
        """
        coeffs = self.symbol_coeffs.get(symbol, self.global_coeffs)

        # Binary search for depth that gives target probability
        low, high = 0.05, 0.50  # 5% to 50% drawdown range

        for _ in range(20):  # 20 iterations for precision
            mid = (low + high) / 2
            prob = self._logistic_probability(mid, coeffs)

            if prob < target_prob:
                high = mid
            else:
                low = mid

        return -mid * 100  # Return as negative percentage

    def get_symbol_stats(self, symbol: str) -> Dict:
        """Get statistics for a symbol's correction history"""
        if symbol not in self.symbol_history:
            return {'events': 0}

        history = self.symbol_history[symbol]
        corrections = [e for e in history if e.did_correct]

        return {
            'events': len(history),
            'corrections': len(corrections),
            'correction_rate': len(corrections) / len(history) if history else 0,
            'avg_correction_time_hours': (
                np.mean([e.correction_time_hours for e in corrections])
                if corrections else 0
            ),
            'coefficients': self.symbol_coeffs.get(symbol, self.global_coeffs).tolist(),
            'confidence': self.symbol_confidence.get(symbol, 0)
        }


# Singleton instance
_model_instance = None

def get_bayesian_model() -> BayesianCorrectionModel:
    """Get singleton Bayesian correction model"""
    global _model_instance
    if _model_instance is None:
        _model_instance = BayesianCorrectionModel()
    return _model_instance


if __name__ == "__main__":
    # Demo
    model = BayesianCorrectionModel('/tmp/test_bayesian.json')

    # Simulate some correction events
    for i in range(20):
        drawdown = -15 - i * 2  # -15% to -55%
        # Deeper drawdowns more likely to correct (simulated)
        did_correct = abs(drawdown) > 25 or np.random.random() > 0.5

        model.record_correction_event(
            symbol="BTC/USDT:USDT",
            drawdown_pct=drawdown,
            did_correct=did_correct,
            correction_time_hours=np.random.uniform(1, 24) if did_correct else 0
        )

    # Test predictions
    print("\nCorrection Probabilities for BTC/USDT:USDT:")
    print("-" * 50)
    for depth in [-10, -20, -30, -40, -50]:
        prob, conf = model.get_correction_probability("BTC/USDT:USDT", depth)
        print(f"  Drawdown {depth}%: P(correction) = {prob:.1%} (confidence: {conf:.1%})")

    recommended = model.get_recommended_averaging_depth("BTC/USDT:USDT", 0.80)
    print(f"\nRecommended averaging depth for 80% correction probability: {recommended:.1f}%")

    print(f"\nSymbol stats: {model.get_symbol_stats('BTC/USDT:USDT')}")
