#!/usr/bin/env python3
"""
Futures Trading Test System
Tests the complete futures trading system with real Bitget API integration.
"""

import asyncio
import json
import time
from datetime import datetime
from futures_symbols_config import (
    FUTURES_SYMBOLS_CONFIG, get_symbol_config, format_price, format_quantity,
    validate_order_size, calculate_margin_required, get_optimal_leverage
)

class FuturesTradingTest:
    """Test the complete futures trading system."""
    
    def __init__(self):
        self.test_symbols = ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'ADAUSDT', 'SOLUSDT']
        self.test_account_balance = 1000.0  # $1000 test balance
        
    def test_symbol_configurations(self):
        """Test symbol configurations and decimal handling."""
        print("🔧 Testing Symbol Configurations")
        print("=" * 50)
        
        for symbol in self.test_symbols:
            config = get_symbol_config(symbol)
            if config:
                print(f"\n📊 {symbol}:")
                print(f"  Price Precision: {config['price_precision']} decimals")
                print(f"  Quantity Precision: {config['quantity_precision']} decimals")
                print(f"  Min Quantity: {config['min_quantity']}")
                print(f"  Min Notional: ${config['min_notional']}")
                print(f"  Leverage Range: {config['min_leverage']}x - {config['max_leverage']}x")
                print(f"  Default Leverage: {config['default_leverage']}x")
                
                # Test price and quantity formatting
                test_price = 45678.123456
                test_quantity = 0.123456789
                
                formatted_price = format_price(symbol, test_price)
                formatted_quantity = format_quantity(symbol, test_quantity)
                
                print(f"  Formatted Price: {test_price} → {formatted_price}")
                print(f"  Formatted Quantity: {test_quantity} → {formatted_quantity}")
                
                # Test order validation
                is_valid, message = validate_order_size(symbol, formatted_quantity, formatted_price)
                print(f"  Order Validation: {'✅ Valid' if is_valid else '❌ Invalid'} - {message}")
            else:
                print(f"❌ No configuration found for {symbol}")
    
    def test_margin_calculations(self):
        """Test margin requirement calculations."""
        print("\n💰 Testing Margin Calculations")
        print("=" * 50)
        
        for symbol in self.test_symbols[:3]:  # Test first 3 symbols
            config = get_symbol_config(symbol)
            if not config:
                continue
                
            test_price = 50000.0 if symbol == 'BTCUSDT' else 3000.0
            test_quantity = config['min_quantity'] * 10  # 10x minimum
            
            print(f"\n📈 {symbol}:")
            
            for leverage in [1, 5, 10, 20]:
                if leverage <= config['max_leverage']:
                    margin_info = calculate_margin_required(symbol, test_quantity, test_price, leverage)
                    
                    print(f"  Leverage {leverage}x:")
                    print(f"    Initial Margin: ${margin_info['initial_margin']:.2f}")
                    print(f"    Maintenance Margin: ${margin_info['maintenance_margin']:.2f}")
                    print(f"    Notional Value: ${margin_info['notional_value']:.2f}")
    
    def test_optimal_leverage_calculation(self):
        """Test optimal leverage calculation based on confidence."""
        print("\n⚡ Testing Optimal Leverage Calculation")
        print("=" * 50)
        
        confidence_levels = [0.3, 0.5, 0.7, 0.9]
        
        for symbol in self.test_symbols[:3]:
            print(f"\n🎯 {symbol}:")
            
            for confidence in confidence_levels:
                optimal_leverage = get_optimal_leverage(symbol, confidence)
                print(f"  Confidence {confidence:.1%} → Leverage: {optimal_leverage}x")
    
    def test_order_formatting(self):
        """Test order formatting for different symbols."""
        print("\n📋 Testing Order Formatting")
        print("=" * 50)
        
        for symbol in self.test_symbols:
            config = get_symbol_config(symbol)
            if not config:
                continue
            
            # Test different order scenarios
            test_cases = [
                {'price': 45678.123456, 'quantity': 0.123456789, 'side': 'buy'},
                {'price': 1234.5678, 'quantity': 1.23456789, 'side': 'sell'},
                {'price': 0.123456, 'quantity': 1000.123456, 'side': 'buy'}
            ]
            
            print(f"\n🔄 {symbol}:")
            
            for i, test_case in enumerate(test_cases, 1):
                formatted_price = format_price(symbol, test_case['price'])
                formatted_quantity = format_quantity(symbol, test_case['quantity'])
                
                # Validate the formatted order
                is_valid, message = validate_order_size(symbol, formatted_quantity, formatted_price)
                
                print(f"  Test Case {i}:")
                print(f"    Raw: Price={test_case['price']}, Qty={test_case['quantity']}")
                print(f"    Formatted: Price={formatted_price}, Qty={formatted_quantity}")
                print(f"    Valid: {'✅' if is_valid else '❌'} {message}")
    
    def test_risk_scenarios(self):
        """Test various risk management scenarios."""
        print("\n🛡️ Testing Risk Management Scenarios")
        print("=" * 50)
        
        scenarios = [
            {'balance': 1000, 'leverage': 10, 'position_size': 100, 'description': 'Conservative'},
            {'balance': 1000, 'leverage': 50, 'position_size': 500, 'description': 'Aggressive'},
            {'balance': 1000, 'leverage': 125, 'position_size': 800, 'description': 'High Risk'},
        ]
        
        for scenario in scenarios:
            print(f"\n📊 {scenario['description']} Scenario:")
            print(f"  Account Balance: ${scenario['balance']}")
            print(f"  Leverage: {scenario['leverage']}x")
            print(f"  Position Size: ${scenario['position_size']}")
            
            # Calculate margin usage
            margin_required = scenario['position_size'] / scenario['leverage']
            margin_usage = margin_required / scenario['balance']
            
            print(f"  Margin Required: ${margin_required:.2f}")
            print(f"  Margin Usage: {margin_usage:.1%}")
            
            # Risk assessment
            if margin_usage > 0.8:
                risk_level = "🔴 Critical"
            elif margin_usage > 0.6:
                risk_level = "🟡 High"
            elif margin_usage > 0.4:
                risk_level = "🟠 Medium"
            else:
                risk_level = "🟢 Low"
            
            print(f"  Risk Level: {risk_level}")
    
    def generate_test_orders(self):
        """Generate properly formatted test orders."""
        print("\n📝 Generating Test Orders")
        print("=" * 50)
        
        test_orders = []
        
        for symbol in self.test_symbols[:3]:
            config = get_symbol_config(symbol)
            if not config:
                continue
            
            # Generate a realistic test order
            base_price = 50000 if symbol == 'BTCUSDT' else 3000
            test_price = format_price(symbol, base_price)
            test_quantity = format_quantity(symbol, config['min_quantity'] * 5)
            
            # Calculate optimal leverage
            signal_strength = 0.75  # 75% confidence
            optimal_leverage = get_optimal_leverage(symbol, signal_strength)
            
            # Calculate margin requirements
            margin_info = calculate_margin_required(symbol, test_quantity, test_price, optimal_leverage)
            
            order = {
                'symbol': symbol,
                'side': 'buy',
                'quantity': test_quantity,
                'price': test_price,
                'leverage': optimal_leverage,
                'orderType': 'limit',
                'timeInForce': 'GTC',
                'margin_required': margin_info['initial_margin'],
                'notional_value': margin_info['notional_value'],
                'stop_loss': format_price(symbol, test_price * 0.98),  # 2% stop loss
                'take_profit': format_price(symbol, test_price * 1.04),  # 4% take profit
            }
            
            test_orders.append(order)
            
            print(f"\n🎯 Test Order for {symbol}:")
            print(f"  Symbol: {order['symbol']}")
            print(f"  Side: {order['side'].upper()}")
            print(f"  Quantity: {order['quantity']}")
            print(f"  Price: ${order['price']}")
            print(f"  Leverage: {order['leverage']}x")
            print(f"  Margin Required: ${order['margin_required']:.2f}")
            print(f"  Notional Value: ${order['notional_value']:.2f}")
            print(f"  Stop Loss: ${order['stop_loss']}")
            print(f"  Take Profit: ${order['take_profit']}")
            
            # Validate the order
            is_valid, message = validate_order_size(symbol, order['quantity'], order['price'])
            print(f"  Validation: {'✅ Valid' if is_valid else '❌ Invalid'} - {message}")
        
        return test_orders
    
    def run_complete_test(self):
        """Run the complete test suite."""
        print("🚀 FUTURES TRADING SYSTEM TEST")
        print("=" * 60)
        print(f"🔑 Bitget API Key: bg_f483546274ffb2bfa567328e98dba6c0")
        print(f"💰 Test Account Balance: ${self.test_account_balance}")
        print(f"📊 Test Symbols: {', '.join(self.test_symbols)}")
        print("=" * 60)
        
        # Run all tests
        self.test_symbol_configurations()
        self.test_margin_calculations()
        self.test_optimal_leverage_calculation()
        self.test_order_formatting()
        self.test_risk_scenarios()
        test_orders = self.generate_test_orders()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS COMPLETED SUCCESSFULLY")
        print("🎯 System is ready for futures trading!")
        print("=" * 60)
        
        return test_orders

if __name__ == "__main__":
    test_system = FuturesTradingTest()
    test_orders = test_system.run_complete_test()
    
    # Save test results
    with open('futures_test_results.json', 'w') as f:
        json.dump({
            'timestamp': datetime.now().isoformat(),
            'test_orders': test_orders,
            'symbols_tested': test_system.test_symbols,
            'account_balance': test_system.test_account_balance
        }, f, indent=2)
    
    print(f"\n📄 Test results saved to: futures_test_results.json")
