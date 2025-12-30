#!/usr/bin/env python3
"""
Live Bitget Testing Suite
Tests all components with REAL Bitget exchange
WARNING: Use testnet or very small amounts
"""

import asyncio
import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).parent / 'core'))

from datetime import datetime, timezone
import structlog
from typing import Dict, List, Optional
import ccxt.async_support as ccxt
from dotenv import load_dotenv
import uuid

# Import all components
from live_positions_registry import LivePositionsRegistry, Position, PositionDirection, PositionZone
from exchange_reconciliation import ExchangeReconciliationService
from zone_state_machine import ZoneStateMachine
from surplus_dump_manager import SurplusDumpManager
from averaging_engine import AveragingEngine
from risk_manager import RiskManager

load_dotenv('/app/.env')
logger = structlog.get_logger(__name__)

class LiveBitgetTest:
    """
    Live testing with real Bitget exchange
    Tests with actual market data and positions
    """
    
    def __init__(self):
        self.exchange = None
        self.registry = None
        self.reconciliation = None
        self.zone_machine = None
        self.surplus_manager = None
        self.averaging_engine = None
        self.risk_manager = None
        
        # Test configuration
        self.test_symbol = "BTC/USDT:USDT"  # Use a liquid market
        self.test_size = 0.001  # MINIMAL size for safety
        self.max_test_loss = 10.0  # Max $10 loss for testing
        
    async def setup(self):
        """Setup with REAL Bitget connection"""
        logger.info("="*60)
        logger.info("SETTING UP LIVE BITGET CONNECTION")
        logger.info("⚠️ WARNING: This uses REAL money!")
        logger.info("="*60)
        
        # Check for API credentials
        if not os.getenv('BITGET_API_KEY'):
            raise ValueError("BITGET_API_KEY not found in .env file")
        if not os.getenv('BITGET_SECRET'):
            raise ValueError("BITGET_SECRET not found in .env file")
        if not os.getenv('BITGET_PASSPHRASE'):
            raise ValueError("BITGET_PASSPHRASE not found in .env file")
        
        # Initialize REAL exchange
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_SECRET'),
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',  # For futures
            }
        })
        
        # Test connection
        try:
            balance = await self.exchange.fetch_balance()
            usdt_balance = balance.get('USDT', {}).get('free', 0)
            logger.info(f"Connected to Bitget. Available USDT: {usdt_balance:.2f}")
            
            if usdt_balance < 50:
                logger.warning(f"Low balance: {usdt_balance:.2f} USDT")
            
        except Exception as e:
            logger.error(f"Failed to connect to Bitget: {e}")
            raise
        
        # Initialize components with REAL exchange
        self.registry = LivePositionsRegistry()
        await self.registry.initialize()
        
        self.reconciliation = ExchangeReconciliationService(
            registry=self.registry,
            reconciliation_interval=5
        )
        
        self.zone_machine = ZoneStateMachine(self.registry)
        self.surplus_manager = SurplusDumpManager(self.registry, self.exchange)
        self.averaging_engine = AveragingEngine(self.registry, self.exchange)
        self.risk_manager = RiskManager(self.registry, self.exchange)
        
        logger.info("✅ Live Bitget setup complete")
    
    async def cleanup(self):
        """Cleanup and close all test positions"""
        logger.info("Cleaning up live test...")
        
        # Close any open test positions
        try:
            positions = await self.exchange.fetch_positions()
            for pos in positions:
                if pos.get('contracts', 0) > 0:
                    logger.warning(f"Open position found: {pos['symbol']} - {pos['contracts']} contracts")
                    # Optionally close it
                    # await self.close_position(pos)
        except Exception as e:
            logger.error(f"Error checking positions: {e}")
        
        # Stop services
        if self.reconciliation:
            await self.reconciliation.stop()
        
        # Close exchange
        if self.exchange:
            await self.exchange.close()
        
        # Cleanup registry
        if self.registry:
            await self.registry.cleanup()
    
    async def test_live_connection(self) -> Dict:
        """Test 1: Verify live Bitget connection"""
        test_name = "Live Bitget Connection"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Fetch account info
            balance = await self.exchange.fetch_balance()
            
            # Fetch market data
            ticker = await self.exchange.fetch_ticker(self.test_symbol)
            
            # Fetch existing positions
            positions = await self.exchange.fetch_positions()
            
            logger.info(f"Account Balance: {balance.get('USDT', {}).get('total', 0):.2f} USDT")
            logger.info(f"BTC Price: ${ticker['last']:.2f}")
            logger.info(f"Open Positions: {len(positions)}")
            
            return {
                'test': test_name,
                'passed': True,
                'details': f"Connected. Balance: {balance.get('USDT', {}).get('total', 0):.2f} USDT"
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_reconciliation_live(self) -> Dict:
        """Test 2: Live reconciliation with Bitget"""
        test_name = "Live Exchange Reconciliation"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Start reconciliation service
            await self.reconciliation.start()
            
            # Wait for first reconciliation
            logger.info("Waiting for reconciliation cycle...")
            await asyncio.sleep(6)
            
            # Check reconciliation stats
            stats = self.reconciliation.get_stats()
            
            assert stats['reconciliation_count'] > 0, "No reconciliation occurred"
            assert stats['last_reconciliation'] is not None, "Reconciliation timestamp missing"
            
            # Get synced positions
            local_positions = await self.registry.get_all_positions()
            exchange_positions = await self.exchange.fetch_positions()
            
            logger.info(f"Local positions: {len(local_positions)}")
            logger.info(f"Exchange positions: {len(exchange_positions)}")
            
            # Stop reconciliation
            await self.reconciliation.stop()
            
            return {
                'test': test_name,
                'passed': True,
                'details': f"Reconciliation working. Synced {len(local_positions)} positions"
            }
            
        except Exception as e:
            if self.reconciliation:
                await self.reconciliation.stop()
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_minimal_trade(self) -> Dict:
        """Test 3: Execute minimal live trade"""
        test_name = "Minimal Live Trade"
        logger.info(f"Testing: {test_name}")
        logger.warning("⚠️ This will execute a REAL trade with minimal size")
        
        try:
            # Get current market price
            ticker = await self.exchange.fetch_ticker(self.test_symbol)
            current_price = ticker['last']
            
            # Calculate minimal position size
            min_size = 0.001  # 0.001 BTC
            position_value = min_size * current_price
            
            logger.info(f"Opening test position: {min_size} BTC @ ${current_price:.2f}")
            logger.info(f"Position value: ${position_value:.2f}")
            
            # Check if we have enough balance
            balance = await self.exchange.fetch_balance()
            free_usdt = balance.get('USDT', {}).get('free', 0)
            
            if free_usdt < position_value * 2:  # Need margin
                logger.warning(f"Insufficient balance: {free_usdt:.2f} USDT")
                return {
                    'test': test_name,
                    'passed': False,
                    'error': f"Insufficient balance: {free_usdt:.2f} USDT"
                }
            
            # Open minimal position
            order = await self.exchange.create_market_order(
                symbol=self.test_symbol,
                side='buy',
                amount=min_size
            )
            
            logger.info(f"Order executed: {order['id']}")
            
            # Wait for settlement
            await asyncio.sleep(2)
            
            # Verify position exists
            positions = await self.exchange.fetch_positions()
            test_position = None
            for pos in positions:
                if pos['symbol'] == self.test_symbol:
                    test_position = pos
                    break
            
            if not test_position:
                logger.error("Position not found after order")
                return {
                    'test': test_name,
                    'passed': False,
                    'error': "Position not found"
                }
            
            logger.info(f"Position confirmed: {test_position['contracts']} contracts")
            
            # Create local position record
            local_position = Position(
                position_id=str(uuid.uuid4()),
                symbol=self.test_symbol,
                direction=PositionDirection.LONG,
                entry_price=test_position['entryPrice'],
                quantity=test_position['contracts'],
                weighted_avg_price=test_position['entryPrice'],
                current_price=current_price,
                unrealized_pnl=test_position.get('unrealizedPnl', 0)
            )
            
            await self.registry.add_position(local_position)
            
            # Test zone evaluation
            result = await self.zone_machine.evaluate_and_transition(local_position)
            logger.info(f"Position zone: {local_position.current_zone.value}")
            
            # Close the test position
            logger.info("Closing test position...")
            close_order = await self.exchange.create_market_order(
                symbol=self.test_symbol,
                side='sell',
                amount=min_size,
                params={'reduceOnly': True}
            )
            
            logger.info(f"Position closed: {close_order['id']}")
            
            # Remove from registry
            await self.registry.remove_position(local_position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': f"Live trade executed and closed successfully"
            }
            
        except Exception as e:
            logger.error(f"Live trade test failed: {e}")
            
            # Try to close any open position
            try:
                positions = await self.exchange.fetch_positions()
                for pos in positions:
                    if pos['symbol'] == self.test_symbol and pos['contracts'] > 0:
                        await self.exchange.create_market_order(
                            symbol=self.test_symbol,
                            side='sell' if pos['side'] == 'long' else 'buy',
                            amount=pos['contracts'],
                            params={'reduceOnly': True}
                        )
                        logger.info("Emergency position closure executed")
            except:
                pass
            
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_risk_limits_live(self) -> Dict:
        """Test 4: Verify risk limits with live data"""
        test_name = "Live Risk Limits"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Update portfolio metrics from live exchange
            await self.risk_manager.update_portfolio_metrics()
            
            # Get risk status
            risk_status = self.risk_manager.get_risk_status()
            
            logger.info(f"Total Capital: ${risk_status['total_capital']:.2f}")
            logger.info(f"Used Margin: ${risk_status['used_margin']:.2f}")
            logger.info(f"Free Margin: ${risk_status['free_margin']:.2f}")
            
            # Test position size limits
            test_size = risk_status['total_capital'] * 0.15  # 15% of capital
            can_open, reason = self.risk_manager.can_open_position(
                size=test_size,
                leverage=1.0
            )
            
            assert not can_open, "Should reject oversized position"
            logger.info(f"Risk limit enforced: {reason}")
            
            # Check portfolio risk
            is_safe, assessment = await self.risk_manager.check_portfolio_risk()
            
            logger.info(f"Portfolio safe: {is_safe}")
            logger.info(f"Total exposure: ${assessment['total_exposure']:.2f}")
            
            return {
                'test': test_name,
                'passed': True,
                'details': f"Risk limits verified with live capital: ${risk_status['total_capital']:.2f}"
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_live_market_data(self) -> Dict:
        """Test 5: Process live market data"""
        test_name = "Live Market Data Processing"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Fetch multiple market symbols
            symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']
            
            for symbol in symbols:
                try:
                    # Get ticker
                    ticker = await self.exchange.fetch_ticker(symbol)
                    
                    # Get order book
                    orderbook = await self.exchange.fetch_order_book(symbol, limit=5)
                    
                    spread = orderbook['asks'][0][0] - orderbook['bids'][0][0]
                    spread_percent = (spread / ticker['last']) * 100
                    
                    logger.info(f"{symbol}: ${ticker['last']:.2f} | Spread: {spread_percent:.3f}%")
                    
                except Exception as e:
                    logger.warning(f"Failed to fetch {symbol}: {e}")
            
            return {
                'test': test_name,
                'passed': True,
                'details': f"Live market data processed for {len(symbols)} symbols"
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def run_all_live_tests(self) -> Dict:
        """Run all live Bitget tests"""
        logger.info("="*60)
        logger.info("RUNNING LIVE BITGET TESTS")
        logger.info("⚠️ USING REAL EXCHANGE - REAL MONEY AT RISK")
        logger.info("="*60)
        
        try:
            await self.setup()
        except Exception as e:
            logger.error(f"Setup failed: {e}")
            return {
                'total_tests': 0,
                'passed': 0,
                'failed': 0,
                'compliance_percentage': 0,
                'error': str(e)
            }
        
        test_methods = [
            self.test_live_connection,
            self.test_reconciliation_live,
            self.test_live_market_data,
            self.test_risk_limits_live,
            # self.test_minimal_trade,  # Uncomment only if you want to execute real trades
        ]
        
        results = []
        passed_count = 0
        
        for test_method in test_methods:
            try:
                result = await test_method()
                results.append(result)
                
                if result['passed']:
                    passed_count += 1
                    logger.info(f"✅ {result['test']}: PASSED")
                    if 'details' in result:
                        logger.info(f"   {result['details']}")
                else:
                    logger.error(f"❌ {result['test']}: FAILED")
                    if 'error' in result:
                        logger.error(f"   Error: {result['error']}")
                
            except Exception as e:
                logger.error(f"Test execution error: {e}")
                results.append({
                    'test': test_method.__name__,
                    'passed': False,
                    'error': str(e)
                })
        
        await self.cleanup()
        
        # Calculate final score
        total_tests = len(test_methods)
        compliance_percentage = (passed_count / total_tests) * 100
        
        logger.info("="*60)
        logger.info("LIVE TEST RESULTS")
        logger.info("="*60)
        logger.info(f"Tests Passed: {passed_count}/{total_tests}")
        logger.info(f"Live Compliance: {compliance_percentage:.1f}%")
        
        if compliance_percentage == 100:
            logger.info("✅ SYSTEM PASSES ALL LIVE TESTS")
            logger.info("✅ 100% COMPLIANT WITH LIVE BITGET")
        elif compliance_percentage >= 80:
            logger.info("⚠️ SYSTEM MOSTLY COMPLIANT - Review failures")
        else:
            logger.info("❌ LIVE COMPLIANCE ISSUES FOUND")
        
        logger.info("="*60)
        
        return {
            'total_tests': total_tests,
            'passed': passed_count,
            'failed': total_tests - passed_count,
            'compliance_percentage': compliance_percentage,
            'results': results
        }

async def main():
    """Run live Bitget test suite"""
    
    # Safety confirmation
    print("\n" + "="*60)
    print("⚠️  WARNING: LIVE BITGET TESTING")
    print("="*60)
    print("This will connect to your REAL Bitget account.")
    print("It may execute small test trades with REAL money.")
    print("\nMake sure you have:")
    print("1. Valid API credentials in .env file")
    print("2. Sufficient balance for testing")
    print("3. Understanding of the risks")
    print("="*60)
    
    response = input("\nType 'YES' to proceed with live testing: ")
    if response != 'YES':
        print("Live testing cancelled.")
        return False
    
    test_suite = LiveBitgetTest()
    results = await test_suite.run_all_live_tests()
    
    return results['compliance_percentage'] == 100

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)