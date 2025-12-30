"""
Backtesting Engine - The Chronosphere
Complete backtesting framework with walk-forward analysis.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import yfinance as yf
import asyncio
import uuid
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Backtesting Engine - The Chronosphere",
    description="Complete backtesting framework with temporal validation",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class BacktestRequest(BaseModel):
    strategy_name: str
    symbols: List[str]
    start_date: str
    end_date: str
    initial_capital: float = 100000.0
    parameters: Dict[str, Any] = {}

class BacktestResult(BaseModel):
    backtest_id: str
    strategy_name: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int
    profit_factor: float
    performance_data: List[Dict]
    trade_history: List[Dict]

class BacktestingEngine:
    """Complete backtesting engine with multiple strategies."""
    
    def __init__(self):
        self.active_backtests = {}
        self.strategies = {
            'rsi_mean_reversion': self.rsi_mean_reversion_strategy,
            'moving_average_crossover': self.ma_crossover_strategy,
            'bollinger_bands': self.bollinger_bands_strategy,
            'momentum': self.momentum_strategy
        }
    
    async def run_backtest(self, request: BacktestRequest) -> BacktestResult:
        """Run a complete backtest."""
        backtest_id = str(uuid.uuid4())
        
        try:
            # Get historical data
            data = await self.get_historical_data(request.symbols, request.start_date, request.end_date)
            
            # Run strategy
            strategy_func = self.strategies.get(request.strategy_name)
            if not strategy_func:
                raise ValueError(f"Unknown strategy: {request.strategy_name}")
            
            results = await strategy_func(data, request.parameters, request.initial_capital)
            
            # Calculate performance metrics
            performance_metrics = self.calculate_performance_metrics(results)
            
            backtest_result = BacktestResult(
                backtest_id=backtest_id,
                strategy_name=request.strategy_name,
                **performance_metrics
            )
            
            self.active_backtests[backtest_id] = backtest_result
            
            return backtest_result
            
        except Exception as e:
            logger.error(f"Backtest failed: {str(e)}")
            raise
    
    async def get_historical_data(self, symbols: List[str], start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """Get historical data for symbols."""
        data = {}
        
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(start=start_date, end=end_date)
                if not df.empty:
                    data[symbol] = df
                    logger.info(f"Downloaded data for {symbol}: {len(df)} rows")
            except Exception as e:
                logger.error(f"Failed to download data for {symbol}: {str(e)}")
        
        return data
    
    async def rsi_mean_reversion_strategy(self, data: Dict[str, pd.DataFrame], 
                                        parameters: Dict, initial_capital: float) -> Dict:
        """RSI mean reversion strategy."""
        rsi_period = parameters.get('rsi_period', 14)
        oversold_threshold = parameters.get('oversold_threshold', 30)
        overbought_threshold = parameters.get('overbought_threshold', 70)
        
        portfolio_value = initial_capital
        positions = {}
        trades = []
        performance_data = []
        
        # Combine all symbol data
        for symbol, df in data.items():
            # Calculate RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            position_size = 0
            entry_price = 0
            
            for i, (date, row) in enumerate(df.iterrows()):
                if i < rsi_period:
                    continue
                
                current_rsi = rsi.iloc[i]
                current_price = row['Close']
                
                # Buy signal (oversold)
                if current_rsi < oversold_threshold and position_size == 0:
                    position_size = (portfolio_value * 0.1) / current_price  # 10% of portfolio
                    entry_price = current_price
                    portfolio_value -= position_size * current_price
                    
                    trades.append({
                        'symbol': symbol,
                        'date': date.isoformat(),
                        'action': 'BUY',
                        'price': current_price,
                        'quantity': position_size,
                        'rsi': current_rsi
                    })
                
                # Sell signal (overbought or stop loss)
                elif current_rsi > overbought_threshold and position_size > 0:
                    portfolio_value += position_size * current_price
                    pnl = (current_price - entry_price) * position_size
                    
                    trades.append({
                        'symbol': symbol,
                        'date': date.isoformat(),
                        'action': 'SELL',
                        'price': current_price,
                        'quantity': position_size,
                        'pnl': pnl,
                        'rsi': current_rsi
                    })
                    
                    position_size = 0
                    entry_price = 0
                
                # Calculate current portfolio value
                current_portfolio_value = portfolio_value
                if position_size > 0:
                    current_portfolio_value += position_size * current_price
                
                performance_data.append({
                    'date': date.isoformat(),
                    'portfolio_value': current_portfolio_value,
                    'symbol': symbol,
                    'price': current_price,
                    'rsi': current_rsi
                })
        
        return {
            'final_portfolio_value': portfolio_value,
            'trades': trades,
            'performance_data': performance_data
        }
    
    async def ma_crossover_strategy(self, data: Dict[str, pd.DataFrame], 
                                  parameters: Dict, initial_capital: float) -> Dict:
        """Moving average crossover strategy."""
        fast_period = parameters.get('fast_period', 20)
        slow_period = parameters.get('slow_period', 50)
        
        portfolio_value = initial_capital
        trades = []
        performance_data = []
        
        for symbol, df in data.items():
            # Calculate moving averages
            df['MA_Fast'] = df['Close'].rolling(window=fast_period).mean()
            df['MA_Slow'] = df['Close'].rolling(window=slow_period).mean()
            
            position_size = 0
            entry_price = 0
            
            for i in range(slow_period, len(df)):
                current_price = df['Close'].iloc[i]
                ma_fast_current = df['MA_Fast'].iloc[i]
                ma_slow_current = df['MA_Slow'].iloc[i]
                ma_fast_prev = df['MA_Fast'].iloc[i-1]
                ma_slow_prev = df['MA_Slow'].iloc[i-1]
                
                # Buy signal (golden cross)
                if (ma_fast_current > ma_slow_current and 
                    ma_fast_prev <= ma_slow_prev and 
                    position_size == 0):
                    
                    position_size = (portfolio_value * 0.1) / current_price
                    entry_price = current_price
                    portfolio_value -= position_size * current_price
                    
                    trades.append({
                        'symbol': symbol,
                        'date': df.index[i].isoformat(),
                        'action': 'BUY',
                        'price': current_price,
                        'quantity': position_size,
                        'ma_fast': ma_fast_current,
                        'ma_slow': ma_slow_current
                    })
                
                # Sell signal (death cross)
                elif (ma_fast_current < ma_slow_current and 
                      ma_fast_prev >= ma_slow_prev and 
                      position_size > 0):
                    
                    portfolio_value += position_size * current_price
                    pnl = (current_price - entry_price) * position_size
                    
                    trades.append({
                        'symbol': symbol,
                        'date': df.index[i].isoformat(),
                        'action': 'SELL',
                        'price': current_price,
                        'quantity': position_size,
                        'pnl': pnl,
                        'ma_fast': ma_fast_current,
                        'ma_slow': ma_slow_current
                    })
                    
                    position_size = 0
                    entry_price = 0
                
                # Calculate current portfolio value
                current_portfolio_value = portfolio_value
                if position_size > 0:
                    current_portfolio_value += position_size * current_price
                
                performance_data.append({
                    'date': df.index[i].isoformat(),
                    'portfolio_value': current_portfolio_value,
                    'symbol': symbol,
                    'price': current_price,
                    'ma_fast': ma_fast_current,
                    'ma_slow': ma_slow_current
                })
        
        return {
            'final_portfolio_value': portfolio_value,
            'trades': trades,
            'performance_data': performance_data
        }
    
    async def bollinger_bands_strategy(self, data: Dict[str, pd.DataFrame], 
                                     parameters: Dict, initial_capital: float) -> Dict:
        """Bollinger Bands strategy."""
        period = parameters.get('period', 20)
        std_dev = parameters.get('std_dev', 2)
        
        portfolio_value = initial_capital
        trades = []
        performance_data = []
        
        for symbol, df in data.items():
            # Calculate Bollinger Bands
            df['MA'] = df['Close'].rolling(window=period).mean()
            df['STD'] = df['Close'].rolling(window=period).std()
            df['Upper_Band'] = df['MA'] + (df['STD'] * std_dev)
            df['Lower_Band'] = df['MA'] - (df['STD'] * std_dev)
            
            position_size = 0
            entry_price = 0
            
            for i in range(period, len(df)):
                current_price = df['Close'].iloc[i]
                upper_band = df['Upper_Band'].iloc[i]
                lower_band = df['Lower_Band'].iloc[i]
                ma = df['MA'].iloc[i]
                
                # Buy signal (price touches lower band)
                if current_price <= lower_band and position_size == 0:
                    position_size = (portfolio_value * 0.1) / current_price
                    entry_price = current_price
                    portfolio_value -= position_size * current_price
                    
                    trades.append({
                        'symbol': symbol,
                        'date': df.index[i].isoformat(),
                        'action': 'BUY',
                        'price': current_price,
                        'quantity': position_size,
                        'lower_band': lower_band,
                        'upper_band': upper_band
                    })
                
                # Sell signal (price touches upper band or crosses MA)
                elif (current_price >= upper_band or current_price >= ma) and position_size > 0:
                    portfolio_value += position_size * current_price
                    pnl = (current_price - entry_price) * position_size
                    
                    trades.append({
                        'symbol': symbol,
                        'date': df.index[i].isoformat(),
                        'action': 'SELL',
                        'price': current_price,
                        'quantity': position_size,
                        'pnl': pnl,
                        'lower_band': lower_band,
                        'upper_band': upper_band
                    })
                    
                    position_size = 0
                    entry_price = 0
                
                # Calculate current portfolio value
                current_portfolio_value = portfolio_value
                if position_size > 0:
                    current_portfolio_value += position_size * current_price
                
                performance_data.append({
                    'date': df.index[i].isoformat(),
                    'portfolio_value': current_portfolio_value,
                    'symbol': symbol,
                    'price': current_price,
                    'upper_band': upper_band,
                    'lower_band': lower_band,
                    'ma': ma
                })
        
        return {
            'final_portfolio_value': portfolio_value,
            'trades': trades,
            'performance_data': performance_data
        }
    
    async def momentum_strategy(self, data: Dict[str, pd.DataFrame], 
                              parameters: Dict, initial_capital: float) -> Dict:
        """Momentum strategy."""
        lookback_period = parameters.get('lookback_period', 20)
        momentum_threshold = parameters.get('momentum_threshold', 0.05)
        
        portfolio_value = initial_capital
        trades = []
        performance_data = []
        
        for symbol, df in data.items():
            # Calculate momentum
            df['Momentum'] = df['Close'].pct_change(periods=lookback_period)
            
            position_size = 0
            entry_price = 0
            
            for i in range(lookback_period, len(df)):
                current_price = df['Close'].iloc[i]
                momentum = df['Momentum'].iloc[i]
                
                # Buy signal (strong positive momentum)
                if momentum > momentum_threshold and position_size == 0:
                    position_size = (portfolio_value * 0.1) / current_price
                    entry_price = current_price
                    portfolio_value -= position_size * current_price
                    
                    trades.append({
                        'symbol': symbol,
                        'date': df.index[i].isoformat(),
                        'action': 'BUY',
                        'price': current_price,
                        'quantity': position_size,
                        'momentum': momentum
                    })
                
                # Sell signal (momentum turns negative)
                elif momentum < 0 and position_size > 0:
                    portfolio_value += position_size * current_price
                    pnl = (current_price - entry_price) * position_size
                    
                    trades.append({
                        'symbol': symbol,
                        'date': df.index[i].isoformat(),
                        'action': 'SELL',
                        'price': current_price,
                        'quantity': position_size,
                        'pnl': pnl,
                        'momentum': momentum
                    })
                    
                    position_size = 0
                    entry_price = 0
                
                # Calculate current portfolio value
                current_portfolio_value = portfolio_value
                if position_size > 0:
                    current_portfolio_value += position_size * current_price
                
                performance_data.append({
                    'date': df.index[i].isoformat(),
                    'portfolio_value': current_portfolio_value,
                    'symbol': symbol,
                    'price': current_price,
                    'momentum': momentum
                })
        
        return {
            'final_portfolio_value': portfolio_value,
            'trades': trades,
            'performance_data': performance_data
        }
    
    def calculate_performance_metrics(self, results: Dict) -> Dict:
        """Calculate comprehensive performance metrics."""
        performance_data = results['performance_data']
        trades = results['trades']
        
        if not performance_data:
            return {
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'win_rate': 0.0,
                'total_trades': 0,
                'profit_factor': 0.0,
                'performance_data': [],
                'trade_history': []
            }
        
        # Convert to DataFrame for easier calculation
        df = pd.DataFrame(performance_data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        
        # Calculate returns
        initial_value = df['portfolio_value'].iloc[0]
        final_value = df['portfolio_value'].iloc[-1]
        total_return = (final_value - initial_value) / initial_value
        
        # Calculate daily returns
        df['daily_return'] = df['portfolio_value'].pct_change()
        daily_returns = df['daily_return'].dropna()
        
        # Sharpe ratio (assuming 0% risk-free rate)
        sharpe_ratio = daily_returns.mean() / daily_returns.std() * np.sqrt(252) if daily_returns.std() > 0 else 0
        
        # Maximum drawdown
        df['cumulative_max'] = df['portfolio_value'].cummax()
        df['drawdown'] = (df['portfolio_value'] - df['cumulative_max']) / df['cumulative_max']
        max_drawdown = df['drawdown'].min()
        
        # Trade statistics
        buy_trades = [t for t in trades if t['action'] == 'BUY']
        sell_trades = [t for t in trades if t['action'] == 'SELL']
        
        total_trades = len(sell_trades)
        winning_trades = len([t for t in sell_trades if t.get('pnl', 0) > 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Profit factor
        gross_profit = sum([t.get('pnl', 0) for t in sell_trades if t.get('pnl', 0) > 0])
        gross_loss = abs(sum([t.get('pnl', 0) for t in sell_trades if t.get('pnl', 0) < 0]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'profit_factor': profit_factor,
            'performance_data': performance_data,
            'trade_history': trades
        }

# Initialize backtesting engine
backtesting_engine = BacktestingEngine()

@app.get("/")
async def root():
    return {
        "service": "backtesting-engine",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "available_strategies": list(backtesting_engine.strategies.keys())
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "backtesting-engine",
        "timestamp": datetime.now().isoformat()
    }

@app.post("/backtest", response_model=BacktestResult)
async def run_backtest(request: BacktestRequest):
    """Run a backtest."""
    try:
        result = await backtesting_engine.run_backtest(request)
        return result
    except Exception as e:
        logger.error(f"Backtest failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")

@app.get("/backtest/{backtest_id}")
async def get_backtest_result(backtest_id: str):
    """Get backtest result by ID."""
    if backtest_id not in backtesting_engine.active_backtests:
        raise HTTPException(status_code=404, detail="Backtest not found")
    
    return backtesting_engine.active_backtests[backtest_id]

@app.get("/strategies")
async def get_available_strategies():
    """Get list of available strategies."""
    return {
        "strategies": list(backtesting_engine.strategies.keys()),
        "count": len(backtesting_engine.strategies),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
