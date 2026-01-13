"""
AI-XYZ Prediction Model V4
Fixes from V3 analysis:
1. Better quiet/ranging market handling
2. Confidence-based signal filtering
3. Improved divergence detection
4. Adaptive thresholds based on volatility
5. Trend persistence measurement
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Tuple
from dataclasses import dataclass
from enum import Enum

class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    VOLATILE = "volatile"
    QUIET = "quiet"

@dataclass
class PredictionResult:
    direction: str
    confidence: float
    target_15m: float
    target_30m: float
    target_60m: float
    range_low: float
    range_high: float
    regime: MarketRegime
    signals: Dict
    score_breakdown: Dict

class PredictionModelV4:
    """
    V4 Improvements:
    - Conservative in quiet markets (bias toward NEUTRAL)
    - Require signal confluence for directional calls
    - Volume confirmation required
    - Trend persistence check
    """
    
    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100
        return 100 - (100 / (1 + avg_gain / avg_loss))
    
    def detect_regime(self, df: pd.DataFrame) -> Tuple[MarketRegime, float]:
        """Detect market regime with confidence"""
        closes = df['c'].values
        highs = df['h'].values
        lows = df['l'].values
        
        # ATR-based volatility
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:])
        atr_pct = atr / closes[-1] * 100
        
        # Trend via regression
        slope, _, r_value, _, _ = stats.linregress(range(20), closes[-20:])
        trend_strength = r_value ** 2  # R-squared
        
        # Recent range compression
        range_20 = (highs[-20:].max() - lows[-20:].min()) / closes[-1] * 100
        
        if atr_pct > 1.5:
            return MarketRegime.VOLATILE, 0.8
        elif atr_pct < 0.25 or range_20 < 2:
            return MarketRegime.QUIET, 0.3  # Low confidence in quiet markets
        elif trend_strength > 0.6:
            if slope > 0:
                return MarketRegime.TRENDING_UP, trend_strength
            else:
                return MarketRegime.TRENDING_DOWN, trend_strength
        else:
            return MarketRegime.RANGING, 0.5
    
    def measure_trend_persistence(self, closes: np.ndarray) -> Dict:
        """Measure how persistent the current trend is"""
        # Count consecutive up/down moves
        changes = np.diff(closes[-20:])
        up_count = sum(1 for c in changes if c > 0)
        down_count = sum(1 for c in changes if c < 0)
        
        # Measure trend consistency
        if up_count > 12:
            persistence = 'STRONG_UP'
            score = (up_count - 10) / 10
        elif down_count > 12:
            persistence = 'STRONG_DOWN'
            score = (down_count - 10) / 10
        else:
            persistence = 'WEAK'
            score = 0
        
        # Check for reversals
        recent_changes = changes[-5:]
        recent_up = sum(1 for c in recent_changes if c > 0)
        reversing = (up_count > down_count and recent_up < 2) or \
                    (down_count > up_count and recent_up > 3)
        
        return {
            'persistence': persistence,
            'score': score,
            'reversing': reversing,
            'up_count': up_count,
            'down_count': down_count
        }
    
    def volume_confirmation(self, df: pd.DataFrame) -> Dict:
        """Check if volume confirms price action"""
        closes = df['c'].values
        volumes = df['v'].values
        
        # Volume trend
        vol_sma = np.mean(volumes[-20:])
        vol_recent = np.mean(volumes[-5:])
        vol_expanding = vol_recent > vol_sma * 1.2
        vol_contracting = vol_recent < vol_sma * 0.8
        
        # Volume-price alignment
        price_up = closes[-1] > closes[-5]
        vol_up_moves = sum(volumes[i] for i in range(-5, 0) if closes[i] > closes[i-1])
        vol_down_moves = sum(volumes[i] for i in range(-5, 0) if closes[i] < closes[i-1])
        
        if vol_up_moves > 0 or vol_down_moves > 0:
            vol_bias = (vol_up_moves - vol_down_moves) / (vol_up_moves + vol_down_moves)
        else:
            vol_bias = 0
        
        # Confirmation
        bullish_confirmed = price_up and vol_bias > 0.2 and vol_expanding
        bearish_confirmed = not price_up and vol_bias < -0.2 and vol_expanding
        
        return {
            'vol_expanding': vol_expanding,
            'vol_contracting': vol_contracting,
            'vol_bias': vol_bias,
            'bullish_confirmed': bullish_confirmed,
            'bearish_confirmed': bearish_confirmed
        }
    
    def calculate_signal_confluence(self, df: pd.DataFrame) -> Dict:
        """Calculate how many signals align in the same direction"""
        closes = df['c'].values
        current = closes[-1]
        
        signals = {
            'bullish': [],
            'bearish': [],
            'neutral': []
        }
        
        # 1. EMA Cross
        ema9 = pd.Series(closes).ewm(span=9).mean().iloc[-1]
        ema21 = pd.Series(closes).ewm(span=21).mean().iloc[-1]
        if ema9 > ema21 * 1.001:  # 0.1% buffer
            signals['bullish'].append('EMA_CROSS')
        elif ema9 < ema21 * 0.999:
            signals['bearish'].append('EMA_CROSS')
        else:
            signals['neutral'].append('EMA_CROSS')
        
        # 2. RSI
        rsi = self.calculate_rsi(closes)
        if rsi > 55:
            signals['bullish'].append('RSI')
        elif rsi < 45:
            signals['bearish'].append('RSI')
        else:
            signals['neutral'].append('RSI')
        
        # 3. Price vs VWAP
        vwap = (df['c'] * df['v']).sum() / df['v'].sum()
        if current > vwap * 1.002:
            signals['bullish'].append('VWAP')
        elif current < vwap * 0.998:
            signals['bearish'].append('VWAP')
        else:
            signals['neutral'].append('VWAP')
        
        # 4. Recent momentum
        mom_5 = (closes[-1] / closes[-6] - 1) * 100
        if mom_5 > 0.3:
            signals['bullish'].append('MOMENTUM')
        elif mom_5 < -0.3:
            signals['bearish'].append('MOMENTUM')
        else:
            signals['neutral'].append('MOMENTUM')
        
        # 5. Slope
        slope = np.polyfit(range(10), closes[-10:], 1)[0]
        slope_pct = slope / closes[-1] * 100 * 10  # per 10 candles
        if slope_pct > 0.2:
            signals['bullish'].append('SLOPE')
        elif slope_pct < -0.2:
            signals['bearish'].append('SLOPE')
        else:
            signals['neutral'].append('SLOPE')
        
        # 6. Higher highs / Lower lows
        recent_highs = df['h'].values[-10:]
        recent_lows = df['l'].values[-10:]
        hh = recent_highs[-1] > recent_highs[-5:-1].max()
        ll = recent_lows[-1] < recent_lows[-5:-1].min()
        hl = recent_lows[-1] > recent_lows[-5:-1].min()
        lh = recent_highs[-1] < recent_highs[-5:-1].max()
        
        if hh and hl:
            signals['bullish'].append('STRUCTURE')
        elif ll and lh:
            signals['bearish'].append('STRUCTURE')
        else:
            signals['neutral'].append('STRUCTURE')
        
        bull_count = len(signals['bullish'])
        bear_count = len(signals['bearish'])
        neutral_count = len(signals['neutral'])
        total = bull_count + bear_count + neutral_count
        
        # Confluence score
        if bull_count >= 4:
            confluence = 'STRONG_BULL'
            score = bull_count / total
        elif bear_count >= 4:
            confluence = 'STRONG_BEAR'
            score = bear_count / total
        elif bull_count >= 3 and bear_count <= 1:
            confluence = 'MODERATE_BULL'
            score = bull_count / total * 0.8
        elif bear_count >= 3 and bull_count <= 1:
            confluence = 'MODERATE_BEAR'
            score = bear_count / total * 0.8
        else:
            confluence = 'MIXED'
            score = 0.3
        
        return {
            'bullish': signals['bullish'],
            'bearish': signals['bearish'],
            'neutral': signals['neutral'],
            'bull_count': bull_count,
            'bear_count': bear_count,
            'confluence': confluence,
            'score': score,
            'rsi': rsi,
            'vwap': vwap,
            'mom_5': mom_5
        }
    
    def predict(self, df: pd.DataFrame, orderbook: Dict = None) -> PredictionResult:
        """V4 Prediction with conservative approach"""
        closes = df['c'].values
        highs = df['h'].values
        lows = df['l'].values
        current = closes[-1]
        
        # ATR for targets/ranges
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:])
        
        # Get all analyses
        regime, regime_confidence = self.detect_regime(df)
        trend_pers = self.measure_trend_persistence(closes)
        vol_conf = self.volume_confirmation(df)
        confluence = self.calculate_signal_confluence(df)
        
        signals = {
            'regime': regime.value,
            'regime_conf': f'{regime_confidence:.0%}',
            'trend_pers': trend_pers['persistence'],
            'vol_confirmed': vol_conf['bullish_confirmed'] or vol_conf['bearish_confirmed'],
            'confluence': confluence['confluence'],
            'bull_signals': confluence['bullish'],
            'bear_signals': confluence['bearish'],
            'rsi': confluence['rsi'],
            'mom_5': confluence['mom_5']
        }
        
        # === V4 DECISION LOGIC ===
        
        # In QUIET or RANGING markets with weak confluence -> NEUTRAL
        if regime in [MarketRegime.QUIET, MarketRegime.RANGING]:
            if confluence['confluence'] == 'MIXED':
                direction = 'NEUTRAL'
                confidence = 40
            elif confluence['confluence'] in ['STRONG_BULL', 'MODERATE_BULL']:
                # Need volume confirmation in quiet markets
                if vol_conf['bullish_confirmed'] or confluence['bull_count'] >= 5:
                    direction = 'BULLISH'
                    confidence = 50 + confluence['score'] * 20
                else:
                    direction = 'NEUTRAL'
                    confidence = 45
            elif confluence['confluence'] in ['STRONG_BEAR', 'MODERATE_BEAR']:
                if vol_conf['bearish_confirmed'] or confluence['bear_count'] >= 5:
                    direction = 'BEARISH'
                    confidence = 50 + confluence['score'] * 20
                else:
                    direction = 'NEUTRAL'
                    confidence = 45
            else:
                direction = 'NEUTRAL'
                confidence = 40
        
        # In TRENDING markets - follow trend unless reversing
        elif regime in [MarketRegime.TRENDING_UP, MarketRegime.TRENDING_DOWN]:
            if regime == MarketRegime.TRENDING_UP:
                if trend_pers['reversing']:
                    direction = 'NEUTRAL'
                    confidence = 50
                else:
                    direction = 'BULLISH'
                    confidence = 60 + regime_confidence * 20
            else:
                if trend_pers['reversing']:
                    direction = 'NEUTRAL'
                    confidence = 50
                else:
                    direction = 'BEARISH'
                    confidence = 60 + regime_confidence * 20
        
        # In VOLATILE markets - require strong confluence
        else:  # VOLATILE
            if confluence['confluence'] == 'STRONG_BULL':
                direction = 'BULLISH'
                confidence = 55 + confluence['score'] * 25
            elif confluence['confluence'] == 'STRONG_BEAR':
                direction = 'BEARISH'
                confidence = 55 + confluence['score'] * 25
            else:
                direction = 'NEUTRAL'
                confidence = 35  # Low confidence in volatile + mixed
        
        # Order book adjustment if available
        if orderbook:
            bids = sum([b[1] for b in orderbook.get('bids', [])[:10]])
            asks = sum([a[1] for a in orderbook.get('asks', [])[:10]])
            if bids + asks > 0:
                imbalance = (bids - asks) / (bids + asks)
                signals['orderbook_imbalance'] = f'{imbalance:.2f}'
                
                # Only adjust if strong imbalance aligns with direction
                if direction == 'BULLISH' and imbalance > 0.3:
                    confidence = min(85, confidence + 10)
                elif direction == 'BEARISH' and imbalance < -0.3:
                    confidence = min(85, confidence + 10)
                elif direction != 'NEUTRAL' and abs(imbalance) > 0.3:
                    # Imbalance against direction -> reduce confidence
                    if (direction == 'BULLISH' and imbalance < -0.2) or \
                       (direction == 'BEARISH' and imbalance > 0.2):
                        confidence = max(40, confidence - 15)
        
        # Calculate targets
        if direction == 'BULLISH':
            mult = 1.0 + (confidence - 50) / 100
            target_15m = current + atr * 0.4 * mult
            target_30m = current + atr * 0.8 * mult
            target_60m = current + atr * 1.2 * mult
        elif direction == 'BEARISH':
            mult = 1.0 + (confidence - 50) / 100
            target_15m = current - atr * 0.4 * mult
            target_30m = current - atr * 0.8 * mult
            target_60m = current - atr * 1.2 * mult
        else:
            target_15m = current
            target_30m = current
            target_60m = current
        
        # Range based on regime
        if regime == MarketRegime.VOLATILE:
            range_mult = 2.5
        elif regime == MarketRegime.QUIET:
            range_mult = 1.2
        else:
            range_mult = 1.8
        
        return PredictionResult(
            direction=direction,
            confidence=confidence,
            target_15m=target_15m,
            target_30m=target_30m,
            target_60m=target_60m,
            range_low=current - atr * range_mult,
            range_high=current + atr * range_mult,
            regime=regime,
            signals=signals,
            score_breakdown={
                'regime_conf': regime_confidence,
                'confluence_score': confluence['score'],
                'bull_count': confluence['bull_count'],
                'bear_count': confluence['bear_count'],
                'vol_confirmed': vol_conf['bullish_confirmed'] or vol_conf['bearish_confirmed']
            }
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
    
    model = PredictionModelV4()
    result = model.predict(df, orderbook)
    
    print('=' * 70)
    print('       PREDICTION MODEL V4 - API3/USDT')
    print('=' * 70)
    print(f'\nCurrent Price: ${df["c"].iloc[-1]:.4f}')
    print(f'\nDirection: {result.direction}')
    print(f'Confidence: {result.confidence:.1f}%')
    print(f'Regime: {result.regime.value}')
    print(f'\nTargets:')
    print(f'  15m: ${result.target_15m:.4f} ({(result.target_15m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'  30m: ${result.target_30m:.4f} ({(result.target_30m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'  60m: ${result.target_60m:.4f} ({(result.target_60m/df["c"].iloc[-1]-1)*100:+.2f}%)')
    print(f'\nExpected Range: ${result.range_low:.4f} - ${result.range_high:.4f}')
    print(f'\nSignals:')
    for k, v in result.signals.items():
        print(f'  {k}: {v}')
