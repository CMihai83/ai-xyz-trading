#!/usr/bin/env python3
import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

exchange = ccxt.bitget({
    'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
    'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
    'password': '2609Luiza',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

print("=== Checking TA/USDT:USDT Position ===\n")

positions = exchange.fetch_positions()
ta_found = False

for pos in positions:
    if pos['symbol'] == 'TA/USDT:USDT' and pos['contracts'] > 0:
        ta_found = True
        print(f'TA Position on Exchange:')
        print(f'  Contracts: {pos["contracts"]}')
        print(f'  Side: {pos["side"]}')
        print(f'  Mark Price: ${pos.get("markPrice", 0)}')
        print(f'  Unrealized PNL: ${pos.get("unrealizedPnl", 0):.4f}')
        print(f'  Percentage: {pos.get("percentage", 0):.2f}%')
        
        # Check the orders history
        print("\n=== Recent TA Orders ===")
        try:
            orders = exchange.fetch_closed_orders('TA/USDT:USDT', limit=10)
            for order in orders[-5:]:  # Last 5 orders
                print(f"  {order['datetime']}: {order['side']} {order['amount']} @ ${order.get('price', 0)}")
                if order.get('info', {}).get('orderType') == 'stop_loss':
                    print(f"    ⚠️ STOP LOSS ORDER")
        except:
            print("  Could not fetch order history")

if not ta_found:
    print("❌ No active TA/USDT:USDT position found on exchange")