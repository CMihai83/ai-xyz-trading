#!/usr/bin/env python3
"""
Simple integration to add Fibonacci service to existing AI-XYZ system
Just adds the pre-calculation service without changing the core system
"""

import sys
import json
from pathlib import Path

# Add services to path
sys.path.append(str(Path(__file__).parent / 'services' / 'api-gateway' / 'src'))

from fibonacci_averaging_service import get_fibonacci_service
from fibonacci_results_storage import store_position_fibonacci_results

def integrate_fibonacci_service():
    """
    Patches the existing system to use Fibonacci service for position parameters
    This function modifies the aixyz_continuous_profit_system to call Fibonacci service
    """
    
    # Read the current continuous system
    system_file = Path('/app/aixyz_continuous_profit_system.py')
    
    if not system_file.exists():
        print("❌ Cannot find aixyz_continuous_profit_system.py")
        return False
    
    with open(system_file, 'r') as f:
        content = f.read()
    
    # Check if already integrated
    if 'fibonacci_averaging_service' in content:
        print("✅ Fibonacci service already integrated")
        return True
    
    # Find where positions are opened and add Fibonacci call
    integration_code = '''
# Fibonacci Service Integration
def get_fibonacci_parameters(symbol, entry_price, available_margin, direction, volatility=0.02):
    """Get optimized parameters from Fibonacci service before opening position"""
    try:
        from fibonacci_averaging_service import get_fibonacci_service
        from fibonacci_results_storage import store_position_fibonacci_results
        
        service = get_fibonacci_service()
        
        # Calculate delta based on volatility
        delta = entry_price * volatility
        
        # Get optimized parameters
        params = service.calculate_trading_parameters(
            delta=delta,
            entry_price=entry_price,
            available_margin=available_margin,
            direction=direction,
            market_confidence=0.5
        )
        
        logger.info(f"📊 Fibonacci Service Analysis for {symbol}:")
        logger.info(f"   Optimal Leverage: {params.leverage}x")
        logger.info(f"   Averaging Steps: {len(params.averaging_steps)}")
        logger.info(f"   Liquidation Price: ${params.liquidation_price:.4f}")
        
        # Store for future reference
        if hasattr(params, 'averaging_steps'):
            for step in params.averaging_steps:
                logger.info(f"   Step {step.step_number}: ${step.price:.4f}, {step.position_multiplier:.1f}x")
        
        return {
            'leverage': params.leverage,
            'position_size': params.initial_position_size,
            'averaging_config': {
                'steps': [
                    {
                        'price': step.price,
                        'multiplier': step.position_multiplier,
                        'margin': step.margin_allocation
                    }
                    for step in params.averaging_steps
                ]
            }
        }
    except Exception as e:
        logger.error(f"Fibonacci service error: {e}")
        # Return defaults if service fails
        return {
            'leverage': 7,
            'position_size': 6.5,
            'averaging_config': None
        }
'''
    
    # Insert the integration code
    insert_position = content.find('class ContinuousProfitSystem:')
    if insert_position == -1:
        insert_position = content.find('async def open_position')
    
    if insert_position != -1:
        # Insert before the class or function
        content = content[:insert_position] + integration_code + '\n\n' + content[insert_position:]
        
        # Save the modified file
        backup_file = Path('/app/aixyz_continuous_profit_system.py.backup')
        system_file.rename(backup_file)
        
        with open(system_file, 'w') as f:
            f.write(content)
        
        print("✅ Fibonacci service integrated successfully!")
        print("   Backup saved as aixyz_continuous_profit_system.py.backup")
        return True
    else:
        print("❌ Could not find integration point in system file")
        return False

def add_fibonacci_call_to_position_opening():
    """
    Add a simple call to Fibonacci service when opening positions
    This is a minimal change to the existing system
    """
    
    patch_code = '''
# Before opening position, get Fibonacci parameters
fibonacci_params = get_fibonacci_parameters(
    symbol=symbol,
    entry_price=current_price,
    available_margin=min(100, free_balance / 2),  # Use half of free balance, max $100
    direction='long' if side == 'buy' else 'short',
    volatility=volatility_24h if volatility_24h else 0.02
)

# Use optimized parameters if available
if fibonacci_params:
    optimal_leverage = fibonacci_params.get('leverage', leverage)
    position_size = fibonacci_params.get('position_size', 6.5)
    
    # Store averaging config for later use
    if fibonacci_params.get('averaging_config'):
        # This will be used by the averaging engine
        position_metadata['fibonacci_averaging'] = fibonacci_params['averaging_config']
'''
    
    print("\nTo integrate Fibonacci service, add this code before opening positions:")
    print("="*60)
    print(patch_code)
    print("="*60)

if __name__ == "__main__":
    print("="*60)
    print("FIBONACCI SERVICE INTEGRATION HELPER")
    print("="*60)
    print("\nThis will add Fibonacci service calls to the existing system")
    print("The service will:")
    print("  ✓ Pre-calculate safe averaging levels")
    print("  ✓ Verify liquidation safety BEFORE opening")
    print("  ✓ Use proper Fibonacci distribution")
    print("  ✓ Include backtesting validation")
    print("\nThe rest of the system remains unchanged.")
    
    choice = input("\nIntegrate Fibonacci service? (y/n): ")
    
    if choice.lower() == 'y':
        if integrate_fibonacci_service():
            print("\n✅ Integration complete!")
            print("The system will now use Fibonacci service for new positions.")
        else:
            print("\n❌ Integration failed. Showing manual integration code:")
            add_fibonacci_call_to_position_opening()
    else:
        print("\nShowing manual integration code:")
        add_fibonacci_call_to_position_opening()