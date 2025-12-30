#!/usr/bin/env python3
"""
Analyze recent losses from AI-XYZ trading system
"""
import ccxt
import os
from datetime import datetime, timedelta
import pandas as pd

# Initialize exchange with environment variables
api_key = os.getenv('BITGET_API_KEY', 'bg_1dfc40220e38b5b118c4828b0cbcc2cb')
secret = os.getenv('BITGET_API_SECRET', '3cd89a3ceac5330b6a7323c43e91a5e38e0c536678e76a9e36a984966f02951b')
passphrase = os.getenv('BITGET_API_PASSPHRASE', '83Rule4All')

exchange = ccxt.bitget({
    'apiKey': api_key,
    'secret': secret,
    'password': passphrase,
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'adjustForTimeDifference': True
    }
})

print("=" * 80)
print("AI-XYZ RECENT LOSSES ANALYSIS")
print("=" * 80)
print()

try:
    # Get current balance
    balance = exchange.fetch_balance()
    total_balance = balance['USDT']['total'] if 'USDT' in balance else 0
    print(f"💰 Current Balance: ${total_balance:.2f} USDT")
    
    # Get closed orders/trades from the last 7 days
    since = int((datetime.now() - timedelta(days=7)).timestamp() * 1000)
    
    # Try to fetch closed orders
    try:
        closed_orders = exchange.fetch_closed_orders(since=since, limit=100)
        print(f"\n📊 Found {len(closed_orders)} closed orders in last 7 days")
    except Exception as e:
        print(f"⚠️ Could not fetch closed orders: {e}")
        closed_orders = []
    
    # Try to fetch my trades
    try:
        # Get trades for multiple symbols that were recently traded
        symbols = ['BAKE/USDT:USDT', 'BR/USDT:USDT', 'XAUT/USDT:USDT', 'NAORIS/USDT:USDT', 'PTB/USDT:USDT']
        all_trades = []
        
        for symbol in symbols:
            try:
                trades = exchange.fetch_my_trades(symbol, since=since, limit=50)
                if trades:
                    all_trades.extend(trades)
                    print(f"  Found {len(trades)} trades for {symbol}")
            except:
                pass
        
        if all_trades:
            print(f"\n💹 Total trades analyzed: {len(all_trades)}")
            
            # Group trades by symbol and calculate P&L
            symbol_pnl = {}
            for trade in all_trades:
                symbol = trade['symbol']
                if symbol not in symbol_pnl:
                    symbol_pnl[symbol] = {
                        'trades': [],
                        'total_cost': 0,
                        'total_amount': 0,
                        'fees': 0
                    }
                
                symbol_pnl[symbol]['trades'].append(trade)
                
                # Calculate based on side
                if trade['side'] == 'buy':
                    symbol_pnl[symbol]['total_cost'] += trade['cost']
                    symbol_pnl[symbol]['total_amount'] += trade['amount']
                else:  # sell
                    symbol_pnl[symbol]['total_cost'] -= trade['cost']
                    symbol_pnl[symbol]['total_amount'] -= trade['amount']
                
                if trade['fee']:
                    symbol_pnl[symbol]['fees'] += trade['fee']['cost'] if trade['fee']['cost'] else 0
            
            print("\n📉 LOSSES BY SYMBOL:")
            print("-" * 40)
            
            total_losses = 0
            for symbol, data in symbol_pnl.items():
                if data['total_amount'] == 0:  # Position closed
                    realized_pnl = -data['total_cost'] - data['fees']
                    if realized_pnl < 0:
                        print(f"{symbol}:")
                        print(f"  Realized Loss: ${realized_pnl:.2f}")
                        print(f"  Number of trades: {len(data['trades'])}")
                        print(f"  Fees paid: ${data['fees']:.2f}")
                        total_losses += realized_pnl
            
            if total_losses < 0:
                print("-" * 40)
                print(f"📊 TOTAL LOSSES: ${total_losses:.2f}")
                print(f"📊 Loss as % of current balance: {abs(total_losses/total_balance*100):.1f}%")
        else:
            print("No trades found in the specified period")
            
    except Exception as e:
        print(f"Error fetching trades: {e}")
    
    # Get current open positions
    print("\n🔴 CURRENT POSITIONS WITH LOSSES:")
    print("-" * 40)
    
    positions = exchange.fetch_positions()
    total_unrealized_loss = 0
    
    for pos in positions:
        if pos['contracts'] > 0 and pos['unrealizedPnl'] and pos['unrealizedPnl'] < 0:
            print(f"{pos['symbol']} ({pos['side'].upper()}):")
            print(f"  Unrealized Loss: ${pos['unrealizedPnl']:.2f} ({pos['percentage']:.1f}%)")
            print(f"  Size: {pos['contracts']} contracts")
            print(f"  Entry: ${pos['markPrice']:.5f}")
            total_unrealized_loss += pos['unrealizedPnl']
    
    if total_unrealized_loss < 0:
        print("-" * 40)
        print(f"📊 TOTAL UNREALIZED LOSSES: ${total_unrealized_loss:.2f}")
        print(f"📊 Unrealized loss as % of balance: {abs(total_unrealized_loss/total_balance*100):.1f}%")
    
    print("\n" + "=" * 80)
    print("LOSS ANALYSIS SUMMARY")
    print("=" * 80)
    
    if total_losses < 0 or total_unrealized_loss < 0:
        print(f"💔 Total Realized Losses (closed): ${total_losses:.2f}")
        print(f"📉 Total Unrealized Losses (open): ${total_unrealized_loss:.2f}")
        print(f"📊 Combined Loss Impact: ${total_losses + total_unrealized_loss:.2f}")
        print(f"📊 Total impact on balance: {abs((total_losses + total_unrealized_loss)/total_balance*100):.1f}%")
    else:
        print("✅ No significant losses detected in recent trading")
        
except Exception as e:
    print(f"Error analyzing losses: {e}")
    import traceback
    traceback.print_exc()