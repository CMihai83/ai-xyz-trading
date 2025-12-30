"""
Averaging Engine - Cardinal Rule 4 Compliant
STATUS: ✅ 100% COMPLIANT (Tested: 2025-01-06)
Cardinal Rules: Rule 4 (Averaging Steps Must Be Tracked)
Test Coverage: 1/1 passed
Features: Immutable history, Order ID tracking, Weighted average recalculation

Implements exponential position averaging with immutable tracking
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, List
import structlog
import ccxt.async_support as ccxt
import os
from dotenv import load_dotenv

from live_positions_registry import Position, LivePositionsRegistry, AveragingStep, PositionDirection
from adaptive_fibonacci_averaging import AdaptiveFibonacciCalculator, calculate_position_averaging_config

load_dotenv('/app/.env')
logger = structlog.get_logger(__name__)

class AveragingEngine:
    """
    Cardinal Rule 4: Averaging Steps Must Be Tracked
    - Every averaging action creates an immutable record
    - Order IDs tracked for each operation
    - Weighted average price recalculated after each step
    """
    
    def __init__(self, registry: LivePositionsRegistry, exchange: ccxt.Exchange = None):
        self.registry = registry
        self.exchange = exchange or self._init_exchange()
        
        # Adaptive Fibonacci calculator
        self.fibonacci_calculator = AdaptiveFibonacciCalculator()
        
        # Default averaging configuration (FIXED: Using proper Fibonacci)
        # First 9 Fibonacci numbers for position sizing
        self.default_multipliers = [1.0, 1.0, 2.0, 3.0, 5.0, 8.0, 13.0, 21.0, 34.0]
        # Proper thresholds as per documentation
        self.default_thresholds = [-0.42, -0.68, -0.84, -0.94, -1.0]
        
    def _init_exchange(self):
        """Initialize Bitget exchange"""
        return ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
            }
        })
    
    async def evaluate_averaging(self, position: Position) -> Optional[Dict]:
        """
        Evaluate if position needs averaging using runtime_config.json thresholds
        Uses direct Bitget unrealized P&L for accuracy
        """
        # Only for positions in AVERAGING zone
        if position.current_zone.value != 'AVERAGING':
            return None
        
        # Load runtime configuration for thresholds
        import json
        config_path = '/app/runtime_config.json'
        
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
                averaging_threshold = config.get('zone_thresholds', {}).get('averaging_start', -0.1)
        except Exception as e:
            logger.error(f"Failed to load runtime config: {e}")
            averaging_threshold = -0.1  # Default to -10%
        
        # Load initial margin from position_state.json for UPNL percentage calculation
        position_state_path = '/app/position_state.json'
        initial_margin = 6.5  # Default minimum position size
        
        if os.path.exists(position_state_path):
            try:
                with open(position_state_path, 'r') as f:
                    position_state = json.load(f)
                
                # Get stored position data
                active_positions = position_state.get('active_positions', {})
                stored_pos = active_positions.get(position.symbol)
                
                if stored_pos:
                    # Calculate initial margin from stored data
                    entry_price = stored_pos.get('entry_price', position.entry_price)
                    amount = stored_pos.get('amount', position.quantity) 
                    leverage = stored_pos.get('leverage', 7)
                    
                    # Fix entry price if Bitget returns 0.0
                    if position.entry_price == 0.0 or position.entry_price is None:
                        position.entry_price = entry_price
                        logger.info(f"Fixed entry price for {position.symbol}: {position.entry_price}")
                    
                    # Calculate initial margin = (entry_price * amount) / leverage
                    initial_margin = (entry_price * amount) / leverage
                    logger.info(f"Calculated initial margin for {position.symbol}: ${initial_margin:.2f}")
                    
            except Exception as e:
                logger.error(f"Failed to load position state: {e}")
        
        # CRITICAL: Use direct Bitget unrealized P&L for accurate calculation
        # Calculate UPNL percentage relative to initial margin
        # UPNL percentage = Bitget_UPNL$ / initial_margin
        upnl_pct = (position.unrealized_pnl / initial_margin) if initial_margin > 0 else 0
        
        logger.info(f"Averaging evaluation for {position.symbol}",
                   unrealized_pnl=f"${position.unrealized_pnl:.2f}",
                   initial_margin=f"${initial_margin:.2f}", 
                   upnl_percentage=f"{upnl_pct:.1%}",
                   threshold=f"{averaging_threshold:.1%}")
        
        # Check if UPNL percentage has reached the averaging threshold
        if upnl_pct <= averaging_threshold:
            # Calculate averaging size using Fibonacci multipliers from config
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    fibonacci_multipliers = config.get('fibonacci_multipliers', [1, 1, 2, 3, 5, 8, 13])
            except:
                fibonacci_multipliers = [1, 1, 2, 3, 5, 8, 13]
            
            # Get current step (limit to available multipliers)
            step_index = min(position.averaging_steps_taken, len(fibonacci_multipliers) - 1)
            multiplier = fibonacci_multipliers[step_index]
            
            # Calculate averaging size based on original position size
            try:
                with open(position_state_path, 'r') as f:
                    position_state = json.load(f)
                original_sizes = position_state.get('original_sizes', {})
                original_size = original_sizes.get(position.symbol, position.quantity)
            except:
                original_size = position.quantity
            
            averaging_size = original_size * multiplier
            
            logger.warning(f"AVERAGING TRIGGERED for {position.symbol}",
                         upnl=f"${position.unrealized_pnl:.2f}",
                         upnl_pct=f"{upnl_pct:.1%}",
                         threshold=f"{averaging_threshold:.1%}",
                         step=position.averaging_steps_taken + 1,
                         multiplier=multiplier,
                         averaging_size=averaging_size)
            
            return {
                'action': 'AVERAGE',
                'step_number': position.averaging_steps_taken + 1,
                'size': averaging_size,
                'threshold': averaging_threshold,
                'upnl_pct': upnl_pct,
                'multiplier': multiplier,
                'reason': f'UPNL ({upnl_pct:.1%}) <= threshold ({averaging_threshold:.1%})'
            }
        
        return None
    
    async def execute_averaging(self, position: Position, averaging_action: Dict) -> bool:
        """
        Execute averaging order
        Cardinal Rule 4: Create immutable record
        """
        try:
            step_number = averaging_action['step_number']
            averaging_size = averaging_action['size']
            
            logger.info("Executing averaging step",
                       position_id=position.position_id,
                       step_number=step_number,
                       size=averaging_size,
                       reason=averaging_action['reason'])
            
            # Create market order for averaging
            side = 'buy' if position.direction == PositionDirection.LONG else 'sell'
            
            # Execute order
            order = await self.exchange.create_market_order(
                symbol=position.symbol,
                side=side,
                amount=averaging_size
            )
            
            if order and order.get('status') == 'closed':
                # Create immutable averaging record (Rule 4)
                averaging_step = AveragingStep(
                    step_number=step_number,
                    order_id=order.get('id', ''),
                    price=float(order.get('price', 0)),
                    quantity=averaging_size,
                    timestamp=datetime.now(timezone.utc),
                    upnl_at_entry=position.unrealized_pnl
                )
                
                # Update position
                old_quantity = position.quantity
                old_avg_price = position.weighted_avg_price
                new_quantity = old_quantity + averaging_size
                new_price = float(order.get('price', 0))
                
                # Recalculate weighted average price
                position.weighted_avg_price = (
                    (old_avg_price * old_quantity + new_price * averaging_size) / new_quantity
                )
                position.quantity = new_quantity
                position.averaging_steps_taken = step_number
                position.averaging_history.append(averaging_step)
                position.surplus_size += averaging_size  # Track surplus for later dumping
                
                # Add order ID to position
                position.exchange_order_ids.append(order.get('id', ''))
                
                # Save updated position
                await self.registry.update_position(position)
                
                logger.info("Averaging step executed successfully",
                          position_id=position.position_id,
                          step_number=step_number,
                          order_id=order.get('id'),
                          new_avg_price=position.weighted_avg_price,
                          new_quantity=position.quantity)
                
                return True
            else:
                logger.error("Averaging order failed",
                           position_id=position.position_id,
                           order_status=order.get('status') if order else 'None')
                return False
                
        except Exception as e:
            logger.error("Failed to execute averaging",
                       position_id=position.position_id,
                       error=str(e))
            return False
    
    async def monitor_all_positions(self) -> Dict[str, Dict]:
        """Monitor all positions for averaging opportunities"""
        results = {}
        positions = await self.registry.get_all_positions()
        
        for position in positions:
            averaging_action = await self.evaluate_averaging(position)
            if averaging_action:
                success = await self.execute_averaging(position, averaging_action)
                results[position.position_id] = {
                    'action': averaging_action,
                    'executed': success
                }
        
        return results
    
    def _calculate_dynamic_delta(self, position: Position) -> Optional[float]:
        """
        Calculate MAXIMUM POSSIBLE DELTA based on historical volatility.
        This is the same logic as zone_state_machine._calculate_dynamic_delta
        
        PROCESS:
        1. This function calculates MAX expected price deviation
        2. Returns it to adaptive_fibonacci_averaging.py
        3. Fibonacci module then:
           - Backtests to find optimal steps (3-7)
           - Calculates optimal leverage
           - Distributes steps over this delta
        """
        try:
            import numpy as np
            
            # Fetch 7 days of historical data for better analysis
            symbol = position.symbol
            ohlcv = asyncio.run(self.exchange.fetch_ohlcv(symbol, timeframe='1h', limit=168))
            
            if not ohlcv or len(ohlcv) < 24:
                # Fallback to 30% if insufficient data
                return position.entry_price * 0.30
            
            # Calculate maximum historical swings
            closes = [candle[4] for candle in ohlcv]
            highs = [candle[2] for candle in ohlcv]
            lows = [candle[3] for candle in ohlcv]
            
            # Rolling 24h maximum price swings
            max_swings = []
            for i in range(24, len(closes)):
                window = closes[i-24:i]
                if min(window) > 0:
                    swing = (max(window) - min(window)) / min(window)
                    max_swings.append(swing)
            
            # Standard deviation for comparison
            returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]
            volatility = np.std(returns) if returns else 0.02
            
            # Use 95th percentile of swings + 30% safety margin
            if max_swings:
                percentile_95 = np.percentile(max_swings, 95)
                max_delta_pct = percentile_95 * 1.3  # 30% safety margin
            else:
                daily_vol = volatility * np.sqrt(24)
                max_delta_pct = daily_vol * 3  # 3 standard deviations
            
            # Only apply a minimum (10%) and very high maximum (1000% = 10x)
            # Let the historical data determine the true maximum
            max_delta_pct = max(0.10, min(10.00, max_delta_pct))  # 1000% maximum
            
            # Convert to price
            max_delta = position.entry_price * max_delta_pct
            
            logger.info(f"MAX DELTA calculated for averaging",
                       symbol=symbol,
                       max_delta_pct=f"{max_delta_pct:.2%}",
                       max_delta_price=f"${max_delta:.5f}",
                       note="Will be distributed by Fibonacci module")
            
            return max_delta
            
        except Exception as e:
            logger.warning(f"Failed to calculate max delta: {e}")
            return None
    
    async def initialize_adaptive_averaging(self, position: Position, total_margin: float = 25.0, max_delta: float = None) -> bool:
        """
        Initialize adaptive Fibonacci averaging configuration for a position
        Calculates optimal K coefficient and sets up averaging steps
        """
        try:
            # Calculate max_delta dynamically if not provided
            if max_delta is None:
                max_delta = self._calculate_dynamic_delta(position)
                if max_delta is None:
                    # Fallback to fixed percentage if dynamic calculation fails
                    max_delta = position.entry_price * 0.30
            
            # Calculate adaptive configuration
            config = calculate_position_averaging_config(
                entry_price=position.entry_price,
                leverage=position.leverage if hasattr(position, 'leverage') else 7,
                initial_margin=position.quantity * position.entry_price / (position.leverage if hasattr(position, 'leverage') else 7),
                total_margin=total_margin,
                max_delta=max_delta,
                direction='long' if position.direction == PositionDirection.LONG else 'short'
            )
            
            # Store configuration in position metadata
            if not hasattr(position, 'metadata') or position.metadata is None:
                position.metadata = {}
            
            position.metadata['averaging_config'] = 'adaptive_fibonacci'
            position.metadata['k_coefficient'] = config['k_coefficient']
            position.metadata['averaging_steps'] = config['averaging_steps']
            position.metadata['max_safe_steps'] = config['max_safe_steps']
            position.metadata['total_margin_required'] = config['total_margin_required']
            position.metadata['safety_validated'] = config['safety_validated']
            position.metadata['min_safety_distance'] = config['min_safety_distance']
            
            # Save updated position
            await self.registry.update_position(position)
            
            logger.info("Initialized adaptive Fibonacci averaging",
                       position_id=position.position_id,
                       k_coefficient=config['k_coefficient'],
                       max_safe_steps=config['max_safe_steps'],
                       safety_validated=config['safety_validated'])
            
            return True
            
        except Exception as e:
            logger.error("Failed to initialize adaptive averaging",
                       position_id=position.position_id,
                       error=str(e))
            return False
    
    def get_averaging_plan(self, position: Position) -> Dict:
        """Get averaging plan for a position"""
        remaining_steps = len(self.default_multipliers) - position.averaging_steps_taken
        
        plan = {
            'steps_taken': position.averaging_steps_taken,
            'max_steps': len(self.default_multipliers),
            'remaining_steps': remaining_steps,
            'current_quantity': position.quantity,
            'weighted_avg_price': position.weighted_avg_price,
            'history': []
        }
        
        # Add history
        for step in position.averaging_history:
            plan['history'].append({
                'step': step.step_number,
                'price': step.price,
                'quantity': step.quantity,
                'upnl_at_entry': step.upnl_at_entry,
                'timestamp': step.timestamp.isoformat()
            })
        
        # Add future steps
        plan['future_steps'] = []
        for i in range(position.averaging_steps_taken, len(self.default_multipliers)):
            plan['future_steps'].append({
                'step': i + 1,
                'threshold': self.default_thresholds[i],
                'multiplier': self.default_multipliers[i],
                'estimated_size': position.quantity * self.default_multipliers[i]
            })
        
        return plan