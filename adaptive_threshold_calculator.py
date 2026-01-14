#!/usr/bin/env python3
"""
Adaptive Threshold Calculator for AI-XYZ
Dynamically adjusts averaging and surplus dump thresholds based on market conditions
"""
import ccxt
import json
import numpy as np
from datetime import datetime, timedelta
import logging
from typing import Dict, Tuple
import os
from dotenv import load_dotenv

load_dotenv('/app/.env')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class AdaptiveThresholdCalculator:
    def __init__(self):
        self.api_key = os.getenv('BITGET_API_KEY')
        self.api_secret = os.getenv('BITGET_API_SECRET')
        self.api_passphrase = os.getenv('BITGET_API_PASSPHRASE', '')

        self.exchange = ccxt.bitget({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'password': self.api_passphrase,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        })

        # Load base configuration
        with open('/app/runtime_config.json', 'r') as f:
            self.base_config = json.load(f)

        # Market regimes
        self.REGIME_HIGH_VOLATILITY = 'HIGH_VOLATILITY'
        self.REGIME_TRENDING = 'TRENDING'
        self.REGIME_RANGING = 'RANGING'
        self.REGIME_NORMAL = 'NORMAL'

    def calculate_atr(self, symbol: str, timeframe: str = '1h', period: int = 14) -> float:
        """Calculate Average True Range"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=period + 1)

            if len(ohlcv) < period:
                return 0.0

            highs = [x[2] for x in ohlcv]
            lows = [x[3] for x in ohlcv]
            closes = [x[4] for x in ohlcv]

            # Calculate True Range
            true_ranges = []
            for i in range(1, len(ohlcv)):
                high_low = highs[i] - lows[i]
                high_close = abs(highs[i] - closes[i-1])
                low_close = abs(lows[i] - closes[i-1])
                true_range = max(high_low, high_close, low_close)
                true_ranges.append(true_range)

            # Calculate ATR
            atr = np.mean(true_ranges)
            current_price = closes[-1]
            atr_percent = (atr / current_price) * 100 if current_price > 0 else 0

            return atr_percent

        except Exception as e:
            logging.error(f"Error calculating ATR for {symbol}: {e}")
            return 2.0  # Default 2% ATR

    def calculate_volatility(self, symbol: str, timeframe: str = '5m', periods: int = 100) -> float:
        """Calculate recent price volatility"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=periods)

            if len(ohlcv) < 2:
                return 10.0  # Default 10% volatility

            closes = [x[4] for x in ohlcv]
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

            # Calculate standard deviation of returns
            volatility = np.std(returns) * np.sqrt(len(returns)) * 100

            return volatility

        except Exception as e:
            logging.error(f"Error calculating volatility for {symbol}: {e}")
            return 10.0  # Default 10% volatility

    def detect_market_regime(self, symbol: str) -> str:
        """Detect current market regime for the symbol"""
        try:
            # Get multiple timeframe data
            ohlcv_5m = self.exchange.fetch_ohlcv(symbol, '5m', limit=100)
            ohlcv_1h = self.exchange.fetch_ohlcv(symbol, '1h', limit=24)

            if len(ohlcv_5m) < 50 or len(ohlcv_1h) < 10:
                return self.REGIME_NORMAL

            # Calculate short-term volatility
            closes_5m = [x[4] for x in ohlcv_5m]
            returns_5m = [(closes_5m[i] - closes_5m[i-1]) / closes_5m[i-1] for i in range(1, len(closes_5m))]
            volatility_5m = np.std(returns_5m) * 100

            # Calculate trend strength
            closes_1h = [x[4] for x in ohlcv_1h]
            sma_short = np.mean(closes_1h[-10:])
            sma_long = np.mean(closes_1h)
            trend_strength = abs((sma_short - sma_long) / sma_long) * 100

            # Classify regime
            if volatility_5m > 2.0:  # High short-term volatility
                return self.REGIME_HIGH_VOLATILITY
            elif trend_strength > 5.0:  # Strong trend
                return self.REGIME_TRENDING
            elif volatility_5m < 0.5 and trend_strength < 2.0:  # Low volatility, no trend
                return self.REGIME_RANGING
            else:
                return self.REGIME_NORMAL

        except Exception as e:
            logging.error(f"Error detecting market regime for {symbol}: {e}")
            return self.REGIME_NORMAL

    def calculate_adaptive_thresholds(self, symbol: str) -> Dict:
        """Calculate adaptive thresholds based on market conditions"""
        try:
            # Get market metrics
            atr = self.calculate_atr(symbol)
            volatility = self.calculate_volatility(symbol)
            regime = self.detect_market_regime(symbol)

            logging.info(f"{symbol} - ATR: {atr:.2f}%, Volatility: {volatility:.2f}%, Regime: {regime}")

            # Base thresholds from config
            base_averaging = self.base_config['zone_thresholds']['averaging_start']

            # Adaptive averaging threshold
            if regime == self.REGIME_HIGH_VOLATILITY:
                # More aggressive averaging in high volatility
                averaging_start = max(-0.20, base_averaging * (1 + volatility/100))
                averaging_multiplier = 0.8  # Tighter steps
            elif regime == self.REGIME_TRENDING:
                # Moderate averaging in trends
                averaging_start = -0.35
                averaging_multiplier = 1.0
            elif regime == self.REGIME_RANGING:
                # Conservative in ranging markets
                averaging_start = -0.45
                averaging_multiplier = 1.2  # Wider steps
            else:  # NORMAL
                averaging_start = base_averaging
                averaging_multiplier = 1.0

            # Adjust based on ATR
            if atr > 5.0:  # Very high ATR
                averaging_start = max(-0.35, averaging_start)  # Updated from -0.25
            elif atr < 1.0:  # Very low ATR
                averaging_start = min(-0.50, averaging_start)

            # Calculate averaging steps
            steps = []
            current_threshold = averaging_start
            for i in range(5):
                steps.append(current_threshold)
                current_threshold = current_threshold * (1.2 * averaging_multiplier)

            # Adaptive surplus dump thresholds
            if regime == self.REGIME_HIGH_VOLATILITY:
                # Quicker profit taking in volatile markets
                surplus_dump_85 = 0.80  # Take profits at 80% of peak
                surplus_dump_50 = 0.45  # And at 45% of peak
            elif regime == self.REGIME_TRENDING:
                # Let profits run in trends
                surplus_dump_85 = 0.90  # Wait for 90% of peak
                surplus_dump_50 = 0.60  # And 60% of peak
            else:
                # Standard thresholds
                surplus_dump_85 = 0.85
                surplus_dump_50 = 0.50

            # Stop loss adjustment
            if volatility > 20:
                stop_loss = -0.50  # Tighter stop in extreme volatility
            else:
                stop_loss = -0.70  # Standard stop loss

            adaptive_thresholds = {
                'symbol': symbol,
                'regime': regime,
                'atr_percent': atr,
                'volatility_percent': volatility,
                'averaging_start': averaging_start,
                'averaging_steps': steps,
                'surplus_dump_85': surplus_dump_85,
                'surplus_dump_50': surplus_dump_50,
                'stop_loss': stop_loss,
                'averaging_multiplier': averaging_multiplier,
                'timestamp': datetime.now().isoformat()
            }

            return adaptive_thresholds

        except Exception as e:
            logging.error(f"Error calculating adaptive thresholds for {symbol}: {e}")
            # Return base config on error
            return {
                'symbol': symbol,
                'regime': 'UNKNOWN',
                'averaging_start': -0.42,
                'averaging_steps': [-0.42, -0.50, -0.60, -0.70, -0.80],
                'surplus_dump_85': 0.85,
                'surplus_dump_50': 0.50,
                'stop_loss': -0.70,
                'error': str(e)
            }

    def update_position_thresholds(self):
        """Update thresholds for all active positions"""
        try:
            # Read current position state
            with open('/app/position_state.json', 'r') as f:
                position_state = json.load(f)

            # Calculate adaptive thresholds for each position
            adaptive_configs = {}
            for symbol in position_state.get('active_positions', {}).keys():
                thresholds = self.calculate_adaptive_thresholds(symbol)
                adaptive_configs[symbol] = thresholds

                logging.info(f"Updated thresholds for {symbol}:")
                logging.info(f"  Regime: {thresholds['regime']}")
                logging.info(f"  Averaging Start: {thresholds['averaging_start']*100:.1f}%")
                logging.info(f"  Stop Loss: {thresholds['stop_loss']*100:.1f}%")

            # Save adaptive configurations
            with open('/app/adaptive_thresholds.json', 'w') as f:
                json.dump(adaptive_configs, f, indent=2)

            logging.info(f"Updated adaptive thresholds for {len(adaptive_configs)} positions")
            return adaptive_configs

        except Exception as e:
            logging.error(f"Error updating position thresholds: {e}")
            return {}

    def get_optimal_entry_timing(self, symbol: str) -> Dict:
        """Determine optimal entry timing based on market conditions"""
        regime = self.detect_market_regime(symbol)
        volatility = self.calculate_volatility(symbol)

        timing = {
            'symbol': symbol,
            'regime': regime,
            'volatility': volatility,
            'entry_recommendation': 'WAIT',
            'confidence': 0.5
        }

        if regime == self.REGIME_RANGING:
            timing['entry_recommendation'] = 'GOOD'
            timing['confidence'] = 0.8
            timing['reason'] = 'Market is ranging, good for mean reversion'
        elif regime == self.REGIME_HIGH_VOLATILITY and volatility < 30:
            timing['entry_recommendation'] = 'MODERATE'
            timing['confidence'] = 0.6
            timing['reason'] = 'High volatility provides opportunities'
        elif regime == self.REGIME_TRENDING:
            timing['entry_recommendation'] = 'WAIT'
            timing['confidence'] = 0.3
            timing['reason'] = 'Strong trend, wait for pullback'
        else:
            timing['entry_recommendation'] = 'MODERATE'
            timing['confidence'] = 0.5
            timing['reason'] = 'Normal market conditions'

        return timing

def main():
    """Run adaptive threshold calculation"""
    calculator = AdaptiveThresholdCalculator()

    print("="*60)
    print("ADAPTIVE THRESHOLD CALCULATOR")
    print("="*60)

    # Update thresholds for active positions
    configs = calculator.update_position_thresholds()

    if configs:
        print("\nAdaptive Thresholds Updated:")
        for symbol, config in configs.items():
            print(f"\n{symbol}:")
            print(f"  Market Regime: {config.get('regime', 'N/A')}")
            print(f"  Volatility: {config.get('volatility_percent', 0):.2f}%")
            print(f"  ATR: {config.get('atr_percent', 0):.2f}%")
            print(f"  Averaging Start: {config.get('averaging_start', -0.42)*100:.1f}%")
            print(f"  Stop Loss: {config.get('stop_loss', -0.70)*100:.1f}%")

    # Test with a sample symbol
    print("\n" + "="*60)
    print("Testing with BTC/USDT:USDT...")
    btc_thresholds = calculator.calculate_adaptive_thresholds('BTC/USDT:USDT')
    print(json.dumps(btc_thresholds, indent=2))

    # Get entry timing recommendation
    timing = calculator.get_optimal_entry_timing('BTC/USDT:USDT')
    print(f"\nEntry Timing: {timing['entry_recommendation']} (Confidence: {timing['confidence']*100:.0f}%)")
    print(f"Reason: {timing.get('reason', 'N/A')}")

if __name__ == "__main__":
    main()