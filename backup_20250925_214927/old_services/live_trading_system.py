#!/usr/bin/env python3
"""
Live Trading System with Fibonacci Delta Thresholds
Complete self-contained trading system for /app
"""

import asyncio
import sys
import os
from pathlib import Path
from datetime import datetime
import structlog
from typing import Dict, List, Optional
import ccxt.async_support as ccxt

# Add services to path
sys.path.append(str(Path(__file__).parent / 'services' / 'api-gateway' / 'src'))

from dotenv import load_dotenv
import os
# Load from specific path
load_dotenv('/app/.env')

# Import our components
from live_positions_registry import LivePositionsRegistry, Position, PositionZone
from position_zone_manager import PositionZoneManager
from fibonacci_delta_calculator import FibonacciDeltaCalculator
from bitget_futures_client import BitgetFuturesClient
from market_scanner import MarketScanner

# Configure logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)

class LiveTradingSystem:
    """Main trading system with all components integrated"""
    
    def __init__(self):
        self.registry = None
        self.zone_manager = None
        self.bitget_client = None
        self.market_scanner = None
        self.ccxt_exchange = None
        self.running = False
        
        # Trading parameters
        self.max_positions = 10
        self.position_size_usd = 5.0  # Reduced to $5 per position for $7.29 balance
        self.leverage = 10  # Reduced leverage for safety
        self.min_confidence = 0.5  # Lower threshold for more opportunities
        
    async def initialize(self):
        """Initialize all components"""
        try:
            logger.info("="*60)
            logger.info("LIVE TRADING SYSTEM - AI XYZ")
            logger.info("With Dynamic Fibonacci Delta Thresholds")
            logger.info("="*60)
            
            # Initialize Bitget client
            logger.info("Initializing Bitget client...")
            api_key = os.getenv('BITGET_API_KEY')
            api_secret = os.getenv('BITGET_API_SECRET')
            passphrase = os.getenv('BITGET_API_PASSPHRASE')  # Correct env var name
            
            if not all([api_key, api_secret, passphrase]):
                logger.error(f"Missing credentials: key={bool(api_key)}, secret={bool(api_secret)}, pass={bool(passphrase)}")
                
            self.bitget_client = BitgetFuturesClient(
                api_key=api_key,
                api_secret=api_secret,
                passphrase=passphrase
            )
            
            # Initialize CCXT for better market operations
            self.ccxt_exchange = ccxt.bitget({
                'apiKey': api_key,
                'secret': api_secret,
                'password': passphrase,  # CCXT uses 'password' not 'passphrase'
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'defaultMarginMode': 'isolated'
                }
            })
            await self.ccxt_exchange.load_markets()
            
            # Check balance
            balance = await self.get_balance()
            logger.info(f"✅ Connected to Bitget - Balance: ${balance:.2f} USDT")
            
            # Initialize positions registry
            logger.info("Initializing positions registry...")
            self.registry = LivePositionsRegistry()
            await self.registry.connect()
            logger.info("✅ Positions registry connected")
            
            # Initialize zone manager for position management
            logger.info("Initializing zone manager...")
            self.zone_manager = PositionZoneManager(
                registry=self.registry,
                bitget_client=self.bitget_client,
                check_interval=5,
                manage_manual_positions=True  # Manage all positions including manual
            )
            
            # Initialize market scanner with exchange
            logger.info("Initializing market scanner...")
            self.market_scanner = MarketScanner(self.ccxt_exchange)
            await self.market_scanner.initialize()
            logger.info("✅ Market scanner ready")
            
            # Sync existing positions from exchange
            await self.sync_exchange_positions()
            
            logger.info("✅ All components initialized successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False
            
    async def get_balance(self) -> float:
        """Get USDT balance"""
        try:
            balance = await self.ccxt_exchange.fetch_balance()
            return balance['USDT']['free'] + balance['USDT']['used']
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0
            
    async def sync_exchange_positions(self):
        """Sync positions from exchange to registry"""
        try:
            positions = await self.ccxt_exchange.fetch_positions()
            
            for pos in positions:
                if pos['contracts'] > 0:  # Has open position
                    symbol = pos['symbol']
                    
                    # Convert CCXT symbol format (EGLD/USDT:USDT) to our format (EGLD)
                    clean_symbol = symbol.split('/')[0] if '/' in symbol else symbol.replace(':USDT', '').replace('USDT', '')
                    
                    # Check if already in registry
                    existing = await self.registry.get_position_by_symbol(clean_symbol)
                    if existing:
                        # Update existing position
                        updates = {
                            'current_price': pos['markPrice'],
                            'current_quantity': pos['contracts'],
                            'unrealized_pnl': pos['unrealizedPnl'] or 0
                        }
                        await self.registry.update_position(existing.position_id, updates)
                    else:
                        # Add new position to registry
                        from uuid import uuid4
                        new_position = Position(
                            position_id=str(uuid4()),
                            symbol=clean_symbol,
                            direction='long' if pos['side'] == 'long' else 'short',
                            initial_entry_price=pos['entryPrice'],
                            initial_quantity=pos['contracts'],
                            initial_order_id='manual_sync',  # No order ID for synced positions
                            current_quantity=pos['contracts'],
                            weighted_avg_price=pos['entryPrice'],
                            current_price=pos['markPrice'],
                            unrealized_pnl=pos['unrealizedPnl'] or 0,
                            leverage=self.leverage,
                            margin_mode='isolated',
                            is_manual=True,  # Mark as manual since it existed before
                            entry_timestamp=datetime.now()
                        )
                        await self.registry.add_position(new_position)
                        logger.info(f"Synced position: {symbol} {pos['side']}")
                        
            logger.info(f"Synced {len(positions)} positions from exchange")
            
        except Exception as e:
            logger.error(f"Error syncing positions: {e}")
            
    async def open_position(self, signal: Dict):
        """Open a new position based on signal with Fibonacci averaging parameters"""
        try:
            symbol = signal['symbol']
            side = signal['signal']  # 'long' or 'short'
            
            # Check if we already have this position
            existing = await self.registry.get_position_by_symbol(symbol.replace(':USDT', ''))
            if existing:
                logger.info(f"Position already exists for {symbol}")
                return
                
            # Check max positions
            all_positions = await self.registry.get_all_positions()
            if len(all_positions) >= self.max_positions:
                logger.info(f"Max positions reached ({self.max_positions})")
                return
            
            # Get current price
            current_price = signal['price']
            
            # Import and use Fibonacci service
            from fibonacci_averaging_service import get_fibonacci_service
            fibonacci_service = get_fibonacci_service()
            
            # Calculate delta based on market volatility or signal data
            # Use volatility from signal or default to 2%
            volatility = signal.get('volatility', 0.02)
            delta = current_price * volatility
            
            # Get available margin for this position
            balance = await self.get_balance()
            available_margin_per_position = balance / max(1, (self.max_positions - len(all_positions)))
            available_margin_per_position = min(available_margin_per_position, 100)  # Cap at $100
            
            # Calculate optimal trading parameters
            trading_params = fibonacci_service.calculate_trading_parameters(
                delta=delta,
                entry_price=current_price,
                available_margin=available_margin_per_position,
                direction=side,
                market_confidence=signal.get('confidence', 0.5)
            )
            
            # Log Fibonacci analysis results
            logger.info(f"="*60)
            logger.info(f"📊 FIBONACCI AVERAGING ANALYSIS - {symbol}")
            logger.info(f"="*60)
            logger.info(f"Market Volatility: {volatility:.1%}")
            logger.info(f"Delta Range: ${delta:.2f}")
            logger.info(f"Available Margin: ${available_margin_per_position:.2f}")
            logger.info(f"Optimal Leverage: {trading_params.leverage}x")
            logger.info(f"Averaging Steps Planned: {len(trading_params.averaging_steps)}")
            logger.info(f"Initial Position Size: ${trading_params.initial_position_size:.2f}")
            logger.info(f"Total Margin Required: ${trading_params.total_margin_required:.2f}")
            logger.info(f"Liquidation Price: ${trading_params.liquidation_price:.2f}")
            logger.info(f"Confidence Score: {trading_params.confidence_score:.2f}")
            
            # Log detailed averaging plan
            logger.info(f"\n📈 AVERAGING STEPS CONFIGURATION:")
            for step in trading_params.averaging_steps:
                distance_pct = ((current_price - step.price) / current_price) * 100
                logger.info(f"  Step {step.step_number}: "
                          f"Price=${step.price:.2f} ({distance_pct:+.1f}%), "
                          f"Multiplier={step.position_multiplier:.2f}x, "
                          f"Margin=${step.margin_allocation:.2f}, "
                          f"Fib Weight={step.fibonacci_weight}")
            
            # Store averaging parameters in position metadata for future use
            averaging_config = {
                'leverage': trading_params.leverage,
                'averaging_steps': [
                    {
                        'step_number': step.step_number,
                        'price': step.price,
                        'margin_allocation': step.margin_allocation,
                        'position_multiplier': step.position_multiplier,
                        'fibonacci_weight': step.fibonacci_weight
                    }
                    for step in trading_params.averaging_steps
                ],
                'liquidation_price': trading_params.liquidation_price,
                'total_margin_allocated': trading_params.total_margin_required
            }
            
            # Use optimized parameters
            optimal_leverage = trading_params.leverage
            initial_position_value = trading_params.initial_position_size
            
            # Calculate contracts with optimized parameters
            contracts = initial_position_value / current_price
            
            # Format for Bitget
            market = self.ccxt_exchange.market(symbol)
            contracts = self.ccxt_exchange.amount_to_precision(symbol, contracts)
            
            # Set optimized leverage
            await self.ccxt_exchange.set_leverage(optimal_leverage, symbol)
            
            # Place order with optimized parameters
            order = await self.ccxt_exchange.create_market_order(
                symbol=symbol,
                side='buy' if side == 'long' else 'sell',
                amount=contracts,
                params={
                    'marginMode': 'isolated',
                    'positionSide': side
                }
            )
            
            if order and order['status'] == 'closed':
                # Add to registry with Fibonacci configuration
                from uuid import uuid4
                position_id = str(uuid4())
                position = Position(
                    position_id=position_id,
                    symbol=symbol.replace(':USDT', ''),
                    direction=side,
                    initial_entry_price=order['average'],
                    initial_quantity=order['amount'],
                    initial_order_id=order['id'],
                    current_quantity=order['amount'],
                    weighted_avg_price=order['average'],
                    current_price=order['average'],
                    leverage=optimal_leverage,  # Use optimized leverage
                    margin_mode='isolated',
                    is_manual=False,
                    entry_timestamp=datetime.now(),
                    metadata=averaging_config  # Store Fibonacci configuration
                )
                await self.registry.add_position(position)
                
                # Store Fibonacci results with position ID
                from fibonacci_results_storage import store_position_fibonacci_results
                
                # Create response dict for storage
                fibonacci_response = {
                    'success': True,
                    'leverage': trading_params.leverage,
                    'initial_position_size': trading_params.initial_position_size,
                    'averaging_steps': [
                        {
                            'step_number': step.step_number,
                            'price': step.price,
                            'margin_allocation': step.margin_allocation,
                            'position_multiplier': step.position_multiplier,
                            'fibonacci_weight': step.fibonacci_weight,
                            'distance_from_entry': step.distance_from_entry,
                            'liquidation_safety': step.liquidation_safety
                        }
                        for step in trading_params.averaging_steps
                    ],
                    'total_margin_required': trading_params.total_margin_required,
                    'liquidation_price': trading_params.liquidation_price,
                    'confidence_score': trading_params.confidence_score,
                    'max_loss_tolerance': trading_params.max_loss_tolerance
                }
                
                # Store the results
                store_position_fibonacci_results(
                    position_id=position_id,
                    symbol=symbol,
                    entry_price=order['average'],
                    direction=side,
                    fibonacci_service_response=fibonacci_response
                )
                
                logger.info(f"✅ POSITION OPENED WITH FIBONACCI OPTIMIZATION")
                logger.info(f"   Symbol: {symbol} @ ${order['average']:.4f}")
                logger.info(f"   Direction: {side.upper()}")
                logger.info(f"   Size: {contracts} contracts (${initial_position_value:.2f})")
                logger.info(f"   Leverage: {optimal_leverage}x (optimized)")
                logger.info(f"   Averaging Steps Ready: {len(trading_params.averaging_steps)}")
                logger.info(f"   Signal confidence: {signal.get('confidence', 0.5):.2f}")
                logger.info(f"   Reasons: {', '.join(signal.get('reasons', ['Fibonacci optimized']))}")
                
        except Exception as e:
            logger.error(f"Failed to open position for {signal['symbol']}: {e}")
            
    async def update_position_prices(self):
        """Update current prices for all positions"""
        try:
            positions = await self.registry.get_all_positions()
            
            for position in positions:
                try:
                    # Convert our symbol format to CCXT format
                    # Handle different formats: EGLD, EGLDUSDT, REDNEWUSDT
                    clean_symbol = position.symbol.replace('USDT', '')
                    
                    # Skip REDNEW as it doesn't exist on Bitget
                    if 'REDNEW' in clean_symbol.upper():
                        logger.debug(f"Skipping REDNEW symbol - not available on Bitget")
                        continue
                        
                    symbol = f"{clean_symbol}/USDT:USDT"
                    ticker = await self.ccxt_exchange.fetch_ticker(symbol)
                    
                    # Update position
                    current_price = ticker['last']
                    
                    # Calculate UPNL
                    if position.direction == 'long':
                        unrealized_pnl = (current_price - position.weighted_avg_price) * position.current_quantity
                    else:
                        unrealized_pnl = (position.weighted_avg_price - current_price) * position.current_quantity
                        
                    # Update position in registry
                    updates = {
                        'current_price': current_price,
                        'unrealized_pnl': unrealized_pnl
                    }
                    await self.registry.update_position(position.position_id, updates)
                    
                except Exception as e:
                    logger.error(f"Error updating price for {position.symbol}: {e}")
                    
        except Exception as e:
            logger.error(f"Error updating positions: {e}")
            
    async def display_status(self):
        """Display current system status"""
        try:
            positions = await self.registry.get_all_positions()
            balance = await self.get_balance()
            
            total_upnl = sum(p.unrealized_pnl for p in positions)
            
            print("\n" + "="*60)
            print(f"LIVE TRADING STATUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("="*60)
            print(f"Balance: ${balance:.2f} USDT")
            print(f"Positions: {len(positions)}/{self.max_positions}")
            print(f"Total UPNL: ${total_upnl:.2f}")
            
            if positions:
                print("\nActive Positions:")
                print("-"*60)
                for pos in positions:
                    pos_type = "MANUAL" if pos.is_manual else "AUTO"
                    pnl_emoji = "🟢" if pos.unrealized_pnl > 0 else "🔴"
                    print(f"{pnl_emoji} [{pos_type}] {pos.symbol} {pos.direction.upper()}")
                    print(f"   Entry: ${pos.weighted_avg_price:.4f} | Current: ${pos.current_price:.4f}")
                    print(f"   UPNL: ${pos.unrealized_pnl:.2f} | Zone: {pos.current_zone.value}")
                    print(f"   Averaging: {pos.averaging_steps_taken}/{pos.custom_params.max_averaging_steps}")
                    
        except Exception as e:
            logger.error(f"Error displaying status: {e}")
            
    async def trading_loop(self):
        """Main trading loop"""
        self.running = True
        scan_counter = 0
        
        while self.running:
            try:
                # Update position prices
                await self.update_position_prices()
                
                # Scan for new opportunities every 5 minutes
                scan_counter += 1
                if scan_counter >= 60:  # 60 * 5 seconds = 5 minutes
                    scan_counter = 0
                    logger.info("Scanning market for opportunities...")
                    
                    signals = await self.market_scanner.scan_market()
                    
                    # Process top signals
                    for signal in signals[:3]:  # Top 3 signals
                        if signal['confidence'] >= self.min_confidence:
                            await self.open_position(signal)
                            
                # Display status every 30 seconds
                if scan_counter % 6 == 0:
                    await self.display_status()
                    
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in trading loop: {e}")
                await asyncio.sleep(10)
                
    async def start(self):
        """Start the trading system"""
        if not await self.initialize():
            logger.error("Failed to initialize system")
            return
            
        logger.info("Starting trading system...")
        
        # Start zone manager for position management
        await self.zone_manager.start()
        logger.info("✅ Zone manager started - Managing positions with Fibonacci thresholds")
        
        # Display initial status
        await self.display_status()
        
        # Start trading loop
        logger.info("✅ Trading loop started - Scanning for opportunities...")
        
        try:
            await self.trading_loop()
        except KeyboardInterrupt:
            logger.info("Shutdown requested...")
        finally:
            await self.stop()
            
    async def stop(self):
        """Stop the trading system"""
        logger.info("Stopping trading system...")
        self.running = False
        
        if self.zone_manager:
            await self.zone_manager.stop()
            
        if self.market_scanner:
            await self.market_scanner.close()
            
        if self.ccxt_exchange:
            await self.ccxt_exchange.close()
            
        if self.registry:
            await self.registry.disconnect()
            
        logger.info("Trading system stopped")

async def main():
    """Main entry point"""
    system = LiveTradingSystem()
    await system.start()

if __name__ == "__main__":
    asyncio.run(main())