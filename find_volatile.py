#!/usr/bin/env python3
import ccxt
import os
from dotenv import load_dotenv

load_dotenv('.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

# Get top volatile coins
tickers = exchange.fetch_tickers()
volatile = []
for symbol, ticker in tickers.items():
    if 'USDT:USDT' in symbol and ticker.get('percentage'):
        volatile.append({
            'symbol': symbol,
            'change': abs(ticker['percentage']),
            'volume': ticker.get('quoteVolume', 0),
            'direction': 'UP' if ticker['percentage'] > 0 else 'DOWN'
        })

# Sort by volatility
volatile.sort(key=lambda x: x['change'], reverse=True)

print('Top 20 Most Volatile Coins (by 24h change):')
print('='*60)
for i, coin in enumerate(volatile[:20], 1):
    print(f"{i:2}. {coin['symbol']:20} {coin['change']:6.2f}% {coin['direction']:4} Vol: ${coin['volume']/1e6:6.1f}M")

# Find high leverage coins with good volatility
print('\nHigh Leverage + Volatility Candidates:')
print('='*60)
for coin in volatile[:30]:
    market = exchange.markets.get(coin['symbol'])
    if market:
        info = market.get('info', {})
        max_leverage = float(info.get('maxLever', 0))
        if max_leverage >= 50 and coin['change'] > 5:
            print(f"{coin['symbol']:20} Lev: {max_leverage:3.0f}x Change: {coin['change']:6.2f}% {coin['direction']}")