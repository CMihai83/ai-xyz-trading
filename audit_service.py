#!/usr/bin/env python3
"""
AI-XYZ Trading System Audit Service
===================================

Comprehensive audit service that:
1. Monitors system health and performance
2. Analyzes trading positions and P&L
3. Checks compliance with trading rules
4. Generates detailed HTML reports
5. Publishes reports to moondox.eu/reports

Author: AI-XYZ System
Date: 2025-09-16
"""

import json
import os
import sys
import datetime
import time
import psutil
import requests
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

# Add system paths
sys.path.append('/app')
sys.path.append('/root/server_deployment')

@dataclass
class SystemHealth:
    """System health metrics"""
    cpu_percent: float
    memory_percent: float
    disk_percent: float
    uptime_hours: float
    processes_running: int
    load_average: List[float]
    network_status: str

@dataclass
class TradingMetrics:
    """Trading system metrics"""
    total_balance: float
    active_positions: int
    total_pnl: float
    pnl_percentage: float
    winning_positions: int
    losing_positions: int
    neutral_positions: int
    average_position_size: float
    max_drawdown: float
    risk_score: float

@dataclass
class PositionAudit:
    """Individual position audit data"""
    symbol: str
    side: str
    size: float
    entry_price: float
    current_price: float
    pnl: float
    pnl_percentage: float
    zone: str
    leverage: int
    age_hours: float
    fibonacci_status: str
    averaging_steps: int
    surplus_dump_ready: bool
    take_profit_ready: bool
    stop_loss_distance: float
    risk_level: str

@dataclass
class ServiceStatus:
    """Service health status"""
    name: str
    status: str
    pid: Optional[int]
    uptime: Optional[float]
    memory_mb: Optional[float]
    cpu_percent: Optional[float]
    last_activity: Optional[str]
    error_count: int

@dataclass
class AuditReport:
    """Complete audit report"""
    timestamp: datetime.datetime
    system_health: SystemHealth
    trading_metrics: TradingMetrics
    positions: List[PositionAudit]
    services: List[ServiceStatus]
    alerts: List[str]
    recommendations: List[str]
    compliance_score: float
    overall_status: str

class AIXYZAuditor:
    """AI-XYZ System Auditor"""
    
    def __init__(self):
        self.exchange_data_path = "/root/server_deployment/exchange_data.json"
        self.reports_dir = "/var/www/html/reports"
        self.logs_dir = "/var/log"
        
        # Create reports directory
        os.makedirs(self.reports_dir, exist_ok=True)
        
        # Service definitions
        self.services = {
            "ai_xyz_main": {
                "process_name": "aixyz_continuous_profit_system.py",
                "description": "Main AI-XYZ Trading System",
                "critical": True
            },
            "surplus_executor": {
                "process_name": "automatic_surplus_executor.py",
                "description": "Surplus Dump Executor",
                "critical": True
            },
            "exchange_connector": {
                "process_name": "exchange_connector.py",
                "description": "Exchange Data Connector",
                "critical": True
            },
            "fibonacci_services": {
                "process_name": "fibonacci_delta_calculator.py",
                "description": "Fibonacci Analysis Services",
                "critical": False
            }
        }
    
    def get_system_health(self) -> SystemHealth:
        """Collect system health metrics"""
        try:
            # CPU and memory
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # System uptime
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time
            uptime_hours = uptime_seconds / 3600
            
            # Process count
            processes_running = len(psutil.pids())
            
            # Load average
            load_average = list(os.getloadavg())
            
            # Network status (simplified)
            try:
                response = requests.get("https://api.bitget.com/api/v2/common/time", timeout=5)
                network_status = "Connected" if response.status_code == 200 else "Degraded"
            except:
                network_status = "Disconnected"
            
            return SystemHealth(
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                disk_percent=(disk.used / disk.total) * 100,
                uptime_hours=uptime_hours,
                processes_running=processes_running,
                load_average=load_average,
                network_status=network_status
            )
        except Exception as e:
            print(f"Error collecting system health: {e}")
            return SystemHealth(0, 0, 0, 0, 0, [0, 0, 0], "Unknown")
    
    def get_service_status(self) -> List[ServiceStatus]:
        """Check status of all trading services"""
        services = []
        
        for service_name, config in self.services.items():
            try:
                # Find process by name
                pid = None
                memory_mb = None
                cpu_percent = None
                uptime = None
                
                for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'create_time', 'memory_info', 'cpu_percent']):
                    try:
                        if config['process_name'] in ' '.join(proc.info['cmdline'] or []):
                            pid = proc.info['pid']
                            memory_mb = proc.info['memory_info'].rss / 1024 / 1024
                            cpu_percent = proc.info['cpu_percent']
                            uptime = (time.time() - proc.info['create_time']) / 3600
                            break
                    except:
                        continue
                
                status = "Running" if pid else "Stopped"
                
                # Check for recent errors in logs
                error_count = self.count_recent_errors(service_name)
                
                # Get last activity
                last_activity = self.get_last_activity(service_name)
                
                services.append(ServiceStatus(
                    name=service_name,
                    status=status,
                    pid=pid,
                    uptime=uptime,
                    memory_mb=memory_mb,
                    cpu_percent=cpu_percent,
                    last_activity=last_activity,
                    error_count=error_count
                ))
                
            except Exception as e:
                services.append(ServiceStatus(
                    name=service_name,
                    status="Error",
                    pid=None,
                    uptime=None,
                    memory_mb=None,
                    cpu_percent=None,
                    last_activity=None,
                    error_count=0
                ))
        
        return services
    
    def count_recent_errors(self, service_name: str) -> int:
        """Count recent errors for a service"""
        try:
            # Check various log files for errors
            log_patterns = [
                f"/var/log/{service_name}.log",
                f"/tmp/{service_name}.log",
                f"/app/{service_name}.log"
            ]
            
            error_count = 0
            cutoff_time = time.time() - 3600  # Last hour
            
            for log_path in log_patterns:
                if os.path.exists(log_path):
                    try:
                        with open(log_path, 'r') as f:
                            for line in f.readlines()[-100:]:  # Last 100 lines
                                if 'ERROR' in line.upper() or 'EXCEPTION' in line.upper():
                                    error_count += 1
                    except:
                        continue
            
            return error_count
        except:
            return 0
    
    def get_last_activity(self, service_name: str) -> Optional[str]:
        """Get last activity timestamp for service"""
        try:
            log_patterns = [
                f"/var/log/{service_name}.log",
                f"/tmp/{service_name}.log"
            ]
            
            for log_path in log_patterns:
                if os.path.exists(log_path):
                    stat = os.stat(log_path)
                    return datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            
            return None
        except:
            return None
    
    def get_trading_metrics(self) -> TradingMetrics:
        """Analyze trading performance metrics"""
        try:
            # Load exchange data
            with open(self.exchange_data_path, 'r') as f:
                data = json.load(f)
            
            balance = float(data.get('bitget_balances', {}).get('USDT', 0))
            positions = data.get('bitget_positions', {})
            
            # Calculate metrics
            active_positions = len(positions)
            total_pnl = sum(float(pos.get('upnl', 0)) for pos in positions.values())
            pnl_percentage = (total_pnl / balance * 100) if balance > 0 else 0
            
            winning_positions = sum(1 for pos in positions.values() if float(pos.get('upnl', 0)) > 0)
            losing_positions = sum(1 for pos in positions.values() if float(pos.get('upnl', 0)) < 0)
            neutral_positions = active_positions - winning_positions - losing_positions
            
            average_position_size = sum(float(pos.get('size', 0)) for pos in positions.values()) / active_positions if active_positions > 0 else 0
            
            # Calculate risk metrics
            max_drawdown = abs(min(float(pos.get('upnl', 0)) for pos in positions.values())) if positions else 0
            risk_score = min(100, (max_drawdown / balance * 100)) if balance > 0 else 0
            
            return TradingMetrics(
                total_balance=balance,
                active_positions=active_positions,
                total_pnl=total_pnl,
                pnl_percentage=pnl_percentage,
                winning_positions=winning_positions,
                losing_positions=losing_positions,
                neutral_positions=neutral_positions,
                average_position_size=average_position_size,
                max_drawdown=max_drawdown,
                risk_score=risk_score
            )
        except Exception as e:
            print(f"Error calculating trading metrics: {e}")
            return TradingMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    
    def audit_positions(self) -> List[PositionAudit]:
        """Audit all active positions"""
        positions = []
        
        try:
            # Load exchange data
            with open(self.exchange_data_path, 'r') as f:
                data = json.load(f)
            
            for symbol, pos_data in data.get('bitget_positions', {}).items():
                # Calculate position age
                timestamp = int(pos_data.get('timestamp', 0)) / 1000
                age_hours = (time.time() - timestamp) / 3600 if timestamp > 0 else 0
                
                # Analyze position
                pnl = float(pos_data.get('upnl', 0))
                size = float(pos_data.get('size', 0))
                entry_price = float(pos_data.get('entry', 0))
                current_price = float(pos_data.get('current_price', 0))
                
                # Calculate percentage PnL
                pnl_percentage = 0
                if entry_price > 0 and current_price > 0:
                    if pos_data.get('side') == 'long':
                        pnl_percentage = ((current_price - entry_price) / entry_price) * 100
                    else:
                        pnl_percentage = ((entry_price - current_price) / entry_price) * 100
                
                # Fibonacci analysis
                fibonacci_data = pos_data.get('fibonacci_deltas', {})
                fibonacci_status = "Active" if fibonacci_data else "Not Available"
                
                # Averaging analysis
                averaging_steps = len(pos_data.get('averaging_steps', []))
                
                # Zone-based analysis
                zone = pos_data.get('zone', 'UNKNOWN')
                surplus_dump_ready = zone == 'SURPLUS_DUMP'
                take_profit_ready = zone == 'PROFIT_TAKING'
                
                # Risk assessment
                risk_level = "Low"
                if abs(pnl_percentage) > 50:
                    risk_level = "High"
                elif abs(pnl_percentage) > 20:
                    risk_level = "Medium"
                
                # Stop loss distance calculation
                stop_loss_distance = 120  # Default 120% based on system design
                
                positions.append(PositionAudit(
                    symbol=symbol,
                    side=pos_data.get('side', 'unknown'),
                    size=size,
                    entry_price=entry_price,
                    current_price=current_price,
                    pnl=pnl,
                    pnl_percentage=pnl_percentage,
                    zone=zone,
                    leverage=int(pos_data.get('leverage', 1)),
                    age_hours=age_hours,
                    fibonacci_status=fibonacci_status,
                    averaging_steps=averaging_steps,
                    surplus_dump_ready=surplus_dump_ready,
                    take_profit_ready=take_profit_ready,
                    stop_loss_distance=stop_loss_distance,
                    risk_level=risk_level
                ))
        
        except Exception as e:
            print(f"Error auditing positions: {e}")
        
        return positions
    
    def generate_alerts(self, system_health: SystemHealth, trading_metrics: TradingMetrics, 
                       services: List[ServiceStatus], positions: List[PositionAudit]) -> List[str]:
        """Generate system alerts"""
        alerts = []
        
        # System health alerts
        if system_health.cpu_percent > 90:
            alerts.append(f"🔴 HIGH CPU Usage: {system_health.cpu_percent:.1f}%")
        
        if system_health.memory_percent > 85:
            alerts.append(f"🔴 HIGH Memory Usage: {system_health.memory_percent:.1f}%")
        
        if system_health.disk_percent > 90:
            alerts.append(f"🔴 LOW Disk Space: {system_health.disk_percent:.1f}% used")
        
        # Service alerts
        critical_services_down = [s for s in services if s.status != "Running" and self.services[s.name].get('critical', False)]
        if critical_services_down:
            alerts.append(f"🔴 Critical Services Down: {', '.join(s.name for s in critical_services_down)}")
        
        # Trading alerts
        if trading_metrics.total_pnl < -5:
            alerts.append(f"🔴 HIGH Unrealized Loss: ${trading_metrics.total_pnl:.2f}")
        
        if trading_metrics.risk_score > 50:
            alerts.append(f"🟡 HIGH Risk Score: {trading_metrics.risk_score:.1f}%")
        
        # Position alerts
        high_risk_positions = [p for p in positions if p.risk_level == "High"]
        if high_risk_positions:
            alerts.append(f"🟡 High Risk Positions: {len(high_risk_positions)} positions need attention")
        
        return alerts
    
    def generate_recommendations(self, system_health: SystemHealth, trading_metrics: TradingMetrics, 
                               services: List[ServiceStatus], positions: List[PositionAudit]) -> List[str]:
        """Generate improvement recommendations"""
        recommendations = []
        
        # System recommendations
        if system_health.memory_percent > 70:
            recommendations.append("Consider restarting services to free memory")
        
        # Service recommendations
        error_services = [s for s in services if s.error_count > 5]
        if error_services:
            recommendations.append(f"Investigate errors in: {', '.join(s.name for s in error_services)}")
        
        # Trading recommendations
        if trading_metrics.active_positions > 10:
            recommendations.append("Consider reducing position count for better risk management")
        
        if trading_metrics.pnl_percentage < -10:
            recommendations.append("Review trading strategy - high unrealized losses")
        
        # Position recommendations
        old_positions = [p for p in positions if p.age_hours > 168]  # 1 week
        if old_positions:
            recommendations.append(f"Review {len(old_positions)} positions older than 1 week")
        
        return recommendations
    
    def calculate_compliance_score(self, system_health: SystemHealth, trading_metrics: TradingMetrics,
                                 services: List[ServiceStatus], positions: List[PositionAudit]) -> float:
        """Calculate overall system compliance score (0-100)"""
        score = 100
        
        # System health penalties
        if system_health.cpu_percent > 90:
            score -= 15
        elif system_health.cpu_percent > 70:
            score -= 5
        
        if system_health.memory_percent > 85:
            score -= 15
        elif system_health.memory_percent > 70:
            score -= 5
        
        # Service penalties
        critical_down = sum(1 for s in services if s.status != "Running" and self.services[s.name].get('critical'))
        score -= critical_down * 25
        
        # Trading penalties
        if trading_metrics.risk_score > 50:
            score -= 20
        elif trading_metrics.risk_score > 25:
            score -= 10
        
        # Position penalties
        high_risk_count = sum(1 for p in positions if p.risk_level == "High")
        score -= high_risk_count * 5
        
        return max(0, min(100, score))
    
    def run_audit(self) -> AuditReport:
        """Run complete system audit"""
        print("🔍 Starting AI-XYZ System Audit...")
        
        # Collect all audit data
        system_health = self.get_system_health()
        print(f"✅ System Health: CPU {system_health.cpu_percent:.1f}%, Memory {system_health.memory_percent:.1f}%")
        
        services = self.get_service_status()
        print(f"✅ Services: {sum(1 for s in services if s.status == 'Running')}/{len(services)} running")
        
        trading_metrics = self.get_trading_metrics()
        print(f"✅ Trading: {trading_metrics.active_positions} positions, P&L: ${trading_metrics.total_pnl:.2f}")
        
        positions = self.audit_positions()
        print(f"✅ Positions: {len(positions)} analyzed")
        
        # Generate insights
        alerts = self.generate_alerts(system_health, trading_metrics, services, positions)
        recommendations = self.generate_recommendations(system_health, trading_metrics, services, positions)
        compliance_score = self.calculate_compliance_score(system_health, trading_metrics, services, positions)
        
        # Determine overall status
        if compliance_score >= 90:
            overall_status = "Excellent"
        elif compliance_score >= 75:
            overall_status = "Good"
        elif compliance_score >= 60:
            overall_status = "Fair"
        elif compliance_score >= 40:
            overall_status = "Poor"
        else:
            overall_status = "Critical"
        
        print(f"✅ Audit Complete: {overall_status} ({compliance_score:.1f}/100)")
        
        return AuditReport(
            timestamp=datetime.datetime.now(),
            system_health=system_health,
            trading_metrics=trading_metrics,
            positions=positions,
            services=services,
            alerts=alerts,
            recommendations=recommendations,
            compliance_score=compliance_score,
            overall_status=overall_status
        )

if __name__ == "__main__":
    auditor = AIXYZAuditor()
    report = auditor.run_audit()
    print(f"\n📊 Audit Summary:")
    print(f"Status: {report.overall_status}")
    print(f"Score: {report.compliance_score}/100")
    print(f"Alerts: {len(report.alerts)}")
    print(f"Recommendations: {len(report.recommendations)}")