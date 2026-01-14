#!/usr/bin/env python3
"""
Real-Time Risk Alerts for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Triggers alerts for critical events:
- High drawdown (>10%, >15%, >20%)
- Margin threshold breaches (>70%, >85%, >95%)
- Regime shifts (to HIGH_VOLATILITY)
- Multiple positions in AVERAGING zone
- Liquidation warnings
- System health issues

Notification channels:
- Console/Log output
- Dashboard API
- Telegram (if configured)

Author: Claude + Grok Consortium
"""

import json
import os
import redis
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import logging
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class AlertSeverity(Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    EMERGENCY = "EMERGENCY"


@dataclass
class Alert:
    """Represents a risk alert."""
    severity: AlertSeverity
    category: str
    message: str
    value: float
    threshold: float
    timestamp: datetime
    symbol: Optional[str] = None
    action_required: Optional[str] = None


class RiskAlertManager:
    """
    Manages real-time risk monitoring and alerting.

    Monitors:
    - Account drawdown
    - Margin utilization
    - Market regime changes
    - Position zone distributions
    - Individual position health
    """

    # Alert thresholds
    DRAWDOWN_THRESHOLDS = {
        AlertSeverity.WARNING: 0.10,      # 10% drawdown
        AlertSeverity.CRITICAL: 0.15,     # 15% drawdown
        AlertSeverity.EMERGENCY: 0.20     # 20% drawdown
    }

    MARGIN_THRESHOLDS = {
        AlertSeverity.WARNING: 0.70,      # 70% margin used
        AlertSeverity.CRITICAL: 0.85,     # 85% margin used
        AlertSeverity.EMERGENCY: 0.95     # 95% margin used
    }

    AVERAGING_POSITION_THRESHOLDS = {
        AlertSeverity.WARNING: 5,         # 5+ positions in AVERAGING
        AlertSeverity.CRITICAL: 8,        # 8+ positions in AVERAGING
        AlertSeverity.EMERGENCY: 10       # 10+ positions in AVERAGING
    }

    def __init__(self):
        self.redis_host = os.getenv('REDIS_HOST', 'localhost')
        self.redis_port = int(os.getenv('REDIS_PORT', 6379))
        self.redis_client = self._connect_redis()

        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')

        self.alerts_history: List[Alert] = []
        self.last_regime = 'NORMAL'
        self.cooldowns: Dict[str, datetime] = {}
        self.cooldown_minutes = 15  # Don't repeat same alert for 15 min

        # Alert callbacks
        self.callbacks: List[Callable[[Alert], None]] = []

    def _connect_redis(self) -> Optional[redis.Redis]:
        """Connect to Redis."""
        try:
            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                db=1,
                decode_responses=True
            )
            client.ping()
            return client
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            return None

    def add_callback(self, callback: Callable[[Alert], None]):
        """Add alert callback function."""
        self.callbacks.append(callback)

    def _is_on_cooldown(self, alert_key: str) -> bool:
        """Check if alert is on cooldown."""
        if alert_key not in self.cooldowns:
            return False

        cooldown_until = self.cooldowns[alert_key]
        return datetime.now() < cooldown_until

    def _set_cooldown(self, alert_key: str):
        """Set cooldown for an alert."""
        self.cooldowns[alert_key] = datetime.now() + timedelta(minutes=self.cooldown_minutes)

    def _get_position_state(self) -> Dict:
        """Get current position state."""
        try:
            with open('/root/ai_xyz/position_state.json', 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _get_adaptive_thresholds(self) -> Dict:
        """Get current adaptive thresholds."""
        try:
            with open('/root/ai_xyz/adaptive_thresholds.json', 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _trigger_alert(self, alert: Alert):
        """Trigger an alert through all channels."""
        # Add to history
        self.alerts_history.append(alert)
        if len(self.alerts_history) > 1000:
            self.alerts_history = self.alerts_history[-500:]

        # Log
        severity_colors = {
            AlertSeverity.INFO: '',
            AlertSeverity.WARNING: '⚠️ ',
            AlertSeverity.CRITICAL: '🔴 ',
            AlertSeverity.EMERGENCY: '🚨 '
        }
        prefix = severity_colors.get(alert.severity, '')
        logger.warning(f"{prefix}[{alert.severity.value}] {alert.category}: {alert.message}")

        if alert.action_required:
            logger.warning(f"   Action: {alert.action_required}")

        # Store in Redis
        if self.redis_client:
            try:
                alert_data = {
                    'severity': alert.severity.value,
                    'category': alert.category,
                    'message': alert.message,
                    'value': alert.value,
                    'threshold': alert.threshold,
                    'timestamp': alert.timestamp.isoformat(),
                    'symbol': alert.symbol,
                    'action_required': alert.action_required
                }
                self.redis_client.lpush('risk_alerts', json.dumps(alert_data))
                self.redis_client.ltrim('risk_alerts', 0, 99)  # Keep last 100
            except Exception as e:
                logger.error(f"Failed to store alert in Redis: {e}")

        # Send to Telegram (for CRITICAL and above)
        if alert.severity in [AlertSeverity.CRITICAL, AlertSeverity.EMERGENCY]:
            self._send_telegram(alert)

        # Call registered callbacks
        for callback in self.callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def _send_telegram(self, alert: Alert):
        """Send alert to Telegram."""
        if not self.telegram_token or not self.telegram_chat_id:
            return

        try:
            emoji = '🚨' if alert.severity == AlertSeverity.EMERGENCY else '🔴'
            message = f"{emoji} *AI-XYZ Risk Alert*\n\n"
            message += f"*Severity:* {alert.severity.value}\n"
            message += f"*Category:* {alert.category}\n"
            message += f"*Message:* {alert.message}\n"
            if alert.action_required:
                message += f"\n*Action Required:* {alert.action_required}"

            url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
            data = {
                'chat_id': self.telegram_chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            requests.post(url, data=data, timeout=5)
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

    def check_drawdown(self, current_balance: float, peak_balance: float) -> Optional[Alert]:
        """Check for drawdown alerts."""
        if peak_balance <= 0:
            return None

        drawdown = (peak_balance - current_balance) / peak_balance

        for severity, threshold in sorted(self.DRAWDOWN_THRESHOLDS.items(),
                                         key=lambda x: x[1], reverse=True):
            if drawdown >= threshold:
                alert_key = f"drawdown_{severity.value}"
                if self._is_on_cooldown(alert_key):
                    return None

                self._set_cooldown(alert_key)

                action = None
                if severity == AlertSeverity.EMERGENCY:
                    action = "Consider reducing positions or adding margin"
                elif severity == AlertSeverity.CRITICAL:
                    action = "Monitor positions closely, avoid new entries"

                alert = Alert(
                    severity=severity,
                    category="DRAWDOWN",
                    message=f"Account drawdown at {drawdown*100:.1f}%",
                    value=drawdown,
                    threshold=threshold,
                    timestamp=datetime.now(),
                    action_required=action
                )
                self._trigger_alert(alert)
                return alert

        return None

    def check_margin_utilization(self, used_margin: float, total_margin: float) -> Optional[Alert]:
        """Check for margin utilization alerts."""
        if total_margin <= 0:
            return None

        utilization = used_margin / total_margin

        for severity, threshold in sorted(self.MARGIN_THRESHOLDS.items(),
                                         key=lambda x: x[1], reverse=True):
            if utilization >= threshold:
                alert_key = f"margin_{severity.value}"
                if self._is_on_cooldown(alert_key):
                    return None

                self._set_cooldown(alert_key)

                action = None
                if severity == AlertSeverity.EMERGENCY:
                    action = "URGENT: Close positions or add funds to avoid liquidation"
                elif severity == AlertSeverity.CRITICAL:
                    action = "Reduce position sizes, no new positions"

                alert = Alert(
                    severity=severity,
                    category="MARGIN",
                    message=f"Margin utilization at {utilization*100:.1f}%",
                    value=utilization,
                    threshold=threshold,
                    timestamp=datetime.now(),
                    action_required=action
                )
                self._trigger_alert(alert)
                return alert

        return None

    def check_regime_change(self, new_regime: str) -> Optional[Alert]:
        """Check for regime change alerts."""
        if new_regime == self.last_regime:
            return None

        # Alert on transition to HIGH_VOLATILITY
        if new_regime == 'HIGH_VOLATILITY':
            alert_key = "regime_high_vol"
            if self._is_on_cooldown(alert_key):
                self.last_regime = new_regime
                return None

            self._set_cooldown(alert_key)

            alert = Alert(
                severity=AlertSeverity.WARNING,
                category="REGIME_CHANGE",
                message=f"Market regime changed: {self.last_regime} -> HIGH_VOLATILITY",
                value=0,
                threshold=0,
                timestamp=datetime.now(),
                action_required="Leverage reduced automatically. Monitor positions."
            )
            self._trigger_alert(alert)
            self.last_regime = new_regime
            return alert

        self.last_regime = new_regime
        return None

    def check_averaging_positions(self, zones: Dict[str, str]) -> Optional[Alert]:
        """Check for too many positions in AVERAGING zone."""
        averaging_count = sum(1 for zone in zones.values() if zone == 'AVERAGING')

        for severity, threshold in sorted(self.AVERAGING_POSITION_THRESHOLDS.items(),
                                         key=lambda x: x[1], reverse=True):
            if averaging_count >= threshold:
                alert_key = f"averaging_{severity.value}"
                if self._is_on_cooldown(alert_key):
                    return None

                self._set_cooldown(alert_key)

                action = None
                if severity == AlertSeverity.EMERGENCY:
                    action = "Consider closing worst performers to free capital"
                elif severity == AlertSeverity.CRITICAL:
                    action = "Review positions, prioritize exits for recovery"

                alert = Alert(
                    severity=severity,
                    category="POSITION_HEALTH",
                    message=f"{averaging_count} positions in AVERAGING zone",
                    value=averaging_count,
                    threshold=threshold,
                    timestamp=datetime.now(),
                    action_required=action
                )
                self._trigger_alert(alert)
                return alert

        return None

    def check_position_liquidation_risk(self, symbol: str, upnl_pct: float,
                                        leverage: int) -> Optional[Alert]:
        """Check if individual position is at liquidation risk."""
        # Liquidation typically at -100%/leverage UPNL
        liquidation_threshold = -100 / leverage * 0.9  # 90% of liquidation

        if upnl_pct <= liquidation_threshold:
            alert_key = f"liquidation_{symbol}"
            if self._is_on_cooldown(alert_key):
                return None

            self._set_cooldown(alert_key)

            alert = Alert(
                severity=AlertSeverity.EMERGENCY,
                category="LIQUIDATION_RISK",
                message=f"{symbol} at {upnl_pct:.1f}% UPNL - near liquidation",
                value=upnl_pct,
                threshold=liquidation_threshold,
                timestamp=datetime.now(),
                symbol=symbol,
                action_required="Add margin or close position immediately"
            )
            self._trigger_alert(alert)
            return alert

        return None

    def run_all_checks(self) -> List[Alert]:
        """Run all risk checks and return triggered alerts."""
        alerts = []

        # Get current state
        position_state = self._get_position_state()
        thresholds = self._get_adaptive_thresholds()

        # Account metrics
        balance = position_state.get('balance', 0)
        peak_balance = position_state.get('peak_balance', balance)
        active_positions = position_state.get('active_positions', {})
        zones = position_state.get('zones', {})

        # Estimate margin (simplified)
        used_margin = len(active_positions) * 5  # ~$5 per position
        total_margin = balance

        # Run checks
        drawdown_alert = self.check_drawdown(balance, peak_balance)
        if drawdown_alert:
            alerts.append(drawdown_alert)

        margin_alert = self.check_margin_utilization(used_margin, total_margin)
        if margin_alert:
            alerts.append(margin_alert)

        averaging_alert = self.check_averaging_positions(zones)
        if averaging_alert:
            alerts.append(averaging_alert)

        # Regime check
        if thresholds:
            sample_params = list(thresholds.values())[0]
            regime = sample_params.get('regime', 'NORMAL')
            regime_alert = self.check_regime_change(regime)
            if regime_alert:
                alerts.append(regime_alert)

        # Check individual positions for liquidation risk
        for symbol, pos_data in active_positions.items():
            upnl_pct = pos_data.get('upnl_pct', 0)
            leverage = pos_data.get('leverage', 10)
            liq_alert = self.check_position_liquidation_risk(symbol, upnl_pct, leverage)
            if liq_alert:
                alerts.append(liq_alert)

        return alerts

    def get_recent_alerts(self, limit: int = 20) -> List[Dict]:
        """Get recent alerts."""
        recent = self.alerts_history[-limit:]
        return [{
            'severity': a.severity.value,
            'category': a.category,
            'message': a.message,
            'timestamp': a.timestamp.isoformat(),
            'symbol': a.symbol
        } for a in recent]

    def get_alert_summary(self) -> Dict:
        """Get summary of recent alerts."""
        last_24h = datetime.now() - timedelta(hours=24)
        recent = [a for a in self.alerts_history if a.timestamp > last_24h]

        return {
            'total_24h': len(recent),
            'by_severity': {
                'INFO': sum(1 for a in recent if a.severity == AlertSeverity.INFO),
                'WARNING': sum(1 for a in recent if a.severity == AlertSeverity.WARNING),
                'CRITICAL': sum(1 for a in recent if a.severity == AlertSeverity.CRITICAL),
                'EMERGENCY': sum(1 for a in recent if a.severity == AlertSeverity.EMERGENCY)
            },
            'by_category': {}
        }


# Singleton instance
_alert_manager_instance = None

def get_risk_alert_manager() -> RiskAlertManager:
    """Get or create the singleton RiskAlertManager instance."""
    global _alert_manager_instance
    if _alert_manager_instance is None:
        _alert_manager_instance = RiskAlertManager()
    return _alert_manager_instance


if __name__ == "__main__":
    # Test the risk alert manager
    print("=" * 60)
    print("RISK ALERT MANAGER TEST")
    print("=" * 60)

    manager = RiskAlertManager()

    # Test drawdown alerts
    print("\nDrawdown Alert Tests:")
    for dd in [0.05, 0.10, 0.15, 0.20, 0.25]:
        peak = 1000
        current = peak * (1 - dd)
        alert = manager.check_drawdown(current, peak)
        status = f"Alert: {alert.severity.value}" if alert else "No alert"
        print(f"  {dd*100:.0f}% drawdown: {status}")

    # Test margin alerts
    print("\nMargin Utilization Alert Tests:")
    manager.cooldowns.clear()  # Reset cooldowns
    for util in [0.50, 0.70, 0.85, 0.95]:
        alert = manager.check_margin_utilization(util * 100, 100)
        status = f"Alert: {alert.severity.value}" if alert else "No alert"
        print(f"  {util*100:.0f}% utilization: {status}")

    # Test regime change
    print("\nRegime Change Alert Tests:")
    manager.cooldowns.clear()
    for regime in ['NORMAL', 'TRENDING', 'HIGH_VOLATILITY', 'RANGING']:
        alert = manager.check_regime_change(regime)
        status = f"Alert: {alert.message}" if alert else "No alert"
        print(f"  -> {regime}: {status}")

    print("\nRisk Alert Manager initialized successfully.")
