"""
AI-XYZ Prediction Model FINAL
Combines V2 simplicity with V5's Grok optimizations:
- V2-style indicator logic (proven to work)
- V5 volatility scaling
- Better target calculation from V2
- Weighted scoring from V5
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict


@dataclass
class PredictionResult:
    direction: str
    confidence: float
    target_15m: float
    target_30m: float
    target_60m: float
    range_low: float
    range_high: float
    bull_score: float
    bear_score: float
    net_score: float
    signals: Dict


class PredictionModelFinal:
    """
    Final optimized model combining V2 + V5 + Grok recommendations
    
    Key features:
    - Simple V2 indicators (EMA, RSI, VWAP, Slope)
    - Volatility-scaled thresholds from V5
    - Better target calculation (V2 style)
    - Low direction threshold for sensitivity
    """
    
    def calculate_atr(self, highs, lows, closes, period=14):
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        return np.mean(tr[-period:])
    
    def calculate_rsi(self, prices, period=14):
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100
        return 100 - (100 / (1 + avg_gain / avg_loss))
    
    def predict(self, df: pd.DataFrame, orderbook: Dict = None) -> PredictionResult:
        closes = df['c'].values
        highs = df['h'].values
        lows = df['l'].values
        volumes = df['v'].values
        current = closes[-1]
        
        # ATR and volatility scaling
        atr = self.calculate_atr(highs, lows, closes)
        atr_pct = atr / current * 100
        baseline_atr = 0.003 * current
        vol_scale = max(0.5, min(2.0, atr / baseline_atr))
        
        signals = {}
        bull_score = 0
        bear_score = 0
        
        # === 1. EMA CROSS (weight: 1.0) ===
        ema9 = pd.Series(closes).ewm(span=9).mean().iloc[-1]
        ema21 = pd.Series(closes).ewm(span=21).mean().iloc[-1]
        
        if ema9 > ema21:
            bull_score += 1
            signals['ema'] = 'BULLISH'
        else:
            bear_score += 1
            signals['ema'] = 'BEARISH'
        
        # === 2. RSI (weight: 0.5) ===
        rsi = self.calculate_rsi(closes)
        # Scaled thresholds
        ob = 60 / vol_scale
        os = 40 * vol_scale
        
        if rsi > 50:
            bull_score += 0.5
            if rsi > ob:
                bear_score += 0.3  # Overbought correction risk
                signals['rsi'] = f'OVERBOUGHT ({rsi:.0f})'
            else:
                signals['rsi'] = f'BULLISH ({rsi:.0f})'
        else:
            bear_score += 0.5
            if rsi < os:
                bull_score += 0.3  # Oversold bounce potential
                signals['rsi'] = f'OVERSOLD ({rsi:.0f})'
            else:
                signals['rsi'] = f'BEARISH ({rsi:.0f})'
        
        # === 3. VWAP (weight: 1.0) ===
        vwap = (df['c'] * df['v']).sum() / df['v'].sum()
        vwap_dist = (current - vwap) / vwap * 100
        
        if current > vwap:
            bull_score += 1
            signals['vwap'] = f'ABOVE ({vwap_dist:+.1f}%)'
        else:
            bear_score += 1
            signals['vwap'] = f'BELOW ({vwap_dist:+.1f}%)'
        
        # === 4. SLOPE (weight: 1.0) ===
        slope = np.polyfit(range(20), closes[-20:], 1)[0]
        slope_pct = slope / current * 1000  # Per 1000 candles
        
        if slope > 0:
            bull_score += 1
            signals['slope'] = f'UP ({slope_pct:+.2f})'
        else:
            bear_score += 1
            signals['slope'] = f'DOWN ({slope_pct:+.2f})'
        
        # === 5. MOMENTUM (extra signal) ===
        mom_5 = (closes[-1] / closes[-6] - 1) * 100
        if mom_5 > 0.3:
            bull_score += 0.5
            signals['momentum'] = f'BULLISH ({mom_5:+.2f}%)'
        elif mom_5 < -0.3:
            bear_score += 0.5
            signals['momentum'] = f'BEARISH ({mom_5:+.2f}%)'
        else:
            signals['momentum'] = f'FLAT ({mom_5:+.2f}%)'
        
        # === NET SCORE & DIRECTION ===
        net_score = bull_score - bear_score
        
        # Lower threshold (1.0) for sensitivity (was 1.5 in V2)
        if net_score > 1.0:
            direction = 'BULLISH'
            confidence = 55 + net_score * 10
        elif net_score < -1.0:
            direction = 'BEARISH'
            confidence = 55 + abs(net_score) * 10
        else:
            direction = 'NEUTRAL'
            confidence = 40 + abs(net_score) * 8
        
        confidence = min(85, confidence)
        
        # Order book adjustment
        if orderbook:
            bids = sum([b[1] for b in orderbook.get('bids', [])[:10]])
            asks = sum([a[1] for a in orderbook.get('asks', [])[:10]])
            if bids + asks > 0:
                imbalance = (bids - asks) / (bids + asks)
                signals['orderbook'] = f'{imbalance:+.2f}'
                if (direction == 'BULLISH' and imbalance > 0.25) or \
                   (direction == 'BEARISH' and imbalance < -0.25):
                    confidence = min(90, confidence + 8)
        
        # === TARGETS (V2 style - conservative) ===
        if direction == 'BULLISH':
            target_15m = current + atr * 0.5
            target_30m = current + atr * 1.0
            target_60m = current + atr * 1.5
        elif direction == 'BEARISH':
            target_15m = current - atr * 0.5
            target_30m = current - atr * 1.0
            target_60m = current - atr * 1.5
        else:
            target_15m = current
            target_30m = current
            target_60m = current
        
        # Range (V2 style)
        range_mult = 2.0
        
        signals['vol_scale'] = f'{vol_scale:.2f}x'
        signals['atr'] = f'{atr_pct:.3f}%'
        signals['bull'] = f'{bull_score:.1f}'
        signals['bear'] = f'{bear_score:.1f}'
        
        return PredictionResult(
            direction=direction,
            confidence=confidence,
            target_15m=target_15m,
            target_30m=target_30m,
            target_60m=target_60m,
            range_low=current - atr * range_mult,
            range_high=current + atr * range_mult,
            bull_score=bull_score,
            bear_score=bear_score,
            net_score=net_score,
            signals=signals
        )


if __name__ == '__main__':
    import ccxt
    from dotenv import dotenv_values
    
    env = dotenv_values('/root/ai_xyz/.env')
    
    exchange = ccxt.bitget({
        'apiKey': env.get('BITGET_API_KEY'),
        'secret': env.get('BITGET_API_SECRET'),
        'password': env.get('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })
    
    symbol = 'API3/USDT:USDT'
    ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=100)
    df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    orderbook = exchange.fetch_order_book(symbol, limit=20)
    
    model = PredictionModelFinal()
    result = model.predict(df, orderbook)
    
    print('=' * 70)
    print('       FINAL PREDICTION MODEL - API3/USDT')
    print('=' * 70)
    print(f'\nCurrent Price: ${df["c"].iloc[-1]:.4f}')
    print(f'\nDirection: {result.direction}')
    print(f'Confidence: {result.confidence:.1f}%')
    print(f'Scores: Bull={result.bull_score:.1f} Bear={result.bear_score:.1f} Net={result.net_score:+.1f}')
    print(f'\nTargets:')
    print(f'  15m: ${result.target_15m:.4f} ({(result.target_15m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'  30m: ${result.target_30m:.4f} ({(result.target_30m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'  60m: ${result.target_60m:.4f} ({(result.target_60m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'\nRange: ${result.range_low:.4f} - ${result.range_high:.4f}')
    print(f'\nSignals:')
    for k, v in result.signals.items():
        print(f'  {k}: {v}')
