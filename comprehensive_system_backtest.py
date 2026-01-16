#!/usr/bin/env python3
"""
Comprehensive Trading System Backtest
======================================
Analyzes current trading logic across multiple coins, timeframes, and markets.

Tests:
1. Market Shift Predictor on various assets
2. Entry/exit logic effectiveness
3. Timeframe performance comparison
4. Multi-asset consensus accuracy

Created: January 15, 2026
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import ccxt
from dotenv import load_dotenv
import warnings
warnings.filterwarnings('ignore')

# Load environment
load_dotenv('/root/ai_xyz/.env')

# Import market shift predictor
from market_shift_predictor import MarketShiftPredictor, MarketShiftBacktester, ShiftDirection

# Test configuration
COINS_TO_TEST = [
    # Major pairs
    'BTC/USDT:USDT',
    'ETH/USDT:USDT',
    'SOL/USDT:USDT',
    # Large caps
    'XRP/USDT:USDT',
    'DOGE/USDT:USDT',
    'ADA/USDT:USDT',
    'AVAX/USDT:USDT',
    'LINK/USDT:USDT',
    # Mid caps (higher volatility)
    'PEPE/USDT:USDT',
    'WIF/USDT:USDT',
    'BONK/USDT:USDT',
    'ARB/USDT:USDT',
]

TIMEFRAMES = ['1h', '4h', '1d']

# Backtest parameters
INITIAL_CAPITAL = 10000
BASE_POSITION_PCT = 0.02  # 2% per trade
MAX_POSITION_PCT = 0.05   # 5% max
LOOKBACK_CANDLES = 100


def get_exchange():
    """Initialize exchange connection"""
    return ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })


def fetch_historical_data(exchange, symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    """Fetch historical OHLCV data"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f"  Error fetching {symbol} {timeframe}: {e}")
        return None


def run_single_backtest(ohlcv: pd.DataFrame, predictor: MarketShiftPredictor) -> Dict:
    """Run backtest on single asset/timeframe"""
    backtester = MarketShiftBacktester(predictor)
    return backtester.backtest(
        ohlcv=ohlcv,
        initial_capital=INITIAL_CAPITAL,
        base_position_pct=BASE_POSITION_PCT,
        max_position_pct=MAX_POSITION_PCT,
        lookback_window=LOOKBACK_CANDLES
    )


def analyze_signal_accuracy(ohlcv: pd.DataFrame, predictor: MarketShiftPredictor,
                             forward_periods: int = 10) -> Dict:
    """
    Analyze how accurate the shift predictions are.
    Check if price moved in predicted direction within N periods.
    """
    correct = 0
    total = 0
    bullish_correct = 0
    bullish_total = 0
    bearish_correct = 0
    bearish_total = 0

    for i in range(100, len(ohlcv) - forward_periods):
        window = ohlcv.iloc[i-100:i].copy()
        prediction = predictor.predict(window)

        if prediction.direction != ShiftDirection.NEUTRAL:
            total += 1
            current_price = ohlcv.iloc[i]['close']
            future_price = ohlcv.iloc[i + forward_periods]['close']
            price_change = (future_price - current_price) / current_price

            if prediction.direction == ShiftDirection.BULLISH:
                bullish_total += 1
                if price_change > 0:
                    correct += 1
                    bullish_correct += 1
            else:  # BEARISH
                bearish_total += 1
                if price_change < 0:
                    correct += 1
                    bearish_correct += 1

    return {
        'total_signals': total,
        'correct_signals': correct,
        'accuracy': correct / total if total > 0 else 0,
        'bullish_signals': bullish_total,
        'bullish_accuracy': bullish_correct / bullish_total if bullish_total > 0 else 0,
        'bearish_signals': bearish_total,
        'bearish_accuracy': bearish_correct / bearish_total if bearish_total > 0 else 0
    }


def run_comprehensive_backtest():
    """Run backtest across all coins and timeframes"""
    print("=" * 80)
    print("COMPREHENSIVE TRADING SYSTEM BACKTEST")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Coins: {len(COINS_TO_TEST)}")
    print(f"Timeframes: {TIMEFRAMES}")
    print(f"Initial Capital: ${INITIAL_CAPITAL:,.2f}")
    print()

    exchange = get_exchange()
    exchange.load_markets()
    predictor = MarketShiftPredictor()

    results = []

    for symbol in COINS_TO_TEST:
        print(f"\n{'='*60}")
        print(f"Testing: {symbol}")
        print(f"{'='*60}")

        for timeframe in TIMEFRAMES:
            print(f"\n  Timeframe: {timeframe}")

            # Fetch data
            ohlcv = fetch_historical_data(exchange, symbol, timeframe, limit=600)

            if ohlcv is None or len(ohlcv) < 200:
                print(f"    Insufficient data, skipping...")
                continue

            # Run backtest
            try:
                bt_result = run_single_backtest(ohlcv, predictor)

                # Run signal accuracy analysis
                accuracy = analyze_signal_accuracy(ohlcv, predictor)

                result = {
                    'symbol': symbol,
                    'timeframe': timeframe,
                    'candles': len(ohlcv),
                    'total_return': bt_result.get('total_return', 0),
                    'total_trades': bt_result.get('total_trades', 0),
                    'win_rate': bt_result.get('win_rate', 0),
                    'profit_factor': bt_result.get('profit_factor', 0),
                    'max_drawdown': bt_result.get('max_drawdown', 0),
                    'sharpe_ratio': bt_result.get('sharpe_ratio', 0),
                    'signal_accuracy': accuracy['accuracy'],
                    'bullish_accuracy': accuracy['bullish_accuracy'],
                    'bearish_accuracy': accuracy['bearish_accuracy'],
                    'total_signals': accuracy['total_signals']
                }
                results.append(result)

                # Print summary
                print(f"    Return: {bt_result.get('total_return', 0):+.1%}")
                print(f"    Trades: {bt_result.get('total_trades', 0)}")
                print(f"    Win Rate: {bt_result.get('win_rate', 0):.1%}")
                print(f"    PF: {bt_result.get('profit_factor', 0):.2f}")
                print(f"    Signal Accuracy: {accuracy['accuracy']:.1%} ({accuracy['total_signals']} signals)")

            except Exception as e:
                print(f"    Error: {e}")
                continue

    return results


def analyze_results(results: List[Dict]):
    """Analyze and summarize backtest results"""
    if not results:
        print("\nNo results to analyze!")
        return

    df = pd.DataFrame(results)

    print("\n" + "=" * 80)
    print("BACKTEST RESULTS ANALYSIS")
    print("=" * 80)

    # Overall summary
    print("\n1. OVERALL PERFORMANCE")
    print("-" * 40)
    print(f"Total tests: {len(df)}")
    print(f"Avg Return: {df['total_return'].mean():+.2%}")
    print(f"Avg Win Rate: {df['win_rate'].mean():.1%}")
    print(f"Avg Profit Factor: {df['profit_factor'].mean():.2f}")
    print(f"Avg Signal Accuracy: {df['signal_accuracy'].mean():.1%}")

    # By timeframe
    print("\n2. PERFORMANCE BY TIMEFRAME")
    print("-" * 40)
    tf_summary = df.groupby('timeframe').agg({
        'total_return': 'mean',
        'win_rate': 'mean',
        'profit_factor': 'mean',
        'signal_accuracy': 'mean',
        'total_trades': 'sum'
    }).round(3)
    print(tf_summary.to_string())

    # By coin
    print("\n3. PERFORMANCE BY COIN")
    print("-" * 40)
    coin_summary = df.groupby('symbol').agg({
        'total_return': 'mean',
        'win_rate': 'mean',
        'profit_factor': 'mean',
        'signal_accuracy': 'mean',
        'total_trades': 'sum'
    }).round(3)
    print(coin_summary.to_string())

    # Best performers
    print("\n4. TOP 10 BEST COMBINATIONS")
    print("-" * 40)
    top = df.nlargest(10, 'total_return')[['symbol', 'timeframe', 'total_return', 'win_rate', 'profit_factor', 'signal_accuracy']]
    print(top.to_string(index=False))

    # Worst performers
    print("\n5. TOP 10 WORST COMBINATIONS")
    print("-" * 40)
    bottom = df.nsmallest(10, 'total_return')[['symbol', 'timeframe', 'total_return', 'win_rate', 'profit_factor', 'signal_accuracy']]
    print(bottom.to_string(index=False))

    # Signal analysis
    print("\n6. SIGNAL DIRECTION ANALYSIS")
    print("-" * 40)
    print(f"Avg Bullish Accuracy: {df['bullish_accuracy'].mean():.1%}")
    print(f"Avg Bearish Accuracy: {df['bearish_accuracy'].mean():.1%}")
    print(f"Total Signals Generated: {df['total_signals'].sum()}")

    # Recommendations
    print("\n7. RECOMMENDATIONS")
    print("-" * 40)

    # Best timeframe
    best_tf = tf_summary['total_return'].idxmax()
    print(f"Best Timeframe: {best_tf} ({tf_summary.loc[best_tf, 'total_return']:+.2%} avg return)")

    # Best coins
    profitable_coins = coin_summary[coin_summary['total_return'] > 0].index.tolist()
    print(f"Profitable Coins: {', '.join([c.split('/')[0] for c in profitable_coins[:5]])}")

    # Coins to avoid
    unprofitable_coins = coin_summary[coin_summary['total_return'] < -0.05].index.tolist()
    if unprofitable_coins:
        print(f"Avoid: {', '.join([c.split('/')[0] for c in unprofitable_coins[:3]])}")

    # Signal reliability
    high_accuracy = df[df['signal_accuracy'] > 0.55][['symbol', 'timeframe', 'signal_accuracy']].sort_values('signal_accuracy', ascending=False)
    if len(high_accuracy) > 0:
        print(f"\nHigh Accuracy Signals (>55%):")
        for _, row in high_accuracy.head(5).iterrows():
            print(f"  {row['symbol'].split('/')[0]} {row['timeframe']}: {row['signal_accuracy']:.1%}")

    return df


def main():
    """Main entry point"""
    try:
        results = run_comprehensive_backtest()
        df = analyze_results(results)

        # Save results
        if df is not None:
            output_file = f"/root/ai_xyz/backtest_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df.to_csv(output_file, index=False)
            print(f"\nResults saved to: {output_file}")

        print(f"\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    except Exception as e:
        print(f"\nBacktest failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
