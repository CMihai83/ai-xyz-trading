#!/usr/bin/env python3
"""
Force AI-XYZ system to open positions for testing all lifecycle stages
This will temporarily adjust parameters to find opportunities
"""

import json
import time
import os
import sys
import asyncio
import ccxt.async_support as ccxt
from datetime import datetime
from dotenv import load_dotenv

load_dotenv('/app/.env')

class ForcePositionOpener:
    def __init__(self):
        self.original_config = None
        self.test_config = {
            'averaging_threshold': -0.05,  # More aggressive averaging at -5%
            'profit_threshold': 0.03,      # Lower profit target at 3%
            'surplus_trigger': 0.03,       # Lower surplus trigger
            'position_size': 6.5,
            'max_positions': 2              # Allow 2 positions for testing
        }
        
    def backup_config(self):
        """Backup original configuration"""
        with open('/app/runtime_config.json', 'r') as f:
            self.original_config = json.load(f)
        with open('/app/config_backup_test.json', 'w') as f:
            json.dump(self.original_config, f)
        print(f"✅ Backed up original config")
        
    def apply_test_config(self):
        """Apply test configuration for easier opportunity finding"""
        with open('/app/runtime_config.json', 'w') as f:
            json.dump(self.test_config, f)
        print(f"✅ Applied test config:")
        print(f"   - Averaging threshold: {self.test_config['averaging_threshold']} (-5%)")
        print(f"   - Profit threshold: {self.test_config['profit_threshold']} (3%)")
        print(f"   - Max positions: {self.test_config['max_positions']}")
        
    def restore_config(self):
        """Restore original configuration"""
        if self.original_config:
            with open('/app/runtime_config.json', 'w') as f:
                json.dump(self.original_config, f)
            print(f"✅ Restored original config")
            
    async def find_volatile_opportunities(self):
        """Find the most volatile coins for testing"""
        exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_API_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        
        try:
            # Get all tickers
            tickers = await exchange.fetch_tickers()
            
            # Filter USDT perpetuals with good volume
            opportunities = []
            for symbol, ticker in tickers.items():
                if symbol.endswith('/USDT:USDT'):
                    volume_24h = ticker.get('quoteVolume', 0)
                    price_change = abs(ticker.get('percentage', 0))
                    
                    if volume_24h > 100000 and price_change > 5:  # Active and volatile
                        opportunities.append({
                            'symbol': symbol,
                            'change_24h': ticker.get('percentage', 0),
                            'volume': volume_24h,
                            'volatility_score': price_change * (volume_24h / 100000)
                        })
            
            # Sort by volatility score
            opportunities.sort(key=lambda x: x['volatility_score'], reverse=True)
            
            print(f"\n📊 Top 10 Volatile Opportunities:")
            for i, opp in enumerate(opportunities[:10]):
                print(f"   {i+1}. {opp['symbol']}: {opp['change_24h']:.2f}% change, score: {opp['volatility_score']:.1f}")
            
            await exchange.close()
            return opportunities[:5]  # Return top 5
            
        except Exception as e:
            print(f"❌ Error finding opportunities: {e}")
            await exchange.close()
            return []
            
    async def trigger_position_open(self):
        """Trigger the AI-XYZ system to scan and open positions"""
        print("\n🔄 Triggering market scan...")
        
        # Create a signal file that the system can detect
        signal_data = {
            'force_scan': True,
            'timestamp': datetime.now().isoformat(),
            'min_score': 0.3,  # Lower minimum score
            'rsi_oversold': 40,  # Less strict RSI
            'rsi_overbought': 60
        }
        
        with open('/app/force_scan_signal.json', 'w') as f:
            json.dump(signal_data, f)
        
        print("✅ Scan signal created")
        print("   System should pick up opportunities within 30 seconds")
        
async def main():
    print("=" * 60)
    print("AI-XYZ POSITION LIFECYCLE TESTING")
    print("=" * 60)
    
    tester = ForcePositionOpener()
    
    try:
        # Step 1: Backup and apply test config
        print("\n1️⃣ Adjusting parameters for testing...")
        tester.backup_config()
        tester.apply_test_config()
        
        # Step 2: Find volatile opportunities
        print("\n2️⃣ Finding volatile opportunities...")
        opportunities = await tester.find_volatile_opportunities()
        
        if not opportunities:
            print("❌ No suitable opportunities found")
            return
            
        # Step 3: Trigger position opening
        print("\n3️⃣ Triggering position opening...")
        await tester.trigger_position_open()
        
        # Step 4: Monitor for position lifecycle
        print("\n4️⃣ Monitoring position lifecycle...")
        print("   The system will now:")
        print("   - Open positions in volatile coins")
        print("   - Perform averaging at -5% intervals")
        print("   - Execute surplus dump at +3%")
        print("   - Test stop loss if needed")
        print("\n   Monitor with: tail -f /tmp/aixyz_main.log")
        print("   Check status with: ./status.sh")
        
        print("\n⏰ Test will run for 10 minutes...")
        print("   After testing, config will be restored automatically")
        
        # Wait for testing
        await asyncio.sleep(600)  # 10 minutes
        
    except KeyboardInterrupt:
        print("\n⚠️ Test interrupted by user")
        
    finally:
        # Always restore config
        print("\n5️⃣ Restoring original configuration...")
        tester.restore_config()
        
        # Clean up signal file
        if os.path.exists('/app/force_scan_signal.json'):
            os.remove('/app/force_scan_signal.json')
            print("✅ Cleaned up signal file")
        
        print("\n✅ Test complete!")
        print("   Check ./status.sh for final results")

if __name__ == "__main__":
    asyncio.run(main())