#!/usr/bin/env python3
"""
Closed Position Reconciliation Service
Analyzes closed positions from last 24 hours and recommends improvements
"""
import ccxt
import json
import os
import pytz
from datetime import datetime, timedelta
from collections import defaultdict
from dotenv import load_dotenv
import logging
from typing import Dict, List, Any, Optional

load_dotenv('/app/.env')

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/app/position_reconciliation.log'),
        logging.StreamHandler()
    ]
)

class ClosedPositionReconciler:
    def __init__(self):
        self.api_key = os.getenv('BITGET_API_KEY')
        self.api_secret = os.getenv('BITGET_API_SECRET')
        self.api_passphrase = os.getenv('BITGET_API_PASSPHRASE', '')

        self.exchange = ccxt.bitget({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'password': self.api_passphrase,
            'enableRateLimit': True,
            'rateLimit': 50,
            'options': {
                'defaultType': 'swap',
            }
        })

        # Load system configuration
        with open('/app/runtime_config.json', 'r') as f:
            self.config = json.load(f)

        # Load position state
        try:
            with open('/app/position_state.json', 'r') as f:
                self.position_state = json.load(f)
        except:
            self.position_state = {}

        self.report = {
            'timestamp': datetime.now().isoformat(),
            'closed_positions': [],
            'performance_metrics': {},
            'improvement_recommendations': [],
            'system_compliance': {},
            'anomalies': []
        }

    def fetch_closed_positions(self, hours=24):
        """Fetch closed positions from the last N hours"""
        try:
            since = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)
            closed_orders = []

            # Fetch closed orders from exchange
            try:
                # Get all orders (including closed)
                symbols = ['BTC/USDT:USDT', 'ETH/USDT:USDT']  # Start with major pairs

                # Get all traded symbols from recent history
                markets = self.exchange.load_markets()

                for symbol in markets:
                    if ':USDT' in symbol:
                        try:
                            orders = self.exchange.fetch_closed_orders(
                                symbol,
                                since=since,
                                limit=100
                            )
                            if orders:
                                closed_orders.extend(orders)
                        except Exception as e:
                            if 'symbol' not in str(e).lower():
                                logging.debug(f"Error fetching {symbol}: {e}")

            except Exception as e:
                logging.warning(f"Error fetching closed orders: {e}")

            # Group orders by position/symbol
            positions_map = defaultdict(list)
            for order in closed_orders:
                key = f"{order['symbol']}_{order.get('clientOrderId', order['id'][:8])}"
                positions_map[key].append(order)

            # Analyze each closed position
            closed_positions = []
            for position_key, orders in positions_map.items():
                position = self.analyze_position(position_key, orders)
                if position:
                    closed_positions.append(position)

            self.report['closed_positions'] = closed_positions
            logging.info(f"Found {len(closed_positions)} closed positions in last {hours} hours")

            return closed_positions

        except Exception as e:
            logging.error(f"Error fetching closed positions: {e}")
            return []

    def analyze_position(self, position_key: str, orders: List[Dict]) -> Optional[Dict]:
        """Analyze a single closed position"""
        if not orders:
            return None

        try:
            symbol = orders[0]['symbol']

            # Calculate position metrics
            total_buy_volume = 0
            total_sell_volume = 0
            total_buy_cost = 0
            total_sell_proceeds = 0
            fees_paid = 0

            entry_time = None
            exit_time = None

            for order in orders:
                if order['filled'] > 0:
                    if order['side'] == 'buy':
                        total_buy_volume += order['filled']
                        total_buy_cost += order['filled'] * order['average']
                    else:
                        total_sell_volume += order['filled']
                        total_sell_proceeds += order['filled'] * order['average']

                    fees_paid += order.get('fee', {}).get('cost', 0)

                    # Track times
                    order_time = order['timestamp']
                    if not entry_time or order_time < entry_time:
                        entry_time = order_time
                    if not exit_time or order_time > exit_time:
                        exit_time = order_time

            # Skip if no actual trades
            if total_buy_volume == 0 and total_sell_volume == 0:
                return None

            # Determine position side
            is_long = total_buy_volume > total_sell_volume

            # Calculate PnL
            if is_long:
                entry_price = total_buy_cost / total_buy_volume if total_buy_volume > 0 else 0
                exit_price = total_sell_proceeds / total_sell_volume if total_sell_volume > 0 else 0
                volume = min(total_buy_volume, total_sell_volume)
                pnl = (exit_price - entry_price) * volume - fees_paid
            else:
                entry_price = total_sell_proceeds / total_sell_volume if total_sell_volume > 0 else 0
                exit_price = total_buy_cost / total_buy_volume if total_buy_volume > 0 else 0
                volume = min(total_buy_volume, total_sell_volume)
                pnl = (entry_price - exit_price) * volume - fees_paid

            # Calculate metrics
            pnl_percent = (pnl / (entry_price * volume)) * 100 if entry_price > 0 else 0
            duration = (exit_time - entry_time) / (1000 * 60 * 60) if entry_time and exit_time else 0  # hours

            position_analysis = {
                'symbol': symbol,
                'side': 'LONG' if is_long else 'SHORT',
                'entry_price': entry_price,
                'exit_price': exit_price,
                'volume': volume,
                'pnl': pnl,
                'pnl_percent': pnl_percent,
                'fees_paid': fees_paid,
                'duration_hours': duration,
                'entry_time': datetime.fromtimestamp(entry_time/1000).isoformat() if entry_time else None,
                'exit_time': datetime.fromtimestamp(exit_time/1000).isoformat() if exit_time else None,
                'num_orders': len(orders),
                'averaging_detected': len([o for o in orders if o['side'] == ('buy' if is_long else 'sell')]) > 1
            }

            return position_analysis

        except Exception as e:
            logging.error(f"Error analyzing position {position_key}: {e}")
            return None

    def analyze_performance_metrics(self):
        """Calculate overall performance metrics"""
        positions = self.report['closed_positions']

        if not positions:
            self.report['performance_metrics'] = {
                'total_positions': 0,
                'message': 'No closed positions found'
            }
            return

        # Calculate metrics
        total_pnl = sum(p['pnl'] for p in positions)
        winning_positions = [p for p in positions if p['pnl'] > 0]
        losing_positions = [p for p in positions if p['pnl'] < 0]

        metrics = {
            'total_positions': len(positions),
            'winning_positions': len(winning_positions),
            'losing_positions': len(losing_positions),
            'win_rate': (len(winning_positions) / len(positions) * 100) if positions else 0,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / len(positions) if positions else 0,
            'avg_win': sum(p['pnl'] for p in winning_positions) / len(winning_positions) if winning_positions else 0,
            'avg_loss': sum(p['pnl'] for p in losing_positions) / len(losing_positions) if losing_positions else 0,
            'total_fees': sum(p['fees_paid'] for p in positions),
            'positions_with_averaging': len([p for p in positions if p['averaging_detected']]),
            'avg_duration_hours': sum(p['duration_hours'] for p in positions) / len(positions) if positions else 0
        }

        # Calculate profit factor
        gross_profit = sum(p['pnl'] for p in winning_positions)
        gross_loss = abs(sum(p['pnl'] for p in losing_positions))
        metrics['profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        self.report['performance_metrics'] = metrics

    def check_system_compliance(self):
        """Check if closed positions followed system rules"""
        compliance = {
            'averaging_threshold_compliance': 0,
            'surplus_dump_compliance': 0,
            'stop_loss_compliance': 0,
            'fibonacci_sizing_compliance': 0,
            'violations': []
        }

        positions = self.report['closed_positions']

        for position in positions:
            # Check for violations

            # 1. Stop loss violation (positions that lost more than 70%)
            if position['pnl_percent'] < -70:
                compliance['violations'].append({
                    'symbol': position['symbol'],
                    'type': 'STOP_LOSS_VIOLATION',
                    'details': f"Lost {position['pnl_percent']:.2f}% (stop loss should be at -70%)"
                })

            # 2. Check if averaging happened when it should have
            if position['pnl_percent'] < -42 and not position['averaging_detected']:
                compliance['violations'].append({
                    'symbol': position['symbol'],
                    'type': 'AVERAGING_NOT_TRIGGERED',
                    'details': f"Lost {position['pnl_percent']:.2f}% without averaging (threshold: -42%)"
                })

            # 3. Check for premature exits (profitable positions closed too early)
            if 0 < position['pnl_percent'] < 5:
                compliance['violations'].append({
                    'symbol': position['symbol'],
                    'type': 'PREMATURE_EXIT',
                    'details': f"Closed at {position['pnl_percent']:.2f}% profit (take profit threshold: $5)"
                })

        # Calculate compliance rates
        total_positions = len(positions)
        if total_positions > 0:
            compliance['stop_loss_compliance'] = (total_positions - len([v for v in compliance['violations'] if v['type'] == 'STOP_LOSS_VIOLATION'])) / total_positions * 100
            compliance['averaging_threshold_compliance'] = (total_positions - len([v for v in compliance['violations'] if v['type'] == 'AVERAGING_NOT_TRIGGERED'])) / total_positions * 100

        self.report['system_compliance'] = compliance

    def generate_recommendations(self):
        """Generate improvement recommendations based on analysis"""
        recommendations = []
        metrics = self.report['performance_metrics']
        compliance = self.report['system_compliance']

        # 1. Win rate improvement
        if metrics.get('win_rate', 0) < 50:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'ENTRY_LOGIC',
                'issue': f"Low win rate: {metrics.get('win_rate', 0):.1f}%",
                'recommendation': "Improve entry signals with better market regime detection and momentum confirmation"
            })

        # 2. Risk management
        if metrics.get('avg_loss', 0) < -10:
            recommendations.append({
                'priority': 'HIGH',
                'category': 'RISK_MANAGEMENT',
                'issue': f"High average loss: ${metrics.get('avg_loss', 0):.2f}",
                'recommendation': "Implement tighter stop losses or improve averaging logic to reduce losses"
            })

        # 3. Averaging effectiveness
        positions_with_averaging = metrics.get('positions_with_averaging', 0)
        total_positions = metrics.get('total_positions', 0)
        if total_positions > 0 and positions_with_averaging > 0:
            averaging_positions = [p for p in self.report['closed_positions'] if p['averaging_detected']]
            avg_pnl_with_averaging = sum(p['pnl'] for p in averaging_positions) / len(averaging_positions) if averaging_positions else 0

            if avg_pnl_with_averaging < 0:
                recommendations.append({
                    'priority': 'MEDIUM',
                    'category': 'AVERAGING_STRATEGY',
                    'issue': f"Averaging positions losing money: ${avg_pnl_with_averaging:.2f} avg",
                    'recommendation': "Review momentum guardian signals and consider tighter averaging thresholds"
                })

        # 4. Compliance issues
        if compliance.get('violations'):
            violation_types = set(v['type'] for v in compliance['violations'])
            for vtype in violation_types:
                count = len([v for v in compliance['violations'] if v['type'] == vtype])
                recommendations.append({
                    'priority': 'HIGH',
                    'category': 'SYSTEM_COMPLIANCE',
                    'issue': f"{count} {vtype} violations detected",
                    'recommendation': f"Fix {vtype.replace('_', ' ').lower()} logic in autonomous_sync.py"
                })

        # 5. Profit optimization
        if metrics.get('profit_factor', 0) < 1.5:
            recommendations.append({
                'priority': 'MEDIUM',
                'category': 'PROFIT_OPTIMIZATION',
                'issue': f"Low profit factor: {metrics.get('profit_factor', 0):.2f}",
                'recommendation': "Improve surplus dump timing and take profit logic to capture more gains"
            })

        self.report['improvement_recommendations'] = recommendations

    def detect_anomalies(self):
        """Detect anomalous patterns in closed positions"""
        anomalies = []
        positions = self.report['closed_positions']

        for position in positions:
            # 1. Unusually short positions (less than 1 hour)
            if position['duration_hours'] < 1 and position['num_orders'] > 2:
                anomalies.append({
                    'symbol': position['symbol'],
                    'type': 'RAPID_TRADING',
                    'details': f"Position lasted only {position['duration_hours']:.2f} hours with {position['num_orders']} orders"
                })

            # 2. Excessive fees
            if position['fees_paid'] > abs(position['pnl']) * 0.5:
                anomalies.append({
                    'symbol': position['symbol'],
                    'type': 'HIGH_FEES',
                    'details': f"Fees ({position['fees_paid']:.2f}) are {position['fees_paid']/abs(position['pnl'])*100:.1f}% of PnL"
                })

            # 3. Large losses without averaging
            if position['pnl_percent'] < -20 and not position['averaging_detected']:
                anomalies.append({
                    'symbol': position['symbol'],
                    'type': 'NO_AVERAGING_ON_LOSS',
                    'details': f"Lost {position['pnl_percent']:.1f}% without any averaging attempts"
                })

        self.report['anomalies'] = anomalies

    def generate_report(self):
        """Generate comprehensive reconciliation report"""
        logging.info("=" * 80)
        logging.info("CLOSED POSITION RECONCILIATION REPORT")
        logging.info("=" * 80)
        logging.info(f"Report Generated: {self.report['timestamp']}")
        logging.info("")

        # Performance Summary
        metrics = self.report['performance_metrics']
        logging.info("PERFORMANCE SUMMARY")
        logging.info("-" * 40)
        logging.info(f"Total Positions Closed: {metrics.get('total_positions', 0)}")
        logging.info(f"Win Rate: {metrics.get('win_rate', 0):.1f}%")
        logging.info(f"Total PnL: ${metrics.get('total_pnl', 0):.2f}")
        logging.info(f"Average PnL: ${metrics.get('avg_pnl', 0):.2f}")
        logging.info(f"Profit Factor: {metrics.get('profit_factor', 0):.2f}")
        logging.info(f"Positions with Averaging: {metrics.get('positions_with_averaging', 0)}")
        logging.info("")

        # System Compliance
        compliance = self.report['system_compliance']
        logging.info("SYSTEM COMPLIANCE")
        logging.info("-" * 40)
        logging.info(f"Stop Loss Compliance: {compliance.get('stop_loss_compliance', 0):.1f}%")
        logging.info(f"Averaging Compliance: {compliance.get('averaging_threshold_compliance', 0):.1f}%")

        if compliance.get('violations'):
            logging.info(f"\nViolations Found: {len(compliance['violations'])}")
            for violation in compliance['violations'][:5]:  # Show first 5
                logging.info(f"  - {violation['symbol']}: {violation['type']}")

        logging.info("")

        # Recommendations
        recs = self.report['improvement_recommendations']
        if recs:
            logging.info("IMPROVEMENT RECOMMENDATIONS")
            logging.info("-" * 40)

            # Sort by priority
            high_priority = [r for r in recs if r['priority'] == 'HIGH']
            medium_priority = [r for r in recs if r['priority'] == 'MEDIUM']

            for rec in high_priority:
                logging.info(f"🔴 HIGH PRIORITY - {rec['category']}")
                logging.info(f"   Issue: {rec['issue']}")
                logging.info(f"   Recommendation: {rec['recommendation']}")
                logging.info("")

            for rec in medium_priority:
                logging.info(f"🟡 MEDIUM PRIORITY - {rec['category']}")
                logging.info(f"   Issue: {rec['issue']}")
                logging.info(f"   Recommendation: {rec['recommendation']}")
                logging.info("")

        # Anomalies
        if self.report.get('anomalies'):
            logging.info("ANOMALIES DETECTED")
            logging.info("-" * 40)
            for anomaly in self.report['anomalies'][:5]:  # Show first 5
                logging.info(f"  - {anomaly['symbol']}: {anomaly['type']}")
                logging.info(f"    {anomaly['details']}")

        logging.info("")
        logging.info("=" * 80)

        # Save report to file
        report_file = f"/app/reports/reconciliation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        os.makedirs('/app/reports', exist_ok=True)

        with open(report_file, 'w') as f:
            json.dump(self.report, f, indent=2)

        logging.info(f"Full report saved to: {report_file}")

        return self.report

    def run(self):
        """Main execution method"""
        try:
            logging.info("Starting closed position reconciliation...")

            # Fetch and analyze closed positions
            self.fetch_closed_positions(hours=24)

            # Perform analysis
            self.analyze_performance_metrics()
            self.check_system_compliance()
            self.generate_recommendations()
            self.detect_anomalies()

            # Generate and display report
            self.generate_report()

            return self.report

        except Exception as e:
            logging.error(f"Error running reconciliation: {e}")
            return None

if __name__ == "__main__":
    reconciler = ClosedPositionReconciler()
    report = reconciler.run()