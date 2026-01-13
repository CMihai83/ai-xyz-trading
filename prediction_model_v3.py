"""
AI-XYZ Prediction Model V3
Improved prediction with:
- Volume-Price Analysis (VPA)
- Momentum Divergence Detection
- Market Microstructure Signals
- Adaptive Volatility Regimes
- Order Book Imbalance
- Multi-Timeframe Confluence
"""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, Tuple, List
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

class PredictionModelV3:
    """Enhanced prediction model with multiple signal sources"""
    
    def __init__(self):
        self.weights = {
            'trend': 1.5,
            'momentum': 1.2,
            'volume': 1.0,
            'mean_reversion': 1.3,
            'microstructure': 0.8,
            'divergence': 1.4,
            'regime': 1.0
        }
    
    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI"""
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    def calculate_macd(self, prices: np.ndarray) -> Tuple[float, float, float]:
        """Calculate MACD, Signal, Histogram"""
        ema12 = pd.Series(prices).ewm(span=12).mean().iloc[-1]
        ema26 = pd.Series(prices).ewm(span=26).mean().iloc[-1]
        macd = ema12 - ema26
        signal = pd.Series(prices).ewm(span=12).mean().ewm(span=9).mean().iloc[-1] - \
                 pd.Series(prices).ewm(span=26).mean().ewm(span=9).mean().iloc[-1]
        histogram = macd - signal
        return macd, signal, histogram
    
    def calculate_bollinger(self, prices: np.ndarray, period: int = 20) -> Tuple[float, float, float]:
        """Calculate Bollinger Bands"""
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        upper = sma + (2 * std)
        lower = sma - (2 * std)
        position = (prices[-1] - lower) / (upper - lower) if upper != lower else 0.5
        return upper, lower, position
    
    def detect_divergence(self, prices: np.ndarray, indicator: np.ndarray) -> str:
        """Detect bullish/bearish divergence"""
        price_slope = np.polyfit(range(len(prices[-10:])), prices[-10:], 1)[0]
        ind_slope = np.polyfit(range(len(indicator[-10:])), indicator[-10:], 1)[0]
        
        # Bullish divergence: price falling, indicator rising
        if price_slope < 0 and ind_slope > 0:
            return 'BULLISH'
        # Bearish divergence: price rising, indicator falling
        if price_slope > 0 and ind_slope < 0:
            return 'BEARISH'
        return 'NONE'
    
    def detect_regime(self, df: pd.DataFrame) -> MarketRegime:
        """Detect current market regime"""
        closes = df['c'].values
        highs = df['h'].values
        lows = df['l'].values
        
        # Calculate ATR for volatility
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:])
        atr_pct = atr / closes[-1] * 100
        
        # Calculate trend strength
        slope, _, r_value, _, _ = stats.linregress(range(20), closes[-20:])
        trend_strength = abs(r_value)
        
        # Determine regime
        if atr_pct > 1.5:  # High volatility
            return MarketRegime.VOLATILE
        elif atr_pct < 0.3:  # Very low volatility
            return MarketRegime.QUIET
        elif trend_strength > 0.7 and slope > 0:
            return MarketRegime.TRENDING_UP
        elif trend_strength > 0.7 and slope < 0:
            return MarketRegime.TRENDING_DOWN
        else:
            return MarketRegime.RANGING
    
    def volume_price_analysis(self, df: pd.DataFrame) -> Dict:
        """Analyze volume-price relationship"""
        closes = df['c'].values
        volumes = df['v'].values
        
        # Volume trend
        vol_sma = np.mean(volumes[-20:])
        vol_recent = np.mean(volumes[-5:])
        vol_ratio = vol_recent / vol_sma if vol_sma > 0 else 1
        
        # Volume-weighted direction
        up_vol = sum(volumes[i] for i in range(-10, 0) if closes[i] > closes[i-1])
        down_vol = sum(volumes[i] for i in range(-10, 0) if closes[i] < closes[i-1])
        vol_direction = (up_vol - down_vol) / (up_vol + down_vol) if (up_vol + down_vol) > 0 else 0
        
        # Accumulation/Distribution
        clv = ((closes - df['l'].values) - (df['h'].values - closes)) / \
              (df['h'].values - df['l'].values + 0.0001)
        ad_line = np.cumsum(clv[-20:] * volumes[-20:])
        ad_slope = np.polyfit(range(len(ad_line)), ad_line, 1)[0]
        
        return {
            'vol_ratio': vol_ratio,
            'vol_direction': vol_direction,
            'ad_slope': ad_slope,
            'accumulating': ad_slope > 0 and vol_direction > 0,
            'distributing': ad_slope < 0 and vol_direction < 0
        }
    
    def calculate_support_resistance(self, df: pd.DataFrame) -> Dict:
        """Calculate dynamic support/resistance levels"""
        highs = df['h'].values[-50:]
        lows = df['l'].values[-50:]
        closes = df['c'].values
        current = closes[-1]
        
        # Pivot points
        pivot = (highs.max() + lows.min() + current) / 3
        r1 = 2 * pivot - lows.min()
        r2 = pivot + (highs.max() - lows.min())
        s1 = 2 * pivot - highs.max()
        s2 = pivot - (highs.max() - lows.min())
        
        # Recent swing levels
        swing_high = highs[-20:].max()
        swing_low = lows[-20:].min()
        
        # Distance to levels
        dist_to_resistance = (min(r1, swing_high) - current) / current * 100
        dist_to_support = (current - max(s1, swing_low)) / current * 100
        
        return {
            'pivot': pivot,
            'r1': r1, 'r2': r2,
            's1': s1, 's2': s2,
            'swing_high': swing_high,
            'swing_low': swing_low,
            'dist_resistance': dist_to_resistance,
            'dist_support': dist_to_support,
            'near_resistance': dist_to_resistance < 0.5,
            'near_support': dist_to_support < 0.5
        }
    
    def momentum_analysis(self, df: pd.DataFrame) -> Dict:
        """Comprehensive momentum analysis"""
        closes = df['c'].values
        
        # Multiple ROC periods
        roc_5 = (closes[-1] / closes[-6] - 1) * 100 if len(closes) > 5 else 0
        roc_10 = (closes[-1] / closes[-11] - 1) * 100 if len(closes) > 10 else 0
        roc_20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) > 20 else 0
        
        # Momentum acceleration
        mom_recent = closes[-1] - closes[-5] if len(closes) > 5 else 0
        mom_prior = closes[-5] - closes[-10] if len(closes) > 10 else 0
        acceleration = mom_recent - mom_prior
        
        # Stochastic
        low_14 = df['l'].values[-14:].min()
        high_14 = df['h'].values[-14:].max()
        stoch_k = (closes[-1] - low_14) / (high_14 - low_14) * 100 if high_14 != low_14 else 50
        
        return {
            'roc_5': roc_5,
            'roc_10': roc_10,
            'roc_20': roc_20,
            'acceleration': acceleration,
            'stoch_k': stoch_k,
            'oversold': stoch_k < 20,
            'overbought': stoch_k > 80,
            'momentum_aligned': (roc_5 > 0 and roc_10 > 0) or (roc_5 < 0 and roc_10 < 0)
        }
    
    def predict(self, df: pd.DataFrame, orderbook: Dict = None) -> PredictionResult:
        """Main prediction function"""
        closes = df['c'].values
        highs = df['h'].values
        lows = df['l'].values
        current = closes[-1]
        
        # Calculate all indicators
        rsi = self.calculate_rsi(closes)
        macd, macd_signal, macd_hist = self.calculate_macd(closes)
        bb_upper, bb_lower, bb_position = self.calculate_bollinger(closes)
        
        # EMAs
        ema9 = pd.Series(closes).ewm(span=9).mean().iloc[-1]
        ema21 = pd.Series(closes).ewm(span=21).mean().iloc[-1]
        ema50 = pd.Series(closes).ewm(span=50).mean().iloc[-1] if len(closes) >= 50 else ema21
        
        # ATR
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]), 
                                 np.abs(lows[1:] - closes[:-1])))
        atr = np.mean(tr[-14:])
        
        # Get all analysis
        regime = self.detect_regime(df)
        vpa = self.volume_price_analysis(df)
        sr_levels = self.calculate_support_resistance(df)
        momentum = self.momentum_analysis(df)
        
        # RSI divergence
        rsi_series = np.array([self.calculate_rsi(closes[:i+1]) for i in range(len(closes)-10, len(closes))])
        divergence = self.detect_divergence(closes[-10:], rsi_series)
        
        # === SCORING SYSTEM ===
        bull_score = 0
        bear_score = 0
        signals = {}
        
        # 1. TREND SIGNALS (weight: 1.5)
        trend_bull = 0
        trend_bear = 0
        
        if ema9 > ema21:
            trend_bull += 1
            signals['ema_cross'] = 'BULLISH'
        else:
            trend_bear += 1
            signals['ema_cross'] = 'BEARISH'
        
        if current > ema50:
            trend_bull += 0.5
        else:
            trend_bear += 0.5
        
        # Trend strength from regression
        slope, _, r_value, _, _ = stats.linregress(range(20), closes[-20:])
        if abs(r_value) > 0.6:
            if slope > 0:
                trend_bull += 1
            else:
                trend_bear += 1
        
        bull_score += trend_bull * self.weights['trend']
        bear_score += trend_bear * self.weights['trend']
        signals['trend_score'] = f"Bull:{trend_bull:.1f} Bear:{trend_bear:.1f}"
        
        # 2. MOMENTUM SIGNALS (weight: 1.2)
        mom_bull = 0
        mom_bear = 0
        
        if momentum['momentum_aligned']:
            if momentum['roc_5'] > 0:
                mom_bull += 1
            else:
                mom_bear += 1
        
        if momentum['acceleration'] > 0:
            mom_bull += 0.5
        else:
            mom_bear += 0.5
        
        if macd_hist > 0:
            mom_bull += 0.5
        else:
            mom_bear += 0.5
        
        bull_score += mom_bull * self.weights['momentum']
        bear_score += mom_bear * self.weights['momentum']
        signals['momentum'] = f"ROC5:{momentum['roc_5']:.2f}% Accel:{momentum['acceleration']:.4f}"
        
        # 3. VOLUME SIGNALS (weight: 1.0)
        vol_bull = 0
        vol_bear = 0
        
        if vpa['accumulating']:
            vol_bull += 1.5
        elif vpa['distributing']:
            vol_bear += 1.5
        
        if vpa['vol_direction'] > 0.2:
            vol_bull += 0.5
        elif vpa['vol_direction'] < -0.2:
            vol_bear += 0.5
        
        bull_score += vol_bull * self.weights['volume']
        bear_score += vol_bear * self.weights['volume']
        signals['volume'] = f"Dir:{vpa['vol_direction']:.2f} Ratio:{vpa['vol_ratio']:.2f}"
        
        # 4. MEAN REVERSION SIGNALS (weight: 1.3)
        mr_bull = 0
        mr_bear = 0
        
        # RSI extremes
        if rsi < 30:
            mr_bull += 1.5
            signals['rsi_extreme'] = 'OVERSOLD'
        elif rsi > 70:
            mr_bear += 1.5
            signals['rsi_extreme'] = 'OVERBOUGHT'
        elif rsi < 40:
            mr_bull += 0.5
        elif rsi > 60:
            mr_bear += 0.5
        
        # Bollinger extremes
        if bb_position < 0.1:
            mr_bull += 1
            signals['bb_extreme'] = 'LOWER_BAND'
        elif bb_position > 0.9:
            mr_bear += 1
            signals['bb_extreme'] = 'UPPER_BAND'
        
        # Stochastic extremes
        if momentum['oversold']:
            mr_bull += 0.5
        elif momentum['overbought']:
            mr_bear += 0.5
        
        bull_score += mr_bull * self.weights['mean_reversion']
        bear_score += mr_bear * self.weights['mean_reversion']
        signals['mean_reversion'] = f"RSI:{rsi:.1f} BB:{bb_position:.2f}"
        
        # 5. DIVERGENCE SIGNALS (weight: 1.4)
        if divergence == 'BULLISH':
            bull_score += 2 * self.weights['divergence']
            signals['divergence'] = 'BULLISH (strong)'
        elif divergence == 'BEARISH':
            bear_score += 2 * self.weights['divergence']
            signals['divergence'] = 'BEARISH (strong)'
        else:
            signals['divergence'] = 'NONE'
        
        # 6. SUPPORT/RESISTANCE (weight: 0.8)
        sr_bull = 0
        sr_bear = 0
        
        if sr_levels['near_support']:
            sr_bull += 1
            signals['sr_level'] = 'NEAR_SUPPORT'
        elif sr_levels['near_resistance']:
            sr_bear += 1
            signals['sr_level'] = 'NEAR_RESISTANCE'
        
        bull_score += sr_bull * self.weights['microstructure']
        bear_score += sr_bear * self.weights['microstructure']
        
        # 7. REGIME ADJUSTMENT (weight: 1.0)
        if regime == MarketRegime.TRENDING_UP:
            bull_score += 1 * self.weights['regime']
        elif regime == MarketRegime.TRENDING_DOWN:
            bear_score += 1 * self.weights['regime']
        elif regime == MarketRegime.QUIET:
            # In quiet markets, lean toward mean reversion
            if current < ema21:
                bull_score += 0.5 * self.weights['regime']
            else:
                bear_score += 0.5 * self.weights['regime']
        
        signals['regime'] = regime.value
        
        # 8. ORDER BOOK IMBALANCE (if available)
        if orderbook:
            bids = sum([b[1] for b in orderbook.get('bids', [])[:10]])
            asks = sum([a[1] for a in orderbook.get('asks', [])[:10]])
            imbalance = (bids - asks) / (bids + asks) if (bids + asks) > 0 else 0
            
            if imbalance > 0.2:
                bull_score += 1 * self.weights['microstructure']
                signals['orderbook'] = f'BUY_PRESSURE ({imbalance:.2f})'
            elif imbalance < -0.2:
                bear_score += 1 * self.weights['microstructure']
                signals['orderbook'] = f'SELL_PRESSURE ({imbalance:.2f})'
        
        # === FINAL DIRECTION ===
        net_score = bull_score - bear_score
        total_score = bull_score + bear_score
        
        # Dynamic thresholds based on regime
        if regime in [MarketRegime.QUIET, MarketRegime.RANGING]:
            threshold = 1.5  # Need stronger signal in choppy markets
        else:
            threshold = 1.0
        
        if net_score > threshold:
            direction = 'BULLISH'
            confidence = min(85, 50 + net_score * 8)
            target_mult = 1.2 + (net_score / 10)
        elif net_score < -threshold:
            direction = 'BEARISH'
            confidence = min(85, 50 + abs(net_score) * 8)
            target_mult = 1.2 + (abs(net_score) / 10)
        else:
            direction = 'NEUTRAL'
            confidence = 40 + abs(net_score) * 5
            target_mult = 0.5
        
        # Calculate targets
        if direction == 'BULLISH':
            target_15m = current + atr * 0.5 * target_mult
            target_30m = current + atr * 1.0 * target_mult
            target_60m = current + atr * 1.5 * target_mult
        elif direction == 'BEARISH':
            target_15m = current - atr * 0.5 * target_mult
            target_30m = current - atr * 1.0 * target_mult
            target_60m = current - atr * 1.5 * target_mult
        else:
            target_15m = current
            target_30m = current
            target_60m = current
        
        # Range based on regime
        if regime == MarketRegime.VOLATILE:
            range_mult = 3.0
        elif regime == MarketRegime.QUIET:
            range_mult = 1.5
        else:
            range_mult = 2.0
        
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
                'bull_score': bull_score,
                'bear_score': bear_score,
                'net_score': net_score,
                'threshold': threshold
            }
        )


def run_prediction(symbol: str = 'API3/USDT:USDT'):
    """Run prediction for a symbol"""
    import ccxt
    import os
    from dotenv import load_dotenv
    
    load_dotenv()
    
    exchange = ccxt.bitget({
        'apiKey': os.getenv('BITGET_API_KEY'),
        'secret': os.getenv('BITGET_API_SECRET'),
        'password': os.getenv('BITGET_API_PASSPHRASE'),
        'options': {'defaultType': 'swap'}
    })
    
    # Fetch data
    ohlcv = exchange.fetch_ohlcv(symbol, '5m', limit=100)
    df = pd.DataFrame(ohlcv, columns=['ts', 'o', 'h', 'l', 'c', 'v'])
    
    # Fetch orderbook
    orderbook = exchange.fetch_order_book(symbol, limit=20)
    
    # Run prediction
    model = PredictionModelV3()
    result = model.predict(df, orderbook)
    
    return result, df


if __name__ == '__main__':
    result, df = run_prediction()
    
    print('=' * 70)
    print('       PREDICTION MODEL V3 - API3/USDT')
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
    print(f'\nScore Breakdown:')
    print(f'  Bull Score: {result.score_breakdown["bull_score"]:.2f}')
    print(f'  Bear Score: {result.score_breakdown["bear_score"]:.2f}')
    print(f'  Net Score: {result.score_breakdown["net_score"]:.2f}')
    print(f'  Threshold: {result.score_breakdown["threshold"]:.2f}')
    print(f'\nSignals:')
    for k, v in result.signals.items():
        print(f'  {k}: {v}')
