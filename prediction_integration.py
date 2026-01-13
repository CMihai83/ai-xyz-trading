"""
AI-XYZ Prediction Model Integration
Integrates the prediction service with the main trading system.

This module provides:
1. Scanner enhancement with prediction signals
2. Entry signal filtering based on predictions
3. Exit signal generation for open positions
4. Real-time prediction updates
"""

import logging
from typing import Dict, List, Optional, Callable
from datetime import datetime
import threading
import time

from prediction_service import PredictionService, get_prediction_service, TradingSignal, SignalStrength

logger = logging.getLogger(__name__)


class PredictionIntegration:
    """
    Integrates prediction model with AI-XYZ trading system.
    """

    def __init__(self, trading_system, min_confidence: float = 70,
                 min_risk_reward: float = 0.5, enable_exit_signals: bool = True):
        """
        Initialize prediction integration.

        Args:
            trading_system: AIXYZContinuousProfit instance
            min_confidence: Minimum prediction confidence for signals
            min_risk_reward: Minimum risk/reward ratio
            enable_exit_signals: Whether to generate exit signals
        """
        self.trading_system = trading_system
        self.min_confidence = min_confidence
        self.min_risk_reward = min_risk_reward
        self.enable_exit_signals = enable_exit_signals

        # Get prediction service with exchange
        self.prediction_service = get_prediction_service(trading_system.exchange)

        # Track positions for exit signals
        self.monitored_positions: Dict[str, Dict] = {}

        # Statistics
        self.signals_generated = 0
        self.signals_acted_on = 0
        self.exit_signals_generated = 0

        logger.info(f"PredictionIntegration initialized (min_conf={min_confidence}, min_rr={min_risk_reward})")

    def enhance_scanner_opportunities(self, opportunities: List[Dict]) -> List[Dict]:
        """
        Enhance scanner opportunities with prediction data.

        Args:
            opportunities: List of opportunities from scanner

        Returns:
            Enhanced opportunities with prediction alignment
        """
        enhanced = []

        for opp in opportunities:
            try:
                enhanced_opp = self.prediction_service.enhance_scanner_result(opp)

                # Log prediction alignment
                if enhanced_opp.get('prediction'):
                    pred = enhanced_opp['prediction']
                    aligned = enhanced_opp.get('prediction_aligned')

                    if aligned is True:
                        logger.debug(f"✓ {opp['symbol']}: Prediction ALIGNED "
                                   f"({pred['direction']} {pred['confidence']:.0f}%)")
                    elif aligned is False:
                        logger.debug(f"✗ {opp['symbol']}: Prediction CONFLICTS "
                                   f"({pred['direction']} {pred['confidence']:.0f}%)")

                enhanced.append(enhanced_opp)

            except Exception as e:
                logger.error(f"Error enhancing {opp.get('symbol', 'unknown')}: {e}")
                enhanced.append(opp)

        # Sort by adjusted score if available
        enhanced.sort(key=lambda x: x.get('adjusted_score', x.get('score', 0)), reverse=True)

        return enhanced

    def filter_entry_by_prediction(self, symbol: str, scanner_direction: str) -> Dict:
        """
        Filter entry signal based on prediction.

        Args:
            symbol: Trading symbol
            scanner_direction: Direction from scanner ('long' or 'short')

        Returns:
            Dict with approval status and reason
        """
        signal = self.prediction_service.predict(symbol)

        if signal is None:
            return {
                'approved': True,  # Allow if no prediction available
                'reason': 'No prediction available',
                'confidence': 0
            }

        prediction_direction = 'long' if signal.direction == 'BULLISH' else \
                              'short' if signal.direction == 'BEARISH' else 'neutral'

        # Check alignment
        if signal.direction == 'NEUTRAL':
            return {
                'approved': True,
                'reason': 'Prediction neutral - using scanner signal',
                'confidence': signal.confidence
            }

        # If scanner direction is neutral, use prediction direction
        if scanner_direction == 'neutral':
            return {
                'approved': True,
                'reason': f'Scanner neutral - using prediction: {signal.direction} ({signal.confidence:.0f}%)',
                'confidence': signal.confidence,
                'direction': prediction_direction  # Return prediction direction for use
            }

        if prediction_direction == scanner_direction:
            if signal.confidence >= self.min_confidence:
                self.signals_generated += 1
                return {
                    'approved': True,
                    'reason': f'Prediction ALIGNED: {signal.direction} ({signal.confidence:.0f}%)',
                    'confidence': signal.confidence,
                    'target': signal.target_60m,
                    'stop_loss': signal.stop_loss,
                    'risk_reward': signal.risk_reward,
                    'strength': signal.strength.value
                }
            else:
                return {
                    'approved': True,
                    'reason': f'Prediction aligned but low confidence ({signal.confidence:.0f}%)',
                    'confidence': signal.confidence
                }
        else:
            # Prediction conflicts with scanner
            if signal.confidence >= 80:
                return {
                    'approved': False,
                    'reason': f'Prediction CONFLICTS: {signal.direction} ({signal.confidence:.0f}%) - BLOCKED',
                    'confidence': signal.confidence
                }
            else:
                return {
                    'approved': True,
                    'reason': f'Prediction conflicts but low confidence ({signal.confidence:.0f}%) - allowing scanner',
                    'confidence': signal.confidence
                }

    def check_exit_signal(self, symbol: str, position_side: str,
                         entry_price: float, current_upnl_pct: float) -> Optional[Dict]:
        """
        Check if position should be exited based on prediction.

        Args:
            symbol: Trading symbol
            position_side: 'long' or 'short'
            entry_price: Position entry price
            current_upnl_pct: Current unrealized P&L percentage

        Returns:
            Exit signal dict or None
        """
        if not self.enable_exit_signals:
            return None

        exit_signal = self.prediction_service.get_exit_signal(
            symbol, position_side, entry_price
        )

        if exit_signal:
            self.exit_signals_generated += 1
            logger.info(f"🚨 EXIT SIGNAL for {symbol}: {exit_signal['reason']}")

        return exit_signal

    def get_prediction_for_position(self, symbol: str) -> Optional[Dict]:
        """
        Get current prediction for an open position.

        Args:
            symbol: Trading symbol

        Returns:
            Prediction data or None
        """
        signal = self.prediction_service.predict(symbol)
        if signal is None:
            return None

        return {
            'direction': signal.direction,
            'confidence': signal.confidence,
            'strength': signal.strength.value,
            'target_15m': signal.target_15m,
            'target_30m': signal.target_30m,
            'target_60m': signal.target_60m,
            'stop_loss': signal.stop_loss,
            'risk_reward': signal.risk_reward,
            'signals': signal.signals,
            'valid_until': signal.expires_at.isoformat()
        }

    def get_best_opportunities(self, symbols: List[str], top_n: int = 5) -> List[Dict]:
        """
        Get best trading opportunities based on predictions.

        Args:
            symbols: List of symbols to analyze
            top_n: Number of top opportunities to return

        Returns:
            List of best opportunities
        """
        predictions = self.prediction_service.predict_batch(symbols)

        opportunities = []
        for symbol, signal in predictions.items():
            if signal.direction == 'NEUTRAL':
                continue

            if signal.confidence < self.min_confidence:
                continue

            if signal.risk_reward < self.min_risk_reward:
                continue

            opportunities.append({
                'symbol': symbol,
                'direction': signal.direction,
                'confidence': signal.confidence,
                'strength': signal.strength.value,
                'entry': signal.entry_price,
                'target': signal.target_60m,
                'stop_loss': signal.stop_loss,
                'risk_reward': signal.risk_reward,
                'expected_return': abs(signal.target_60m - signal.entry_price) / signal.entry_price * 100
            })

        # Sort by confidence * risk_reward
        opportunities.sort(key=lambda x: x['confidence'] * x['risk_reward'], reverse=True)

        return opportunities[:top_n]

    def get_stats(self) -> Dict:
        """Get integration statistics"""
        service_stats = self.prediction_service.get_stats()
        return {
            **service_stats,
            'signals_generated': self.signals_generated,
            'signals_acted_on': self.signals_acted_on,
            'exit_signals_generated': self.exit_signals_generated,
            'min_confidence': self.min_confidence,
            'min_risk_reward': self.min_risk_reward,
            'exit_signals_enabled': self.enable_exit_signals
        }


def patch_trading_system_with_predictions(trading_system, min_confidence: float = 70):
    """
    Patch the trading system to include prediction integration.

    Args:
        trading_system: AIXYZContinuousProfit instance
        min_confidence: Minimum confidence threshold

    Returns:
        PredictionIntegration instance
    """
    integration = PredictionIntegration(
        trading_system,
        min_confidence=min_confidence,
        min_risk_reward=0.5,
        enable_exit_signals=True
    )

    # Store integration on trading system
    trading_system.prediction_integration = integration

    logger.info("Trading system patched with prediction integration")

    return integration


def create_prediction_enhanced_scanner(scanner, exchange):
    """
    Create a wrapper around the scanner that enhances results with predictions.

    Args:
        scanner: ScannerV4 instance
        exchange: CCXT exchange instance

    Returns:
        Enhanced scanner function
    """
    prediction_service = get_prediction_service(exchange)

    original_scan = scanner.scan_market

    def enhanced_scan(*args, **kwargs):
        # Get original results
        results = original_scan(*args, **kwargs)

        # Enhance with predictions
        enhanced_results = []
        for result in results:
            enhanced = prediction_service.enhance_scanner_result(result)
            enhanced_results.append(enhanced)

        # Re-sort by adjusted score
        enhanced_results.sort(
            key=lambda x: x.get('adjusted_score', x.get('score', 0)),
            reverse=True
        )

        return enhanced_results

    return enhanced_scan
