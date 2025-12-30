#!/usr/bin/env python3
"""Emergency averaging for TOSHI position at -37% loss"""

import ccxt
import time

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
    'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
    'password': '2609Luiza',
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# Get TOSHI position
positions = exchange.fetch_positions()
toshi_pos = None
for pos in positions:
    if 'TOSHI' in pos['symbol']:
        toshi_pos = pos
        break

if not toshi_pos:
    print("TOSHI position not found")
    exit()

print(f"TOSHI Position:")
print(f"  Current P&L: {toshi_pos['percentage']:.2f}%")
print(f"  Current size: {toshi_pos['contracts']}")
print(f"  Unrealized P&L: ${toshi_pos['unrealizedPnl']:.4f}")

# Calculate averaging size - double the current position
averaging_size = toshi_pos['contracts']  # Same size as current position
print(f"\nAveraging with {averaging_size} contracts")

# Get current ticker
ticker = exchange.fetch_ticker('TOSHI/USDT:USDT')
current_price = ticker['ask']
print(f"Current price: {current_price}")

try:
    # Place averaging order (SHORT position, so we SELL more)
    order = exchange.create_market_order(
        symbol='TOSHI/USDT:USDT',
        side='sell',  # SHORT position
        amount=averaging_size
    )
    print(f"\n✅ Averaging order placed: {order['id']}")
    print(f"   Amount: {order['amount']}")
    print(f"   Price: {order['price']}")
    
    # Wait and check new position
    time.sleep(3)
    new_positions = exchange.fetch_positions()
    for pos in new_positions:
        if 'TOSHI' in pos['symbol']:
            print(f"\n📊 Updated TOSHI position:")
            print(f"   New size: {pos['contracts']}")
            print(f"   New P&L: {pos['percentage']:.2f}%")
            print(f"   New unrealized: ${pos['unrealizedPnl']:.4f}")
            break
            
except Exception as e:
    print(f"❌ Error placing averaging order: {e}")