#!/usr/bin/env python3
"""
Bitget Onchain Runner - Continuous Operation
=============================================
Runs the BitgetOnchainService in continuous mode, scanning for
opportunities and monitoring xStock prices every 4 hours.
"""

import asyncio
import os
import structlog
from datetime import datetime
from bitget_onchain_service import BitgetOnchainService

logger = structlog.get_logger(__name__)

# Configuration
SCAN_INTERVAL_HOURS = int(os.getenv('SCAN_INTERVAL_HOURS', 4))
SCAN_INTERVAL_SECONDS = SCAN_INTERVAL_HOURS * 3600


async def run_continuous():
    """Run continuous scanning loop"""
    logger.info("Starting Bitget Onchain continuous runner",
               interval_hours=SCAN_INTERVAL_HOURS)

    while True:
        try:
            async with BitgetOnchainService() as service:
                # Scan for opportunities
                logger.info("="*60)
                logger.info(f"xSTOCKS SCAN - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info("="*60)

                opportunities = await service.scan_opportunities()

                if opportunities:
                    logger.info(f"Found {len(opportunities)} stocks")
                    for opp in opportunities:
                        signal_icon = {'buy': '+', 'sell': '-', 'hold': '='}[opp['signal']]
                        logger.info(f"  {signal_icon} {opp['symbol']:8} ${opp['price']:>8.2f} "
                                   f"24h: {opp['change_24h']:>+6.2f}% [{opp['sector']}]")

                    # Log top movers
                    buy_signals = [o for o in opportunities if o['signal'] == 'buy']
                    sell_signals = [o for o in opportunities if o['signal'] == 'sell']

                    if buy_signals:
                        logger.info(f"BUY signals: {', '.join([o['symbol'] for o in buy_signals])}")
                    if sell_signals:
                        logger.info(f"SELL signals: {', '.join([o['symbol'] for o in sell_signals])}")
                else:
                    logger.warning("No opportunities found")

                logger.info(f"Next scan in {SCAN_INTERVAL_HOURS} hours...")

        except Exception as e:
            logger.error(f"Error in scan cycle: {e}")

        # Wait for next scan
        await asyncio.sleep(SCAN_INTERVAL_SECONDS)


def main():
    """Main entry point"""
    try:
        asyncio.run(run_continuous())
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()
