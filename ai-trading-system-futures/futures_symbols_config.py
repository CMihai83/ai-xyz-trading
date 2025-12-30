#!/usr/bin/env python3
"""
Futures Trading Symbols Configuration
Defines precise decimal handling, minimum sizes, and leverage for each trading pair.
"""

FUTURES_SYMBOLS_CONFIG = {
    # Major Cryptocurrencies
    'BTCUSDT': {
        'symbol': 'BTCUSDT',
        'base_asset': 'BTC',
        'quote_asset': 'USDT',
        'price_precision': 2,
        'quantity_precision': 6,
        'min_quantity': 0.000001,
        'max_quantity': 1000.0,
        'min_notional': 5.0,
        'max_notional': 1000000.0,
        'tick_size': 0.01,
        'step_size': 0.000001,
        'max_leverage': 125,
        'min_leverage': 1,
        'default_leverage': 20,
        'margin_requirement': 0.008,  # 0.8% initial margin at 125x
        'maintenance_margin': 0.004,  # 0.4% maintenance margin
        'funding_interval': 8,  # hours
        'contract_size': 0.001,
        'settlement_currency': 'USDT'
    },
    'ETHUSDT': {
        'symbol': 'ETHUSDT',
        'base_asset': 'ETH',
        'quote_asset': 'USDT',
        'price_precision': 2,
        'quantity_precision': 4,
        'min_quantity': 0.0001,
        'max_quantity': 10000.0,
        'min_notional': 5.0,
        'max_notional': 500000.0,
        'tick_size': 0.01,
        'step_size': 0.0001,
        'max_leverage': 100,
        'min_leverage': 1,
        'default_leverage': 15,
        'margin_requirement': 0.01,
        'maintenance_margin': 0.005,
        'funding_interval': 8,
        'contract_size': 0.01,
        'settlement_currency': 'USDT'
    },
    'BNBUSDT': {
        'symbol': 'BNBUSDT',
        'base_asset': 'BNB',
        'quote_asset': 'USDT',
        'price_precision': 3,
        'quantity_precision': 2,
        'min_quantity': 0.01,
        'max_quantity': 10000.0,
        'min_notional': 5.0,
        'max_notional': 200000.0,
        'tick_size': 0.001,
        'step_size': 0.01,
        'max_leverage': 75,
        'min_leverage': 1,
        'default_leverage': 10,
        'margin_requirement': 0.0133,
        'maintenance_margin': 0.0067,
        'funding_interval': 8,
        'contract_size': 0.1,
        'settlement_currency': 'USDT'
    },
    'ADAUSDT': {
        'symbol': 'ADAUSDT',
        'base_asset': 'ADA',
        'quote_asset': 'USDT',
        'price_precision': 4,
        'quantity_precision': 1,
        'min_quantity': 0.1,
        'max_quantity': 1000000.0,
        'min_notional': 5.0,
        'max_notional': 100000.0,
        'tick_size': 0.0001,
        'step_size': 0.1,
        'max_leverage': 50,
        'min_leverage': 1,
        'default_leverage': 8,
        'margin_requirement': 0.02,
        'maintenance_margin': 0.01,
        'funding_interval': 8,
        'contract_size': 1.0,
        'settlement_currency': 'USDT'
    },
    'SOLUSDT': {
        'symbol': 'SOLUSDT',
        'base_asset': 'SOL',
        'quote_asset': 'USDT',
        'price_precision': 3,
        'quantity_precision': 2,
        'min_quantity': 0.01,
        'max_quantity': 50000.0,
        'min_notional': 5.0,
        'max_notional': 150000.0,
        'tick_size': 0.001,
        'step_size': 0.01,
        'max_leverage': 50,
        'min_leverage': 1,
        'default_leverage': 12,
        'margin_requirement': 0.02,
        'maintenance_margin': 0.01,
        'funding_interval': 8,
        'contract_size': 0.1,
        'settlement_currency': 'USDT'
    },
    'XRPUSDT': {
        'symbol': 'XRPUSDT',
        'base_asset': 'XRP',
        'quote_asset': 'USDT',
        'price_precision': 4,
        'quantity_precision': 1,
        'min_quantity': 0.1,
        'max_quantity': 1000000.0,
        'min_notional': 5.0,
        'max_notional': 100000.0,
        'tick_size': 0.0001,
        'step_size': 0.1,
        'max_leverage': 50,
        'min_leverage': 1,
        'default_leverage': 10,
        'margin_requirement': 0.02,
        'maintenance_margin': 0.01,
        'funding_interval': 8,
        'contract_size': 1.0,
        'settlement_currency': 'USDT'
    },
    'DOTUSDT': {
        'symbol': 'DOTUSDT',
        'base_asset': 'DOT',
        'quote_asset': 'USDT',
        'price_precision': 3,
        'quantity_precision': 2,
        'min_quantity': 0.01,
        'max_quantity': 100000.0,
        'min_notional': 5.0,
        'max_notional': 80000.0,
        'tick_size': 0.001,
        'step_size': 0.01,
        'max_leverage': 50,
        'min_leverage': 1,
        'default_leverage': 8,
        'margin_requirement': 0.02,
        'maintenance_margin': 0.01,
        'funding_interval': 8,
        'contract_size': 0.1,
        'settlement_currency': 'USDT'
    },
    'AVAXUSDT': {
        'symbol': 'AVAXUSDT',
        'base_asset': 'AVAX',
        'quote_asset': 'USDT',
        'price_precision': 3,
        'quantity_precision': 2,
        'min_quantity': 0.01,
        'max_quantity': 50000.0,
        'min_notional': 5.0,
        'max_notional': 100000.0,
        'tick_size': 0.001,
        'step_size': 0.01,
        'max_leverage': 50,
        'min_leverage': 1,
        'default_leverage': 10,
        'margin_requirement': 0.02,
        'maintenance_margin': 0.01,
        'funding_interval': 8,
        'contract_size': 0.1,
        'settlement_currency': 'USDT'
    },
    'LINKUSDT': {
        'symbol': 'LINKUSDT',
        'base_asset': 'LINK',
        'quote_asset': 'USDT',
        'price_precision': 3,
        'quantity_precision': 2,
        'min_quantity': 0.01,
        'max_quantity': 100000.0,
        'min_notional': 5.0,
        'max_notional': 80000.0,
        'tick_size': 0.001,
        'step_size': 0.01,
        'max_leverage': 50,
        'min_leverage': 1,
        'default_leverage': 8,
        'margin_requirement': 0.02,
        'maintenance_margin': 0.01,
        'funding_interval': 8,
        'contract_size': 0.1,
        'settlement_currency': 'USDT'
    },
    'MATICUSDT': {
        'symbol': 'MATICUSDT',
        'base_asset': 'MATIC',
        'quote_asset': 'USDT',
        'price_precision': 4,
        'quantity_precision': 1,
        'min_quantity': 0.1,
        'max_quantity': 1000000.0,
        'min_notional': 5.0,
        'max_notional': 50000.0,
        'tick_size': 0.0001,
        'step_size': 0.1,
        'max_leverage': 25,
        'min_leverage': 1,
        'default_leverage': 5,
        'margin_requirement': 0.04,
        'maintenance_margin': 0.02,
        'funding_interval': 8,
        'contract_size': 1.0,
        'settlement_currency': 'USDT'
    }
}

def get_symbol_config(symbol):
    """Get configuration for a specific symbol."""
    return FUTURES_SYMBOLS_CONFIG.get(symbol.upper())

def format_price(symbol, price):
    """Format price according to symbol precision."""
    config = get_symbol_config(symbol)
    if not config:
        return round(price, 4)
    return round(price, config['price_precision'])

def format_quantity(symbol, quantity):
    """Format quantity according to symbol precision."""
    config = get_symbol_config(symbol)
    if not config:
        return round(quantity, 6)
    return round(quantity, config['quantity_precision'])

def validate_order_size(symbol, quantity, price):
    """Validate if order size meets minimum requirements."""
    config = get_symbol_config(symbol)
    if not config:
        return False, "Symbol configuration not found"
    
    if quantity < config['min_quantity']:
        return False, f"Quantity {quantity} below minimum {config['min_quantity']}"
    
    if quantity > config['max_quantity']:
        return False, f"Quantity {quantity} above maximum {config['max_quantity']}"
    
    notional = quantity * price
    if notional < config['min_notional']:
        return False, f"Notional {notional} below minimum {config['min_notional']}"
    
    if notional > config['max_notional']:
        return False, f"Notional {notional} above maximum {config['max_notional']}"
    
    return True, "Valid order size"

def calculate_margin_required(symbol, quantity, price, leverage):
    """Calculate margin required for a position."""
    config = get_symbol_config(symbol)
    if not config:
        return None
    
    notional = quantity * price
    margin_required = notional / leverage
    maintenance_margin = notional * config['maintenance_margin']
    
    return {
        'initial_margin': margin_required,
        'maintenance_margin': maintenance_margin,
        'notional_value': notional,
        'leverage': leverage
    }

def get_optimal_leverage(symbol, confidence, risk_tolerance=0.5):
    """Calculate optimal leverage based on confidence and risk tolerance."""
    config = get_symbol_config(symbol)
    if not config:
        return 1
    
    # Base leverage calculation
    base_leverage = config['default_leverage']
    max_leverage = config['max_leverage']
    
    # Adjust based on confidence (0.0 to 1.0)
    confidence_multiplier = confidence * risk_tolerance
    
    # Calculate optimal leverage
    optimal_leverage = int(base_leverage * (1 + confidence_multiplier))
    
    # Ensure within limits
    optimal_leverage = max(config['min_leverage'], min(optimal_leverage, max_leverage))
    
    return optimal_leverage

if __name__ == "__main__":
    # Test the configuration
    for symbol, config in FUTURES_SYMBOLS_CONFIG.items():
        print(f"{symbol}: Leverage {config['min_leverage']}-{config['max_leverage']}x, "
              f"Min Size: {config['min_quantity']}, "
              f"Price Precision: {config['price_precision']}")
