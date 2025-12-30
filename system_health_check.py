#!/usr/bin/env python3
"""
System Health Check for AI-XYZ
Performs comprehensive health checks and sends alerts if issues detected
"""
import json
import os
import psutil
import logging
from datetime import datetime, timedelta
import requests
from typing import Dict, List, Any

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class SystemHealthCheck:
    def __init__(self):
        self.health_status = {
            'timestamp': datetime.now().isoformat(),
            'overall_health': 'HEALTHY',
            'score': 100,
            'services': {},
            'resources': {},
            'positions': {},
            'alerts': []
        }

        self.critical_services = [
            'autonomous_sync',
            'momentum_guardian',
            'surplus_dump_manager'
        ]

        self.thresholds = {
            'cpu_percent': 80,
            'memory_percent': 80,
            'disk_percent': 90,
            'position_loss_percent': 50,
            'service_restart_count': 5
        }

    def check_service_status(self):
        """Check if critical services are running"""
        for service in self.critical_services:
            is_running = False
            pid = None
            cpu_usage = 0
            memory_usage = 0

            for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    cmdline = proc.info.get('cmdline')
                    if cmdline and any(service in cmd for cmd in cmdline):
                        is_running = True
                        pid = proc.info['pid']
                        process = psutil.Process(pid)
                        cpu_usage = process.cpu_percent(interval=1)
                        memory_usage = process.memory_info().rss / 1024 / 1024  # MB
                        break
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            self.health_status['services'][service] = {
                'running': is_running,
                'pid': pid,
                'cpu_usage': cpu_usage,
                'memory_mb': memory_usage
            }

            if not is_running:
                self.health_status['alerts'].append({
                    'severity': 'CRITICAL',
                    'service': service,
                    'message': f'{service} is not running'
                })
                self.health_status['score'] -= 20

    def check_system_resources(self):
        """Check system resource usage"""
        # CPU
        cpu_percent = psutil.cpu_percent(interval=1)
        self.health_status['resources']['cpu_percent'] = cpu_percent
        if cpu_percent > self.thresholds['cpu_percent']:
            self.health_status['alerts'].append({
                'severity': 'WARNING',
                'resource': 'CPU',
                'message': f'CPU usage high: {cpu_percent}%'
            })
            self.health_status['score'] -= 10

        # Memory
        memory = psutil.virtual_memory()
        self.health_status['resources']['memory_percent'] = memory.percent
        self.health_status['resources']['memory_available_gb'] = memory.available / 1024**3
        if memory.percent > self.thresholds['memory_percent']:
            self.health_status['alerts'].append({
                'severity': 'WARNING',
                'resource': 'Memory',
                'message': f'Memory usage high: {memory.percent}%'
            })
            self.health_status['score'] -= 10

        # Disk
        disk = psutil.disk_usage('/app')
        self.health_status['resources']['disk_percent'] = disk.percent
        self.health_status['resources']['disk_free_gb'] = disk.free / 1024**3
        if disk.percent > self.thresholds['disk_percent']:
            self.health_status['alerts'].append({
                'severity': 'WARNING',
                'resource': 'Disk',
                'message': f'Disk usage high: {disk.percent}%'
            })
            self.health_status['score'] -= 10

    def check_position_state(self):
        """Check position state file health"""
        try:
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)

            active_positions = state.get('active_positions', {})
            self.health_status['positions']['count'] = len(active_positions)

            # Check for positions with extreme losses
            for symbol, position in active_positions.items():
                upnl = position.get('upnl', 0)
                margin = position.get('margin', 1)
                upnl_percent = (upnl / margin * 100) if margin > 0 else 0

                if upnl_percent < -self.thresholds['position_loss_percent']:
                    self.health_status['alerts'].append({
                        'severity': 'HIGH',
                        'position': symbol,
                        'message': f'Position {symbol} has {upnl_percent:.1f}% loss'
                    })
                    self.health_status['score'] -= 15

            # Check file size
            file_size = os.path.getsize('/app/position_state.json')
            if file_size > 5 * 1024 * 1024:  # 5MB
                self.health_status['alerts'].append({
                    'severity': 'WARNING',
                    'file': 'position_state.json',
                    'message': f'File size large: {file_size/1024/1024:.1f}MB'
                })

            self.health_status['positions']['file_size_mb'] = file_size / 1024 / 1024

        except Exception as e:
            self.health_status['alerts'].append({
                'severity': 'CRITICAL',
                'file': 'position_state.json',
                'message': f'Cannot read position state: {str(e)}'
            })
            self.health_status['score'] -= 25

    def check_log_errors(self):
        """Check for recent errors in logs"""
        log_files = [
            '/app/logs/autonomous_sync.log',
            '/app/logs/momentum_guardian.log',
            '/app/logs/surplus_dump.log'
        ]

        error_count = 0
        for log_file in log_files:
            if os.path.exists(log_file):
                try:
                    # Read last 100 lines
                    with open(log_file, 'r') as f:
                        lines = f.readlines()[-100:]

                    for line in lines:
                        if 'ERROR' in line or 'CRITICAL' in line:
                            error_count += 1

                except Exception:
                    pass

        if error_count > 10:
            self.health_status['alerts'].append({
                'severity': 'WARNING',
                'logs': 'error_count',
                'message': f'Found {error_count} errors in recent logs'
            })
            self.health_status['score'] -= 5

    def check_service_restarts(self):
        """Check SystemD service restart counts"""
        import subprocess

        for service in ['ai-xyz-autonomous', 'ai-xyz-momentum', 'ai-xyz-surplus']:
            try:
                result = subprocess.run(
                    ['systemctl', 'show', service, '-p', 'NRestarts'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                if result.returncode == 0:
                    restarts = int(result.stdout.split('=')[1].strip())
                    if restarts > self.thresholds['service_restart_count']:
                        self.health_status['alerts'].append({
                            'severity': 'HIGH',
                            'service': service,
                            'message': f'{service} restarted {restarts} times'
                        })
                        self.health_status['score'] -= 10

            except Exception:
                pass  # SystemD might not be configured yet

    def determine_overall_health(self):
        """Determine overall system health status"""
        score = self.health_status['score']

        if score >= 90:
            self.health_status['overall_health'] = 'HEALTHY'
        elif score >= 70:
            self.health_status['overall_health'] = 'DEGRADED'
        elif score >= 50:
            self.health_status['overall_health'] = 'UNHEALTHY'
        else:
            self.health_status['overall_health'] = 'CRITICAL'

    def send_alerts(self):
        """Send alerts if critical issues detected"""
        critical_alerts = [a for a in self.health_status['alerts'] if a['severity'] == 'CRITICAL']

        if critical_alerts:
            # Log critical alerts
            for alert in critical_alerts:
                logging.error(f"CRITICAL ALERT: {alert['message']}")

            # Here you would implement actual alerting (Telegram, Email, etc.)
            # For now, just log to a special file
            with open('/app/critical_alerts.log', 'a') as f:
                f.write(f"{datetime.now().isoformat()} - {json.dumps(critical_alerts)}\n")

    def save_report(self):
        """Save health check report"""
        report_file = f"/app/health_reports/health_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs('/app/health_reports', exist_ok=True)

        with open(report_file, 'w') as f:
            json.dump(self.health_status, f, indent=2)

        # Also save as latest
        with open('/app/health_status_latest.json', 'w') as f:
            json.dump(self.health_status, f, indent=2)

        logging.info(f"Health report saved to {report_file}")

    def run_health_check(self):
        """Run complete health check"""
        logging.info("Starting system health check...")

        # Run all checks
        self.check_service_status()
        self.check_system_resources()
        self.check_position_state()
        self.check_log_errors()
        self.check_service_restarts()

        # Determine overall health
        self.determine_overall_health()

        # Send alerts if needed
        self.send_alerts()

        # Save report
        self.save_report()

        # Log summary
        logging.info(f"Health Check Complete: {self.health_status['overall_health']} (Score: {self.health_status['score']})")

        if self.health_status['alerts']:
            logging.warning(f"Found {len(self.health_status['alerts'])} alerts")
            for alert in self.health_status['alerts'][:5]:  # Show first 5
                logging.warning(f"  - {alert['severity']}: {alert['message']}")

        return self.health_status

if __name__ == "__main__":
    checker = SystemHealthCheck()
    status = checker.run_health_check()

    # Print summary
    print(f"\n{'='*60}")
    print(f"AI-XYZ System Health Check")
    print(f"{'='*60}")
    print(f"Timestamp: {status['timestamp']}")
    print(f"Overall Health: {status['overall_health']}")
    print(f"Health Score: {status['score']}/100")
    print(f"\nServices:")
    for service, info in status['services'].items():
        status_emoji = '✅' if info['running'] else '❌'
        print(f"  {status_emoji} {service}: {'Running' if info['running'] else 'NOT RUNNING'}")
        if info['running']:
            print(f"      PID: {info['pid']}, CPU: {info['cpu_usage']:.1f}%, Memory: {info['memory_mb']:.1f}MB")

    print(f"\nSystem Resources:")
    print(f"  CPU: {status['resources']['cpu_percent']:.1f}%")
    print(f"  Memory: {status['resources']['memory_percent']:.1f}%")
    print(f"  Disk: {status['resources']['disk_percent']:.1f}%")

    if status['alerts']:
        print(f"\n⚠️  Alerts ({len(status['alerts'])})")
        for alert in status['alerts']:
            print(f"  [{alert['severity']}] {alert['message']}")

    print(f"{'='*60}\n")