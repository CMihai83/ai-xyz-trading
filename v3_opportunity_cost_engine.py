#!/usr/bin/env python3
"""
V3: Opportunity Cost Engine
Calculates and optimizes for opportunity costs in real-time

Sprint 14 Enhancement: Now uses shared ScannerV4 and PreTradeBacktester
instead of its own market scanner for unified opportunity detection.
"""

import ccxt
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
import json
import os
import sys
from typing import Dict, List, Optional

# Import AI components (all required dependencies now installed)
from dynamic_threshold_engine import DynamicThresholdEngine
from opportunity_cost_predictor import OpportunityCostPredictor
from correlation_matrix_analyzer import CorrelationMatrixAnalyzer
from markowitz_optimizer import MarkowitzOptimizer
from rl_closing_agent import RLClosingAgent

# Import shared scanner and backtester (Sprint 14 unification)
try:
    from pre_trade_backtest import PreTradeBacktester
    BACKTEST_AVAILABLE = True
except ImportError:
    BACKTEST_AVAILABLE = False
    print("⚠️ PreTradeBacktester not available")

class OpportunityCostEngine:
    """
    Advanced AI-powered opportunity cost calculation and optimization
    Features: ML predictions, dynamic thresholds, correlation analysis, behavioral factors
    """

    def __init__(self, exchange):
        self.exchange = exchange
        self.market_cache = {}
        self.opportunity_history = []

        # Base thresholds (will be adjusted dynamically)
        self.base_thresholds = {
            'high_cost': 0.05,      # 5%+ opportunity cost = close immediately
            'moderate_cost': 0.03, # 3%+ opportunity cost = close if conditions met
            'acceptable_cost': 0.02 # 2%+ opportunity cost = monitor closely
        }

        # Initialize AI components (all fully active)
        self.dynamic_thresholds = DynamicThresholdEngine()
        self.ml_predictor = OpportunityCostPredictor()
        self.correlation_analyzer = CorrelationMatrixAnalyzer(exchange)
        self.markowitz_optimizer = MarkowitzOptimizer()
        self.rl_agent = RLClosingAgent()

        # Behavioral economics factors
        self.behavioral_factors = {
            'momentum_threshold': 0.02,  # 2% recent momentum
            'herding_multiplier': 1.0,
            'loss_aversion_ratio': 2.0,  # Loss hurts 2x more than gain feels good
            'disposition_effect': True   # Tendency to hold losers, sell winners
        }

        # Sprint 14: Initialize shared backtester
        if BACKTEST_AVAILABLE:
            self.backtester = PreTradeBacktester(self.exchange)
            print("✅ PreTradeBacktester integrated")
        else:
            self.backtester = None

        # Sprint 14: Shared scanner results cache (from ScannerV4)
        self.shared_scanner_results = None
        self.shared_scanner_timestamp = None
        self.scanner_results_ttl = 60  # Use scanner results for 60 seconds

        print("🚀 Advanced Opportunity Cost Engine initialized with AI components")

    def calculate_portfolio_opportunity_cost(self, current_positions, total_capital):
        """
        Calculate opportunity cost for entire portfolio vs market alternatives

        Args:
            current_positions: Dict of current positions
            total_capital: Total available capital

        Returns:
            dict: Opportunity cost analysis
        """
        # Get market performance for alternatives
        market_opportunities = self.scan_market_opportunities()

        # Calculate current portfolio performance
        portfolio_performance = self.calculate_portfolio_performance(current_positions)

        # Calculate opportunity costs
        opportunity_costs = {}
        total_opportunity_cost = 0
        total_allocated_capital = 0

        for symbol, pos_data in current_positions.items():
            if 'entry_price' in pos_data and 'amount' in pos_data:
                # Calculate current position value and P&L
                current_value = pos_data['amount'] * pos_data['entry_price'] * (1 + pos_data.get('pnl', 0))
                allocated_capital = current_value / pos_data.get('leverage', 1)

                # Get market alternative performance
                market_perf = market_opportunities.get(symbol, {'return': 0, 'sharpe': 0})

                # Calculate opportunity cost
                position_pnl = pos_data.get('pnl', 0)
                market_return = market_perf['return']
                opportunity_cost = market_return - position_pnl

                opportunity_costs[symbol] = {
                    'allocated_capital': allocated_capital,
                    'position_pnl': position_pnl,
                    'market_return': market_return,
                    'opportunity_cost': opportunity_cost,
                    'cost_severity': self.assess_cost_severity(opportunity_cost),
                    'sharpe_vs_market': market_perf['sharpe']
                }

                total_opportunity_cost += opportunity_cost * allocated_capital
                total_allocated_capital += allocated_capital

        # Calculate portfolio-level opportunity cost
        portfolio_opportunity_cost = total_opportunity_cost / total_allocated_capital if total_allocated_capital > 0 else 0

        # Calculate reallocation recommendations
        reallocation_recommendations = self.generate_reallocation_recommendations(
            opportunity_costs, market_opportunities, total_capital, total_allocated_capital
        )

        return {
            'portfolio_opportunity_cost': portfolio_opportunity_cost,
            'position_costs': opportunity_costs,
            'reallocation_recommendations': reallocation_recommendations,
            'market_opportunities': market_opportunities,
            'unallocated_capital': total_capital - total_allocated_capital
        }

    def set_scanner_results(self, scanner_results: List[Dict]):
        """
        Sprint 14: Receive scanner results from ScannerV4 (shared scanner)

        Args:
            scanner_results: List of opportunities from ScannerV4.scan_market()
        """
        self.shared_scanner_results = scanner_results
        self.shared_scanner_timestamp = datetime.now()
        print(f"📊 OpportunityCostEngine: Received {len(scanner_results)} opportunities from ScannerV4")

    def scan_market_opportunities(self, max_markets=100, use_backtest=True):
        """
        Scan market for high-opportunity assets

        Sprint 14: Now uses shared ScannerV4 results when available,
        and validates opportunities with PreTradeBacktester.

        Args:
            max_markets: Maximum number of markets to scan (top by volume)
            use_backtest: Whether to validate with PreTradeBacktester (default True)

        Returns:
            dict: Market opportunities ranked by Sharpe ratio
        """
        # Sprint 14: Use shared scanner results if available and fresh
        if self.shared_scanner_results and self.shared_scanner_timestamp:
            age = (datetime.now() - self.shared_scanner_timestamp).total_seconds()
            if age < self.scanner_results_ttl:
                print(f"  📊 Using shared ScannerV4 results ({age:.0f}s old, {len(self.shared_scanner_results)} opportunities)")
                return self._convert_scanner_results_to_opportunities(
                    self.shared_scanner_results,
                    use_backtest=use_backtest
                )

        # Fallback: Own scanner (if ScannerV4 results not available)
        print(f"  📊 Running fallback opportunity scan (ScannerV4 results not available)")

        # Dynamically get USDT-margined perpetual futures from Bitget, sorted by volume
        try:
            if not self.exchange.markets:
                self.exchange.load_markets()

            # Get all USDT futures
            all_futures = [
                symbol for symbol, market in self.exchange.markets.items()
                if market.get('swap', False)
                and market.get('linear', False)
                and market.get('settle') == 'USDT'
                and market.get('active', True)
            ]

            # Fetch tickers to get 24h volume (single API call for all)
            print(f"  📊 Found {len(all_futures)} USDT futures, fetching volumes...")
            tickers = self.exchange.fetch_tickers(all_futures[:200])  # Bitget may limit batch size

            # Sort by 24h quote volume (USDT volume)
            sorted_by_volume = sorted(
                [(symbol, ticker.get('quoteVolume', 0) or 0) for symbol, ticker in tickers.items()],
                key=lambda x: x[1],
                reverse=True
            )

            # Take top markets by volume
            opportunity_universe = [symbol for symbol, vol in sorted_by_volume[:max_markets]]
            print(f"  📊 Scanning top {len(opportunity_universe)} markets by volume")

        except Exception as e:
            print(f"  ⚠️ Failed to load markets: {e}, using fallback list")
            opportunity_universe = [
                'BTC/USDT:USDT', 'ETH/USDT:USDT', 'BNB/USDT:USDT', 'SOL/USDT:USDT',
                'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'ADA/USDT:USDT', 'AVAX/USDT:USDT',
                'LINK/USDT:USDT', 'DOT/USDT:USDT', 'MATIC/USDT:USDT', 'UNI/USDT:USDT'
            ]

        opportunities = {}

        for symbol in opportunity_universe:
            try:
                # Get 24h performance
                ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=24)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

                if len(df) >= 24:
                    start_price = df['close'].iloc[0]
                    end_price = df['close'].iloc[-1]
                    total_return = (end_price - start_price) / start_price

                    returns = df['close'].pct_change().dropna()
                    volatility = returns.std()

                    # Calculate risk-adjusted metrics
                    sharpe_ratio = total_return / (volatility + 1e-6)
                    sortino_ratio = total_return / (returns[returns < 0].std() + 1e-6) if len(returns[returns < 0]) > 0 else 0

                    opp_data = {
                        'return': total_return,
                        'volatility': volatility,
                        'sharpe': sharpe_ratio,
                        'sortino': sortino_ratio,
                        'volume': df['volume'].mean(),
                        'current_price': end_price
                    }

                    # Sprint 14: Validate with backtest
                    if use_backtest and self.backtester:
                        direction = 'long' if total_return > 0 else 'short'
                        backtest_result = self.backtester.validate_trade(symbol, direction, days=30)
                        opp_data['backtest_score'] = backtest_result.score
                        opp_data['backtest_approved'] = backtest_result.should_trade
                        opp_data['backtest_win_rate'] = backtest_result.win_rate
                        opp_data['backtest_sharpe'] = backtest_result.sharpe_ratio

                        # Only include if backtest approved
                        if not backtest_result.should_trade:
                            continue  # Skip this opportunity

                    opportunities[symbol] = opp_data

            except Exception as e:
                continue

        # Rank by Sharpe ratio
        ranked_opportunities = dict(sorted(opportunities.items(),
                                         key=lambda x: x[1]['sharpe'], reverse=True))

        return ranked_opportunities

    def _convert_scanner_results_to_opportunities(self, scanner_results: List[Dict], use_backtest: bool = True) -> Dict:
        """
        Sprint 14: Convert ScannerV4 results to opportunity cost format with backtest validation
        """
        opportunities = {}

        for opp in scanner_results:
            symbol = opp.get('symbol', '')
            if not symbol:
                continue

            # Convert scanner format to opportunity cost format
            opp_data = {
                'return': opp.get('performance', {}).get('return_24h', opp.get('return', 0)),
                'volatility': opp.get('volatility', opp.get('performance', {}).get('volatility', 0.05)),
                'sharpe': opp.get('sharpe', opp.get('score', 0)),
                'sortino': opp.get('sortino', 0),
                'volume': opp.get('volume', opp.get('performance', {}).get('volume', 0)),
                'current_price': opp.get('current_price', opp.get('price', 0)),
                'scanner_score': opp.get('score', 0),
                'scanner_signal': opp.get('signal', 'unknown'),
                'direction': opp.get('direction', 'long')
            }

            # Sprint 14: Validate with backtest
            # V2.1.0: Skip backtest when portfolio in drawdown (adversity/black swan opportunity!)
            skip_backtest_for_adversity = False
            try:
                positions = self.exchange.fetch_positions()
                active = [p for p in positions if abs(p.get('contracts', 0)) > 0]
                if active:
                    total_upnl = sum(float(p.get('unrealizedPnl', 0) or 0) for p in active)
                    total_margin = sum(float(p.get('initialMargin', 0) or p.get('collateral', 0) or 0) for p in active)
                    portfolio_drawdown = (total_upnl / total_margin * 100) if total_margin > 0 else 0
                    # If portfolio is down 15%+ = adversity opportunity, skip backtest
                    if portfolio_drawdown <= -15:
                        skip_backtest_for_adversity = True
            except:
                pass

            if use_backtest and self.backtester and not skip_backtest_for_adversity:
                direction = opp_data.get('direction', 'long')
                try:
                    backtest_result = self.backtester.validate_trade(symbol, direction, days=30)
                    opp_data['backtest_score'] = backtest_result.score
                    opp_data['backtest_approved'] = backtest_result.should_trade
                    opp_data['backtest_win_rate'] = backtest_result.win_rate
                    opp_data['backtest_sharpe'] = backtest_result.sharpe_ratio
                    opp_data['backtest_profit_factor'] = backtest_result.profit_factor

                    # Only include if backtest approved OR scanner score is very high (>0.85)
                    if not backtest_result.should_trade and opp_data['scanner_score'] < 0.85:
                        print(f"  ⛔ {symbol}: Scanner approved but backtest rejected (score: {backtest_result.score:.2f})")
                        continue
                    elif not backtest_result.should_trade:
                        print(f"  ⚠️ {symbol}: Backtest rejected but scanner score high ({opp_data['scanner_score']:.2f}), including")
                except Exception as e:
                    opp_data['backtest_score'] = 0
                    opp_data['backtest_approved'] = False
                    print(f"  ⚠️ Backtest failed for {symbol}: {e}")
            elif skip_backtest_for_adversity:
                opp_data['backtest_score'] = opp_data['scanner_score']  # Use scanner score as backtest
                opp_data['backtest_approved'] = True
                print(f"  ⚡ {symbol}: Skipping backtest - portfolio in drawdown (buy the dip!)")

            opportunities[symbol] = opp_data

        # Rank by combined score (scanner + backtest if available)
        def combined_score(item):
            data = item[1]
            scanner = data.get('scanner_score', 0)
            backtest = data.get('backtest_score', scanner)  # Fallback to scanner if no backtest
            return (scanner * 0.6 + backtest * 0.4)  # 60% scanner, 40% backtest

        ranked_opportunities = dict(sorted(opportunities.items(), key=combined_score, reverse=True))

        print(f"  ✅ Converted {len(ranked_opportunities)} opportunities with backtest validation")
        return ranked_opportunities

    def calculate_portfolio_performance(self, positions):
        """Calculate overall portfolio performance metrics"""
        if not positions:
            return {'total_pnl': 0, 'weighted_sharpe': 0, 'allocation_efficiency': 0}

        total_pnl = 0
        total_allocation = 0

        for symbol, pos_data in positions.items():
            pnl = pos_data.get('pnl', 0)
            allocation = pos_data.get('amount', 0) * pos_data.get('entry_price', 1) / pos_data.get('leverage', 1)

            total_pnl += pnl * allocation
            total_allocation += allocation

        avg_pnl = total_pnl / total_allocation if total_allocation > 0 else 0

        return {
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'total_allocation': total_allocation
        }

    def assess_cost_severity(self, opportunity_cost, market_data=None, position_data=None, market_context=None):
        """Assess the severity of opportunity cost using dynamic thresholds"""
        # Get dynamic thresholds if AI components are available
        if self.dynamic_thresholds and market_data and position_data and market_context:
            thresholds = self._get_dynamic_thresholds(market_data, position_data, market_context)
        else:
            thresholds = self.base_thresholds

        if opportunity_cost >= thresholds['high_cost']:
            return 'CRITICAL'  # High cost = rotate immediately
        elif opportunity_cost >= thresholds['moderate_cost']:
            return 'HIGH'  # Moderate cost = consider rotating after time
        elif opportunity_cost >= thresholds['acceptable_cost']:
            return 'MODERATE'  # Acceptable cost = monitor for rotation
        elif opportunity_cost >= 0:
            return 'LOW'
        else:
            return 'NEGATIVE'  # Position outperforming market - KEEP

    def generate_reallocation_recommendations(self, opportunity_costs, market_opportunities, total_capital, allocated_capital):
        """
        Generate LESS AGGRESSIVE reallocation recommendations
        """
        recommendations = []

        # AI-Enhanced: Use dynamic severity assessment for close candidates
        close_candidates = []
        for symbol, cost_data in opportunity_costs.items():
            # Get market context for dynamic assessment
            market_data = market_opportunities.get(symbol, {})
            position_data = {'position_value_usd': cost_data.get('allocated_capital', 0)}
            market_context = {'total_capital': total_capital, 'allocated_capital': allocated_capital}

            severity = self.assess_cost_severity(
                cost_data['opportunity_cost'],
                market_data={'market_volatility': market_data.get('volatility', 0.05)},
                position_data=position_data,
                market_context=market_context
            )

            if severity in ['CRITICAL', 'HIGH']:
                priority = 'CRITICAL' if severity == 'CRITICAL' else 'HIGH'
                close_candidates.append({
                    'symbol': symbol,
                    'opportunity_cost': cost_data['opportunity_cost'],
                    'capital_to_free': cost_data['allocated_capital'],
                    'priority': priority,
                    'ai_severity': severity
                })

        # Identify best market opportunities
        top_opportunities = list(market_opportunities.items())[:5]  # Top 5 by Sharpe

        # Calculate optimal reallocation
        available_capital = total_capital * 0.7 - allocated_capital  # 70% utilization target

        if available_capital > 0:
            # Allocate to top opportunities
            allocation_per_opportunity = available_capital / len(top_opportunities)

            for symbol, opp_data in top_opportunities:
                if allocation_per_opportunity > total_capital * 0.02:  # Min 2% allocation
                    recommendations.append({
                        'action': 'OPEN',
                        'symbol': symbol,
                        'allocation': allocation_per_opportunity,
                        'expected_return': opp_data['return'],
                        'sharpe_ratio': opp_data['sharpe'],
                        'reason': 'High Sharpe opportunity'
                    })

        # Add close recommendations
        for candidate in sorted(close_candidates, key=lambda x: x['opportunity_cost'], reverse=True):
            recommendations.append({
                'action': 'CLOSE',
                'symbol': candidate['symbol'],
                'capital_to_free': candidate['capital_to_free'],
                'opportunity_cost': candidate['opportunity_cost'],
                'reason': f"High opportunity cost ({candidate['opportunity_cost']*100:.1f}%)"
            })

        return recommendations

    def should_close_position(self, symbol, position_data, market_context):
        """
        Advanced AI-powered position closing decision
        Uses ML predictions, dynamic thresholds, correlation analysis, and behavioral factors
        GUARD CONDITION: Only close if unrealized P&L > +$0.15
        """
        # GUARD: Only consider closing if position has unrealized profit > +$0.15
        unrealized_pl_usd = position_data.get('unrealized_pl_usd', 0)

        if unrealized_pl_usd <= 0.15:
            # Position not profitable enough - DO NOT CLOSE regardless of opportunity cost
            return {
                'should_close': False,
                'opportunity_cost': 0,
                'reason': f'UPNL ${unrealized_pl_usd:.4f} below +$0.15 threshold - holding',
                'monitor': True
            }

        # Position has UPNL > +$0.15, now use advanced AI analysis
        print(f"🤖 AI Analysis for {symbol}: UPNL=${unrealized_pl_usd:.4f}")

        # Get current market data for AI analysis
        market_data = self._gather_market_data_for_ai(symbol, position_data, market_context)

        # Calculate dynamic thresholds based on current conditions
        current_thresholds = self._get_dynamic_thresholds(market_data, position_data, market_context)

        # Get ML predictions for opportunity cost
        ml_prediction = self._get_ml_opportunity_prediction(symbol, position_data, market_data)

        # Get correlation-enhanced opportunity cost
        correlation_analysis = self._get_correlation_enhanced_cost(symbol, position_data, market_context)

        # Apply behavioral economics adjustments
        behavioral_adjustments = self._apply_behavioral_factors(position_data, market_data)

        # Get RL-based recommendation
        rl_recommendation = self._get_rl_recommendation(position_data, market_data)

        # Combine all factors for final decision
        final_decision = self._make_final_closing_decision(
            symbol, position_data, market_data, current_thresholds,
            ml_prediction, correlation_analysis, behavioral_adjustments, rl_recommendation
        )

        # Log AI decision for learning
        self._log_ai_decision(symbol, position_data, final_decision)

        return final_decision

    def _gather_market_data_for_ai(self, symbol: str, position_data: Dict, market_context: Dict) -> Dict:
        """Gather comprehensive market data for AI analysis"""
        market_data = {
            'symbol': symbol,
            'current_pnl': position_data.get('pnl', 0),
            'holding_time_hours': position_data.get('holding_time_hours', 0),
            'position_size_pct': position_data.get('position_size_pct', 0),
            'unrealized_pl_usd': position_data.get('unrealized_pl_usd', 0)
        }

        # Add market performance data
        market_perf = market_context.get('market_performance', {}).get(symbol, {})
        market_data.update({
            'market_return_1h': market_perf.get('return_1h', 0),
            'market_return_24h': market_perf.get('return_24h', 0),
            'market_volatility': market_perf.get('volatility', 0.05),
            'correlation_with_market': market_perf.get('correlation', 0)
        })

        # Add technical indicators if available
        technical_data = market_context.get('technical_indicators', {}).get(symbol, {})
        market_data.update({
            'rsi': technical_data.get('rsi', 50),
            'macd_signal': technical_data.get('macd_signal', 0),
            'bb_position': technical_data.get('bb_position', 0),
            'volume_ratio': technical_data.get('volume_ratio', 1.0),
            'price_change_1h': technical_data.get('price_change_1h', 0),
            'price_change_24h': technical_data.get('price_change_24h', 0)
        })

        return market_data

    def _get_dynamic_thresholds(self, market_data: Dict, position_data: Dict, market_context: Dict) -> Dict:
        """Get dynamic thresholds using AI analysis"""
        # Get portfolio context
        portfolio_data = {
            'total_portfolio_value': market_context.get('total_capital', 1000),
            'current_drawdown_pct': market_context.get('current_drawdown_pct', 0),
            'recent_win_rate': market_context.get('recent_win_rate', 0.5),
            'margin_utilization': market_context.get('margin_utilization', 0.5)
        }

        dynamic_thresholds = self.dynamic_thresholds.calculate_dynamic_thresholds(
            market_data, position_data, portfolio_data
        )

        print(f"🎯 Dynamic thresholds: {self.dynamic_thresholds.get_threshold_explanation(dynamic_thresholds)}")
        return dynamic_thresholds

    def _get_ml_opportunity_prediction(self, symbol: str, position_data: Dict, market_data: Dict) -> Dict:
        """Get ML prediction for opportunity cost"""
        prediction = self.ml_predictor.predict_opportunity_cost(market_data)
        optimal_holding = self.ml_predictor.predict_optimal_holding_time(market_data)

        print(f"🎯 ML Prediction: ${prediction.get('predicted_cost', 0):.4f} (confidence: {prediction.get('confidence', 0):.2f})")
        print(f"⏰ Optimal Holding: {optimal_holding.get('optimal_hours', 4):.1f} hours")
        return {
            'predicted_cost': prediction.get('predicted_cost', market_data.get('current_opportunity_cost', 0)),
            'confidence': prediction.get('confidence', 0.5),
            'optimal_holding_hours': optimal_holding.get('optimal_hours', 4),
            'method': prediction.get('method', 'ml_prediction')
        }

    def _get_correlation_enhanced_cost(self, symbol: str, position_data: Dict, market_context: Dict) -> Dict:
        """Get correlation-enhanced opportunity cost analysis"""
        market_opportunities = market_context.get('market_opportunities', {})
        correlation_analysis = self.correlation_analyzer.calculate_opportunity_cost_with_correlations(
            symbol, position_data, market_opportunities
        )

        portfolio_cost = correlation_analysis.get('portfolio_enhanced_cost', 0)
        insights = correlation_analysis.get('correlation_insights', [])

        print(f"📊 Correlation analysis: Portfolio cost={portfolio_cost:.4f}, Insights: {len(insights)}")

        return {
            'enhanced_cost': portfolio_cost,
            'insights': insights,
            'sector_analysis': correlation_analysis.get('sector_analysis', {}),
            'market_regime': correlation_analysis.get('market_regime', {})
        }

    def _apply_behavioral_factors(self, position_data: Dict, market_data: Dict) -> Dict:
        """Apply behavioral economics adjustments"""
        adjustments = {
            'momentum_multiplier': 1.0,
            'herding_multiplier': 1.0,
            'loss_aversion_multiplier': 1.0,
            'disposition_multiplier': 1.0
        }

        # Momentum adjustment
        recent_momentum = market_data.get('price_change_1h', 0)
        if abs(recent_momentum) > self.behavioral_factors['momentum_threshold']:
            if recent_momentum > 0:
                adjustments['momentum_multiplier'] = 1.2  # Strong upward momentum - more patient
            else:
                adjustments['momentum_multiplier'] = 0.8  # Strong downward momentum - more aggressive

        # Loss aversion adjustment
        pnl = position_data.get('pnl', 0)
        if pnl < 0:
            # Losses hurt more - be more conservative
            adjustments['loss_aversion_multiplier'] = self.behavioral_factors['loss_aversion_ratio']
        else:
            # Profits feel good - be more patient
            adjustments['loss_aversion_multiplier'] = 1 / self.behavioral_factors['loss_aversion_ratio']

        # Disposition effect
        if self.behavioral_factors['disposition_effect']:
            if pnl < 0:
                adjustments['disposition_multiplier'] = 1.3  # Tendency to hold losers longer
            else:
                adjustments['disposition_multiplier'] = 0.9  # Tendency to sell winners faster

        total_multiplier = (
            adjustments['momentum_multiplier'] *
            adjustments['herding_multiplier'] *
            adjustments['loss_aversion_multiplier'] *
            adjustments['disposition_multiplier']
        )

        return {
            'total_multiplier': total_multiplier,
            'individual_adjustments': adjustments
        }

    def _get_rl_recommendation(self, position_data: Dict, market_data: Dict) -> Dict:
        """Get RL-based closing recommendation"""
        rl_result = self.rl_agent.get_closing_recommendation(position_data, {'current_opportunity_cost': market_data.get('current_opportunity_cost', 0), 'market_performance': {position_data.get('symbol', ''): {'volatility': market_data.get('market_volatility', 0.05), 'correlation': market_data.get('correlation_with_market', 0)}}})
        return rl_result

    def _make_final_closing_decision(self, symbol: str, position_data: Dict, market_data: Dict,
                                   thresholds: Dict, ml_pred: Dict, corr_analysis: Dict,
                                   behavioral_adj: Dict, rl_rec: Dict) -> Dict:
        """Make final closing decision combining all AI factors"""

        # Combine opportunity costs from different sources
        base_cost = market_data.get('current_opportunity_cost', 0)
        ml_cost = ml_pred.get('predicted_cost', base_cost)
        corr_cost = corr_analysis.get('enhanced_cost', base_cost)

        # Weighted ensemble
        ensemble_cost = (base_cost * 0.4 + ml_cost * 0.4 + corr_cost * 0.2)

        # Apply behavioral adjustments
        adjusted_cost = ensemble_cost * behavioral_adj['total_multiplier']

        # Apply time factors
        holding_time_mins = position_data.get('holding_time_hours', 0) * 60
        time_factor = min(holding_time_mins / 60, 2)
        final_cost = adjusted_cost * (1 + time_factor)

        # Check against dynamic thresholds
        unrealized_pl_usd = position_data.get('unrealized_pl_usd', 0)

        if final_cost >= thresholds['high_cost']:
            return {
                'should_close': True,
                'reason': f'AI: High opportunity cost ({final_cost*100:.1f}%) - ML pred: {ml_cost*100:.1f}%, Corr: {corr_cost*100:.1f}%',
                'opportunity_cost': final_cost,
                'urgency': 'IMMEDIATE',
                'ai_insights': {
                    'ml_confidence': ml_pred.get('confidence', 0.5),
                    'correlation_insights': corr_analysis.get('insights', []),
                    'behavioral_adjustments': behavioral_adj['individual_adjustments'],
                    'rl_recommendation': rl_rec.get('action', 'UNKNOWN'),
                    'rl_confidence': rl_rec.get('confidence', 0.5)
                }
            }
        elif final_cost >= thresholds['moderate_cost'] and holding_time_mins > 120:
            return {
                'should_close': True,
                'reason': f'AI: Moderate opportunity cost after 2hr+ ({final_cost*100:.1f}%) - time-based exit',
                'opportunity_cost': final_cost,
                'urgency': 'MEDIUM',
                'ai_insights': {
                    'ml_confidence': ml_pred.get('confidence', 0.5),
                    'correlation_insights': corr_analysis.get('insights', []),
                    'optimal_holding': ml_pred.get('optimal_holding_hours', 4),
                    'rl_recommendation': rl_rec.get('action', 'UNKNOWN'),
                    'rl_confidence': rl_rec.get('confidence', 0.5)
                }
            }
        elif holding_time_mins > 480:  # 8 hours max
            return {
                'should_close': True,
                'reason': f'AI: Maximum holding time exceeded ({holding_time_mins:.0f}min) - forced exit',
                'opportunity_cost': final_cost,
                'urgency': 'LOW'
            }
        else:
            # HOLD decision
            correlation_status = "correlated" if final_cost < thresholds['acceptable_cost'] else "diverging"
            behavioral_factors = behavioral_adj['individual_adjustments']

            return {
                'should_close': False,
                'reason': f'AI HOLD: {correlation_status} with market, opp_cost={final_cost*100:.1f}%, time={holding_time_mins:.0f}min',
                'opportunity_cost': final_cost,
                'urgency': 'NONE',
                'ai_insights': {
                    'ml_prediction': ml_cost,
                    'correlation_status': correlation_status,
                    'behavioral_factors': behavioral_factors,
                    'recommended_holding': ml_pred.get('optimal_holding_hours', 4),
                    'rl_recommendation': rl_rec.get('action', 'UNKNOWN'),
                    'rl_confidence': rl_rec.get('confidence', 0.5)
                }
            }

    def _log_ai_decision(self, symbol: str, position_data: Dict, decision: Dict):
        """Log AI decision for continuous learning"""
        decision_log = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'position_data': position_data,
            'decision': decision,
            'ai_components_used': {
                'dynamic_thresholds': self.dynamic_thresholds is not None,
                'ml_predictor': self.ml_predictor is not None,
                'correlation_analyzer': self.correlation_analyzer is not None
            }
        }

        self.opportunity_history.append(decision_log)

        # Keep only recent history
        if len(self.opportunity_history) > 1000:
            self.opportunity_history = self.opportunity_history[-1000:]

        print(f"📝 AI decision logged for {symbol}: {decision.get('should_close', False)}")

    def train_ai_models(self, historical_data: pd.DataFrame):
        """Train AI models with historical data"""
        print("🚀 Training AI models for opportunity cost optimization...")

        # Train ML models
        self.ml_predictor.train_models(historical_data)
        print("✅ ML models trained")

        # Train RL agent
        self.rl_agent.train_on_historical_data(historical_data, episodes=500)
        print("✅ RL agent trained")

        print("🎯 AI training complete - ready for advanced opportunity cost analysis")

    def get_markowitz_allocation(self, opportunities: Dict, current_positions: Dict,
                               total_capital: float, risk_tolerance: float = 0.5) -> Dict:
        """
        Get optimal capital allocation using Markowitz portfolio theory

        Args:
            opportunities: Market opportunities
            current_positions: Current portfolio positions
            total_capital: Total available capital
            risk_tolerance: Risk tolerance (0-1)

        Returns:
            dict: Markowitz optimization results
        """
        return self.markowitz_optimizer.optimize_portfolio(
            opportunities, current_positions, total_capital, risk_tolerance
        )

    def _fallback_markowitz_allocation(self, opportunities: Dict, total_capital: float) -> Dict:
        """Fallback allocation when Markowitz optimizer is unavailable"""
        print("⚠️ Using fallback allocation (Markowitz unavailable)")

        if not opportunities:
            return {'optimal_allocations': {}, 'sharpe_ratio': 0}

        n_opportunities = len(opportunities)
        equal_allocation = (total_capital * 0.7) / n_opportunities

        allocations = {}
        for symbol in opportunities.keys():
            allocations[symbol] = {
                'weight': 1.0 / n_opportunities,
                'allocation_usd': equal_allocation,
                'action': 'OPEN'
            }

        return {
            'optimal_allocations': allocations,
            'expected_portfolio_return': 0.05,
            'sharpe_ratio': 0.5,
            'diversification_score': 0.8
        }

    def get_rl_closing_recommendation(self, position_data: Dict, market_context: Dict) -> Dict:
        """
        Get closing recommendation from trained RL agent

        Args:
            position_data: Current position data
            market_context: Current market context

        Returns:
            dict: RL-based closing recommendation
        """
        return self.rl_agent.get_closing_recommendation(position_data, market_context)

    def optimize_capital_allocation(self, current_positions, market_opportunities, total_capital):
        """
        Optimize capital allocation using opportunity cost analysis
        """
        # Calculate current allocation efficiency
        current_allocation = sum(
            pos['amount'] * pos['entry_price'] / pos.get('leverage', 1)
            for pos in current_positions.values()
        )

        # Find optimal allocation using Sharpe ratio maximization
        optimal_allocations = {}

        # Keep some allocation to current positions if performing well
        performing_positions = {
            symbol: pos for symbol, pos in current_positions.items()
            if pos.get('pnl', 0) > -0.1  # Less than 10% loss
        }

        # Allocate remaining capital to top opportunities
        remaining_capital = total_capital * 0.7 - current_allocation
        top_opportunities = list(market_opportunities.items())[:3]

        if remaining_capital > 0 and top_opportunities:
            allocation_per_opp = remaining_capital / len(top_opportunities)

            for symbol, opp_data in top_opportunities:
                if allocation_per_opp > total_capital * 0.02:  # Minimum allocation
                    optimal_allocations[symbol] = {
                        'allocation': allocation_per_opp,
                        'expected_sharpe': opp_data['sharpe'],
                        'reason': 'High opportunity cost alternative'
                    }

        return {
            'optimal_allocations': optimal_allocations,
            'capital_efficiency': current_allocation / (total_capital * 0.7),
            'reallocation_needed': remaining_capital > total_capital * 0.05
        }