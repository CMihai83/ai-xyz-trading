#!/usr/bin/env python3
import json

with open('/app/bitget_symbols_info.json', 'r') as f:
    data = json.load(f)

# Check ASTER
if 'ASTER/USDT:USDT' in data['symbols']:
    aster = data['symbols']['ASTER/USDT:USDT']
    print('ASTER/USDT:USDT Requirements:')
    print('='*50)
    print(f'Amount precision: {aster["amount_precision"]} decimals')
    print(f'Min amount: {aster["min_amount"]} contracts')
    print(f'Min cost (notional): ${aster["min_cost"]}')
    print(f'Requires whole contracts: {aster["requires_whole_contracts"]}')
    print(f'Contract size: {aster["contract_size"]}')
    print(f'Max leverage: {aster["max_leverage"]}')
    print()
    print('ANALYSIS:')
    print('-'*50)
    if aster['requires_whole_contracts']:
        print('❌ ASTER requires WHOLE CONTRACTS (no decimals)')
        print('   This explains why 2.94 or 3.1 contracts would fail!')
        print('   The system tried to add ~3 contracts with decimals')
    else:
        print(f'✅ ASTER allows {aster["amount_precision"]} decimal places')

# Show more examples
print('\n\nOther symbols requiring whole contracts:')
count = 0
for symbol, info in data['symbols'].items():
    if info['requires_whole_contracts'] and count < 10:
        min_cost = info["min_cost"]
        min_amount = info["min_amount"]
        print(f'  {symbol}: min={min_amount}, min_cost=${min_cost}')
        count += 1

# Count totals
whole_count = sum(1 for s in data['symbols'].values() if s['requires_whole_contracts'])
total = len(data['symbols'])
print(f'\nTotal: {whole_count}/{total} symbols require whole contracts')