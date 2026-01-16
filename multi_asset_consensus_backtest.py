#!/usr/bin/env python3
"""
Multi-Asset Consensus Backtest
==============================
Tests the multi-asset consensus and combined prediction approaches
to compare against single-asset predictions.

Created: January 15, 2026
"""

import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List
import ccxt
from dotenv import load_dotenv
import warnings
warnings.filterwarnings('ignore')

load_dotenv('/root/ai_xyz/.env')

from market_shift_predictor import MarketShiftPredictor, ShiftDirection, ShiftPrediction


def get_exchange():
    """Initialize exchange connection"""
    return ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })


def fetch_ohlcv(exchange, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """Fetch historical OHLCV data"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"  Error fetching {symbol}: {e}")
        return None


def test_single_vs_multi_asset(timeframe: str = '4h'):
    """Compare single asset vs multi-asset consensus predictions"""
    print(f"\n{'='*70}")
    print(f"SINGLE ASSET VS MULTI-ASSET CONSENSUS TEST - {timeframe}")
    print(f"{'='*70}\n")

    exchange = get_exchange()
    exchange.load_markets()
    predictor = MarketShiftPredictor()

    # Core assets for multi-asset consensus
    core_assets = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']

    # Additional test assets
    test_assets = [
        'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'AVAX/USDT:USDT',
        'LINK/USDT:USDT', 'WIF/USDT:USDT', 'ARB/USDT:USDT'
    ]

    # Fetch core asset data
    print("Fetching core assets for multi-asset consensus...")
    ohlcv_dict = {}
    for symbol in core_assets:
        df = fetch_ohlcv(exchange, symbol, timeframe, limit=500)
        if df is not None:
            ohlcv_dict[symbol] = df
            print(f"  {symbol}: {len(df)} candles")

    if len(ohlcv_dict) < 2:
        print("Insufficient core asset data!")
        return

    results = {
        'single_btc': {'correct': 0, 'total': 0},
        'multi_asset': {'correct': 0, 'total': 0},
        'combined': {'correct': 0, 'total': 0}
    }

    forward_periods = 10  # Look ahead periods for verification
    lookback = 100

    # Find shortest common length
    min_length = min(len(df) for df in ohlcv_dict.values())

    print(f"\nTesting predictions over {min_length - lookback - forward_periods} periods...")
    print(f"Looking ahead {forward_periods} periods for verification\n")

    for i in range(lookback, min_length - forward_periods):
        # Prepare windows for each asset
        windows = {}
        for symbol, df in ohlcv_dict.items():
            windows[symbol] = df.iloc[i-lookback:i].copy()

        # Single BTC prediction
        btc_pred = predictor.predict(windows['BTC/USDT:USDT'])

        # Multi-asset consensus
        multi_pred = predictor.predict_multi_asset(windows)

        # Combined prediction (no positions for simplicity)
        combined_pred = predictor.predict_combined(windows, positions=[])

        # Check BTC price movement for verification
        btc_current = ohlcv_dict['BTC/USDT:USDT'].iloc[i]['close']
        btc_future = ohlcv_dict['BTC/USDT:USDT'].iloc[i + forward_periods]['close']
        actual_move = (btc_future - btc_current) / btc_current

        # Score predictions
        def score_prediction(pred: ShiftPrediction, actual: float) -> int:
            if pred.direction == ShiftDirection.NEUTRAL:
                return -1  # Skip neutral
            if pred.direction == ShiftDirection.BULLISH and actual > 0.001:  # >0.1% move up
                return 1
            if pred.direction == ShiftDirection.BEARISH and actual < -0.001:  # >0.1% move down
                return 1
            return 0

        btc_score = score_prediction(btc_pred, actual_move)
        multi_score = score_prediction(multi_pred, actual_move)
        combined_score = score_prediction(combined_pred, actual_move)

        if btc_score >= 0:
            results['single_btc']['total'] += 1
            results['single_btc']['correct'] += btc_score

        if multi_score >= 0:
            results['multi_asset']['total'] += 1
            results['multi_asset']['correct'] += multi_score

        if combined_score >= 0:
            results['combined']['total'] += 1
            results['combined']['correct'] += combined_score

    # Print results
    print("\nRESULTS:")
    print("-" * 50)

    for method, data in results.items():
        if data['total'] > 0:
            accuracy = data['correct'] / data['total']
            print(f"{method:15} | Signals: {data['total']:4} | Correct: {data['correct']:4} | Accuracy: {accuracy:.1%}")

    return results


def test_trading_simulation():
    """
    Simulate actual trading with multi-asset consensus
    """
    print(f"\n{'='*70}")
    print("TRADING SIMULATION WITH MULTI-ASSET CONSENSUS")
    print(f"{'='*70}\n")

    exchange = get_exchange()
    exchange.load_markets()
    predictor = MarketShiftPredictor()

    # Fetch data
    core_assets = ['BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT']
    ohlcv_dict = {}

    print("Fetching 4h data for simulation...")
    for symbol in core_assets:
        df = fetch_ohlcv(exchange, symbol, '4h', limit=500)
        if df is not None:
            ohlcv_dict[symbol] = df

    # Simulation parameters
    initial_capital = 10000
    capital = initial_capital
    position = None  # {'side': 'long'/'short', 'entry': price, 'size': contracts}
    trades = []

    lookback = 100
    min_length = min(len(df) for df in ohlcv_dict.values())

    print(f"Simulating trading over {min_length - lookback} periods...")

    for i in range(lookback, min_length):
        # Prepare windows
        windows = {}
        for symbol, df in ohlcv_dict.items():
            windows[symbol] = df.iloc[i-lookback:i].copy()

        # Get combined prediction
        prediction = predictor.predict_combined(windows, positions=[])

        current_price = ohlcv_dict['BTC/USDT:USDT'].iloc[i]['close']

        # Position management
        if position:
            # Calculate unrealized P&L
            if position['side'] == 'long':
                unrealized_pct = (current_price - position['entry']) / position['entry']
            else:
                unrealized_pct = (position['entry'] - current_price) / position['entry']

            # Exit conditions
            should_exit = False
            exit_reason = ""

            # Take profit at 5%
            if unrealized_pct > 0.05:
                should_exit = True
                exit_reason = "take_profit"
            # Stop loss at -3%
            elif unrealized_pct < -0.03:
                should_exit = True
                exit_reason = "stop_loss"
            # Signal reversal
            elif (position['side'] == 'long' and prediction.direction == ShiftDirection.BEARISH and prediction.confidence > 0.5):
                should_exit = True
                exit_reason = "signal_reversal"
            elif (position['side'] == 'short' and prediction.direction == ShiftDirection.BULLISH and prediction.confidence > 0.5):
                should_exit = True
                exit_reason = "signal_reversal"

            if should_exit:
                if position['side'] == 'long':
                    pnl = (current_price - position['entry']) * position['size']
                else:
                    pnl = (position['entry'] - current_price) * position['size']

                capital += pnl
                trades.append({
                    'side': position['side'],
                    'entry': position['entry'],
                    'exit': current_price,
                    'pnl': pnl,
                    'pnl_pct': unrealized_pct,
                    'reason': exit_reason
                })
                position = None

        # Entry conditions
        if position is None and prediction.direction != ShiftDirection.NEUTRAL:
            if prediction.confidence > 0.5:  # Only high confidence signals
                position_value = capital * 0.02  # 2% position
                size = position_value / current_price

                position = {
                    'side': 'long' if prediction.direction == ShiftDirection.BULLISH else 'short',
                    'entry': current_price,
                    'size': size
                }

    # Close any remaining position
    if position:
        final_price = ohlcv_dict['BTC/USDT:USDT'].iloc[-1]['close']
        if position['side'] == 'long':
            pnl = (final_price - position['entry']) * position['size']
        else:
            pnl = (position['entry'] - final_price) * position['size']
        capital += pnl
        trades.append({
            'side': position['side'],
            'entry': position['entry'],
            'exit': final_price,
            'pnl': pnl,
            'reason': 'end_of_sim'
        })

    # Calculate statistics
    print("\nSIMULATION RESULTS:")
    print("-" * 50)
    print(f"Initial Capital: ${initial_capital:,.2f}")
    print(f"Final Capital:   ${capital:,.2f}")
    print(f"Total Return:    {(capital - initial_capital) / initial_capital:+.2%}")
    print(f"Total Trades:    {len(trades)}")

    if trades:
        wins = [t for t in trades if t['pnl'] > 0]
        losses = [t for t in trades if t['pnl'] <= 0]

        print(f"Wins:            {len(wins)}")
        print(f"Losses:          {len(losses)}")
        print(f"Win Rate:        {len(wins)/len(trades):.1%}")

        if wins:
            print(f"Avg Win:         ${np.mean([t['pnl'] for t in wins]):,.2f}")
        if losses:
            print(f"Avg Loss:        ${np.mean([t['pnl'] for t in losses]):,.2f}")

        total_wins = sum(t['pnl'] for t in wins) if wins else 0
        total_losses = abs(sum(t['pnl'] for t in losses)) if losses else 0

        if total_losses > 0:
            print(f"Profit Factor:   {total_wins / total_losses:.2f}")

        # Exit reasons
        reasons = {}
        for t in trades:
            r = t.get('reason', 'unknown')
            reasons[r] = reasons.get(r, 0) + 1
        print(f"\nExit Reasons:")
        for r, count in reasons.items():
            print(f"  {r}: {count}")

    return trades


def main():
    print("=" * 70)
    print("MULTI-ASSET CONSENSUS BACKTEST SUITE")
    print("=" * 70)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Test 1: Compare single vs multi-asset for different timeframes
    for tf in ['1h', '4h']:
        test_single_vs_multi_asset(tf)

    # Test 2: Trading simulation
    test_trading_simulation()

    print(f"\n\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()
