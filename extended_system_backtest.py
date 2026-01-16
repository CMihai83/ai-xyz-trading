#!/usr/bin/env python3
"""
Extended Trading System Backtest
=================================
Comprehensive analysis with:
- Multiple timeframes: 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d
- Maximum historical data (1500 candles)
- All available trading pairs
- Zone-based strategy simulation

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
import time
warnings.filterwarnings('ignore')

load_dotenv('/root/ai_xyz/.env')

from market_shift_predictor import MarketShiftPredictor, MarketShiftBacktester, ShiftDirection

# Extended configuration
TIMEFRAMES = ['15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
MAX_CANDLES = 1500  # Maximum candles to fetch

# All major trading pairs
COINS_TO_TEST = [
    # Top 10 by market cap
    'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'XRP/USDT:USDT',
    'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'AVAX/USDT:USDT', 'LINK/USDT:USDT',
    'DOT/USDT:USDT', 'MATIC/USDT:USDT',
    # Layer 1s
    'NEAR/USDT:USDT', 'APT/USDT:USDT', 'SUI/USDT:USDT', 'SEI/USDT:USDT',
    'FTM/USDT:USDT', 'ATOM/USDT:USDT', 'INJ/USDT:USDT',
    # Layer 2s / DeFi
    'ARB/USDT:USDT', 'OP/USDT:USDT', 'UNI/USDT:USDT', 'AAVE/USDT:USDT',
    # Memes / High volatility
    'PEPE/USDT:USDT', 'WIF/USDT:USDT', 'FLOKI/USDT:USDT', 'SHIB/USDT:USDT',
    # AI / Gaming
    'FET/USDT:USDT', 'RENDER/USDT:USDT', 'IMX/USDT:USDT', 'GALA/USDT:USDT',
]

# Backtest parameters
INITIAL_CAPITAL = 10000
BASE_POSITION_PCT = 0.02
MAX_POSITION_PCT = 0.05
LOOKBACK_CANDLES = 100

# Zone thresholds
ZONE_THRESHOLDS = {
    'averaging': -0.25,
    'profit_taking': 0.05,
    'stop_loss': -0.90
}
FIBONACCI_MULTIPLIERS = [1.0, 1.618, 2.618, 4.236, 6.854]
BASE_MARGIN = 0.70
LEVERAGE = 5


def get_exchange():
    """Initialize exchange connection"""
    return ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'},
        'enableRateLimit': True
    })


def fetch_historical_data(exchange, symbol: str, timeframe: str, limit: int = 1500) -> pd.DataFrame:
    """Fetch maximum historical OHLCV data"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        return None


def calculate_timeframe_days(timeframe: str, candles: int) -> float:
    """Calculate how many days of data we have"""
    tf_minutes = {
        '15m': 15, '30m': 30, '1h': 60, '2h': 120,
        '4h': 240, '6h': 360, '12h': 720, '1d': 1440
    }
    minutes = tf_minutes.get(timeframe, 60)
    return (candles * minutes) / 1440


def run_shift_predictor_backtest(ohlcv: pd.DataFrame, predictor: MarketShiftPredictor) -> Dict:
    """Run market shift predictor backtest"""
    backtester = MarketShiftBacktester(predictor)
    return backtester.backtest(
        ohlcv=ohlcv,
        initial_capital=INITIAL_CAPITAL,
        base_position_pct=BASE_POSITION_PCT,
        max_position_pct=MAX_POSITION_PCT,
        lookback_window=LOOKBACK_CANDLES
    )


def analyze_signal_accuracy(ohlcv: pd.DataFrame, predictor: MarketShiftPredictor,
                           forward_periods: List[int] = [5, 10, 20, 50]) -> Dict:
    """Analyze signal accuracy over multiple forward periods"""
    results = {}

    for fp in forward_periods:
        correct = 0
        total = 0

        for i in range(100, len(ohlcv) - fp):
            window = ohlcv.iloc[i-100:i].copy()
            prediction = predictor.predict(window)

            if prediction.direction != ShiftDirection.NEUTRAL:
                total += 1
                current_price = ohlcv.iloc[i]['close']
                future_price = ohlcv.iloc[i + fp]['close']
                price_change = (future_price - current_price) / current_price

                if prediction.direction == ShiftDirection.BULLISH and price_change > 0.001:
                    correct += 1
                elif prediction.direction == ShiftDirection.BEARISH and price_change < -0.001:
                    correct += 1

        results[f'accuracy_{fp}'] = correct / total if total > 0 else 0
        results[f'signals_{fp}'] = total

    return results


class ZonePosition:
    """Zone-based position simulation"""
    def __init__(self, side: str, entry_price: float):
        self.side = side
        self.entry_price = entry_price
        self.avg_entry = entry_price
        self.entries = [(entry_price, BASE_MARGIN)]
        self.total_margin = BASE_MARGIN
        self.averaging_steps = 0
        self.peak_upnl = 0
        self.closed = False
        self.close_price = 0
        self.close_reason = ""

    @property
    def position_size(self):
        return self.total_margin * LEVERAGE

    def calculate_upnl_pct(self, price):
        if self.side == 'long':
            return (price - self.avg_entry) / self.avg_entry * LEVERAGE
        return (self.avg_entry - price) / self.avg_entry * LEVERAGE

    def calculate_upnl(self, price):
        return self.calculate_upnl_pct(price) * self.total_margin

    def update_avg_entry(self):
        total_val = sum(p * m for p, m in self.entries)
        total_m = sum(m for _, m in self.entries)
        self.avg_entry = total_val / total_m if total_m > 0 else self.entry_price

    def add_averaging(self, price):
        if self.averaging_steps >= 5:
            return False
        self.averaging_steps += 1
        mult = FIBONACCI_MULTIPLIERS[min(self.averaging_steps, 4)]
        add_margin = BASE_MARGIN * mult * 0.2
        self.entries.append((price, add_margin))
        self.total_margin += add_margin
        self.update_avg_entry()
        return True

    def get_final_pnl(self):
        return self.calculate_upnl(self.close_price if self.closed else self.entry_price)


def run_zone_backtest(ohlcv: pd.DataFrame, predictor: MarketShiftPredictor) -> Dict:
    """Run zone-based strategy backtest"""
    positions = []
    active = None
    lookback = 100

    for i in range(lookback, len(ohlcv)):
        bar = ohlcv.iloc[i]
        price = bar['close']
        low, high = bar['low'], bar['high']

        if active:
            check_price = low if active.side == 'long' else high
            upnl_pct = active.calculate_upnl_pct(check_price)
            upnl = active.calculate_upnl(check_price)

            if upnl > active.peak_upnl:
                active.peak_upnl = upnl

            if upnl_pct <= ZONE_THRESHOLDS['stop_loss']:
                active.closed = True
                active.close_price = check_price
                active.close_reason = 'stop_loss'
            elif upnl_pct <= ZONE_THRESHOLDS['averaging']:
                active.add_averaging(check_price)
            elif upnl_pct >= ZONE_THRESHOLDS['profit_taking']:
                if active.peak_upnl > 0 and upnl < active.peak_upnl * 0.85:
                    active.closed = True
                    active.close_price = price
                    active.close_reason = 'surplus_dump'

            if active.closed:
                positions.append(active)
                active = None

        if active is None:
            window = ohlcv.iloc[i-lookback:i].copy()
            pred = predictor.predict(window)
            if pred.direction != ShiftDirection.NEUTRAL and pred.confidence > 0.5:
                side = 'long' if pred.direction == ShiftDirection.BULLISH else 'short'
                active = ZonePosition(side, price)

    if active:
        active.closed = True
        active.close_price = ohlcv.iloc[-1]['close']
        active.close_reason = 'end_of_backtest'
        positions.append(active)

    if not positions:
        return {'trades': 0}

    wins = [p for p in positions if p.get_final_pnl() > 0]
    losses = [p for p in positions if p.get_final_pnl() <= 0]

    reasons = {}
    for p in positions:
        reasons[p.close_reason] = reasons.get(p.close_reason, 0) + 1

    return {
        'trades': len(positions),
        'wins': len(wins),
        'losses': len(losses),
        'win_rate': len(wins) / len(positions),
        'total_pnl': sum(p.get_final_pnl() for p in positions),
        'avg_steps_win': np.mean([p.averaging_steps for p in wins]) if wins else 0,
        'avg_steps_loss': np.mean([p.averaging_steps for p in losses]) if losses else 0,
        'close_reasons': reasons
    }


def main():
    print("=" * 80)
    print("EXTENDED TRADING SYSTEM BACKTEST")
    print("=" * 80)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Coins: {len(COINS_TO_TEST)}")
    print(f"Timeframes: {TIMEFRAMES}")
    print(f"Max Candles: {MAX_CANDLES}")
    print()

    exchange = get_exchange()
    exchange.load_markets()
    predictor = MarketShiftPredictor()

    all_results = []
    valid_symbols = []

    # First, check which symbols are available
    print("Checking available symbols...")
    for symbol in COINS_TO_TEST:
        if symbol in exchange.markets:
            valid_symbols.append(symbol)
        else:
            print(f"  {symbol} not available")

    print(f"Testing {len(valid_symbols)} symbols\n")

    total_tests = len(valid_symbols) * len(TIMEFRAMES)
    current = 0

    for symbol in valid_symbols:
        base = symbol.split('/')[0]
        print(f"\n{'='*60}")
        print(f"Testing: {symbol}")
        print(f"{'='*60}")

        for timeframe in TIMEFRAMES:
            current += 1
            progress = current / total_tests * 100

            # Fetch data
            ohlcv = fetch_historical_data(exchange, symbol, timeframe, MAX_CANDLES)

            if ohlcv is None or len(ohlcv) < 200:
                print(f"  {timeframe:4} | Insufficient data")
                continue

            days_of_data = calculate_timeframe_days(timeframe, len(ohlcv))

            try:
                # Run market shift backtest
                bt_result = run_shift_predictor_backtest(ohlcv, predictor)

                # Run signal accuracy analysis
                accuracy = analyze_signal_accuracy(ohlcv, predictor, [5, 10, 20, 50])

                # Run zone-based backtest
                zone_result = run_zone_backtest(ohlcv, predictor)

                result = {
                    'symbol': symbol,
                    'base': base,
                    'timeframe': timeframe,
                    'candles': len(ohlcv),
                    'days': days_of_data,
                    # Shift predictor results
                    'sp_return': bt_result.get('total_return', 0),
                    'sp_trades': bt_result.get('total_trades', 0),
                    'sp_win_rate': bt_result.get('win_rate', 0),
                    'sp_profit_factor': bt_result.get('profit_factor', 0),
                    'sp_max_dd': bt_result.get('max_drawdown', 0),
                    'sp_sharpe': bt_result.get('sharpe_ratio', 0),
                    # Accuracy at different horizons
                    'acc_5': accuracy.get('accuracy_5', 0),
                    'acc_10': accuracy.get('accuracy_10', 0),
                    'acc_20': accuracy.get('accuracy_20', 0),
                    'acc_50': accuracy.get('accuracy_50', 0),
                    'signals_10': accuracy.get('signals_10', 0),
                    # Zone strategy results
                    'zone_trades': zone_result.get('trades', 0),
                    'zone_wins': zone_result.get('wins', 0),
                    'zone_win_rate': zone_result.get('win_rate', 0),
                    'zone_pnl': zone_result.get('total_pnl', 0),
                    'zone_avg_steps_win': zone_result.get('avg_steps_win', 0),
                    'zone_avg_steps_loss': zone_result.get('avg_steps_loss', 0),
                }
                all_results.append(result)

                # Print summary
                print(f"  {timeframe:4} | {len(ohlcv):4} candles ({days_of_data:.0f}d) | " +
                      f"SP: {bt_result.get('total_return', 0):+.1%} WR:{bt_result.get('win_rate', 0):.0%} | " +
                      f"Zone: {zone_result.get('win_rate', 0):.0%} WR ${zone_result.get('total_pnl', 0):+.2f} | " +
                      f"Acc@10: {accuracy.get('accuracy_10', 0):.0%}")

            except Exception as e:
                print(f"  {timeframe:4} | Error: {str(e)[:50]}")
                continue

            # Rate limiting
            time.sleep(0.1)

    # Save raw results
    if all_results:
        df = pd.DataFrame(all_results)
        output_file = f"/root/ai_xyz/extended_backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(output_file, index=False)
        print(f"\n\nRaw results saved to: {output_file}")

        # Comprehensive analysis
        analyze_extended_results(df)

    print(f"\n\nCompleted: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


def analyze_extended_results(df: pd.DataFrame):
    """Comprehensive analysis of extended backtest results"""

    print("\n" + "=" * 80)
    print("COMPREHENSIVE ANALYSIS")
    print("=" * 80)

    # 1. Overall Statistics
    print("\n" + "=" * 60)
    print("1. OVERALL STATISTICS")
    print("=" * 60)
    print(f"Total tests: {len(df)}")
    print(f"Unique symbols: {df['base'].nunique()}")
    print(f"Timeframes tested: {df['timeframe'].nunique()}")
    print(f"Total candles analyzed: {df['candles'].sum():,}")
    print(f"Total days of data: {df['days'].sum():,.0f}")

    # 2. By Timeframe Analysis
    print("\n" + "=" * 60)
    print("2. PERFORMANCE BY TIMEFRAME")
    print("=" * 60)

    tf_order = ['15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d']
    tf_stats = df.groupby('timeframe').agg({
        'candles': 'mean',
        'days': 'mean',
        'sp_return': 'mean',
        'sp_win_rate': 'mean',
        'sp_profit_factor': 'mean',
        'acc_5': 'mean',
        'acc_10': 'mean',
        'acc_20': 'mean',
        'acc_50': 'mean',
        'zone_win_rate': 'mean',
        'zone_pnl': 'sum',
        'zone_trades': 'sum'
    }).reindex([t for t in tf_order if t in df['timeframe'].values])

    print("\nShift Predictor Performance:")
    print(f"{'TF':>5} | {'Candles':>7} | {'Days':>5} | {'Return':>8} | {'WinRate':>7} | {'PF':>5}")
    print("-" * 55)
    for tf in tf_stats.index:
        row = tf_stats.loc[tf]
        print(f"{tf:>5} | {row['candles']:>7.0f} | {row['days']:>5.0f} | " +
              f"{row['sp_return']:>+7.2%} | {row['sp_win_rate']:>6.1%} | {row['sp_profit_factor']:>5.2f}")

    print("\nSignal Accuracy by Forward Period:")
    print(f"{'TF':>5} | {'@5':>6} | {'@10':>6} | {'@20':>6} | {'@50':>6}")
    print("-" * 45)
    for tf in tf_stats.index:
        row = tf_stats.loc[tf]
        print(f"{tf:>5} | {row['acc_5']:>5.1%} | {row['acc_10']:>5.1%} | " +
              f"{row['acc_20']:>5.1%} | {row['acc_50']:>5.1%}")

    print("\nZone Strategy Performance:")
    print(f"{'TF':>5} | {'Trades':>7} | {'WinRate':>7} | {'Total PnL':>10}")
    print("-" * 40)
    for tf in tf_stats.index:
        row = tf_stats.loc[tf]
        print(f"{tf:>5} | {row['zone_trades']:>7.0f} | {row['zone_win_rate']:>6.1%} | ${row['zone_pnl']:>+9.2f}")

    # 3. By Symbol Analysis
    print("\n" + "=" * 60)
    print("3. PERFORMANCE BY SYMBOL (Top 15)")
    print("=" * 60)

    sym_stats = df.groupby('base').agg({
        'sp_return': 'mean',
        'sp_win_rate': 'mean',
        'sp_profit_factor': 'mean',
        'acc_10': 'mean',
        'zone_win_rate': 'mean',
        'zone_pnl': 'sum'
    }).sort_values('zone_pnl', ascending=False)

    print(f"\n{'Symbol':>8} | {'SP Ret':>8} | {'SP WR':>6} | {'Acc@10':>7} | {'Zone WR':>7} | {'Zone PnL':>10}")
    print("-" * 65)
    for sym in sym_stats.head(15).index:
        row = sym_stats.loc[sym]
        print(f"{sym:>8} | {row['sp_return']:>+7.2%} | {row['sp_win_rate']:>5.1%} | " +
              f"{row['acc_10']:>6.1%} | {row['zone_win_rate']:>6.1%} | ${row['zone_pnl']:>+9.2f}")

    # 4. Best Combinations
    print("\n" + "=" * 60)
    print("4. TOP 20 BEST COMBINATIONS (by Zone P&L)")
    print("=" * 60)

    top = df.nlargest(20, 'zone_pnl')[['base', 'timeframe', 'days', 'sp_return',
                                        'acc_10', 'zone_win_rate', 'zone_pnl', 'zone_trades']]
    print(f"\n{'Symbol':>8} | {'TF':>4} | {'Days':>5} | {'SP Ret':>7} | {'Acc@10':>6} | {'Zone WR':>7} | {'PnL':>8} | {'Trades':>6}")
    print("-" * 75)
    for _, row in top.iterrows():
        print(f"{row['base']:>8} | {row['timeframe']:>4} | {row['days']:>5.0f} | " +
              f"{row['sp_return']:>+6.1%} | {row['acc_10']:>5.1%} | {row['zone_win_rate']:>6.1%} | " +
              f"${row['zone_pnl']:>+7.2f} | {row['zone_trades']:>6.0f}")

    # 5. Worst Combinations
    print("\n" + "=" * 60)
    print("5. TOP 10 WORST COMBINATIONS (by Zone P&L)")
    print("=" * 60)

    bottom = df.nsmallest(10, 'zone_pnl')[['base', 'timeframe', 'days', 'sp_return',
                                            'acc_10', 'zone_win_rate', 'zone_pnl']]
    print(f"\n{'Symbol':>8} | {'TF':>4} | {'Days':>5} | {'SP Ret':>7} | {'Acc@10':>6} | {'Zone WR':>7} | {'PnL':>8}")
    print("-" * 65)
    for _, row in bottom.iterrows():
        print(f"{row['base']:>8} | {row['timeframe']:>4} | {row['days']:>5.0f} | " +
              f"{row['sp_return']:>+6.1%} | {row['acc_10']:>5.1%} | {row['zone_win_rate']:>6.1%} | " +
              f"${row['zone_pnl']:>+7.2f}")

    # 6. Accuracy Analysis
    print("\n" + "=" * 60)
    print("6. SIGNAL ACCURACY ANALYSIS")
    print("=" * 60)

    # Best accuracy combinations
    high_acc = df[df['acc_10'] > 0.55][['base', 'timeframe', 'acc_5', 'acc_10', 'acc_20', 'acc_50', 'signals_10']].sort_values('acc_10', ascending=False)

    if len(high_acc) > 0:
        print(f"\nHigh Accuracy Combinations (>55% at 10 periods):")
        print(f"{'Symbol':>8} | {'TF':>4} | {'@5':>5} | {'@10':>5} | {'@20':>5} | {'@50':>5} | {'Signals':>7}")
        print("-" * 55)
        for _, row in high_acc.head(15).iterrows():
            print(f"{row['base']:>8} | {row['timeframe']:>4} | {row['acc_5']:>4.0%} | " +
                  f"{row['acc_10']:>4.0%} | {row['acc_20']:>4.0%} | {row['acc_50']:>4.0%} | {row['signals_10']:>7.0f}")

    # 7. Recommendations
    print("\n" + "=" * 60)
    print("7. KEY FINDINGS & RECOMMENDATIONS")
    print("=" * 60)

    # Best timeframe
    best_tf = tf_stats['zone_pnl'].idxmax()
    best_tf_wr = tf_stats.loc[best_tf, 'zone_win_rate']
    best_tf_pnl = tf_stats.loc[best_tf, 'zone_pnl']
    print(f"\n1. BEST TIMEFRAME: {best_tf}")
    print(f"   Win Rate: {best_tf_wr:.1%}, Total P&L: ${best_tf_pnl:+.2f}")

    # Most accurate timeframe
    best_acc_tf = tf_stats['acc_10'].idxmax()
    best_acc = tf_stats.loc[best_acc_tf, 'acc_10']
    print(f"\n2. MOST ACCURATE TIMEFRAME: {best_acc_tf}")
    print(f"   Signal Accuracy @10 periods: {best_acc:.1%}")

    # Best symbols
    profitable_symbols = sym_stats[sym_stats['zone_pnl'] > 0].index.tolist()[:5]
    print(f"\n3. MOST PROFITABLE SYMBOLS:")
    for sym in profitable_symbols:
        pnl = sym_stats.loc[sym, 'zone_pnl']
        wr = sym_stats.loc[sym, 'zone_win_rate']
        print(f"   {sym}: ${pnl:+.2f} ({wr:.0%} win rate)")

    # Symbols to avoid
    loss_symbols = sym_stats[sym_stats['zone_pnl'] < -5].index.tolist()[:3]
    if loss_symbols:
        print(f"\n4. AVOID THESE SYMBOLS:")
        for sym in loss_symbols:
            pnl = sym_stats.loc[sym, 'zone_pnl']
            print(f"   {sym}: ${pnl:.2f}")

    # Accuracy vs Horizon
    print(f"\n5. ACCURACY DEGRADES WITH HORIZON:")
    avg_acc = df[['acc_5', 'acc_10', 'acc_20', 'acc_50']].mean()
    print(f"   @5 periods:  {avg_acc['acc_5']:.1%}")
    print(f"   @10 periods: {avg_acc['acc_10']:.1%}")
    print(f"   @20 periods: {avg_acc['acc_20']:.1%}")
    print(f"   @50 periods: {avg_acc['acc_50']:.1%}")

    # Zone strategy averaging analysis
    avg_steps_win = df['zone_avg_steps_win'].mean()
    avg_steps_loss = df['zone_avg_steps_loss'].mean()
    print(f"\n6. AVERAGING EFFECTIVENESS:")
    print(f"   Avg steps on winning trades: {avg_steps_win:.2f}")
    print(f"   Avg steps on losing trades: {avg_steps_loss:.2f}")


if __name__ == "__main__":
    main()
