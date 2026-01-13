#!/usr/bin/env python3
"""
Backtest API Service
Exposes backtesting functionality via REST API
"""

import os
import json
import asyncio
import uuid
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import logging
import numpy as np
import pandas as pd
import ccxt
from dotenv import load_dotenv

load_dotenv()

# Import backtesting components
from backtesting_service import BacktestingService, DynamicDeltaEngine, FibonacciAveragingOptimizer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize exchange for real data
exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'options': {'defaultType': 'swap'}
})

app = FastAPI(
    title="AI-XYZ Backtesting API",
    description="Backtesting service for Fibonacci averaging strategies",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
backtesting_service = BacktestingService()
delta_engine = DynamicDeltaEngine(backtesting_service)
fibonacci_optimizer = FibonacciAveragingOptimizer(backtesting_service)


# Request/Response models
class AnalyzeRequest(BaseModel):
    symbol: str
    timeframe: str = "1d"
    days: int = 30


class DeltaRequest(BaseModel):
    symbol: str
    current_price: float
    leverage: int = 10


class AveragingPlanRequest(BaseModel):
    symbol: str
    current_price: float
    entry_price: float
    leverage: int = 10
    volatility: float = 1.0
    volume_ratio: float = 1.0


class BacktestRequest(BaseModel):
    symbol: str
    leverage: int = 10
    direction: str = "long"
    averaging_steps: int = 5
    timeframe: str = "5m"
    days: int = 30


# Store for running backtests
backtest_results: Dict[str, Dict] = {}


@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "service": "AI-XYZ Backtesting API",
        "version": "2.0.0",
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    """Health check"""
    return {"status": "ok"}


@app.post("/analyze")
async def analyze_coin(request: AnalyzeRequest):
    """
    Analyze historical performance of a coin
    """
    try:
        result = backtesting_service.analyze_coin_performance(
            request.symbol,
            request.timeframe,
            request.days
        )
        return {
            "symbol": request.symbol,
            "analysis": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/optimal-delta")
async def get_optimal_delta(request: DeltaRequest):
    """
    Calculate optimal delta for a symbol
    """
    try:
        result = backtesting_service.calculate_optimal_delta(
            request.symbol,
            request.current_price,
            request.leverage
        )
        return {
            "symbol": request.symbol,
            "current_price": request.current_price,
            "leverage": request.leverage,
            "optimal_delta": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Delta calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/adaptive-delta")
async def get_adaptive_delta(request: AveragingPlanRequest):
    """
    Calculate adaptive delta based on market conditions
    """
    try:
        market_context = {
            "volatility": request.volatility,
            "volume_ratio": request.volume_ratio,
            "spread_pct": 0.1
        }
        position_data = {
            "current_price": request.current_price,
            "entry_price": request.entry_price,
            "leverage": request.leverage
        }

        result = delta_engine.calculate_adaptive_delta(
            request.symbol,
            market_context,
            position_data
        )
        return {
            "symbol": request.symbol,
            "adaptive_delta": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Adaptive delta calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/averaging-plan")
async def get_averaging_plan(request: AveragingPlanRequest):
    """
    Generate optimal Fibonacci averaging plan
    """
    try:
        market_context = {
            "volatility": request.volatility,
            "volume_ratio": request.volume_ratio,
            "spread_pct": 0.1
        }
        position_data = {
            "current_price": request.current_price,
            "entry_price": request.entry_price,
            "leverage": request.leverage
        }

        result = fibonacci_optimizer.generate_optimal_averaging_plan(
            request.symbol,
            position_data,
            market_context
        )
        return {
            "symbol": request.symbol,
            "averaging_plan": result,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Averaging plan generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/results")
async def get_all_results():
    """
    Get all backtest results
    """
    return {
        "results": backtest_results,
        "count": len(backtest_results),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/results/{backtest_id}")
async def get_result(backtest_id: str):
    """
    Get specific backtest result
    """
    if backtest_id not in backtest_results:
        raise HTTPException(status_code=404, detail="Backtest not found")
    return backtest_results[backtest_id]


@app.delete("/results/{backtest_id}")
async def delete_result(backtest_id: str):
    """
    Delete backtest result
    """
    if backtest_id not in backtest_results:
        raise HTTPException(status_code=404, detail="Backtest not found")
    del backtest_results[backtest_id]
    return {"status": "deleted", "backtest_id": backtest_id}


@app.get("/symbols")
async def get_supported_symbols():
    """
    Get list of symbols that can be backtested
    """
    # Common USDT perpetual futures
    symbols = [
        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
        "XRP/USDT:USDT", "DOGE/USDT:USDT", "AVAX/USDT:USDT",
        "MATIC/USDT:USDT", "LINK/USDT:USDT", "DOT/USDT:USDT",
        "UNI/USDT:USDT", "ATOM/USDT:USDT", "LTC/USDT:USDT",
        "FIL/USDT:USDT", "APT/USDT:USDT", "ARB/USDT:USDT",
        "OP/USDT:USDT", "INJ/USDT:USDT", "SUI/USDT:USDT",
        "SEI/USDT:USDT", "TIA/USDT:USDT", "JUP/USDT:USDT",
        "WIF/USDT:USDT", "PEPE/USDT:USDT", "BONK/USDT:USDT"
    ]
    return {"symbols": symbols, "count": len(symbols)}


@app.get("/metrics")
async def get_service_metrics():
    """
    Get service metrics
    """
    return {
        "total_backtests": len(backtest_results),
        "service_uptime": "healthy",
        "timestamp": datetime.now().isoformat()
    }


# ==================== FULL BACKTEST ENGINE ====================

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI indicator"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def fetch_ohlcv_sync(symbol: str, timeframe: str = '1h', limit: int = 720) -> pd.DataFrame:
    """Fetch historical OHLCV data from exchange"""
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        logger.error(f"Failed to fetch OHLCV: {e}")
        return pd.DataFrame()


def run_fibonacci_backtest(
    df: pd.DataFrame,
    leverage: int = 10,
    direction: str = 'long',
    take_profit_pct: float = 5.0,
    stop_loss_pct: float = -50.0,
    rsi_entry: int = 35,
    rsi_exit: int = 70
) -> Dict:
    """
    Run Fibonacci averaging backtest on historical data

    Returns detailed backtest results
    """
    # Fibonacci averaging config (matching AI-XYZ system)
    fib_multipliers = [1.0, 1.618, 2.618, 4.236, 6.854]
    averaging_thresholds = [-0.05, -0.10, -0.15, -0.20, -0.25]  # % drop triggers

    # Calculate indicators
    df = df.copy()
    df['rsi'] = calculate_rsi(df['close'])
    df['sma20'] = df['close'].rolling(20).mean()
    df['volatility'] = df['close'].pct_change().rolling(20).std() * 100

    trades = []
    position = None

    for i in range(50, len(df)):
        current_price = df['close'].iloc[i]
        current_rsi = df['rsi'].iloc[i]
        current_time = df['timestamp'].iloc[i]

        if position is None:
            # Entry conditions
            should_enter = False
            if direction == 'long' and current_rsi < rsi_entry:
                should_enter = True
            elif direction == 'short' and current_rsi > (100 - rsi_entry):
                should_enter = True

            if should_enter:
                position = {
                    'entry_price': current_price,
                    'entry_time': current_time,
                    'entry_idx': i,
                    'size': 1.0,
                    'avg_price': current_price,
                    'total_size': 1.0,
                    'avg_steps': 0,
                    'peak_pnl': 0,
                    'max_dd': 0,
                    'avg_history': []
                }
        else:
            # Calculate P&L
            if direction == 'long':
                pnl_pct = ((current_price - position['avg_price']) / position['avg_price']) * leverage * 100
            else:
                pnl_pct = ((position['avg_price'] - current_price) / position['avg_price']) * leverage * 100

            position['peak_pnl'] = max(position['peak_pnl'], pnl_pct)
            position['max_dd'] = min(position['max_dd'], pnl_pct)

            # Check averaging
            if position['avg_steps'] < len(averaging_thresholds):
                threshold = averaging_thresholds[position['avg_steps']] * leverage * 100
                if pnl_pct <= threshold:
                    # Execute averaging
                    multiplier = fib_multipliers[position['avg_steps']]
                    add_size = multiplier

                    # Update weighted average
                    old_cost = position['avg_price'] * position['total_size']
                    new_cost = current_price * add_size
                    position['total_size'] += add_size
                    new_avg = (old_cost + new_cost) / position['total_size']

                    position['avg_history'].append({
                        'step': position['avg_steps'] + 1,
                        'price': current_price,
                        'old_avg': position['avg_price'],
                        'new_avg': new_avg,
                        'size_added': add_size,
                        'pnl_at_avg': pnl_pct
                    })

                    position['avg_price'] = new_avg
                    position['avg_steps'] += 1

            # Exit conditions
            exit_reason = None

            # Take profit
            if pnl_pct >= take_profit_pct:
                exit_reason = 'take_profit'
            # Stop loss
            elif pnl_pct <= stop_loss_pct:
                exit_reason = 'stop_loss'
            # Timeout after 200 candles
            elif i - position['entry_idx'] > 200:
                exit_reason = 'timeout'
            # RSI exit (only in profit)
            elif direction == 'long' and current_rsi > rsi_exit and pnl_pct > 0:
                exit_reason = 'rsi_exit'
            elif direction == 'short' and current_rsi < (100 - rsi_exit) and pnl_pct > 0:
                exit_reason = 'rsi_exit'

            if exit_reason:
                trade = {
                    'entry_price': float(position['entry_price']),
                    'entry_time': position['entry_time'].isoformat() if hasattr(position['entry_time'], 'isoformat') else str(position['entry_time']),
                    'exit_time': current_time.isoformat() if hasattr(current_time, 'isoformat') else str(current_time),
                    'avg_price': float(position['avg_price']),
                    'exit_price': float(current_price),
                    'pnl_pct': float(round(pnl_pct, 2)),
                    'avg_steps': int(position['avg_steps']),
                    'total_size': float(position['total_size']),
                    'duration_candles': int(i - position['entry_idx']),
                    'exit_reason': exit_reason,
                    'peak_pnl': float(round(position['peak_pnl'], 2)),
                    'max_dd': float(round(position['max_dd'], 2)),
                    'averaging_history': position['avg_history'],
                    'is_winner': bool(pnl_pct > 0)
                }
                trades.append(trade)
                position = None

    # Calculate summary statistics
    if not trades:
        return {'error': 'No trades executed', 'trades': []}

    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]

    total_pnl = sum(t['pnl_pct'] for t in trades)
    gross_profit = sum(t['pnl_pct'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl_pct'] for t in losses)) if losses else 0.001  # Avoid division by zero

    avg_steps = [t['avg_steps'] for t in trades]
    durations = [t['duration_candles'] for t in trades]
    max_dds = [t['max_dd'] for t in trades]

    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        r = t['exit_reason']
        exit_reasons[r] = exit_reasons.get(r, 0) + 1

    # Averaging analysis
    trades_with_avg = [t for t in trades if t['avg_steps'] > 0]
    avg_recovery_rate = 0
    if trades_with_avg:
        avg_wins = [t for t in trades_with_avg if t['pnl_pct'] > 0]
        avg_recovery_rate = len(avg_wins) / len(trades_with_avg) * 100

    return {
        'summary': {
            'total_trades': int(len(trades)),
            'wins': int(len(wins)),
            'losses': int(len(losses)),
            'win_rate': float(round(len(wins) / len(trades) * 100, 1)),
            'total_pnl_pct': float(round(total_pnl, 2)),
            'gross_profit_pct': float(round(gross_profit, 2)),
            'gross_loss_pct': float(round(gross_loss, 2)),
            'profit_factor': float(round(gross_profit / gross_loss, 2)) if gross_loss > 0 else 999.99,
            'avg_win_pct': float(round(gross_profit / len(wins), 2)) if wins else 0.0,
            'avg_loss_pct': float(round(-gross_loss / len(losses), 2)) if losses else 0.0,
            'expectancy': float(round(total_pnl / len(trades), 2))
        },
        'averaging_analysis': {
            'avg_steps_used': float(round(np.mean(avg_steps), 2)),
            'max_steps_used': int(max(avg_steps)),
            'trades_with_averaging': int(len(trades_with_avg)),
            'averaging_recovery_rate': float(round(avg_recovery_rate, 1))
        },
        'timing': {
            'avg_duration_candles': float(round(np.mean(durations), 1)),
            'longest_trade_candles': int(max(durations)),
            'shortest_trade_candles': int(min(durations))
        },
        'risk_metrics': {
            'avg_max_drawdown_pct': float(round(np.mean(max_dds), 2)),
            'worst_drawdown_pct': float(round(min(max_dds), 2)),
            'best_peak_pnl_pct': float(round(max(t['peak_pnl'] for t in trades), 2))
        },
        'exit_reasons': exit_reasons,
        'trades': trades[-20:]  # Last 20 trades for detail
    }


class FullBacktestRequest(BaseModel):
    symbol: str
    timeframe: str = "1h"
    candles: int = 720
    leverage: int = 10
    direction: str = "long"
    take_profit_pct: float = 5.0
    stop_loss_pct: float = -50.0
    rsi_entry: int = 35
    rsi_exit: int = 70


@app.post("/backtest")
async def run_backtest(request: FullBacktestRequest):
    """
    Run full Fibonacci averaging backtest with real exchange data

    Parameters:
    - symbol: Trading pair (e.g., "API3/USDT:USDT")
    - timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
    - candles: Number of historical candles (max 1000)
    - leverage: Trading leverage
    - direction: "long" or "short"
    - take_profit_pct: Take profit percentage
    - stop_loss_pct: Stop loss percentage (negative)
    - rsi_entry: RSI threshold for entry
    - rsi_exit: RSI threshold for exit
    """
    try:
        backtest_id = str(uuid.uuid4())[:8]
        logger.info(f"Starting backtest {backtest_id} for {request.symbol}")

        # Fetch historical data
        df = fetch_ohlcv_sync(request.symbol, request.timeframe, min(request.candles, 1000))

        if df.empty:
            raise HTTPException(status_code=400, detail="Failed to fetch historical data")

        # Run backtest
        results = run_fibonacci_backtest(
            df=df,
            leverage=request.leverage,
            direction=request.direction,
            take_profit_pct=request.take_profit_pct,
            stop_loss_pct=request.stop_loss_pct,
            rsi_entry=request.rsi_entry,
            rsi_exit=request.rsi_exit
        )

        # Store results
        backtest_results[backtest_id] = {
            'id': backtest_id,
            'symbol': request.symbol,
            'config': {
                'timeframe': request.timeframe,
                'candles': len(df),
                'leverage': request.leverage,
                'direction': request.direction,
                'take_profit_pct': request.take_profit_pct,
                'stop_loss_pct': request.stop_loss_pct,
                'rsi_entry': request.rsi_entry,
                'rsi_exit': request.rsi_exit
            },
            'data_range': {
                'start': df['timestamp'].iloc[0].isoformat() if not df.empty else None,
                'end': df['timestamp'].iloc[-1].isoformat() if not df.empty else None
            },
            'results': results,
            'timestamp': datetime.now().isoformat()
        }

        return backtest_results[backtest_id]

    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/backtest/compare")
async def compare_backtests(symbols: List[str], timeframe: str = "1h", leverage: int = 10):
    """
    Run backtests on multiple symbols and compare results
    """
    results = {}
    for symbol in symbols[:10]:  # Limit to 10 symbols
        try:
            df = fetch_ohlcv_sync(symbol, timeframe, 720)
            if not df.empty:
                bt_result = run_fibonacci_backtest(df, leverage=leverage)
                results[symbol] = {
                    'win_rate': bt_result['summary']['win_rate'],
                    'profit_factor': bt_result['summary']['profit_factor'],
                    'total_pnl': bt_result['summary']['total_pnl_pct'],
                    'total_trades': bt_result['summary']['total_trades'],
                    'avg_recovery_rate': bt_result['averaging_analysis']['averaging_recovery_rate']
                }
        except Exception as e:
            results[symbol] = {'error': str(e)}

    # Rank by profit factor
    ranked = sorted(
        [(s, r) for s, r in results.items() if 'profit_factor' in r],
        key=lambda x: x[1]['profit_factor'],
        reverse=True
    )

    return {
        'comparison': results,
        'ranking': [{'symbol': s, **r} for s, r in ranked],
        'timestamp': datetime.now().isoformat()
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting Backtest API on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)
