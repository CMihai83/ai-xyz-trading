#!/usr/bin/env python3
"""
Unified Market Intelligence System for AI-XYZ
Sprint 3: Intelligent opportunity discovery with self-adjustment
Combines market scanning, technical analysis, and AI scoring
"""

import json
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import ccxt
from collections import deque
import threading


class UnifiedMarketIntelligence:
    """
    Centralized market intelligence for opportunity discovery
    Self-adjusting based on success rates
    """

    def __init__(self):
        # Configuration
        self.config_file = '/app/runtime_config.json'
        self.state_file = '/app/market_intelligence_state.json'

        # Load configuration
        self.config = self._load_config()

        # Market data storage
        self.market_data = {}
        self.opportunity_scores = {}
        self.historical_success = {}

        # Technical indicators
        self.indicators = {
            'rsi': {'weight': 0.2, 'threshold': 30},
            'volume': {'weight': 0.15, 'threshold': 1.5},
            'volatility': {'weight': 0.25, 'threshold': 0.02},
            'trend': {'weight': 0.2, 'threshold': 0.01},
            'momentum': {'weight': 0.2, 'threshold': 0.5}
        }

        # Self-adjustment parameters
        self.learning_rate = 0.01
        self.success_threshold = 0.6
        self.adjustment_interval = 3600  # 1 hour

        # Opportunity thresholds
        self.min_opportunity_score = 0.7
        self.max_concurrent_opportunities = 5

        # Initialize logging
        self._setup_logging()

        # Exchange connection
        self.exchange = self._init_exchange()

    def _setup_logging(self):
        """Configure logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('MarketIntelligence')

    def _load_config(self) -> Dict:
        """Load runtime configuration"""
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Config load error: {e}")
            return {}

    def _init_exchange(self):
        """Initialize exchange connection"""
        try:
            import os
            from dotenv import load_dotenv
            load_dotenv('/app/.env')

            exchange = ccxt.bitget({
                'apiKey': os.getenv('BITGET_API_KEY'),
                'secret': os.getenv('BITGET_SECRET_KEY'),
                'password': os.getenv('BITGET_PASSPHRASE'),
                'enableRateLimit': True,
                'options': {
                    'defaultType': 'swap',
                    'productType': 'USDT-FUTURES'
                }
            })

            self.logger.info("Exchange connection established")
            return exchange

        except Exception as e:
            self.logger.error(f"Exchange init failed: {e}")
            return None

    def scan_markets(self) -> Dict[str, float]:
        """
        Scan all configured markets for opportunities

        Returns:
            Dictionary of symbol: opportunity_score
        """
        opportunities = {}
        symbols = self.config.get('opportunity_symbols', [])

        self.logger.info(f"Scanning {len(symbols)} markets...")

        for symbol in symbols:
            try:
                # Fetch market data
                data = self._fetch_market_data(symbol)

                if data:
                    # Calculate opportunity score
                    score = self._calculate_opportunity_score(symbol, data)

                    if score >= self.min_opportunity_score:
                        opportunities[symbol] = score
                        self.logger.info(f"✅ Opportunity found: {symbol} (score: {score:.2f})")

                time.sleep(0.1)  # Rate limiting

            except Exception as e:
                self.logger.error(f"Error scanning {symbol}: {e}")

        # Sort by score and limit
        sorted_opps = dict(sorted(
            opportunities.items(),
            key=lambda x: x[1],
            reverse=True
        )[:self.max_concurrent_opportunities])

        self.opportunity_scores = sorted_opps
        self._save_state()

        return sorted_opps

    def _fetch_market_data(self, symbol: str) -> Optional[Dict]:
        """
        Fetch comprehensive market data for symbol

        Args:
            symbol: Trading symbol

        Returns:
            Market data dictionary
        """
        try:
            # Fetch OHLCV data
            ohlcv = self.exchange.fetch_ohlcv(symbol, '5m', limit=100)

            if not ohlcv:
                return None

            # Convert to DataFrame for analysis
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )

            # Calculate technical indicators
            data = {
                'symbol': symbol,
                'current_price': df['close'].iloc[-1],
                'volume_24h': df['volume'].sum(),
                'high_24h': df['high'].max(),
                'low_24h': df['low'].min(),
                'volatility': df['close'].pct_change().std(),
                'rsi': self._calculate_rsi(df['close']),
                'trend': self._calculate_trend(df['close']),
                'momentum': self._calculate_momentum(df),
                'volume_ratio': df['volume'].iloc[-1] / df['volume'].mean()
            }

            self.market_data[symbol] = data
            return data

        except Exception as e:
            self.logger.error(f"Data fetch error for {symbol}: {e}")
            return None

    def _calculate_opportunity_score(self, symbol: str, data: Dict) -> float:
        """
        Calculate weighted opportunity score

        Args:
            symbol: Trading symbol
            data: Market data

        Returns:
            Opportunity score (0-1)
        """
        score = 0.0
        components = {}

        # RSI component (oversold = opportunity)
        if data['rsi'] < self.indicators['rsi']['threshold']:
            components['rsi'] = 1.0
        elif data['rsi'] < 40:
            components['rsi'] = (40 - data['rsi']) / 10
        else:
            components['rsi'] = 0.0

        # Volume component (high volume = opportunity)
        if data['volume_ratio'] > self.indicators['volume']['threshold']:
            components['volume'] = min(data['volume_ratio'] / 2, 1.0)
        else:
            components['volume'] = data['volume_ratio'] / self.indicators['volume']['threshold']

        # Volatility component (moderate volatility preferred)
        optimal_vol = 0.03
        if abs(data['volatility'] - optimal_vol) < 0.01:
            components['volatility'] = 1.0
        else:
            components['volatility'] = max(0, 1 - abs(data['volatility'] - optimal_vol) * 10)

        # Trend component (reversal potential)
        if data['trend'] < -self.indicators['trend']['threshold']:
            components['trend'] = min(abs(data['trend']) * 10, 1.0)
        else:
            components['trend'] = 0.0

        # Momentum component
        if data['momentum'] < -self.indicators['momentum']['threshold']:
            components['momentum'] = min(abs(data['momentum']), 1.0)
        else:
            components['momentum'] = max(0, 1 - data['momentum'])

        # Calculate weighted score
        for indicator, value in components.items():
            weight = self.indicators[indicator]['weight']
            score += value * weight

        # Apply success rate adjustment
        if symbol in self.historical_success:
            success_rate = self.historical_success[symbol]
            score *= (0.5 + success_rate * 0.5)  # Blend score with historical success

        return min(score, 1.0)

    def _calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate RSI indicator"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

    def _calculate_trend(self, prices: pd.Series) -> float:
        """Calculate price trend"""
        if len(prices) < 20:
            return 0

        # Simple linear regression slope
        x = np.arange(len(prices[-20:]))
        y = prices[-20:].values

        slope = np.polyfit(x, y, 1)[0]
        return slope / prices.iloc[-1]  # Normalize by current price

    def _calculate_momentum(self, df: pd.DataFrame) -> float:
        """Calculate momentum indicator"""
        # Price rate of change
        roc = (df['close'].iloc[-1] - df['close'].iloc[-10]) / df['close'].iloc[-10]

        # Volume-weighted momentum
        volume_weight = df['volume'].iloc[-10:].mean() / df['volume'].mean()

        return roc * volume_weight

    def self_adjust_parameters(self):
        """
        Self-adjust scoring parameters based on success rates
        """
        try:
            # Load historical performance
            performance = self._load_performance_history()

            if not performance:
                return

            self.logger.info("Self-adjusting parameters based on performance...")

            # Calculate success rates per indicator
            indicator_performance = {}

            for trade in performance:
                symbol = trade['symbol']
                success = trade['success']
                scores = trade.get('component_scores', {})

                for indicator, score in scores.items():
                    if indicator not in indicator_performance:
                        indicator_performance[indicator] = []

                    indicator_performance[indicator].append({
                        'score': score,
                        'success': success
                    })

            # Adjust weights based on correlation with success
            for indicator in self.indicators:
                if indicator in indicator_performance:
                    data = indicator_performance[indicator]

                    if len(data) > 10:
                        # Calculate correlation between score and success
                        scores = [d['score'] for d in data]
                        successes = [d['success'] for d in data]

                        correlation = np.corrcoef(scores, successes)[0, 1]

                        # Adjust weight based on correlation
                        if not np.isnan(correlation):
                            old_weight = self.indicators[indicator]['weight']
                            adjustment = correlation * self.learning_rate
                            new_weight = max(0.05, min(0.4, old_weight + adjustment))

                            self.indicators[indicator]['weight'] = new_weight

                            if abs(adjustment) > 0.01:
                                self.logger.info(
                                    f"Adjusted {indicator} weight: "
                                    f"{old_weight:.3f} → {new_weight:.3f}"
                                )

            # Normalize weights
            total_weight = sum(ind['weight'] for ind in self.indicators.values())
            for indicator in self.indicators:
                self.indicators[indicator]['weight'] /= total_weight

            self._save_config()

        except Exception as e:
            self.logger.error(f"Self-adjustment error: {e}")

    def _load_performance_history(self) -> List[Dict]:
        """Load historical trading performance"""
        try:
            with open('/app/performance_history.json', 'r') as f:
                return json.load(f)
        except:
            return []

    def _save_state(self):
        """Save current state"""
        try:
            state = {
                'timestamp': datetime.now().isoformat(),
                'opportunity_scores': self.opportunity_scores,
                'market_data': self.market_data,
                'indicators': self.indicators
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

        except Exception as e:
            self.logger.error(f"State save error: {e}")

    def _save_config(self):
        """Save updated configuration"""
        try:
            self.config['market_intelligence'] = {
                'indicators': self.indicators,
                'min_opportunity_score': self.min_opportunity_score,
                'max_concurrent_opportunities': self.max_concurrent_opportunities
            }

            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)

        except Exception as e:
            self.logger.error(f"Config save error: {e}")

    def get_best_opportunities(self, count: int = 3) -> List[Tuple[str, float]]:
        """
        Get top opportunities by score

        Args:
            count: Number of opportunities to return

        Returns:
            List of (symbol, score) tuples
        """
        if not self.opportunity_scores:
            self.scan_markets()

        return list(self.opportunity_scores.items())[:count]

    def should_enter_position(self, symbol: str) -> Tuple[bool, float]:
        """
        Determine if position should be entered

        Args:
            symbol: Trading symbol

        Returns:
            (should_enter, confidence_score)
        """
        # Check if we have recent data
        if symbol not in self.market_data:
            data = self._fetch_market_data(symbol)
            if not data:
                return False, 0.0

        score = self.opportunity_scores.get(symbol, 0)

        # Additional entry criteria
        criteria = {
            'min_score': score >= self.min_opportunity_score,
            'volatility_ok': 0.01 < self.market_data[symbol]['volatility'] < 0.05,
            'volume_ok': self.market_data[symbol]['volume_ratio'] > 0.8,
            'trend_favorable': self.market_data[symbol]['trend'] < 0.02
        }

        passed = sum(criteria.values())
        confidence = passed / len(criteria)

        should_enter = passed >= 3 and score >= self.min_opportunity_score

        if should_enter:
            self.logger.info(
                f"Entry signal for {symbol}: "
                f"Score={score:.2f}, Confidence={confidence:.2f}"
            )

        return should_enter, confidence


def main():
    """Test market intelligence system"""
    intelligence = UnifiedMarketIntelligence()

    print("\n" + "="*70)
    print("🧠 UNIFIED MARKET INTELLIGENCE TEST")
    print("="*70)

    # Test market scanning
    print("\n📊 Scanning markets...")
    opportunities = intelligence.scan_markets()

    if opportunities:
        print(f"\n✅ Found {len(opportunities)} opportunities:")
        for symbol, score in opportunities.items():
            print(f"  {symbol}: {score:.3f}")
    else:
        print("❌ No opportunities found")

    # Test self-adjustment
    print("\n🔄 Self-adjusting parameters...")
    intelligence.self_adjust_parameters()

    # Get best opportunities
    best = intelligence.get_best_opportunities(3)
    if best:
        print(f"\n🎯 Top opportunities:")
        for symbol, score in best:
            print(f"  {symbol}: {score:.3f}")

    print("\n" + "="*70)


if __name__ == "__main__":
    main()