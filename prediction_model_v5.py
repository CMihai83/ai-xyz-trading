"""
AI-XYZ Prediction Model V5
Based on Grok's recommendations:
1. Volatility-scaled thresholds
2. Weighted scoring (not strict confluence)
3. Sensitive to small moves (0.5-2%)
4. Adaptive to low-vol conditions
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict
from dataclasses import dataclass


@dataclass
class PredictionResult:
    direction: str
    confidence: float
    target_15m: float
    target_30m: float
    target_60m: float
    range_low: float
    range_high: float
    total_score: float
    signals: Dict


class PredictionModelV5:
    """
    Grok-optimized prediction model for low-volatility crypto markets
    
    Key changes from V4:
    - Weighted scoring (not strict confluence)
    - Volatility-scaled thresholds
    - Lower thresholds for RSI (40/60 instead of 30/70)
    - Smaller direction threshold (0.5 vs 1.5)
    """
    
    def __init__(self):
        # Weights from Grok's recommendation
        self.weights = {
            'ema_cross': 0.4,
            'rsi': 0.3,
            'vwap': 0.2,
            'slope': 0.1
        }
        # Thresholds (lower for low-vol markets)
        self.direction_threshold = 0.3  # Was 0.5, lowered for sensitivity
        
    def calculate_atr(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        """Calculate Average True Range"""
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        return np.mean(tr[-period:])
    
    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100
        return 100 - (100 / (1 + avg_gain / avg_loss))
    
    def predict(self, df: pd.DataFrame, orderbook: Dict = None) -> PredictionResult:
        """
        V5 Prediction with Grok's weighted scoring approach
        """
        closes = df['c'].values
        highs = df['h'].values
        lows = df['l'].values
        volumes = df['v'].values
        current = closes[-1]
        
        # ATR for volatility scaling
        atr = self.calculate_atr(highs, lows, closes)
        atr_pct = atr / current * 100
        
        # Average ATR for normalization (baseline ~0.3% for typical crypto)
        baseline_atr = 0.003 * current  # 0.3%
        vol_scale = max(0.5, min(2.0, atr / baseline_atr))  # Cap scaling between 0.5x and 2x
        
        signals = {}
        
        # === 1. EMA CROSS (weight: 0.4) ===
        ema9 = pd.Series(closes).ewm(span=9).mean().iloc[-1]
        ema21 = pd.Series(closes).ewm(span=21).mean().iloc[-1]
        
        if ema9 > ema21:
            ema_signal = 1  # Bullish
            signals['ema_cross'] = f'BULLISH (9:{ema9:.4f} > 21:{ema21:.4f})'
        else:
            ema_signal = -1  # Bearish
            signals['ema_cross'] = f'BEARISH (9:{ema9:.4f} < 21:{ema21:.4f})'
        
        # === 2. RSI WITH SCALED THRESHOLDS (weight: 0.3) ===
        rsi = self.calculate_rsi(closes)
        
        # Grok's recommendation: 40/60 thresholds scaled by volatility
        overbought = 60 / vol_scale  # Lower in low-vol
        oversold = 40 * vol_scale    # Higher in low-vol
        
        if rsi > overbought:
            rsi_signal = -1  # Bearish (overbought)
            signals['rsi'] = f'BEARISH (RSI:{rsi:.1f} > {overbought:.1f})'
        elif rsi < oversold:
            rsi_signal = 1   # Bullish (oversold)
            signals['rsi'] = f'BULLISH (RSI:{rsi:.1f} < {oversold:.1f})'
        else:
            rsi_signal = 0   # Neutral
            signals['rsi'] = f'NEUTRAL (RSI:{rsi:.1f})'
        
        # === 3. VWAP WITH 0.5% THRESHOLD (weight: 0.2) ===
        vwap = (df['c'] * df['v']).sum() / df['v'].sum()
        vwap_pct_diff = (current - vwap) / vwap * 100
        
        # 0.5% threshold scaled by volatility
        vwap_threshold = 0.5 / vol_scale
        
        if vwap_pct_diff > vwap_threshold:
            vwap_signal = 1  # Bullish (above VWAP)
            signals['vwap'] = f'BULLISH ({vwap_pct_diff:+.2f}% above VWAP)'
        elif vwap_pct_diff < -vwap_threshold:
            vwap_signal = -1  # Bearish (below VWAP)
            signals['vwap'] = f'BEARISH ({vwap_pct_diff:+.2f}% below VWAP)'
        else:
            vwap_signal = 0
            signals['vwap'] = f'NEUTRAL ({vwap_pct_diff:+.2f}%)'
        
        # === 4. SLOPE WITH SCALED THRESHOLD (weight: 0.1) ===
        slope = np.polyfit(range(10), closes[-10:], 1)[0]
        slope_pct = slope / current * 100 * 10  # Per 10 candles
        
        # 0.1% per period threshold scaled
        slope_threshold = 0.1 / vol_scale
        
        if slope_pct > slope_threshold:
            slope_signal = 1  # Bullish
            signals['slope'] = f'BULLISH ({slope_pct:+.3f}%/10)'
        elif slope_pct < -slope_threshold:
            slope_signal = -1  # Bearish
            signals['slope'] = f'BEARISH ({slope_pct:+.3f}%/10)'
        else:
            slope_signal = 0
            signals['slope'] = f'NEUTRAL ({slope_pct:+.3f}%/10)'
        
        # === WEIGHTED TOTAL SCORE ===
        total_score = (
            ema_signal * self.weights['ema_cross'] +
            rsi_signal * self.weights['rsi'] +
            vwap_signal * self.weights['vwap'] +
            slope_signal * self.weights['slope']
        )
        
        signals['total_score'] = f'{total_score:+.2f}'
        signals['vol_scale'] = f'{vol_scale:.2f}x'
        signals['atr_pct'] = f'{atr_pct:.3f}%'
        
        # === DIRECTION DECISION ===
        # Lower threshold (0.3) for sensitivity to small moves
        if total_score > self.direction_threshold:
            direction = 'BULLISH'
            confidence = 50 + abs(total_score) * 40
        elif total_score < -self.direction_threshold:
            direction = 'BEARISH'
            confidence = 50 + abs(total_score) * 40
        else:
            direction = 'NEUTRAL'
            confidence = 40 + abs(total_score) * 20
        
        confidence = min(85, confidence)
        
        # Order book adjustment
        if orderbook:
            bids = sum([b[1] for b in orderbook.get('bids', [])[:10]])
            asks = sum([a[1] for a in orderbook.get('asks', [])[:10]])
            if bids + asks > 0:
                imbalance = (bids - asks) / (bids + asks)
                signals['orderbook'] = f'{imbalance:+.2f}'
                
                # Boost confidence if orderbook aligns
                if (direction == 'BULLISH' and imbalance > 0.2) or \
                   (direction == 'BEARISH' and imbalance < -0.2):
                    confidence = min(90, confidence + 10)
        
        # === TARGETS ===
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
        
        # Range
        range_mult = 2.0 / vol_scale  # Tighter in low-vol
        
        return PredictionResult(
            direction=direction,
            confidence=confidence,
            target_15m=target_15m,
            target_30m=target_30m,
            target_60m=target_60m,
            range_low=current - atr * range_mult,
            range_high=current + atr * range_mult,
            total_score=total_score,
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
    
    model = PredictionModelV5()
    result = model.predict(df, orderbook)
    
    print('=' * 70)
    print('       PREDICTION MODEL V5 (Grok-Optimized)')
    print('=' * 70)
    print(f'\nCurrent Price: ${df["c"].iloc[-1]:.4f}')
    print(f'\nDirection: {result.direction}')
    print(f'Confidence: {result.confidence:.1f}%')
    print(f'Total Score: {result.total_score:+.2f}')
    print(f'\nTargets:')
    print(f'  15m: ${result.target_15m:.4f} ({(result.target_15m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'  30m: ${result.target_30m:.4f} ({(result.target_30m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'  60m: ${result.target_60m:.4f} ({(result.target_60m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'\nExpected Range: ${result.range_low:.4f} - ${result.range_high:.4f}')
    print(f'\nSignals:')
    for k, v in result.signals.items():
        print(f'  {k}: {v}')
