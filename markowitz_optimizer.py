#!/usr/bin/env python3
"""
Markowitz Portfolio Optimizer for Opportunity Cost Service
Uses Modern Portfolio Theory for optimal capital allocation across opportunities
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.covariance import LedoitWolf
import ccxt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')

class MarkowitzOptimizer:
    """
    Modern Portfolio Theory optimizer for capital allocation
    Maximizes Sharpe ratio while considering opportunity costs
    """

    def __init__(self, risk_free_rate: float = 0.02):
        self.risk_free_rate = risk_free_rate
        self.expected_returns = {}
        self.covariance_matrix = None
        self.asset_universe = []

    def optimize_portfolio(self, opportunities: Dict, current_positions: Dict,
                          total_capital: float, risk_tolerance: float = 0.5) -> Dict:
        """
        Optimize portfolio allocation using Markowitz theory

        Args:
            opportunities: Dict of market opportunities with expected returns and risks
            current_positions: Current portfolio positions
            total_capital: Total available capital
            risk_tolerance: Risk tolerance (0=conservative, 1=aggressive)

        Returns:
            dict: Optimal allocation recommendations
        """
        print("📊 Running Markowitz Portfolio Optimization...")

        # Prepare asset universe
        all_assets = set(opportunities.keys()) | set(current_positions.keys())
        self.asset_universe = list(all_assets)

        if len(self.asset_universe) < 2:
            return self._fallback_allocation(opportunities, total_capital)

        try:
            # Estimate expected returns and covariance
            expected_returns = self._estimate_expected_returns(opportunities, current_positions)
            covariance_matrix = self._estimate_covariance_matrix(opportunities, current_positions)

            # Ensure proper data types
            expected_returns = np.array(expected_returns, dtype=float)
            covariance_matrix = np.array(covariance_matrix, dtype=float)

            # Add opportunity cost penalty to expected returns
            adjusted_returns = self._adjust_for_opportunity_cost(expected_returns, opportunities)

            # Optimize portfolio
            optimal_weights = self._markowitz_optimization(
                adjusted_returns, covariance_matrix, risk_tolerance
            )

            # Convert to allocation recommendations
            recommendations = self._generate_allocation_recommendations(
                optimal_weights, opportunities, current_positions, total_capital, expected_returns, covariance_matrix
            )

            print(".4f")
            return recommendations

        except Exception as e:
            print(f"❌ Markowitz optimization failed: {e}")
            import traceback
            traceback.print_exc()
            return self._fallback_allocation(opportunities, total_capital)

    def _estimate_expected_returns(self, opportunities: Dict, current_positions: Dict) -> np.ndarray:
        """Estimate expected returns for all assets"""
        returns = []

        for asset in self.asset_universe:
            if asset in opportunities:
                # Use opportunity data
                opp_data = opportunities[asset]
                expected_return = opp_data.get('expected_return', 0)
                sharpe_ratio = opp_data.get('sharpe_ratio', 0)

                # Adjust based on Sharpe ratio (higher Sharpe = higher expected return)
                risk_adjusted_return = expected_return * (1 + sharpe_ratio * 0.1)

            elif asset in current_positions:
                # Use current position performance
                pos_data = current_positions[asset]
                current_pnl = pos_data.get('pnl', 0)
                holding_time = pos_data.get('holding_time_hours', 1)

                # Extrapolate current performance
                annualized_return = current_pnl * (24 / holding_time) if holding_time > 0 else 0
                risk_adjusted_return = annualized_return

            else:
                risk_adjusted_return = 0.02  # Default 2% return

            returns.append(risk_adjusted_return)

        return np.array(returns)

    def _estimate_covariance_matrix(self, opportunities: Dict, current_positions: Dict) -> np.ndarray:
        """Estimate covariance matrix using Ledoit-Wolf shrinkage"""
        # Create synthetic covariance matrix based on available data
        n_assets = len(self.asset_universe)
        cov_matrix = np.zeros((n_assets, n_assets))

        # Fill diagonal with volatility estimates
        for i, asset in enumerate(self.asset_universe):
            if asset in opportunities:
                volatility = opportunities[asset].get('volatility', 0.05)
            elif asset in current_positions:
                # Estimate from position data
                pnl = current_positions[asset].get('pnl', 0)
                volatility = abs(pnl) * 2  # Rough volatility estimate
            else:
                volatility = 0.05  # Default

            cov_matrix[i, i] = volatility ** 2

        # Fill off-diagonal with correlation estimates
        for i in range(n_assets):
            for j in range(i + 1, n_assets):
                asset_i = self.asset_universe[i]
                asset_j = self.asset_universe[j]

                # Estimate correlation based on sector similarity
                correlation = self._estimate_correlation(asset_i, asset_j, opportunities)
                cov_i = cov_matrix[i, i]
                cov_j = cov_matrix[j, j]

                covariance = correlation * np.sqrt(cov_i * cov_j)
                cov_matrix[i, j] = covariance
                cov_matrix[j, i] = covariance

        # Apply Ledoit-Wolf shrinkage for stability
        try:
            lw = LedoitWolf()
            cov_matrix = lw.fit(cov_matrix).covariance_
        except:
            pass  # Use original if shrinkage fails

        return cov_matrix

    def _estimate_correlation(self, asset_i: str, asset_j: str, opportunities: Dict) -> float:
        """Estimate correlation between two assets"""
        # Check if both have correlation data
        corr_i = opportunities.get(asset_i, {}).get('correlation_with_market', 0)
        corr_j = opportunities.get(asset_j, {}).get('correlation_with_market', 0)

        # Similar correlation with market = higher correlation between assets
        base_correlation = (corr_i + corr_j) / 2

        # Add sector-based correlation
        sector_similarity = self._get_sector_similarity(asset_i, asset_j)
        correlation = base_correlation + (sector_similarity - 0.5) * 0.3

        # Bound between -1 and 1
        return np.clip(correlation, -1, 1)

    def _get_sector_similarity(self, asset_i: str, asset_j: str) -> float:
        """Get sector similarity score between two assets"""
        # Simple sector mapping (expand this based on your asset universe)
        sector_map = {
            'BTC': 'store_of_value', 'ETH': 'smart_contract',
            'ADA': 'smart_contract', 'DOT': 'smart_contract',
            'LINK': 'oracle', 'UNI': 'defi', 'AAVE': 'defi',
            'SUSHI': 'defi', 'COMP': 'defi', 'MKR': 'defi',
            'YFI': 'defi', 'CRV': 'defi', 'BAL': 'defi'
        }

        sector_i = sector_map.get(asset_i.replace('/USDT', '').replace('USDT:', ''), 'other')
        sector_j = sector_map.get(asset_j.replace('/USDT', '').replace('USDT:', ''), 'other')

        if sector_i == sector_j and sector_i != 'other':
            return 0.8  # Same sector
        elif sector_i != 'other' and sector_j != 'other':
            return 0.3  # Different known sectors
        else:
            return 0.1  # Unknown sectors

    def _adjust_for_opportunity_cost(self, expected_returns: np.ndarray, opportunities: Dict) -> np.ndarray:
        """Adjust expected returns based on opportunity cost analysis"""
        adjusted_returns = expected_returns.copy()

        for i, asset in enumerate(self.asset_universe):
            if asset in opportunities:
                opp_cost = opportunities[asset].get('opportunity_cost', 0)
                # Penalize assets with high opportunity cost
                penalty = opp_cost * 0.5  # 50% penalty factor
                adjusted_returns[i] -= penalty

        return adjusted_returns

    def _markowitz_optimization(self, expected_returns: np.ndarray, covariance_matrix: np.ndarray,
                              risk_tolerance: float) -> np.ndarray:
        """Perform Markowitz portfolio optimization"""
        n_assets = len(expected_returns)

        # Objective: maximize Sharpe ratio
        def objective(weights):
            portfolio_return = np.dot(weights, expected_returns)
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(covariance_matrix, weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility
            return -sharpe_ratio  # Minimize negative Sharpe

        # Constraints
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},  # Weights sum to 1
        ]

        # Bounds: 0 to 1 (no short selling)
        bounds = [(0, 1) for _ in range(n_assets)]

        # Initial guess: equal weight
        initial_weights = np.ones(n_assets) / n_assets

        # Adjust for risk tolerance
        # Higher risk tolerance allows more concentrated portfolios
        if risk_tolerance > 0.5:
            # Allow higher concentration
            bounds = [(0, min(1, 0.3 + risk_tolerance)) for _ in range(n_assets)]
        elif risk_tolerance < 0.3:
            # Force diversification
            bounds = [(0, 0.15) for _ in range(n_assets)]  # Max 15% per asset

        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints,
            options={'maxiter': 1000, 'ftol': 1e-9}
        )

        if result.success:
            return result.x
        else:
            # Fallback to equal weight
            return np.ones(n_assets) / n_assets

    def _generate_allocation_recommendations(self, optimal_weights: np.ndarray, opportunities: Dict,
                                           current_positions: Dict, total_capital: float,
                                           expected_returns: np.ndarray = None, covariance_matrix: np.ndarray = None) -> Dict:
        """Generate actionable allocation recommendations"""

        recommendations = {
            'optimal_allocations': {},
            'rebalancing_actions': [],
            'expected_portfolio_return': 0,
            'expected_portfolio_volatility': 0,
            'sharpe_ratio': 0,
            'diversification_score': 0
        }

        # Calculate optimal capital allocations
        available_capital = total_capital * 0.7  # 70% utilization
        min_allocation = total_capital * 0.01   # 1% minimum

        for i, asset in enumerate(self.asset_universe):
            weight = optimal_weights[i]
            allocation = weight * available_capital

            if allocation >= min_allocation:
                # Get expected return for this asset
                if expected_returns is not None and i < len(expected_returns):
                    asset_return = expected_returns[i]
                else:
                    asset_return = opportunities.get(asset, {}).get('expected_return', 0.02)

                recommendations['optimal_allocations'][asset] = {
                    'weight': weight,
                    'allocation_usd': allocation,
                    'expected_return': asset_return,
                    'action': self._determine_action(asset, allocation, current_positions)
                }

        # Calculate portfolio metrics
        if expected_returns is not None:
            portfolio_return = np.dot(optimal_weights, expected_returns)
        else:
            # Fallback: use equal weight returns
            portfolio_return = np.mean([opp.get('expected_return', 0.02) for opp in opportunities.values()])

        portfolio_volatility = np.sqrt(np.dot(optimal_weights.T, np.dot(covariance_matrix, optimal_weights)))
        sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility

        recommendations.update({
            'expected_portfolio_return': portfolio_return,
            'expected_portfolio_volatility': portfolio_volatility,
            'sharpe_ratio': sharpe_ratio,
            'diversification_score': self._calculate_diversification_score(optimal_weights)
        })

        return recommendations

    def _determine_action(self, asset: str, optimal_allocation: float, current_positions: Dict) -> str:
        """Determine whether to OPEN, HOLD, or CLOSE position"""
        current_allocation = 0

        if asset in current_positions:
            pos_data = current_positions[asset]
            current_allocation = (pos_data.get('amount', 0) *
                                pos_data.get('entry_price', 1) /
                                pos_data.get('leverage', 1))

        if current_allocation == 0:
            return 'OPEN'
        elif abs(optimal_allocation - current_allocation) / current_allocation > 0.1:
            return 'REALLOCATE'
        else:
            return 'HOLD'

    def _calculate_diversification_score(self, weights: np.ndarray) -> float:
        """Calculate portfolio diversification score"""
        # Herfindahl-Hirschman Index (lower = more diversified)
        hhi = np.sum(weights ** 2)

        # Convert to diversification score (0-1, higher = more diversified)
        diversification_score = 1 - hhi

        return diversification_score

    def _fallback_allocation(self, opportunities: Dict, total_capital: float) -> Dict:
        """Fallback allocation when optimization fails"""
        print("⚠️ Using fallback equal-weight allocation")

        allocations = {}
        available_capital = total_capital * 0.7
        min_allocation = total_capital * 0.01

        if opportunities:
            n_opportunities = len(opportunities)
            equal_allocation = available_capital / n_opportunities

            for asset in opportunities.keys():
                if equal_allocation >= min_allocation:
                    allocations[asset] = {
                        'weight': 1.0 / n_opportunities,
                        'allocation_usd': equal_allocation,
                        'expected_return': opportunities[asset].get('expected_return', 0),
                        'action': 'OPEN'
                    }

        return {
            'optimal_allocations': allocations,
            'rebalancing_actions': [],
            'expected_portfolio_return': 0.05,  # Conservative estimate
            'expected_portfolio_volatility': 0.08,
            'sharpe_ratio': 0.375,
            'diversification_score': 0.8
        }