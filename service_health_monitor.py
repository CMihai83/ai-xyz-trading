#!/usr/bin/env python3
"""
Service Health Monitor for AI-XYZ
Ensures all critical services are running and restarts them if needed
"""
import os
import psutil
import subprocess
import time
import json
from datetime import datetime
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/logs/service_monitor.log'),
        logging.StreamHandler()
    ]
)

class ServiceHealthMonitor:
    def __init__(self):
        self.critical_services = [
            {
                'name': 'autonomous_sync',
                'script': 'autonomous_sync.py',
                'log_file': '/app/logs/autonomous_sync.log',
                'required': True
            },
            {
                'name': 'momentum_guardian',
                'script': 'momentum_guardian.py',
                'log_file': '/app/logs/momentum_guardian.log',
                'required': True
            },
            {
                'name': 'surplus_dump_manager',
                'script': 'surplus_dump_manager.py',
                'log_file': '/app/logs/surplus_dump.log',
                'required': False
            }
        ]

        self.check_interval = 30  # seconds
        self.restart_attempts = {}
        self.max_restart_attempts = 3

    def is_service_running(self, service_name):
        """Check if a service is running"""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline')
                if cmdline and any(service_name in cmd for cmd in cmdline):
                    return proc.info['pid']
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return None

    def start_service(self, service):
        """Start a service"""
        try:
            # Change to ai_xyz directory
            os.chdir('/app')

            # Start the service
            cmd = f"python3 {service['script']} > {service['log_file']} 2>&1 &"
            subprocess.Popen(cmd, shell=True)

            time.sleep(2)  # Wait for service to start

            # Verify it started
            pid = self.is_service_running(service['name'])
            if pid:
                logging.info(f"✅ Started {service['name']} with PID {pid}")
                return True
            else:
                logging.error(f"❌ Failed to start {service['name']}")
                return False

        except Exception as e:
            logging.error(f"Error starting {service['name']}: {e}")
            return False

    def check_service_health(self, service):
        """Check if a service is healthy"""
        pid = self.is_service_running(service['name'])

        if not pid:
            return False

        try:
            # Check if process is responsive
            process = psutil.Process(pid)
            if process.status() == psutil.STATUS_ZOMBIE:
                logging.warning(f"⚠️ {service['name']} is a zombie process")
                return False

            # Check CPU usage (if stuck in infinite loop)
            cpu_percent = process.cpu_percent(interval=1)
            if cpu_percent > 90:
                logging.warning(f"⚠️ {service['name']} using {cpu_percent}% CPU")

            # Check memory usage
            memory_info = process.memory_info()
            memory_mb = memory_info.rss / 1024 / 1024
            if memory_mb > 500:  # More than 500MB
                logging.warning(f"⚠️ {service['name']} using {memory_mb:.1f}MB memory")

            return True

        except psutil.NoSuchProcess:
            return False

    def restart_service(self, service):
        """Restart a service"""
        service_name = service['name']

        # Track restart attempts
        if service_name not in self.restart_attempts:
            self.restart_attempts[service_name] = 0

        if self.restart_attempts[service_name] >= self.max_restart_attempts:
            logging.error(f"🚫 Max restart attempts reached for {service_name}")
            return False

        # Kill existing process
        pid = self.is_service_running(service_name)
        if pid:
            try:
                process = psutil.Process(pid)
                process.terminate()
                time.sleep(2)
                if process.is_running():
                    process.kill()
                logging.info(f"🔄 Killed {service_name} (PID {pid})")
            except:
                pass

        # Start service
        if self.start_service(service):
            self.restart_attempts[service_name] = 0
            return True
        else:
            self.restart_attempts[service_name] += 1
            return False

    def check_position_state(self):
        """Check if position state file is healthy"""
        try:
            with open('/app/position_state.json', 'r') as f:
                state = json.load(f)

            # Check for corrupted data
            if 'active_positions' not in state:
                logging.error("⚠️ position_state.json missing 'active_positions'")
                return False

            # Check file size (shouldn't be too large)
            file_size = os.path.getsize('/app/position_state.json')
            if file_size > 10 * 1024 * 1024:  # 10MB
                logging.warning(f"⚠️ position_state.json is {file_size/1024/1024:.1f}MB")

            return True

        except Exception as e:
            logging.error(f"Error reading position_state.json: {e}")
            return False

    def generate_status_report(self):
        """Generate a status report of all services"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'services': {},
            'health_score': 100
        }

        for service in self.critical_services:
            pid = self.is_service_running(service['name'])
            is_healthy = self.check_service_health(service) if pid else False

            report['services'][service['name']] = {
                'running': pid is not None,
                'pid': pid,
                'healthy': is_healthy,
                'required': service['required']
            }

            if service['required'] and not is_healthy:
                report['health_score'] -= 33

        # Check position state
        if not self.check_position_state():
            report['health_score'] -= 10

        return report

    def monitor_loop(self):
        """Main monitoring loop"""
        logging.info("🚀 Starting AI-XYZ Service Health Monitor")
        logging.info(f"Monitoring {len(self.critical_services)} services")
        logging.info(f"Check interval: {self.check_interval} seconds")

        while True:
            try:
                # Generate status report
                report = self.generate_status_report()

                # Log status
                logging.info(f"Health Score: {report['health_score']}%")

                for service_name, status in report['services'].items():
                    if status['running']:
                        logging.info(f"✅ {service_name} - PID {status['pid']}")
                    else:
                        logging.warning(f"❌ {service_name} - NOT RUNNING")

                # Restart failed services
                for service in self.critical_services:
                    service_status = report['services'][service['name']]

                    if service['required'] and not service_status['healthy']:
                        logging.warning(f"🔄 Restarting {service['name']}...")
                        self.restart_service(service)

                # Save report
                with open('/app/service_status.json', 'w') as f:
                    json.dump(report, f, indent=2)

                # Sleep before next check
                time.sleep(self.check_interval)

            except KeyboardInterrupt:
                logging.info("🛑 Service monitor stopped by user")
                break
            except Exception as e:
                logging.error(f"Error in monitor loop: {e}")
                time.sleep(self.check_interval)

if __name__ == "__main__":
    monitor = ServiceHealthMonitor()
    monitor.monitor_loop()