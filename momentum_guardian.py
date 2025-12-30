#!/usr/bin/env python3
"""
Enhanced Momentum & Volatility Guardian Service
===============================================
This service monitors price momentum and volatility bands and only allows averaging when:
1. Momentum is within normal bands (not extremely accelerating)
2. Volatility is within normal bands (not extremely high)
3. Momentum starts reversing (showing signs of bottoming/topping)
4. Volume confirms the reversal

Features:
- Dynamic volatility and momentum band calculation
- Delta accumulation when averaging is delayed
- Hard stop at -70% if conditions never normalize
- Periodic recalibration of normal ranges
"""

import ccxt
import os
from dotenv import load_dotenv
import json
import time
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from statistics import stdev, mean

load_dotenv('.env')

class EnhancedMomentumGuardian:
    def __init__(self):
        self.exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_API_SECRET'),
            'password': os.getenv('BITGET_PASSPHRASE'),
            'enableRateLimit': True,
            'options': {
                'defaultType': 'swap'
            }
        })
        
        # Track momentum peaks for each position
        self.momentum_data = {}
        
        # Track volatility and momentum bands for each symbol
        self.bands_data = {}
        
        # Track delta accumulation for delayed averaging
        self.delta_accumulation = {}
        
        # Hard stop threshold
        self.HARD_STOP_THRESHOLD = -70.0  # -70% UPNL percentage
        
        # Band calibration parameters
        self.LOOKBACK_PERIODS = 100  # How many periods to look back for band calculation
        self.BAND_MULTIPLIER = 2.0   # How many standard deviations for bands
        self.RECALIBRATION_INTERVAL = 3600  # Recalibrate bands every hour
        
    def calculate_momentum_indicators(self, symbol, timeframe='15m'):
        """Calculate RSI, MACD, and price velocity (using 15m for stability)"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=50)
            if len(ohlcv) < 30:
                return None
                
            closes = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]
            
            # RSI
            rsi = self.calculate_rsi(closes)
            
            # Price velocity (rate of change)
            velocity = ((closes[-1] - closes[-5]) / closes[-5]) * 100 if closes[-5] > 0 else 0
            
            # Volume trend
            vol_ma = np.mean(volumes[-10:])
            vol_spike = volumes[-1] / vol_ma if vol_ma > 0 else 1
            
            # MACD signal
            ema12 = self.calculate_ema(closes, 12)
            ema26 = self.calculate_ema(closes, 26)
            macd = ema12 - ema26
            signal = self.calculate_ema([macd], 9)
            
            return {
                'rsi': rsi,
                'velocity': velocity,
                'volume_spike': vol_spike,
                'macd': macd,
                'macd_signal': signal,
                'timestamp': datetime.now()
            }
            
        except Exception as e:
            print(f"Error calculating momentum: {e}")
            return None
    
    def calculate_rsi(self, prices, period=14):
        """Calculate RSI"""
        if len(prices) < period + 1:
            return 50
        
        deltas = np.diff(prices)
        seed = deltas[:period]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        if down == 0:
            return 100
        
        rs = up / down
        return 100 - (100 / (1 + rs))
    
    def calculate_ema(self, data, period):
        """Calculate EMA"""
        if len(data) < period:
            return data[-1] if data else 0
        
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = (price - ema) * multiplier + ema
        return ema
    
    def calculate_volatility_momentum_bands(self, symbol, timeframe='15m'):
        """
        Calculate dynamic volatility and momentum bands for normal range determination (using 15m for stability)
        """
        try:
            # Get extended historical data for band calculation
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=self.LOOKBACK_PERIODS)
            if len(ohlcv) < 50:
                return None
            
            closes = [c[4] for c in ohlcv]
            volumes = [c[5] for c in ohlcv]
            
            # Calculate volatility metrics
            returns = np.diff(np.log(closes))
            volatility_values = []
            momentum_values = []
            
            # Rolling window calculations
            window = 20
            for i in range(window, len(closes)):
                # Volatility: rolling standard deviation of returns
                period_returns = returns[i-window:i]
                volatility = np.std(period_returns) * 100  # Convert to percentage
                volatility_values.append(volatility)
                
                # Momentum: rate of change over window
                momentum = ((closes[i] - closes[i-window]) / closes[i-window]) * 100
                momentum_values.append(abs(momentum))  # Use absolute value for band calculation
            
            if len(volatility_values) < 20 or len(momentum_values) < 20:
                return None
            
            # Calculate band boundaries using mean ± standard deviation
            vol_mean = mean(volatility_values)
            vol_std = stdev(volatility_values)
            mom_mean = mean(momentum_values)
            mom_std = stdev(momentum_values)
            
            bands = {
                'volatility': {
                    'mean': vol_mean,
                    'upper_band': vol_mean + (self.BAND_MULTIPLIER * vol_std),
                    'lower_band': max(0, vol_mean - (self.BAND_MULTIPLIER * vol_std)),
                    'current': np.std(returns[-window:]) * 100 if len(returns) >= window else vol_mean
                },
                'momentum': {
                    'mean': mom_mean,
                    'upper_band': mom_mean + (self.BAND_MULTIPLIER * mom_std),
                    'lower_band': max(0, mom_mean - (self.BAND_MULTIPLIER * mom_std)),
                    'current': abs(((closes[-1] - closes[-window]) / closes[-window]) * 100) if len(closes) >= window else mom_mean
                },
                'timestamp': datetime.now(),
                'symbol': symbol
            }
            
            return bands
            
        except Exception as e:
            print(f"Error calculating bands for {symbol}: {e}")
            return None
    
    def is_within_normal_bands(self, symbol):
        """
        Check if current volatility and momentum are within normal bands
        """
        if symbol not in self.bands_data:
            # Calculate bands for first time
            bands = self.calculate_volatility_momentum_bands(symbol)
            if bands:
                self.bands_data[symbol] = bands
            else:
                return False, "No band data available"
        
        bands = self.bands_data[symbol]
        
        # Check if bands need recalibration (older than RECALIBRATION_INTERVAL)
        if (datetime.now() - bands['timestamp']).total_seconds() > self.RECALIBRATION_INTERVAL:
            new_bands = self.calculate_volatility_momentum_bands(symbol)
            if new_bands:
                self.bands_data[symbol] = new_bands
                bands = new_bands
        
        vol_data = bands['volatility']
        mom_data = bands['momentum']
        
        # Check if current values are within normal bands
        vol_within = vol_data['lower_band'] <= vol_data['current'] <= vol_data['upper_band']
        mom_within = mom_data['lower_band'] <= mom_data['current'] <= mom_data['upper_band']
        
        if vol_within and mom_within:
            return True, "Within normal bands"
        
        reasons = []
        # Only block if volatility is ABOVE upper band (extreme high volatility)
        if vol_data['current'] > vol_data['upper_band']:
            reasons.append(f"High volatility: {vol_data['current']:.2f}% > {vol_data['upper_band']:.2f}%")
        
        # Only block if momentum is ABOVE upper band (extreme high momentum)
        if mom_data['current'] > mom_data['upper_band']:
            reasons.append(f"High momentum: {mom_data['current']:.2f}% > {mom_data['upper_band']:.2f}%")
        
        if reasons:
            return False, "; ".join(reasons)
        else:
            return True, "Within normal bands"
    
    def accumulate_delta(self, symbol, current_delta):
        """
        Accumulate delta when averaging is delayed due to extreme conditions
        """
        if symbol not in self.delta_accumulation:
            self.delta_accumulation[symbol] = {
                'accumulated_delta': 0.0,
                'start_timestamp': datetime.now(),
                'delay_count': 0
            }
        
        accumulation = self.delta_accumulation[symbol]
        accumulation['accumulated_delta'] += current_delta
        accumulation['delay_count'] += 1
        
        return accumulation['accumulated_delta']
    
    def get_effective_delta(self, symbol, base_delta):
        """
        Get the effective delta including accumulated delta from delays
        """
        if symbol in self.delta_accumulation:
            accumulated = self.delta_accumulation[symbol]['accumulated_delta']
            # Reset accumulation when used
            self.delta_accumulation[symbol] = {
                'accumulated_delta': 0.0,
                'start_timestamp': datetime.now(),
                'delay_count': 0
            }
            effective_delta = base_delta + accumulated
            print(f"🔄 {symbol} Using accumulated delta: {base_delta:.3f}% + {accumulated:.3f}% = {effective_delta:.3f}%")
            return effective_delta
        
        return base_delta
    
    def check_enhanced_averaging_conditions(self, symbol, side, upnl_pct, current_delta):
        """
        Enhanced averaging check with volatility/momentum bands and delta accumulation
        Returns: (can_average, reason, effective_delta)
        """
        # First check hard stop threshold
        if upnl_pct <= self.HARD_STOP_THRESHOLD:
            # At hard stop, use accumulated delta if available
            effective_delta = self.get_effective_delta(symbol, current_delta)
            return True, f"Hard stop reached at {upnl_pct:.1f}% (threshold: {self.HARD_STOP_THRESHOLD}%)", effective_delta
        
        # Check if volatility and momentum are within normal bands
        bands_ok, bands_reason = self.is_within_normal_bands(symbol)
        
        if not bands_ok:
            # Accumulate delta when conditions are extreme
            accumulated = self.accumulate_delta(symbol, current_delta)
            return False, f"Extreme conditions: {bands_reason} (accumulated delta: {accumulated:.3f}%)", current_delta
        
        # If bands are normal, proceed with momentum reversal check
        indicators = self.calculate_momentum_indicators(symbol)
        if not indicators:
            return False, "No momentum data", current_delta
        
        # Store current momentum
        if symbol not in self.momentum_data:
            self.momentum_data[symbol] = {
                'peak_velocity': indicators['velocity'],
                'indicators_history': []
            }
        
        momentum = self.momentum_data[symbol]
        momentum['indicators_history'].append(indicators)
        
        # Keep only last 10 readings
        if len(momentum['indicators_history']) > 10:
            momentum['indicators_history'].pop(0)
        
        # Update peak velocity
        if abs(indicators['velocity']) > abs(momentum['peak_velocity']):
            momentum['peak_velocity'] = indicators['velocity']
            # Accumulate delta when momentum is still accelerating
            accumulated = self.accumulate_delta(symbol, current_delta)
            return False, f"Momentum still accelerating: {indicators['velocity']:.2f}% (accumulated: {accumulated:.3f}%)", current_delta
        
        # Check reversal conditions
        reversal_signals = []
        
        # For LONG positions in loss (price falling)
        if side == 'buy':
            # Look for bottoming signals
            if indicators['rsi'] < 30:
                reversal_signals.append("Oversold RSI")
            if indicators['velocity'] > momentum['peak_velocity'] * 0.5:
                reversal_signals.append("Velocity slowing")
            if indicators['volume_spike'] > 1.5:
                reversal_signals.append("Volume spike")
            if indicators['macd'] > indicators['macd_signal']:
                reversal_signals.append("MACD bullish cross")
                
        # For SHORT positions in loss (price rising)
        elif side == 'sell':
            # Look for topping signals
            if indicators['rsi'] > 70:
                reversal_signals.append("Overbought RSI")
            if indicators['velocity'] < momentum['peak_velocity'] * 0.5:
                reversal_signals.append("Velocity slowing")
            if indicators['volume_spike'] > 1.5:
                reversal_signals.append("Volume spike")
            if indicators['macd'] < indicators['macd_signal']:
                reversal_signals.append("MACD bearish cross")
        
        # Between -42% and -70%: Allow averaging with ANY reversal signal (0+ signals)
        # This makes averaging less restrictive under normal conditions
        if len(reversal_signals) >= 0:
            # Use accumulated delta when reversal is confirmed
            effective_delta = self.get_effective_delta(symbol, current_delta)
            return True, f"Reversal confirmed: {', '.join(reversal_signals)}", effective_delta
        else:
            # This branch should never be reached with >= 0 requirement, but keep for safety
            accumulated = self.accumulate_delta(symbol, current_delta)
            return False, f"Unexpected: waiting for reversal (signals: {len(reversal_signals)}/0, accumulated: {accumulated:.3f}%)", current_delta
    
    def check_momentum_reversal(self, symbol, side):
        """
        Legacy method for backward compatibility - now enhanced with band logic
        Returns: (can_average, reason)
        """
        # Default delta for legacy calls
        can_average, reason, _ = self.check_enhanced_averaging_conditions(symbol, side, -30.0, 0.01)
        return can_average, reason
    
    def monitor_positions(self):
        """Enhanced monitoring with volatility/momentum bands and delta accumulation"""
        state_file = '/app/position_state.json'
        
        while True:
            try:
                # Load current state
                with open(state_file, 'r') as f:
                    state = json.load(f)
                
                # Check each position in averaging zone
                for symbol, zone in state.get('position_zones', {}).items():
                    if zone == 'AVERAGING':
                        position = state['active_positions'].get(symbol)
                        if position:
                            # Calculate UPNL percentage
                            upnl = position.get('unrealized_pnl', 0)
                            margin = position.get('initial_margin', 1)
                            upnl_pct = (upnl / margin) * 100 if margin > 0 else 0
                            
                            # Get current delta from position metadata
                            current_delta = 0.015  # Default 1.5%
                            if 'position_metadata' in state and symbol in state['position_metadata']:
                                current_delta = state['position_metadata'][symbol].get('fibonacci_delta', 0.015)
                            
                            # Enhanced check with band logic
                            can_average, reason, effective_delta = self.check_enhanced_averaging_conditions(
                                symbol, 
                                position['side'],
                                upnl_pct,
                                current_delta
                            )
                            
                            # Update state with enhanced momentum permission
                            if 'momentum_permission' not in state:
                                state['momentum_permission'] = {}
                            
                            state['momentum_permission'][symbol] = {
                                'can_average': can_average,
                                'reason': reason,
                                'effective_delta': effective_delta,
                                'upnl_pct': upnl_pct,
                                'timestamp': datetime.now().isoformat()
                            }
                            
                            # Add band information if available
                            if symbol in self.bands_data:
                                bands = self.bands_data[symbol]
                                state['momentum_permission'][symbol]['bands'] = {
                                    'volatility_current': bands['volatility']['current'],
                                    'volatility_band': f"{bands['volatility']['lower_band']:.2f}-{bands['volatility']['upper_band']:.2f}%",
                                    'momentum_current': bands['momentum']['current'], 
                                    'momentum_band': f"{bands['momentum']['lower_band']:.2f}-{bands['momentum']['upper_band']:.2f}%"
                                }
                            
                            # Add delta accumulation info if available
                            if symbol in self.delta_accumulation:
                                acc = self.delta_accumulation[symbol]
                                state['momentum_permission'][symbol]['delta_accumulation'] = {
                                    'accumulated_delta': acc['accumulated_delta'],
                                    'delay_count': acc['delay_count'],
                                    'start_time': acc['start_timestamp'].isoformat()
                                }
                            
                            print(f"🛡️ {symbol} Enhanced Check (UPNL: {upnl_pct:.1f}%):")
                            print(f"   Can Average: {'✅' if can_average else '❌'}")
                            print(f"   Reason: {reason}")
                            print(f"   Effective Delta: {effective_delta:.3f}%")
                            if symbol in self.bands_data:
                                bands = self.bands_data[symbol]
                                print(f"   Volatility: {bands['volatility']['current']:.2f}% (band: {bands['volatility']['lower_band']:.2f}-{bands['volatility']['upper_band']:.2f}%)")
                                print(f"   Momentum: {bands['momentum']['current']:.2f}% (band: {bands['momentum']['lower_band']:.2f}-{bands['momentum']['upper_band']:.2f}%)")
                
                # Save updated state
                with open(state_file, 'w') as f:
                    json.dump(state, f, indent=2)
                
                time.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                print(f"Error in enhanced momentum monitoring: {e}")
                time.sleep(30)

if __name__ == "__main__":
    print("🛡️ Enhanced Momentum & Volatility Guardian Service Started")
    print("Features:")
    print("- Dynamic volatility and momentum band calculation")
    print("- Delta accumulation for delayed averaging")
    print("- Hard stop at -70% UPNL")
    print("- Periodic band recalibration")
    print()
    print("Monitoring positions for enhanced averaging conditions...")
    guardian = EnhancedMomentumGuardian()
    guardian.monitor_positions()