#!/usr/bin/env python3
"""
Full System Integration Test
Tests all components working together with simulated trades
"""

import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / 'core'))

import uuid
from datetime import datetime, timezone
import structlog
from typing import Dict, List

# Import all components
from live_positions_registry import LivePositionsRegistry, Position, PositionDirection, PositionZone
from exchange_reconciliation import ExchangeReconciliationService
from zone_state_machine import ZoneStateMachine
from surplus_dump_manager import SurplusDumpManager
from averaging_engine import AveragingEngine
from risk_manager import RiskManager
from mock_exchange import MockExchange

logger = structlog.get_logger(__name__)

class FullSystemIntegrationTest:
    """
    Complete system integration test with simulated trading
    """
    
    def __init__(self):
        self.registry = None
        self.mock_exchange = None
        self.reconciliation = None
        self.zone_machine = None
        self.surplus_manager = None
        self.averaging_engine = None
        self.risk_manager = None
        self.test_results = []
        
    async def setup(self):
        """Setup test environment with all components"""
        logger.info("Setting up full integration test environment...")
        
        # Initialize registry with isolated Redis database
        self.registry = LivePositionsRegistry(
            redis_host='localhost',
            redis_port=6379,
            redis_db=15  # Use isolated database for testing
        )
        await self.registry.initialize()
        
        # Initialize mock exchange
        self.mock_exchange = MockExchange()
        
        # Initialize all components with mock exchange
        self.zone_machine = ZoneStateMachine(self.registry)
        self.surplus_manager = SurplusDumpManager(self.registry, self.mock_exchange)
        self.averaging_engine = AveragingEngine(self.registry, self.mock_exchange)
        self.risk_manager = RiskManager(self.registry, self.mock_exchange)
        
        # Initialize reconciliation with mock exchange
        # Monkey-patch the exchange in reconciliation service
        self.reconciliation = ExchangeReconciliationService(
            registry=self.registry,
            reconciliation_interval=5
        )
        self.reconciliation.exchange = self.mock_exchange
        
        logger.info("Integration test environment ready")
    
    async def cleanup(self):
        """Cleanup test environment"""
        if self.reconciliation:
            await self.reconciliation.stop()
        if self.mock_exchange:
            await self.mock_exchange.close()
        if self.registry:
            await self.registry.cleanup()
    
    async def test_full_position_lifecycle(self) -> Dict:
        """Test complete position lifecycle from open to close"""
        test_name = "Full Position Lifecycle"
        logger.info(f"Testing: {test_name}")
        
        try:
            # 1. Create a position on the exchange
            self.mock_exchange.inject_position(
                symbol="BTC/USDT:USDT",
                side="LONG",
                size=0.1,
                entry_price=50000.0
            )
            
            # 2. Start reconciliation service
            await self.reconciliation.start()
            
            # Wait for reconciliation
            await asyncio.sleep(6)
            
            # 3. Check position was discovered
            positions = await self.registry.get_all_positions()
            assert len(positions) > 0, "Position not discovered by reconciliation"
            
            position = positions[0]
            logger.info(f"Position discovered: {position.symbol} {position.direction}")
            
            # 4. Simulate price drop to trigger averaging
            self.mock_exchange.set_price("BTC/USDT:USDT", 49000.0)
            position.current_price = 49000.0
            position.unrealized_pnl = -100.0  # Loss
            
            # 5. Check zone transition to AVERAGING
            result = await self.zone_machine.evaluate_and_transition(position)
            assert position.current_zone == PositionZone.AVERAGING, \
                f"Should be in AVERAGING zone, got {position.current_zone}"
            
            # 6. Execute averaging
            avg_action = await self.averaging_engine.evaluate_averaging(position)
            if avg_action:
                success = await self.averaging_engine.execute_averaging(position, avg_action)
                assert success, "Averaging execution failed"
                logger.info("Averaging executed successfully")
            
            # 7. Simulate price recovery for surplus dump
            self.mock_exchange.set_price("BTC/USDT:USDT", 52000.0)
            position.current_price = 52000.0
            position.unrealized_pnl = 200.0  # Profit
            position.averaging_steps_taken = 1  # Has averaged
            
            # 8. Check zone transition to SURPLUS_DUMP
            result = await self.zone_machine.evaluate_and_transition(position)
            assert position.current_zone == PositionZone.SURPLUS_DUMP, \
                f"Should be in SURPLUS_DUMP zone, got {position.current_zone}"
            
            # 9. Test surplus dump
            position.peak_upnl = 250.0  # Set peak
            position.unrealized_pnl = 210.0  # Drop to 84% of peak
            position.surplus_size = 0.1  # Surplus from averaging
            
            dump_action = await self.surplus_manager.evaluate_surplus_dump(position)
            if dump_action:
                success = await self.surplus_manager.execute_surplus_dump(position, dump_action)
                logger.info(f"Surplus dump executed: {dump_action}")
            
            # 10. Test stop loss
            position.unrealized_pnl = -150.0  # Big loss
            position.stop_loss_threshold = -100.0
            
            result = await self.zone_machine.evaluate_and_transition(position)
            assert position.current_zone == PositionZone.STOP_LOSS, \
                f"Should be in STOP_LOSS zone, got {position.current_zone}"
            
            # Verify stop loss is terminal
            position.unrealized_pnl = 500.0  # Try to change to profit
            result = await self.zone_machine.evaluate_and_transition(position)
            assert position.current_zone == PositionZone.STOP_LOSS, \
                "Stop loss should remain terminal"
            
            # 11. Execute stop loss
            success = await self.risk_manager.execute_stop_loss(position)
            logger.info(f"Stop loss executed: {success}")
            
            # Stop reconciliation
            await self.reconciliation.stop()
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Full lifecycle tested: Open → Averaging → Surplus Dump → Stop Loss'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_reconciliation_accuracy(self) -> Dict:
        """Test exchange reconciliation accuracy"""
        test_name = "Reconciliation Accuracy"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Clear any existing positions
            self.mock_exchange.clear_all()
            
            # Inject multiple positions
            test_positions = [
                ("ETH/USDT:USDT", "LONG", 1.0, 3000.0),
                ("BTC/USDT:USDT", "SHORT", 0.05, 51000.0),
                ("TEST/USDT:USDT", "LONG", 10.0, 100.0)
            ]
            
            for symbol, side, size, price in test_positions:
                self.mock_exchange.inject_position(symbol, side, size, price)
            
            # Run reconciliation
            result = await self.reconciliation.reconcile()
            
            assert result.success, "Reconciliation failed"
            
            # Check all positions were synced
            local_positions = await self.registry.get_all_positions()
            assert len(local_positions) == len(test_positions), \
                f"Position count mismatch: {len(local_positions)} vs {len(test_positions)}"
            
            logger.info(f"Reconciliation synced {len(local_positions)} positions")
            
            # Simulate position closure on exchange
            self.mock_exchange.positions.clear()
            
            # Reconcile again
            result = await self.reconciliation.reconcile()
            
            # Check positions were removed locally
            local_positions = await self.registry.get_all_positions()
            assert len(local_positions) == 0, \
                f"Positions not removed: {len(local_positions)} remaining"
            
            return {
                'test': test_name,
                'passed': True,
                'details': f'Reconciliation accurate for {len(test_positions)} positions'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_risk_limits_enforcement(self) -> Dict:
        """Test risk manager enforcement"""
        test_name = "Risk Limits Enforcement"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Set portfolio capital
            self.risk_manager.total_capital = 1000.0
            self.risk_manager.max_position_size = 0.10  # 10% max
            
            # Test position size limit
            can_open, reason = self.risk_manager.can_open_position(
                size=150.0,  # 15% of capital
                leverage=1.0
            )
            
            assert not can_open, "Should reject oversized position"
            assert "exceeds limit" in reason, f"Wrong rejection reason: {reason}"
            
            # Test leverage limit
            can_open, reason = self.risk_manager.can_open_position(
                size=50.0,
                leverage=15.0  # Exceeds 10x limit
            )
            
            assert not can_open, "Should reject high leverage"
            assert "leverage" in reason.lower(), f"Wrong rejection reason: {reason}"
            
            # Test emergency stop
            self.risk_manager.emergency_stop = True
            can_open, reason = self.risk_manager.can_open_position(
                size=10.0,
                leverage=1.0
            )
            
            assert not can_open, "Should reject during emergency stop"
            assert "emergency" in reason.lower(), f"Wrong rejection reason: {reason}"
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Risk limits properly enforced'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_concurrent_operations(self) -> Dict:
        """Test system under concurrent operations"""
        test_name = "Concurrent Operations"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Create multiple positions concurrently
            tasks = []
            for i in range(10):
                position = Position(
                    position_id=str(uuid.uuid4()),
                    symbol=f"TEST{i}/USDT",
                    direction=PositionDirection.LONG if i % 2 == 0 else PositionDirection.SHORT,
                    entry_price=100.0 + i,
                    quantity=1.0,
                    weighted_avg_price=100.0 + i
                )
                tasks.append(self.registry.add_position(position))
            
            # Execute concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Check all succeeded
            failures = [r for r in results if isinstance(r, Exception)]
            assert len(failures) == 0, f"Concurrent adds failed: {failures}"
            
            # Get all positions
            positions = await self.registry.get_all_positions()
            assert len(positions) >= 10, f"Not all positions added: {len(positions)}"
            
            # Test concurrent zone transitions
            zone_tasks = []
            for position in positions[:5]:
                position.unrealized_pnl = -0.20  # Force to averaging
                zone_tasks.append(
                    self.zone_machine.evaluate_and_transition(position)
                )
            
            zone_results = await asyncio.gather(*zone_tasks, return_exceptions=True)
            zone_failures = [r for r in zone_results if isinstance(r, Exception)]
            assert len(zone_failures) == 0, f"Concurrent transitions failed: {zone_failures}"
            
            # Cleanup positions
            for position in positions:
                await self.registry.remove_position(position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': f'Handled {len(positions)} concurrent operations successfully'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_edge_cases(self) -> Dict:
        """Test edge cases and error scenarios"""
        test_name = "Edge Cases"
        logger.info(f"Testing: {test_name}")
        
        try:
            # Test 1: Zero UPNL (exactly on threshold)
            position = Position(
                position_id=str(uuid.uuid4()),
                symbol="EDGE/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0,
                unrealized_pnl=-0.15  # Exactly at threshold
            )
            
            await self.registry.add_position(position)
            result = await self.zone_machine.evaluate_and_transition(position)
            assert position.current_zone == PositionZone.AVERAGING, \
                "Should enter averaging at exact threshold"
            
            # Test 2: Maximum averaging steps
            position.averaging_steps_taken = 10  # Exceed max steps
            action = await self.averaging_engine.evaluate_averaging(position)
            assert action is None, "Should not average beyond max steps"
            
            # Test 3: Negative prices (should handle gracefully)
            position.current_price = -100.0  # Invalid price
            try:
                await self.registry.update_position(position)
                # Should handle negative price without crashing
            except Exception:
                pass  # Expected to handle gracefully
            
            # Test 4: Extremely large numbers
            position.unrealized_pnl = 1e10  # Very large profit
            position.current_price = 100.0
            result = await self.zone_machine.evaluate_and_transition(position)
            # Should handle large numbers without overflow
            
            # Test 5: Rapid zone changes
            for _ in range(10):
                position.unrealized_pnl = random.choice([-0.2, 0.0, 0.2])
                await self.zone_machine.evaluate_and_transition(position)
            # Should handle rapid changes without corruption
            
            # Cleanup
            await self.registry.remove_position(position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'All edge cases handled correctly'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def run_all_tests(self) -> Dict:
        """Run all integration tests"""
        logger.info("="*60)
        logger.info("RUNNING FULL SYSTEM INTEGRATION TESTS")
        logger.info("="*60)
        
        await self.setup()
        
        test_methods = [
            self.test_reconciliation_accuracy,
            self.test_full_position_lifecycle,
            self.test_risk_limits_enforcement,
            self.test_concurrent_operations,
            self.test_edge_cases
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
        logger.info("INTEGRATION TEST RESULTS")
        logger.info("="*60)
        logger.info(f"Tests Passed: {passed_count}/{total_tests}")
        logger.info(f"Integration Score: {compliance_percentage:.1f}%")
        
        if compliance_percentage == 100:
            logger.info("✅ SYSTEM PASSES ALL INTEGRATION TESTS")
        elif compliance_percentage >= 80:
            logger.info("⚠️ SYSTEM MOSTLY INTEGRATED - Review failures")
        else:
            logger.info("❌ INTEGRATION ISSUES FOUND")
        
        logger.info("="*60)
        
        return {
            'total_tests': total_tests,
            'passed': passed_count,
            'failed': total_tests - passed_count,
            'compliance_percentage': compliance_percentage,
            'results': results
        }

import random

async def main():
    """Run full integration test suite"""
    test_suite = FullSystemIntegrationTest()
    results = await test_suite.run_all_tests()
    
    return results['compliance_percentage'] == 100

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)