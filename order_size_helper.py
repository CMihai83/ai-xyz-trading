#!/usr/bin/env python3
"""
Order Size Helper - Ensures correct decimal precision for Bitget orders
"""
import math
from bitget_symbols_manager import BitgetSymbolsManager

class OrderSizeHelper:
    def __init__(self):
        self.symbols_manager = BitgetSymbolsManager()
        # Load existing data on init
        self.symbols_manager.load_symbols_data()
        # Start background update service
        self.symbols_manager.start_background_service(update_interval=3600)
    
    def prepare_order_size(self, symbol: str, amount: float, round_up: bool = True) -> float:
        """
        Prepare order size with correct precision for a symbol
        
        Args:
            symbol: Trading symbol (e.g., 'BTC/USDT:USDT')
            amount: Desired amount
            round_up: Whether to round up (for meeting minimums) or use normal rounding
            
        Returns:
            Properly rounded amount for the symbol
        """
        # Get symbol info
        info = self.symbols_manager.get_symbol_info(symbol)
        
        if not info:
            print(f"⚠️ Symbol {symbol} not found, using default rounding to whole number")
            return math.ceil(amount) if round_up else round(amount)
        
        precision = info.get('amount_precision', 0)
        min_amount = float(info.get('min_amount', 1))
        lot_size = float(info.get('lot_size', 1))

        print(f"DEBUG: lot_size type={type(lot_size)}, value={lot_size}")

        # Round to lot size first
        # CRITICAL: Convert to float to prevent integer overflow on large amounts (e.g., SHIB)
        if lot_size > 0:
            amount = float(amount)
            lot_size = float(lot_size)
            if round_up:
                amount = float(math.ceil(amount / lot_size)) * lot_size
            else:
                amount = float(round(amount / lot_size)) * lot_size
        
        # Then apply precision
        if precision == 0:
            # No decimals allowed
            amount = float(math.ceil(amount)) if round_up else float(round(amount))
        else:
            # Round to specified decimal places
            # CRITICAL: Use Python's round() which handles large numbers safely
            # Avoid math.ceil(amount * multiplier) which causes overflow on large amounts
            if round_up:
                # Round up to precision decimals
                amount = float(math.ceil(amount * (10 ** precision))) / (10 ** precision)
            else:
                # Normal rounding to precision decimals
                amount = float(round(amount, precision))
        
        # Ensure minimum
        if amount < min_amount:
            amount = min_amount
        
        return amount
    
    def validate_order_size(self, symbol: str, amount: float, price: float) -> dict:
        """
        Validate if order size meets requirements
        
        Returns:
            dict with 'valid' boolean and 'reason' if invalid
        """
        info = self.symbols_manager.get_symbol_info(symbol)
        
        if not info:
            return {
                'valid': False,
                'reason': f'Symbol {symbol} not found in database'
            }
        
        min_amount = info.get('min_amount', 1)
        max_amount = info.get('max_amount')
        min_cost = info.get('min_cost', 5)
        
        # Check minimum amount
        if amount < min_amount:
            return {
                'valid': False,
                'reason': f'Amount {amount} below minimum {min_amount}'
            }
        
        # Check maximum amount
        if max_amount and amount > max_amount:
            return {
                'valid': False,
                'reason': f'Amount {amount} above maximum {max_amount}'
            }
        
        # Check minimum cost (notional value)
        cost = amount * price
        if cost < min_cost:
            return {
                'valid': False,
                'reason': f'Notional value ${cost:.2f} below minimum ${min_cost}'
            }
        
        # Check precision
        precision = info.get('amount_precision', 0)
        if precision == 0 and amount != int(amount):
            return {
                'valid': False,
                'reason': f'Symbol requires whole contracts, got {amount}'
            }
        
        return {'valid': True}
    
    def get_minimum_order_requirements(self, symbol: str, price: float) -> dict:
        """Get minimum order requirements for a symbol at current price"""
        info = self.symbols_manager.get_symbol_info(symbol)
        
        if not info:
            return {
                'min_contracts': 1,
                'min_notional': 5,
                'min_margin_at_10x': 0.5
            }
        
        min_amount = info.get('min_amount', 1)
        min_cost = info.get('min_cost', 5)
        
        # Calculate minimum contracts to meet cost requirement
        min_contracts_for_cost = math.ceil(min_cost / price) if price > 0 else min_amount
        
        # Take the larger of the two minimums
        min_contracts = max(min_amount, min_contracts_for_cost)
        
        return {
            'min_contracts': min_contracts,
            'min_notional': min_contracts * price,
            'min_margin_at_10x': (min_contracts * price) / 10,
            'precision': info.get('amount_precision', 0),
            'requires_whole': info.get('requires_whole_contracts', True)
        }

# Example usage
if __name__ == "__main__":
    helper = OrderSizeHelper()
    
    # Test with ASTER
    symbol = 'ASTER/USDT:USDT'
    amount = 2.94  # Decimal amount
    price = 2.10
    
    print(f"Original amount: {amount}")
    rounded = helper.prepare_order_size(symbol, amount, round_up=True)
    print(f"Rounded amount: {rounded}")
    
    validation = helper.validate_order_size(symbol, rounded, price)
    print(f"Validation: {validation}")
    
    requirements = helper.get_minimum_order_requirements(symbol, price)
    print(f"Minimum requirements: {requirements}")