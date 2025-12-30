#!/usr/bin/env python3
"""
Smart Leverage Manager for AI-XYZ
Implements anti-liquidation leverage with Kelly Criterion
Dynamically adjusts leverage based on market conditions
"""

import json
import numpy as np
from typing import Dict, Tuple
from datetime import datetime, timedelta


class SmartLeverageManager:
    """
    Intelligent leverage management to prevent liquidation
    Uses Kelly Criterion with safety factors
    """

    def __init__(self):
        self.config_file = '/app/runtime_config.json'
        self.state_file = '/app/position_state.json'
        self.max_allowed_leverage = 20
        self.min_allowed_leverage = 1
        self.safety_factor = 0.25  # Quarter Kelly for safety
        self.volatility_history = {}
        self.win_rate_history = {}

    def calculate_safe_leverage(
        self,
        symbol: str,
        volatility: float,
        win_rate: float = 0.5,
        current_drawdown: float = 0
    ) -> int:
        """
        Calculate safe leverage using Kelly Criterion with safety factors

        Args:
            symbol: Trading symbol
            volatility: Current market volatility (0-1 scale)
            win_rate: Historical win rate (0-1)
            current_drawdown: Current portfolio drawdown (%)

        Returns:
            Safe leverage to use (integer)
        """

        # Kelly-inspired leverage calculation
        edge = win_rate - 0.5  # Edge over random
        odds = 1.5  # Average profit/loss ratio target

        # Base Kelly leverage
        if volatility > 0:
            kelly_leverage = (edge * odds) / (volatility ** 2)
        else:
            kelly_leverage = 10

        # Apply quarter-Kelly for safety
        safe_kelly = kelly_leverage * self.safety_factor

        # Volatility-based cap (high volatility = lower leverage)
        volatility_cap = 10 / (1 + volatility * 5)

        # Drawdown adjustment (reduce leverage during drawdowns)
        drawdown_factor = 1.0
        if current_drawdown < -10:
            drawdown_factor = 0.8
        elif current_drawdown < -20:
            drawdown_factor = 0.6
        elif current_drawdown < -30:
            drawdown_factor = 0.4

        # Market regime adjustments
        regime_factor = self._get_regime_factor(volatility)

        # Calculate final leverage
        calculated_leverage = min(
            safe_kelly * drawdown_factor * regime_factor,
            volatility_cap,
            self.max_allowed_leverage
        )

        # Ensure minimum leverage
        final_leverage = max(
            int(calculated_leverage),
            self.min_allowed_leverage
        )

        # Log the calculation
        self._log_leverage_decision(
            symbol=symbol,
            volatility=volatility,
            win_rate=win_rate,
            kelly_raw=kelly_leverage,
            kelly_safe=safe_kelly,
            volatility_cap=volatility_cap,
            drawdown_factor=drawdown_factor,
            final=final_leverage
        )

        return final_leverage

    def _get_regime_factor(self, volatility: float) -> float:
        """
        Get leverage adjustment factor based on market regime

        Args:
            volatility: Current volatility

        Returns:
            Regime adjustment factor
        """
        if volatility < 0.1:  # Low volatility
            return 1.2  # Can use slightly higher leverage
        elif volatility < 0.3:  # Normal volatility
            return 1.0  # Standard leverage
        elif volatility < 0.5:  # High volatility
            return 0.7  # Reduce leverage
        else:  # Extreme volatility
            return 0.4  # Significantly reduce leverage

    def adjust_position_leverage(self, symbol: str) -> Dict:
        """
        Adjust leverage for an existing position based on current conditions

        Args:
            symbol: Trading symbol

        Returns:
            Dictionary with adjustment details
        """
        try:
            # Load current state
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            position = state.get('positions', {}).get(symbol)
            if not position:
                return {'error': f'No position found for {symbol}'}

            # Calculate current metrics
            current_leverage = position.get('leverage', 8)
            upnl = position.get('unrealized_pnl', 0)
            entry = position.get('entry_price', 0)
            amount = position.get('amount', 0)

            if entry > 0 and amount > 0:
                position_value = entry * amount
                upnl_pct = (upnl / position_value) * 100
            else:
                upnl_pct = 0

            # Estimate volatility (simplified - would use real market data)
            volatility = self._estimate_volatility(symbol)

            # Get historical win rate
            win_rate = self.win_rate_history.get(symbol, 0.5)

            # Calculate new safe leverage
            new_leverage = self.calculate_safe_leverage(
                symbol=symbol,
                volatility=volatility,
                win_rate=win_rate,
                current_drawdown=upnl_pct
            )

            # Determine if adjustment needed
            needs_adjustment = abs(new_leverage - current_leverage) >= 2

            adjustment = {
                'symbol': symbol,
                'current_leverage': current_leverage,
                'recommended_leverage': new_leverage,
                'needs_adjustment': needs_adjustment,
                'reason': self._get_adjustment_reason(
                    current_leverage,
                    new_leverage,
                    volatility
                ),
                'timestamp': datetime.now().isoformat()
            }

            # Update configuration if needed
            if needs_adjustment:
                self._update_leverage_config(new_leverage)

            return adjustment

        except Exception as e:
            return {'error': str(e)}

    def _estimate_volatility(self, symbol: str) -> float:
        """
        Estimate current volatility for symbol
        In production, would use real price data

        Args:
            symbol: Trading symbol

        Returns:
            Estimated volatility (0-1 scale)
        """
        # Simplified volatility estimation
        # In production, calculate from historical price data
        base_volatility = 0.2  # Default 20% volatility

        # Adjust based on symbol characteristics
        if 'BTC' in symbol:
            base_volatility *= 0.8  # BTC generally less volatile
        elif any(x in symbol for x in ['MEME', 'PUMP', 'PEPE']):
            base_volatility *= 2.0  # Meme coins more volatile

        return min(base_volatility, 1.0)

    def _get_adjustment_reason(
        self,
        current: int,
        recommended: int,
        volatility: float
    ) -> str:
        """
        Get human-readable reason for leverage adjustment

        Args:
            current: Current leverage
            recommended: Recommended leverage
            volatility: Current volatility

        Returns:
            Reason string
        """
        if recommended > current:
            if volatility < 0.1:
                return "Low volatility allows higher leverage"
            else:
                return "Favorable conditions for increased leverage"
        elif recommended < current:
            if volatility > 0.4:
                return "High volatility requires leverage reduction"
            else:
                return "Risk conditions suggest lower leverage"
        else:
            return "Current leverage is optimal"

    def _update_leverage_config(self, new_leverage: int):
        """
        Update runtime configuration with new leverage

        Args:
            new_leverage: New leverage value
        """
        try:
            # Load current config
            with open(self.config_file, 'r') as f:
                config = json.load(f)

            # Update leverage
            config['leverage'] = new_leverage

            # Save updated config
            with open(self.config_file, 'w') as f:
                json.dump(config, f, indent=2)

            print(f"✅ Leverage updated to {new_leverage}x in config")

        except Exception as e:
            print(f"❌ Error updating leverage config: {e}")

    def _log_leverage_decision(self, **kwargs):
        """Log leverage calculation details"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            **kwargs
        }

        # In production, would log to file or database
        if kwargs.get('final') != 8:  # Only log if different from default
            print(f"📊 Leverage Decision: {kwargs['symbol']} = {kwargs['final']}x")
            print(f"   Volatility: {kwargs['volatility']:.2%}")
            print(f"   Kelly Raw: {kwargs['kelly_raw']:.1f}x")
            print(f"   Kelly Safe: {kwargs['kelly_safe']:.1f}x")

    def monitor_and_adjust_all_positions(self) -> Dict:
        """
        Monitor all positions and suggest leverage adjustments

        Returns:
            Dictionary of adjustment recommendations
        """
        recommendations = {}

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            positions = state.get('positions', {})

            for symbol in positions:
                adjustment = self.adjust_position_leverage(symbol)
                if adjustment.get('needs_adjustment'):
                    recommendations[symbol] = adjustment

            return recommendations

        except Exception as e:
            return {'error': str(e)}


def main():
    """Test smart leverage manager"""
    manager = SmartLeverageManager()

    # Test cases
    test_cases = [
        ("BTC/USDT", 0.15, 0.55),  # Low volatility, positive edge
        ("MEME/USDT", 0.45, 0.48),  # High volatility, negative edge
        ("ETH/USDT", 0.25, 0.52),  # Medium volatility, small edge
    ]

    print("\n" + "="*60)
    print("SMART LEVERAGE MANAGER TEST")
    print("="*60)

    for symbol, volatility, win_rate in test_cases:
        leverage = manager.calculate_safe_leverage(
            symbol=symbol,
            volatility=volatility,
            win_rate=win_rate
        )
        print(f"\n{symbol}:")
        print(f"  Volatility: {volatility:.1%}")
        print(f"  Win Rate: {win_rate:.1%}")
        print(f"  ✅ Recommended Leverage: {leverage}x")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()