#!/usr/bin/env python3
"""
Grok Recommendation #2: Volatility Regime Detection using Hidden Markov Model
Replaces rolling average volatility with regime detection.

Detects market regimes: LOW_VOL, NORMAL_VOL, HIGH_VOL, CRISIS
"""
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import json
import os
import logging
from datetime import datetime
from collections import deque

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class VolatilityRegime(Enum):
    LOW_VOL = "low_vol"
    NORMAL_VOL = "normal_vol"
    HIGH_VOL = "high_vol"
    CRISIS = "crisis"


@dataclass
class RegimeState:
    """Current regime state with probabilities"""
    regime: VolatilityRegime
    probability: float
    regime_duration: int  # Candles in current regime
    transition_prob: Dict[str, float]  # Probabilities of transitioning to each regime


class VolatilityRegimeHMM:
    """
    Hidden Markov Model for volatility regime detection.

    States: LOW_VOL, NORMAL_VOL, HIGH_VOL, CRISIS
    Observations: Realized volatility levels

    Uses simplified Baum-Welch style updates without full EM.
    """

    # State indices
    STATES = [VolatilityRegime.LOW_VOL, VolatilityRegime.NORMAL_VOL,
              VolatilityRegime.HIGH_VOL, VolatilityRegime.CRISIS]
    N_STATES = 4

    # Initial transition matrix (rows: from, cols: to)
    # Regimes tend to persist (high diagonal values)
    INITIAL_TRANSITION = np.array([
        [0.90, 0.08, 0.02, 0.00],  # LOW_VOL
        [0.10, 0.80, 0.08, 0.02],  # NORMAL_VOL
        [0.02, 0.10, 0.80, 0.08],  # HIGH_VOL
        [0.00, 0.05, 0.15, 0.80],  # CRISIS
    ])

    # Volatility thresholds for emission probabilities (annualized %)
    VOL_THRESHOLDS = {
        VolatilityRegime.LOW_VOL: (0, 20),
        VolatilityRegime.NORMAL_VOL: (15, 40),
        VolatilityRegime.HIGH_VOL: (35, 80),
        VolatilityRegime.CRISIS: (70, 200),
    }

    def __init__(self, state_file: str = '/app/volatility_regime_state.json'):
        self.state_file = state_file

        # Transition matrix
        self.transition_matrix = self.INITIAL_TRANSITION.copy()

        # Current state probabilities (start with uniform)
        self.state_probs = np.array([0.1, 0.7, 0.15, 0.05])

        # Per-symbol regime tracking
        self.symbol_regimes: Dict[str, RegimeState] = {}

        # Historical volatility observations
        self.vol_history: deque = deque(maxlen=500)

        # Regime duration tracking
        self.regime_durations: Dict[str, int] = {}

        # Global market regime
        self.global_regime = VolatilityRegime.NORMAL_VOL

        self._load_state()

    def _load_state(self):
        """Load saved state"""
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    data = json.load(f)

                self.transition_matrix = np.array(data.get('transition_matrix', self.INITIAL_TRANSITION.tolist()))
                self.state_probs = np.array(data.get('state_probs', [0.1, 0.7, 0.15, 0.05]))
                self.global_regime = VolatilityRegime(data.get('global_regime', 'normal_vol'))

                logger.info(f"Loaded HMM state, global regime: {self.global_regime.value}")
        except Exception as e:
            logger.warning(f"Could not load HMM state: {e}")

    def _save_state(self):
        """Save state to file"""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'transition_matrix': self.transition_matrix.tolist(),
                'state_probs': self.state_probs.tolist(),
                'global_regime': self.global_regime.value,
                'symbol_regimes': {
                    s: {
                        'regime': r.regime.value,
                        'probability': r.probability,
                        'duration': r.regime_duration
                    }
                    for s, r in self.symbol_regimes.items()
                }
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save HMM state: {e}")

    def _calculate_emission_prob(self, volatility: float, regime: VolatilityRegime) -> float:
        """
        Calculate probability of observing volatility given regime.

        Uses Gaussian emission with regime-specific mean and std.
        """
        low, high = self.VOL_THRESHOLDS[regime]
        mean = (low + high) / 2
        std = (high - low) / 4  # Approximate std

        # Gaussian PDF (simplified)
        z = (volatility - mean) / std
        prob = np.exp(-0.5 * z ** 2)

        return max(prob, 1e-10)  # Minimum probability for numerical stability

    def _get_emission_vector(self, volatility: float) -> np.ndarray:
        """Get emission probabilities for all states"""
        emissions = np.array([
            self._calculate_emission_prob(volatility, regime)
            for regime in self.STATES
        ])
        return emissions / emissions.sum()  # Normalize

    def update(self, volatility: float, symbol: Optional[str] = None) -> RegimeState:
        """
        Update regime detection with new volatility observation.

        Uses forward algorithm for filtering.

        Args:
            volatility: Current realized volatility (annualized %)
            symbol: Optional symbol for per-symbol tracking

        Returns:
            Current regime state
        """
        self.vol_history.append(volatility)

        # Forward step: P(state_t | obs_1:t)
        emissions = self._get_emission_vector(volatility)

        # Predict: sum over previous states
        predicted = self.transition_matrix.T @ self.state_probs

        # Update with observation
        updated = predicted * emissions
        updated = updated / updated.sum()  # Normalize

        self.state_probs = updated

        # Determine most likely regime
        regime_idx = np.argmax(updated)
        regime = self.STATES[regime_idx]
        probability = updated[regime_idx]

        # Update global regime if probability is high enough
        if probability > 0.5:
            if regime != self.global_regime:
                logger.info(f"Global regime change: {self.global_regime.value} -> {regime.value} (p={probability:.2f})")
            self.global_regime = regime

        # Update duration tracking
        duration_key = symbol or 'global'
        if duration_key not in self.regime_durations:
            self.regime_durations[duration_key] = 0

        if symbol:
            prev_regime = self.symbol_regimes.get(symbol)
            if prev_regime and prev_regime.regime == regime:
                self.regime_durations[duration_key] += 1
            else:
                self.regime_durations[duration_key] = 1

        # Create regime state
        regime_state = RegimeState(
            regime=regime,
            probability=probability,
            regime_duration=self.regime_durations[duration_key],
            transition_prob={
                s.value: self.transition_matrix[regime_idx, i]
                for i, s in enumerate(self.STATES)
            }
        )

        if symbol:
            self.symbol_regimes[symbol] = regime_state

        # Save state periodically
        if len(self.vol_history) % 10 == 0:
            self._save_state()

        return regime_state

    def get_regime(self, symbol: Optional[str] = None) -> RegimeState:
        """Get current regime state"""
        if symbol and symbol in self.symbol_regimes:
            return self.symbol_regimes[symbol]

        # Return global regime state
        regime_idx = np.argmax(self.state_probs)
        return RegimeState(
            regime=self.STATES[regime_idx],
            probability=self.state_probs[regime_idx],
            regime_duration=self.regime_durations.get('global', 0),
            transition_prob={
                s.value: self.transition_matrix[regime_idx, i]
                for i, s in enumerate(self.STATES)
            }
        )

    def get_regime_factor(self, symbol: Optional[str] = None) -> Dict[str, float]:
        """
        Get regime-based adjustment factors for trading parameters.

        Returns factors for:
        - position_size: Multiplier for position sizing
        - averaging_threshold: Multiplier for averaging trigger
        - profit_taking: Multiplier for profit taking threshold
        - stop_loss: Multiplier for stop loss
        """
        regime_state = self.get_regime(symbol)
        regime = regime_state.regime

        # Base factors by regime
        factors = {
            VolatilityRegime.LOW_VOL: {
                'position_size': 1.2,      # Larger positions in calm markets
                'averaging_threshold': 0.8, # Tighter averaging (smaller drawdown needed)
                'profit_taking': 0.8,       # Take profits earlier
                'stop_loss': 0.9,           # Tighter stops
                'max_leverage': 15,         # Can use more leverage
            },
            VolatilityRegime.NORMAL_VOL: {
                'position_size': 1.0,
                'averaging_threshold': 1.0,
                'profit_taking': 1.0,
                'stop_loss': 1.0,
                'max_leverage': 10,
            },
            VolatilityRegime.HIGH_VOL: {
                'position_size': 0.7,       # Smaller positions
                'averaging_threshold': 1.3,  # Wider averaging thresholds
                'profit_taking': 1.2,        # Let profits run more
                'stop_loss': 1.3,            # Wider stops
                'max_leverage': 7,
            },
            VolatilityRegime.CRISIS: {
                'position_size': 0.3,       # Very small positions
                'averaging_threshold': 2.0,  # Very wide averaging
                'profit_taking': 1.5,        # Take quick profits
                'stop_loss': 2.0,            # Wide emergency stops
                'max_leverage': 3,           # Minimal leverage
            },
        }

        return factors[regime]

    def calculate_volatility(self, returns: List[float], annualize: bool = True) -> float:
        """
        Calculate realized volatility from returns.

        Args:
            returns: List of period returns
            annualize: Whether to annualize (assumes 365 trading days for crypto)

        Returns:
            Volatility as percentage
        """
        if len(returns) < 2:
            return 30.0  # Default to normal volatility

        vol = np.std(returns) * 100  # Convert to percentage

        if annualize:
            # Annualize based on period (assuming returns are from 5m candles)
            periods_per_year = 365 * 24 * 12  # 5-minute candles per year
            vol = vol * np.sqrt(periods_per_year)

        return vol

    def get_expected_regime_duration(self) -> Dict[str, float]:
        """Get expected duration (in periods) for each regime"""
        # Expected duration = 1 / (1 - self_transition_prob)
        durations = {}
        for i, regime in enumerate(self.STATES):
            self_prob = self.transition_matrix[i, i]
            expected = 1 / (1 - self_prob) if self_prob < 1 else float('inf')
            durations[regime.value] = expected

        return durations

    def get_regime_transition_forecast(self, horizon: int = 10) -> Dict[str, np.ndarray]:
        """
        Forecast regime probabilities over horizon periods.

        Returns probability distribution at each future time step.
        """
        forecasts = {'steps': list(range(1, horizon + 1))}

        probs = self.state_probs.copy()
        for step in range(1, horizon + 1):
            probs = self.transition_matrix.T @ probs
            for i, regime in enumerate(self.STATES):
                if regime.value not in forecasts:
                    forecasts[regime.value] = []
                forecasts[regime.value].append(probs[i])

        return forecasts

    def print_status(self):
        """Print current regime status"""
        regime_state = self.get_regime()

        print("\n" + "=" * 60)
        print("📊 VOLATILITY REGIME STATUS (HMM)")
        print("=" * 60)
        print(f"\nCurrent Regime: {regime_state.regime.value.upper()}")
        print(f"Confidence: {regime_state.probability:.1%}")
        print(f"Duration: {regime_state.regime_duration} periods")

        print("\nState Probabilities:")
        for i, regime in enumerate(self.STATES):
            bar = "█" * int(self.state_probs[i] * 30)
            print(f"  {regime.value:<12} {self.state_probs[i]:>6.1%} {bar}")

        print("\nTransition Probabilities (from current):")
        for regime, prob in regime_state.transition_prob.items():
            print(f"  → {regime:<12} {prob:.1%}")

        factors = self.get_regime_factor()
        print("\nTrading Adjustments:")
        print(f"  Position Size:  {factors['position_size']:.1f}x")
        print(f"  Averaging:      {factors['averaging_threshold']:.1f}x threshold")
        print(f"  Max Leverage:   {factors['max_leverage']}x")

        print("=" * 60)


# Singleton instance
_hmm_instance = None

def get_volatility_hmm() -> VolatilityRegimeHMM:
    """Get singleton HMM instance"""
    global _hmm_instance
    if _hmm_instance is None:
        _hmm_instance = VolatilityRegimeHMM()
    return _hmm_instance


if __name__ == "__main__":
    # Demo
    hmm = VolatilityRegimeHMM('/tmp/test_hmm.json')

    # Simulate volatility sequence (transitioning from normal to high vol)
    np.random.seed(42)

    vol_sequence = (
        list(np.random.normal(25, 5, 20)) +  # Normal vol
        list(np.random.normal(50, 10, 15)) +  # High vol
        list(np.random.normal(90, 15, 10)) +  # Crisis
        list(np.random.normal(40, 8, 10)) +   # Back to high
        list(np.random.normal(20, 3, 15))     # Low vol
    )

    print("Simulating volatility regime transitions...")
    print("-" * 60)

    for i, vol in enumerate(vol_sequence):
        state = hmm.update(vol)
        if i % 10 == 0 or i == len(vol_sequence) - 1:
            print(f"Period {i:>3}: Vol={vol:>5.1f}% | Regime={state.regime.value:<10} | P={state.probability:.2f}")

    hmm.print_status()

    # Forecast
    forecast = hmm.get_regime_transition_forecast(5)
    print("\n5-Step Regime Forecast:")
    for regime in hmm.STATES:
        probs = forecast[regime.value]
        print(f"  {regime.value}: {[f'{p:.1%}' for p in probs]}")
