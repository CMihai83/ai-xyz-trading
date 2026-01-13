"""
AI-XYZ Prediction Service
Integrates the prediction model with the trading system.

Features:
- Multi-symbol prediction caching
- Integration with scanner for entry signals
- Exit signal generation
- Real-time prediction updates
"""

import numpy as np
import pandas as pd
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import logging

# Import the prediction model
from prediction_model_final import PredictionModelFinal, PredictionResult

logger = logging.getLogger(__name__)


class SignalStrength(Enum):
    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NEUTRAL = "neutral"


@dataclass
class TradingSignal:
    """Trading signal with prediction data"""
    symbol: str
    direction: str  # BULLISH, BEARISH, NEUTRAL
    confidence: float
    strength: SignalStrength
    entry_price: float
    target_15m: float
    target_30m: float
    target_60m: float
    stop_loss: float
    risk_reward: float
    signals: Dict
    timestamp: datetime = field(default_factory=datetime.now)
    expires_at: datetime = None

    def __post_init__(self):
        if self.expires_at is None:
            self.expires_at = self.timestamp + timedelta(minutes=15)

    def is_valid(self) -> bool:
        """Check if signal is still valid"""
        return datetime.now() < self.expires_at

    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'direction': self.direction,
            'confidence': self.confidence,
            'strength': self.strength.value,
            'entry_price': self.entry_price,
            'target_15m': self.target_15m,
            'target_30m': self.target_30m,
            'target_60m': self.target_60m,
            'stop_loss': self.stop_loss,
            'risk_reward': self.risk_reward,
            'signals': self.signals,
            'timestamp': self.timestamp.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'is_valid': self.is_valid()
        }


class PredictionService:
    """
    Service for generating and managing trading predictions.
    Integrates with the AI-XYZ trading system.
    """

    def __init__(self, exchange=None, cache_ttl: int = 60):
        """
        Initialize prediction service.

        Args:
            exchange: CCXT exchange instance
            cache_ttl: Cache time-to-live in seconds
        """
        self.exchange = exchange
        self.model = PredictionModelFinal()
        self.cache_ttl = cache_ttl
        self._cache: Dict[str, Dict] = {}
        self._lock = threading.Lock()

        # Performance tracking
        self.prediction_count = 0
        self.correct_predictions = 0
        self.last_predictions: Dict[str, TradingSignal] = {}

        logger.info("PredictionService initialized")

    def set_exchange(self, exchange):
        """Set exchange instance"""
        self.exchange = exchange

    def _get_cached(self, symbol: str) -> Optional[Dict]:
        """Get cached prediction if still valid"""
        with self._lock:
            if symbol in self._cache:
                cached = self._cache[symbol]
                if time.time() - cached['timestamp'] < self.cache_ttl:
                    return cached['data']
        return None

    def _set_cache(self, symbol: str, data: Dict):
        """Cache prediction data"""
        with self._lock:
            self._cache[symbol] = {
                'data': data,
                'timestamp': time.time()
            }

    def _fetch_ohlcv(self, symbol: str, timeframe: str = '5m', limit: int = 100) -> Optional[pd.DataFrame]:
        """Fetch OHLCV data for symbol"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
            return df
        except Exception as e:
            logger.error(f"Error fetching OHLCV for {symbol}: {e}")
            return None

    def _fetch_orderbook(self, symbol: str, limit: int = 20) -> Optional[Dict]:
        """Fetch order book for symbol"""
        try:
            return self.exchange.fetch_order_book(symbol, limit=limit)
        except Exception as e:
            logger.warning(f"Error fetching orderbook for {symbol}: {e}")
            return None

    def predict(self, symbol: str, use_cache: bool = True) -> Optional[TradingSignal]:
        """
        Generate prediction for a symbol.

        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')
            use_cache: Whether to use cached predictions

        Returns:
            TradingSignal or None if prediction fails
        """
        # Check cache
        if use_cache:
            cached = self._get_cached(symbol)
            if cached:
                return cached

        # Fetch data
        df = self._fetch_ohlcv(symbol)
        if df is None or len(df) < 50:
            return None

        orderbook = self._fetch_orderbook(symbol)

        # Run prediction
        try:
            result = self.model.predict(df, orderbook)
        except Exception as e:
            logger.error(f"Prediction error for {symbol}: {e}")
            return None

        current_price = df['c'].iloc[-1]

        # Calculate ATR for stop loss
        highs = df['h'].values
        lows = df['l'].values
        closes = df['c'].values
        tr = np.maximum(highs[1:] - lows[1:],
                       np.maximum(np.abs(highs[1:] - closes[:-1]),
                                 np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:])

        # Calculate stop loss
        if result.direction == 'BULLISH':
            stop_loss = current_price - atr * 2
        elif result.direction == 'BEARISH':
            stop_loss = current_price + atr * 2
        else:
            stop_loss = current_price

        # Calculate risk/reward
        if result.direction == 'BULLISH':
            risk = current_price - stop_loss
            reward = result.target_60m - current_price
        elif result.direction == 'BEARISH':
            risk = stop_loss - current_price
            reward = current_price - result.target_60m
        else:
            risk = atr
            reward = 0

        risk_reward = reward / risk if risk > 0 else 0

        # Determine signal strength
        if result.confidence >= 80 and abs(result.net_score) >= 2.5:
            strength = SignalStrength.STRONG
        elif result.confidence >= 65 and abs(result.net_score) >= 1.5:
            strength = SignalStrength.MODERATE
        elif result.confidence >= 50:
            strength = SignalStrength.WEAK
        else:
            strength = SignalStrength.NEUTRAL

        # Create trading signal
        signal = TradingSignal(
            symbol=symbol,
            direction=result.direction,
            confidence=result.confidence,
            strength=strength,
            entry_price=current_price,
            target_15m=result.target_15m,
            target_30m=result.target_30m,
            target_60m=result.target_60m,
            stop_loss=stop_loss,
            risk_reward=risk_reward,
            signals=result.signals
        )

        # Cache result
        self._set_cache(symbol, signal)
        self.last_predictions[symbol] = signal
        self.prediction_count += 1

        return signal

    def predict_batch(self, symbols: List[str]) -> Dict[str, TradingSignal]:
        """
        Generate predictions for multiple symbols.

        Args:
            symbols: List of trading symbols

        Returns:
            Dictionary of symbol -> TradingSignal
        """
        results = {}
        for symbol in symbols:
            signal = self.predict(symbol)
            if signal:
                results[symbol] = signal
        return results

    def get_entry_signal(self, symbol: str, min_confidence: float = 70,
                         min_rr: float = 0.5) -> Optional[Dict]:
        """
        Get entry signal for a symbol if conditions are met.

        Args:
            symbol: Trading symbol
            min_confidence: Minimum confidence threshold
            min_rr: Minimum risk/reward ratio

        Returns:
            Entry signal dict or None
        """
        signal = self.predict(symbol)
        if signal is None:
            return None

        # Check entry conditions
        if signal.direction == 'NEUTRAL':
            return None

        if signal.confidence < min_confidence:
            return None

        if signal.risk_reward < min_rr:
            return None

        return {
            'symbol': symbol,
            'side': 'buy' if signal.direction == 'BULLISH' else 'sell',
            'direction': signal.direction,
            'confidence': signal.confidence,
            'strength': signal.strength.value,
            'entry_price': signal.entry_price,
            'target': signal.target_60m,
            'stop_loss': signal.stop_loss,
            'risk_reward': signal.risk_reward,
            'reason': f"Prediction model: {signal.direction} with {signal.confidence:.0f}% confidence"
        }

    def get_exit_signal(self, symbol: str, position_side: str,
                        entry_price: float) -> Optional[Dict]:
        """
        Check if position should be exited based on prediction.

        Args:
            symbol: Trading symbol
            position_side: 'long' or 'short'
            entry_price: Position entry price

        Returns:
            Exit signal dict or None
        """
        signal = self.predict(symbol)
        if signal is None:
            return None

        current_price = signal.entry_price

        # Calculate current P&L
        if position_side == 'long':
            pnl_pct = (current_price - entry_price) / entry_price * 100
        else:
            pnl_pct = (entry_price - current_price) / entry_price * 100

        exit_signal = None
        reason = None

        # Check for reversal signal
        if position_side == 'long' and signal.direction == 'BEARISH' and signal.confidence >= 75:
            exit_signal = 'reversal'
            reason = f"Bearish reversal signal ({signal.confidence:.0f}% confidence)"

        elif position_side == 'short' and signal.direction == 'BULLISH' and signal.confidence >= 75:
            exit_signal = 'reversal'
            reason = f"Bullish reversal signal ({signal.confidence:.0f}% confidence)"

        # Check for target reached
        elif position_side == 'long' and pnl_pct >= 2.0 and signal.strength in [SignalStrength.WEAK, SignalStrength.NEUTRAL]:
            exit_signal = 'target'
            reason = f"Target reached ({pnl_pct:.2f}%) with weakening momentum"

        elif position_side == 'short' and pnl_pct >= 2.0 and signal.strength in [SignalStrength.WEAK, SignalStrength.NEUTRAL]:
            exit_signal = 'target'
            reason = f"Target reached ({pnl_pct:.2f}%) with weakening momentum"

        if exit_signal:
            return {
                'symbol': symbol,
                'signal': exit_signal,
                'reason': reason,
                'current_price': current_price,
                'pnl_pct': pnl_pct,
                'prediction_direction': signal.direction,
                'prediction_confidence': signal.confidence
            }

        return None

    def enhance_scanner_result(self, scanner_result: Dict) -> Dict:
        """
        Enhance scanner result with prediction data.

        Args:
            scanner_result: Result from ScannerV4

        Returns:
            Enhanced result with prediction
        """
        symbol = scanner_result.get('symbol')
        if not symbol:
            return scanner_result

        signal = self.predict(symbol)
        if signal is None:
            scanner_result['prediction'] = None
            return scanner_result

        # Add prediction data
        scanner_result['prediction'] = {
            'direction': signal.direction,
            'confidence': signal.confidence,
            'strength': signal.strength.value,
            'target_60m': signal.target_60m,
            'stop_loss': signal.stop_loss,
            'risk_reward': signal.risk_reward
        }

        # Adjust scanner score based on prediction alignment
        original_score = scanner_result.get('score', 0.5)
        scanner_direction = scanner_result.get('direction', 'neutral')

        # Boost score if prediction aligns with scanner
        if (scanner_direction == 'long' and signal.direction == 'BULLISH') or \
           (scanner_direction == 'short' and signal.direction == 'BEARISH'):
            alignment_boost = 0.1 * (signal.confidence / 100)
            scanner_result['adjusted_score'] = min(1.0, original_score + alignment_boost)
            scanner_result['prediction_aligned'] = True
        elif signal.direction != 'NEUTRAL':
            # Reduce score if prediction conflicts
            scanner_result['adjusted_score'] = max(0, original_score - 0.05)
            scanner_result['prediction_aligned'] = False
        else:
            scanner_result['adjusted_score'] = original_score
            scanner_result['prediction_aligned'] = None

        return scanner_result

    def get_market_overview(self, symbols: List[str]) -> Dict:
        """
        Get market overview with predictions for multiple symbols.

        Args:
            symbols: List of symbols to analyze

        Returns:
            Market overview dict
        """
        predictions = self.predict_batch(symbols)

        bullish = []
        bearish = []
        neutral = []

        for symbol, signal in predictions.items():
            entry = {
                'symbol': symbol,
                'confidence': signal.confidence,
                'strength': signal.strength.value,
                'target': signal.target_60m,
                'entry': signal.entry_price
            }

            if signal.direction == 'BULLISH':
                bullish.append(entry)
            elif signal.direction == 'BEARISH':
                bearish.append(entry)
            else:
                neutral.append(entry)

        # Sort by confidence
        bullish.sort(key=lambda x: x['confidence'], reverse=True)
        bearish.sort(key=lambda x: x['confidence'], reverse=True)

        return {
            'timestamp': datetime.now().isoformat(),
            'total_analyzed': len(symbols),
            'bullish_count': len(bullish),
            'bearish_count': len(bearish),
            'neutral_count': len(neutral),
            'market_bias': 'bullish' if len(bullish) > len(bearish) * 1.5 else
                          'bearish' if len(bearish) > len(bullish) * 1.5 else 'neutral',
            'top_bullish': bullish[:5],
            'top_bearish': bearish[:5],
            'neutral': neutral[:5]
        }

    def validate_prediction(self, symbol: str, predicted_direction: str,
                           actual_price: float, predicted_price: float) -> bool:
        """
        Validate a past prediction for accuracy tracking.

        Args:
            symbol: Trading symbol
            predicted_direction: BULLISH, BEARISH, NEUTRAL
            actual_price: Actual price at prediction expiry
            predicted_price: Price when prediction was made

        Returns:
            Whether prediction was correct
        """
        actual_change = (actual_price - predicted_price) / predicted_price * 100

        correct = False
        if predicted_direction == 'BULLISH' and actual_change > 0.2:
            correct = True
        elif predicted_direction == 'BEARISH' and actual_change < -0.2:
            correct = True
        elif predicted_direction == 'NEUTRAL' and abs(actual_change) < 0.5:
            correct = True

        if correct:
            self.correct_predictions += 1

        return correct

    def get_accuracy(self) -> float:
        """Get prediction accuracy"""
        if self.prediction_count == 0:
            return 0
        return self.correct_predictions / self.prediction_count * 100

    def get_stats(self) -> Dict:
        """Get service statistics"""
        return {
            'prediction_count': self.prediction_count,
            'correct_predictions': self.correct_predictions,
            'accuracy': self.get_accuracy(),
            'cache_size': len(self._cache),
            'active_predictions': len([s for s in self.last_predictions.values() if s.is_valid()])
        }


# Singleton instance
_prediction_service: Optional[PredictionService] = None


def get_prediction_service(exchange=None) -> PredictionService:
    """Get or create prediction service singleton"""
    global _prediction_service
    if _prediction_service is None:
        _prediction_service = PredictionService(exchange)
    elif exchange is not None:
        _prediction_service.set_exchange(exchange)
    return _prediction_service
