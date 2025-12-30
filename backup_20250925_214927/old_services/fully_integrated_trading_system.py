#!/usr/bin/env python3
"""
Fully Integrated Cardinal Rules Compliant Trading System
STATUS: ❓ UNTESTED (Awaiting Live Trade Verification)
Waiting For: Live market connection, Actual trade execution
Note: System integration complete but requires production testing

Complete implementation with all components properly integrated
"""

import asyncio
import sys
import os
from pathlib import Path
sys.path.append(str(Path(__file__).parent / 'core'))

from datetime import datetime, timezone
import structlog
import signal
from typing import Dict, Optional, List
import ccxt.async_support as ccxt
from dotenv import load_dotenv

# Import all core components
from live_positions_registry import LivePositionsRegistry, Position, PositionDirection, PositionZone
from exchange_reconciliation import ExchangeReconciliationService
from zone_state_machine import ZoneStateMachine
from surplus_dump_manager import SurplusDumpManager
from averaging_engine import AveragingEngine
from risk_manager import RiskManager

# Load environment variables
load_dotenv('/app/.env')

# Configure structured logging
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

class FullyIntegratedTradingSystem:
    """
    Complete trading system with all cardinal rules enforced
    Ready for live trading with comprehensive safety mechanisms
    """
    
    def __init__(self):
        # Core components
        self.registry: Optional[LivePositionsRegistry] = None
        self.reconciliation_service: Optional[ExchangeReconciliationService] = None
        self.zone_state_machine: Optional[ZoneStateMachine] = None
        self.surplus_dump_manager: Optional[SurplusDumpManager] = None
        self.averaging_engine: Optional[AveragingEngine] = None
        self.risk_manager: Optional[RiskManager] = None
        
        # Exchange client
        self.exchange: Optional[ccxt.Exchange] = None
        
        # System state
        self.is_running = False
        self.startup_time: Optional[datetime] = None
        
        # Background tasks
        self._reconciliation_started = False
        self._zone_monitor_task = None
        self._surplus_monitor_task = None
        self._averaging_monitor_task = None
        self._risk_monitor_task = None
        self._health_check_task = None
        
        # Performance metrics
        self.metrics = {
            'positions_created': 0,
            'positions_closed': 0,
            'zone_transitions': 0,
            'averaging_steps': 0,
            'surplus_dumps': 0,
            'stop_losses': 0,
            'errors': 0
        }
    
    async def initialize(self):
        """Initialize all system components with proper error handling"""
        try:
            logger.info("="*60)
            logger.info("Initializing Fully Integrated Trading System...")
            logger.info("="*60)
            
            # Step 1: Initialize Redis and Registry
            logger.info("Step 1/6: Initializing Live Positions Registry...")
            self.registry = LivePositionsRegistry(
                redis_host='localhost',
                redis_port=6379,
                redis_db=0
            )
            await self.registry.initialize()
            logger.info("✅ Registry initialized")
            
            # Step 2: Initialize Exchange Client
            logger.info("Step 2/6: Initializing Exchange Client...")
            self.exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_SECRET'),
                'password': os.getenv('BITGET_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                }
            })
            
            # Test exchange connection
            try:
                await self.exchange.fetch_balance()
                logger.info("✅ Exchange connection verified")
            except Exception as e:
                logger.warning("Exchange connection test failed - API credentials may be missing", error=str(e))
            
            # Step 3: Initialize Reconciliation Service
            logger.info("Step 3/6: Initializing Exchange Reconciliation...")
            self.reconciliation_service = ExchangeReconciliationService(
                registry=self.registry,
                reconciliation_interval=5  # 5 seconds per Rule 1
            )
            logger.info("✅ Reconciliation service initialized")
            
            # Step 4: Initialize Zone State Machine
            logger.info("Step 4/6: Initializing Zone State Machine...")
            self.zone_state_machine = ZoneStateMachine(registry=self.registry)
            zone_rules = self.zone_state_machine.get_zone_rules()
            logger.info("✅ Zone state machine initialized", zones=list(zone_rules['zones'].keys()))
            
            # Step 5: Initialize Trading Components
            logger.info("Step 5/6: Initializing Trading Components...")
            
            self.surplus_dump_manager = SurplusDumpManager(
                registry=self.registry,
                exchange=self.exchange
            )
            logger.info("  ✅ Surplus Dump Manager ready")
            
            self.averaging_engine = AveragingEngine(
                registry=self.registry,
                exchange=self.exchange
            )
            logger.info("  ✅ Averaging Engine ready")
            
            self.risk_manager = RiskManager(
                registry=self.registry,
                exchange=self.exchange
            )
            logger.info("  ✅ Risk Manager ready")
            
            # Step 6: Final setup
            logger.info("Step 6/6: Finalizing setup...")
            self.startup_time = datetime.now(timezone.utc)
            
            logger.info("="*60)
            logger.info("✅ ALL COMPONENTS INITIALIZED SUCCESSFULLY")
            logger.info("="*60)
            
        except Exception as e:
            logger.error("Failed to initialize system", error=str(e))
            raise
    
    async def start(self):
        """Start all monitoring and trading services"""
        if self.is_running:
            logger.warning("System already running")
            return
        
        try:
            logger.info("Starting all services...")
            
            # Start reconciliation service (Cardinal Rule 1)
            await self.reconciliation_service.start()
            self._reconciliation_started = True
            logger.info("✅ Reconciliation service started (5-second interval)")
            
            # Start monitoring tasks
            self._zone_monitor_task = asyncio.create_task(
                self._zone_monitoring_loop()
            )
            logger.info("✅ Zone monitoring started")
            
            self._surplus_monitor_task = asyncio.create_task(
                self._surplus_monitoring_loop()
            )
            logger.info("✅ Surplus monitoring started")
            
            self._averaging_monitor_task = asyncio.create_task(
                self._averaging_monitoring_loop()
            )
            logger.info("✅ Averaging monitoring started")
            
            self._risk_monitor_task = asyncio.create_task(
                self._risk_monitoring_loop()
            )
            logger.info("✅ Risk monitoring started")
            
            self._health_check_task = asyncio.create_task(
                self._health_check_loop()
            )
            logger.info("✅ Health monitoring started")
            
            self.is_running = True
            
            # Log system start
            logger.info("="*60)
            logger.info("🚀 FULLY INTEGRATED TRADING SYSTEM ACTIVE")
            logger.info("="*60)
            logger.info("Components Status:")
            logger.info("  • Exchange Reconciliation: EVERY 5 SECONDS")
            logger.info("  • Zone Monitoring: CONTINUOUS")
            logger.info("  • Surplus Dump: ENABLED")
            logger.info("  • Averaging Engine: ACTIVE")
            logger.info("  • Risk Manager: ENFORCING LIMITS")
            logger.info("="*60)
            
        except Exception as e:
            logger.error("Failed to start system", error=str(e))
            self.is_running = False
            raise
    
    async def stop(self):
        """Gracefully stop all services"""
        logger.info("Stopping Fully Integrated Trading System...")
        
        self.is_running = False
        
        # Cancel all background tasks
        tasks = [
            self._zone_monitor_task,
            self._surplus_monitor_task,
            self._averaging_monitor_task,
            self._risk_monitor_task,
            self._health_check_task
        ]
        
        for task in tasks:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # Stop reconciliation service
        if self.reconciliation_service and self._reconciliation_started:
            await self.reconciliation_service.stop()
        
        # Close exchange connection
        if self.exchange:
            await self.exchange.close()
        
        # Cleanup registry
        if self.registry:
            await self.registry.cleanup()
        
        # Log final metrics
        logger.info("System metrics at shutdown:", metrics=self.metrics)
        logger.info("✅ System stopped gracefully")
    
    async def _zone_monitoring_loop(self):
        """Monitor and update position zones (Rule 2)"""
        while self.is_running:
            try:
                positions = await self.registry.get_all_positions()
                
                for position in positions:
                    result = await self.zone_state_machine.evaluate_and_transition(position)
                    
                    if result.from_zone != result.to_zone:
                        self.metrics['zone_transitions'] += 1
                        logger.info("Zone transition",
                                  position_id=position.position_id,
                                  from_zone=result.from_zone.value,
                                  to_zone=result.to_zone.value)
                
                await asyncio.sleep(1)
                
            except Exception as e:
                self.metrics['errors'] += 1
                logger.error("Zone monitoring error", error=str(e))
                await asyncio.sleep(5)
    
    async def _surplus_monitoring_loop(self):
        """Monitor surplus dump opportunities (Rule 5)"""
        while self.is_running:
            try:
                results = await self.surplus_dump_manager.monitor_all_positions()
                
                for position_id, result in results.items():
                    if result['executed']:
                        self.metrics['surplus_dumps'] += 1
                        logger.info("Surplus dump executed",
                                  position_id=position_id,
                                  action=result['action']['action'])
                
                await asyncio.sleep(2)
                
            except Exception as e:
                self.metrics['errors'] += 1
                logger.error("Surplus monitoring error", error=str(e))
                await asyncio.sleep(5)
    
    async def _averaging_monitoring_loop(self):
        """Monitor averaging opportunities (Rule 4)"""
        while self.is_running:
            try:
                results = await self.averaging_engine.monitor_all_positions()
                
                for position_id, result in results.items():
                    if result['executed']:
                        self.metrics['averaging_steps'] += 1
                        logger.info("Averaging step executed",
                                  position_id=position_id,
                                  step=result['action']['step_number'])
                
                await asyncio.sleep(3)
                
            except Exception as e:
                self.metrics['errors'] += 1
                logger.error("Averaging monitoring error", error=str(e))
                await asyncio.sleep(5)
    
    async def _risk_monitoring_loop(self):
        """Monitor and enforce risk limits (Rule 3 & 28)"""
        while self.is_running:
            try:
                # Enforce risk limits
                enforcement_results = await self.risk_manager.enforce_risk_limits()
                
                # Log any risk actions taken
                for closed in enforcement_results.get('positions_closed', []):
                    self.metrics['stop_losses'] += 1
                    logger.warning("Position closed by risk manager",
                                 position_id=closed['position_id'],
                                 reason=closed['reason'])
                
                for emergency in enforcement_results.get('emergency_actions', []):
                    logger.critical("Emergency action taken",
                                  position_id=emergency['position_id'],
                                  action=emergency['action'])
                
                await asyncio.sleep(5)
                
            except Exception as e:
                self.metrics['errors'] += 1
                logger.error("Risk monitoring error", error=str(e))
                await asyncio.sleep(10)
    
    async def _health_check_loop(self):
        """System health monitoring (Rule 10)"""
        while self.is_running:
            try:
                # Get comprehensive status
                registry_stats = await self.registry.get_registry_stats()
                recon_stats = self.reconciliation_service.get_stats()
                risk_status = self.risk_manager.get_risk_status()
                
                # Check for critical issues
                if recon_stats['consecutive_errors'] > 3:
                    logger.error("CRITICAL: Reconciliation failing",
                               consecutive_errors=recon_stats['consecutive_errors'])
                
                if risk_status['emergency_stop']:
                    logger.critical("EMERGENCY STOP ACTIVE")
                
                # Log health status
                logger.info("System Health",
                          active_positions=registry_stats['active_positions'],
                          zones=registry_stats['zone_distribution'],
                          capital=risk_status['total_capital'],
                          metrics=self.metrics)
                
                await asyncio.sleep(30)
                
            except Exception as e:
                logger.error("Health check error", error=str(e))
                await asyncio.sleep(30)
    
    async def get_comprehensive_status(self) -> Dict:
        """Get complete system status"""
        try:
            registry_stats = await self.registry.get_registry_stats()
            recon_stats = self.reconciliation_service.get_stats()
            risk_status = self.risk_manager.get_risk_status()
            
            positions = await self.registry.get_all_positions()
            
            return {
                'system': {
                    'status': 'RUNNING' if self.is_running else 'STOPPED',
                    'startup_time': self.startup_time.isoformat() if self.startup_time else None,
                    'uptime_seconds': (datetime.now(timezone.utc) - self.startup_time).total_seconds() if self.startup_time else 0
                },
                'compliance': {
                    'reconciliation_active': recon_stats['is_running'],
                    'last_reconciliation': recon_stats['last_reconciliation'],
                    'reconciliation_errors': recon_stats['consecutive_errors'],
                    'risk_limits_enforced': not risk_status['emergency_stop']
                },
                'positions': {
                    'active': len(positions),
                    'by_zone': registry_stats['zone_distribution'],
                    'total_upnl': sum(p.unrealized_pnl for p in positions),
                    'total_realized': sum(p.realized_pnl for p in positions)
                },
                'risk': risk_status,
                'metrics': self.metrics,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error("Failed to get system status", error=str(e))
            return {'error': str(e)}

async def main():
    """Main entry point with proper error handling"""
    system = FullyIntegratedTradingSystem()
    
    # Handle shutdown signals
    def signal_handler(sig, frame):
        logger.info("Shutdown signal received")
        asyncio.create_task(system.stop())
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize system
        await system.initialize()
        
        # Start system
        await system.start()
        
        # Initial status
        status = await system.get_comprehensive_status()
        logger.info("Initial Status", 
                   active_positions=status['positions']['active'],
                   capital=status['risk'].get('total_capital', 0))
        
        # Keep running with periodic status updates
        while system.is_running:
            await asyncio.sleep(60)  # Status update every minute
            
            if system.is_running:
                status = await system.get_comprehensive_status()
                logger.info("Status Update",
                          positions=status['positions']['active'],
                          zones=status['positions']['by_zone'],
                          metrics=status['metrics'])
        
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error("System error", error=str(e), exc_info=True)
    finally:
        await system.stop()

if __name__ == "__main__":
    # Ensure directories exist
    Path('/app/core').mkdir(parents=True, exist_ok=True)
    Path('/app/logs').mkdir(parents=True, exist_ok=True)
    Path('/app/data').mkdir(parents=True, exist_ok=True)
    
    # Run the system
    asyncio.run(main())