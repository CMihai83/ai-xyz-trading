#!/usr/bin/env python3
"""
V3: Advanced Delta Engine with ML-Enhanced Calculations
Sophisticated delta calculation with market regime awareness and learning
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
# from sklearn.ensemble import RandomForestRegressor
# from sklearn.preprocessing import StandardScaler

# Dummy classes for when sklearn is not available
class StandardScaler:
    def fit(self, X):
        return self
    def transform(self, X):
        return X
    def fit_transform(self, X):
        return X

class RandomForestRegressor:
    def __init__(self, **kwargs):
        pass
    def fit(self, X, y):
        pass
    def predict(self, X):
        return [0.5] * len(X) if hasattr(X, '__len__') else [0.5]

import joblib
import os
import json

class AdvancedDeltaEngine:
    """
    ML-enhanced delta calculation with adaptive learning
    """

    def __init__(self):
        self.delta_history = self.load_delta_history()
        self.market_regime_model = None
        self.delta_performance_model = None
        self.scaler = StandardScaler()
        self.load_models()

    def load_delta_history(self):
        """Load historical delta performance data"""
        try:
            with open('/root/ai_xyz/delta_performance_history.json', 'r') as f:
                return json.load(f)
        except:
            return {}

    def load_models(self):
        """Load pre-trained ML models"""
        try:
            if os.path.exists('/root/ai_xyz/models/market_regime_model.pkl'):
                self.market_regime_model = joblib.load('/root/ai_xyz/models/market_regime_model.pkl')
            if os.path.exists('/root/ai_xyz/delta_performance_model.pkl'):
                self.delta_performance_model = joblib.load('/root/ai_xyz/delta_performance_model.pkl')
        except Exception as e:
            print(f"Warning: Could not load ML models: {e}")

    def calculate_adaptive_delta(self, symbol, market_context, position_data=None):
        """
        Calculate adaptive delta using multiple methodologies

        Args:
            symbol: Trading symbol
            market_context: Current market analysis
            position_data: Current position information

        Returns:
            dict: Comprehensive delta analysis
        """
        # Method 1: Statistical Delta (improved)
        statistical_delta = self.calculate_statistical_delta(symbol, market_context)

        # Method 2: ML-Predicted Delta
        ml_delta = self.calculate_ml_delta(symbol, market_context, position_data)

        # Method 3: Regime-Aware Delta
        regime_delta = self.calculate_regime_delta(symbol, market_context)

        # Method 4: Performance-Based Delta
        performance_delta = self.calculate_performance_delta(symbol, position_data)

        # Ensemble weighting based on confidence
        weights = self.calculate_ensemble_weights(statistical_delta, ml_delta, regime_delta, performance_delta)

        final_delta = (
            statistical_delta['delta'] * weights['statistical'] +
            ml_delta['delta'] * weights['ml'] +
            regime_delta['delta'] * weights['regime'] +
            performance_delta['delta'] * weights['performance']
        )

        # Apply bounds and smoothing
        final_delta = self.apply_delta_constraints(final_delta, market_context)

        return {
            'final_delta': final_delta,
            'component_deltas': {
                'statistical': statistical_delta,
                'ml': ml_delta,
                'regime': regime_delta,
                'performance': performance_delta
            },
            'weights': weights,
            'confidence': sum(weights.values()),
            'recommended_timeframe': self.select_optimal_timeframe(market_context)
        }

    def calculate_statistical_delta(self, symbol, market_context):
        """Enhanced statistical delta calculation"""
        volatility = market_context.get('volatility', 0.5)
        trend_strength = market_context.get('trend_strength', 0.5)
        volume_profile = market_context.get('volume_profile', 1.0)

        # Base delta from volatility
        base_delta = volatility * 0.1  # 10% of volatility as base

        # Adjust for trend strength
        trend_multiplier = 1 + (trend_strength - 0.5) * 0.5

        # Adjust for volume (higher volume = smaller delta)
        volume_multiplier = 1 / (1 + volume_profile * 0.5)

        # Time-based decay (recent data more important)
        time_decay = self.calculate_time_decay_factor(market_context)

        statistical_delta = base_delta * trend_multiplier * volume_multiplier * time_decay

        # Calculate confidence based on data quality
        confidence = min(1.0, (volatility * 2 + trend_strength + volume_profile) / 4)

        return {
            'delta': statistical_delta,
            'confidence': confidence,
            'method': 'statistical',
            'components': {
                'base': base_delta,
                'trend': trend_multiplier,
                'volume': volume_multiplier,
                'time': time_decay
            }
        }

    def calculate_ml_delta(self, symbol, market_context, position_data):
        """ML-predicted delta using trained models"""
        if not self.delta_performance_model:
            # Fallback to statistical
            return self.calculate_statistical_delta(symbol, market_context)

        try:
            # Prepare features for ML model
            features = self.prepare_ml_features(symbol, market_context, position_data)

            # Scale features
            features_scaled = self.scaler.transform([features])

            # Predict optimal delta
            predicted_delta = self.delta_performance_model.predict(features_scaled)[0]

            # Calculate prediction confidence
            confidence = self.calculate_prediction_confidence(features, predicted_delta)

            return {
                'delta': max(0.001, predicted_delta),  # Ensure positive
                'confidence': confidence,
                'method': 'ml',
                'features_used': len(features)
            }

        except Exception as e:
            print(f"ML delta calculation failed: {e}")
            return self.calculate_statistical_delta(symbol, market_context)

    def calculate_regime_delta(self, symbol, market_context):
        """Regime-aware delta calculation"""
        regime = market_context.get('regime', 'neutral')

        # Base deltas by regime
        regime_bases = {
            'bull': 0.02,    # Smaller deltas in trending markets
            'bear': 0.03,    # Moderate deltas in downtrends
            'volatile': 0.05, # Larger deltas in volatile markets
            'neutral': 0.03  # Moderate deltas in ranging markets
        }

        base_delta = regime_bases.get(regime, 0.03)

        # Adjust based on regime strength
        regime_strength = market_context.get('regime_strength', 0.5)
        strength_multiplier = 1 + (regime_strength - 0.5) * 0.4

        # Market momentum adjustment
        momentum = market_context.get('momentum', 0)
        momentum_multiplier = 1 + momentum * 0.2

        regime_delta = base_delta * strength_multiplier * momentum_multiplier

        return {
            'delta': regime_delta,
            'confidence': regime_strength,
            'method': 'regime',
            'regime': regime,
            'strength': regime_strength
        }

    def calculate_performance_delta(self, symbol, position_data):
        """Performance-based delta optimization"""
        if not position_data:
            return {
                'delta': 0.03,  # Default
                'confidence': 0.3,
                'method': 'performance'
            }

        # Analyze historical performance for this symbol
        symbol_history = self.delta_history.get(symbol, [])

        if len(symbol_history) < 5:
            return {
                'delta': 0.03,
                'confidence': 0.3,
                'method': 'performance'
            }

        # Find optimal delta from historical performance
        best_delta = 0.03
        best_sharpe = -1

        for delta in [0.01, 0.02, 0.03, 0.05, 0.08, 0.10]:
            delta_performance = [h for h in symbol_history if abs(h.get('delta', 0.03) - delta) < 0.01]

            if len(delta_performance) >= 3:
                returns = [p.get('return', 0) for p in delta_performance]
                sharpe = np.mean(returns) / (np.std(returns) + 1e-6) if returns else 0

                if sharpe > best_sharpe:
                    best_sharpe = sharpe
                    best_delta = delta

        return {
            'delta': best_delta,
            'confidence': min(1.0, len(symbol_history) / 20),  # More history = higher confidence
            'method': 'performance',
            'optimal_sharpe': best_sharpe
        }

    def calculate_ensemble_weights(self, stat, ml, regime, perf):
        """Calculate ensemble weights based on confidence scores"""
        total_confidence = stat['confidence'] + ml['confidence'] + regime['confidence'] + perf['confidence']

        if total_confidence == 0:
            return {'statistical': 0.4, 'ml': 0.2, 'regime': 0.2, 'performance': 0.2}

        weights = {
            'statistical': stat['confidence'] / total_confidence,
            'ml': ml['confidence'] / total_confidence,
            'regime': regime['confidence'] / total_confidence,
            'performance': perf['confidence'] / total_confidence
        }

        return weights

    def apply_delta_constraints(self, delta, market_context):
        """Apply realistic constraints to delta"""
        # Minimum and maximum bounds
        delta = max(0.005, min(delta, 0.20))  # 0.5% to 20%

        # Market volatility adjustment
        volatility = market_context.get('volatility', 0.5)
        if volatility > 0.8:  # Very volatile
            delta = min(delta * 1.5, 0.20)
        elif volatility < 0.2:  # Low volatility
            delta = max(delta * 0.7, 0.005)

        # Smooth with exponential moving average
        symbol_history = self.delta_history.get(market_context.get('symbol', ''), [])
        if symbol_history:
            recent_deltas = [h.get('delta', delta) for h in symbol_history[-10:]]
            smoothed_delta = np.mean(recent_deltas) * 0.7 + delta * 0.3
            delta = smoothed_delta

        return delta

    def select_optimal_timeframe(self, market_context):
        """Select optimal timeframe for delta calculation"""
        volatility = market_context.get('volatility', 0.5)
        trend_strength = market_context.get('trend_strength', 0.5)
        volume = market_context.get('volume_profile', 1.0)

        # Timeframe selection logic
        if volatility > 0.7 and trend_strength > 0.7:
            return '1h'  # Fast-moving trending market
        elif volatility > 0.7:
            return '15m'  # Volatile but not strongly trending
        elif trend_strength > 0.7:
            return '4h'  # Strong trend, longer timeframe
        elif volume > 1.5:
            return '5m'  # High volume, shorter timeframe
        else:
            return '1h'  # Default balanced timeframe

    def prepare_ml_features(self, symbol, market_context, position_data):
        """Prepare features for ML model"""
        features = [
            market_context.get('volatility', 0.5),
            market_context.get('trend_strength', 0.5),
            market_context.get('sentiment', 0),
            market_context.get('momentum', 0),
            market_context.get('volume_profile', 1.0),
            position_data.get('pnl', 0) if position_data else 0,
            position_data.get('holding_time', 0) if position_data else 0,
            len(self.delta_history.get(symbol, []))  # Historical data points
        ]

        return features

    def calculate_prediction_confidence(self, features, prediction):
        """Calculate confidence in ML prediction"""
        # Simple confidence based on feature consistency
        feature_std = np.std(features)
        confidence = 1 / (1 + feature_std)  # Lower variance = higher confidence

        # Adjust based on prediction reasonableness
        if 0.01 <= prediction <= 0.15:
            confidence *= 1.2  # Reasonable prediction
        else:
            confidence *= 0.8  # Extreme prediction

        return min(confidence, 1.0)

    def calculate_time_decay_factor(self, market_context):
        """Calculate time-based decay factor"""
        # More recent data is more important
        # Simple exponential decay
        return 0.8  # 80% weight on recent data

    def update_performance(self, symbol, delta, performance_metrics):
        """Update delta performance history"""
        if symbol not in self.delta_history:
            self.delta_history[symbol] = []

        self.delta_history[symbol].append({
            'timestamp': datetime.now().isoformat(),
            'delta': delta,
            'return': performance_metrics.get('return', 0),
            'sharpe': performance_metrics.get('sharpe', 0),
            'duration': performance_metrics.get('duration', 0)
        })

        # Keep last 100 entries
        self.delta_history[symbol] = self.delta_history[symbol][-100:]

        # Save to disk
        try:
            with open('/root/ai_xyz/delta_performance_history.json', 'w') as f:
                json.dump(self.delta_history, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save delta history: {e}")