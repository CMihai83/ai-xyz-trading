#!/usr/bin/env python3
import ccxt
import os
from dotenv import load_dotenv

load_dotenv('/app/.env')

exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# Get market info for ASTER
markets = exchange.load_markets()
aster = markets.get('ASTER/USDT:USDT', {})

if aster:
    print('ASTER/USDT:USDT Market Requirements Analysis:')
    print('='*60)
    
    # Extract limits
    limits = aster.get('limits', {})
    amount_limits = limits.get('amount', {})
    cost_limits = limits.get('cost', {})
    
    min_amount = amount_limits.get('min', 'N/A')
    min_cost = cost_limits.get('min', 'N/A')
    contract_size = aster.get('contractSize', 1)
    
    print(f"Minimum contracts: {min_amount}")
    print(f"Minimum cost (USDT): {min_cost}")
    print(f"Contract size: {contract_size}")
    
    print()
    print('Current Position vs Requirements:')
    print('-'*60)
    print(f"Your position: 3 contracts × ~$2.10 = $6.30 notional")
    
    if min_cost != 'N/A' and min_cost:
        print(f"Required minimum: ${min_cost} USDT")
        if 6.30 >= min_cost:
            print("✅ Position MEETS minimum requirement")
        else:
            print("❌ Position BELOW minimum requirement")
    
    if min_amount != 'N/A' and min_amount:
        print(f"Minimum contracts required: {min_amount}")
        if 3 >= min_amount:
            print("✅ Contract count MEETS minimum")
        else:
            print("❌ Contract count BELOW minimum")
            print(f"   Need {min_amount - 3} more contracts")
    
    print()
    print('CONCLUSION:')
    print('-'*60)
    print("Based on Bitget's error 'less than the minimum amount 5 USDT':")
    print("The issue is likely that ASTER has specific minimums.")
    print("Even though $6.30 > $5, the pair might have higher requirements.")
else:
    print("ASTER/USDT:USDT not found in Bitget markets")