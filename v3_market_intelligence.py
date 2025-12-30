#!/usr/bin/env python3
"""
V3: AI Market Intelligence Engine
Analyzes market conditions for adaptive trading decisions
"""

import ccxt
import numpy as np
from datetime import datetime, timedelta
import pandas as pd

class AIMarketIntelligence:
    """
    Analyzes market conditions using technical indicators and basic AI
    """

    def __init__(self, exchange):
        self.exchange = exchange
        self.market_cache = {}

    def analyze_market_context(self, symbol):
        """
        Analyze current market context for a symbol

        Returns:
            dict: Market context with regime, volatility, sentiment, etc.
        """
        try:
            # Get recent price data
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # Calculate technical indicators
            df = self.calculate_indicators(df)

            # Determine market regime
            regime = self.detect_regime(df)

            # Calculate volatility
            volatility = self.calculate_volatility(df)

            # Basic sentiment (placeholder - would integrate real sentiment analysis)
            sentiment = self.estimate_sentiment(df)

            # Detect patterns
            patterns = self.detect_patterns(df)

            context = {
                'regime': regime,
                'volatility': volatility,
                'sentiment': sentiment,
                'patterns': patterns,
                'trend_strength': self.calculate_trend_strength(df),
                'support_resistance': self.find_support_resistance(df),
                'momentum': self.calculate_momentum(df)
            }

            return context

        except Exception as e:
            print(f"Error analyzing market context for {symbol}: {e}")
            return self.get_default_context()

    def calculate_indicators(self, df):
        """Calculate technical indicators"""
        # Simple Moving Averages
        df['SMA20'] = df['close'].rolling(20).mean()
        df['SMA50'] = df['close'].rolling(50).mean()

        # RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        # MACD
        ema12 = df['close'].ewm(span=12).mean()
        ema26 = df['close'].ewm(span=26).mean()
        df['MACD'] = ema12 - ema26
        df['Signal'] = df['MACD'].ewm(span=9).mean()

        # Bollinger Bands
        df['BB_middle'] = df['close'].rolling(20).mean()
        df['BB_std'] = df['close'].rolling(20).std()
        df['BB_upper'] = df['BB_middle'] + 2 * df['BB_std']
        df['BB_lower'] = df['BB_middle'] - 2 * df['BB_std']

        return df

    def detect_regime(self, df):
        """Detect market regime"""
        if len(df) < 50:
            return 'neutral'

        recent = df.tail(20)

        # Trend analysis
        sma20_trend = recent['SMA20'].iloc[-1] > recent['SMA20'].iloc[0]
        sma50_trend = recent['SMA50'].iloc[-1] > recent['SMA50'].iloc[0]

        # Volatility
        volatility = recent['close'].pct_change().std()

        # RSI analysis
        rsi = recent['RSI'].iloc[-1]

        if sma20_trend and sma50_trend and rsi > 50:
            return 'bull'
        elif not sma20_trend and not sma50_trend and rsi < 50:
            return 'bear'
        elif volatility > 0.02:  # 2% daily volatility
            return 'volatile'
        else:
            return 'neutral'

    def calculate_volatility(self, df):
        """Calculate current volatility"""
        if len(df) < 20:
            return 0.5

        returns = df['close'].pct_change().dropna()
        volatility = returns.std()

        # Normalize to 0-1 scale
        normalized_vol = min(max(volatility * 100, 0), 1)

        return normalized_vol

    def estimate_sentiment(self, df):
        """Basic sentiment estimation from price action"""
        if len(df) < 20:
            return 0

        recent = df.tail(10)

        # Bullish signals
        bullish = sum([
            recent['close'].iloc[-1] > recent['SMA20'].iloc[-1],  # Above SMA20
            recent['RSI'].iloc[-1] > 60,  # Overbought but trending up
            recent['MACD'].iloc[-1] > recent['Signal'].iloc[-1]  # MACD positive
        ])

        # Bearish signals
        bearish = sum([
            recent['close'].iloc[-1] < recent['SMA20'].iloc[-1],  # Below SMA20
            recent['RSI'].iloc[-1] < 40,  # Oversold but trending down
            recent['MACD'].iloc[-1] < recent['Signal'].iloc[-1]  # MACD negative
        ])

        sentiment = (bullish - bearish) / 6  # Normalize to -1 to 1

        return sentiment

    def detect_patterns(self, df):
        """Detect basic chart patterns"""
        patterns = []

        if len(df) < 20:
            return patterns

        recent = df.tail(20)

        # Double bottom pattern
        if self.is_double_bottom(recent):
            patterns.append('double_bottom')

        # Head and shoulders
        if self.is_head_shoulders(recent):
            patterns.append('head_shoulders')

        # Bullish engulfing
        if self.is_bullish_engulfing(recent):
            patterns.append('bullish_engulfing')

        return patterns

    def is_double_bottom(self, df):
        """Basic double bottom detection"""
        if len(df) < 10:
            return False

        # Simplified check
        lows = df['low'].tail(10)
        if lows.iloc[-1] < lows.iloc[-3] and lows.iloc[-1] > lows.iloc[-5]:
            return True
        return False

    def is_head_shoulders(self, df):
        """Basic head and shoulders detection"""
        # Simplified - would need more sophisticated analysis
        return False

    def is_bullish_engulfing(self, df):
        """Basic bullish engulfing pattern"""
        if len(df) < 2:
            return False

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        if (curr['open'] < prev['close'] and
            curr['close'] > prev['open'] and
            curr['close'] > curr['open']):
            return True
        return False

    def calculate_trend_strength(self, df):
        """Calculate trend strength"""
        if len(df) < 20:
            return 0

        # ADX-like calculation (simplified)
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift(1))
        low_close = abs(df['low'] - df['close'].shift(1))

        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = tr.rolling(14).mean()

        trend_strength = atr.iloc[-1] / df['close'].iloc[-1]

        return min(trend_strength * 100, 1)  # Normalize

    def find_support_resistance(self, df):
        """Find basic support/resistance levels"""
        if len(df) < 20:
            return {'support': None, 'resistance': None}

        recent = df.tail(50)

        support = recent['low'].min()
        resistance = recent['high'].max()

        return {'support': support, 'resistance': resistance}

    def calculate_momentum(self, df):
        """Calculate momentum indicator"""
        if len(df) < 10:
            return 0

        # Rate of change
        roc = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]

        return roc

    def get_default_context(self):
        """Return default market context"""
        return {
            'regime': 'neutral',
            'volatility': 0.5,
            'sentiment': 0,
            'patterns': [],
            'trend_strength': 0,
            'support_resistance': {'support': None, 'resistance': None},
            'momentum': 0
        }