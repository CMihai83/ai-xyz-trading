#!/usr/bin/env python3
"""
Close all positions and open 5 high-volatility test positions
"""
import ccxt
import os
import time
import sys

def main():
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })

    print("=" * 60)
    print("STEP 1: CLOSING ALL CURRENT POSITIONS")
    print("=" * 60)
    sys.stdout.flush()

    positions = exchange.fetch_positions()
    open_positions = [p for p in positions if p['contracts'] > 0]

    print(f"Found {len(open_positions)} positions to close")
    sys.stdout.flush()

    for pos in open_positions:
        symbol = pos['symbol']
        side = pos['side']
        contracts = pos['contracts']
        close_side = 'sell' if side == 'long' else 'buy'

        try:
            order = exchange.create_market_order(
                symbol, close_side, contracts,
                params={'reduceOnly': True, 'marginCoin': 'USDT'}
            )
            print(f"  ✅ Closed {symbol}: {side} {contracts} contracts")
            sys.stdout.flush()
        except Exception as e:
            print(f"  ❌ Failed to close {symbol}: {e}")
            sys.stdout.flush()
        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("STEP 2: FINDING HIGH VOLATILITY COINS")
    print("=" * 60)
    sys.stdout.flush()

    # Load markets
    exchange.load_markets()

    # Get all USDT futures
    usdt_futures = [
        symbol for symbol, market in exchange.markets.items()
        if market.get('swap', False) and market.get('linear', False)
        and market.get('settle') == 'USDT' and market.get('active', True)
    ]

    print(f"Scanning {len(usdt_futures)} USDT futures for volatility...")
    sys.stdout.flush()

    # Fetch tickers
    tickers = exchange.fetch_tickers(usdt_futures[:100])

    # Calculate volatility (price change % in 24h)
    volatility_data = []
    for symbol, ticker in tickers.items():
        pct_change = ticker.get('percentage', 0) or 0
        volume = ticker.get('quoteVolume', 0) or 0
        last_price = ticker.get('last', 0) or 0

        # Only consider coins with decent volume (>$500k) and reasonable price
        if volume > 500000 and last_price > 0.0001:
            volatility_data.append({
                'symbol': symbol,
                'pct_change': abs(pct_change),
                'direction': 'long' if pct_change < 0 else 'short',  # Counter-trend
                'volume': volume,
                'price': last_price
            })

    # Sort by volatility (highest absolute % change)
    volatility_data.sort(key=lambda x: x['pct_change'], reverse=True)

    # Take top 5 most volatile
    top_volatile = volatility_data[:10]  # Get top 10 to have options

    print("\nTop 10 most volatile coins (24h):")
    for i, coin in enumerate(top_volatile):
        print(f"  {i+1}. {coin['symbol']}: {coin['pct_change']:.2f}% change, Vol: ${coin['volume']/1e6:.1f}M")
    sys.stdout.flush()

    print("\n" + "=" * 60)
    print("STEP 3: OPENING 5 TEST POSITIONS")
    print("=" * 60)
    sys.stdout.flush()

    # Select 5 diverse positions (mix of long/short, different volatility levels)
    selected = []

    # Pick from top volatile - mix directions
    for coin in top_volatile:
        if len(selected) >= 5:
            break
        # Skip if we already have this coin
        if coin['symbol'] in [s['symbol'] for s in selected]:
            continue
        selected.append(coin)

    # Position sizing: ~$8 margin each with 10x leverage = $80 notional
    margin_per_position = 2.0  # $2 margin each
    leverage = 10

    for coin in selected:
        symbol = coin['symbol']
        side = coin['direction']
        price = coin['price']

        # Calculate position size
        notional = margin_per_position * leverage  # $20 notional value
        amount = notional / price

        # Get market info for precision
        market = exchange.markets.get(symbol)
        if market:
            # Round to proper precision
            amount_precision = market.get('precision', {}).get('amount', 8)
            if isinstance(amount_precision, float):
                # Convert decimal precision to integer digits
                amount_precision = max(0, -int(round(amount_precision)))
            min_amount = market.get('limits', {}).get('amount', {}).get('min', 0) or 0.001
            amount = max(round(amount, int(amount_precision)), min_amount * 1.1)

        try:
            # Set leverage first
            try:
                exchange.set_leverage(leverage, symbol, params={'marginCoin': 'USDT', 'holdSide': side})
            except:
                pass  # Leverage might already be set

            # Open position
            order = exchange.create_market_order(
                symbol, 'buy' if side == 'long' else 'sell', amount,
                params={'marginCoin': 'USDT'}
            )
            print(f"  ✅ Opened {side.upper()} {symbol}: {amount} @ ~${price:.6f}")
            print(f"     Notional: ~${amount * price:.2f}, Margin: ~${amount * price / leverage:.2f}")
            sys.stdout.flush()
        except Exception as e:
            print(f"  ❌ Failed to open {symbol}: {e}")
            sys.stdout.flush()

        time.sleep(0.5)

    print("\n" + "=" * 60)
    print("STEP 4: VERIFYING NEW POSITIONS")
    print("=" * 60)
    sys.stdout.flush()

    time.sleep(1)
    positions = exchange.fetch_positions()
    open_positions = [p for p in positions if p['contracts'] > 0]

    print(f"\nNow have {len(open_positions)} open positions:")
    for p in open_positions:
        upnl = p.get('unrealizedPnl', 0) or 0
        entry = p.get('entryPrice', 0) or 0
        print(f"  {p['symbol']}: {p['side']} {p['contracts']} @ ${entry:.6f}, UPNL: ${upnl:.4f}")
    sys.stdout.flush()

    print("\n✅ Test positions ready! Monitor the system for:")
    print("  - Take Profit: Positions closing at +$0.15 UPNL")
    print("  - Averaging: Positions getting averaged at -25% drawdown")
    print("  - Surplus Dump: Averaged positions closing at profit")
    print("  - Stop Loss: Positions closing at max drawdown")
    sys.stdout.flush()

if __name__ == '__main__':
    main()
