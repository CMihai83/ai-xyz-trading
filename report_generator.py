#!/usr/bin/env python3
"""
AI-XYZ Audit Report Generator
============================

Generates beautiful HTML reports for the AI-XYZ trading system audit.
Publishes reports to moondox.eu/reports for web viewing.

Author: AI-XYZ System
Date: 2025-09-16
"""

import json
import os
import datetime
from typing import Dict, List, Any
from audit_service import AuditReport, AIXYZAuditor

class ReportGenerator:
    """Generate HTML reports from audit data"""
    
    def __init__(self):
        self.reports_dir = "/var/www/html/reports"
        self.templates_dir = "/app/templates"
        
        # Ensure directories exist
        os.makedirs(self.reports_dir, exist_ok=True)
        os.makedirs(self.templates_dir, exist_ok=True)
    
    def generate_html_report(self, report: AuditReport) -> str:
        """Generate complete HTML report"""
        
        # Status color mapping
        status_colors = {
            "Excellent": "#22c55e",
            "Good": "#84cc16", 
            "Fair": "#eab308",
            "Poor": "#f97316",
            "Critical": "#ef4444"
        }
        
        # Risk level colors
        risk_colors = {
            "Low": "#22c55e",
            "Medium": "#eab308", 
            "High": "#ef4444"
        }
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI-XYZ System Audit Report - {report.timestamp.strftime('%Y-%m-%d %H:%M')}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6; color: #333; background: #f8fafc;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 2rem 0; text-align: center;
        }}
        
        .container {{ max-width: 1200px; margin: 0 auto; padding: 0 1rem; }}
        
        .status-badge {{
            display: inline-block; padding: 0.5rem 1rem; border-radius: 25px;
            font-weight: bold; color: white; margin-left: 1rem;
            background: {status_colors.get(report.overall_status, '#6b7280')};
        }}
        
        .score {{ font-size: 3rem; font-weight: bold; margin: 0.5rem 0; }}
        
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.5rem; margin: 2rem 0; }}
        
        .card {{
            background: white; border-radius: 10px; padding: 1.5rem; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            border-left: 4px solid #667eea;
        }}
        
        .card h3 {{ color: #374151; margin-bottom: 1rem; font-size: 1.25rem; }}
        
        .metric {{ display: flex; justify-content: space-between; margin: 0.5rem 0; }}
        .metric-label {{ color: #6b7280; }}
        .metric-value {{ font-weight: bold; }}
        
        .positions-table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        .positions-table th, .positions-table td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid #e5e7eb; }}
        .positions-table th {{ background: #f9fafb; font-weight: 600; }}
        
        .alert {{ background: #fef2f2; border: 1px solid #fecaca; color: #dc2626; padding: 1rem; border-radius: 5px; margin: 0.5rem 0; }}
        .recommendation {{ background: #f0f9ff; border: 1px solid #bae6fd; color: #0369a1; padding: 1rem; border-radius: 5px; margin: 0.5rem 0; }}
        
        .service-status {{ display: inline-block; padding: 0.25rem 0.5rem; border-radius: 15px; font-size: 0.875rem; font-weight: 500; }}
        .service-running {{ background: #d1fae5; color: #065f46; }}
        .service-stopped {{ background: #fee2e2; color: #dc2626; }}
        
        .chart-container {{ position: relative; height: 300px; margin: 1rem 0; }}
        
        .pnl-positive {{ color: #22c55e; font-weight: bold; }}
        .pnl-negative {{ color: #ef4444; font-weight: bold; }}
        
        .zone-neutral {{ background: #f3f4f6; color: #374151; }}
        .zone-profit {{ background: #d1fae5; color: #065f46; }}
        .zone-loss {{ background: #fee2e2; color: #dc2626; }}
        
        @media (max-width: 768px) {{
            .grid {{ grid-template-columns: 1fr; }}
            .positions-table {{ font-size: 0.875rem; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1>AI-XYZ Trading System Audit Report</h1>
            <p>{report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <div class="score">{report.compliance_score:.1f}/100</div>
            <span class="status-badge">{report.overall_status}</span>
        </div>
    </div>

    <div class="container">
        <!-- Executive Summary -->
        <div class="grid">
            <div class="card">
                <h3>🎯 Executive Summary</h3>
                <div class="metric">
                    <span class="metric-label">Overall Status</span>
                    <span class="metric-value" style="color: {status_colors.get(report.overall_status, '#6b7280')}">{report.overall_status}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Compliance Score</span>
                    <span class="metric-value">{report.compliance_score:.1f}/100</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Active Alerts</span>
                    <span class="metric-value">{len(report.alerts)}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Recommendations</span>
                    <span class="metric-value">{len(report.recommendations)}</span>
                </div>
            </div>
            
            <div class="card">
                <h3>💰 Trading Performance</h3>
                <div class="metric">
                    <span class="metric-label">Total Balance</span>
                    <span class="metric-value">${report.trading_metrics.total_balance:.2f}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Active Positions</span>
                    <span class="metric-value">{report.trading_metrics.active_positions}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Total P&L</span>
                    <span class="metric-value {'pnl-positive' if report.trading_metrics.total_pnl >= 0 else 'pnl-negative'}">${report.trading_metrics.total_pnl:.2f}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">P&L Percentage</span>
                    <span class="metric-value {'pnl-positive' if report.trading_metrics.pnl_percentage >= 0 else 'pnl-negative'}">{report.trading_metrics.pnl_percentage:.2f}%</span>
                </div>
            </div>
            
            <div class="card">
                <h3>🖥️ System Health</h3>
                <div class="metric">
                    <span class="metric-label">CPU Usage</span>
                    <span class="metric-value">{report.system_health.cpu_percent:.1f}%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Memory Usage</span>
                    <span class="metric-value">{report.system_health.memory_percent:.1f}%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Disk Usage</span>
                    <span class="metric-value">{report.system_health.disk_percent:.1f}%</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Uptime</span>
                    <span class="metric-value">{report.system_health.uptime_hours:.1f}h</span>
                </div>
            </div>
        </div>

        <!-- Alerts Section -->
        {self.generate_alerts_section(report.alerts)}

        <!-- Recommendations Section -->
        {self.generate_recommendations_section(report.recommendations)}

        <!-- Services Status -->
        {self.generate_services_section(report.services)}

        <!-- Positions Analysis -->
        {self.generate_positions_section(report.positions)}

        <!-- Charts -->
        {self.generate_charts_section(report)}
    </div>

    <script>
        {self.generate_charts_javascript(report)}
    </script>
</body>
</html>"""
        return html
    
    def generate_alerts_section(self, alerts: List[str]) -> str:
        """Generate alerts section"""
        if not alerts:
            return """
            <div class="card">
                <h3>✅ System Alerts</h3>
                <p style="color: #22c55e; font-weight: bold;">No active alerts - system operating normally</p>
            </div>"""
        
        alerts_html = ""
        for alert in alerts:
            alerts_html += f'<div class="alert">{alert}</div>'
        
        return f"""
        <div class="card">
            <h3>⚠️ System Alerts ({len(alerts)})</h3>
            {alerts_html}
        </div>"""
    
    def generate_recommendations_section(self, recommendations: List[str]) -> str:
        """Generate recommendations section"""
        if not recommendations:
            return """
            <div class="card">
                <h3>💡 Recommendations</h3>
                <p style="color: #22c55e;">System is optimally configured - no recommendations</p>
            </div>"""
        
        rec_html = ""
        for rec in recommendations:
            rec_html += f'<div class="recommendation">{rec}</div>'
        
        return f"""
        <div class="card">
            <h3>💡 Recommendations ({len(recommendations)})</h3>
            {rec_html}
        </div>"""
    
    def generate_services_section(self, services) -> str:
        """Generate services status section"""
        services_html = ""
        for service in services:
            status_class = "service-running" if service.status == "Running" else "service-stopped"
            services_html += f"""
            <tr>
                <td>{service.name}</td>
                <td><span class="service-status {status_class}">{service.status}</span></td>
                <td>{service.pid or 'N/A'}</td>
                <td>{f'{service.uptime:.1f}h' if service.uptime else 'N/A'}</td>
                <td>{f'{service.memory_mb:.1f}MB' if service.memory_mb else 'N/A'}</td>
                <td>{service.error_count}</td>
            </tr>"""
        
        return f"""
        <div class="card" style="grid-column: 1 / -1;">
            <h3>🔧 Services Status</h3>
            <table class="positions-table">
                <thead>
                    <tr>
                        <th>Service</th>
                        <th>Status</th>
                        <th>PID</th>
                        <th>Uptime</th>
                        <th>Memory</th>
                        <th>Errors</th>
                    </tr>
                </thead>
                <tbody>
                    {services_html}
                </tbody>
            </table>
        </div>"""
    
    def generate_positions_section(self, positions) -> str:
        """Generate positions analysis section"""
        if not positions:
            return """
            <div class="card" style="grid-column: 1 / -1;">
                <h3>📊 Active Positions</h3>
                <p>No active positions</p>
            </div>"""
        
        positions_html = ""
        for pos in positions:
            zone_class = f"zone-{pos.zone.lower()}" if pos.zone.lower() in ['profit', 'loss'] else "zone-neutral"
            pnl_class = "pnl-positive" if pos.pnl >= 0 else "pnl-negative"
            
            positions_html += f"""
            <tr>
                <td><strong>{pos.symbol}</strong></td>
                <td>{pos.side.upper()}</td>
                <td>{pos.size:.0f}</td>
                <td>${pos.current_price:.4f}</td>
                <td class="{pnl_class}">${pos.pnl:.4f}</td>
                <td class="{pnl_class}">{pos.pnl_percentage:.2f}%</td>
                <td><span class="service-status {zone_class}">{pos.zone}</span></td>
                <td>{pos.leverage}x</td>
                <td>{pos.age_hours:.1f}h</td>
                <td style="color: {'#ef4444' if pos.risk_level == 'High' else '#eab308' if pos.risk_level == 'Medium' else '#22c55e'}">{pos.risk_level}</td>
            </tr>"""
        
        return f"""
        <div class="card" style="grid-column: 1 / -1;">
            <h3>📊 Active Positions ({len(positions)})</h3>
            <table class="positions-table">
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Side</th>
                        <th>Size</th>
                        <th>Price</th>
                        <th>P&L</th>
                        <th>P&L %</th>
                        <th>Zone</th>
                        <th>Leverage</th>
                        <th>Age</th>
                        <th>Risk</th>
                    </tr>
                </thead>
                <tbody>
                    {positions_html}
                </tbody>
            </table>
        </div>"""
    
    def generate_charts_section(self, report: AuditReport) -> str:
        """Generate charts section"""
        return """
        <div class="grid">
            <div class="card">
                <h3>📈 System Resources</h3>
                <div class="chart-container">
                    <canvas id="resourcesChart"></canvas>
                </div>
            </div>
            
            <div class="card">
                <h3>💰 Position P&L Distribution</h3>
                <div class="chart-container">
                    <canvas id="pnlChart"></canvas>
                </div>
            </div>
        </div>"""
    
    def generate_charts_javascript(self, report: AuditReport) -> str:
        """Generate JavaScript for charts"""
        
        # Prepare position PnL data
        pnl_data = [pos.pnl for pos in report.positions] if report.positions else [0]
        pnl_labels = [pos.symbol for pos in report.positions] if report.positions else ['No Positions']
        
        return f"""
        // System Resources Chart
        const resourcesCtx = document.getElementById('resourcesChart').getContext('2d');
        new Chart(resourcesCtx, {{
            type: 'doughnut',
            data: {{
                labels: ['CPU', 'Memory', 'Disk'],
                datasets: [{{
                    data: [{report.system_health.cpu_percent}, {report.system_health.memory_percent}, {report.system_health.disk_percent}],
                    backgroundColor: ['#ef4444', '#f97316', '#eab308']
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ position: 'bottom' }}
                }}
            }}
        }});

        // Position P&L Chart
        const pnlCtx = document.getElementById('pnlChart').getContext('2d');
        new Chart(pnlCtx, {{
            type: 'bar',
            data: {{
                labels: {json.dumps(pnl_labels)},
                datasets: [{{
                    label: 'P&L ($)',
                    data: {json.dumps(pnl_data)},
                    backgroundColor: {json.dumps(['#22c55e' if pnl >= 0 else '#ef4444' for pnl in pnl_data])}
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ beginAtZero: true }}
                }}
            }}
        }});"""
    
    def save_report(self, report: AuditReport) -> str:
        """Save HTML report to file"""
        # Generate filename
        timestamp = report.timestamp.strftime('%Y%m%d_%H%M%S')
        filename = f"aixyz_audit_{timestamp}.html"
        filepath = os.path.join(self.reports_dir, filename)
        
        # Generate HTML
        html_content = self.generate_html_report(report)
        
        # Save file
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Update index file
        self.update_index_file(report, filename)
        
        return filepath
    
    def update_index_file(self, report: AuditReport, filename: str):
        """Update reports index page"""
        
        # Status color mapping
        status_colors = {
            "Excellent": "#22c55e",
            "Good": "#84cc16", 
            "Fair": "#eab308",
            "Poor": "#f97316",
            "Critical": "#ef4444"
        }
        
        index_html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI-XYZ System Reports</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6; color: #333; background: #f8fafc;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 2rem 0; text-align: center;
        }}
        
        .container {{ max-width: 1000px; margin: 0 auto; padding: 2rem 1rem; }}
        
        .latest-report {{
            background: white; border-radius: 10px; padding: 2rem; 
            box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 2rem;
            border-left: 4px solid #667eea;
        }}
        
        .status-badge {{
            display: inline-block; padding: 0.5rem 1rem; border-radius: 25px;
            font-weight: bold; color: white; margin-left: 1rem;
            background: {status_colors.get(report.overall_status, '#6b7280')};
        }}
        
        .metrics {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1.5rem 0; }}
        
        .metric {{
            background: #f9fafb; padding: 1rem; border-radius: 8px; text-align: center;
        }}
        
        .metric-value {{ font-size: 1.5rem; font-weight: bold; color: #374151; }}
        .metric-label {{ color: #6b7280; font-size: 0.875rem; }}
        
        .view-button {{
            background: #667eea; color: white; padding: 0.75rem 2rem;
            border: none; border-radius: 5px; font-size: 1rem; cursor: pointer;
            text-decoration: none; display: inline-block; margin-top: 1rem;
        }}
        
        .view-button:hover {{ background: #5a67d8; }}
        
        .info {{ background: #f0f9ff; border: 1px solid #bae6fd; padding: 1rem; border-radius: 5px; margin-top: 2rem; }}
        
        .pnl-positive {{ color: #22c55e; font-weight: bold; }}
        .pnl-negative {{ color: #ef4444; font-weight: bold; }}
        
        @media (max-width: 768px) {{
            .metrics {{ grid-template-columns: repeat(2, 1fr); }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="container">
            <h1>🔍 AI-XYZ System Reports</h1>
            <p>Automated Trading System Monitoring & Audit</p>
        </div>
    </div>

    <div class="container">
        <div class="latest-report">
            <h2>Latest System Audit</h2>
            <p><strong>Generated:</strong> {report.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            <span class="status-badge">{report.overall_status}</span>
            
            <div class="metrics">
                <div class="metric">
                    <div class="metric-value">{report.compliance_score:.0f}/100</div>
                    <div class="metric-label">Compliance Score</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value">{report.trading_metrics.active_positions}</div>
                    <div class="metric-label">Active Positions</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value {'pnl-positive' if report.trading_metrics.total_pnl >= 0 else 'pnl-negative'}">${report.trading_metrics.total_pnl:.2f}</div>
                    <div class="metric-label">Total P&L</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value">{report.system_health.cpu_percent:.0f}%</div>
                    <div class="metric-label">CPU Usage</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value">{len(report.alerts)}</div>
                    <div class="metric-label">Active Alerts</div>
                </div>
                
                <div class="metric">
                    <div class="metric-value">{len([s for s in report.services if s.status == 'Running'])}/{len(report.services)}</div>
                    <div class="metric-label">Services Running</div>
                </div>
            </div>
            
            <a href="{filename}" class="view-button">📊 View Detailed Report</a>
        </div>
        
        <div class="info">
            <h3>📋 About These Reports</h3>
            <p><strong>Purpose:</strong> Comprehensive automated audits of the AI-XYZ trading system</p>
            <p><strong>Frequency:</strong> Generated every 30 minutes</p>
            <p><strong>Coverage:</strong> System health, trading performance, position analysis, service status</p>
            <p><strong>Access:</strong> Reports available at <code>moondox.eu/reports</code></p>
        </div>
    </div>
</body>
</html>"""
        
        # Save index file
        index_path = os.path.join(self.reports_dir, 'index.html')
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(index_html)

def main():
    """Generate a test report"""
    print("🚀 Generating AI-XYZ Audit Report...")
    
    # Run audit
    auditor = AIXYZAuditor()
    report = auditor.run_audit()
    
    # Generate report
    generator = ReportGenerator()
    filepath = generator.save_report(report)
    
    print(f"✅ Report generated: {filepath}")
    print(f"🌐 Available at: https://moondox.eu/reports/")
    
    return filepath

if __name__ == "__main__":
    main()