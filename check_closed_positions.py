#!/usr/bin/env python3
import ccxt
import json
from datetime import datetime, timedelta

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': 'bg_90a87df4c4de9e10c893e7c30e91b74c',
    'secret': '973c3fc8797e086f95b2b37c7a5a67e1f63b2e968de969ad9c887d1e913c6795',
    'password': 'AlexGruber1710',
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

# Get trade history for last 24 hours
now = datetime.now()
yesterday = now - timedelta(days=1)
since = int(yesterday.timestamp() * 1000)

print('=== CHECKING CLOSED POSITIONS AND SURPLUS DUMP CONDITIONS ===')
print(f'Time range: {yesterday.strftime("%Y-%m-%d %H:%M")} to {now.strftime("%Y-%m-%d %H:%M")}\n')

try:
    # Fetch closed orders
    closed_orders = exchange.fetch_closed_orders(since=since, limit=500)
    
    print(f'Total closed orders found: {len(closed_orders)}')
    
    # Group orders by symbol to identify position closures
    positions = {}
    for order in closed_orders:
        if order['status'] == 'closed' and order['filled'] > 0:
            symbol = order['symbol']
            if symbol not in positions:
                positions[symbol] = {
                    'buys': [],
                    'sells': [],
                    'total_buy_volume': 0,
                    'total_sell_volume': 0,
                    'avg_buy_price': 0,
                    'avg_sell_price': 0
                }
            
            order_info = {
                'timestamp': order['timestamp'],
                'datetime': order['datetime'],
                'side': order['side'],
                'type': order['type'],
                'price': order['price'] or order['average'],
                'amount': order['amount'],
                'cost': order['cost']
            }
            
            if order['side'] == 'buy':
                positions[symbol]['buys'].append(order_info)
                positions[symbol]['total_buy_volume'] += order['amount']
            else:
                positions[symbol]['sells'].append(order_info)
                positions[symbol]['total_sell_volume'] += order['amount']
    
    # Analyze closed positions
    print('\n=== POSITION CLOSURE ANALYSIS ===')
    
    for symbol, data in positions.items():
        if data['buys'] and data['sells']:
            print(f'\n{symbol}:')
            
            # Calculate average prices
            total_buy_cost = sum(b['price'] * b['amount'] for b in data['buys'])
            total_sell_revenue = sum(s['price'] * s['amount'] for s in data['sells'])
            
            if data['total_buy_volume'] > 0:
                data['avg_buy_price'] = total_buy_cost / data['total_buy_volume']
            if data['total_sell_volume'] > 0:
                data['avg_sell_price'] = total_sell_revenue / data['total_sell_volume']
            
            # Determine if position was closed at profit or loss
            net_volume = data['total_buy_volume'] - data['total_sell_volume']
            
            print(f'  Buy orders: {len(data["buys"])} (Total: {data["total_buy_volume"]:.4f})')
            print(f'  Sell orders: {len(data["sells"])} (Total: {data["total_sell_volume"]:.4f})')
            print(f'  Avg buy price: ${data["avg_buy_price"]:.4f}')
            print(f'  Avg sell price: ${data["avg_sell_price"]:.4f}')
            
            # Check for potential surplus dump pattern
            if len(data['buys']) > 1:  # Multiple buys indicate averaging
                print(f'  ⚠️ AVERAGING DETECTED - {len(data["buys"])} buy orders')
                
                # Check sell pattern for surplus dump
                if len(data['sells']) > 1:
                    sell_times = sorted([s['timestamp'] for s in data['sells']])
                    sell_amounts = [s['amount'] for s in sorted(data['sells'], key=lambda x: x['timestamp'])]
                    
                    print(f'  📊 Sell pattern analysis:')
                    for i, sell in enumerate(sorted(data['sells'], key=lambda x: x['timestamp'])):
                        print(f'    Sell {i+1}: {sell["datetime"]} - {sell["amount"]:.4f} @ ${sell["price"]:.4f}')
                    
                    # Check if sells follow surplus dump pattern (partial sells at profit levels)
                    if data['avg_sell_price'] > data['avg_buy_price']:
                        profit_pct = ((data['avg_sell_price'] - data['avg_buy_price']) / data['avg_buy_price']) * 100
                        print(f'  ✅ Position closed in PROFIT: +{profit_pct:.2f}%')
                        
                        if len(data['sells']) >= 2:
                            print(f'  🎯 POSSIBLE SURPLUS DUMP - Multiple sells after averaging')
                    else:
                        loss_pct = ((data['avg_buy_price'] - data['avg_sell_price']) / data['avg_buy_price']) * 100
                        print(f'  ❌ Position closed at LOSS: -{loss_pct:.2f}%')
                        print(f'  ⚠️ REVIEW NEEDED: Position with averaging closed at loss')
                        print(f'     Should have triggered surplus dump if price recovered above entry')
            
            # Timeline analysis
            first_buy = min(data['buys'], key=lambda x: x['timestamp'])
            last_sell = max(data['sells'], key=lambda x: x['timestamp']) if data['sells'] else None
            
            if last_sell:
                position_duration = (last_sell['timestamp'] - first_buy['timestamp']) / (1000 * 60 * 60)
                print(f'  Position duration: {position_duration:.2f} hours')
                print(f'  Entry: {first_buy["datetime"]}')
                print(f'  Exit: {last_sell["datetime"]}')

except Exception as e:
    print(f'Error analyzing positions: {e}')
    import traceback
    traceback.print_exc()

# Fetch recent trades for P&L verification
print('\n=== REALIZED P&L VERIFICATION ===')
try:
    trades = exchange.fetch_my_trades(since=since, limit=500)
    
    pnl_by_symbol = {}
    for trade in trades:
        symbol = trade['symbol']
        if symbol not in pnl_by_symbol:
            pnl_by_symbol[symbol] = {
                'total_pnl': 0,
                'positive_trades': 0,
                'negative_trades': 0,
                'trades': []
            }
        
        # Extract realized PnL if available
        if trade.get('info'):
            info = trade['info']
            realized_pnl = float(info.get('realizedPnl', 0) or 0)
            if realized_pnl != 0:
                pnl_by_symbol[symbol]['total_pnl'] += realized_pnl
                if realized_pnl > 0:
                    pnl_by_symbol[symbol]['positive_trades'] += 1
                else:
                    pnl_by_symbol[symbol]['negative_trades'] += 1
                    
                pnl_by_symbol[symbol]['trades'].append({
                    'datetime': trade['datetime'],
                    'side': trade['side'],
                    'price': trade['price'],
                    'amount': trade['amount'],
                    'realized_pnl': realized_pnl
                })
    
    # Print P&L summary
    total_pnl = 0
    for symbol, data in pnl_by_symbol.items():
        if data['trades']:
            total_pnl += data['total_pnl']
            status = '✅' if data['total_pnl'] > 0 else '❌'
            print(f'\n{symbol}: {status} ${data["total_pnl"]:.4f}')
            print(f'  Profitable trades: {data["positive_trades"]}')
            print(f'  Losing trades: {data["negative_trades"]}')
    
    print(f'\n=== TOTAL P&L (24h): ${total_pnl:.4f} ===')
    
except Exception as e:
    print(f'Error fetching P&L data: {e}')

print('\n=== SURPLUS DUMP COMPLIANCE CHECK ===')
print('Rules for surplus dump activation:')
print('1. Position must have averaging steps (multiple buys)')
print('2. Price must recover above weighted average entry')
print('3. System should dump 50% at 85% of peak, 50% at 50% of peak')
print('\nPositions requiring review are marked with ⚠️ above')