"""
Futures Trading Engine - Orchestrates futures/perpetual trading with Bitget.
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import structlog
import httpx
from bitget_futures_client import BitgetFuturesClient
from config import settings
try:
    from futures_symbols_config import (
        get_symbol_config, format_price, format_quantity,
        validate_order_size, calculate_margin_required, get_optimal_leverage
    )
except ImportError:
    # Fallback if config not available
    get_symbol_config = lambda x: None
    format_price = lambda s, p: str(round(p, 2))
    format_quantity = lambda s, q: str(q)
    validate_order_size = lambda s, q, p: (True, "OK")
    calculate_margin_required = lambda s, q, p, l: {'initial_margin': 0}
    get_optimal_leverage = lambda s, c, r=0.5: 10

logger = structlog.get_logger(__name__)

class FuturesTradingEngine:
    """Futures trading engine that manages perpetual contracts."""
    
    def __init__(self):
        self.futures_client = BitgetFuturesClient(
            api_key=settings.BITGET_API_KEY,
            api_secret=settings.BITGET_API_SECRET,
            passphrase=settings.BITGET_API_PASSPHRASE
        )
        self.active_positions = {}
        self.running = False
        self.trading_enabled = True  # ENABLE LIVE TRADING
        self.default_leverage = 20  # Default 20x leverage - INCREASED
        self.max_leverage = 20  # Maximum 20x leverage
        self.product_type = "USDT-FUTURES"  # USDT perpetual contracts
        self.product_type_v2 = "USDT-FUTURES"  # For v2 endpoints
        self.margin_coin = "USDT"
        self.zone_manager = None  # Will be set by main.py
        self.registry = None  # Will be set by main.py
        
    async def start(self):
        """Start the futures trading engine."""
        logger.info("Starting Futures Trading Engine...")
        self.running = True
        
        # Test Bitget Futures connection
        try:
            account_info = self.futures_client.get_futures_account(self.product_type)
            logger.info("Bitget Futures connection established", accounts=len(account_info))
            
            # Try to set position mode but don't fail if it's already set
            try:
                self.futures_client.set_position_mode(self.product_type_v2, "double_hold")
                logger.info("Set position mode to hedge mode (double_hold)")
            except Exception as e:
                logger.info("Position mode already configured or not changeable", error=str(e))
            
        except Exception as e:
            logger.error("Failed to connect to Bitget Futures", error=str(e))
            return False
        
        # Start main trading loop
        asyncio.create_task(self.futures_trading_loop())
        asyncio.create_task(self.position_monitoring_loop())
        
        return True
    
    async def stop(self):
        """Stop the futures trading engine."""
        logger.info("Stopping Futures Trading Engine...")
        self.running = False
    
    async def futures_trading_loop(self):
        """Main futures trading loop - scans market and makes trading decisions."""
        while self.running:
            try:
                # Get market scan results for futures
                scan_results = await self.get_futures_market_scan()
                
                # Process each signal for futures trading
                for signal in scan_results.get('scan_results', []):
                    await self.process_futures_signal(signal)
                
                # Wait before next scan
                await asyncio.sleep(30)  # Scan every 30 seconds
                
            except Exception as e:
                logger.error("Error in futures trading loop", error=str(e))
                await asyncio.sleep(60)  # Wait longer on error
    
    async def position_monitoring_loop(self):
        """Monitor futures positions and manage their lifecycle."""
        while self.running:
            try:
                # Check for position management triggers
                for position_id, position in self.active_positions.items():
                    await self.manage_futures_position(position)
                
                # Wait before next check
                await asyncio.sleep(10)  # Check every 10 seconds for futures
                
            except Exception as e:
                logger.error("Error in futures position monitoring", error=str(e))
                await asyncio.sleep(30)
    
    async def get_futures_market_scan(self) -> Dict:
        """Get market scan results optimized for futures trading."""
        try:
            # Get all USDT perpetual tickers - use umcbl for V1 endpoint
            all_tickers = self.futures_client.get_all_futures_tickers("umcbl")
            logger.info(f"Scanning {len(all_tickers)} futures symbols for trading opportunities")
            
            scan_results = []
            for ticker in all_tickers[:20]:  # Analyze top 20 by volume
                symbol = ticker.get('symbol', '')
                if not symbol.endswith('USDT'):
                    continue
                    
                # Analyze each symbol for trading opportunities
                signal = await self.analyze_futures_opportunity(symbol, ticker)
                if signal:
                    scan_results.append(signal)
            
            return {'scan_results': scan_results}
            
        except Exception as e:
            logger.error("Failed to get futures market scan", error=str(e))
            return {'scan_results': []}
    
    async def analyze_futures_opportunity(self, symbol: str, ticker: Dict) -> Optional[Dict]:
        """Analyze a futures symbol for trading opportunities."""
        try:
            # Get recent price data
            klines = self.futures_client.get_futures_klines(symbol, '5m', 100)
            
            if not klines or len(klines) < 20:
                return None
            
            # Calculate simple indicators
            closes = [float(k[4]) for k in klines]  # Close prices
            current_price = float(ticker.get('last', 0))
            
            # Simple momentum strategy for futures
            sma_20 = sum(closes[-20:]) / 20
            sma_5 = sum(closes[-5:]) / 5
            
            # Calculate price momentum
            momentum = (current_price - closes[-10]) / closes[-10] * 100
            
            signal_type = None
            signal_strength = 0.0
            
            # Long signal: price above SMA20, positive momentum (LOWERED FOR TESTING)
            if sma_5 > sma_20 * 1.002 and momentum > 0.5:  # Was 1.01 and 1.0
                signal_type = "LONG"
                signal_strength = min(momentum / 2.0, 1.0)  # Normalize to 0-1 (adjusted)
            
            # Short signal: price below SMA20, negative momentum (LOWERED FOR TESTING)
            elif sma_5 < sma_20 * 0.998 and momentum < -0.5:  # Was 0.99 and -1.0
                signal_type = "SHORT"
                signal_strength = min(abs(momentum) / 2.0, 1.0)  # Adjusted
            
            if signal_type:
                return {
                    'symbol': symbol.replace('USDT', ''),  # Remove USDT suffix
                    'futures_symbol': symbol,
                    'signal_type': signal_type,
                    'signal_strength': signal_strength,
                    'current_price': current_price,
                    'momentum': momentum,
                    'volume_24h': float(ticker.get('usdtVolume', 0))
                }
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to analyze futures opportunity for {symbol}", error=str(e))
            return None
    
    async def process_futures_signal(self, signal: Dict):
        """Process a futures trading signal."""
        try:
            futures_symbol = signal['futures_symbol']
            
            # Check if we already have a position in this symbol
            existing_positions = self.futures_client.get_single_position(futures_symbol, self.margin_coin)
            if existing_positions and len(existing_positions) > 0:
                has_position = any(float(pos.get('total', 0)) > 0 for pos in existing_positions)
                if has_position:
                    return
            
            # Analyze decision through risk management  
            if self.trading_enabled and signal['signal_strength'] > 0.05:  # Lowered threshold for small account
                logger.info("EXECUTING LIVE TRADE", signal=signal, trading_enabled=self.trading_enabled)
                if signal['signal_type'] == 'LONG':
                    await self.open_long_position(signal)
                elif signal['signal_type'] == 'SHORT':
                    await self.open_short_position(signal)
            else:
                logger.info("Trade signal received but not executed", 
                           trading_enabled=self.trading_enabled, 
                           signal_strength=signal['signal_strength'])
                    
        except Exception as e:
            logger.error("Error processing futures signal", signal=signal, error=str(e))
    
    async def open_long_position(self, signal: Dict):
        """Open a long futures position."""
        try:
            futures_symbol = signal['futures_symbol']
            current_price = signal['current_price']
            
            # Get account balance
            account_balance = self.get_futures_account_balance()
            
            # Risk 50% of account per trade (increased due to small balance and high leverage)
            risk_amount = account_balance * 0.50
            
            # Set leverage to 20x for maximum trading power
            leverage = 20  # Fixed at 20x leverage
            self.futures_client.set_leverage(futures_symbol, self.margin_coin, leverage)
            
            # Calculate position size with leverage and proper formatting
            position_value = risk_amount * leverage
            size = position_value / current_price
            
            # CRITICAL: Ensure minimum notional value of $6
            MIN_NOTIONAL = 6.0
            notional_value = size * current_price
            if notional_value < MIN_NOTIONAL:
                size = MIN_NOTIONAL / current_price
                notional_value = MIN_NOTIONAL
                logger.info(f"Adjusted size to meet minimum notional: {size} (${notional_value})")
            
            # Apply symbol-specific formatting
            config = get_symbol_config(futures_symbol)
            if config:
                size = float(format_quantity(futures_symbol, size))
                # Ensure minimum order size
                if size < config['min_quantity']:
                    size = config['min_quantity']
                # Validate order
                is_valid, msg = validate_order_size(futures_symbol, size, current_price)
                if not is_valid:
                    logger.warning(f"Order validation failed: {msg}")
                    return
            
            # Final check: Ensure notional value is still >= $6 after formatting
            final_notional = size * current_price
            if final_notional < MIN_NOTIONAL:
                logger.error(f"Cannot meet minimum notional value of ${MIN_NOTIONAL}. Notional: ${final_notional}")
                return
            
            # Calculate stop loss and take profit with proper formatting
            stop_loss_price = current_price * 0.98  # 2% stop loss
            take_profit_price = current_price * 1.05  # 5% take profit
            
            # Format prices according to symbol precision
            if config:
                stop_loss_price = float(format_price(futures_symbol, stop_loss_price))
                take_profit_price = float(format_price(futures_symbol, take_profit_price))
            
            # Place long order
            order_result = self.futures_client.place_futures_order(
                symbol=futures_symbol,
                margin_coin=self.margin_coin,
                size=str(size),
                side='open_long',
                order_type='market',
                stop_loss_price=str(stop_loss_price),
                take_profit_price=str(take_profit_price)
            )
            
            logger.info("Long position opened", 
                       symbol=futures_symbol,
                       size=size,
                       leverage=leverage,
                       entry_price=current_price,
                       order_id=order_result.get('orderId'))
            
            # Track position
            position_id = order_result.get('orderId')
            self.active_positions[position_id] = {
                'id': position_id,
                'symbol': signal['symbol'],
                'futures_symbol': futures_symbol,
                'side': 'long',
                'size': size,
                'entry_price': current_price,
                'leverage': leverage,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'timestamp': datetime.now().isoformat()
            }
            
            # Notify zone manager about new position
            if self.zone_manager:
                await self.zone_manager.on_position_opened(
                    symbol=signal['symbol'],
                    side='long',
                    entry_price=current_price,
                    quantity=size,
                    order_id=position_id
                )
            
        except Exception as e:
            logger.error("Failed to open long position", symbol=signal['futures_symbol'], error=str(e))
    
    async def open_short_position(self, signal: Dict):
        """Open a short futures position."""
        try:
            futures_symbol = signal['futures_symbol']
            current_price = signal['current_price']
            
            # Get account balance
            account_balance = self.get_futures_account_balance()
            
            # Risk 50% of account per trade (increased due to small balance and high leverage)
            risk_amount = account_balance * 0.50
            
            # Set leverage to 20x for maximum trading power
            leverage = 20  # Fixed at 20x leverage
            self.futures_client.set_leverage(futures_symbol, self.margin_coin, leverage)
            
            # Calculate position size with leverage and proper formatting
            position_value = risk_amount * leverage
            size = position_value / current_price
            
            # CRITICAL: Ensure minimum notional value of $6
            MIN_NOTIONAL = 6.0
            notional_value = size * current_price
            if notional_value < MIN_NOTIONAL:
                size = MIN_NOTIONAL / current_price
                notional_value = MIN_NOTIONAL
                logger.info(f"Adjusted size to meet minimum notional: {size} (${notional_value})")
            
            # Apply symbol-specific formatting
            config = get_symbol_config(futures_symbol)
            if config:
                size = float(format_quantity(futures_symbol, size))
                # Ensure minimum order size
                if size < config['min_quantity']:
                    size = config['min_quantity']
                # Validate order
                is_valid, msg = validate_order_size(futures_symbol, size, current_price)
                if not is_valid:
                    logger.warning(f"Order validation failed: {msg}")
                    return
            
            # Final check: Ensure notional value is still >= $6 after formatting
            final_notional = size * current_price
            if final_notional < MIN_NOTIONAL:
                logger.error(f"Cannot meet minimum notional value of ${MIN_NOTIONAL}. Notional: ${final_notional}")
                return
            
            # Calculate stop loss and take profit
            stop_loss_price = current_price * 1.02  # 2% stop loss
            take_profit_price = current_price * 0.95  # 5% take profit
            
            # Place short order
            order_result = self.futures_client.place_futures_order(
                symbol=futures_symbol,
                margin_coin=self.margin_coin,
                size=str(size),
                side='open_short',
                order_type='market',
                stop_loss_price=str(stop_loss_price),
                take_profit_price=str(take_profit_price)
            )
            
            logger.info("Short position opened",
                       symbol=futures_symbol,
                       size=size,
                       leverage=leverage,
                       entry_price=current_price,
                       order_id=order_result.get('orderId'))
            
            # Track position
            position_id = order_result.get('orderId')
            self.active_positions[position_id] = {
                'id': position_id,
                'symbol': signal['symbol'],
                'futures_symbol': futures_symbol,
                'side': 'short',
                'size': size,
                'entry_price': current_price,
                'leverage': leverage,
                'stop_loss': stop_loss_price,
                'take_profit': take_profit_price,
                'timestamp': datetime.now().isoformat()
            }
            
            # Notify zone manager about new position
            if self.zone_manager:
                await self.zone_manager.on_position_opened(
                    symbol=signal['symbol'],
                    side='short',
                    entry_price=current_price,
                    quantity=size,
                    order_id=position_id
                )
            
        except Exception as e:
            logger.error("Failed to open short position", symbol=signal['futures_symbol'], error=str(e))
    
    async def update_futures_positions(self):
        """Update all active futures positions."""
        try:
            # Get all positions from exchange
            all_positions = self.futures_client.get_all_positions(self.product_type)
            
            # Update tracked positions
            for position in all_positions:
                if float(position.get('total', 0)) > 0:
                    symbol = position.get('symbol')
                    
                    # Find matching tracked position
                    for pid, tracked_pos in self.active_positions.items():
                        if tracked_pos['futures_symbol'] == symbol:
                            # Update with current data
                            tracked_pos['current_price'] = float(position.get('markPrice', 0))
                            tracked_pos['unrealized_pnl'] = float(position.get('unrealizedPL', 0))
                            tracked_pos['pnl_percentage'] = float(position.get('margin', 0))
                            
        except Exception as e:
            # Don't fail the entire engine if position update fails - this is normal when no positions
            logger.debug("Position update skipped", error=str(e))
    
    async def manage_futures_position(self, position: Dict):
        """Manage a futures position based on market conditions."""
        try:
            # Check if position has reached take profit or stop loss
            current_price = position.get('current_price', 0)
            entry_price = position['entry_price']
            
            if not current_price:
                return
            
            pnl_percentage = ((current_price - entry_price) / entry_price * 100)
            if position['side'] == 'short':
                pnl_percentage = -pnl_percentage
            
            # Dynamic exit conditions
            if pnl_percentage > 8:  # Take profit at 8%
                await self.close_futures_position(position, "take_profit")
            elif pnl_percentage < -3:  # Stop loss at 3%
                await self.close_futures_position(position, "stop_loss")
            elif pnl_percentage > 3:  # Trailing stop after 3% profit
                # Move stop loss to breakeven
                new_stop = entry_price * (1.01 if position['side'] == 'long' else 0.99)
                position['stop_loss'] = new_stop
                
        except Exception as e:
            logger.error("Failed to manage futures position", position_id=position.get('id'), error=str(e))
    
    async def close_futures_position(self, position: Dict, reason: str):
        """Close a futures position."""
        try:
            futures_symbol = position['futures_symbol']
            side = 'close_long' if position['side'] == 'long' else 'close_short'
            
            # Place closing order
            order_result = self.futures_client.place_futures_order(
                symbol=futures_symbol,
                margin_coin=self.margin_coin,
                size=str(position['size']),
                side=side,
                order_type='market'
            )
            
            logger.info("Futures position closed",
                       symbol=futures_symbol,
                       side=position['side'],
                       reason=reason,
                       pnl=position.get('unrealized_pnl', 0))
            
            # Remove from tracked positions
            if position['id'] in self.active_positions:
                del self.active_positions[position['id']]
                
        except Exception as e:
            logger.error("Failed to close futures position", position=position, error=str(e))
    
    def get_futures_account_balance(self) -> float:
        """Get futures account balance in USDT."""
        try:
            accounts = self.futures_client.get_futures_account(self.product_type)
            for account in accounts:
                if account.get('marginCoin') == 'USDT':
                    return float(account.get('available', 0))
            return 100.0  # Default balance for testing
        except:
            return 100.0  # Default balance for testing
    
    async def get_futures_trading_status(self) -> Dict:
        """Get current futures trading engine status."""
        try:
            # Get all positions
            all_positions = self.futures_client.get_all_positions(self.product_type)
            
            total_pnl = sum(float(pos.get('unrealizedPL', 0)) for pos in all_positions)
            
            return {
                'running': self.running,
                'active_positions': len(self.active_positions),
                'total_positions': len(all_positions),
                'account_balance': self.get_futures_account_balance(),
                'total_unrealized_pnl': total_pnl,
                'positions': list(self.active_positions.values()),
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            logger.error("Failed to get futures trading status", error=str(e))
            return {
                'running': self.running,
                'active_positions': 0,
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }

# Global futures trading engine instance
futures_trading_engine = FuturesTradingEngine()