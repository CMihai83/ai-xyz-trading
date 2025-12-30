#!/usr/bin/env python3
"""
Launch AI-XYZ Continuous Trading System
Simplified version for immediate execution
"""

import ccxt
import time
import json
from datetime import datetime
from position_sizing_config import PositionSizingConfig
from enhanced_market_scanner import EnhancedMarketScanner

class ContinuousTradingSystem:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
            'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
            'password': '2609Luiza',
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap',
                'defaultMarginMode': 'isolated'
            }
        })
        
        self.scanner = EnhancedMarketScanner()
        self.max_positions = 10
        self.min_score = 0.5
        self.active_positions = {}
        self.total_pnl = 0
    
    def scan_and_open(self):
        """Scan market and open positions"""
        print(f"\n🔍 Scanning at {datetime.now().strftime('%H:%M:%S')}...")
        
        # Get current positions
        positions = self.exchange.fetch_positions()
        active = [p for p in positions if p['contracts'] > 0]
        current_count = len(active)
        
        print(f"  Current positions: {current_count}/{self.max_positions}")
        
        if current_count >= self.max_positions:
            print("  Max positions reached")
            return
        
        # Generate trading signals
        signals = self.scanner.generate_trading_signals(max_signals=self.max_positions - current_count)
        
        if not signals:
            print("  No opportunities found")
            return
        
        # Open positions
        for signal in signals:
            try:
                symbol = signal['symbol']
                
                # Check if already have position
                if any(p['symbol'] == symbol for p in active):
                    continue
                
                print(f"\n🎯 Opening {symbol}")
                print(f"  Action: {signal['action']}")
                print(f"  Score: {signal['score']:.2f}")
                print(f"  Leverage: {signal['leverage']}x")
                
                # Calculate position size
                sizing = PositionSizingConfig.get_position_size_for_signal(signal)
                
                # Get current price
                ticker = self.exchange.fetch_ticker(symbol)
                price = ticker['last']
                amount = sizing['position_value'] / price
                
                # Set margin and leverage
                self.exchange.set_margin_mode('isolated', symbol)
                self.exchange.set_leverage(signal['leverage'], symbol)
                
                # Execute trade
                side = signal['action'].lower()
                order = self.exchange.create_order(
                    symbol=symbol,
                    type='market',
                    side=side,
                    amount=amount
                )
                
                print(f"  ✅ Opened: {amount:.4f} contracts @ {price}")
                
                self.active_positions[symbol] = {
                    'entry_price': price,
                    'amount': amount,
                    'side': side,
                    'leverage': signal['leverage'],
                    'opened_at': datetime.now().isoformat()
                }
                
            except Exception as e:
                print(f"  ❌ Failed: {e}")
    
    def monitor_positions(self):
        """Monitor and manage positions"""
        print(f"\n📊 Monitoring at {datetime.now().strftime('%H:%M:%S')}...")
        
        positions = self.exchange.fetch_positions()
        total_upnl = 0
        
        for pos in positions:
            if pos['contracts'] > 0:
                symbol = pos['symbol']
                upnl = pos.get('unrealizedPnl', 0)
                pct = pos.get('percentage', 0)
                total_upnl += upnl
                
                # Display status
                status = "🟢" if upnl > 0 else "🔴"
                print(f"  {symbol}: {status} ${upnl:.4f} ({pct:.2f}%)")
                
                # Take profit at 5%
                if pct > 5.0:
                    try:
                        side = 'sell' if pos['side'] == 'long' else 'buy'
                        self.exchange.create_order(
                            symbol=symbol,
                            type='market',
                            side=side,
                            amount=pos['contracts'],
                            params={'reduceOnly': True}
                        )
                        print(f"    ✅ Profit taken: ${upnl:.4f}")
                        self.total_pnl += upnl
                        if symbol in self.active_positions:
                            del self.active_positions[symbol]
                    except:
                        pass
                
                # Stop loss at -10%
                elif pct < -10.0:
                    try:
                        side = 'sell' if pos['side'] == 'long' else 'buy'
                        self.exchange.create_order(
                            symbol=symbol,
                            type='market',
                            side=side,
                            amount=pos['contracts'],
                            params={'reduceOnly': True}
                        )
                        print(f"    🛑 Stop loss: ${upnl:.4f}")
                        self.total_pnl += upnl
                        if symbol in self.active_positions:
                            del self.active_positions[symbol]
                    except:
                        pass
        
        print(f"  Total UPNL: ${total_upnl:.4f}")
        print(f"  Session P&L: ${self.total_pnl:.4f}")
    
    def run(self, duration_minutes=5):
        """Run the system for specified duration"""
        print("="*70)
        print("AI-XYZ CONTINUOUS TRADING SYSTEM")
        print("="*70)
        print(f"Start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Get starting balance
        balance = self.exchange.fetch_balance()
        start_balance = balance.get('USDT', {}).get('total', 0)
        print(f"Starting Balance: ${start_balance:.2f} USDT")
        
        print(f"\n🚀 Running for {duration_minutes} minutes...")
        print("="*70)
        
        end_time = time.time() + (duration_minutes * 60)
        cycle = 0
        
        try:
            while time.time() < end_time:
                cycle += 1
                print(f"\n📍 Cycle #{cycle}")
                
                # Scan and open new positions
                self.scan_and_open()
                
                # Wait 15 seconds
                time.sleep(15)
                
                # Monitor existing positions
                self.monitor_positions()
                
                # Display balance
                balance = self.exchange.fetch_balance()
                current_balance = balance.get('USDT', {}).get('total', 0)
                print(f"\n💰 Balance: ${current_balance:.2f} USDT")
                
                # Wait before next cycle
                time.sleep(15)
                
        except KeyboardInterrupt:
            print("\n⛔ Stopped by user")
        
        # Final summary
        print("\n" + "="*70)
        print("FINAL SUMMARY")
        print("="*70)
        
        balance = self.exchange.fetch_balance()
        final_balance = balance.get('USDT', {}).get('total', 0)
        
        print(f"Starting Balance: ${start_balance:.2f}")
        print(f"Final Balance: ${final_balance:.2f}")
        print(f"Net Change: ${final_balance - start_balance:.2f}")
        print(f"Session P&L: ${self.total_pnl:.4f}")
        
        if start_balance > 0:
            roi = ((final_balance - start_balance) / start_balance) * 100
            print(f"ROI: {roi:.2f}%")
        
        # List active positions
        positions = self.exchange.fetch_positions()
        active = [p for p in positions if p['contracts'] > 0]
        
        if active:
            print(f"\nActive Positions ({len(active)}):")
            for pos in active:
                print(f"  {pos['symbol']}: {pos['side']} | UPNL: ${pos.get('unrealizedPnl', 0):.4f}")

if __name__ == "__main__":
    system = ContinuousTradingSystem()
    system.run(duration_minutes=5)  # Run for 5 minutes