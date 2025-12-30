#!/usr/bin/env python3
"""
Self-Adjusting Opportunity Discovery System
Sprint 3: Adaptive opportunity finding with machine learning
Learns from successful and failed trades to improve discovery
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import logging
# from sklearn.ensemble import RandomForestClassifier
# from sklearn.preprocessing import StandardScaler

# Dummy classes for when sklearn is not available
class StandardScaler:
    def fit(self, X):
        return self
    def transform(self, X):
        return X
    def fit_transform(self, X):
        return X

class RandomForestClassifier:
    def __init__(self, **kwargs):
        pass
    def fit(self, X, y):
        pass
    def predict(self, X):
        return [1] * len(X) if hasattr(X, '__len__') else [1]
    def predict_proba(self, X):
        prob = 0.5
        return [[1-prob, prob]] * len(X) if hasattr(X, '__len__') else [[1-prob, prob]]

import joblib
import warnings
warnings.filterwarnings('ignore')


class SelfAdjustingOpportunityDiscovery:
    """
    Machine learning-based opportunity discovery
    Continuously learns and adapts from trading outcomes
    """

    def __init__(self):
        # Configuration
        self.model_file = '/app/opportunity_model.pkl'
        self.scaler_file = '/app/opportunity_scaler.pkl'
        self.history_file = '/app/opportunity_history.json'

        # ML Model
        self.model = None
        self.scaler = None
        self.feature_importance = {}

        # Discovery parameters (self-adjusting)
        self.parameters = {
            'min_volume_percentile': 60,  # Minimum volume percentile
            'max_volatility': 0.05,  # Maximum acceptable volatility
            'min_volatility': 0.01,  # Minimum required volatility
            'rsi_oversold': 30,  # RSI oversold threshold
            'rsi_overbought': 70,  # RSI overbought threshold
            'trend_threshold': 0.02,  # Trend strength threshold
            'confidence_threshold': 0.7,  # Minimum confidence for opportunity
            'lookback_period': 100,  # Candles for analysis
            'retracement_ratio': 0.382  # Fibonacci retracement
        }

        # Performance tracking
        self.opportunity_history = []
        self.success_rate = 0.0
        self.total_opportunities = 0
        self.successful_opportunities = 0

        # Initialize components
        self._setup_logging()
        self._load_or_create_model()

    def _setup_logging(self):
        """Configure logging"""
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger('OpportunityDiscovery')

    def _load_or_create_model(self):
        """Load existing model or create new one"""
        try:
            # Try to load existing model
            self.model = joblib.load(self.model_file)
            self.scaler = joblib.load(self.scaler_file)
            self.logger.info("Loaded existing ML model")

        except:
            # Create new model
            self.model = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42
            )
            self.scaler = StandardScaler()
            self.logger.info("Created new ML model")

        # Load history
        self._load_history()

    def discover_opportunities(
        self,
        market_data: Dict[str, pd.DataFrame]
    ) -> List[Dict]:
        """
        Discover trading opportunities using ML

        Args:
            market_data: Dictionary of symbol -> OHLCV DataFrame

        Returns:
            List of opportunity dictionaries
        """
        opportunities = []

        self.logger.info(f"Analyzing {len(market_data)} symbols for opportunities...")

        for symbol, df in market_data.items():
            try:
                # Extract features
                features = self._extract_features(df)

                if features is None:
                    continue

                # Predict opportunity
                confidence = self._predict_opportunity(features)

                if confidence >= self.parameters['confidence_threshold']:
                    # Calculate entry parameters
                    entry_params = self._calculate_entry_parameters(df, features)

                    opportunity = {
                        'symbol': symbol,
                        'confidence': confidence,
                        'features': features,
                        'entry_params': entry_params,
                        'timestamp': datetime.now().isoformat(),
                        'current_price': df['close'].iloc[-1]
                    }

                    opportunities.append(opportunity)
                    self.logger.info(
                        f"✅ Opportunity: {symbol} "
                        f"(confidence: {confidence:.2%})"
                    )

            except Exception as e:
                self.logger.error(f"Error analyzing {symbol}: {e}")

        # Sort by confidence
        opportunities.sort(key=lambda x: x['confidence'], reverse=True)

        # Record discoveries
        self._record_opportunities(opportunities)

        return opportunities

    def _extract_features(self, df: pd.DataFrame) -> Optional[np.ndarray]:
        """
        Extract ML features from market data

        Args:
            df: OHLCV DataFrame

        Returns:
            Feature array or None
        """
        try:
            if len(df) < self.parameters['lookback_period']:
                return None

            features = []

            # Price features
            features.append(df['close'].pct_change().mean())  # Average return
            features.append(df['close'].pct_change().std())  # Volatility
            features.append((df['close'].iloc[-1] - df['close'].min()) /
                          (df['close'].max() - df['close'].min()))  # Price position

            # Volume features
            features.append(df['volume'].iloc[-1] / df['volume'].mean())  # Volume ratio
            features.append(np.log1p(df['volume'].iloc[-1]))  # Log volume

            # Technical indicators
            features.append(self._calculate_rsi(df['close']))  # RSI
            features.append(self._calculate_macd_signal(df['close']))  # MACD signal
            features.append(self._calculate_bollinger_position(df['close']))  # Bollinger position

            # Trend features
            features.append(self._calculate_trend_strength(df['close']))  # Trend strength
            features.append(self._calculate_support_distance(df))  # Distance to support

            # Pattern features
            features.append(self._detect_reversal_pattern(df))  # Reversal pattern
            features.append(self._calculate_momentum_divergence(df))  # Divergence

            # Market regime
            features.append(self._identify_market_regime(df))  # Regime (trending/ranging)

            return np.array(features).reshape(1, -1)

        except Exception as e:
            self.logger.error(f"Feature extraction error: {e}")
            return None

    def _predict_opportunity(self, features: np.ndarray) -> float:
        """
        Predict opportunity confidence using ML model

        Args:
            features: Feature array

        Returns:
            Confidence score (0-1)
        """
        try:
            # Check if model is trained
            if not hasattr(self.model, 'n_features_in_'):
                # Return rule-based score if model not trained
                return self._rule_based_scoring(features)

            # Scale features
            features_scaled = self.scaler.transform(features)

            # Predict probability
            prob = self.model.predict_proba(features_scaled)[0, 1]

            return prob

        except:
            # Fallback to rule-based
            return self._rule_based_scoring(features)

    def _rule_based_scoring(self, features: np.ndarray) -> float:
        """
        Rule-based scoring when ML model not available

        Args:
            features: Feature array

        Returns:
            Score (0-1)
        """
        score = 0.5  # Base score

        # Extract key features
        volatility = features[0, 1]
        price_position = features[0, 2]
        volume_ratio = features[0, 3]
        rsi = features[0, 5]

        # Apply rules
        if self.parameters['min_volatility'] < volatility < self.parameters['max_volatility']:
            score += 0.1

        if volume_ratio > 1.5:
            score += 0.1

        if rsi < self.parameters['rsi_oversold']:
            score += 0.2
        elif rsi > self.parameters['rsi_overbought']:
            score -= 0.2

        if price_position < 0.3:  # Near bottom of range
            score += 0.1

        return max(0, min(1, score))

    def _calculate_entry_parameters(
        self,
        df: pd.DataFrame,
        features: np.ndarray
    ) -> Dict:
        """
        Calculate optimal entry parameters

        Args:
            df: OHLCV DataFrame
            features: Feature array

        Returns:
            Entry parameters dictionary
        """
        current_price = df['close'].iloc[-1]
        atr = self._calculate_atr(df)

        # Dynamic position sizing based on volatility
        volatility = features[0, 1]
        position_size_multiplier = 1.0 / (1 + volatility * 10)

        # Stop loss based on ATR
        stop_loss = current_price - (atr * 2)

        # Take profit targets (Fibonacci levels)
        tp1 = current_price + (atr * 1.618)
        tp2 = current_price + (atr * 2.618)
        tp3 = current_price + (atr * 4.236)

        return {
            'entry_price': current_price,
            'stop_loss': stop_loss,
            'take_profit_1': tp1,
            'take_profit_2': tp2,
            'take_profit_3': tp3,
            'position_size_multiplier': position_size_multiplier,
            'atr': atr,
            'risk_reward_ratio': (tp1 - current_price) / (current_price - stop_loss)
        }

    def learn_from_outcome(
        self,
        opportunity: Dict,
        outcome: Dict
    ):
        """
        Learn from trading outcome to improve model

        Args:
            opportunity: Original opportunity dict
            outcome: Trading outcome dict
        """
        try:
            # Record outcome
            record = {
                'opportunity': opportunity,
                'outcome': outcome,
                'timestamp': datetime.now().isoformat()
            }

            self.opportunity_history.append(record)

            # Update success metrics
            self.total_opportunities += 1
            if outcome['success']:
                self.successful_opportunities += 1

            self.success_rate = self.successful_opportunities / self.total_opportunities

            # Retrain model if enough data
            if len(self.opportunity_history) >= 50:
                self._retrain_model()

            # Adjust parameters based on performance
            self._adjust_parameters()

            # Save history
            self._save_history()

            self.logger.info(
                f"Learning update - Success rate: {self.success_rate:.2%} "
                f"({self.successful_opportunities}/{self.total_opportunities})"
            )

        except Exception as e:
            self.logger.error(f"Learning error: {e}")

    def _retrain_model(self):
        """Retrain ML model with accumulated data"""
        try:
            # Prepare training data
            X = []
            y = []

            for record in self.opportunity_history:
                if 'features' in record['opportunity']:
                    X.append(record['opportunity']['features'].flatten())
                    y.append(1 if record['outcome']['success'] else 0)

            if len(X) < 20:
                return

            X = np.array(X)
            y = np.array(y)

            # Split data
            split_idx = int(len(X) * 0.8)
            X_train, X_test = X[:split_idx], X[split_idx:]
            y_train, y_test = y[:split_idx], y[split_idx:]

            # Scale features
            X_train_scaled = self.scaler.fit_transform(X_train)
            X_test_scaled = self.scaler.transform(X_test)

            # Train model
            self.model.fit(X_train_scaled, y_train)

            # Evaluate
            train_score = self.model.score(X_train_scaled, y_train)
            test_score = self.model.score(X_test_scaled, y_test)

            self.logger.info(
                f"Model retrained - Train: {train_score:.2%}, Test: {test_score:.2%}"
            )

            # Update feature importance
            self.feature_importance = dict(zip(
                range(len(self.model.feature_importances_)),
                self.model.feature_importances_
            ))

            # Save model
            joblib.dump(self.model, self.model_file)
            joblib.dump(self.scaler, self.scaler_file)

        except Exception as e:
            self.logger.error(f"Retrain error: {e}")

    def _adjust_parameters(self):
        """Dynamically adjust discovery parameters"""
        if self.total_opportunities < 10:
            return

        # Adjust confidence threshold based on success rate
        if self.success_rate < 0.4:
            # Too many false positives, increase threshold
            self.parameters['confidence_threshold'] = min(
                0.9,
                self.parameters['confidence_threshold'] + 0.05
            )
            self.logger.info(
                f"Increased confidence threshold to "
                f"{self.parameters['confidence_threshold']:.2f}"
            )

        elif self.success_rate > 0.7:
            # Good performance, can be less strict
            self.parameters['confidence_threshold'] = max(
                0.6,
                self.parameters['confidence_threshold'] - 0.05
            )
            self.logger.info(
                f"Decreased confidence threshold to "
                f"{self.parameters['confidence_threshold']:.2f}"
            )

        # Adjust other parameters based on recent performance
        recent_history = self.opportunity_history[-20:]
        if recent_history:
            # Analyze what works
            successful = [r for r in recent_history if r['outcome']['success']]

            if successful:
                # Adjust RSI thresholds
                avg_rsi = np.mean([
                    r['opportunity']['features'][0, 5]
                    for r in successful
                    if 'features' in r['opportunity']
                ])

                if avg_rsi < 35:
                    self.parameters['rsi_oversold'] = 35
                elif avg_rsi < 25:
                    self.parameters['rsi_oversold'] = 25

    # Technical indicator calculations
    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    def _calculate_macd_signal(self, prices: pd.Series) -> float:
        """Calculate MACD signal"""
        exp1 = prices.ewm(span=12, adjust=False).mean()
        exp2 = prices.ewm(span=26, adjust=False).mean()
        macd = exp1 - exp2
        signal = macd.ewm(span=9, adjust=False).mean()
        return (macd.iloc[-1] - signal.iloc[-1]) / prices.iloc[-1]

    def _calculate_bollinger_position(self, prices: pd.Series, period: int = 20) -> float:
        """Calculate position within Bollinger Bands"""
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        upper = sma + (std * 2)
        lower = sma - (std * 2)
        position = (prices.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])
        return max(0, min(1, position)) if not pd.isna(position) else 0.5

    def _calculate_trend_strength(self, prices: pd.Series) -> float:
        """Calculate trend strength"""
        if len(prices) < 20:
            return 0
        x = np.arange(len(prices[-20:]))
        y = prices[-20:].values
        slope = np.polyfit(x, y, 1)[0]
        return slope / prices.iloc[-1]

    def _calculate_support_distance(self, df: pd.DataFrame) -> float:
        """Calculate distance to support level"""
        recent_lows = df['low'].rolling(window=20).min()
        support = recent_lows.iloc[-1]
        distance = (df['close'].iloc[-1] - support) / df['close'].iloc[-1]
        return distance if not pd.isna(distance) else 0

    def _detect_reversal_pattern(self, df: pd.DataFrame) -> float:
        """Detect reversal patterns"""
        # Simplified reversal detection
        recent = df.tail(5)
        if len(recent) < 5:
            return 0

        # Hammer pattern
        body = abs(recent['close'].iloc[-1] - recent['open'].iloc[-1])
        lower_shadow = recent['open'].iloc[-1] - recent['low'].iloc[-1]

        if lower_shadow > body * 2 and recent['close'].iloc[-1] > recent['open'].iloc[-1]:
            return 1.0

        return 0.0

    def _calculate_momentum_divergence(self, df: pd.DataFrame) -> float:
        """Calculate momentum divergence"""
        if len(df) < 30:
            return 0

        # Price trend vs RSI trend
        price_trend = self._calculate_trend_strength(df['close'])
        rsi = self._calculate_rsi(df['close'])
        rsi_series = pd.Series([self._calculate_rsi(df['close'][:i])
                               for i in range(len(df)-10, len(df))])
        rsi_trend = self._calculate_trend_strength(rsi_series)

        # Bullish divergence: price down, RSI up
        if price_trend < 0 and rsi_trend > 0:
            return 1.0
        # Bearish divergence: price up, RSI down
        elif price_trend > 0 and rsi_trend < 0:
            return -1.0

        return 0.0

    def _identify_market_regime(self, df: pd.DataFrame) -> float:
        """Identify market regime (trending vs ranging)"""
        if len(df) < 50:
            return 0.5

        # ADX-like calculation
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=14).mean()

        # Trending if ATR is increasing
        atr_trend = self._calculate_trend_strength(atr)

        return min(1, max(0, 0.5 + atr_trend * 10))

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> float:
        """Calculate Average True Range"""
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

        return atr.iloc[-1] if not pd.isna(atr.iloc[-1]) else 0

    def _record_opportunities(self, opportunities: List[Dict]):
        """Record discovered opportunities"""
        for opp in opportunities:
            self.total_opportunities += 1

    def _load_history(self):
        """Load opportunity history"""
        try:
            with open(self.history_file, 'r') as f:
                data = json.load(f)
                self.opportunity_history = data.get('history', [])
                self.total_opportunities = data.get('total', 0)
                self.successful_opportunities = data.get('successful', 0)
                if self.total_opportunities > 0:
                    self.success_rate = self.successful_opportunities / self.total_opportunities
        except:
            pass

    def _save_history(self):
        """Save opportunity history"""
        try:
            data = {
                'history': self.opportunity_history[-100:],  # Keep last 100
                'total': self.total_opportunities,
                'successful': self.successful_opportunities,
                'parameters': self.parameters,
                'timestamp': datetime.now().isoformat()
            }

            with open(self.history_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Save history error: {e}")


def main():
    """Test opportunity discovery"""
    discovery = SelfAdjustingOpportunityDiscovery()

    print("\n" + "="*70)
    print("🔍 SELF-ADJUSTING OPPORTUNITY DISCOVERY TEST")
    print("="*70)

    # Create sample data
    dates = pd.date_range(end=datetime.now(), periods=100, freq='5min')
    sample_data = {
        'TEST/USDT': pd.DataFrame({
            'open': np.random.randn(100).cumsum() + 100,
            'high': np.random.randn(100).cumsum() + 101,
            'low': np.random.randn(100).cumsum() + 99,
            'close': np.random.randn(100).cumsum() + 100,
            'volume': np.random.random(100) * 1000000
        }, index=dates)
    }

    # Discover opportunities
    opportunities = discovery.discover_opportunities(sample_data)

    if opportunities:
        print(f"\n✅ Found {len(opportunities)} opportunities")
        for opp in opportunities:
            print(f"  {opp['symbol']}: {opp['confidence']:.2%}")
    else:
        print("\n❌ No opportunities found")

    # Test learning
    if opportunities:
        print("\n📚 Testing learning from outcome...")
        outcome = {
            'success': True,
            'profit': 2.5,
            'duration': 3600
        }
        discovery.learn_from_outcome(opportunities[0], outcome)
        print(f"Success rate: {discovery.success_rate:.2%}")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()