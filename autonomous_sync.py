#!/usr/bin/env python3
"""
Autonomous Exchange Sync - Makes AI-XYZ fully self-contained
"""
import ccxt
import json
import os
import time
import asyncio
from datetime import datetime
from dotenv import load_dotenv
import sys

# Add paths for dynamic averaging imports
sys.path.insert(0, '/app/core')
sys.path.insert(0, '/app/services/api-gateway/src')

# Import dynamic averaging services
try:
    from adaptive_fibonacci_averaging import AdaptiveFibonacciCalculator
    from fibonacci_delta_calculator import FibonacciDeltaCalculator
    DYNAMIC_AVERAGING_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Dynamic averaging services not available: {e}")
    DYNAMIC_AVERAGING_AVAILABLE = False
    AdaptiveFibonacciCalculator = None
    FibonacciDeltaCalculator = None

# Import orchestrator integration (optional)
try:
    from orchestrator_integration import OrchestratorIntegration
except ImportError:
    OrchestratorIntegration = None

load_dotenv('/app/.env')

class AutonomousSync:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

        # Initialize dynamic averaging calculators if available
        self.adaptive_calc = AdaptiveFibonacciCalculator(num_steps=5) if DYNAMIC_AVERAGING_AVAILABLE else None
        self.delta_calc = FibonacciDeltaCalculator(self.exchange) if DYNAMIC_AVERAGING_AVAILABLE else None

        # Initialize orchestrator integration if available
        self.orchestrator = None
        if OrchestratorIntegration:
            try:
                self.orchestrator = OrchestratorIntegration()
                if self.orchestrator.enabled:
                    print("🤖 Orchestrator integration enabled for averaging decisions")
            except Exception as e:
                print(f"⚠️ Orchestrator integration disabled: {e}")
        
    def calculate_fallback_delta(self, symbol):
        """Calculate delta using multi-timeframe analysis as fallback"""
        try:
            import numpy as np
            timeframes = ['1m', '5m', '15m', '1h', '4h', '1d']
            deltas = []

            for tf in timeframes:
                try:
                    ohlcv = self.exchange.fetch_ohlcv(symbol, tf, limit=100)
                    if len(ohlcv) >= 20:
                        highs = [c[2] for c in ohlcv[-20:]]
                        lows = [c[3] for c in ohlcv[-20:]]
                        closes = [c[4] for c in ohlcv[-20:]]

                        # Calculate range as percentage
                        avg_price = np.mean(closes)
                        if avg_price > 0:
                            range_pct = (max(highs) - min(lows)) / avg_price
                            deltas.append(range_pct)
                except:
                    continue

            if deltas:
                # Use weighted average with more weight on medium timeframes
                weights = [0.05, 0.10, 0.25, 0.30, 0.20, 0.10][:len(deltas)]
                weights = [w/sum(weights) for w in weights]
                delta = np.average(deltas, weights=weights)

                # Apply leverage adjustment
                delta = delta * 8  # Assuming 8x leverage

                # Ensure minimum delta for proper distribution
                MIN_DELTA = 50.0  # 50% minimum
                if delta < MIN_DELTA:
                    print(f"📈 Adjusting delta from {delta:.1f}% to {MIN_DELTA:.0f}% minimum")
                    delta = MIN_DELTA

                return delta

            return 50.0  # Default 50% if calculation fails
        except Exception as e:
            print(f"⚠️ Fallback delta calculation error: {e}")
            return 50.0

    def fix_manual_positions(self, state):
        """Fix manual positions missing required fields"""
        modified = False
        for symbol, position in state.get('active_positions', {}).items():
            if position.get('opened_at') == 'manual':
                if 'initial_margin' not in position:
                    amount = position.get('amount', 0)
                    entry_price = position.get('entry_price', 0)
                    leverage = position.get('leverage', 1)
                    if amount and entry_price and leverage:
                        position_value = amount * entry_price
                        position['initial_margin'] = position_value / leverage
                        modified = True
                        print(f"✅ Added initial_margin to {symbol}: ${position['initial_margin']:.4f}")

                if 'safety_margin' not in position:
                    position['safety_margin'] = 3.0
                    modified = True
                    print(f"✅ Added safety_margin to {symbol}: $3.00")

        return modified

    def sync_positions(self):
        """Sync positions and trigger averaging when needed"""
        state_file = '/app/position_state.json'

        try:
            with open(state_file, 'r') as f:
                state = json.load(f)

            # Fix any manual positions missing fields
            if self.fix_manual_positions(state):
                with open(state_file, 'w') as f:
                    json.dump(state, f, indent=2)
            
            positions = self.exchange.fetch_positions()
            
            for pos in positions:
                symbol = pos['symbol']
                # Process ALL positions with open contracts from the exchange
                if pos.get('contracts', 0) > 0:
                    upnl = pos.get('unrealizedPnl', 0)
                    current_price = pos.get('markPrice', 0)

                    # Ensure position exists in state
                    if symbol in state['active_positions']:
                        # Update existing position with UPNL
                        entry = state['active_positions'][symbol]['entry_price']
                        amount = state['active_positions'][symbol]['amount']
                        leverage = state['active_positions'][symbol].get('leverage', 8)
                    else:
                        # Add new position from exchange if not in state (manual positions)
                        print(f"📌 Found manual position on exchange: {symbol}")
                        entry = pos.get('entryPrice', current_price)
                        amount = pos.get('contracts', 0)
                        leverage = pos.get('leverage', 8)
                        side = pos.get('side', 'buy').lower()

                        # Ensure side is normalized
                        if side == 'long':
                            side = 'buy'
                        elif side == 'short':
                            side = 'sell'

                        state['active_positions'][symbol] = {
                            'entry_price': entry,
                            'amount': amount,
                            'side': side,
                            'leverage': leverage,
                            'opened_at': datetime.now().isoformat(),
                            'source': 'manual_exchange',
                            'confidence': 0.75,
                            'initial_margin': (amount * entry) / leverage if leverage > 0 else amount * entry,
                            'safety_margin': 1.0
                        }

                        # Initialize all required state fields for new position
                        if symbol not in state.get('position_zones', {}):
                            state['position_zones'][symbol] = 'NEUTRAL'
                        if symbol not in state.get('averaging_steps', {}):
                            state['averaging_steps'][symbol] = 0
                        if symbol not in state.get('peak_upnl', {}):
                            state['peak_upnl'][symbol] = 0
                        if symbol not in state.get('peak_upnl_timestamps', {}):
                            state['peak_upnl_timestamps'][symbol] = datetime.now().isoformat()
                        if symbol not in state.get('surplus_dump_stage', {}):
                            state['surplus_dump_stage'][symbol] = 0
                        if symbol not in state.get('original_sizes', {}):
                            state['original_sizes'][symbol] = amount
                        if symbol not in state.get('position_multipliers', {}):
                            state['position_multipliers'][symbol] = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]

                        print(f"✅ Added manual position {symbol} to state with all fields initialized")

                    # Always update UPNL and current price
                    state['active_positions'][symbol]['unrealized_pnl'] = upnl
                    state['active_positions'][symbol]['current_price'] = current_price
                    
                    # Auto-detect averaging steps from position size changes
                    original_size = state['original_sizes'].get(symbol, amount)
                    if amount > original_size * 1.5:  # Significant size increase
                        size_ratio = amount / original_size
                        # Estimate steps from size ratio
                        if size_ratio >= 15:
                            estimated_steps = 5
                        elif size_ratio >= 8:
                            estimated_steps = 4
                        elif size_ratio >= 4:
                            estimated_steps = 3
                        elif size_ratio >= 2.5:
                            estimated_steps = 2
                        else:
                            estimated_steps = 1
                        
                        current_steps = state['averaging_steps'].get(symbol, 0)
                        if estimated_steps > current_steps:
                            print(f"📊 Detected averaging: {symbol} size {original_size}->{amount} ({size_ratio:.1f}x), steps: {current_steps}->{estimated_steps}")
                            state['averaging_steps'][symbol] = estimated_steps
                    
                    # Track peak UPNL dynamically
                    if symbol not in state.get('peak_upnl', {}):
                        state['peak_upnl'][symbol] = upnl
                    elif upnl > state['peak_upnl'][symbol]:
                        state['peak_upnl'][symbol] = upnl
                        print(f"📈 New peak UPNL for {symbol}: ${upnl:.2f}")
                    
                    # Check for surplus dump scenario
                    zone = state['position_zones'].get(symbol)
                    steps_taken = state['averaging_steps'].get(symbol, 0)
                    
                    if zone == 'SURPLUS_DUMP' and steps_taken > 0:
                        peak = state['peak_upnl'].get(symbol, upnl)
                        dump_stage = state['surplus_dump_stage'].get(symbol, 0)
                        
                        print(f"💰 {symbol} in SURPLUS DUMP zone")
                        print(f"   Current UPNL: ${upnl:.2f}")
                        print(f"   Peak UPNL: ${peak:.2f}")
                        print(f"   Dump stage: {dump_stage}/2")
                        
                        # Stage 1: Dump 50% at 85% of peak (amount now properly defined)
                        if dump_stage == 0 and upnl >= peak * 0.85:
                            surplus_size = (amount - state['original_sizes'].get(symbol, amount)) * 0.5
                            if surplus_size > 0:
                                try:
                                    order = self.exchange.create_market_order(
                                        symbol=symbol,
                                        side='sell' if state['active_positions'][symbol]['side'] == 'buy' else 'buy',
                                        amount=surplus_size
                                    )
                                    if order and order.get('status') == 'closed':
                                        state['surplus_dump_stage'][symbol] = 1
                                        state['active_positions'][symbol]['amount'] -= surplus_size
                                        print(f"✅ Stage 1 dump: {surplus_size} contracts at ${current_price}")
                                except Exception as e:
                                    print(f"❌ Surplus dump failed: {e}")
                        
                        # Stage 2: Dump remaining at 50% of peak
                        elif dump_stage == 1 and upnl >= peak * 0.50:
                            surplus_size = amount - state['original_sizes'].get(symbol, amount)
                            if surplus_size > 0:
                                try:
                                    order = self.exchange.create_market_order(
                                        symbol=symbol,
                                        side='sell' if state['active_positions'][symbol]['side'] == 'buy' else 'buy',
                                        amount=surplus_size
                                    )
                                    if order and order.get('status') == 'closed':
                                        state['surplus_dump_stage'][symbol] = 2
                                        state['position_zones'][symbol] = 'NEUTRAL'
                                        state['averaging_steps'][symbol] = 0
                                        state['active_positions'][symbol]['amount'] = state['original_sizes'].get(symbol, amount)
                                        print(f"✅ Stage 2 dump: {surplus_size} contracts at ${current_price}")
                                        print(f"✅ Position reset to NEUTRAL zone")
                                except Exception as e:
                                    print(f"❌ Surplus dump failed: {e}")
                    
                    # FIXED: Calculate UPNL% against position value, not margin
                    position_value = entry * amount if entry > 0 and amount > 0 else 1.0
                    initial_margin = position_value / leverage if leverage > 0 else position_value
                    # Calculate UPNL percentage based on margin (not position value)
                    upnl_pct = (upnl / initial_margin) * 100 if initial_margin > 0 else 0
                    
                    print(f"📊 {symbol}: UPNL=${upnl:.2f} ({upnl_pct:.1f}%)")
                    
                    # Dynamic zone transitions based on UPNL
                    current_zone = state['position_zones'].get(symbol, 'NEUTRAL')
                    steps_taken = state['averaging_steps'].get(symbol, 0)
                    
                    # GATE THRESHOLD: -42% is the minimum gate to allow averaging
                    # No averaging is allowed above -42% UPNL (from config)
                    # Load config
                    try:
                        with open('/app/runtime_config.json', 'r') as f:
                            config = json.load(f)
                    except:
                        config = {'zone_thresholds': {'averaging_start': -0.42}}

                    GATE_THRESHOLD = config['zone_thresholds']['averaging_start'] * 100
                    MAX_AVERAGING_THRESHOLD = -70.0

                    # Transition to AVERAGING if loss exceeds gate threshold
                    if upnl_pct <= GATE_THRESHOLD and current_zone != 'AVERAGING':
                        if steps_taken > 0 and upnl_pct > 0:
                            # Position recovered with averaging steps - move to SURPLUS_DUMP
                            state['position_zones'][symbol] = 'SURPLUS_DUMP'
                            print(f"🎯 {symbol} moved to SURPLUS_DUMP (recovery after averaging)")
                        else:
                            # Only enter averaging zone after passing -25% gate
                            state['position_zones'][symbol] = 'AVERAGING'
                            print(f"⚠️ {symbol} moved to AVERAGING zone (passed {GATE_THRESHOLD}% gate)")
                    
                    # Transition to SURPLUS_DUMP if recovered after averaging
                    elif steps_taken > 0 and upnl_pct > 10 and current_zone == 'AVERAGING':
                        state['position_zones'][symbol] = 'SURPLUS_DUMP'
                        print(f"💰 {symbol} recovered! Moving to SURPLUS_DUMP zone")
                        print(f"   Steps taken: {steps_taken}, UPNL: {upnl_pct:.1f}%")
                        print(f"   Surplus size: {amount - state['original_sizes'].get(symbol, amount)} contracts")
                    
                    # TAKE PROFIT SUSPENDED - Only averaging and surplus dump active
                    # No automatic profit taking for positions without averaging
                    
                    # Check averaging trigger - Dynamic Fibonacci-based threshold
                    # First averaging step triggers at first Fibonacci threshold
                    # We need to check if we should enter averaging zone
                    steps_taken = state.get('averaging_steps', {}).get(symbol, 0)
                    zone = state.get('position_zones', {}).get(symbol)
                    
                    # Check for zone entry if not already averaging
                    # IMPORTANT: Gate threshold of -42% must be passed first (FIXED)
                    if steps_taken == 0 and zone != 'AVERAGING':
                        GATE_THRESHOLD = -42.0

                        # Gate check - no averaging zone entry above -42% (FIXED)
                        if upnl_pct > GATE_THRESHOLD:
                            # Still above gate, cannot enter averaging zone
                            if upnl_pct < 0:
                                print(f"📊 {symbol}: UPNL {upnl_pct:.1f}% - Waiting for {GATE_THRESHOLD}% gate")
                        else:
                            # Gate passed, now check Fibonacci threshold
                            # Calculate first threshold based on Fibonacci delta
                            # Default to conservative -42% if no delta available
                            first_threshold = -42

                            # Try to get stored delta or calculate it
                            if 'position_metadata' in state and symbol in state['position_metadata']:
                                stored_delta = state['position_metadata'][symbol].get('fibonacci_delta')
                                if stored_delta and stored_delta > 0:
                                    # First Fibonacci ratio is 233/sum(fib_sequence)
                                    fib_sequence = [233, 144, 89, 55, 34, 21, 13, 8, 5, 3]
                                    fib_sum = sum(fib_sequence)
                                    first_fib_ratio = fib_sequence[0] / fib_sum
                                    # First threshold is based on first Fibonacci ratio of delta
                                    first_threshold = -(first_fib_ratio * stored_delta * 100)

                            # Apply both gate and Fibonacci thresholds
                            if upnl_pct <= max(first_threshold, GATE_THRESHOLD):
                                state['position_zones'][symbol] = 'AVERAGING'
                                print(f"🔄 {symbol} moved to AVERAGING zone at {upnl_pct:.1f}% (gate passed, threshold: {first_threshold:.1f}%)")
                    
                    # IMPORTANT: Process averaging for positions already IN the averaging zone
                    if zone == 'AVERAGING':
                        print(f"🔍 {symbol} is in AVERAGING zone, checking for next step...")
                        steps = state['averaging_steps'].get(symbol, 0)
                        print(f"   Current steps: {steps}, UPNL%: {upnl_pct:.1f}%")
                        
                        # Calculate max steps based on available capital
                        # Get current position value and available capital
                        position_value = amount * current_price
                        margin_used = position_value / state['active_positions'][symbol].get('leverage', 1)
                        
                        # Get free balance from exchange
                        try:
                            balance = self.exchange.fetch_balance()
                            free_balance = balance['USDT']['free'] if 'USDT' in balance else 100  # Default 100 USDT
                            total_capital = free_balance + margin_used
                        except:
                            free_balance = 100  # Default if can't fetch
                            total_capital = free_balance + margin_used
                        
                        # Calculate how many steps we can afford
                        # Fibonacci sequence for position sizing
                        multipliers = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]
                        cumulative_multiplier = sum(multipliers[:steps+1])

                        # DYNAMIC FIBONACCI THRESHOLDS - Calculate using stored delta
                        # Reverse Fibonacci sequence (233 down to 3) for cumulative distribution
                        fib_sequence = [233, 144, 89, 55, 34, 21, 13, 8, 5, 3]
                        fib_sum = sum(fib_sequence)

                        # Get stored delta from position metadata
                        fibonacci_delta = 50.0  # Default fallback
                        if symbol in state.get('position_metadata', {}):
                            fibonacci_delta = state['position_metadata'][symbol].get('fibonacci_delta', 50.0)

                        # Calculate cumulative thresholds using Fibonacci distribution
                        averaging_thresholds = []
                        cumulative = 0
                        for fib_num in fib_sequence:
                            cumulative += (fib_num / fib_sum) * fibonacci_delta
                            # Convert to negative percentage threshold
                            threshold_pct = -cumulative
                            averaging_thresholds.append(threshold_pct)

                        print(f"📊 Dynamic Fibonacci thresholds (delta {fibonacci_delta:.1f}%): {[f'{t:.1f}%' for t in averaging_thresholds[:5]]}")

                        # Check if we should average at current UPNL
                        should_execute_averaging = False
                        if steps < len(averaging_thresholds):
                            threshold = averaging_thresholds[steps]
                            if upnl_pct <= threshold:
                                should_execute_averaging = True
                                print(f"🎯 Step {steps+1} threshold {threshold:.1f}% reached at {upnl_pct:.1f}%")
                        original_size = state['original_sizes'].get(symbol, amount)
                        original_value = original_size * entry
                        original_margin = original_value / state['active_positions'][symbol].get('leverage', 1)
                        
                        # Find max affordable steps
                        max_steps = 0
                        for i in range(13):
                            total_needed = sum(multipliers[:i+1]) * original_margin
                            if total_needed <= total_capital:
                                max_steps = i + 1
                            else:
                                break
                        
                        print(f"💰 Capital: ${total_capital:.2f}, Max steps: {max_steps}, Current step: {steps}")

                        if steps < max_steps:  # Dynamic max based on capital
                            # Initialize momentum check variables BEFORE any usage
                            momentum_ok = True
                            momentum_reason = "No momentum check"

                            # Check orchestrator for averaging decision
                            should_average = True
                            next_size = None
                            averaging_reason = None

                            # Orchestrator fixed - UPNL calculation now uses margin-based formula
                            if self.orchestrator and self.orchestrator.enabled:
                                try:
                                    decision = self.orchestrator.should_average(
                                        symbol,
                                        state['active_positions'][symbol],
                                        current_price
                                    )

                                    if decision['source'] == 'orchestrator':
                                        # Use orchestrator decision
                                        should_average = decision['should_average']
                                        next_size = decision.get('size')
                                        averaging_reason = decision.get('reason')

                                        if should_average:
                                            print(f"🤖 Orchestrator decision: AVERAGE")
                                            print(f"   Reason: {averaging_reason}")
                                            print(f"   Confidence: {decision.get('confidence', 0):.1%}")
                                        else:
                                            print(f"🤖 Orchestrator decision: HOLD")
                                            print(f"   Reason: {averaging_reason}")
                                except Exception as e:
                                    print(f"⚠️ Orchestrator error, using original logic: {e}")

                            # Fall back to original logic if needed
                            if next_size is None and should_average:
                                # Extended Fibonacci multiplier sequence
                                original_size = state['original_sizes'].get(symbol, amount)
                                base_size = original_size * multipliers[min(steps, 12)]  # Use all 13 multipliers

                                # Ensure minimum order value from config (default $40 USDT after leverage)
                                try:
                                    with open('/app/runtime_config.json', 'r') as f:
                                        config = json.load(f)
                                    min_position_value = config.get('min_position_size', 40.0)
                                except:
                                    min_position_value = 40.0

                                min_contracts = min_position_value / current_price
                                next_size = max(base_size, min_contracts)

                            # Final check: threshold reached AND (momentum OK OR hard bypass at -70%)
                            final_averaging_check = should_execute_averaging and (momentum_ok or upnl_pct <= -70.0)

                            # Debug output
                            if should_execute_averaging and not momentum_ok and upnl_pct > -70.0:
                                print(f"⏸️ Averaging BLOCKED by momentum guardian:")
                                print(f"   Threshold reached: {averaging_thresholds[steps]:.1f}%")
                                print(f"   Current UPNL: {upnl_pct:.1f}%")
                                print(f"   Reason: {momentum_reason}")
                                print(f"   Hard bypass at -70% not reached yet")

                            if should_average and next_size and final_averaging_check:
                                print(f"⚠️ {symbol} AVERAGING TRIGGERED:")
                                print(f"   Loss: {upnl_pct:.1f}%")
                                print(f"   Steps taken: {steps}")
                                print(f"   Next size: {next_size} contracts")

                                # EXECUTE AVERAGING ORDER NOW
                                try:
                                    order = self.exchange.create_market_order(
                                        symbol=symbol,
                                        side='buy' if state['active_positions'][symbol]['side'] == 'buy' else 'sell',
                                        amount=next_size
                                    )

                                    if order and order.get('status') == 'closed':
                                        state['averaging_steps'][symbol] = steps + 1
                                        state['active_positions'][symbol]['amount'] += next_size

                                        # Recalculate weighted average price
                                        old_value = state['active_positions'][symbol].get('amount', amount) * entry
                                        new_value = next_size * current_price
                                        total_amount = state['active_positions'][symbol]['amount']
                                        state['active_positions'][symbol]['entry_price'] = (old_value + new_value) / total_amount

                                        print(f"✅ AVERAGING EXECUTED: {next_size} contracts at ${current_price:.6f}")
                                        print(f"   New total: {total_amount} contracts")
                                        print(f"   New avg price: ${state['active_positions'][symbol]['entry_price']:.6f}")
                                except Exception as e:
                                    print(f"❌ Averaging execution failed: {e}")
                            
                            # Calculate proper Fibonacci delta using dynamic service
                            import numpy as np

                            # Check if we have calculated delta, if not calculate it
                            if 'fibonacci_delta' not in state.get('position_metadata', {}).get(symbol, {}):
                                # Always use fallback method (FibonacciDeltaCalculator requires async)
                                fibonacci_delta = self.calculate_fallback_delta(symbol)

                                # Store the calculated delta
                                if 'position_metadata' not in state:
                                    state['position_metadata'] = {}
                                if symbol not in state['position_metadata']:
                                    state['position_metadata'][symbol] = {}
                                state['position_metadata'][symbol]['fibonacci_delta'] = fibonacci_delta
                                print(f"📊 Stored Fibonacci delta: {fibonacci_delta:.1f}% for {symbol}")
                            else:
                                fibonacci_delta = state['position_metadata'][symbol]['fibonacci_delta']
                            
                            # CRITICAL: No averaging without calculated delta
                            if fibonacci_delta is None or fibonacci_delta <= 0:
                                print(f"⛔ Invalid delta ({fibonacci_delta}) - NO AVERAGING")
                                continue

                            # Initialize momentum check variables
                            momentum_ok = True
                            momentum_reason = "No momentum check"
                            effective_delta = fibonacci_delta
                            # GATE ENFORCEMENT: Maximum threshold is -70%
                            hard_average_threshold = -70.0  # Maximum averaging threshold (gate limit)

                            # Initialize delta accumulation tracking
                            if 'delta_accumulation' not in state:
                                state['delta_accumulation'] = {}
                            if symbol not in state['delta_accumulation']:
                                state['delta_accumulation'][symbol] = {
                                    'accumulated_delta': 0.0,
                                    'delay_count': 0,
                                    'start_timestamp': datetime.now().isoformat()
                                }

                            # Check if we hit the hard averaging threshold (-70%)
                            # CRITICAL: At -70%, FORCE averaging regardless of momentum conditions
                            if upnl_pct <= hard_average_threshold:
                                # At -70%, execute averaging with accumulated delta immediately
                                if state['delta_accumulation'][symbol]['accumulated_delta'] > 0:
                                    effective_delta = fibonacci_delta + state['delta_accumulation'][symbol]['accumulated_delta']
                                    print(f"🔴 HARD BYPASS at {upnl_pct:.1f}% (≤ {hard_average_threshold}%) - FORCING AVERAGING")
                                    print(f"   Using accumulated delta: {fibonacci_delta:.3f}% + {state['delta_accumulation'][symbol]['accumulated_delta']:.3f}% = {effective_delta:.3f}%")
                                    # Reset accumulation after use
                                    state['delta_accumulation'][symbol] = {
                                        'accumulated_delta': 0.0,
                                        'delay_count': 0,
                                        'start_timestamp': datetime.now().isoformat()
                                    }
                                else:
                                    print(f"🔴 HARD BYPASS at {upnl_pct:.1f}% (≤ {hard_average_threshold}%) - FORCING AVERAGING")
                                # FORCE averaging - override all momentum checks
                                momentum_ok = True
                                momentum_reason = f"HARD BYPASS: Forced averaging at {upnl_pct:.1f}% (momentum checks disabled)"
                            else:
                                # Normal conditions - check momentum and volatility
                                if 'momentum_permission' in state:
                                    perm = state['momentum_permission'].get(symbol, {})
                                    momentum_ok = perm.get('can_average', False)
                                    momentum_reason = perm.get('reason', 'Unknown')
                                    
                                    # If momentum guardian blocked averaging, accumulate delta
                                    if not momentum_ok:
                                        # Check if it's blocked due to extreme volatility (not low volatility)
                                        is_extreme_volatility = False
                                        if 'bands' in perm:
                                            volatility_current = perm['bands'].get('volatility_current', 0)
                                            volatility_band = perm['bands'].get('volatility_band', '0-100%')
                                            try:
                                                # Parse band (e.g., "0.44-0.69%")
                                                band_parts = volatility_band.replace('%', '').split('-')
                                                upper_volatility = float(band_parts[1])
                                                
                                                # Check if blocked due to HIGH volatility (above upper band)
                                                if volatility_current > upper_volatility:
                                                    is_extreme_volatility = True
                                                    print(f"🔥 High volatility blocking: {volatility_current:.2f}% > {upper_volatility:.2f}%")
                                            except:
                                                pass  # Failed to parse bands
                                        
                                        # Accumulate delta for any blocking reason (momentum or extreme volatility)
                                        state['delta_accumulation'][symbol]['accumulated_delta'] += fibonacci_delta
                                        state['delta_accumulation'][symbol]['delay_count'] += 1
                                        momentum_reason += f" (accumulated: {state['delta_accumulation'][symbol]['accumulated_delta']:.3f}%)"
                                        
                                        if is_extreme_volatility:
                                            print(f"🔥 Extreme volatility - accumulating delta: {state['delta_accumulation'][symbol]['accumulated_delta']:.3f}%")
                                        else:
                                            print(f"⏸️ Momentum blocking - accumulating delta: {state['delta_accumulation'][symbol]['accumulated_delta']:.3f}%")
                                    
                                    # If momentum permits and we have accumulated delta, use it
                                    if momentum_ok and state['delta_accumulation'][symbol]['accumulated_delta'] > 0:
                                        effective_delta = fibonacci_delta + state['delta_accumulation'][symbol]['accumulated_delta']
                                        print(f"✅ Using accumulated delta: {fibonacci_delta:.3f}% + {state['delta_accumulation'][symbol]['accumulated_delta']:.3f}% = {effective_delta:.3f}%")
                                        # Reset accumulation after use
                                        state['delta_accumulation'][symbol] = {
                                            'accumulated_delta': 0.0,
                                            'delay_count': 0,
                                            'start_timestamp': datetime.now().isoformat()
                                        }
                            
                            # Calculate max steps based on available capital (same logic as above)
                            multipliers = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]
                            try:
                                balance = self.exchange.fetch_balance()
                                free_balance = balance['USDT']['free'] if 'USDT' in balance else 100
                                total_capital = free_balance + (position_value / leverage if leverage > 0 else position_value)
                            except:
                                total_capital = 100 + (position_value / leverage if leverage > 0 else position_value)
                            
                            # Find max affordable steps
                            max_steps = 0
                            for i in range(13):
                                total_needed = sum(multipliers[:i+1]) * (original_size * entry / leverage if leverage > 0 else original_size * entry)
                                if total_needed <= total_capital:
                                    max_steps = i + 1
                                else:
                                    break
                            
            
            # Clean up closed positions - remove from state if not on exchange
            exchange_symbols = {pos['symbol'] for pos in positions if pos.get('contracts', 0) > 0}
            closed_positions = []
            for symbol in list(state['active_positions'].keys()):
                if symbol not in exchange_symbols:
                    closed_positions.append(symbol)
                    del state['active_positions'][symbol]
                    # Clean up related state entries
                    if symbol in state.get('position_zones', {}):
                        del state['position_zones'][symbol]
                    if symbol in state.get('averaging_steps', {}):
                        del state['averaging_steps'][symbol]
                    if symbol in state.get('peak_upnl', {}):
                        del state['peak_upnl'][symbol]
                    if symbol in state.get('surplus_dump_stage', {}):
                        del state['surplus_dump_stage'][symbol]

            if closed_positions:
                print(f"🧹 Cleaned up closed positions: {', '.join(closed_positions)}")

            # Save state
            state['timestamp'] = datetime.now().isoformat()
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
                
        except Exception as e:
            print(f"❌ Sync error: {e}")
    
    def run(self):
        print("🚀 AI-XYZ Autonomous Sync Started")
        while True:
            try:
                self.sync_positions()
                
                # Dynamic refresh rate based on position zones
                refresh_interval = 10  # Default 10 seconds
                
                # Check if we need faster refresh
                try:
                    with open('/app/position_state.json', 'r') as f:
                        state = json.load(f)
                    
                    # Check zones for all active positions
                    for symbol, zone in state.get('position_zones', {}).items():
                        if zone == 'SURPLUS_DUMP':
                            refresh_interval = 1  # 1 second for surplus dump
                            print(f"⚡ Fast refresh (1s) - {symbol} in SURPLUS_DUMP")
                            break
                        # PROFIT_TAKING SUSPENDED - Skip this zone
                        # elif zone == 'PROFIT_TAKING':
                        #     refresh_interval = 2  # 2 seconds for profit taking
                        #     print(f"⚡ Medium refresh (2s) - {symbol} in PROFIT_TAKING")
                        elif zone == 'AVERAGING' and refresh_interval > 3:
                            refresh_interval = 3  # 3 seconds for averaging zone
                            print(f"⚡ Averaging refresh (3s) - {symbol} in AVERAGING")
                except:
                    pass  # If can't read state, use default interval
                
                time.sleep(refresh_interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(10)

if __name__ == "__main__":
    sync = AutonomousSync()
    sync.run()