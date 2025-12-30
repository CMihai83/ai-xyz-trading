"""
Futures Market Scanner - Scans futures/perpetual markets for trading opportunities.
"""

import asyncio
import time
from typing import Dict, List, Optional
import httpx
import numpy as np
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)

class FuturesMarketScanner:
    """Scanner specifically for futures/perpetual markets."""
    
    def __init__(self):
        self.base_url = "https://api.bitget.com"
        self.futures_symbols = [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "XRPUSDT", "ADAUSDT",
            "DOGEUSDT", "SOLUSDT", "DOTUSDT", "MATICUSDT", "AVAXUSDT",
            "LTCUSDT", "LINKUSDT", "UNIUSDT", "ATOMUSDT", "XLMUSDT",
            "NEARUSDT", "FTMUSDT", "ALGOUSDT", "VETUSDT", "ICPUSDT"
        ]
        self.scan_interval = 30  # seconds
        
    async def scan_futures_markets(self) -> List[Dict]:
        """Scan futures markets for trading opportunities."""
        signals = []
        
        for symbol in self.futures_symbols:
            try:
                signal = await self.analyze_futures_symbol(symbol)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error scanning {symbol}", error=str(e))
        
        # Sort by signal strength
        signals.sort(key=lambda x: x.get('signal_strength', 0), reverse=True)
        
        return signals[:10]  # Return top 10 signals
    
    async def analyze_futures_symbol(self, symbol: str) -> Optional[Dict]:
        """Analyze a futures symbol for trading opportunities."""
        try:
            async with httpx.AsyncClient() as client:
                # Get kline data using V2 API
                response = await client.get(
                    f"{self.base_url}/api/v2/mix/market/candles",
                    params={
                        "productType": "USDT-FUTURES",
                        "symbol": symbol,
                        "granularity": "5m",
                        "limit": 100
                    }
                )
                
                if response.status_code != 200:
                    return None
                
                data = response.json()
                if not data.get('data'):
                    return None
                
                klines = data['data']
                if len(klines) < 50:
                    return None
                
                # Extract price data
                closes = np.array([float(k[4]) for k in klines])
                highs = np.array([float(k[2]) for k in klines])
                lows = np.array([float(k[3]) for k in klines])
                volumes = np.array([float(k[5]) for k in klines])
                
                # Calculate indicators
                rsi = self.calculate_rsi(closes)
                macd_signal = self.calculate_macd(closes)
                bb_signal = self.calculate_bollinger_bands(closes)
                volume_signal = self.calculate_volume_signal(volumes)
                momentum = self.calculate_momentum(closes)
                
                # Generate composite signal for futures
                signal_type, signal_strength = self.generate_futures_signal(
                    rsi, macd_signal, bb_signal, volume_signal, momentum
                )
                
                if signal_type:
                    return {
                        'symbol': symbol.replace('USDT', ''),
                        'futures_symbol': symbol,
                        'signal_type': signal_type,
                        'signal_strength': signal_strength,
                        'current_price': float(closes[-1]),
                        'rsi': rsi,
                        'momentum': momentum,
                        'volume_24h': float(volumes[-24:].sum()) if len(volumes) >= 24 else float(volumes.sum()),
                        'timestamp': datetime.now().isoformat(),
                        'indicators': {
                            'rsi': rsi,
                            'macd': macd_signal,
                            'bollinger': bb_signal,
                            'volume': volume_signal,
                            'momentum': momentum
                        }
                    }
                
        except Exception as e:
            logger.error(f"Error analyzing {symbol}", error=str(e))
        
        return None
    
    def calculate_rsi(self, prices: np.ndarray, period: int = 14) -> float:
        """Calculate RSI indicator."""
        if len(prices) < period + 1:
            return 50.0
        
        deltas = np.diff(prices)
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        if down == 0:
            return 100.0
        
        rs = up / down
        rsi = 100 - (100 / (1 + rs))
        
        return float(rsi)
    
    def calculate_macd(self, prices: np.ndarray) -> float:
        """Calculate MACD signal."""
        if len(prices) < 26:
            return 0.0
        
        # Calculate EMAs
        ema12 = self.calculate_ema(prices, 12)
        ema26 = self.calculate_ema(prices, 26)
        
        macd = ema12 - ema26
        signal = self.calculate_ema(np.array([macd]), 9)
        
        return float(macd - signal)
    
    def calculate_ema(self, prices: np.ndarray, period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(prices) < period:
            return float(prices[-1])
        
        multiplier = 2 / (period + 1)
        ema = prices[-period:].mean()
        
        for price in prices[-period:]:
            ema = (price * multiplier) + (ema * (1 - multiplier))
        
        return float(ema)
    
    def calculate_bollinger_bands(self, prices: np.ndarray, period: int = 20) -> float:
        """Calculate Bollinger Bands signal."""
        if len(prices) < period:
            return 0.0
        
        sma = prices[-period:].mean()
        std = prices[-period:].std()
        
        upper_band = sma + (2 * std)
        lower_band = sma - (2 * std)
        current_price = prices[-1]
        
        # Return position relative to bands (-1 to 1)
        if upper_band == lower_band:
            return 0.0
        
        position = (current_price - lower_band) / (upper_band - lower_band)
        return float(position * 2 - 1)
    
    def calculate_volume_signal(self, volumes: np.ndarray) -> float:
        """Calculate volume-based signal."""
        if len(volumes) < 20:
            return 0.0
        
        avg_volume = volumes[-20:].mean()
        current_volume = volumes[-1]
        
        if avg_volume == 0:
            return 0.0
        
        return float((current_volume - avg_volume) / avg_volume)
    
    def calculate_momentum(self, prices: np.ndarray, period: int = 10) -> float:
        """Calculate price momentum."""
        if len(prices) < period:
            return 0.0
        
        return float((prices[-1] - prices[-period]) / prices[-period] * 100)
    
    def generate_futures_signal(self, rsi: float, macd: float, bb: float, 
                                volume: float, momentum: float) -> tuple:
        """Generate composite trading signal for futures."""
        signal_score = 0.0
        signal_type = None
        
        # Long signals
        if rsi < 35:  # Oversold
            signal_score += 0.3
        if macd > 0:  # Bullish MACD
            signal_score += 0.2
        if bb < -0.5:  # Near lower band
            signal_score += 0.2
        if volume > 0.5:  # High volume
            signal_score += 0.15
        if momentum > 2:  # Strong upward momentum
            signal_score += 0.15
        
        if signal_score >= 0.2:  # Lowered threshold from 0.4 to 0.2 for testing
            signal_type = "LONG"
            return signal_type, min(signal_score, 1.0)
        
        # Short signals
        signal_score = 0.0
        if rsi > 65:  # Overbought
            signal_score += 0.3
        if macd < 0:  # Bearish MACD
            signal_score += 0.2
        if bb > 0.5:  # Near upper band
            signal_score += 0.2
        if volume > 0.5:  # High volume
            signal_score += 0.15
        if momentum < -2:  # Strong downward momentum
            signal_score += 0.15
        
        if signal_score >= 0.2:  # Lowered threshold from 0.4 to 0.2 for testing
            signal_type = "SHORT"
            return signal_type, min(signal_score, 1.0)
        
        return None, 0.0

# Global futures scanner instance
futures_scanner = FuturesMarketScanner()