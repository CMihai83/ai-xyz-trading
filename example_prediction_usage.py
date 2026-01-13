"""
Example: How to use the Prediction Model in AI-XYZ Trading System

This script demonstrates the integration points for the prediction model.
"""

import sys
sys.path.insert(0, '/root/ai_xyz')

from prediction_service import get_prediction_service, PredictionService
from prediction_integration import (
    PredictionIntegration,
    patch_trading_system_with_predictions,
    create_prediction_enhanced_scanner
)
from prediction_model_final import PredictionModelFinal


# =============================================================================
# USAGE 1: Direct Model Usage
# =============================================================================
def example_direct_model():
    """Use the prediction model directly"""
    import ccxt
    import pandas as pd
    from dotenv import dotenv_values

    env = dotenv_values('/root/ai_xyz/.env')
    exchange = ccxt.bitget({
        'apiKey': env.get('BITGET_API_KEY'),
        'secret': env.get('BITGET_API_SECRET'),
        'password': env.get('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })

    # Fetch data
    ohlcv = exchange.fetch_ohlcv('API3/USDT:USDT', '5m', limit=100)
    df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    orderbook = exchange.fetch_order_book('API3/USDT:USDT', limit=20)

    # Create model and predict
    model = PredictionModelFinal()
    result = model.predict(df, orderbook)

    print(f"Direction: {result.direction}")
    print(f"Confidence: {result.confidence}%")
    print(f"Target 60m: ${result.target_60m:.4f}")
    print(f"Signals: {result.signals}")


# =============================================================================
# USAGE 2: Prediction Service (Recommended)
# =============================================================================
def example_prediction_service():
    """Use the prediction service for caching and batch predictions"""
    import ccxt
    from dotenv import dotenv_values

    env = dotenv_values('/root/ai_xyz/.env')
    exchange = ccxt.bitget({
        'apiKey': env.get('BITGET_API_KEY'),
        'secret': env.get('BITGET_API_SECRET'),
        'password': env.get('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })

    # Get singleton service
    service = get_prediction_service(exchange)

    # Single prediction (with automatic caching)
    signal = service.predict('BTC/USDT:USDT')
    print(f"BTC: {signal.direction} ({signal.confidence}%)")

    # Batch predictions
    symbols = ['ETH/USDT:USDT', 'SOL/USDT:USDT', 'API3/USDT:USDT']
    predictions = service.predict_batch(symbols)
    for sym, pred in predictions.items():
        print(f"{sym}: {pred.direction}")

    # Get entry signal
    entry = service.get_entry_signal('API3/USDT:USDT')
    if entry:
        print(f"Entry signal: {entry['side']} at ${entry['entry_price']:.4f}")

    # Check exit for open position
    exit_sig = service.get_exit_signal('API3/USDT:USDT', 'long', 0.50)
    if exit_sig:
        print(f"Exit signal: {exit_sig['reason']}")


# =============================================================================
# USAGE 3: Integration with Trading System
# =============================================================================
def example_trading_integration():
    """
    How to integrate with AIXYZContinuousProfit trading system.

    Add this to aixyz_continuous_profit_system.py:
    """

    # In __init__ method:
    '''
    from prediction_integration import patch_trading_system_with_predictions

    # After initializing exchange
    self.prediction_integration = patch_trading_system_with_predictions(
        self,
        min_confidence=70
    )
    '''

    # When processing scanner opportunities:
    '''
    def process_opportunities(self, opportunities):
        # Enhance scanner results with predictions
        enhanced = self.prediction_integration.enhance_scanner_opportunities(opportunities)

        for opp in enhanced:
            symbol = opp['symbol']
            scanner_direction = opp['direction']

            # Check if prediction approves entry
            approval = self.prediction_integration.filter_entry_by_prediction(
                symbol, scanner_direction
            )

            if not approval['approved']:
                print(f"Entry blocked for {symbol}: {approval['reason']}")
                continue

            # Proceed with entry
            # ... existing entry logic ...
    '''

    # When managing open positions:
    '''
    def check_position_exits(self, symbol, position_side, entry_price, current_upnl):
        # Check for prediction-based exit
        exit_signal = self.prediction_integration.check_exit_signal(
            symbol, position_side, entry_price, current_upnl
        )

        if exit_signal:
            print(f"Exit signal for {symbol}: {exit_signal['reason']}")
            return True
        return False
    '''

    print("See code comments for integration examples")


# =============================================================================
# USAGE 4: Enhanced Scanner
# =============================================================================
def example_enhanced_scanner():
    """Enhance scanner with predictions"""
    import ccxt
    from dotenv import dotenv_values
    from scanner_v4 import ScannerV4
    from prediction_integration import create_prediction_enhanced_scanner

    env = dotenv_values('/root/ai_xyz/.env')
    exchange = ccxt.bitget({
        'apiKey': env.get('BITGET_API_KEY'),
        'secret': env.get('BITGET_API_SECRET'),
        'password': env.get('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })

    # Create scanner
    scanner = ScannerV4(exchange=exchange)

    # Wrap with prediction enhancement
    enhanced_scan = create_prediction_enhanced_scanner(scanner, exchange)

    # Now enhanced_scan() returns results with prediction alignment
    # results = enhanced_scan(max_deep_analysis=20)
    print("Scanner wrapped with prediction enhancement")


# =============================================================================
# USAGE 5: API Endpoint
# =============================================================================
def example_api_usage():
    """Using the prediction API"""
    print("""
    Start the API:
    $ python prediction_api.py

    Or via Docker:
    $ docker compose up -d prediction_service

    API Endpoints:

    GET /predict/{symbol}
        curl http://localhost:8009/predict/API3USDT

    GET /predict/batch?symbols=BTCUSDT,ETHUSDT,SOLUSDT
        curl "http://localhost:8009/predict/batch?symbols=BTCUSDT,ETHUSDT"

    GET /market/overview
        curl http://localhost:8009/market/overview

    POST /entry/signal
        curl -X POST http://localhost:8009/entry/signal \\
            -H "Content-Type: application/json" \\
            -d '{"symbol": "API3USDT", "scanner_direction": "short"}'

    POST /exit/signal
        curl -X POST http://localhost:8009/exit/signal \\
            -H "Content-Type: application/json" \\
            -d '{"symbol": "API3USDT", "position_side": "long", "entry_price": 0.50}'

    GET /stats
        curl http://localhost:8009/stats
    """)


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("   AI-XYZ PREDICTION MODEL INTEGRATION EXAMPLES")
    print("=" * 70)

    print("\n[1] Direct Model Usage")
    print("-" * 40)
    example_direct_model()

    print("\n[2] Prediction Service")
    print("-" * 40)
    example_prediction_service()

    print("\n[3] Trading System Integration")
    print("-" * 40)
    example_trading_integration()

    print("\n[4] Enhanced Scanner")
    print("-" * 40)
    example_enhanced_scanner()

    print("\n[5] API Usage")
    print("-" * 40)
    example_api_usage()
