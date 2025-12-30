#!/usr/bin/env python3
"""
AI-XYZ Leverage Risk Manager
Prevents liquidations by monitoring and adjusting high-leverage positions
"""

import json
import time
import logging
from datetime import datetime
import ccxt
import os
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('leverage_risk.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class LeverageRiskManager:
    def __init__(self):
        load_dotenv()
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_SECRET'),
            'password': os.getenv('BITGET_PASSWORD'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

        # Risk thresholds
        self.MAX_SAFE_LEVERAGE = {
            'default': 10,
            'volatile': 8,
            'stable': 15
        }

        self.LIQUIDATION_BUFFER = {
            10: 0.35,   # 35% buffer for 10x
            20: 0.20,   # 20% buffer for 20x
            30: 0.15,   # 15% buffer for 30x
            48: 0.10    # 10% buffer for 48x (CRITICAL)
        }

    def check_position_risk(self, symbol, position_data):
        """Check if position is at risk of liquidation"""
        leverage = position_data.get('leverage', 1)
        side = position_data.get('side', 'buy')
        entry_price = position_data.get('entry_price', 0)

        # Calculate liquidation threshold
        if leverage <= 10:
            buffer = 0.35
        elif leverage <= 20:
            buffer = 0.20
        elif leverage <= 30:
            buffer = 0.15
        else:
            buffer = 0.10  # High risk zone

        # Calculate approximate liquidation price
        if side == 'buy':
            liq_price = entry_price * (1 - 1/leverage + buffer)
        else:
            liq_price = entry_price * (1 + 1/leverage - buffer)

        return {
            'leverage': leverage,
            'risk_level': self.get_risk_level(leverage),
            'liquidation_buffer': buffer,
            'estimated_liq_price': liq_price,
            'recommendations': self.get_recommendations(leverage)
        }

    def get_risk_level(self, leverage):
        """Categorize risk level based on leverage"""
        if leverage <= 8:
            return "LOW"
        elif leverage <= 15:
            return "MEDIUM"
        elif leverage <= 25:
            return "HIGH"
        else:
            return "CRITICAL"

    def get_recommendations(self, leverage):
        """Provide recommendations based on leverage"""
        recommendations = []

        if leverage > 30:
            recommendations.append("⚠️ CRITICAL: Reduce leverage immediately to avoid liquidation")
            recommendations.append("🔴 Set tight stop-loss at -5% to -8%")
            recommendations.append("🚨 Monitor position every minute")

        elif leverage > 20:
            recommendations.append("⚠️ HIGH RISK: Consider reducing leverage")
            recommendations.append("🟠 Set stop-loss at -10% to -15%")
            recommendations.append("📊 Use averaging only with momentum confirmation")

        elif leverage > 10:
            recommendations.append("🟡 MEDIUM RISK: Standard monitoring required")
            recommendations.append("🔵 Set stop-loss at -20% to -25%")
            recommendations.append("✅ Averaging allowed with proper sizing")

        else:
            recommendations.append("🟢 LOW RISK: Safe leverage range")
            recommendations.append("✅ Full averaging strategy applicable")

        return recommendations

    def monitor_positions(self):
        """Continuous monitoring of all positions"""
        while True:
            try:
                # Load position state
                with open('position_state.json', 'r') as f:
                    state = json.load(f)

                logger.info("=" * 60)
                logger.info("LEVERAGE RISK ASSESSMENT")
                logger.info("=" * 60)

                for symbol, pos_data in state['active_positions'].items():
                    risk_analysis = self.check_position_risk(symbol, pos_data)

                    logger.info(f"\n{symbol}:")
                    logger.info(f"  Leverage: {risk_analysis['leverage']}x")
                    logger.info(f"  Risk Level: {risk_analysis['risk_level']}")
                    logger.info(f"  Liquidation Buffer: {risk_analysis['liquidation_buffer']:.1%}")

                    for rec in risk_analysis['recommendations']:
                        logger.info(f"  {rec}")

                    # Alert for critical positions
                    if risk_analysis['risk_level'] == "CRITICAL":
                        logger.warning(f"🚨 CRITICAL ALERT: {symbol} at {risk_analysis['leverage']}x leverage!")

                        # Auto-adjustment logic (optional)
                        if risk_analysis['leverage'] > 40:
                            logger.error(f"⚠️ {symbol} REQUIRES IMMEDIATE ACTION - Leverage too high!")
                            # Could implement auto-deleveraging here if needed

                time.sleep(30)  # Check every 30 seconds

            except Exception as e:
                logger.error(f"Error in monitoring: {e}")
                time.sleep(10)

if __name__ == "__main__":
    manager = LeverageRiskManager()
    logger.info("Starting AI-XYZ Leverage Risk Manager...")
    manager.monitor_positions()