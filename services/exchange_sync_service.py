#!/usr/bin/env python3
"""
Exchange Sync Service - Continuously syncs position data with Bitget
"""
import ccxt
import json
import os
import time
from datetime import datetime
from dotenv import load_dotenv
import sys
sys.path.insert(0, '/app')
sys.path.insert(0, '/app/core')

load_dotenv('/app/.env')

class ExchangeSyncService:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })
        self.registry = LivePositionsRegistry()
        self.averaging_engine = AveragingEngine(self.registry, self.exchange)
        
    def sync_and_check_averaging(self):
        """Sync positions and check for averaging opportunities"""
        state_file = '/app/position_state.json'
        
        try:
            # Load current state
            with open(state_file, 'r') as f:
                state = json.load(f)
            
            # Fetch positions from exchange
            positions = self.exchange.fetch_positions()
            
            for pos in positions:
                symbol = pos['symbol']
                if symbol in state['active_positions']:
                    # Update with live data
                    upnl = pos.get('unrealizedPnl', 0)
                    current_price = pos.get('markPrice', 0)
                    
                    # Update state with live data
                    state['active_positions'][symbol]['unrealized_pnl'] = upnl
                    state['active_positions'][symbol]['current_price'] = current_price
                    state['active_positions'][symbol]['mark_price'] = current_price
                    
                    # Calculate P&L percentage
                    entry = state['active_positions'][symbol]['entry_price']
                    amount = state['active_positions'][symbol]['amount']
                    leverage = state['active_positions'][symbol].get('leverage', 8)
                    
                    if entry > 0:
                        pnl_pct = ((current_price - entry) / entry) * 100
                        state['active_positions'][symbol]['pnl_percentage'] = pnl_pct
                        
                        # Calculate initial margin
                        initial_margin = (entry * amount) / leverage
                        upnl_pct = (upnl / initial_margin) * 100 if initial_margin > 0 else 0
                        
                        print(f"📊 {symbol}: UPNL=${upnl:.2f} ({upnl_pct:.1f}%), Price=${current_price:.5f}")
                        
                        # Check if averaging needed
                        if upnl_pct <= -10 and state['position_zones'].get(symbol) == 'AVERAGING':
                            steps_taken = state['averaging_steps'].get(symbol, 0)
                            print(f"⚠️ {symbol} needs averaging: {upnl_pct:.1f}% loss, {steps_taken} steps taken")
                            
                            # Trigger averaging if not at max steps
                            if steps_taken < 7:  # Max 7 Fibonacci steps
                                print(f"🔄 Triggering averaging for {symbol}...")
                                # This will be handled by the averaging engine
            
            # Save updated state
            state['timestamp'] = datetime.now().isoformat()
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            print(f"❌ Sync error: {e}")
    
    def run(self):
        """Run continuous sync loop"""
        print("🚀 Exchange Sync Service started")
        while True:
            try:
                self.sync_and_check_averaging()
                time.sleep(10)  # Sync every 10 seconds
            except KeyboardInterrupt:
                print("\n👋 Stopping sync service")
                break
            except Exception as e:
                print(f"❌ Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    service = ExchangeSyncService()
    service.run()