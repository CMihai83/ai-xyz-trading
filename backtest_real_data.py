#!/usr/bin/env python3
"""
Real Data Backtest Engine for AI-XYZ Trading System
====================================================
Uses actual historical data from Bitget exchange instead of simulated scenarios.

Features:
- Fetches real OHLCV data from Bitget API
- Tests strategies against actual market movements
- Supports multiple symbols and timeframes
- Caches data to avoid repeated API calls
- Validates results against real price action

Author: Claude + Grok Consortium
Version: 1.0.0
Date: January 16, 2026
"""

import os
import json
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
import ccxt
from dotenv import load_dotenv
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment
load_dotenv('/root/ai_xyz/.env')


@dataclass
class BacktestConfig:
    """Configuration for backtest parameters"""
    stage1_threshold: float = 0.85  # % of peak to trigger stage 1
    stage2_threshold: float = 0.30  # % of peak to trigger stage 2
    averaging_threshold: float = -0.25  # P&L % to trigger averaging
    max_averaging_steps: int = 5
    leverage: int = 10
    initial_margin_usd: float = 5.0
    fibonacci_multipliers: List[float] = field(default_factory=lambda: [1.0, 1.5, 2.0, 2.5, 3.0])


@dataclass
class PositionState:
    """Tracks position state during backtest"""
    symbol: str
    entry_price: float
    entry_time: datetime
    contracts: float
    margin: float
    leverage: int
    side: str = "long"
    averaging_steps: int = 0
    averaging_entries: List[Tuple[float, float, datetime]] = field(default_factory=list)  # (price, contracts, time)
    peak_upnl: float = 0.0
    peak_time: Optional[datetime] = None
    surplus_dump_stage: int = 0
    total_captured: float = 0.0
    is_closed: bool = False
    close_price: float = 0.0
    close_time: Optional[datetime] = None
    close_reason: str = ""


class RealDataBacktest:
    """
    Backtest engine using real market data from Bitget.

    Key features:
    - Fetches actual OHLCV data
    - Simulates position lifecycle with real prices
    - Tests different threshold configurations
    - Compares results to actual outcomes
    """

    CACHE_DIR = "/root/ai_xyz/backtest_cache"

    def __init__(self):
        """Initialize with Bitget connection"""
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'options': {'defaultType': 'swap'}
        })

        # Create cache directory
        os.makedirs(self.CACHE_DIR, exist_ok=True)

        # Data cache
        self.ohlcv_cache: Dict[str, pd.DataFrame] = {}

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = '5m',
        days: int = 7,
        use_cache: bool = True
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data from Bitget.

        Args:
            symbol: Trading pair (e.g., 'AXS/USDT:USDT')
            timeframe: Candle timeframe ('1m', '5m', '15m', '1h', '4h', '1d')
            days: Number of days of history
            use_cache: Whether to use cached data

        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        cache_key = f"{symbol}_{timeframe}_{days}"
        cache_file = os.path.join(self.CACHE_DIR, f"{cache_key.replace('/', '_')}.json")

        # Check cache
        if use_cache and os.path.exists(cache_file):
            cache_age = time.time() - os.path.getmtime(cache_file)
            if cache_age < 3600:  # Cache valid for 1 hour
                logger.info(f"Loading cached data for {symbol}")
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                df = pd.DataFrame(data)
                df['datetime'] = pd.to_datetime(df['datetime'])
                return df

        # Fetch from exchange
        logger.info(f"Fetching {days} days of {timeframe} data for {symbol}")

        # Calculate how many candles we need
        timeframe_minutes = {
            '1m': 1, '5m': 5, '15m': 15, '1h': 60, '4h': 240, '1d': 1440
        }
        minutes = timeframe_minutes.get(timeframe, 5)
        candles_needed = (days * 24 * 60) // minutes

        # Bitget limits to 1000 candles per request
        all_candles = []
        since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

        while len(all_candles) < candles_needed:
            try:
                candles = self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=1000
                )
                if not candles:
                    break

                all_candles.extend(candles)
                since = candles[-1][0] + 1

                if len(candles) < 1000:
                    break

                time.sleep(0.1)  # Rate limiting

            except Exception as e:
                logger.error(f"Error fetching OHLCV: {e}")
                break

        # Convert to DataFrame
        df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)

        # Cache the data (convert timestamps to string for JSON)
        cache_data = df.copy()
        cache_data['datetime'] = cache_data['datetime'].astype(str)
        with open(cache_file, 'w') as f:
            json.dump(cache_data.to_dict('records'), f)

        logger.info(f"Fetched {len(df)} candles for {symbol}")
        return df

    def calculate_upnl(
        self,
        entry_price: float,
        current_price: float,
        contracts: float,
        leverage: int,
        side: str = "long"
    ) -> Tuple[float, float]:
        """
        Calculate UPNL in USD and percentage.

        Returns:
            Tuple of (upnl_usd, upnl_pct)
        """
        if side == "long":
            price_change_pct = (current_price - entry_price) / entry_price
        else:
            price_change_pct = (entry_price - current_price) / entry_price

        upnl_pct = price_change_pct * leverage
        margin = (contracts * entry_price) / leverage
        upnl_usd = margin * upnl_pct

        return upnl_usd, upnl_pct

    def calculate_weighted_entry(self, entries: List[Tuple[float, float, datetime]]) -> float:
        """Calculate weighted average entry price from averaging entries"""
        if not entries:
            return 0.0

        total_contracts = sum(c for _, c, _ in entries)
        if total_contracts == 0:
            return 0.0

        weighted_sum = sum(p * c for p, c, _ in entries)
        return weighted_sum / total_contracts

    def simulate_position(
        self,
        df: pd.DataFrame,
        config: BacktestConfig,
        entry_idx: int = 0,
        side: str = "long"
    ) -> PositionState:
        """
        Simulate a position through the price data.

        Args:
            df: OHLCV DataFrame
            config: Backtest configuration
            entry_idx: Index to start position
            side: 'long' or 'short'

        Returns:
            Final position state
        """
        entry_row = df.iloc[entry_idx]
        entry_price = entry_row['close']
        entry_time = entry_row['datetime']

        # Initial position
        initial_contracts = (config.initial_margin_usd * config.leverage) / entry_price

        position = PositionState(
            symbol=f"BACKTEST",
            entry_price=entry_price,
            entry_time=entry_time,
            contracts=initial_contracts,
            margin=config.initial_margin_usd,
            leverage=config.leverage,
            side=side,
            averaging_entries=[(entry_price, initial_contracts, entry_time)]
        )

        original_contracts = initial_contracts
        averaging_threshold = config.averaging_threshold

        # Simulate through price data
        for idx in range(entry_idx + 1, len(df)):
            row = df.iloc[idx]
            current_price = row['close']
            current_time = row['datetime']

            # Calculate weighted entry
            weighted_entry = self.calculate_weighted_entry(position.averaging_entries)

            # Calculate current UPNL
            upnl_usd, upnl_pct = self.calculate_upnl(
                weighted_entry, current_price, position.contracts, config.leverage, side
            )

            # Update peak tracking
            if upnl_usd > position.peak_upnl:
                position.peak_upnl = upnl_usd
                position.peak_time = current_time

            # Check for averaging (during drawdown)
            if (position.averaging_steps < config.max_averaging_steps and
                upnl_pct <= averaging_threshold):

                # Execute averaging step
                multiplier = config.fibonacci_multipliers[
                    min(position.averaging_steps, len(config.fibonacci_multipliers) - 1)
                ]
                new_contracts = initial_contracts * multiplier
                position.averaging_entries.append((current_price, new_contracts, current_time))
                position.contracts += new_contracts
                position.averaging_steps += 1

                # Deeper threshold for next step
                averaging_threshold -= 0.08

                # Update margin
                position.margin = (position.contracts * weighted_entry) / config.leverage

            # Surplus dump logic (only after averaging and in profit)
            surplus_contracts = position.contracts - original_contracts

            if surplus_contracts > 0 and position.peak_upnl > 0.10:
                # Stage 1
                if (position.surplus_dump_stage == 0 and
                    upnl_usd <= position.peak_upnl * config.stage1_threshold):

                    dump_contracts = surplus_contracts * 0.5
                    profit_per_contract = (current_price - weighted_entry) * config.leverage
                    captured = dump_contracts * profit_per_contract
                    position.total_captured += captured
                    position.contracts -= dump_contracts
                    position.surplus_dump_stage = 1

                    logger.debug(f"Stage 1 dump at {current_time}: captured ${captured:.2f}")

                # Stage 2
                elif (position.surplus_dump_stage == 1 and
                      upnl_usd <= position.peak_upnl * config.stage2_threshold):

                    remaining_surplus = position.contracts - original_contracts
                    profit_per_contract = (current_price - weighted_entry) * config.leverage
                    captured = remaining_surplus * profit_per_contract
                    position.total_captured += captured
                    position.contracts = original_contracts
                    position.surplus_dump_stage = 2
                    position.is_closed = True
                    position.close_price = current_price
                    position.close_time = current_time
                    position.close_reason = "surplus_dump_stage2"

                    logger.debug(f"Stage 2 dump at {current_time}: captured ${captured:.2f}")
                    break

        # If position still open, calculate final value
        if not position.is_closed:
            final_row = df.iloc[-1]
            final_price = final_row['close']
            weighted_entry = self.calculate_weighted_entry(position.averaging_entries)
            final_upnl, _ = self.calculate_upnl(
                weighted_entry, final_price, position.contracts, config.leverage, side
            )
            position.close_price = final_price
            position.close_time = final_row['datetime']
            position.close_reason = "end_of_data"

        return position

    def run_backtest(
        self,
        symbol: str,
        configs: List[Tuple[str, BacktestConfig]],
        timeframe: str = '5m',
        days: int = 7,
        entry_interval: int = 50  # Test entry every N candles
    ) -> Dict:
        """
        Run backtest with multiple configurations on real data.

        Args:
            symbol: Trading pair
            configs: List of (name, config) tuples to test
            timeframe: Candle timeframe
            days: Days of history to test
            entry_interval: How often to test new entry points

        Returns:
            Results dictionary with comparison
        """
        # Fetch data
        df = self.fetch_ohlcv(symbol, timeframe, days)

        if len(df) < 100:
            logger.error(f"Insufficient data for {symbol}")
            return {}

        results = {}

        print("=" * 80)
        print(f"REAL DATA BACKTEST - {symbol}")
        print(f"Data: {len(df)} candles from {df['datetime'].iloc[0]} to {df['datetime'].iloc[-1]}")
        print("=" * 80)
        print()

        for name, config in configs:
            results[name] = {
                'positions': [],
                'total_captured': 0,
                'total_final_value': 0,
                'avg_capture_rate': 0,
                'wins': 0,
                'losses': 0
            }

            # Test multiple entry points
            entry_points = range(0, len(df) - 200, entry_interval)

            for entry_idx in entry_points:
                position = self.simulate_position(df, config, entry_idx)

                # Calculate final P&L
                weighted_entry = self.calculate_weighted_entry(position.averaging_entries)
                final_upnl, _ = self.calculate_upnl(
                    weighted_entry, position.close_price,
                    position.contracts, config.leverage
                )

                total_value = position.total_captured + final_upnl
                capture_rate = position.total_captured / position.peak_upnl if position.peak_upnl > 0 else 0

                results[name]['positions'].append({
                    'entry_time': str(position.entry_time),
                    'close_time': str(position.close_time),
                    'entry_price': position.entry_price,
                    'close_price': position.close_price,
                    'weighted_entry': weighted_entry,
                    'averaging_steps': position.averaging_steps,
                    'peak_upnl': position.peak_upnl,
                    'captured': position.total_captured,
                    'final_upnl': final_upnl,
                    'total_value': total_value,
                    'capture_rate': capture_rate,
                    'close_reason': position.close_reason
                })

                results[name]['total_captured'] += position.total_captured
                results[name]['total_final_value'] += total_value

                if total_value > 0:
                    results[name]['wins'] += 1
                else:
                    results[name]['losses'] += 1

            # Calculate averages
            n_positions = len(results[name]['positions'])
            if n_positions > 0:
                results[name]['avg_capture_rate'] = np.mean([
                    p['capture_rate'] for p in results[name]['positions'] if p['peak_upnl'] > 0
                ])
                results[name]['avg_peak_upnl'] = np.mean([
                    p['peak_upnl'] for p in results[name]['positions']
                ])
                results[name]['win_rate'] = results[name]['wins'] / n_positions

            print(f"{name:<30} Captured: ${results[name]['total_captured']:>10.2f}  "
                  f"Total Value: ${results[name]['total_final_value']:>10.2f}  "
                  f"Win Rate: {results[name].get('win_rate', 0)*100:.1f}%")

        return results

    def print_comparison(self, results: Dict):
        """Print formatted comparison of results"""

        print("\n" + "=" * 80)
        print("BACKTEST RESULTS COMPARISON")
        print("=" * 80)

        # Sort by total value
        sorted_configs = sorted(
            results.keys(),
            key=lambda k: results[k]['total_final_value'],
            reverse=True
        )

        print(f"\n{'Rank':<6} {'Config':<30} {'Captured':<15} {'Total Value':<15} {'Win Rate':<12}")
        print("-" * 80)

        for rank, name in enumerate(sorted_configs, 1):
            r = results[name]
            print(f"{rank:<6} {name:<30} ${r['total_captured']:<14.2f} "
                  f"${r['total_final_value']:<14.2f} {r.get('win_rate', 0)*100:<11.1f}%")

        # Compare best vs current
        if len(sorted_configs) >= 2:
            best = sorted_configs[0]
            current_configs = [c for c in sorted_configs if 'Current' in c or '85/30' in c]

            if current_configs:
                current = current_configs[0]
                best_value = results[best]['total_final_value']
                current_value = results[current]['total_final_value']

                if current_value != 0:
                    improvement = ((best_value - current_value) / abs(current_value)) * 100

                    print(f"\n{'='*80}")
                    print("RECOMMENDATION")
                    print(f"{'='*80}")
                    print(f"\nBest config: {best}")
                    print(f"vs Current:  {current}")
                    print(f"Improvement: {improvement:+.1f}%")

        return sorted_configs[0] if sorted_configs else None


def test_adverse_recovery_thresholds():
    """Test different thresholds specifically for adverse recovery scenario (AXS-like)"""

    backtest = RealDataBacktest()

    # Define configurations to test
    configs = [
        ("85/30 (Current)", BacktestConfig(stage1_threshold=0.85, stage2_threshold=0.30)),
        ("85/40", BacktestConfig(stage1_threshold=0.85, stage2_threshold=0.40)),
        ("75/30", BacktestConfig(stage1_threshold=0.75, stage2_threshold=0.30)),
        ("70/25", BacktestConfig(stage1_threshold=0.70, stage2_threshold=0.25)),
        ("65/20", BacktestConfig(stage1_threshold=0.65, stage2_threshold=0.20)),
        ("50/20 (Hold Longer)", BacktestConfig(stage1_threshold=0.50, stage2_threshold=0.20)),
        ("50/15 (Max Hold)", BacktestConfig(stage1_threshold=0.50, stage2_threshold=0.15)),
    ]

    # Test on AXS
    print("\n" + "=" * 80)
    print("TESTING ON AXS/USDT:USDT (Real Data)")
    print("=" * 80)

    results_axs = backtest.run_backtest(
        'AXS/USDT:USDT',
        configs,
        timeframe='5m',
        days=7,
        entry_interval=100
    )

    backtest.print_comparison(results_axs)

    # Save results
    output = {
        'timestamp': datetime.now().isoformat(),
        'symbol': 'AXS/USDT:USDT',
        'results': {k: {kk: vv for kk, vv in v.items() if kk != 'positions'}
                   for k, v in results_axs.items()}
    }

    with open('/root/ai_xyz/backtest_real_data_results.json', 'w') as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n✅ Results saved to backtest_real_data_results.json")

    return results_axs


def test_multiple_symbols():
    """Test thresholds across multiple symbols for robustness"""

    backtest = RealDataBacktest()

    configs = [
        ("85/30 (Current)", BacktestConfig(stage1_threshold=0.85, stage2_threshold=0.30)),
        ("50/20 (Hold Longer)", BacktestConfig(stage1_threshold=0.50, stage2_threshold=0.20)),
    ]

    symbols = [
        'AXS/USDT:USDT',
        'BLUR/USDT:USDT',
        'DASH/USDT:USDT',
        'DYM/USDT:USDT',
    ]

    all_results = {}

    for symbol in symbols:
        try:
            print(f"\n{'='*80}")
            print(f"Testing {symbol}")
            print("=" * 80)

            results = backtest.run_backtest(
                symbol,
                configs,
                timeframe='5m',
                days=7,
                entry_interval=100
            )

            all_results[symbol] = results

        except Exception as e:
            logger.error(f"Error testing {symbol}: {e}")

    # Aggregate comparison
    print("\n" + "=" * 80)
    print("AGGREGATE RESULTS ACROSS ALL SYMBOLS")
    print("=" * 80)

    aggregate = {}
    for config_name in ['85/30 (Current)', '50/20 (Hold Longer)']:
        aggregate[config_name] = {
            'total_captured': 0,
            'total_final_value': 0,
            'symbols_tested': 0
        }

        for symbol, results in all_results.items():
            if config_name in results:
                aggregate[config_name]['total_captured'] += results[config_name]['total_captured']
                aggregate[config_name]['total_final_value'] += results[config_name]['total_final_value']
                aggregate[config_name]['symbols_tested'] += 1

    for name, data in aggregate.items():
        print(f"{name:<30} Captured: ${data['total_captured']:>10.2f}  "
              f"Total: ${data['total_final_value']:>10.2f}")

    return all_results


if __name__ == "__main__":
    print(f"\n{'='*80}")
    print("AI-XYZ Real Data Backtest Engine")
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"{'='*80}\n")

    # Test adverse recovery thresholds on AXS
    results = test_adverse_recovery_thresholds()
