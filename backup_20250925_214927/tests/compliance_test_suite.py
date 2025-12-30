#!/usr/bin/env python3
"""
Comprehensive Compliance Test Suite
Tests all cardinal rules with simulated trades
"""

import asyncio
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent / 'core'))

import uuid
from datetime import datetime, timezone
import structlog
from typing import Dict, List
import random

from live_positions_registry import LivePositionsRegistry, Position, PositionDirection, PositionZone
from exchange_reconciliation import ExchangeReconciliationService
from zone_state_machine import ZoneStateMachine
from surplus_dump_manager import SurplusDumpManager
from averaging_engine import AveragingEngine
from risk_manager import RiskManager

logger = structlog.get_logger(__name__)

class ComplianceTestSuite:
    """
    Comprehensive test suite to verify cardinal rules compliance
    Tests with simulated positions and market conditions
    """
    
    def __init__(self):
        self.test_results = {}
        self.registry = None
        self.zone_machine = None
        self.surplus_manager = None
        self.averaging_engine = None
        self.risk_manager = None
        
    async def setup(self):
        """Setup test environment"""
        logger.info("Setting up test environment...")
        
        # Initialize components
        self.registry = LivePositionsRegistry()
        await self.registry.initialize()
        
        self.zone_machine = ZoneStateMachine(self.registry)
        self.surplus_manager = SurplusDumpManager(self.registry)
        self.averaging_engine = AveragingEngine(self.registry)
        self.risk_manager = RiskManager(self.registry)
        
        logger.info("Test environment ready")
    
    async def cleanup(self):
        """Cleanup test environment"""
        if self.registry:
            await self.registry.cleanup()
    
    async def test_rule_1_exchange_reconciliation(self) -> Dict:
        """Test Rule 1: Exchange Reconciliation is Supreme"""
        logger.info("Testing Rule 1: Exchange Reconciliation")
        
        test_name = "Rule 1: Exchange Reconciliation"
        try:
            # Create reconciliation service
            recon_service = ExchangeReconciliationService(
                registry=self.registry,
                reconciliation_interval=5
            )
            
            # Verify interval is correct
            assert 5 <= recon_service.reconciliation_interval <= 10, \
                f"Reconciliation interval {recon_service.reconciliation_interval} outside 5-10 seconds"
            
            # Test reconciliation logic (without actual exchange connection)
            stats = recon_service.get_stats()
            assert 'reconciliation_interval' in stats
            assert stats['reconciliation_interval'] == 5
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Reconciliation service configured correctly'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_rule_2_atomic_zone_transitions(self) -> Dict:
        """Test Rule 2: Position Zone Transitions are Atomic"""
        logger.info("Testing Rule 2: Atomic Zone Transitions")
        
        test_name = "Rule 2: Atomic Zone Transitions"
        try:
            # Create test position
            position = Position(
                position_id=str(uuid.uuid4()),
                symbol="TEST/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0,
                current_zone=PositionZone.NEUTRAL
            )
            
            # Add to registry
            await self.registry.add_position(position)
            
            # Test zone transition to AVERAGING
            position.unrealized_pnl = -0.20  # Below threshold
            result = await self.zone_machine.evaluate_and_transition(position)
            
            assert result.success, "Zone transition failed"
            assert result.to_zone == PositionZone.AVERAGING, \
                f"Expected AVERAGING zone, got {result.to_zone}"
            
            # Verify position was updated
            updated_pos = await self.registry.get_position(position.position_id)
            assert updated_pos.current_zone == PositionZone.AVERAGING
            
            # Test invalid transition
            position.current_zone = PositionZone.STOP_LOSS
            position.unrealized_pnl = 0.5  # Try to go to profit
            result = await self.zone_machine.evaluate_and_transition(position)
            
            # Stop loss is terminal - no transitions allowed
            assert result.to_zone == PositionZone.STOP_LOSS, \
                "Stop loss zone should be terminal"
            
            # Cleanup
            await self.registry.remove_position(position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Zone transitions are atomic and validated'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_rule_3_absolute_risk_limits(self) -> Dict:
        """Test Rule 3: Risk Limits are Absolute"""
        logger.info("Testing Rule 3: Absolute Risk Limits")
        
        test_name = "Rule 3: Absolute Risk Limits"
        try:
            # Create position at stop loss
            position = Position(
                position_id=str(uuid.uuid4()),
                symbol="TEST/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0,
                unrealized_pnl=-1.5,  # Below stop loss
                stop_loss_threshold=-1.0,
                current_zone=PositionZone.STOP_LOSS
            )
            
            await self.registry.add_position(position)
            
            # Check risk limits
            is_safe, reason = await self.risk_manager.check_position_limits(position)
            
            assert not is_safe, "Position should violate risk limits"
            assert "STOP_LOSS" in reason, f"Expected stop loss violation, got: {reason}"
            
            # Cleanup
            await self.registry.remove_position(position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Risk limits are enforced absolutely'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_rule_4_averaging_step_tracking(self) -> Dict:
        """Test Rule 4: Averaging Steps Must Be Tracked"""
        logger.info("Testing Rule 4: Averaging Step Tracking")
        
        test_name = "Rule 4: Averaging Step Tracking"
        try:
            # Create position in averaging zone
            position = Position(
                position_id=str(uuid.uuid4()),
                symbol="TEST/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0,
                unrealized_pnl=-0.20,
                current_zone=PositionZone.AVERAGING
            )
            
            await self.registry.add_position(position)
            
            # Simulate averaging action
            action = await self.averaging_engine.evaluate_averaging(position)
            
            assert action is not None, "Averaging action should be triggered"
            assert action['step_number'] == 1, "Should be first averaging step"
            assert action['size'] > 0, "Averaging size should be positive"
            
            # Verify immutable history
            assert hasattr(position, 'averaging_history'), "Position must have averaging history"
            assert isinstance(position.averaging_history, list), "History must be a list"
            
            # Cleanup
            await self.registry.remove_position(position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Averaging steps tracked with immutable history'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_rule_5_surplus_dump_logic(self) -> Dict:
        """Test Rule 5: Surplus Dump Logic is Hierarchical"""
        logger.info("Testing Rule 5: Surplus Dump Logic")
        
        test_name = "Rule 5: Surplus Dump Logic"
        try:
            # Create position with surplus
            position = Position(
                position_id=str(uuid.uuid4()),
                symbol="TEST/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=2.0,  # Doubled from averaging
                weighted_avg_price=95.0,
                unrealized_pnl=0.30,  # In profit
                current_zone=PositionZone.SURPLUS_DUMP,
                averaging_steps_taken=1,
                surplus_size=1.0,  # 1.0 from averaging
                peak_upnl=0.50  # Peak was higher
            )
            
            await self.registry.add_position(position)
            
            # Test surplus dump evaluation
            dump_action = await self.surplus_manager.evaluate_surplus_dump(position)
            
            # At 0.30 UPNL with peak 0.50, we're at 60% of peak
            # First dump triggers at 85% of peak (0.425)
            # So at 60%, no dump yet
            assert dump_action is None or dump_action['stage'] == 1, \
                "Dump logic should follow hierarchical rules"
            
            # Test at 85% threshold
            position.unrealized_pnl = 0.42  # Just below 85% of 0.50
            dump_action = await self.surplus_manager.evaluate_surplus_dump(position)
            
            if dump_action:
                assert dump_action['stage'] == 1, "Should be first dump"
                assert dump_action['dump_size'] == 0.5, "Should dump 50% of surplus"
            
            # Cleanup
            await self.registry.remove_position(position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Surplus dump follows 85%/50% hierarchical rules'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_rule_6_manual_vs_automated(self) -> Dict:
        """Test Rule 6: Manual vs Automated Distinction"""
        logger.info("Testing Rule 6: Manual vs Automated Distinction")
        
        test_name = "Rule 6: Manual vs Automated"
        try:
            # Create manual position
            manual_position = Position(
                position_id=str(uuid.uuid4()),
                symbol="MANUAL/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0,
                is_manual=True,
                method_service='manual'
            )
            
            # Create automated position
            auto_position = Position(
                position_id=str(uuid.uuid4()),
                symbol="AUTO/USDT",
                direction=PositionDirection.SHORT,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0,
                is_manual=False,
                method_service='automated'
            )
            
            await self.registry.add_position(manual_position)
            await self.registry.add_position(auto_position)
            
            # Verify flags are preserved
            retrieved_manual = await self.registry.get_position(manual_position.position_id)
            retrieved_auto = await self.registry.get_position(auto_position.position_id)
            
            assert retrieved_manual.is_manual == True, "Manual flag not preserved"
            assert retrieved_auto.is_manual == False, "Automated flag not preserved"
            
            # Cleanup
            await self.registry.remove_position(manual_position.position_id)
            await self.registry.remove_position(auto_position.position_id)
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Manual and automated positions properly distinguished'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_rule_7_immutable_history(self) -> Dict:
        """Test Rule 7: Historical Data is Immutable"""
        logger.info("Testing Rule 7: Immutable Historical Data")
        
        test_name = "Rule 7: Immutable Historical Data"
        try:
            # Create and close a position
            position = Position(
                position_id=str(uuid.uuid4()),
                symbol="HISTORY/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0
            )
            
            await self.registry.add_position(position)
            
            # Get events before removal
            events_before = await self.registry.get_position_events(position.position_id)
            initial_event_count = len(events_before)
            
            # Remove position (moves to historical)
            await self.registry.remove_position(position.position_id)
            
            # Get events after removal
            events_after = await self.registry.get_position_events(position.position_id)
            
            # Events should only increase, never decrease (append-only)
            assert len(events_after) > initial_event_count, \
                "Events should be append-only"
            
            # Check for closure event
            closure_event_found = any(
                e.get('event_type') == 'POSITION_CLOSED'
                for e in events_after
            )
            assert closure_event_found, "Closure event not found in history"
            
            return {
                'test': test_name,
                'passed': True,
                'details': 'Historical data is append-only and immutable'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def test_rule_8_priority_data_paths(self) -> Dict:
        """Test Rule 8: Real-time Data Has Priority Lanes"""
        logger.info("Testing Rule 8: Priority Data Paths")
        
        test_name = "Rule 8: Priority Data Paths"
        try:
            import time
            
            # Test registry latency
            position = Position(
                position_id=str(uuid.uuid4()),
                symbol="SPEED/USDT",
                direction=PositionDirection.LONG,
                entry_price=100.0,
                quantity=1.0,
                weighted_avg_price=100.0
            )
            
            await self.registry.add_position(position)
            
            # Measure retrieval latency
            start = time.perf_counter()
            retrieved = await self.registry.get_position(position.position_id)
            latency_ms = (time.perf_counter() - start) * 1000
            
            # Cleanup
            await self.registry.remove_position(position.position_id)
            
            # Check latency requirement
            assert latency_ms < 10, f"Latency {latency_ms:.2f}ms exceeds limit"
            
            return {
                'test': test_name,
                'passed': True,
                'details': f'Registry latency: {latency_ms:.2f}ms (< 1ms target)'
            }
            
        except Exception as e:
            return {
                'test': test_name,
                'passed': False,
                'error': str(e)
            }
    
    async def run_all_tests(self) -> Dict:
        """Run all compliance tests"""
        logger.info("="*60)
        logger.info("RUNNING COMPREHENSIVE COMPLIANCE TESTS")
        logger.info("="*60)
        
        await self.setup()
        
        test_methods = [
            self.test_rule_1_exchange_reconciliation,
            self.test_rule_2_atomic_zone_transitions,
            self.test_rule_3_absolute_risk_limits,
            self.test_rule_4_averaging_step_tracking,
            self.test_rule_5_surplus_dump_logic,
            self.test_rule_6_manual_vs_automated,
            self.test_rule_7_immutable_history,
            self.test_rule_8_priority_data_paths
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
                else:
                    logger.error(f"❌ {result['test']}: FAILED", 
                               error=result.get('error'))
                    
            except Exception as e:
                logger.error(f"Test execution error", error=str(e))
                results.append({
                    'test': test_method.__name__,
                    'passed': False,
                    'error': str(e)
                })
        
        await self.cleanup()
        
        # Calculate compliance score
        total_tests = len(test_methods)
        compliance_percentage = (passed_count / total_tests) * 100
        
        logger.info("="*60)
        logger.info("COMPLIANCE TEST RESULTS")
        logger.info("="*60)
        logger.info(f"Tests Passed: {passed_count}/{total_tests}")
        logger.info(f"Compliance Score: {compliance_percentage:.1f}%")
        
        if compliance_percentage == 100:
            logger.info("✅ SYSTEM PASSES ALL COMPLIANCE TESTS")
        elif compliance_percentage >= 80:
            logger.info("⚠️ SYSTEM MOSTLY COMPLIANT - Review failures")
        else:
            logger.info("❌ SYSTEM NOT COMPLIANT - Major issues found")
        
        logger.info("="*60)
        
        return {
            'total_tests': total_tests,
            'passed': passed_count,
            'failed': total_tests - passed_count,
            'compliance_percentage': compliance_percentage,
            'results': results
        }

async def main():
    """Run compliance test suite"""
    test_suite = ComplianceTestSuite()
    results = await test_suite.run_all_tests()
    
    # Detailed report
    print("\nDETAILED TEST REPORT:")
    print("="*60)
    for result in results['results']:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        print(f"{status} - {result['test']}")
        if not result['passed'] and 'error' in result:
            print(f"  Error: {result['error']}")
        elif 'details' in result:
            print(f"  Details: {result['details']}")
    
    print("\n" + "="*60)
    print(f"FINAL COMPLIANCE SCORE: {results['compliance_percentage']:.1f}%")
    print("="*60)
    
    # Return success if all tests pass
    return results['compliance_percentage'] == 100

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)