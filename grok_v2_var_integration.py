#!/usr/bin/env python3
"""
Grok Recommendation #8: Value-at-Risk (VaR) Integration
Adds VaR-based position limits to the risk management framework.
"""
import numpy as np
from scipy import stats
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class VaRResult:
    """VaR calculation result"""
    var_95: float          # 95% VaR (in USD)
    var_99: float          # 99% VaR (in USD)
    cvar_95: float         # Conditional VaR (Expected Shortfall) at 95%
    method: str            # 'historical', 'parametric', or 'monte_carlo'
    horizon_days: int      # Time horizon
    confidence: float      # Confidence level used
    position_value: float  # Portfolio value used


class VaRCalculator:
    """
    Value-at-Risk calculator with multiple methodologies.

    Methods:
    1. Historical VaR - Based on actual return distribution
    2. Parametric VaR - Assuming normal distribution
    3. Monte Carlo VaR - Simulation-based
    """

    def __init__(
        self,
        returns_file: str = '/app/portfolio_returns.json',
        lookback_days: int = 252  # 1 year of trading days
    ):
        self.returns_file = returns_file
        self.lookback_days = lookback_days
        self.returns_history: Dict[str, List[float]] = {}
        self.portfolio_returns: List[float] = []

        self._load_returns()

    def _load_returns(self):
        """Load historical returns data"""
        try:
            if os.path.exists(self.returns_file):
                with open(self.returns_file, 'r') as f:
                    data = json.load(f)
                    self.returns_history = data.get('symbol_returns', {})
                    self.portfolio_returns = data.get('portfolio_returns', [])
        except Exception as e:
            logger.warning(f"Could not load returns data: {e}")

    def _save_returns(self):
        """Save returns data"""
        try:
            data = {
                'last_updated': datetime.now().isoformat(),
                'symbol_returns': {
                    s: returns[-self.lookback_days:]
                    for s, returns in self.returns_history.items()
                },
                'portfolio_returns': self.portfolio_returns[-self.lookback_days:]
            }
            with open(self.returns_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save returns: {e}")

    def add_return(self, symbol: str, return_pct: float, is_portfolio: bool = False):
        """Add a return observation"""
        if symbol not in self.returns_history:
            self.returns_history[symbol] = []

        self.returns_history[symbol].append(return_pct)

        if is_portfolio:
            self.portfolio_returns.append(return_pct)

        # Periodic save
        if len(self.portfolio_returns) % 10 == 0:
            self._save_returns()

    def historical_var(
        self,
        returns: List[float],
        position_value: float,
        confidence: float = 0.95,
        horizon_days: int = 1
    ) -> float:
        """
        Calculate Historical VaR.

        Uses empirical quantile of return distribution.

        Args:
            returns: Historical returns (as decimals, e.g., 0.02 for 2%)
            position_value: Current position value in USD
            confidence: Confidence level (e.g., 0.95 for 95%)
            horizon_days: Time horizon in days

        Returns:
            VaR in USD (negative number representing potential loss)
        """
        if len(returns) < 10:
            logger.warning("Insufficient data for historical VaR")
            return -position_value * 0.20  # Default 20% loss estimate

        returns_array = np.array(returns)

        # Scale for horizon (assuming i.i.d. returns)
        if horizon_days > 1:
            returns_array = returns_array * np.sqrt(horizon_days)

        var_percentile = (1 - confidence) * 100
        var = np.percentile(returns_array, var_percentile) * position_value

        return var

    def parametric_var(
        self,
        returns: List[float],
        position_value: float,
        confidence: float = 0.95,
        horizon_days: int = 1
    ) -> float:
        """
        Calculate Parametric VaR (Variance-Covariance method).

        Assumes returns follow normal distribution.

        Args:
            returns: Historical returns
            position_value: Current position value
            confidence: Confidence level
            horizon_days: Time horizon

        Returns:
            VaR in USD
        """
        if len(returns) < 10:
            logger.warning("Insufficient data for parametric VaR")
            return -position_value * 0.20

        returns_array = np.array(returns)

        mean = np.mean(returns_array)
        std = np.std(returns_array)

        # Z-score for confidence level
        z_score = stats.norm.ppf(1 - confidence)

        # Scale for horizon
        scaled_std = std * np.sqrt(horizon_days)
        scaled_mean = mean * horizon_days

        var = (scaled_mean + z_score * scaled_std) * position_value

        return var

    def monte_carlo_var(
        self,
        returns: List[float],
        position_value: float,
        confidence: float = 0.95,
        horizon_days: int = 1,
        n_simulations: int = 10000
    ) -> float:
        """
        Calculate Monte Carlo VaR.

        Simulates future returns based on historical distribution.

        Args:
            returns: Historical returns
            position_value: Current position value
            confidence: Confidence level
            horizon_days: Time horizon
            n_simulations: Number of Monte Carlo simulations

        Returns:
            VaR in USD
        """
        if len(returns) < 10:
            return -position_value * 0.20

        returns_array = np.array(returns)

        mean = np.mean(returns_array)
        std = np.std(returns_array)

        # Simulate future returns
        simulated_returns = np.random.normal(mean, std, (n_simulations, horizon_days))

        # Cumulative returns over horizon
        cumulative_returns = np.sum(simulated_returns, axis=1)

        # Portfolio values at end of horizon
        final_values = position_value * (1 + cumulative_returns)

        # VaR is the loss at confidence percentile
        var_percentile = (1 - confidence) * 100
        var_value = np.percentile(final_values, var_percentile)

        var = var_value - position_value  # Loss (negative)

        return var

    def conditional_var(
        self,
        returns: List[float],
        position_value: float,
        confidence: float = 0.95,
        horizon_days: int = 1
    ) -> float:
        """
        Calculate Conditional VaR (Expected Shortfall / CVaR).

        Expected loss given that loss exceeds VaR.

        Args:
            returns: Historical returns
            position_value: Current position value
            confidence: Confidence level
            horizon_days: Time horizon

        Returns:
            CVaR in USD
        """
        if len(returns) < 10:
            return -position_value * 0.25

        returns_array = np.array(returns)

        if horizon_days > 1:
            returns_array = returns_array * np.sqrt(horizon_days)

        var_percentile = (1 - confidence) * 100
        var_threshold = np.percentile(returns_array, var_percentile)

        # Expected shortfall: mean of returns below VaR threshold
        tail_returns = returns_array[returns_array <= var_threshold]

        if len(tail_returns) > 0:
            cvar = np.mean(tail_returns) * position_value
        else:
            cvar = var_threshold * position_value

        return cvar

    def calculate_var(
        self,
        symbol: Optional[str] = None,
        position_value: float = 0,
        confidence: float = 0.95,
        horizon_days: int = 1,
        method: str = 'historical'
    ) -> VaRResult:
        """
        Calculate VaR using specified method.

        Args:
            symbol: Trading pair (None for portfolio)
            position_value: Position value in USD
            confidence: Confidence level
            horizon_days: Time horizon
            method: 'historical', 'parametric', or 'monte_carlo'

        Returns:
            VaRResult with calculations
        """
        # Get returns
        if symbol:
            returns = self.returns_history.get(symbol, [])
        else:
            returns = self.portfolio_returns

        if not returns:
            logger.warning(f"No returns data for {symbol or 'portfolio'}")
            returns = [-0.02, -0.01, 0.01, 0.02, -0.03, 0.015, -0.005]  # Dummy data

        # Calculate VaR using specified method
        if method == 'parametric':
            var_95 = self.parametric_var(returns, position_value, 0.95, horizon_days)
            var_99 = self.parametric_var(returns, position_value, 0.99, horizon_days)
        elif method == 'monte_carlo':
            var_95 = self.monte_carlo_var(returns, position_value, 0.95, horizon_days)
            var_99 = self.monte_carlo_var(returns, position_value, 0.99, horizon_days)
        else:  # historical
            var_95 = self.historical_var(returns, position_value, 0.95, horizon_days)
            var_99 = self.historical_var(returns, position_value, 0.99, horizon_days)

        # Always calculate CVaR using historical method
        cvar_95 = self.conditional_var(returns, position_value, 0.95, horizon_days)

        return VaRResult(
            var_95=round(var_95, 4),
            var_99=round(var_99, 4),
            cvar_95=round(cvar_95, 4),
            method=method,
            horizon_days=horizon_days,
            confidence=confidence,
            position_value=position_value
        )


class VaRPositionLimiter:
    """
    Position limiter based on VaR constraints.

    Ensures portfolio VaR stays within acceptable limits.
    """

    def __init__(
        self,
        max_portfolio_var_pct: float = 0.10,  # Max 10% portfolio VaR
        max_position_var_pct: float = 0.05,   # Max 5% position VaR
        var_calculator: VaRCalculator = None
    ):
        self.max_portfolio_var_pct = max_portfolio_var_pct
        self.max_position_var_pct = max_position_var_pct
        self.var_calculator = var_calculator or VaRCalculator()

    def get_max_position_size(
        self,
        symbol: str,
        portfolio_value: float,
        current_portfolio_var: float = None
    ) -> float:
        """
        Calculate maximum position size based on VaR limits.

        Args:
            symbol: Trading pair
            portfolio_value: Total portfolio value
            current_portfolio_var: Current portfolio VaR (optional)

        Returns:
            Maximum position size in USD
        """
        # Calculate symbol VaR for $1000 position
        test_size = 1000.0
        symbol_var = self.var_calculator.calculate_var(
            symbol=symbol,
            position_value=test_size,
            confidence=0.95,
            horizon_days=1
        )

        # VaR per dollar
        var_per_dollar = abs(symbol_var.var_95) / test_size

        # Maximum allowed position VaR
        max_position_var = portfolio_value * self.max_position_var_pct

        # Maximum position size
        if var_per_dollar > 0:
            max_size = max_position_var / var_per_dollar
        else:
            max_size = portfolio_value * 0.10  # Default 10% of portfolio

        return round(max_size, 2)

    def check_position_allowed(
        self,
        symbol: str,
        position_size: float,
        portfolio_value: float,
        existing_positions: Dict[str, float] = None
    ) -> Tuple[bool, str]:
        """
        Check if a position is allowed under VaR constraints.

        Args:
            symbol: Trading pair
            position_size: Proposed position size
            portfolio_value: Total portfolio value
            existing_positions: Dict of symbol -> position value

        Returns:
            Tuple of (allowed, reason)
        """
        # Calculate position VaR
        position_var = self.var_calculator.calculate_var(
            symbol=symbol,
            position_value=position_size,
            confidence=0.95
        )

        # Check position VaR limit
        max_position_var = portfolio_value * self.max_position_var_pct
        if abs(position_var.var_95) > max_position_var:
            return False, f"Position VaR ${abs(position_var.var_95):.2f} exceeds limit ${max_position_var:.2f}"

        # Check portfolio VaR if we have existing positions
        if existing_positions:
            # Simplified: assume VaRs are additive (conservative)
            total_var = abs(position_var.var_95)
            for sym, size in existing_positions.items():
                sym_var = self.var_calculator.calculate_var(sym, size, 0.95)
                total_var += abs(sym_var.var_95)

            max_portfolio_var = portfolio_value * self.max_portfolio_var_pct
            if total_var > max_portfolio_var:
                return False, f"Portfolio VaR ${total_var:.2f} would exceed limit ${max_portfolio_var:.2f}"

        return True, "Position allowed under VaR constraints"

    def adjust_position_size(
        self,
        symbol: str,
        desired_size: float,
        portfolio_value: float
    ) -> float:
        """
        Adjust position size to fit VaR constraints.

        Args:
            symbol: Trading pair
            desired_size: Desired position size
            portfolio_value: Total portfolio value

        Returns:
            Adjusted position size (may be smaller than desired)
        """
        max_size = self.get_max_position_size(symbol, portfolio_value)
        return min(desired_size, max_size)


# Singleton instances
_var_calculator: Optional[VaRCalculator] = None
_var_limiter: Optional[VaRPositionLimiter] = None

def get_var_calculator() -> VaRCalculator:
    """Get singleton VaR calculator"""
    global _var_calculator
    if _var_calculator is None:
        _var_calculator = VaRCalculator()
    return _var_calculator

def get_var_limiter() -> VaRPositionLimiter:
    """Get singleton VaR position limiter"""
    global _var_limiter
    if _var_limiter is None:
        _var_limiter = VaRPositionLimiter()
    return _var_limiter


if __name__ == "__main__":
    # Demo
    print("=" * 60)
    print("VaR INTEGRATION DEMO")
    print("=" * 60)

    # Create calculator with some dummy returns
    calc = VaRCalculator('/tmp/test_var.json')

    # Simulate some returns
    np.random.seed(42)
    btc_returns = list(np.random.normal(0.001, 0.03, 100))  # Mean 0.1%, std 3%
    eth_returns = list(np.random.normal(0.002, 0.05, 100))  # Mean 0.2%, std 5%

    calc.returns_history['BTC/USDT:USDT'] = btc_returns
    calc.returns_history['ETH/USDT:USDT'] = eth_returns
    calc.portfolio_returns = [
        (b + e) / 2 for b, e in zip(btc_returns, eth_returns)
    ]

    # Calculate VaR for $10,000 BTC position
    position_value = 10000
    print(f"\n📊 VaR Analysis for ${position_value:,} BTC position")
    print("-" * 50)

    for method in ['historical', 'parametric', 'monte_carlo']:
        result = calc.calculate_var(
            symbol='BTC/USDT:USDT',
            position_value=position_value,
            confidence=0.95,
            horizon_days=1,
            method=method
        )
        print(f"\n{method.upper()} METHOD:")
        print(f"  95% VaR: ${abs(result.var_95):,.2f} (potential 1-day loss)")
        print(f"  99% VaR: ${abs(result.var_99):,.2f}")
        print(f"  95% CVaR: ${abs(result.cvar_95):,.2f} (expected shortfall)")

    # Test position limiter
    print("\n" + "=" * 60)
    print("POSITION LIMITER TEST")
    print("=" * 60)

    limiter = VaRPositionLimiter(
        max_portfolio_var_pct=0.10,
        max_position_var_pct=0.05,
        var_calculator=calc
    )

    portfolio_value = 50000

    max_btc = limiter.get_max_position_size('BTC/USDT:USDT', portfolio_value)
    max_eth = limiter.get_max_position_size('ETH/USDT:USDT', portfolio_value)

    print(f"\nPortfolio Value: ${portfolio_value:,}")
    print(f"Max BTC Position: ${max_btc:,.2f}")
    print(f"Max ETH Position: ${max_eth:,.2f}")

    # Check if positions are allowed
    allowed, reason = limiter.check_position_allowed(
        'BTC/USDT:USDT',
        position_size=5000,
        portfolio_value=portfolio_value
    )
    print(f"\n$5,000 BTC position: {'✅ Allowed' if allowed else '❌ Rejected'}")
    print(f"  Reason: {reason}")
