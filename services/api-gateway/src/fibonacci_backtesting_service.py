"""
Enhanced Fibonacci Service with Backtesting and Candle Storage
Includes historical data caching and backtesting results
"""

import os
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional, Union
from dataclasses import dataclass, asdict
from enum import Enum
import json
import structlog
import redis
import ccxt.async_support as ccxt
from datetime import datetime, timedelta
import asyncio
import hashlib

logger = structlog.get_logger(__name__)

class TradeDirection(Enum):
    """Trade direction enumeration."""
    LONG = "long"
    SHORT = "short"

@dataclass
class BacktestResult:
    """Results from backtesting Fibonacci configuration"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_return: float
    max_drawdown: float
    win_rate: float
    sharpe_ratio: float
    average_trade_duration: float
    best_trade: float
    worst_trade: float
    recovery_rate: float  # How often position recovers after averaging
    liquidation_events: int
    averaging_effectiveness: float  # How much averaging improved outcomes

@dataclass 
class CandleData:
    """Historical candle data for backtesting"""
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class CandleStorage:
    """Stores and manages historical candle data for reuse"""
    
    def __init__(self):
        redis_host = os.getenv('REDIS_HOST', 'localhost')
        redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, db=1, decode_responses=False)
        self.cache_ttl = 3600  # 1 hour cache
        
    def _get_cache_key(self, symbol: str, timeframe: str, limit: int) -> str:
        """Generate cache key for candle data"""
        return f"candles:{symbol}:{timeframe}:{limit}"
    
    async def get_candles(self, exchange: ccxt.Exchange, symbol: str, 
                         timeframe: str = '5m', limit: int = 2000) -> List[Dict]:
        """
        Get candles from cache or fetch from exchange
        
        Args:
            exchange: CCXT exchange instance
            symbol: Trading symbol
            timeframe: Candle timeframe
            limit: Number of candles
            
        Returns:
            List of candle dictionaries
        """
        cache_key = self._get_cache_key(symbol, timeframe, limit)
        
        # Try to get from cache
        cached_data = self.redis_client.get(cache_key)
        if cached_data:
            logger.debug(f"Using cached candles for {symbol} {timeframe}")
            return json.loads(cached_data)
        
        # Fetch from exchange
        logger.info(f"Fetching {limit} {timeframe} candles for {symbol}")
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            # Convert to list of dicts
            candles = []
            for candle in ohlcv:
                candles.append({
                    'timestamp': candle[0],
                    'open': candle[1],
                    'high': candle[2],
                    'low': candle[3],
                    'close': candle[4],
                    'volume': candle[5]
                })
            
            # Store in cache
            self.redis_client.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(candles)
            )
            
            logger.info(f"Cached {len(candles)} candles for {symbol}")
            return candles
            
        except Exception as e:
            logger.error(f"Error fetching candles: {e}")
            return []
    
    def clear_cache(self, symbol: Optional[str] = None):
        """Clear candle cache"""
        if symbol:
            pattern = f"candles:{symbol}:*"
        else:
            pattern = "candles:*"
        
        for key in self.redis_client.scan_iter(pattern):
            self.redis_client.delete(key)
        
        logger.info(f"Cleared candle cache for pattern: {pattern}")

class FibonacciBacktester:
    """Backtests Fibonacci averaging strategies using historical data"""
    
    def __init__(self):
        self.candle_storage = CandleStorage()
        
    def calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """Calculate RSI for price series"""
        if len(prices) < period + 1:
            return [50] * len(prices)
        
        rsi_values = []
        gains = []
        losses = []
        
        # Calculate price changes
        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0)
            else:
                gains.append(0)
                losses.append(abs(change))
        
        # Calculate RSI for each point
        for i in range(period, len(prices)):
            avg_gain = np.mean(gains[i-period:i]) if i >= period else 0
            avg_loss = np.mean(losses[i-period:i]) if i >= period else 0
            
            if avg_loss == 0:
                rsi_values.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi_values.append(100 - (100 / (1 + rs)))
        
        # Pad beginning with neutral RSI
        rsi_values = [50] * period + rsi_values
        
        return rsi_values
    
    async def backtest_configuration(self, 
                                    symbol: str,
                                    averaging_steps: List[Dict],
                                    leverage: float,
                                    direction: TradeDirection,
                                    candles: List[Dict],
                                    entry_conditions: Optional[Dict] = None) -> BacktestResult:
        """
        Backtest a Fibonacci configuration on historical data
        
        Args:
            symbol: Trading symbol
            averaging_steps: List of averaging step configurations
            leverage: Trading leverage
            direction: Trade direction
            candles: Historical candle data
            entry_conditions: Optional entry conditions (RSI, etc.)
            
        Returns:
            BacktestResult with performance metrics
        """
        if not candles or len(candles) < 100:
            logger.error("Insufficient candle data for backtesting")
            return self._empty_result()
        
        # Extract price data
        closes = [c['close'] for c in candles]
        highs = [c['high'] for c in candles]
        lows = [c['low'] for c in candles]
        
        # Calculate indicators
        rsi = self.calculate_rsi(closes)
        
        # Backtest variables
        trades = []
        positions = []
        current_position = None
        
        # Simulate trading
        for i in range(100, len(candles)):
            current_price = closes[i]
            current_rsi = rsi[i]
            
            # Check entry conditions
            if current_position is None:
                should_enter = self._check_entry_conditions(
                    current_rsi, 
                    direction, 
                    entry_conditions
                )
                
                if should_enter:
                    # Open new position
                    current_position = {
                        'entry_price': current_price,
                        'entry_index': i,
                        'direction': direction,
                        'size': 1.0,
                        'averaged_steps': 0,
                        'weighted_avg_price': current_price,
                        'total_size': 1.0,
                        'max_drawdown': 0,
                        'peak_profit': 0
                    }
                    positions.append(current_position)
            
            elif current_position:
                # Calculate current P&L
                if direction == TradeDirection.LONG:
                    pnl_pct = ((current_price - current_position['weighted_avg_price']) / 
                              current_position['weighted_avg_price']) * 100
                else:
                    pnl_pct = ((current_position['weighted_avg_price'] - current_price) / 
                              current_position['weighted_avg_price']) * 100
                
                # Track drawdown and peak
                current_position['max_drawdown'] = min(current_position['max_drawdown'], pnl_pct)
                current_position['peak_profit'] = max(current_position['peak_profit'], pnl_pct)
                
                # Check for averaging
                if current_position['averaged_steps'] < len(averaging_steps):
                    step = averaging_steps[current_position['averaged_steps']]
                    
                    # Check if price hit averaging trigger
                    should_average = False
                    if direction == TradeDirection.LONG:
                        should_average = current_price <= step['price']
                    else:
                        should_average = current_price >= step['price']
                    
                    if should_average:
                        # Execute averaging
                        old_size = current_position['total_size']
                        new_size = step['position_multiplier']
                        
                        # Update weighted average price
                        current_position['weighted_avg_price'] = (
                            (current_position['weighted_avg_price'] * old_size + 
                             current_price * new_size) / (old_size + new_size)
                        )
                        
                        current_position['total_size'] = old_size + new_size
                        current_position['averaged_steps'] += 1
                        
                        logger.debug(f"Averaged at step {current_position['averaged_steps']}, "
                                   f"price={current_price:.4f}, new_avg={current_position['weighted_avg_price']:.4f}")
                
                # Check exit conditions
                should_exit = False
                exit_reason = ""
                
                # Take profit at 15% (configurable)
                if pnl_pct >= 15:
                    should_exit = True
                    exit_reason = "take_profit"
                
                # Stop loss at -50% (considering leverage)
                elif pnl_pct <= -50 / leverage:
                    should_exit = True
                    exit_reason = "stop_loss"
                
                # Exit if position held too long (optional)
                elif i - current_position['entry_index'] > 1000:  # ~80 hours for 5m candles
                    should_exit = True
                    exit_reason = "timeout"
                
                if should_exit:
                    # Close position
                    trade = {
                        'entry_price': current_position['entry_price'],
                        'exit_price': current_price,
                        'weighted_avg_price': current_position['weighted_avg_price'],
                        'direction': direction,
                        'pnl_pct': pnl_pct,
                        'duration': i - current_position['entry_index'],
                        'averaged_steps': current_position['averaged_steps'],
                        'exit_reason': exit_reason,
                        'max_drawdown': current_position['max_drawdown'],
                        'peak_profit': current_position['peak_profit']
                    }
                    trades.append(trade)
                    current_position = None
        
        # Calculate metrics
        return self._calculate_metrics(trades, leverage)
    
    def _check_entry_conditions(self, rsi: float, direction: TradeDirection, 
                               conditions: Optional[Dict]) -> bool:
        """Check if entry conditions are met"""
        if conditions is None:
            # Default conditions
            if direction == TradeDirection.LONG:
                return rsi < 30  # Oversold
            else:
                return rsi > 70  # Overbought
        
        # Custom conditions
        min_rsi = conditions.get('min_rsi', 0)
        max_rsi = conditions.get('max_rsi', 100)
        
        return min_rsi <= rsi <= max_rsi
    
    def _calculate_metrics(self, trades: List[Dict], leverage: float) -> BacktestResult:
        """Calculate backtest metrics from trades"""
        if not trades:
            return self._empty_result()
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t['pnl_pct'] > 0)
        losing_trades = total_trades - winning_trades
        
        # Returns
        returns = [t['pnl_pct'] for t in trades]
        total_return = sum(returns)
        
        # Win rate
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Drawdown
        max_drawdown = min(t['max_drawdown'] for t in trades) if trades else 0
        
        # Sharpe ratio (simplified)
        if len(returns) > 1:
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe_ratio = (avg_return / std_return) * np.sqrt(252) if std_return > 0 else 0
        else:
            sharpe_ratio = 0
        
        # Trade duration
        durations = [t['duration'] for t in trades]
        avg_duration = np.mean(durations) if durations else 0
        
        # Best/worst trades
        best_trade = max(returns) if returns else 0
        worst_trade = min(returns) if returns else 0
        
        # Recovery rate (how often averaging helped)
        averaged_trades = [t for t in trades if t['averaged_steps'] > 0]
        if averaged_trades:
            recovered_trades = sum(1 for t in averaged_trades if t['pnl_pct'] > 0)
            recovery_rate = recovered_trades / len(averaged_trades)
        else:
            recovery_rate = 0
        
        # Liquidation events (positions that hit stop loss)
        liquidation_events = sum(1 for t in trades if t.get('exit_reason') == 'stop_loss')
        
        # Averaging effectiveness
        if averaged_trades:
            avg_with_averaging = np.mean([t['pnl_pct'] for t in averaged_trades])
            avg_without = np.mean([t['pnl_pct'] for t in trades if t['averaged_steps'] == 0])
            averaging_effectiveness = avg_with_averaging - avg_without if avg_without else avg_with_averaging
        else:
            averaging_effectiveness = 0
        
        return BacktestResult(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            total_return=total_return,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            sharpe_ratio=sharpe_ratio,
            average_trade_duration=avg_duration,
            best_trade=best_trade,
            worst_trade=worst_trade,
            recovery_rate=recovery_rate,
            liquidation_events=liquidation_events,
            averaging_effectiveness=averaging_effectiveness
        )
    
    def _empty_result(self) -> BacktestResult:
        """Return empty backtest result"""
        return BacktestResult(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            total_return=0,
            max_drawdown=0,
            win_rate=0,
            sharpe_ratio=0,
            average_trade_duration=0,
            best_trade=0,
            worst_trade=0,
            recovery_rate=0,
            liquidation_events=0,
            averaging_effectiveness=0
        )

class EnhancedFibonacciService:
    """Enhanced Fibonacci service with integrated backtesting"""
    
    def __init__(self):
        self.fibonacci_sequence = [3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610]
        self.backtester = FibonacciBacktester()
        self.candle_storage = CandleStorage()
        self.min_steps = 3
        self.max_steps = 8
        self.liquidation_buffer = 0.05
        
    async def calculate_with_backtest(self,
                                     exchange: ccxt.Exchange,
                                     symbol: str,
                                     delta: float,
                                     entry_price: float,
                                     available_margin: float,
                                     direction: Union[str, TradeDirection],
                                     market_confidence: float = 0.5) -> Dict:
        """
        Calculate Fibonacci parameters with backtesting
        
        Returns complete analysis including backtest results
        """
        try:
            # Convert direction
            if isinstance(direction, str):
                direction = TradeDirection(direction.lower())
            
            # Get historical candles (cached)
            candles = await self.candle_storage.get_candles(
                exchange, symbol, '5m', 2000
            )
            
            if not candles:
                logger.error(f"No candle data available for {symbol}")
                return {'success': False, 'error': 'No historical data'}
            
            # Find optimal configuration
            best_config = None
            best_score = -float('inf')
            best_backtest = None
            
            for num_steps in range(self.min_steps, self.max_steps + 1):
                for leverage in range(7, 11):  # Test 7x to 10x
                    
                    # Calculate Fibonacci configuration
                    config = self._calculate_fibonacci_config(
                        num_steps, leverage, delta, entry_price, 
                        available_margin, direction
                    )
                    
                    if config and config['is_safe']:
                        # Backtest this configuration
                        backtest_result = await self.backtester.backtest_configuration(
                            symbol=symbol,
                            averaging_steps=config['averaging_steps'],
                            leverage=leverage,
                            direction=direction,
                            candles=candles
                        )
                        
                        # Score configuration
                        score = self._score_configuration(
                            config, backtest_result, market_confidence
                        )
                        
                        if score > best_score:
                            best_score = score
                            best_config = config
                            best_backtest = backtest_result
            
            if best_config:
                return {
                    'success': True,
                    'leverage': best_config['leverage'],
                    'initial_position_size': best_config['initial_position_size'],
                    'averaging_steps': best_config['averaging_steps'],
                    'total_margin_required': best_config['total_margin_required'],
                    'liquidation_price': best_config['liquidation_price'],
                    'confidence_score': market_confidence * (0.8 if best_config['is_safe'] else 0.5),
                    'backtest_results': {
                        'total_trades': best_backtest.total_trades,
                        'win_rate': best_backtest.win_rate,
                        'total_return': best_backtest.total_return,
                        'max_drawdown': best_backtest.max_drawdown,
                        'sharpe_ratio': best_backtest.sharpe_ratio,
                        'recovery_rate': best_backtest.recovery_rate,
                        'averaging_effectiveness': best_backtest.averaging_effectiveness,
                        'liquidation_events': best_backtest.liquidation_events
                    },
                    'candles_used': len(candles),
                    'optimization_score': best_score
                }
            else:
                return {
                    'success': False,
                    'error': 'No safe configuration found',
                    'candles_analyzed': len(candles)
                }
                
        except Exception as e:
            logger.error(f"Error in enhanced Fibonacci service: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _calculate_fibonacci_config(self, num_steps: int, leverage: float,
                                   delta: float, entry_price: float,
                                   available_margin: float, 
                                   direction: TradeDirection) -> Optional[Dict]:
        """Calculate Fibonacci configuration for given parameters"""
        try:
            # Generate Fibonacci weights
            weights = self.fibonacci_sequence[:num_steps][::-1]
            total_weight = sum(weights)
            
            # Calculate step positions
            step_positions = []
            cumulative_distance = 0
            
            for weight in weights:
                distance_ratio = weight / total_weight
                distance_from_entry = distance_ratio * delta
                cumulative_distance += distance_from_entry
                
                if direction == TradeDirection.LONG:
                    step_price = entry_price - cumulative_distance
                else:
                    step_price = entry_price + cumulative_distance
                
                step_positions.append(step_price)
            
            # Calculate margin allocation (inverse weights)
            inverse_weights = weights[::-1]
            margin_allocations = [
                (w / total_weight) * available_margin 
                for w in inverse_weights
            ]
            
            # Calculate multipliers
            initial_position_size = (margin_allocations[0] * leverage) / entry_price
            multipliers = [
                ((m * leverage) / entry_price) / initial_position_size
                for m in margin_allocations
            ]
            
            # Check liquidation safety
            is_safe = self._check_liquidation_safety(
                entry_price, step_positions, margin_allocations,
                leverage, direction
            )
            
            # Build averaging steps
            averaging_steps = []
            for i in range(num_steps):
                averaging_steps.append({
                    'step_number': i + 1,
                    'price': step_positions[i],
                    'margin_allocation': margin_allocations[i],
                    'position_multiplier': multipliers[i],
                    'fibonacci_weight': weights[i]
                })
            
            return {
                'leverage': leverage,
                'initial_position_size': margin_allocations[0] * leverage,
                'averaging_steps': averaging_steps,
                'total_margin_required': sum(margin_allocations),
                'liquidation_price': self._calculate_liquidation_price(
                    entry_price, sum(margin_allocations), leverage, direction
                ),
                'is_safe': is_safe
            }
            
        except Exception as e:
            logger.error(f"Error calculating config: {e}")
            return None
    
    def _check_liquidation_safety(self, entry_price: float, step_positions: List[float],
                                 margin_allocations: List[float], leverage: float,
                                 direction: TradeDirection) -> bool:
        """Check if configuration is safe from liquidation"""
        cumulative_margin = 0
        cumulative_position_size = 0
        
        for step_price, margin in zip(step_positions, margin_allocations):
            cumulative_margin += margin
            position_size = (margin * leverage) / entry_price
            cumulative_position_size += position_size
            
            if direction == TradeDirection.LONG:
                unrealized_pnl = cumulative_position_size * (step_price - entry_price)
            else:
                unrealized_pnl = cumulative_position_size * (entry_price - step_price)
            
            max_acceptable_loss = cumulative_margin * (1 - self.liquidation_buffer)
            
            if abs(unrealized_pnl) > max_acceptable_loss:
                return False
        
        return True
    
    def _calculate_liquidation_price(self, entry_price: float, total_margin: float,
                                    leverage: float, direction: TradeDirection) -> float:
        """Calculate liquidation price"""
        position_size = (total_margin * leverage) / entry_price
        
        if direction == TradeDirection.LONG:
            return entry_price * (1 - (total_margin / (position_size * entry_price)))
        else:
            return entry_price * (1 + (total_margin / (position_size * entry_price)))
    
    def _score_configuration(self, config: Dict, backtest: BacktestResult,
                           market_confidence: float) -> float:
        """Score a configuration based on backtest results"""
        score = 0
        
        # Backtest performance (40% weight)
        score += backtest.win_rate * 20
        score += min(backtest.recovery_rate * 10, 10)
        score += max(0, (1 - backtest.liquidation_events / max(backtest.total_trades, 1)) * 10)
        
        # Risk metrics (30% weight)
        score += max(0, (1 - abs(backtest.max_drawdown) / 100) * 15)
        score += min(backtest.sharpe_ratio * 5, 15)
        
        # Configuration quality (30% weight)
        score += len(config['averaging_steps']) * 2  # More steps = better
        score += (10 - config['leverage']) * 2  # Lower leverage = safer
        score += market_confidence * 10
        
        return score

# Create singleton instance
_enhanced_service = None

def get_enhanced_fibonacci_service() -> EnhancedFibonacciService:
    """Get singleton instance of enhanced Fibonacci service"""
    global _enhanced_service
    if _enhanced_service is None:
        _enhanced_service = EnhancedFibonacciService()
    return _enhanced_service

# Example usage
if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    
    load_dotenv('/app/.env')
    
    async def test_enhanced_service():
        """Test the enhanced Fibonacci service"""
        
        # Initialize exchange
        exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap'
            }
        })
        
        await exchange.load_markets()
        
        # Get service
        service = get_enhanced_fibonacci_service()
        
        # Test with BTC
        print("Testing Enhanced Fibonacci Service with Backtesting")
        print("="*60)
        
        result = await service.calculate_with_backtest(
            exchange=exchange,
            symbol='BTC/USDT:USDT',
            delta=1000,
            entry_price=50000,
            available_margin=100,
            direction='long',
            market_confidence=0.7
        )
        
        if result['success']:
            print(f"✅ Optimal Configuration Found")
            print(f"   Leverage: {result['leverage']}x")
            print(f"   Steps: {len(result['averaging_steps'])}")
            print(f"   Confidence: {result['confidence_score']:.2%}")
            
            print(f"\n📊 Backtest Results:")
            bt = result['backtest_results']
            print(f"   Total Trades: {bt['total_trades']}")
            print(f"   Win Rate: {bt['win_rate']:.2%}")
            print(f"   Total Return: {bt['total_return']:.2%}")
            print(f"   Max Drawdown: {bt['max_drawdown']:.2%}")
            print(f"   Sharpe Ratio: {bt['sharpe_ratio']:.2f}")
            print(f"   Recovery Rate: {bt['recovery_rate']:.2%}")
            print(f"   Averaging Effectiveness: {bt['averaging_effectiveness']:.2%}")
            print(f"   Liquidations: {bt['liquidation_events']}")
            
            print(f"\n📈 Data Analysis:")
            print(f"   Candles Used: {result['candles_used']}")
            print(f"   Optimization Score: {result['optimization_score']:.2f}")
        else:
            print(f"❌ Failed: {result.get('error', 'Unknown error')}")
        
        await exchange.close()
    
    asyncio.run(test_enhanced_service())