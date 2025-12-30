"""
Monitoring Service - The Vital Signs
Comprehensive system monitoring and health tracking.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
import asyncio
import psutil
import time
import httpx
import structlog

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="Monitoring Service - The Vital Signs",
    description="Comprehensive system monitoring and health tracking",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SystemMetrics(BaseModel):
    timestamp: datetime
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    network_io: Dict[str, int]
    active_connections: int

class ServiceHealth(BaseModel):
    service_name: str
    status: str
    response_time: float
    last_check: datetime
    error_count: int

class AlertRule(BaseModel):
    rule_id: str
    metric: str
    threshold: float
    operator: str  # >, <, >=, <=, ==
    severity: str  # critical, warning, info
    enabled: bool

class MonitoringService:
    """Comprehensive monitoring service."""
    
    def __init__(self):
        self.metrics_history = []
        self.service_health = {}
        self.alert_rules = {}
        self.alerts = []
        self.services = {
            'market-scanner': 'http://localhost:8001',
            'ai-decision-engine': 'http://localhost:8002',
            'position-management': 'http://localhost:8003',
            'backtesting-engine': 'http://localhost:8004',
            'ml-framework': 'http://localhost:8005',
            'notification-service': 'http://localhost:8007',
            'data-pipeline': 'http://localhost:8008',
            'risk-engine': 'http://localhost:8009'
        }
        
        # Initialize default alert rules
        self.setup_default_alert_rules()
    
    def setup_default_alert_rules(self):
        """Setup default monitoring alert rules."""
        default_rules = [
            {
                'rule_id': 'high_cpu_usage',
                'metric': 'cpu_usage',
                'threshold': 80.0,
                'operator': '>',
                'severity': 'warning',
                'enabled': True
            },
            {
                'rule_id': 'high_memory_usage',
                'metric': 'memory_usage',
                'threshold': 85.0,
                'operator': '>',
                'severity': 'warning',
                'enabled': True
            },
            {
                'rule_id': 'critical_cpu_usage',
                'metric': 'cpu_usage',
                'threshold': 95.0,
                'operator': '>',
                'severity': 'critical',
                'enabled': True
            },
            {
                'rule_id': 'service_down',
                'metric': 'service_status',
                'threshold': 0,
                'operator': '==',
                'severity': 'critical',
                'enabled': True
            }
        ]
        
        for rule in default_rules:
            self.alert_rules[rule['rule_id']] = AlertRule(**rule)
    
    async def collect_system_metrics(self) -> SystemMetrics:
        """Collect current system metrics."""
        # CPU usage
        cpu_usage = psutil.cpu_percent(interval=1)
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_usage = memory.percent
        
        # Disk usage
        disk = psutil.disk_usage('/')
        disk_usage = (disk.used / disk.total) * 100
        
        # Network I/O
        network = psutil.net_io_counters()
        network_io = {
            'bytes_sent': network.bytes_sent,
            'bytes_recv': network.bytes_recv,
            'packets_sent': network.packets_sent,
            'packets_recv': network.packets_recv
        }
        
        # Active connections
        connections = len(psutil.net_connections())
        
        metrics = SystemMetrics(
            timestamp=datetime.now(),
            cpu_usage=cpu_usage,
            memory_usage=memory_usage,
            disk_usage=disk_usage,
            network_io=network_io,
            active_connections=connections
        )
        
        # Store in history
        self.metrics_history.append(metrics)
        
        # Keep only last 1000 entries
        if len(self.metrics_history) > 1000:
            self.metrics_history = self.metrics_history[-1000:]
        
        # Check alert rules
        await self.check_alert_rules(metrics)
        
        return metrics
    
    async def check_service_health(self) -> Dict[str, ServiceHealth]:
        """Check health of all services."""
        health_results = {}
        
        for service_name, service_url in self.services.items():
            try:
                start_time = time.time()
                
                async with httpx.AsyncClient(timeout=5.0) as client:
                    response = await client.get(f"{service_url}/health")
                
                response_time = (time.time() - start_time) * 1000  # ms
                
                if response.status_code == 200:
                    status = "healthy"
                    error_count = 0
                else:
                    status = "unhealthy"
                    error_count = 1
                
            except Exception as e:
                logger.error(f"Health check failed for {service_name}: {str(e)}")
                status = "unreachable"
                response_time = 0
                error_count = 1
            
            health = ServiceHealth(
                service_name=service_name,
                status=status,
                response_time=response_time,
                last_check=datetime.now(),
                error_count=error_count
            )
            
            health_results[service_name] = health
            self.service_health[service_name] = health
        
        return health_results
    
    async def check_alert_rules(self, metrics: SystemMetrics):
        """Check metrics against alert rules."""
        for rule_id, rule in self.alert_rules.items():
            if not rule.enabled:
                continue
            
            metric_value = getattr(metrics, rule.metric, None)
            if metric_value is None:
                continue
            
            triggered = False
            
            if rule.operator == '>':
                triggered = metric_value > rule.threshold
            elif rule.operator == '<':
                triggered = metric_value < rule.threshold
            elif rule.operator == '>=':
                triggered = metric_value >= rule.threshold
            elif rule.operator == '<=':
                triggered = metric_value <= rule.threshold
            elif rule.operator == '==':
                triggered = metric_value == rule.threshold
            
            if triggered:
                alert = {
                    'alert_id': f"{rule_id}_{int(time.time())}",
                    'rule_id': rule_id,
                    'metric': rule.metric,
                    'value': metric_value,
                    'threshold': rule.threshold,
                    'severity': rule.severity,
                    'message': f"{rule.metric} is {metric_value} (threshold: {rule.threshold})",
                    'timestamp': datetime.now().isoformat()
                }
                
                self.alerts.append(alert)
                logger.warning(f"Alert triggered: {alert['message']}")
                
                # Keep only last 100 alerts
                if len(self.alerts) > 100:
                    self.alerts = self.alerts[-100:]
    
    async def get_system_overview(self) -> Dict:
        """Get comprehensive system overview."""
        # Get latest metrics
        latest_metrics = await self.collect_system_metrics()
        
        # Get service health
        service_health = await self.check_service_health()
        
        # Calculate uptime
        uptime_seconds = time.time() - psutil.boot_time()
        uptime = str(timedelta(seconds=int(uptime_seconds)))
        
        # Count healthy services
        healthy_services = sum(1 for health in service_health.values() if health.status == "healthy")
        total_services = len(service_health)
        
        # Recent alerts
        recent_alerts = [alert for alert in self.alerts if 
                        datetime.fromisoformat(alert['timestamp']) > datetime.now() - timedelta(hours=1)]
        
        return {
            'system_metrics': latest_metrics,
            'service_health': service_health,
            'system_info': {
                'uptime': uptime,
                'healthy_services': f"{healthy_services}/{total_services}",
                'recent_alerts': len(recent_alerts),
                'total_alerts': len(self.alerts)
            },
            'timestamp': datetime.now().isoformat()
        }
    
    async def get_metrics_history(self, hours: int = 24) -> List[SystemMetrics]:
        """Get metrics history for specified hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [m for m in self.metrics_history if m.timestamp > cutoff_time]
    
    def add_alert_rule(self, rule: AlertRule):
        """Add new alert rule."""
        self.alert_rules[rule.rule_id] = rule
    
    def update_alert_rule(self, rule_id: str, updates: Dict):
        """Update existing alert rule."""
        if rule_id in self.alert_rules:
            rule = self.alert_rules[rule_id]
            for key, value in updates.items():
                if hasattr(rule, key):
                    setattr(rule, key, value)
    
    def delete_alert_rule(self, rule_id: str):
        """Delete alert rule."""
        if rule_id in self.alert_rules:
            del self.alert_rules[rule_id]

# Initialize monitoring service
monitoring_service = MonitoringService()

# Background task to collect metrics
async def metrics_collection_task():
    """Background task to collect metrics periodically."""
    while True:
        try:
            await monitoring_service.collect_system_metrics()
            await monitoring_service.check_service_health()
            await asyncio.sleep(30)  # Collect every 30 seconds
        except Exception as e:
            logger.error(f"Metrics collection error: {str(e)}")
            await asyncio.sleep(60)

@app.on_event("startup")
async def startup_event():
    """Start background tasks."""
    asyncio.create_task(metrics_collection_task())

@app.get("/")
async def root():
    return {
        "service": "monitoring-service",
        "status": "operational",
        "timestamp": datetime.now().isoformat(),
        "monitored_services": len(monitoring_service.services)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "monitoring-service",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/system/overview")
async def get_system_overview():
    """Get comprehensive system overview."""
    try:
        overview = await monitoring_service.get_system_overview()
        return overview
    except Exception as e:
        logger.error(f"Error getting system overview: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting system overview: {str(e)}")

@app.get("/metrics/current")
async def get_current_metrics():
    """Get current system metrics."""
    try:
        metrics = await monitoring_service.collect_system_metrics()
        return metrics
    except Exception as e:
        logger.error(f"Error getting current metrics: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting current metrics: {str(e)}")

@app.get("/metrics/history")
async def get_metrics_history(hours: int = 24):
    """Get metrics history."""
    try:
        history = await monitoring_service.get_metrics_history(hours)
        return {
            "metrics": history,
            "count": len(history),
            "hours": hours,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting metrics history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error getting metrics history: {str(e)}")

@app.get("/services/health")
async def get_services_health():
    """Get health status of all services."""
    try:
        health = await monitoring_service.check_service_health()
        return health
    except Exception as e:
        logger.error(f"Error checking services health: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error checking services health: {str(e)}")

@app.get("/alerts")
async def get_alerts():
    """Get all alerts."""
    return {
        "alerts": monitoring_service.alerts,
        "count": len(monitoring_service.alerts),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/alerts/rules")
async def get_alert_rules():
    """Get all alert rules."""
    return {
        "rules": {rule_id: rule.dict() for rule_id, rule in monitoring_service.alert_rules.items()},
        "count": len(monitoring_service.alert_rules),
        "timestamp": datetime.now().isoformat()
    }

@app.post("/alerts/rules")
async def create_alert_rule(rule: AlertRule):
    """Create new alert rule."""
    try:
        monitoring_service.add_alert_rule(rule)
        return {"message": "Alert rule created successfully", "rule_id": rule.rule_id}
    except Exception as e:
        logger.error(f"Error creating alert rule: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error creating alert rule: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
