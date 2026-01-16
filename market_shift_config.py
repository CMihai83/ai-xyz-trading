#!/usr/bin/env python3
"""
Market Shift Predictor - Integration Configuration
===================================================
Designed with Grok AI - January 15, 2026
Updated with Extended Backtest Results - January 15, 2026

Extended Backtest Summary (162 tests, 27 symbols, 6 timeframes):
- Best Zone Strategy Timeframe: 2h (92.1% win rate, +$4.25 P&L)
- Best Signal Accuracy Timeframe: 2h (50.1% @10 periods)
- Best Shift Predictor Timeframe: 4h (1.32 PF)
- Total Data: 132,300 candles, ~9,079 days

Top Performers:
- SEI 2h: 63% accuracy, 100% zone WR, +$4.28
- ARB 4h: 100% zone WR, +$5.96
- XRP 6h: 80% accuracy (highest)
- LINK 2h: 59% accuracy, 100% zone WR

Symbols to Avoid: FLOKI (-$15), GALA (-$10), INJ (-$7), FET (-$7)
"""

# ============================================================================
# RECOMMENDED ASSETS (Based on Extended Backtest)
# ============================================================================

RECOMMENDED_ASSETS = {
    # High confidence: >85% zone win rate AND >$5 P&L
    'high_confidence': [
        'SEI/USDT:USDT',    # +$12.61, 87.5% zone WR
        'ARB/USDT:USDT',    # +$10.22, 87.2% zone WR
        'XRP/USDT:USDT',    # +$9.02, 95.8% zone WR
        'AVAX/USDT:USDT',   # +$8.14, 86.9% zone WR
        'LINK/USDT:USDT',   # +$7.45, 84.7% zone WR
        'APT/USDT:USDT',    # +$6.61, 94.0% zone WR
    ],

    # Medium confidence: Positive P&L, >80% zone WR
    'medium_confidence': [
        'SUI/USDT:USDT',    # +$6.44, 87.3% zone WR
        'RENDER/USDT:USDT', # +$5.29, 89.6% zone WR
        'SOL/USDT:USDT',    # +$4.52, 74.4% zone WR
        'ETH/USDT:USDT',    # +$3.23, 81.3% zone WR
        'ADA/USDT:USDT',    # +$2.83, 88.8% zone WR
        'BTC/USDT:USDT',    # +$1.70, 65.6% zone WR (reliable signals)
        'ATOM/USDT:USDT',   # +$1.67, 85.8% zone WR
        'UNI/USDT:USDT',    # +$1.66, 96.1% zone WR
        'DOGE/USDT:USDT',   # +$0.57, 93.9% zone WR
    ],

    # Avoid: Consistent losses in backtest
    'avoid': [
        'FLOKI/USDT:USDT',  # -$15.04, poor zone performance
        'GALA/USDT:USDT',   # -$10.49, high losses
        'INJ/USDT:USDT',    # -$7.15, inconsistent
        'FET/USDT:USDT',    # -$6.88, low signal accuracy
        'WIF/USDT:USDT',    # -$5.63, high volatility losses
        'DOT/USDT:USDT',    # -$4.37, underperforms
        'IMX/USDT:USDT',    # -$9.66 on 4h, avoid
    ],
}

# Quick lookup set for avoid list
AVOID_SYMBOLS = set(RECOMMENDED_ASSETS['avoid'])
HIGH_CONFIDENCE_SYMBOLS = set(RECOMMENDED_ASSETS['high_confidence'])
MEDIUM_CONFIDENCE_SYMBOLS = set(RECOMMENDED_ASSETS['medium_confidence'])

# ============================================================================
# OPTIMAL SYMBOL/TIMEFRAME COMBINATIONS (From Backtest)
# ============================================================================

OPTIMAL_COMBOS = {
    # Symbol: {'timeframe': tf, 'accuracy': acc, 'zone_wr': wr, 'pnl': pnl}
    'SEI/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.63, 'zone_wr': 1.00, 'pnl': 4.28},
    'ARB/USDT:USDT': {'timeframe': '4h', 'accuracy': 0.20, 'zone_wr': 1.00, 'pnl': 5.96},
    'XRP/USDT:USDT': {'timeframe': '6h', 'accuracy': 0.80, 'zone_wr': 1.00, 'pnl': 1.09},
    'AVAX/USDT:USDT': {'timeframe': '4h', 'accuracy': 0.42, 'zone_wr': 0.89, 'pnl': 3.42},
    'LINK/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.59, 'zone_wr': 1.00, 'pnl': 3.48},
    'APT/USDT:USDT': {'timeframe': '4h', 'accuracy': 0.54, 'zone_wr': 0.92, 'pnl': 4.97},
    'ETH/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.53, 'zone_wr': 1.00, 'pnl': 4.00},
    'BTC/USDT:USDT': {'timeframe': '4h', 'accuracy': 0.68, 'zone_wr': 0.50, 'pnl': -0.02},
    'SOL/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.42, 'zone_wr': 0.91, 'pnl': 2.94},
    'DOGE/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.40, 'zone_wr': 1.00, 'pnl': 3.81},
    'NEAR/USDT:USDT': {'timeframe': '4h', 'accuracy': 0.38, 'zone_wr': 1.00, 'pnl': 4.47},
    'PEPE/USDT:USDT': {'timeframe': '6h', 'accuracy': 0.67, 'zone_wr': 1.00, 'pnl': 2.62},
    'SUI/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.44, 'zone_wr': 0.94, 'pnl': 3.13},
    'SHIB/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.51, 'zone_wr': 1.00, 'pnl': 2.99},
    'ATOM/USDT:USDT': {'timeframe': '4h', 'accuracy': 0.38, 'zone_wr': 0.90, 'pnl': 3.05},
    'UNI/USDT:USDT': {'timeframe': '6h', 'accuracy': 0.53, 'zone_wr': 1.00, 'pnl': 2.42},
    'ADA/USDT:USDT': {'timeframe': '2h', 'accuracy': 0.51, 'zone_wr': 1.00, 'pnl': 3.14},
    'AAVE/USDT:USDT': {'timeframe': '6h', 'accuracy': 0.61, 'zone_wr': 0.80, 'pnl': 0.66},
    'OP/USDT:USDT': {'timeframe': '4h', 'accuracy': 0.30, 'zone_wr': 0.86, 'pnl': 2.89},
    'RENDER/USDT:USDT': {'timeframe': '6h', 'accuracy': 0.26, 'zone_wr': 1.00, 'pnl': 5.56},
}

# High accuracy combos (>55% signal accuracy @10 periods)
HIGH_ACCURACY_COMBOS = {
    'XRP/USDT:USDT': ('6h', 0.80),
    'FET/USDT:USDT': ('1h', 0.72),  # Note: FET has poor zone performance
    'BTC/USDT:USDT': ('4h', 0.68),
    'PEPE/USDT:USDT': ('6h', 0.67),
    'SEI/USDT:USDT': ('2h', 0.63),
    'PEPE/USDT:USDT': ('2h', 0.62),
    'AAVE/USDT:USDT': ('6h', 0.61),
    'ARB/USDT:USDT': ('1h', 0.60),
    'LINK/USDT:USDT': ('2h', 0.59),
    'WIF/USDT:USDT': ('30m', 0.58),
    'AVAX/USDT:USDT': ('1h', 0.57),
}

# ============================================================================
# TIMEFRAME CONFIGURATION (Based on Backtest)
# ============================================================================

# Primary timeframe for shift detection (best signal accuracy)
PREFERRED_TIMEFRAME = '2h'  # 50.1% accuracy, 92.1% zone WR

# Secondary timeframe for confirmation
SECONDARY_TIMEFRAME = '4h'  # 1.32 PF, best for shift predictor

# Fallback timeframe (more data points)
FALLBACK_TIMEFRAME = '1h'

# Timeframe performance from backtest
TIMEFRAME_PERFORMANCE = {
    '15m': {'zone_wr': 0.917, 'pnl': 13.80, 'accuracy': 0.476, 'recommended': False},
    '30m': {'zone_wr': 0.779, 'pnl': -31.02, 'accuracy': 0.362, 'recommended': False},
    '1h':  {'zone_wr': 0.881, 'pnl': -14.67, 'accuracy': 0.447, 'recommended': False},
    '2h':  {'zone_wr': 0.921, 'pnl': 4.25, 'accuracy': 0.501, 'recommended': True},  # BEST
    '4h':  {'zone_wr': 0.851, 'pnl': 0.54, 'accuracy': 0.380, 'recommended': True},
    '6h':  {'zone_wr': 0.822, 'pnl': -8.08, 'accuracy': 0.388, 'recommended': False},
}

def get_optimal_timeframe(symbol: str) -> str:
    """Get the optimal timeframe for a specific symbol based on backtest."""
    if symbol in OPTIMAL_COMBOS:
        return OPTIMAL_COMBOS[symbol]['timeframe']
    return PREFERRED_TIMEFRAME

def get_symbol_accuracy(symbol: str) -> float:
    """Get the signal accuracy for a symbol from backtest."""
    if symbol in OPTIMAL_COMBOS:
        return OPTIMAL_COMBOS[symbol]['accuracy']
    return 0.40  # Default conservative estimate

# ============================================================================
# POSITION SIZING CONFIGURATION
# ============================================================================

POSITION_CONFIG = {
    'base_risk_pct': 0.01,  # 1% risk per trade
    'max_position_pct': 0.03,  # 3% max position
    'leverage_limit': 5,  # Max 5x leverage (from system config)
    'volatility_adjustment': True,  # Scale position inversely to volatility

    # Position size multipliers based on symbol confidence
    'size_multipliers': {
        'high_confidence': 1.2,    # +20% for high confidence symbols
        'medium_confidence': 1.0,  # Normal size
        'avoid': 0.0,              # Don't trade avoid list
    }
}

def get_position_multiplier(symbol: str) -> float:
    """Get position size multiplier based on symbol confidence."""
    if symbol in AVOID_SYMBOLS:
        return 0.0
    elif symbol in HIGH_CONFIDENCE_SYMBOLS:
        return POSITION_CONFIG['size_multipliers']['high_confidence']
    elif symbol in MEDIUM_CONFIDENCE_SYMBOLS:
        return POSITION_CONFIG['size_multipliers']['medium_confidence']
    else:
        return 0.8  # Reduced size for unknown symbols

# ============================================================================
# SIGNAL THRESHOLDS (Optimized from Backtest)
# ============================================================================

SIGNAL_THRESHOLDS = {
    'bullish_entry': 0.45,      # Slightly lower for 2h timeframe
    'bearish_entry': -0.45,     # Slightly lower for 2h timeframe
    'high_confidence': 0.65,    # Adjusted based on accuracy data
    'exit_on_reversal': True,

    # Timeframe-specific thresholds
    'timeframe_thresholds': {
        '2h': {'bullish': 0.45, 'bearish': -0.45, 'confidence': 0.60},
        '4h': {'bullish': 0.50, 'bearish': -0.50, 'confidence': 0.65},
        '6h': {'bullish': 0.50, 'bearish': -0.50, 'confidence': 0.60},
    }
}

def get_signal_thresholds(timeframe: str) -> dict:
    """Get signal thresholds for a specific timeframe."""
    return SIGNAL_THRESHOLDS['timeframe_thresholds'].get(
        timeframe,
        {'bullish': 0.50, 'bearish': -0.50, 'confidence': 0.65}
    )

# ============================================================================
# INTEGRATION WITH MAIN TRADING SYSTEM
# ============================================================================

INTEGRATION_CONFIG = {
    'use_for_new_positions': True,   # Filter new position entries
    'use_for_averaging': True,       # Adjust averaging based on regime
    'use_for_profit_taking': True,   # Accelerate profit taking on bearish shift
    'block_avoid_list': True,        # Block symbols in avoid list from trading

    'shift_actions': {
        'bullish': {
            'new_positions': 'allow_long',    # Allow long entries
            'averaging': 'aggressive',         # More aggressive averaging
            'profit_taking': 'delay',          # Hold for more profit
            'position_size': 1.1,              # +10% position size
        },
        'bearish': {
            'new_positions': 'allow_short',   # Allow short entries, block long
            'averaging': 'conservative',       # Less aggressive averaging
            'profit_taking': 'accelerate',     # Take profits faster
            'position_size': 0.8,              # -20% position size
        },
        'neutral': {
            'new_positions': 'normal',        # Normal entry rules
            'averaging': 'normal',             # Standard averaging
            'profit_taking': 'normal',         # Standard profit taking
            'position_size': 1.0,              # Normal size
        }
    }
}

def get_shift_action(direction: str, action_type: str) -> str:
    """
    Get recommended action based on shift direction.

    Args:
        direction: 'bullish', 'bearish', or 'neutral'
        action_type: 'new_positions', 'averaging', or 'profit_taking'

    Returns:
        Action string
    """
    return INTEGRATION_CONFIG['shift_actions'].get(direction, {}).get(action_type, 'normal')

def should_block_symbol(symbol: str) -> bool:
    """Check if a symbol should be blocked from trading."""
    if not INTEGRATION_CONFIG['block_avoid_list']:
        return False
    return symbol in AVOID_SYMBOLS

def get_symbol_confidence_tier(symbol: str) -> str:
    """Get the confidence tier for a symbol."""
    if symbol in AVOID_SYMBOLS:
        return 'avoid'
    elif symbol in HIGH_CONFIDENCE_SYMBOLS:
        return 'high_confidence'
    elif symbol in MEDIUM_CONFIDENCE_SYMBOLS:
        return 'medium_confidence'
    else:
        return 'unknown'

# ============================================================================
# AVERAGING PARAMETERS (From Backtest Analysis)
# ============================================================================

AVERAGING_CONFIG = {
    # Backtest finding: Winners need 1.32 avg steps, losers need 2.63 steps
    'max_steps_on_weak_signal': 3,   # Limit steps for low confidence signals
    'max_steps_on_strong_signal': 5,  # Full steps for high confidence

    # Adjust steps based on symbol confidence
    'steps_by_confidence': {
        'high_confidence': 5,
        'medium_confidence': 4,
        'avoid': 0,  # No averaging on avoid list
        'unknown': 3,
    }
}

def get_max_averaging_steps(symbol: str, signal_strength: float) -> int:
    """Get maximum averaging steps based on symbol and signal strength."""
    tier = get_symbol_confidence_tier(symbol)
    base_steps = AVERAGING_CONFIG['steps_by_confidence'].get(tier, 3)

    # Reduce steps for weak signals
    if abs(signal_strength) < 0.5:
        return min(base_steps, AVERAGING_CONFIG['max_steps_on_weak_signal'])

    return base_steps


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print("Market Shift Predictor - Optimized Configuration")
    print("=" * 60)
    print(f"Primary Timeframe: {PREFERRED_TIMEFRAME} (50.1% accuracy)")
    print(f"Secondary Timeframe: {SECONDARY_TIMEFRAME} (1.32 PF)")
    print(f"Risk per Trade: {POSITION_CONFIG['base_risk_pct']*100}%")
    print(f"Max Leverage: {POSITION_CONFIG['leverage_limit']}x")

    print(f"\nHigh Confidence Assets ({len(RECOMMENDED_ASSETS['high_confidence'])}):")
    for sym in RECOMMENDED_ASSETS['high_confidence']:
        base = sym.split('/')[0]
        combo = OPTIMAL_COMBOS.get(sym, {})
        print(f"  {base}: {combo.get('timeframe', 'N/A')} - {combo.get('accuracy', 0)*100:.0f}% acc, {combo.get('zone_wr', 0)*100:.0f}% WR")

    print(f"\nMedium Confidence Assets ({len(RECOMMENDED_ASSETS['medium_confidence'])}):")
    for sym in RECOMMENDED_ASSETS['medium_confidence'][:5]:
        base = sym.split('/')[0]
        print(f"  {base}")
    print(f"  ... and {len(RECOMMENDED_ASSETS['medium_confidence'])-5} more")

    print(f"\nAvoid List ({len(RECOMMENDED_ASSETS['avoid'])}):")
    for sym in RECOMMENDED_ASSETS['avoid']:
        base = sym.split('/')[0]
        print(f"  {base}")
