#!/usr/bin/env python3
"""
Automated Position Manager for AI-XYZ System
Provides continuous monitoring and automatic correction of all positions
including surplus dump, averaging, and zone transitions
"""

import asyncio
import ccxt.async_support as ccxt
import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
import structlog
from dotenv import load_dotenv

# Import core components
from core.live_positions_registry import LivePositionsRegistry, Position, PositionZone
from core.zone_state_machine import ZoneStateMachine
from core.surplus_dump_manager import SurplusDumpManager
# Skip missing imports for now - will implement inline

load_dotenv('/app/.env')
logger = structlog.get_logger(__name__)

class AutomatedPositionManager:
    """
    Automated system for managing all position lifecycle events
    """
    
    def __init__(self):
        # Initialize exchange
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        
        # Initialize core components
        self.registry = LivePositionsRegistry()
        self.zone_machine = ZoneStateMachine(self.registry)
        self.surplus_manager = SurplusDumpManager(self.registry, self.exchange)
        # Averaging and risk managers will be implemented inline
        self.averaging_manager = None  # Will implement inline
        self.risk_manager = None  # Will implement inline
        
        # Monitoring intervals (seconds)
        self.position_sync_interval = 10  # Sync with exchange every 10s
        self.zone_check_interval = 5      # Check zones every 5s
        self.surplus_check_interval = 3   # Check surplus dump every 3s
        self.compliance_check_interval = 30  # Full compliance check every 30s
        
        # Automated fix flags
        self.auto_fix_zones = True
        self.auto_execute_surplus = True
        self.auto_execute_averaging = True
        self.auto_close_stop_loss = True
        
        # Alert thresholds
        self.alert_on_zone_mismatch = True
        self.alert_on_surplus_eligible = True
        self.alert_on_compliance_failure = True
        
        self.running = False
        self.tasks = []
        
    async def start(self):
        """Start all automated monitoring and management tasks"""
        if self.running:
            logger.warning("Automated manager already running")
            return
            
        self.running = True
        logger.info("Starting Automated Position Manager")
        
        # Initialize Redis connection for the registry
        await self.registry.initialize()
        logger.info("Redis connection initialized")
        
        # Load markets
        await self.exchange.load_markets()
        
        # Start monitoring tasks
        self.tasks = [
            asyncio.create_task(self.position_sync_loop()),
            asyncio.create_task(self.zone_transition_loop()),
            asyncio.create_task(self.surplus_dump_loop()),
            asyncio.create_task(self.averaging_loop()),
            asyncio.create_task(self.compliance_loop()),
            asyncio.create_task(self.alert_loop())
        ]
        
        # Wait for all tasks
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
    async def stop(self):
        """Stop all automated tasks"""
        self.running = False
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("Automated Position Manager stopped")
        
    async def position_sync_loop(self):
        """Continuously sync positions with exchange"""
        while self.running:
            try:
                # Fetch positions from exchange
                exchange_positions = await self.exchange.fetch_positions()
                
                # Sync with registry
                # First get all existing positions from registry
                all_positions = await self.registry.get_all_positions()
                registry_positions = {p.symbol: p for p in all_positions}
                
                # Update or create positions from exchange
                for pos in exchange_positions:
                    # CRITICAL FIX: Only process positions with actual contracts
                    # Skip positions with 0 contracts (closed positions that still appear in API)
                    contracts = pos.get('contracts', 0)
                    contract_size = pos.get('contractSize', 0)

                    if contracts <= 0 and contract_size <= 0:
                        continue  # Skip closed position slots

                    symbol = pos['symbol']

                    # Check if position exists in registry
                    if symbol in registry_positions:
                        # Update existing position
                        registry_pos = registry_positions[symbol]
                        registry_pos.current_price = pos['markPrice'] if 'markPrice' in pos else pos.get('currentPrice', 0)
                        registry_pos.unrealized_pnl = pos.get('unrealizedPnl', 0)
                        registry_pos.quantity = pos.get('contracts', pos.get('contractSize', 0))
                        
                        # Note: unrealized_pnl_pct is now a calculated property based on 
                        # unrealized_pnl, entry_price, initial_quantity, and leverage
                        
                        await self.registry.update_position(registry_pos)
                    else:
                        # Create new position in registry
                        import uuid
                        from core.live_positions_registry import Position, PositionDirection
                        
                        # Generate unique position ID
                        position_id = f"pos_{symbol.replace('/', '_').replace(':', '_')}_{uuid.uuid4().hex[:8]}"
                        
                        # Determine direction
                        side = pos.get('side', 'long')
                        direction = PositionDirection.LONG if side == 'long' else PositionDirection.SHORT
                        
                        # Create new position
                        new_position = Position(
                            position_id=position_id,
                            symbol=symbol,
                            direction=direction,
                            entry_price=pos.get('entryPrice', pos.get('avgPrice', 0)),
                            quantity=pos.get('contracts', pos.get('contractSize', 0)),
                            initial_quantity=pos.get('contracts', pos.get('contractSize', 0)),
                            weighted_avg_price=pos.get('entryPrice', pos.get('avgPrice', 0)),
                            current_price=pos.get('markPrice', pos.get('currentPrice', 0)),
                            unrealized_pnl=pos.get('unrealizedPnl', 0),
                            leverage=pos.get('leverage', 1),
                            exchange_order_ids=[pos.get('id', '')]
                        )
                        
                        # Add to registry
                        await self.registry.add_position(new_position)
                        logger.info(f"New position added to registry: {symbol} (ID: {position_id})")
                    
                logger.info(f"Synced {len(exchange_positions)} positions with exchange")
                
            except Exception as e:
                logger.error(f"Position sync error: {e}")
                
            await asyncio.sleep(self.position_sync_interval)
            
    async def zone_transition_loop(self):
        """Monitor and fix zone transitions"""
        while self.running:
            try:
                positions = await self.registry.get_all_positions()
                
                for position in positions:
                    # Evaluate correct zone
                    result = await self.zone_machine.evaluate_and_transition(position)
                    
                    if not result.success and self.auto_fix_zones:
                        # Attempt to fix zone transition
                        await self.fix_zone_transition(position)
                        
                    # Special check for surplus dump eligibility
                    if self.should_be_surplus_dump(position) and position.current_zone != PositionZone.SURPLUS_DUMP:
                        logger.warning(f"Position {position.symbol} should be in SURPLUS_DUMP but is in {position.current_zone.value}")
                        
                        if self.auto_fix_zones:
                            # Force transition to surplus dump
                            position.current_zone = PositionZone.SURPLUS_DUMP
                            await self.registry.update_position(position)
                            logger.info(f"Force-transitioned {position.symbol} to SURPLUS_DUMP zone")
                            
            except Exception as e:
                logger.error(f"Zone transition error: {e}")
                
            await asyncio.sleep(self.zone_check_interval)
            
    async def surplus_dump_loop(self):
        """Monitor and execute surplus dumps"""
        while self.running:
            try:
                positions = await self.registry.get_all_positions()
                
                for position in positions:
                    # Check if position eligible for surplus dump
                    if position.current_zone == PositionZone.SURPLUS_DUMP or self.should_be_surplus_dump(position):
                        
                        # Force zone if needed
                        if position.current_zone != PositionZone.SURPLUS_DUMP:
                            position.current_zone = PositionZone.SURPLUS_DUMP
                            await self.registry.update_position(position)
                        
                        # Evaluate surplus dump
                        dump_action = await self.surplus_manager.evaluate_surplus_dump(position)
                        
                        if dump_action and self.auto_execute_surplus:
                            success = await self.surplus_manager.execute_surplus_dump(position, dump_action)
                            
                            if success:
                                logger.info(f"Executed surplus dump for {position.symbol}: {dump_action}")
                                
                                # Send alert
                                await self.send_alert(
                                    "SURPLUS_DUMP_EXECUTED",
                                    f"Surplus dump executed for {position.symbol}\n"
                                    f"Dumped {dump_action['dump_size']} units\n"
                                    f"Reason: {dump_action['reason']}"
                                )
                            else:
                                logger.error(f"Failed to execute surplus dump for {position.symbol}")
                                
            except Exception as e:
                logger.error(f"Surplus dump loop error: {e}")
                
            await asyncio.sleep(self.surplus_check_interval)
            
    async def averaging_loop(self):
        """Monitor and execute averaging operations"""
        while self.running:
            try:
                # Skip averaging for now - focus on surplus dump
                await asyncio.sleep(self.zone_check_interval)
                
            except Exception as e:
                logger.error(f"Averaging loop error: {e}")
                
            await asyncio.sleep(self.zone_check_interval)
            
    async def compliance_loop(self):
        """Check compliance with cardinal rules"""
        while self.running:
            try:
                compliance_report = await self.check_full_compliance()
                
                if compliance_report['violations']:
                    logger.warning(f"Compliance violations detected: {compliance_report['violations']}")
                    
                    if self.alert_on_compliance_failure:
                        await self.send_alert(
                            "COMPLIANCE_VIOLATION",
                            f"Violations: {json.dumps(compliance_report['violations'], indent=2)}"
                        )
                    
                    # Attempt auto-fix
                    if compliance_report['auto_fixable']:
                        await self.auto_fix_compliance(compliance_report)
                        
            except Exception as e:
                logger.error(f"Compliance check error: {e}")
                
            await asyncio.sleep(self.compliance_check_interval)
            
    async def alert_loop(self):
        """Monitor for alert conditions"""
        while self.running:
            try:
                positions = await self.registry.get_all_positions()
                
                for position in positions:
                    # Check for critical conditions
                    if position.unrealized_pnl_pct < -80:
                        await self.send_alert(
                            "CRITICAL_LOSS",
                            f"{position.symbol} approaching liquidation: {position.unrealized_pnl_pct:.1f}%"
                        )
                    
                    # Check for surplus dump opportunities
                    if self.should_be_surplus_dump(position) and self.alert_on_surplus_eligible:
                        await self.send_alert(
                            "SURPLUS_ELIGIBLE",
                            f"{position.symbol} eligible for surplus dump\n"
                            f"PNL: {position.unrealized_pnl:.2f} ({position.unrealized_pnl_pct:.1f}%)\n"
                            f"Averaging steps: {position.averaging_steps_taken}"
                        )
                        
            except Exception as e:
                logger.error(f"Alert loop error: {e}")
                
            await asyncio.sleep(10)  # Check alerts every 10s
            
    def should_be_surplus_dump(self, position: Position) -> bool:
        """Check if position should be in surplus dump zone"""
        # Cardinal Rule: UPNL > 0.15% AND averaging_steps > 0
        return (
            position.unrealized_pnl > position.threshold_positive and
            position.averaging_steps_taken > 0
        )
        
    async def fix_zone_transition(self, position: Position):
        """Attempt to fix zone transition issues"""
        try:
            correct_zone = self.calculate_correct_zone(position)
            
            if correct_zone != position.current_zone:
                logger.info(f"Fixing zone for {position.symbol}: {position.current_zone.value} -> {correct_zone.value}")
                position.current_zone = correct_zone
                await self.registry.update_position(position)
                
        except Exception as e:
            logger.error(f"Failed to fix zone transition: {e}")
            
    def calculate_correct_zone(self, position: Position) -> PositionZone:
        """Calculate the correct zone for a position"""
        upnl = position.unrealized_pnl
        
        # Stop loss check (terminal state)
        if position.current_zone == PositionZone.STOP_LOSS:
            return PositionZone.STOP_LOSS
            
        # Stop loss conditions
        if upnl <= position.stop_loss_threshold and position.averaging_steps_taken >= 5:
            return PositionZone.STOP_LOSS
            
        # Surplus dump check (highest priority after stop loss)
        if upnl > position.threshold_positive and position.averaging_steps_taken > 0:
            return PositionZone.SURPLUS_DUMP
            
        # Profit taking (no averaging)
        if upnl > position.threshold_positive and position.averaging_steps_taken == 0:
            return PositionZone.PROFIT_TAKING
            
        # Averaging zone
        if upnl < position.threshold_negative:
            return PositionZone.AVERAGING
            
        # Default to neutral
        return PositionZone.NEUTRAL
        
    async def check_full_compliance(self) -> Dict:
        """Check compliance with all cardinal rules"""
        violations = []
        auto_fixable = []
        
        positions = await self.registry.get_all_positions()
        
        for position in positions:
            # Rule 2: Atomic zone transitions
            correct_zone = self.calculate_correct_zone(position)
            if correct_zone != position.current_zone:
                violations.append({
                    'rule': 2,
                    'position': position.symbol,
                    'issue': f'Wrong zone: {position.current_zone.value} should be {correct_zone.value}',
                    'fixable': True
                })
                auto_fixable.append(('zone', position.position_id, correct_zone))
                
            # Rule 5: Surplus dump at thresholds
            if position.current_zone == PositionZone.SURPLUS_DUMP:
                if position.peak_upnl > 0:
                    current_pct = (position.unrealized_pnl / position.peak_upnl) * 100
                    if current_pct <= 70 and position.surplus_dump_stage == 0:
                        violations.append({
                            'rule': 5,
                            'position': position.symbol,
                            'issue': f'Surplus dump not executed at 70% of peak',
                            'fixable': True
                        })
                        auto_fixable.append(('surplus', position.position_id, None))
                        
            # Rule 4: Fibonacci averaging thresholds
            if position.current_zone == PositionZone.AVERAGING:
                if position.metadata and 'averaging_steps' in position.metadata:
                    steps = position.metadata['averaging_steps']
                    if position.averaging_steps_taken < len(steps):
                        next_step = steps[position.averaging_steps_taken]
                        threshold = next_step['delta_threshold']
                        if position.unrealized_pnl_pct <= threshold:
                            violations.append({
                                'rule': 4,
                                'position': position.symbol,
                                'issue': f'Averaging not executed at threshold {threshold}%',
                                'fixable': True
                            })
                            auto_fixable.append(('averaging', position.position_id, None))
                            
        return {
            'violations': violations,
            'auto_fixable': len(auto_fixable) > 0,
            'fixes': auto_fixable
        }
        
    async def auto_fix_compliance(self, report: Dict):
        """Automatically fix compliance violations"""
        for fix_type, position_id, data in report['fixes']:
            try:
                if fix_type == 'zone':
                    position = await self.registry.get_position(position_id)
                    position.current_zone = data
                    await self.registry.update_position(position)
                    logger.info(f"Fixed zone for position {position_id}")
                    
                elif fix_type == 'surplus':
                    position = await self.registry.get_position(position_id)
                    dump_action = await self.surplus_manager.evaluate_surplus_dump(position)
                    if dump_action:
                        await self.surplus_manager.execute_surplus_dump(position, dump_action)
                        logger.info(f"Executed surplus dump for position {position_id}")
                        
                elif fix_type == 'averaging':
                    # Skip averaging fixes for now
                    logger.info(f"Averaging fix skipped for position {position_id} (manager not available)")
                        
            except Exception as e:
                logger.error(f"Failed to auto-fix {fix_type} for {position_id}: {e}")
                
    async def send_alert(self, alert_type: str, message: str):
        """Send alert to monitoring system"""
        alert = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'type': alert_type,
            'message': message
        }
        
        # Log alert
        logger.warning(f"ALERT: {alert_type} - {message}")
        
        # Save to alert file
        alert_file = '/app/logs/alerts.json'
        try:
            if os.path.exists(alert_file):
                with open(alert_file, 'r') as f:
                    alerts = json.load(f)
            else:
                alerts = []
                
            alerts.append(alert)
            
            # Keep last 1000 alerts
            if len(alerts) > 1000:
                alerts = alerts[-1000:]
                
            os.makedirs(os.path.dirname(alert_file), exist_ok=True)
            with open(alert_file, 'w') as f:
                json.dump(alerts, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save alert: {e}")
            
    async def get_status(self) -> Dict:
        """Get current status of automated manager"""
        positions = await self.registry.get_all_positions()
        
        status = {
            'running': self.running,
            'positions_monitored': len(positions),
            'auto_fix_zones': self.auto_fix_zones,
            'auto_execute_surplus': self.auto_execute_surplus,
            'auto_execute_averaging': self.auto_execute_averaging,
            'positions': []
        }
        
        for position in positions:
            pos_status = {
                'symbol': position.symbol,
                'zone': position.current_zone.value,
                'upnl': position.unrealized_pnl,
                'upnl_pct': position.unrealized_pnl_pct,
                'averaging_steps': position.averaging_steps_taken,
                'surplus_eligible': self.should_be_surplus_dump(position),
                'correct_zone': self.calculate_correct_zone(position).value
            }
            status['positions'].append(pos_status)
            
        return status


async def main():
    """Run automated position manager"""
    manager = AutomatedPositionManager()
    
    try:
        # Start manager
        await manager.start()
        
    except KeyboardInterrupt:
        logger.info("Shutting down automated manager...")
        await manager.stop()
        

if __name__ == "__main__":
    asyncio.run(main())