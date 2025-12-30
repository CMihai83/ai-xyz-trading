#!/usr/bin/env python3
import ccxt
import random
from datetime import datetime

class SimpleVSAScanner:
    """Simple scanner focused on VSA (Volume Spread Analysis) signals"""
    
    def __init__(self, exchange):
        self.exchange = exchange
        
    def scan_for_opportunities(self):
        """Find opportunities based on volume and price action"""
        try:
            # Get top volume coins
            tickers = self.exchange.fetch_tickers()
            
            opportunities = []
            for symbol, ticker in tickers.items():
                if 'USDT' not in symbol or ':USDT' not in symbol:
                    continue
                    
                # Skip low volume
                volume = ticker.get('quoteVolume', 0)
                if volume < 500000:  # Min $500k volume
                    continue
                
                # Get price change
                change = ticker.get('percentage', 0)
                
                # VSA logic: High volume with small price change = accumulation/distribution
                volume_ratio = volume / 1000000  # Normalize to millions
                price_change_abs = abs(change)
                
                # VSA score: High volume with controlled price = strong signal
                if volume_ratio > 5 and price_change_abs < 10:
                    vsa_score = min(0.9, volume_ratio / 10)
                elif volume_ratio > 2:
                    vsa_score = min(0.7, volume_ratio / 15)
                else:
                    vsa_score = 0.3
                
                # Determine direction based on price action
                if change < -2:
                    direction = 'long'  # Oversold
                elif change > 2:
                    direction = 'short'  # Overbought
                else:
                    # Use volume pattern
                    direction = 'long' if change < 0 else 'short'
                
                # Calculate final score (VSA weighted)
                volatility_score = min(0.5, price_change_abs / 20)
                composite_score = vsa_score * 0.7 + volatility_score * 0.3
                
                if composite_score > 0.25:  # Low threshold to find opportunities
                    opportunities.append({
                        'symbol': symbol,
                        'direction': direction,
                        'score': composite_score,
                        'confidence': composite_score,
                        'leverage': min(10, int(5 + composite_score * 5)),
                        'volatility': price_change_abs,
                        'size_multiplier': 1.0,
                        'price_change_24h': change,
                        'volume': volume,
                        'vsa_score': vsa_score,
                        'reasoning': {
                            'vsa': vsa_score,
                            'volatility': volatility_score,
                            'volume_millions': volume_ratio,
                            'details': f"VSA Signal: Volume ${volume_ratio:.1f}M, Change {change:.1f}%"
                        }
                    })
            
            # Sort by score
            opportunities.sort(key=lambda x: x['score'], reverse=True)
            
            # Return top opportunities
            return opportunities[:5]
            
        except Exception as e:
            print(f"Scanner error: {e}")
            return []

if __name__ == "__main__":
    # Test the scanner
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
    
    scanner = SimpleVSAScanner(exchange)
    print("Scanning for VSA opportunities...")
    opportunities = scanner.scan_for_opportunities()
    
    print(f"\nFound {len(opportunities)} opportunities:")
    for opp in opportunities:
        print(f"  {opp['symbol']}: {opp['direction'].upper()} - Score: {opp['score']:.3f}")
        print(f"    VSA: {opp['vsa_score']:.2f}, Volume: ${opp['volume']/1e6:.1f}M, Change: {opp['price_change_24h']:.1f}%")