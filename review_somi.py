#!/usr/bin/env python3
"""
SOMI Position Review
"""

import ccxt
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv('/app/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap'
    }
})

# Get SOMI position details
positions = exchange.fetch_positions()
somi_position = None

for pos in positions:
    if 'SOMI' in pos['symbol'] and pos['contracts'] > 0:
        somi_position = pos
        break

if somi_position:
    print('='*60)
    print(f'SOMI POSITION REVIEW - {datetime.now().strftime("%H:%M:%S")}')
    print('='*60)
    
    # Extract key metrics
    symbol = somi_position['symbol']
    side = somi_position['side']
    contracts = somi_position['contracts']
    entry_price = somi_position.get('entryPrice', 0)
    mark_price = somi_position.get('markPrice', 0)
    pnl = somi_position.get('unrealizedPnl', 0)
    pnl_pct = somi_position.get('percentage', 0)
    notional = abs(somi_position.get('notional', 0))
    margin = somi_position.get('initialMargin', 0)
    
    print(f'📊 Position Details:')
    print(f'   Symbol: {symbol}')
    print(f'   Side: {side.upper()}')
    print(f'   Contracts: {contracts}')
    print(f'   Notional Value: ${notional:.2f}')
    print(f'   Margin Used: ${margin:.2f}')
    print()
    
    print(f'💰 Price Analysis:')
    print(f'   Entry Price: ${entry_price:.6f}')
    print(f'   Current Price: ${mark_price:.6f}')
    price_diff = mark_price - entry_price
    price_diff_pct = (price_diff / entry_price) * 100 if entry_price > 0 else 0
    print(f'   Price Change: ${price_diff:.6f} ({price_diff_pct:+.2f}%)')
    print()
    
    print(f'📈 P&L Analysis:')
    print(f'   Unrealized PnL: ${pnl:.4f}')
    print(f'   PnL Percentage: {pnl_pct:.2f}%')
    
    # Risk assessment
    print()
    print(f'⚠️ Risk Assessment:')
    if pnl_pct < -20:
        print(f'   🔴 HIGH RISK - Down {abs(pnl_pct):.2f}%')
        print(f'   Action: Consider closing or averaging down')
    elif pnl_pct < -10:
        print(f'   🟡 MEDIUM RISK - Down {abs(pnl_pct):.2f}%')
        print(f'   Action: Monitor closely, prepare for averaging')
    elif pnl_pct < 0:
        print(f'   🟠 LOW RISK - Down {abs(pnl_pct):.2f}%')
        print(f'   Action: Normal volatility, hold position')
    else:
        print(f'   🟢 IN PROFIT - Up {pnl_pct:.2f}%')
        if pnl_pct > 2:
            print(f'   Action: Consider taking partial profits')
    
    # Recovery analysis
    print()
    print(f'🎯 Recovery Targets:')
    breakeven_move = ((entry_price - mark_price) / mark_price) * 100
    print(f'   Breakeven: ${entry_price:.6f} (needs {abs(breakeven_move):.2f}% move)')
    print(f'   +1% Target: ${entry_price * 1.01:.6f}')
    print(f'   +2% Target: ${entry_price * 1.02:.6f}')
    print(f'   +5% Target: ${entry_price * 1.05:.6f}')
    
    # Historical context from log
    print()
    print(f'📜 Recent History:')
    print(f'   Two positions today:')
    print(f'   1st: Entry @ $0.7962, closed with profit')
    print(f'   2nd: Entry @ $0.8009 (current position)')
    print(f'   Best PnL: +$0.92')
    print(f'   Current: ${pnl:.2f}')
    
else:
    print('No SOMI position found')

# Account status
balance = exchange.fetch_balance()
print()
print('-'*60)
print(f'Account Balance: ${balance["USDT"]["total"]:.2f}')