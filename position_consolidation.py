#!/usr/bin/env python3
"""
Position Consolidation Analyzer for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Evaluates if multiple positions can be:
- Merged (similar assets, same direction)
- Hedged more effectively (opposite positions)
- Closed (worst performers to free capital)

Focuses on:
- Reducing overexposure
- Freeing up margin
- Improving capital efficiency

Author: Claude + Grok Consortium
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import numpy as np

# Results file
RESULTS_FILE = '/root/ai_xyz/position_consolidation_results.json'


class ConsolidationAction(Enum):
    CLOSE = "CLOSE"           # Close position entirely
    REDUCE = "REDUCE"         # Reduce position size
    MERGE = "MERGE"           # Merge with similar position
    HEDGE = "HEDGE"           # Hedge with opposite position
    KEEP = "KEEP"             # No action needed


@dataclass
class ConsolidationRecommendation:
    """Recommendation for position consolidation."""
    symbol: str
    action: ConsolidationAction
    reason: str
    priority: int  # 1 = highest priority
    estimated_margin_freed: float
    related_symbol: Optional[str] = None
    details: Optional[Dict] = None


class PositionConsolidationAnalyzer:
    """
    Analyzes positions for consolidation opportunities.

    Identifies:
    - Correlated positions (same sector/type)
    - Opposing positions (natural hedges)
    - Worst performers (candidates for closure)
    - Overweight positions
    """

    # Sector/category mappings for correlation detection
    ASSET_CATEGORIES = {
        'BTC': 'major',
        'ETH': 'major',
        'BNB': 'exchange',
        'SOL': 'layer1',
        'AVAX': 'layer1',
        'NEAR': 'layer1',
        'APT': 'layer1',
        'SUI': 'layer1',
        'LINK': 'oracle',
        'DOGE': 'meme',
        'SHIB': 'meme',
        'PEPE': 'meme',
        'WIF': 'meme',
        'FLOKI': 'meme',
        'UNI': 'defi',
        'AAVE': 'defi',
        'CRV': 'defi',
        'MKR': 'defi',
        'COMP': 'defi',
        'SUSHI': 'defi',
        'FIL': 'storage',
        'AR': 'storage',
        'AXS': 'gaming',
        'SAND': 'gaming',
        'MANA': 'gaming',
        'ENJ': 'gaming',
        'GALA': 'gaming',
        'IMX': 'gaming',
        'MATIC': 'layer2',
        'ARB': 'layer2',
        'OP': 'layer2',
        'XRP': 'payment',
        'XLM': 'payment',
        'ALGO': 'payment',
        'ATOM': 'cosmos',
        'OSMO': 'cosmos',
        'INJ': 'cosmos'
    }

    def __init__(self):
        self.recommendations: List[ConsolidationRecommendation] = []

    def _get_position_state(self) -> Dict:
        """Get current position state."""
        try:
            with open('/root/ai_xyz/position_state.json', 'r') as f:
                return json.load(f)
        except Exception:
            return {}

    def _extract_base_symbol(self, symbol: str) -> str:
        """Extract base asset from trading pair."""
        # Handle formats like "BTC/USDT:USDT" or "BTCUSDT"
        if '/' in symbol:
            return symbol.split('/')[0]
        return symbol.replace('USDT', '').replace(':USDT', '')

    def _get_category(self, symbol: str) -> str:
        """Get asset category for correlation analysis."""
        base = self._extract_base_symbol(symbol)
        return self.ASSET_CATEGORIES.get(base, 'other')

    def analyze_correlation_exposure(self, positions: Dict) -> List[Dict]:
        """
        Analyze exposure to correlated assets.

        Returns groups of positions in same category.
        """
        category_positions = {}

        for symbol, pos_data in positions.items():
            category = self._get_category(symbol)
            if category not in category_positions:
                category_positions[category] = []

            category_positions[category].append({
                'symbol': symbol,
                'side': pos_data.get('side', 'unknown'),
                'amount': pos_data.get('amount', 0),
                'upnl': pos_data.get('unrealized_pnl', 0)
            })

        # Find overexposed categories (2+ positions in same category)
        overexposed = []
        for category, positions_list in category_positions.items():
            if len(positions_list) >= 2:
                total_exposure = sum(p['amount'] for p in positions_list)
                overexposed.append({
                    'category': category,
                    'positions': positions_list,
                    'count': len(positions_list),
                    'total_exposure': total_exposure
                })

        return sorted(overexposed, key=lambda x: x['count'], reverse=True)

    def analyze_opposing_positions(self, positions: Dict) -> List[Dict]:
        """
        Find naturally hedged positions (opposite directions).

        These can potentially be merged/closed to free capital.
        """
        long_positions = {}
        short_positions = {}

        for symbol, pos_data in positions.items():
            base = self._extract_base_symbol(symbol)
            side = pos_data.get('side', '').lower()

            if side in ['buy', 'long']:
                long_positions[base] = {'symbol': symbol, 'data': pos_data}
            elif side in ['sell', 'short']:
                short_positions[base] = {'symbol': symbol, 'data': pos_data}

        # Find assets with both long and short positions
        opposing = []
        for base in set(long_positions.keys()) & set(short_positions.keys()):
            long_data = long_positions[base]
            short_data = short_positions[base]

            net_position = (long_data['data'].get('amount', 0) -
                          short_data['data'].get('amount', 0))

            opposing.append({
                'base_asset': base,
                'long_symbol': long_data['symbol'],
                'short_symbol': short_data['symbol'],
                'long_amount': long_data['data'].get('amount', 0),
                'short_amount': short_data['data'].get('amount', 0),
                'net_position': net_position,
                'can_consolidate': True
            })

        return opposing

    def analyze_worst_performers(self, positions: Dict, zones: Dict,
                                averaging_steps: Dict) -> List[Dict]:
        """
        Identify worst performing positions for potential closure.

        Criteria:
        - High averaging steps (3+)
        - In AVERAGING zone
        - Large unrealized loss
        """
        worst = []

        for symbol, pos_data in positions.items():
            zone = zones.get(symbol, 'NEUTRAL')
            steps = averaging_steps.get(symbol, 0)
            upnl = pos_data.get('unrealized_pnl', 0)
            upnl_pct = pos_data.get('upnl_pct', 0)

            # Score based on multiple factors
            score = 0
            reasons = []

            if steps >= 4:
                score += 40
                reasons.append(f"High averaging ({steps} steps)")
            elif steps >= 3:
                score += 25
                reasons.append(f"Moderate averaging ({steps} steps)")

            if zone == 'AVERAGING':
                score += 30
                reasons.append("In AVERAGING zone")

            if upnl_pct < -30:
                score += 30
                reasons.append(f"Large loss ({upnl_pct:.1f}%)")
            elif upnl_pct < -20:
                score += 20
                reasons.append(f"Significant loss ({upnl_pct:.1f}%)")

            if score >= 40:  # Threshold for consideration
                worst.append({
                    'symbol': symbol,
                    'score': score,
                    'zone': zone,
                    'averaging_steps': steps,
                    'upnl': upnl,
                    'upnl_pct': upnl_pct,
                    'reasons': reasons
                })

        return sorted(worst, key=lambda x: x['score'], reverse=True)

    def generate_recommendations(self) -> List[ConsolidationRecommendation]:
        """Generate consolidation recommendations."""
        self.recommendations = []

        state = self._get_position_state()
        positions = state.get('active_positions', {})
        zones = state.get('zones', {})
        averaging_steps = state.get('averaging_steps', {})

        if not positions:
            return []

        priority = 1

        # 1. Check for opposing positions (highest priority for capital efficiency)
        opposing = self.analyze_opposing_positions(positions)
        for opp in opposing:
            self.recommendations.append(ConsolidationRecommendation(
                symbol=opp['long_symbol'],
                action=ConsolidationAction.HEDGE,
                reason=f"Natural hedge exists with {opp['short_symbol']}",
                priority=priority,
                estimated_margin_freed=min(opp['long_amount'], opp['short_amount']) * 5,
                related_symbol=opp['short_symbol'],
                details=opp
            ))
            priority += 1

        # 2. Check worst performers
        worst = self.analyze_worst_performers(positions, zones, averaging_steps)
        for w in worst[:5]:  # Top 5 worst
            action = ConsolidationAction.CLOSE if w['score'] >= 60 else ConsolidationAction.REDUCE
            self.recommendations.append(ConsolidationRecommendation(
                symbol=w['symbol'],
                action=action,
                reason='; '.join(w['reasons']),
                priority=priority,
                estimated_margin_freed=5.0,  # Approx $5 per position
                details=w
            ))
            priority += 1

        # 3. Check correlated exposure
        correlated = self.analyze_correlation_exposure(positions)
        for group in correlated:
            if group['count'] >= 3:  # 3+ positions in same category
                # Suggest reducing the worst performer in the category
                category_positions = group['positions']
                worst_in_category = min(category_positions, key=lambda x: x['upnl'])

                self.recommendations.append(ConsolidationRecommendation(
                    symbol=worst_in_category['symbol'],
                    action=ConsolidationAction.REDUCE,
                    reason=f"Overexposed to {group['category']} sector ({group['count']} positions)",
                    priority=priority,
                    estimated_margin_freed=2.5,
                    details={'category': group['category'], 'positions': category_positions}
                ))
                priority += 1

        return sorted(self.recommendations, key=lambda x: x.priority)

    def run_analysis(self) -> Dict:
        """Run full consolidation analysis."""
        print("\n" + "="*70)
        print("POSITION CONSOLIDATION ANALYSIS")
        print("="*70)
        print(f"Analysis Time: {datetime.now().isoformat()}")

        state = self._get_position_state()
        positions = state.get('active_positions', {})
        zones = state.get('zones', {})
        averaging_steps = state.get('averaging_steps', {})

        print(f"\nActive Positions: {len(positions)}")

        results = {
            'timestamp': datetime.now().isoformat(),
            'total_positions': len(positions),
            'analysis': {}
        }

        # 1. Opposing positions
        print("\n" + "-"*50)
        print("OPPOSING POSITIONS (Natural Hedges)")
        print("-"*50)
        opposing = self.analyze_opposing_positions(positions)
        results['analysis']['opposing'] = opposing

        if opposing:
            for opp in opposing:
                print(f"  {opp['base_asset']}: LONG {opp['long_amount']:.2f} / SHORT {opp['short_amount']:.2f}")
                print(f"    Net: {opp['net_position']:.2f}")
        else:
            print("  No opposing positions found")

        # 2. Correlated exposure
        print("\n" + "-"*50)
        print("CORRELATED EXPOSURE (Same Sector)")
        print("-"*50)
        correlated = self.analyze_correlation_exposure(positions)
        results['analysis']['correlated'] = correlated

        for group in correlated:
            symbols = [p['symbol'].replace('/USDT:USDT', '') for p in group['positions']]
            print(f"  {group['category'].upper()}: {group['count']} positions")
            print(f"    {', '.join(symbols)}")

        if not correlated:
            print("  No significant correlation exposure")

        # 3. Worst performers
        print("\n" + "-"*50)
        print("WORST PERFORMERS")
        print("-"*50)
        worst = self.analyze_worst_performers(positions, zones, averaging_steps)
        results['analysis']['worst_performers'] = worst

        for w in worst[:5]:
            symbol_short = w['symbol'].replace('/USDT:USDT', '')
            print(f"  {symbol_short}: Score {w['score']}")
            print(f"    Zone: {w['zone']}, Steps: {w['averaging_steps']}, UPNL: {w['upnl_pct']:.1f}%")
            print(f"    Reasons: {'; '.join(w['reasons'])}")

        if not worst:
            print("  No significant underperformers")

        # 4. Recommendations
        print("\n" + "-"*50)
        print("RECOMMENDATIONS")
        print("-"*50)
        recommendations = self.generate_recommendations()
        results['recommendations'] = [
            {
                'symbol': r.symbol,
                'action': r.action.value,
                'reason': r.reason,
                'priority': r.priority,
                'estimated_margin_freed': r.estimated_margin_freed,
                'related_symbol': r.related_symbol
            } for r in recommendations
        ]

        if recommendations:
            total_margin_freed = sum(r.estimated_margin_freed for r in recommendations)
            print(f"\n  Total potential margin freed: ${total_margin_freed:.2f}")
            print()

            for rec in recommendations[:10]:
                symbol_short = rec.symbol.replace('/USDT:USDT', '')
                action_emoji = {
                    ConsolidationAction.CLOSE: '❌',
                    ConsolidationAction.REDUCE: '📉',
                    ConsolidationAction.MERGE: '🔗',
                    ConsolidationAction.HEDGE: '🛡️',
                    ConsolidationAction.KEEP: '✅'
                }
                emoji = action_emoji.get(rec.action, '•')
                print(f"  #{rec.priority} {emoji} {rec.action.value} {symbol_short}")
                print(f"      Reason: {rec.reason}")
                print(f"      Est. margin freed: ${rec.estimated_margin_freed:.2f}")
        else:
            print("  No consolidation actions recommended")

        # Summary
        print("\n" + "="*70)
        print("SUMMARY")
        print("="*70)
        print(f"  Positions analyzed: {len(positions)}")
        print(f"  Opposing pairs found: {len(opposing)}")
        print(f"  Correlated groups: {len(correlated)}")
        print(f"  Underperformers identified: {len(worst)}")
        print(f"  Total recommendations: {len(recommendations)}")

        results['summary'] = {
            'positions_analyzed': len(positions),
            'opposing_pairs': len(opposing),
            'correlated_groups': len(correlated),
            'underperformers': len(worst),
            'total_recommendations': len(recommendations)
        }

        # Save results
        with open(RESULTS_FILE, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\nResults saved to: {RESULTS_FILE}")

        return results


def main():
    """Run position consolidation analysis."""
    analyzer = PositionConsolidationAnalyzer()
    results = analyzer.run_analysis()
    return results


if __name__ == "__main__":
    main()
