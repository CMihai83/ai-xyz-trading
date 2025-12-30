"""
Adaptive Timeframe Delta Service
=================================

This service calculates deltas for multiple timeframes and automatically
switches to larger timeframes when the -85% UPNL safety threshold would
be reached with the current delta.

Logic:
1. Calculate deltas for all timeframes (15m, 1h, 4h, 1d)
2. Start with smallest delta
3. Check if -85% UPNL would be reached with this delta
4. If yes, switch to next larger delta
5. Recalculate averaging steps with new delta
6. Continue until suitable delta found or maximum reached
"""

import structlog
from typing import Dict, List, Tuple, Optional
import ccxt
from datetime import datetime, timedelta
import numpy as np

logger = structlog.get_logger(__name__)

class AdaptiveTimeframeDeltaService:
    """
    Service that manages multiple timeframe deltas and switches between them
    based on safety thresholds
    """
    
    # Timeframes to analyze (in order of evaluation)
    TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']
    
    # Candle counts for each timeframe
    # Using fewer candles for smaller timeframes for more responsive deltas
    CANDLE_COUNTS = {
        '1m': 50,     # ~50 minutes - very recent movements only
        '5m': 100,    # ~8 hours - recent day
        '15m': 200,   # ~2 days - short term
        '1h': 300,    # ~12 days - medium term
        '4h': 400,    # ~66 days - longer term
        '1d': 365     # 1 year - long term
    }
    
    def __init__(self, exchange: ccxt.Exchange):
        self.exchange = exchange
        self.delta_cache = {}
        self.current_timeframe_index = {}  # Track current timeframe per position
        
    async def calculate_all_deltas(self, symbol: str, current_price: float) -> Dict[str, float]:
        """
        Calculate deltas for all timeframes
        Returns dict of timeframe -> delta percentage
        """
        deltas = {}
        
        for timeframe in self.TIMEFRAMES:
            try:
                delta_pct = await self._calculate_timeframe_delta(
                    symbol, 
                    timeframe, 
                    current_price
                )
                deltas[timeframe] = delta_pct
                
                logger.info(
                    f"Calculated {timeframe} delta",
                    symbol=symbol,
                    timeframe=timeframe,
                    delta_pct=f"{delta_pct*100:.1f}%",
                    delta_price=f"${current_price * delta_pct:.4f}"
                )
                
            except Exception as e:
                logger.error(f"Failed to calculate {timeframe} delta", error=str(e))
                deltas[timeframe] = 0.10  # Default 10% on error
                
        # Cache the results
        self.delta_cache[symbol] = {
            'deltas': deltas,
            'timestamp': datetime.now(),
            'current_price': current_price
        }
        
        return deltas
    
    async def _calculate_timeframe_delta(
        self, 
        symbol: str, 
        timeframe: str, 
        current_price: float
    ) -> float:
        """
        Calculate delta for a specific timeframe using consecutive candle ranges
        with volatility-based scaling
        """
        limit = self.CANDLE_COUNTS.get(timeframe, 500)
        
        # Fetch OHLCV data
        ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        
        if not ohlcv or len(ohlcv) < 2:
            return 0.10  # Default 10%
            
        # Calculate consecutive candle ranges
        ranges = []
        returns = []  # For volatility calculation
        
        for i in range(1, len(ohlcv)):
            prev_candle = ohlcv[i-1]
            curr_candle = ohlcv[i]
            
            # Range from previous close to current high/low
            prev_close = prev_candle[4]
            curr_high = curr_candle[2]
            curr_low = curr_candle[3]
            curr_close = curr_candle[4]
            
            # Maximum movement from previous close
            up_range = abs(curr_high - prev_close) / prev_close
            down_range = abs(curr_low - prev_close) / prev_close
            max_range = max(up_range, down_range)
            
            ranges.append(max_range)
            
            # Calculate returns for volatility
            returns.append((curr_close - prev_close) / prev_close)
        
        # Use 95th percentile for safety
        base_delta_pct = np.percentile(ranges, 95) if ranges else 0.10
        
        # Calculate volatility metrics for scaling
        volatility_multiplier = self._calculate_volatility_multiplier(returns, ranges)
        
        # Apply volatility scaling
        delta_pct = base_delta_pct * volatility_multiplier
        
        # Add 30% buffer for safety
        delta_pct *= 1.3
        
        logger.info(
            f"Delta calculation with volatility scaling",
            symbol=symbol,
            timeframe=timeframe,
            base_delta=f"{base_delta_pct*100:.1f}%",
            volatility_multiplier=f"{volatility_multiplier:.2f}x",
            final_delta=f"{delta_pct*100:.1f}%"
        )
        
        return delta_pct
    
    def _calculate_volatility_multiplier(self, returns: List[float], ranges: List[float]) -> float:
        """
        Calculate volatility multiplier based on recent vs average price movements
        
        When price moves rapidly compared to average, increase delta proportionally
        to prevent liquidation from sudden spikes
        """
        if not returns or len(returns) < 10:
            return 1.0
        
        # Calculate recent volatility (last 10% of data)
        recent_window = max(5, len(returns) // 10)
        recent_returns = returns[-recent_window:]
        avg_returns = returns[:-recent_window] if len(returns) > recent_window else returns
        
        # Calculate velocity ratio (recent movement vs average)
        recent_volatility = np.std(recent_returns) if recent_returns else 0
        avg_volatility = np.std(avg_returns) if avg_returns else 0
        
        if avg_volatility == 0:
            return 1.0
            
        velocity_ratio = recent_volatility / avg_volatility
        
        # Also check for spike detection (rapid single movements)
        recent_ranges = ranges[-recent_window:]
        avg_range = np.mean(ranges[:-recent_window]) if len(ranges) > recent_window else np.mean(ranges)
        max_recent_spike = max(recent_ranges) if recent_ranges else avg_range
        spike_ratio = max_recent_spike / avg_range if avg_range > 0 else 1.0
        
        # Combine velocity and spike ratios
        # Use the higher of the two for safety
        combined_ratio = max(velocity_ratio, spike_ratio)
        
        # Calculate multiplier with scaling factor
        # scaling_factor = 0.5 means 50% of excess volatility is added to delta
        scaling_factor = 0.5
        volatility_multiplier = 1.0 + max(0, (combined_ratio - 1.0) * scaling_factor)
        
        # Cap at 2.0x to prevent excessive delta
        volatility_multiplier = min(2.0, volatility_multiplier)
        
        logger.debug(
            f"Volatility multiplier calculation",
            velocity_ratio=f"{velocity_ratio:.2f}",
            spike_ratio=f"{spike_ratio:.2f}",
            combined_ratio=f"{combined_ratio:.2f}",
            multiplier=f"{volatility_multiplier:.2f}"
        )
        
        return volatility_multiplier
    
    def get_adaptive_delta(
        self,
        symbol: str,
        position_data: Dict,
        leverage: int = 10
    ) -> Tuple[float, str, bool]:
        """
        ADAPTIVE TIMEFRAME EXPANSION LOGIC
        ===================================
        This is the core of the adaptive delta system. It implements progressive
        timeframe expansion to handle increasing volatility.
        
        STRATEGY:
        1. NEW POSITIONS: Start with smallest safe timeframe (typically 1m)
        2. MONITOR: Track price movement relative to current delta
        3. EXPAND: When price moves beyond 80% of delta, switch to larger timeframe
        4. NO CAPS: Let delta grow naturally with timeframes (2% → 100%+)
        
        Returns:
            (delta_pct, timeframe, needs_update)
        """
        if symbol not in self.delta_cache:
            logger.error(f"No delta cache for {symbol}")
            return 0.10, '1m', False
            
        cached = self.delta_cache[symbol]
        deltas = cached['deltas']
        current_price = cached['current_price']
        
        # Sort deltas by value (ascending) - smallest first
        sorted_deltas = sorted(deltas.items(), key=lambda x: x[1])
        
        # If this is a new position or no position data, start with smallest delta
        if not position_data or 'entry_price' not in position_data:
            # Start with smallest safe delta
            for timeframe, delta_pct in sorted_deltas:
                if self._check_safety_with_delta(position_data or {}, delta_pct, leverage):
                    logger.info(
                        f"Starting with smallest safe delta",
                        symbol=symbol,
                        timeframe=timeframe,
                        delta=f"{delta_pct*100:.1f}%"
                    )
                    self.current_timeframe_index[symbol] = sorted_deltas.index((timeframe, delta_pct))
                    return delta_pct, timeframe, False
        
        # For existing positions, check if we need to expand to larger timeframe
        entry_price = position_data.get('entry_price', current_price)
        price_movement = abs(current_price - entry_price) / entry_price
        
        # Get current timeframe index
        current_idx = self.current_timeframe_index.get(symbol, 0)
        current_timeframe, current_delta = sorted_deltas[current_idx] if current_idx < len(sorted_deltas) else sorted_deltas[0]
        
        # Check if price has moved beyond 80% of current delta (leave some buffer)
        if price_movement > current_delta * 0.8:
            # Need to switch to larger timeframe
            logger.info(
                f"Price movement {price_movement*100:.1f}% exceeds 80% of current delta {current_delta*100:.1f}%",
                symbol=symbol,
                current_timeframe=current_timeframe
            )
            
            # Find next larger safe delta
            for i in range(current_idx + 1, len(sorted_deltas)):
                timeframe, delta_pct = sorted_deltas[i]
                
                if self._check_safety_with_delta(position_data, delta_pct, leverage):
                    self.current_timeframe_index[symbol] = i
                    logger.info(
                        f"Switching to larger timeframe",
                        symbol=symbol,
                        old_timeframe=current_timeframe,
                        new_timeframe=timeframe,
                        old_delta=f"{current_delta*100:.1f}%",
                        new_delta=f"{delta_pct*100:.1f}%"
                    )
                    return delta_pct, timeframe, True
            
            # If no larger safe delta, keep current
            logger.warning(
                f"No larger safe delta available, keeping current",
                symbol=symbol,
                timeframe=current_timeframe,
                delta=f"{current_delta*100:.1f}%"
            )
            return current_delta, current_timeframe, False
        else:
            # Current delta is still appropriate
            return current_delta, current_timeframe, False
    
    def _check_safety_with_delta(
        self,
        position_data: Dict,
        delta_pct: float,
        leverage: int
    ) -> bool:
        """
        Check if using this delta would keep us safe from -85% UPNL
        at the LAST averaging step (100% of delta)
        """
        # With 10x leverage, we need the LAST step to be before -85% UPNL
        # Last step is at 100% of delta
        # For safety, we want some buffer before -85%, so check against -75%
        max_safe_upnl = 0.75  # 75% max UPNL before liquidation danger
        
        # Calculate UPNL% at last step (100% of delta)
        # For futures: UPNL% = price_move% × leverage
        upnl_pct_at_last_step = delta_pct * leverage
        
        # Delta is safe if last step would be before -75% UPNL
        is_safe = upnl_pct_at_last_step < max_safe_upnl
        
        if not is_safe:
            logger.debug(
                f"Delta would exceed safety threshold",
                delta_pct=f"{delta_pct*100:.1f}%",
                upnl_at_last_step=f"{upnl_pct_at_last_step*100:.1f}%",
                max_safe_upnl=f"{max_safe_upnl*100:.1f}%"
            )
        
        return is_safe
    
    def reset_position_timeframe(self, symbol: str):
        """Reset timeframe tracking for a position (e.g., when closed)"""
        if symbol in self.current_timeframe_index:
            del self.current_timeframe_index[symbol]
            logger.info(f"Reset timeframe tracking for {symbol}")
    
    def get_current_status(self, symbol: str) -> Dict:
        """Get current delta status for a symbol"""
        if symbol not in self.delta_cache:
            return {'status': 'not_initialized'}
            
        cached = self.delta_cache[symbol]
        current_idx = self.current_timeframe_index.get(symbol, 0)
        sorted_deltas = sorted(cached['deltas'].items(), key=lambda x: x[1])
        
        current_timeframe = sorted_deltas[current_idx][0] if current_idx < len(sorted_deltas) else 'unknown'
        current_delta = sorted_deltas[current_idx][1] if current_idx < len(sorted_deltas) else 0
        
        # Get volatility status if available
        volatility_status = cached.get('volatility_status', {})
        
        return {
            'status': 'active',
            'current_timeframe': current_timeframe,
            'current_delta_pct': current_delta,
            'timeframe_index': current_idx,
            'total_timeframes': len(sorted_deltas),
            'all_deltas': cached['deltas'],
            'last_update': cached['timestamp'],
            'volatility_status': volatility_status
        }
    
    async def check_volatility_spike(self, symbol: str) -> Dict:
        """
        Check for real-time volatility spikes that may require delta adjustment
        Returns volatility status and recommended action
        """
        try:
            # Get latest 1m candles for rapid detection
            ohlcv_1m = self.exchange.fetch_ohlcv(symbol, '1m', limit=20)
            
            if not ohlcv_1m or len(ohlcv_1m) < 10:
                return {'spike_detected': False, 'reason': 'insufficient_data'}
            
            # Calculate recent price movements
            recent_moves = []
            for i in range(1, len(ohlcv_1m)):
                prev_close = ohlcv_1m[i-1][4]
                curr_high = ohlcv_1m[i][2]
                curr_low = ohlcv_1m[i][3]
                
                move_pct = max(
                    abs(curr_high - prev_close) / prev_close,
                    abs(curr_low - prev_close) / prev_close
                )
                recent_moves.append(move_pct)
            
            # Check for spikes
            avg_move = np.mean(recent_moves[:-5]) if len(recent_moves) > 5 else np.mean(recent_moves)
            last_5_moves = recent_moves[-5:] if len(recent_moves) >= 5 else recent_moves
            max_recent = max(last_5_moves) if last_5_moves else 0
            
            spike_ratio = max_recent / avg_move if avg_move > 0 else 1.0
            
            # Determine if spike is significant
            spike_detected = spike_ratio > 2.0  # 2x normal movement
            
            status = {
                'spike_detected': spike_detected,
                'spike_ratio': spike_ratio,
                'avg_movement_pct': avg_move * 100,
                'max_recent_pct': max_recent * 100,
                'recommendation': 'increase_delta' if spike_detected else 'normal',
                'suggested_multiplier': min(2.0, 1.0 + (spike_ratio - 1.0) * 0.5) if spike_detected else 1.0
            }
            
            # Cache volatility status
            if symbol in self.delta_cache:
                self.delta_cache[symbol]['volatility_status'] = status
            
            if spike_detected:
                logger.warning(
                    f"Volatility spike detected!",
                    symbol=symbol,
                    spike_ratio=f"{spike_ratio:.2f}x",
                    max_recent=f"{max_recent*100:.2f}%",
                    avg_movement=f"{avg_move*100:.2f}%"
                )
            
            return status
            
        except Exception as e:
            logger.error(f"Failed to check volatility spike", error=str(e))
            return {'spike_detected': False, 'reason': 'error', 'error': str(e)}


async def create_adaptive_delta_service(exchange: ccxt.Exchange) -> AdaptiveTimeframeDeltaService:
    """Factory function to create and initialize the service"""
    service = AdaptiveTimeframeDeltaService(exchange)
    logger.info("Adaptive Timeframe Delta Service initialized")
    return service