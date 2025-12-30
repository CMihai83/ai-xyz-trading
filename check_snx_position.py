import ccxt
import os
from dotenv import load_dotenv

load_dotenv()

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_SECRET'),
    'password': os.getenv('BITGET_PASSWORD'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# Check SNX position
try:
    positions = exchange.fetch_positions(['SNX/USDT:USDT'])
    if positions:
        pos = positions[0]
        print(f'SNX/USDT:USDT Position:')
        print(f'  Contracts: {pos["contracts"]}')
        print(f'  Side: {pos["side"]}')
        print(f'  Entry Price: {pos.get("markPrice", "N/A")}')
        print(f'  Current Price: {pos.get("markPrice", "N/A")}')
        print(f'  UPNL: ${pos.get("unrealizedPnl", 0):.2f} ({pos.get("percentage", 0):.1f}%)')
        print(f'  Margin: ${pos.get("initialMargin", 0):.2f}')
        print(f'  Maintenance Margin: ${pos.get("maintenanceMargin", 0):.2f}')
        if pos.get('marginRatio'):
            print(f'  Margin Ratio: {pos["marginRatio"]:.1%}')
        print(f'  Liquidation Price: {pos.get("liquidationPrice", "N/A")}')
    else:
        print('No SNX position found on exchange')

    # Check order history
    print('\nChecking recent SNX orders...')
    orders = exchange.fetch_closed_orders('SNX/USDT:USDT', limit=10)
    for order in orders[-5:]:
        print(f'  {order["datetime"]}: {order["side"]} {order["amount"]} @ {order["price"]} - {order["status"]}')

except Exception as e:
    print(f'Error checking position: {e}')