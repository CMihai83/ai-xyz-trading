#!/usr/bin/env python3
"""
Correlation Matrix Analyzer for Opportunity Cost Service
Analyzes correlations between assets and market sectors for better opportunity cost calculations
"""

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import ccxt
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import json
import os

class CorrelationMatrixAnalyzer:
    """
    Analyzes correlations between crypto assets and provides market context for opportunity costs
    """

    def __init__(self, exchange):
        self.exchange = exchange
        self.correlation_cache = {}
        self.sector_mappings = {}
        self.volatility_regime = 'normal'
        self._load_sector_mappings()

    def _load_sector_mappings(self):
        """Load predefined sector mappings for crypto assets"""
        self.sector_mappings = {
            # Layer 1
            'BTC': 'layer1', 'ETH': 'layer1', 'ADA': 'layer1', 'SOL': 'layer1',
            'DOT': 'layer1', 'AVAX': 'layer1', 'MATIC': 'layer1', 'LINK': 'layer1',

            # DeFi
            'UNI': 'defi', 'AAVE': 'defi', 'SUSHI': 'defi', 'COMP': 'defi',
            'MKR': 'defi', 'YFI': 'defi', 'CRV': 'defi', 'BAL': 'defi',

            # Gaming/Metaverse
            'MANA': 'gaming', 'SAND': 'gaming', 'AXS': 'gaming', 'ENJ': 'gaming',
            'GAL': 'gaming', 'IMX': 'gaming', 'GALA': 'gaming',

            # DePIN/Infrastructure
            'FIL': 'depin', 'HIVE': 'depin', 'AR': 'depin', 'STORJ': 'depin',
            'FET': 'depin', 'AGIX': 'depin',

            # Meme coins
            'DOGE': 'meme', 'SHIB': 'meme', 'PEPE': 'meme', 'FLOKI': 'meme',

            # AI
            'FET': 'ai', 'AGIX': 'ai', 'OCEAN': 'ai', 'GRT': 'ai',

            # Oracle
            'LINK': 'oracle', 'TRU': 'oracle', 'REP': 'oracle'
        }

    def calculate_correlation_matrix(self, symbols: List[str], timeframe: str = '1h', periods: int = 24) -> pd.DataFrame:
        """
        Calculate correlation matrix for given symbols

        Args:
            symbols: List of trading symbols
            timeframe: Timeframe for correlation calculation
            periods: Number of periods to analyze

        Returns:
            DataFrame: Correlation matrix
        """
        cache_key = f"{','.join(symbols)}_{timeframe}_{periods}"

        if cache_key in self.correlation_cache:
            cached_data = self.correlation_cache[cache_key]
            if (datetime.now() - cached_data['timestamp']).seconds < 300:  # 5 min cache
                return cached_data['matrix']

        try:
            # Fetch price data for all symbols
            price_data = {}
            for symbol in symbols:
                try:
                    ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=periods)
                    closes = [candle[4] for candle in ohlcv]  # Close prices
                    returns = np.diff(np.log(closes))  # Log returns
                    price_data[symbol] = returns
                except Exception as e:
                    print(f"⚠️ Could not fetch data for {symbol}: {e}")
                    continue

            if len(price_data) < 3:
                # Return identity matrix if insufficient data
                return pd.DataFrame(np.eye(len(symbols)), index=symbols, columns=symbols)

            # Create returns DataFrame
            returns_df = pd.DataFrame(price_data)

            # Calculate correlation matrix
            corr_matrix = returns_df.corr()

            # Cache result
            self.correlation_cache[cache_key] = {
                'matrix': corr_matrix,
                'timestamp': datetime.now()
            }

            return corr_matrix

        except Exception as e:
            print(f"❌ Error calculating correlation matrix: {e}")
            # Return identity matrix as fallback
            return pd.DataFrame(np.eye(len(symbols)), index=symbols, columns=symbols)

    def analyze_sector_correlations(self, symbol: str, market_symbols: List[str]) -> Dict:
        """
        Analyze how a symbol correlates with different market sectors

        Args:
            symbol: Symbol to analyze
            market_symbols: All available market symbols

        Returns:
            dict: Sector correlation analysis
        """
        # Group symbols by sector
        sectors = {}
        for sym in market_symbols:
            base_symbol = sym.replace('/USDT', '').replace('USDT:', '')
            sector = self.sector_mappings.get(base_symbol, 'other')
            if sector not in sectors:
                sectors[sector] = []
            sectors[sector].append(sym)

        sector_correlations = {}

        for sector_name, sector_symbols in sectors.items():
            if len(sector_symbols) < 2:
                continue

            try:
                # Calculate correlation with sector
                corr_matrix = self.calculate_correlation_matrix([symbol] + sector_symbols[:10])  # Limit to 10 for performance

                if symbol in corr_matrix.index:
                    sector_corr = corr_matrix.loc[symbol].drop(symbol).mean()
                    sector_correlations[sector_name] = {
                        'correlation': sector_corr,
                        'symbols_count': len(sector_symbols),
                        'correlation_strength': self._interpret_correlation(sector_corr)
                    }
            except Exception as e:
                print(f"⚠️ Error analyzing sector {sector_name}: {e}")
                continue

        return sector_correlations

    def detect_market_regime(self, symbols: List[str]) -> Dict:
        """
        Detect current market regime based on correlation patterns

        Args:
            symbols: Market symbols to analyze

        Returns:
            dict: Market regime analysis
        """
        try:
            corr_matrix = self.calculate_correlation_matrix(symbols)

            # Calculate average correlation
            avg_correlation = corr_matrix.values[np.triu_indices_from(corr_matrix.values, 1)].mean()

            # Calculate correlation volatility (std of correlations)
            corr_volatility = corr_matrix.values[np.triu_indices_from(corr_matrix.values, 1)].std()

            # Determine regime
            if avg_correlation > 0.7:
                regime = 'high_correlation'  # Risk-on, correlated moves
            elif avg_correlation < 0.3:
                regime = 'low_correlation'  # Fragmented market
            else:
                regime = 'normal'

            # Volatility regime
            if corr_volatility > 0.3:
                vol_regime = 'high_volatility'
            elif corr_volatility < 0.1:
                vol_regime = 'low_volatility'
            else:
                vol_regime = 'normal_volatility'

            return {
                'market_regime': regime,
                'volatility_regime': vol_regime,
                'average_correlation': avg_correlation,
                'correlation_volatility': corr_volatility,
                'regime_multiplier': self._get_regime_multiplier(regime, vol_regime)
            }

        except Exception as e:
            print(f"❌ Error detecting market regime: {e}")
            return {
                'market_regime': 'normal',
                'volatility_regime': 'normal_volatility',
                'average_correlation': 0.5,
                'correlation_volatility': 0.2,
                'regime_multiplier': 1.0
            }

    def _get_regime_multiplier(self, market_regime: str, vol_regime: str) -> float:
        """Get multiplier for opportunity cost thresholds based on market regime"""
        base_multiplier = 1.0

        # Market regime adjustments
        if market_regime == 'high_correlation':
            base_multiplier *= 0.8  # More aggressive in correlated markets
        elif market_regime == 'low_correlation':
            base_multiplier *= 1.2  # More patient in fragmented markets

        # Volatility adjustments
        if vol_regime == 'high_volatility':
            base_multiplier *= 0.9  # Slightly more aggressive in volatile markets
        elif vol_regime == 'low_volatility':
            base_multiplier *= 1.1  # More patient in stable markets

        return base_multiplier

    def calculate_opportunity_cost_with_correlations(self, symbol: str, position_data: Dict, market_opportunities: Dict) -> Dict:
        """
        Calculate opportunity cost considering correlation effects

        Args:
            symbol: Current position symbol
            position_data: Current position data
            market_opportunities: Market opportunity data

        Returns:
            dict: Enhanced opportunity cost analysis
        """
        # Get sector correlations
        market_symbols = list(market_opportunities.keys())
        sector_analysis = self.analyze_sector_correlations(symbol, market_symbols)

        # Get market regime
        regime_data = self.detect_market_regime([symbol] + market_symbols[:20])

        # Calculate base opportunity cost
        position_pnl = position_data.get('pnl', 0)
        enhanced_costs = {}

        for opp_symbol, opp_data in market_opportunities.items():
            market_return = opp_data.get('return', 0)
            base_cost = max(0, market_return - position_pnl)

            # Apply correlation adjustments
            correlation_multiplier = self._get_correlation_multiplier(symbol, opp_symbol, sector_analysis)

            # Apply regime adjustments
            regime_multiplier = regime_data.get('regime_multiplier', 1.0)

            # Calculate enhanced opportunity cost
            enhanced_cost = base_cost * correlation_multiplier * regime_multiplier

            enhanced_costs[opp_symbol] = {
                'base_opportunity_cost': base_cost,
                'enhanced_opportunity_cost': enhanced_cost,
                'correlation_multiplier': correlation_multiplier,
                'regime_multiplier': regime_multiplier,
                'correlation_explanation': self._explain_correlation_effect(symbol, opp_symbol, sector_analysis)
            }

        # Calculate portfolio-level opportunity cost
        total_enhanced_cost = sum(cost_data['enhanced_opportunity_cost'] for cost_data in enhanced_costs.values())
        avg_enhanced_cost = total_enhanced_cost / len(enhanced_costs) if enhanced_costs else 0

        return {
            'enhanced_opportunity_costs': enhanced_costs,
            'portfolio_enhanced_cost': avg_enhanced_cost,
            'sector_analysis': sector_analysis,
            'market_regime': regime_data,
            'correlation_insights': self._generate_correlation_insights(sector_analysis, regime_data)
        }

    def _get_correlation_multiplier(self, symbol1: str, symbol2: str, sector_analysis: Dict) -> float:
        """Calculate correlation-based multiplier for opportunity cost"""
        # Check if symbols are in same sector
        base1 = symbol1.replace('/USDT', '').replace('USDT:', '')
        base2 = symbol2.replace('/USDT', '').replace('USDT:', '')

        sector1 = self.sector_mappings.get(base1, 'other')
        sector2 = self.sector_mappings.get(base2, 'other')

        if sector1 == sector2 and sector1 != 'other':
            # Same sector - reduce opportunity cost (less unique alpha)
            return 0.7
        elif sector1 != sector2:
            # Different sectors - increase opportunity cost (more diversification value)
            return 1.3
        else:
            # Unknown or same 'other' category
            return 1.0

    def _interpret_correlation(self, correlation: float) -> str:
        """Interpret correlation strength"""
        if correlation > 0.7:
            return 'very_strong'
        elif correlation > 0.5:
            return 'strong'
        elif correlation > 0.3:
            return 'moderate'
        elif correlation > 0.1:
            return 'weak'
        elif correlation > -0.1:
            return 'very_weak'
        elif correlation > -0.3:
            return 'weak_negative'
        elif correlation > -0.5:
            return 'moderate_negative'
        elif correlation > -0.7:
            return 'strong_negative'
        else:
            return 'very_strong_negative'

    def _explain_correlation_effect(self, symbol1: str, symbol2: str, sector_analysis: Dict) -> str:
        """Generate explanation for correlation effect"""
        base1 = symbol1.replace('/USDT', '').replace('USDT:', '')
        base2 = symbol2.replace('/USDT', '').replace('USDT:', '')

        sector1 = self.sector_mappings.get(base1, 'other')
        sector2 = self.sector_mappings.get(base2, 'other')

        if sector1 == sector2 and sector1 != 'other':
            return f"Same sector ({sector1}) - reduced opportunity cost"
        elif sector1 != sector2:
            return f"Different sectors ({sector1} vs {sector2}) - increased opportunity cost"
        else:
            return "Unknown sector relationship"

    def _generate_correlation_insights(self, sector_analysis: Dict, regime_data: Dict) -> List[str]:
        """Generate insights from correlation analysis"""
        insights = []

        # Sector insights
        if sector_analysis:
            strongest_sector = max(sector_analysis.items(), key=lambda x: abs(x[1]['correlation']))
            sector_name, sector_data = strongest_sector

            if sector_data['correlation'] > 0.5:
                insights.append(f"Strong correlation with {sector_name} sector ({sector_data['correlation']:.2f})")
            elif sector_data['correlation'] < -0.3:
                insights.append(f"Negative correlation with {sector_name} sector ({sector_data['correlation']:.2f})")

        # Regime insights
        regime = regime_data.get('market_regime', 'normal')
        if regime == 'high_correlation':
            insights.append("Market in high-correlation regime - opportunity costs more relevant")
        elif regime == 'low_correlation':
            insights.append("Market in low-correlation regime - more diversification opportunities")

        vol_regime = regime_data.get('volatility_regime', 'normal_volatility')
        if vol_regime == 'high_volatility':
            insights.append("High correlation volatility - thresholds adjusted for uncertainty")

        return insights