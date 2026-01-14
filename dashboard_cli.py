#!/usr/bin/env python3
"""
CLI Performance Dashboard for AI-XYZ Trading System
V1.0.0 - January 14, 2026

Terminal-based dashboard displaying real-time metrics.
No external dependencies required.

Usage: python3 dashboard_cli.py

Author: Claude + Grok Consortium
"""

import json
import os
import sys
import redis
from datetime import datetime
import time

# Colors for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def get_position_state():
    """Get position state from file."""
    try:
        with open('/root/ai_xyz/position_state.json', 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def get_hedge_state():
    """Get hedge state from Redis."""
    try:
        r = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
        state = r.get('hedge_gateway:state')
        if state:
            return json.loads(state)
    except Exception:
        pass
    return {'hedges': {}}


def get_adaptive_thresholds():
    """Get current adaptive thresholds."""
    try:
        with open('/root/ai_xyz/adaptive_thresholds.json', 'r') as f:
            return json.load(f)
    except Exception:
        return {}


def clear_screen():
    """Clear terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')


def format_pnl(value):
    """Format P&L with color."""
    if value > 0:
        return f"{Colors.GREEN}+${value:.2f}{Colors.ENDC}"
    elif value < 0:
        return f"{Colors.RED}${value:.2f}{Colors.ENDC}"
    return f"${value:.2f}"


def format_regime(regime):
    """Format regime with color."""
    colors = {
        'HIGH_VOLATILITY': Colors.RED,
        'TRENDING': Colors.CYAN,
        'RANGING': Colors.YELLOW,
        'NORMAL': Colors.GREEN
    }
    color = colors.get(regime, Colors.ENDC)
    return f"{color}{regime}{Colors.ENDC}"


def format_zone(zone):
    """Format zone with color."""
    colors = {
        'AVERAGING': Colors.RED,
        'PROFIT_TAKING': Colors.GREEN,
        'SURPLUS_DUMP': Colors.YELLOW,
        'NEUTRAL': Colors.BLUE
    }
    color = colors.get(zone, Colors.ENDC)
    return f"{color}{zone}{Colors.ENDC}"


def print_header():
    """Print dashboard header."""
    print(f"\n{Colors.CYAN}{'='*70}{Colors.ENDC}")
    print(f"{Colors.BOLD}{Colors.CYAN}       🤖 AI-XYZ PERFORMANCE DASHBOARD{Colors.ENDC}")
    print(f"{Colors.CYAN}{'='*70}{Colors.ENDC}")
    print(f"  Updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{Colors.CYAN}{'='*70}{Colors.ENDC}\n")


def print_section(title):
    """Print section header."""
    print(f"\n{Colors.BOLD}{Colors.BLUE}▶ {title}{Colors.ENDC}")
    print(f"{Colors.BLUE}{'─'*50}{Colors.ENDC}")


def display_dashboard():
    """Display the dashboard."""
    clear_screen()
    print_header()

    # Get data
    position_state = get_position_state()
    hedge_state = get_hedge_state()
    thresholds = get_adaptive_thresholds()

    active_positions = position_state.get('active_positions', {})
    averaging_steps = position_state.get('averaging_steps', {})
    zones = position_state.get('zones', {})

    # Account Summary
    print_section("💰 ACCOUNT SUMMARY")
    balance = position_state.get('balance', 0)
    total_upnl = sum(p.get('unrealized_pnl', 0) for p in active_positions.values())
    used_margin = len(active_positions) * 5
    margin_util = used_margin / balance * 100 if balance > 0 else 0

    print(f"  Balance:         ${balance:.2f}")
    print(f"  Unrealized P&L:  {format_pnl(total_upnl)}")
    print(f"  Margin Used:     ${used_margin:.2f} ({margin_util:.1f}%)")
    print(f"  Active Positions: {len(active_positions)}")
    print(f"  Active Hedges:   {len(hedge_state.get('hedges', {}))}")

    # Market Regime
    print_section("📊 MARKET REGIME")
    sample_params = list(thresholds.values())[0] if thresholds else {}
    regime = sample_params.get('regime', 'NORMAL')
    atr = sample_params.get('atr_percent', 2.0)
    volatility = sample_params.get('volatility_percent', 10.0)

    print(f"  Current Regime:  {format_regime(regime)}")
    print(f"  ATR:             {atr:.2f}%")
    print(f"  Volatility:      {volatility:.2f}%")

    # Dynamic Parameters
    print_section("🎯 DYNAMIC PARAMETERS")
    avg_trigger = sample_params.get('averaging_start', -0.35)
    sd1 = sample_params.get('surplus_dump_85', 0.85)
    sd2 = sample_params.get('surplus_dump_50', 0.40)

    print(f"  Averaging Trigger:   {avg_trigger*100:.0f}%")
    print(f"  Surplus Dump S1:     {sd1*100:.0f}% of peak")
    print(f"  Surplus Dump S2:     {sd2*100:.0f}% of peak")

    # Positions by Zone
    print_section("📈 POSITIONS BY ZONE")
    zone_counts = {}
    for symbol in active_positions:
        zone = zones.get(symbol, 'NEUTRAL')
        zone_counts[zone] = zone_counts.get(zone, 0) + 1

    for zone in ['AVERAGING', 'NEUTRAL', 'PROFIT_TAKING', 'SURPLUS_DUMP']:
        count = zone_counts.get(zone, 0)
        bar = '█' * count + '░' * (20 - min(count, 20))
        print(f"  {format_zone(zone):25s} {count:2d} [{bar}]")

    # Top Positions
    print_section("📊 TOP POSITIONS (by |P&L|)")
    positions = []
    for symbol, pos_data in active_positions.items():
        upnl = pos_data.get('unrealized_pnl', 0)
        positions.append({
            'symbol': symbol.replace('/USDT:USDT', ''),
            'side': pos_data.get('side', '?'),
            'zone': zones.get(symbol, 'NEUTRAL'),
            'steps': averaging_steps.get(symbol, 0),
            'upnl': upnl
        })

    positions.sort(key=lambda x: abs(x['upnl']), reverse=True)

    print(f"  {'Symbol':<12} {'Side':<6} {'Zone':<15} {'Steps':<6} {'UPNL':>10}")
    print(f"  {'-'*12} {'-'*6} {'-'*15} {'-'*6} {'-'*10}")

    for pos in positions[:10]:
        zone_formatted = format_zone(pos['zone'])
        upnl_formatted = format_pnl(pos['upnl'])
        print(f"  {pos['symbol']:<12} {pos['side']:<6} {zone_formatted:<24} {pos['steps']:<6} {upnl_formatted:>10}")

    # Footer
    print(f"\n{Colors.CYAN}{'='*70}{Colors.ENDC}")
    print(f"  Press Ctrl+C to exit | Auto-refresh every 10 seconds")
    print(f"{Colors.CYAN}{'='*70}{Colors.ENDC}\n")


def main():
    """Main loop for CLI dashboard."""
    print("Starting AI-XYZ CLI Dashboard...")
    print("Press Ctrl+C to exit\n")

    try:
        while True:
            display_dashboard()
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n\nDashboard stopped.")
        sys.exit(0)


if __name__ == '__main__':
    main()
