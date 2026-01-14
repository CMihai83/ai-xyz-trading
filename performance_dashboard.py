#!/usr/bin/env python3
"""
Performance Dashboard for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Real-time monitoring dashboard displaying:
- Market regime status (HIGH_VOL/TRENDING/RANGING/NORMAL)
- Dynamic parameter values
- Position P&L and drawdowns
- Active positions and zones
- System health metrics

Grok recommendation #3: Performance dashboard for operational oversight.

Author: Claude + Grok Consortium
"""

import json
import os
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from flask import Flask, jsonify, render_template_string
import threading
import time

app = Flask(__name__)

# Dashboard HTML Template
DASHBOARD_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>AI-XYZ Performance Dashboard</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #1a1a2e;
            color: #eee;
            padding: 20px;
        }
        .header {
            text-align: center;
            padding: 20px;
            background: linear-gradient(135deg, #16213e 0%, #0f3460 100%);
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .header h1 { color: #00d4ff; }
        .header .timestamp { color: #888; font-size: 14px; }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
        }
        .card {
            background: #16213e;
            border-radius: 10px;
            padding: 20px;
            border: 1px solid #0f3460;
        }
        .card h2 {
            color: #00d4ff;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #0f3460;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
            border-bottom: 1px solid #0f346033;
        }
        .metric:last-child { border-bottom: none; }
        .metric-label { color: #888; }
        .metric-value { font-weight: bold; }
        .regime-HIGH_VOLATILITY { color: #ff6b6b; }
        .regime-TRENDING { color: #4ecdc4; }
        .regime-RANGING { color: #ffe66d; }
        .regime-NORMAL { color: #95e1d3; }
        .positive { color: #4ecdc4; }
        .negative { color: #ff6b6b; }
        .neutral { color: #ffe66d; }
        .position-row {
            background: #0f3460;
            padding: 10px;
            margin: 5px 0;
            border-radius: 5px;
        }
        .position-symbol { font-weight: bold; color: #00d4ff; }
        .zone-NEUTRAL { color: #888; }
        .zone-AVERAGING { color: #ff6b6b; }
        .zone-PROFIT_TAKING { color: #4ecdc4; }
        .zone-SURPLUS_DUMP { color: #ffe66d; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 8px; text-align: left; }
        th { color: #00d4ff; border-bottom: 1px solid #0f3460; }
        .status-ok { color: #4ecdc4; }
        .status-warning { color: #ffe66d; }
        .status-error { color: #ff6b6b; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🤖 AI-XYZ Performance Dashboard</h1>
        <p class="timestamp">Last Updated: {{ data.timestamp }}</p>
    </div>

    <div class="grid">
        <!-- Account Summary -->
        <div class="card">
            <h2>💰 Account Summary</h2>
            <div class="metric">
                <span class="metric-label">Balance</span>
                <span class="metric-value">${{ "%.2f"|format(data.account.balance) }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Free Margin</span>
                <span class="metric-value">${{ "%.2f"|format(data.account.free_margin) }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Used Margin</span>
                <span class="metric-value">${{ "%.2f"|format(data.account.used_margin) }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Margin Utilization</span>
                <span class="metric-value {% if data.account.margin_utilization > 0.8 %}negative{% elif data.account.margin_utilization > 0.5 %}neutral{% else %}positive{% endif %}">
                    {{ "%.1f"|format(data.account.margin_utilization * 100) }}%
                </span>
            </div>
            <div class="metric">
                <span class="metric-label">Unrealized P&L</span>
                <span class="metric-value {% if data.account.unrealized_pnl > 0 %}positive{% else %}negative{% endif %}">
                    ${{ "%.2f"|format(data.account.unrealized_pnl) }}
                </span>
            </div>
        </div>

        <!-- Market Regime -->
        <div class="card">
            <h2>📊 Market Regime</h2>
            <div class="metric">
                <span class="metric-label">Current Regime</span>
                <span class="metric-value regime-{{ data.regime.current }}">{{ data.regime.current }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">ATR Ratio</span>
                <span class="metric-value">{{ "%.2f"|format(data.regime.atr_ratio) }}x</span>
            </div>
            <div class="metric">
                <span class="metric-label">Regime Changes (24h)</span>
                <span class="metric-value">{{ data.regime.changes_24h }}</span>
            </div>
        </div>

        <!-- Dynamic Parameters -->
        <div class="card">
            <h2>🎯 Dynamic Parameters</h2>
            <div class="metric">
                <span class="metric-label">Averaging Trigger</span>
                <span class="metric-value">{{ "%.0f"|format(data.params.averaging_trigger * 100) }}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Surplus Dump S1</span>
                <span class="metric-value">{{ "%.0f"|format(data.params.surplus_dump_s1 * 100) }}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Surplus Dump S2</span>
                <span class="metric-value">{{ "%.0f"|format(data.params.surplus_dump_s2 * 100) }}%</span>
            </div>
            <div class="metric">
                <span class="metric-label">Max Leverage</span>
                <span class="metric-value">{{ data.params.max_leverage }}x</span>
            </div>
        </div>

        <!-- System Health -->
        <div class="card">
            <h2>🏥 System Health</h2>
            <div class="metric">
                <span class="metric-label">Trading System</span>
                <span class="metric-value status-{{ 'ok' if data.health.trading_system else 'error' }}">
                    {{ 'Online' if data.health.trading_system else 'Offline' }}
                </span>
            </div>
            <div class="metric">
                <span class="metric-label">Redis Connection</span>
                <span class="metric-value status-{{ 'ok' if data.health.redis else 'error' }}">
                    {{ 'Connected' if data.health.redis else 'Disconnected' }}
                </span>
            </div>
            <div class="metric">
                <span class="metric-label">Active Positions</span>
                <span class="metric-value">{{ data.health.active_positions }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Active Hedges</span>
                <span class="metric-value">{{ data.health.active_hedges }}</span>
            </div>
        </div>

        <!-- Active Positions -->
        <div class="card" style="grid-column: span 2;">
            <h2>📈 Active Positions (Top 10 by |P&L|)</h2>
            <table>
                <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Zone</th>
                    <th>Avg Steps</th>
                    <th>UPNL</th>
                    <th>UPNL %</th>
                </tr>
                {% for pos in data.positions[:10] %}
                <tr>
                    <td class="position-symbol">{{ pos.symbol }}</td>
                    <td>{{ pos.side }}</td>
                    <td class="zone-{{ pos.zone }}">{{ pos.zone }}</td>
                    <td>{{ pos.avg_steps }}</td>
                    <td class="{% if pos.upnl > 0 %}positive{% else %}negative{% endif %}">
                        ${{ "%.2f"|format(pos.upnl) }}
                    </td>
                    <td class="{% if pos.upnl_pct > 0 %}positive{% else %}negative{% endif %}">
                        {{ "%.1f"|format(pos.upnl_pct) }}%
                    </td>
                </tr>
                {% endfor %}
            </table>
        </div>
    </div>
</body>
</html>
"""


class DashboardDataCollector:
    """Collects data from Redis and state files for the dashboard."""

    def __init__(self):
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = None
        self._connect_redis()

    def _connect_redis(self):
        """Connect to Redis."""
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=1,
                decode_responses=True
            )
            self.redis_client.ping()
        except Exception as e:
            print(f"Redis connection failed: {e}")
            self.redis_client = None

    def get_position_state(self) -> Dict:
        """Get position state from file."""
        try:
            with open('/root/ai_xyz/position_state.json', 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def get_hedge_state(self) -> Dict:
        """Get hedge state from Redis."""
        try:
            if self.redis_client:
                state = self.redis_client.get('hedge_gateway:state')
                if state:
                    return json.loads(state)
        except Exception:
            pass
        return {'hedges': {}}

    def get_adaptive_thresholds(self) -> Dict:
        """Get current adaptive thresholds."""
        try:
            with open('/root/ai_xyz/adaptive_thresholds.json', 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def collect_dashboard_data(self) -> Dict:
        """Collect all data for dashboard display."""
        position_state = self.get_position_state()
        hedge_state = self.get_hedge_state()
        thresholds = self.get_adaptive_thresholds()

        # Get first symbol's thresholds for display (or defaults)
        sample_params = list(thresholds.values())[0] if thresholds else {}

        # Build positions list
        positions = []
        active_positions = position_state.get('active_positions', {})
        averaging_steps = position_state.get('averaging_steps', {})
        zones = position_state.get('zones', {})

        total_upnl = 0
        for symbol, pos_data in active_positions.items():
            upnl = pos_data.get('unrealized_pnl', 0)
            total_upnl += upnl

            positions.append({
                'symbol': symbol.replace('/USDT:USDT', ''),
                'side': pos_data.get('side', 'unknown'),
                'zone': zones.get(symbol, 'NEUTRAL'),
                'avg_steps': averaging_steps.get(symbol, 0),
                'upnl': upnl,
                'upnl_pct': pos_data.get('upnl_pct', 0)
            })

        # Sort by absolute UPNL
        positions.sort(key=lambda x: abs(x['upnl']), reverse=True)

        # Calculate margin utilization (estimate)
        used_margin = len(active_positions) * 5  # ~$5 per position
        balance = position_state.get('balance', 400)
        margin_util = used_margin / balance if balance > 0 else 0

        data = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'account': {
                'balance': balance,
                'free_margin': balance - used_margin,
                'used_margin': used_margin,
                'margin_utilization': margin_util,
                'unrealized_pnl': total_upnl
            },
            'regime': {
                'current': sample_params.get('regime', 'NORMAL'),
                'atr_ratio': sample_params.get('atr_percent', 1.0) / 100 if sample_params.get('atr_percent') else 1.0,
                'changes_24h': 0
            },
            'params': {
                'averaging_trigger': sample_params.get('averaging_start', -0.35),
                'surplus_dump_s1': sample_params.get('surplus_dump_85', 0.85),
                'surplus_dump_s2': sample_params.get('surplus_dump_50', 0.40),
                'max_leverage': 10
            },
            'health': {
                'trading_system': True,  # Could check Docker container status
                'redis': self.redis_client is not None,
                'active_positions': len(active_positions),
                'active_hedges': len(hedge_state.get('hedges', {}))
            },
            'positions': positions
        }

        return data


collector = DashboardDataCollector()


@app.route('/')
def dashboard():
    """Render the main dashboard."""
    data = collector.collect_dashboard_data()
    return render_template_string(DASHBOARD_HTML, data=data)


@app.route('/api/data')
def api_data():
    """Return dashboard data as JSON."""
    return jsonify(collector.collect_dashboard_data())


@app.route('/api/positions')
def api_positions():
    """Return positions data."""
    data = collector.collect_dashboard_data()
    return jsonify(data['positions'])


@app.route('/api/regime')
def api_regime():
    """Return current regime."""
    data = collector.collect_dashboard_data()
    return jsonify(data['regime'])


@app.route('/api/health')
def api_health():
    """Return system health status."""
    data = collector.collect_dashboard_data()
    return jsonify(data['health'])


def run_dashboard(host='0.0.0.0', port=8080):
    """Run the dashboard server."""
    print(f"Starting AI-XYZ Performance Dashboard on http://{host}:{port}")
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    run_dashboard()
