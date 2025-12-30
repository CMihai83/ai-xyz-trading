#!/usr/bin/env python3
"""
ML-based Opportunity Cost Predictor
Uses machine learning to predict future opportunity costs and optimal holding times
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, mean_squared_error
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense, Dropout
from datetime import datetime, timedelta
import json
import os
from typing import Dict, List, Optional, Tuple

class OpportunityCostPredictor:
    """
    ML models for predicting opportunity costs and optimal holding strategies
    """

    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.feature_columns = [
            'current_pnl', 'holding_time_hours', 'position_size_pct',
            'market_volatility', 'market_return_1h', 'market_return_24h',
            'correlation_with_market', 'rsi', 'macd_signal', 'bb_position',
            'volume_ratio', 'price_change_1h', 'price_change_24h'
        ]
        self.target_columns = ['future_opportunity_cost_1h', 'future_opportunity_cost_4h', 'optimal_holding_time']
        self.model_accuracy = {}

    def train_models(self, historical_data: pd.DataFrame):
        """
        Train ML models on historical trading data

        Args:
            historical_data: DataFrame with historical position and market data
        """
        print("🏗️ Training ML models for opportunity cost prediction...")

        # Prepare features and targets
        X, y = self._prepare_training_data(historical_data)

        if len(X) < 100:
            print("⚠️ Insufficient training data. Need at least 100 samples.")
            return

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

        # Scale features
        self.scalers['features'] = StandardScaler()
        X_train_scaled = self.scalers['features'].fit_transform(X_train)
        X_test_scaled = self.scalers['features'].transform(X_test)

        # Train Random Forest model
        print("🌲 Training Random Forest model...")
        rf_model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        rf_model.fit(X_train_scaled, y_train)
        self.models['random_forest'] = rf_model

        # Train Gradient Boosting model
        print("🚀 Training Gradient Boosting model...")
        gb_model = GradientBoostingRegressor(
            n_estimators=100,
            max_depth=6,
            random_state=42
        )
        gb_model.fit(X_train_scaled, y_train)
        self.models['gradient_boosting'] = gb_model

        # Train LSTM model for time series prediction
        print("🧠 Training LSTM model...")
        self._train_lstm_model(historical_data)

        # Evaluate models
        self._evaluate_models(X_test_scaled, y_test)

        print("✅ ML models trained successfully!")

    def _prepare_training_data(self, historical_data: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare features and targets for training"""
        # Create target variables: future opportunity costs
        historical_data = historical_data.copy()

        # Calculate future opportunity costs (1h and 4h ahead)
        historical_data['future_opportunity_cost_1h'] = historical_data.groupby('symbol')['opportunity_cost'].shift(-1)
        historical_data['future_opportunity_cost_4h'] = historical_data.groupby('symbol')['opportunity_cost'].shift(-4)

        # Calculate optimal holding time (time until best exit point)
        historical_data['optimal_holding_time'] = self._calculate_optimal_holding_times(historical_data)

        # Select features and targets
        feature_cols = [col for col in self.feature_columns if col in historical_data.columns]
        target_cols = [col for col in self.target_columns if col in historical_data.columns]

        # Drop NaN values
        valid_data = historical_data.dropna(subset=feature_cols + target_cols)

        X = valid_data[feature_cols].values
        y = valid_data[target_cols[0]].values  # Focus on 1h prediction for now

        return X, y

    def _calculate_optimal_holding_times(self, data: pd.DataFrame) -> pd.Series:
        """Calculate optimal holding times based on historical performance"""
        optimal_times = []

        for symbol in data['symbol'].unique():
            symbol_data = data[data['symbol'] == symbol].copy()
            symbol_data = symbol_data.sort_values('timestamp')

            for idx, row in symbol_data.iterrows():
                # Find the best exit point within next 24 hours
                future_data = symbol_data[
                    (symbol_data['timestamp'] > row['timestamp']) &
                    (symbol_data['timestamp'] <= row['timestamp'] + timedelta(hours=24))
                ]

                if len(future_data) > 0:
                    # Optimal time is when pnl was highest before a significant drop
                    max_pnl_idx = future_data['pnl'].idxmax()
                    optimal_time = (symbol_data.loc[max_pnl_idx, 'timestamp'] - row['timestamp']).total_seconds() / 3600
                    optimal_times.append(min(optimal_time, 24))  # Cap at 24 hours
                else:
                    optimal_times.append(4)  # Default 4 hours

        return pd.Series(optimal_times, index=data.index)

    def _train_lstm_model(self, historical_data: pd.DataFrame):
        """Train LSTM model for time series prediction"""
        # Prepare sequential data for LSTM
        sequence_length = 10  # Use last 10 periods

        sequences = []
        targets = []

        for symbol in historical_data['symbol'].unique():
            symbol_data = historical_data[historical_data['symbol'] == symbol].copy()
            symbol_data = symbol_data.sort_values('timestamp')

            if len(symbol_data) < sequence_length + 1:
                continue

            feature_cols = [col for col in self.feature_columns if col in symbol_data.columns]

            for i in range(len(symbol_data) - sequence_length):
                seq = symbol_data[feature_cols].iloc[i:i+sequence_length].values
                target = symbol_data['future_opportunity_cost_1h'].iloc[i+sequence_length]

                if not np.isnan(target):
                    sequences.append(seq)
                    targets.append(target)

        if len(sequences) < 50:
            print("⚠️ Insufficient sequential data for LSTM training")
            return

        X_lstm = np.array(sequences)
        y_lstm = np.array(targets)

        # Build LSTM model
        model = Sequential([
            LSTM(64, input_shape=(sequence_length, len(feature_cols)), return_sequences=True),
            Dropout(0.2),
            LSTM(32),
            Dropout(0.2),
            Dense(16, activation='relu'),
            Dense(1)
        ])

        model.compile(optimizer='adam', loss='mse', metrics=['mae'])

        # Train model
        model.fit(X_lstm, y_lstm, epochs=50, batch_size=32, verbose=0, validation_split=0.2)

        self.models['lstm'] = model

    def _evaluate_models(self, X_test: np.ndarray, y_test: np.ndarray):
        """Evaluate trained models"""
        for model_name, model in self.models.items():
            if model_name == 'lstm':
                continue  # LSTM evaluation separate

            predictions = model.predict(X_test)

            mae = mean_absolute_error(y_test, predictions)
            mse = mean_squared_error(y_test, predictions)
            rmse = np.sqrt(mse)

            self.model_accuracy[model_name] = {
                'mae': mae,
                'rmse': rmse,
                'accuracy_score': max(0, 1 - mae)  # Simple accuracy metric
            }

            print(f"Model {model_name}: MAE={mae:.4f}, RMSE={rmse:.4f}, Accuracy={self.model_accuracy[model_name]['accuracy_score']:.2f}")
    def predict_opportunity_cost(self, current_data: Dict, prediction_horizon: str = '1h') -> Dict:
        """
        Predict future opportunity cost using ensemble of ML models

        Args:
            current_data: Current position and market data
            prediction_horizon: '1h', '4h', or '24h'

        Returns:
            dict: Predictions from different models
        """
        if not self.models:
            # Fallback to simple calculation
            return {
                'predicted_cost': current_data.get('current_opportunity_cost', 0),
                'confidence': 0.5,
                'method': 'fallback'
            }

        # Prepare features
        features = self._extract_features(current_data)
        features_scaled = self.scalers['features'].transform([features])

        predictions = {}
        confidences = {}

        # Get predictions from each model
        for model_name, model in self.models.items():
            if model_name == 'lstm':
                # LSTM prediction requires sequence data
                continue

            pred = model.predict(features_scaled)[0]
            predictions[model_name] = pred

            # Calculate confidence based on prediction variance
            if hasattr(model, 'predict_proba'):
                # For tree-based models, use prediction variance
                tree_preds = []
                for tree in model.estimators_:
                    tree_preds.append(tree.predict(features_scaled)[0])
                confidences[model_name] = 1 / (1 + np.std(tree_preds))
            else:
                confidences[model_name] = 0.8  # Default confidence

        # Ensemble prediction (weighted average)
        if predictions:
            weights = {name: conf for name, conf in confidences.items()}
            total_weight = sum(weights.values())

            ensemble_pred = sum(pred * weights[name] for name, pred in predictions.items()) / total_weight
            avg_confidence = sum(confidences.values()) / len(confidences)

            return {
                'predicted_cost': ensemble_pred,
                'confidence': avg_confidence,
                'individual_predictions': predictions,
                'method': 'ensemble_ml'
            }
        else:
            return {
                'predicted_cost': current_data.get('current_opportunity_cost', 0),
                'confidence': 0.5,
                'method': 'fallback'
            }

    def predict_optimal_holding_time(self, current_data: Dict) -> Dict:
        """
        Predict optimal holding time for current position

        Args:
            current_data: Current position and market data

        Returns:
            dict: Optimal holding time prediction
        """
        if 'gradient_boosting' not in self.models:
            return {
                'optimal_hours': 4.0,  # Default
                'confidence': 0.5,
                'method': 'fallback'
            }

        features = self._extract_features(current_data)
        features_scaled = self.scalers['features'].transform([features])

        prediction = self.models['gradient_boosting'].predict(features_scaled)[0]

        # Ensure reasonable bounds
        optimal_hours = np.clip(prediction, 0.5, 24)

        return {
            'optimal_hours': optimal_hours,
            'confidence': 0.8,
            'method': 'ml_prediction'
        }

    def _extract_features(self, data: Dict) -> List[float]:
        """Extract feature vector from current data"""
        features = []

        for col in self.feature_columns:
            if col in data:
                features.append(data[col])
            else:
                features.append(0.0)  # Default value

        return features

    def update_model_with_feedback(self, prediction: Dict, actual_outcome: Dict):
        """Update model with actual outcomes for continuous learning"""
        # This would implement online learning
        # For now, just log the feedback
        print(f"📈 Model feedback received: predicted={prediction.get('predicted_cost', 0):.4f}, "
              f"actual={actual_outcome.get('actual_cost', 0):.4f}")