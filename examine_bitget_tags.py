#!/usr/bin/env python3
"""
Examine the tag field in Bitget responses to find superpair identification
"""

import ccxt
import json
import os
from dotenv import load_dotenv

load_dotenv()

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': os.getenv('BITGET_API_KEY'),
    'secret': os.getenv('BITGET_API_SECRET'),
    'password': os.getenv('BITGET_API_PASSPHRASE'),
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

# Load markets
markets = exchange.load_markets()

print("=" * 70)
print("EXAMINING BITGET MARKETS FOR SUPERPAIR IDENTIFICATION")
print("=" * 70)

# Track symbols with different characteristics
superpair_candidates = []
symbol_analysis = {}

# Analyze all futures markets
for symbol, market in markets.items():
    if market['type'] != 'swap' or market['quote'] != 'USDT':
        continue
    
    info = market.get('info', {})
    
    # Check all text fields for SP or super indicators
    symbol_str = json.dumps(info).upper()
    
    has_sp_indicator = False
    sp_location = []
    
    # Check if SP appears in the symbol name itself
    symbol_name = info.get('symbol', '')
    if 'SP' in symbol_name.upper():
        has_sp_indicator = True
        sp_location.append(f"symbol name: {symbol_name}")
    
    # Check all string fields
    for key, value in info.items():
        if isinstance(value, str):
            if 'SP' in value.upper() and key != 'symbol':
                has_sp_indicator = True
                sp_location.append(f"{key}: {value}")
    
    # Store analysis
    analysis = {
        'symbol': symbol,
        'symbol_name': symbol_name,
        'max_leverage': float(info.get('maxLever', 0)),
        'maker_fee': float(info.get('makerFeeRate', 1)),
        'max_positions': int(info.get('maxPositionNum', 0)),
        'has_sp': has_sp_indicator,
        'sp_locations': sp_location
    }
    
    symbol_analysis[symbol] = analysis
    
    # Check if this is a high-tier symbol (potential superpair)
    if (analysis['max_leverage'] >= 100 and 
        analysis['maker_fee'] <= 0.0002 and 
        analysis['max_positions'] >= 150):
        superpair_candidates.append(analysis)

# Print findings
print("\n1. SYMBOLS WITH 'SP' INDICATOR:")
print("-" * 50)
sp_symbols = [s for s in symbol_analysis.values() if s['has_sp']]
if sp_symbols:
    for sym in sp_symbols[:10]:
        print(f"  {sym['symbol']}: {sym['sp_locations']}")
else:
    print("  No symbols found with explicit 'SP' indicator")

print("\n2. HIGH-TIER SYMBOLS (Leverage >= 100x, Fee <= 0.02%, Positions >= 150):")
print("-" * 50)
if superpair_candidates:
    for sym in superpair_candidates[:20]:
        print(f"  {sym['symbol_name']}: Leverage={sym['max_leverage']}x, Fee={sym['maker_fee']*100:.3f}%, Positions={sym['max_positions']}")
else:
    print("  No high-tier symbols found")

# Now let's check if there's a pattern in symbol naming
print("\n3. CHECKING SYMBOL NAMING PATTERNS:")
print("-" * 50)

# Group symbols by base currency
base_groups = {}
for symbol, analysis in symbol_analysis.items():
    market = markets.get(symbol, {})
    base = market.get('base', 'UNKNOWN')
    if base not in base_groups:
        base_groups[base] = []
    base_groups[base].append(analysis)

# Check if certain bases are consistently high-tier
consistent_superpairs = []
for base, symbols in base_groups.items():
    if symbols:
        # Check if all symbols of this base are high-tier
        all_high_tier = all(
            s['max_leverage'] >= 100 and 
            s['maker_fee'] <= 0.0002 and 
            s['max_positions'] >= 150 
            for s in symbols
        )
        
        if all_high_tier and len(symbols) > 0:
            consistent_superpairs.append(base)

if consistent_superpairs:
    print(f"  Bases that are consistently superpairs: {', '.join(consistent_superpairs[:20])}")
else:
    print("  No consistent pattern found")

# Final determination
print("\n" + "=" * 70)
print("CONCLUSION:")
print("=" * 70)

if sp_symbols:
    print("✅ Found symbols with 'SP' indicator - these are likely superpairs")
    print(f"   Total: {len(sp_symbols)} symbols")
elif superpair_candidates:
    print("✅ Bitget superpairs are identified by premium characteristics:")
    print(f"   - High Leverage (>= 100x)")
    print(f"   - Low Fees (<= 0.02%)")
    print(f"   - High Position Limits (>= 150)")
    print(f"   Total identified: {len(superpair_candidates)} superpairs")
    
    # Save the list
    with open('/app/bitget_superpairs.json', 'w') as f:
        json.dump([s['symbol_name'] for s in superpair_candidates], f, indent=2)
    print("\n   Superpair list saved to bitget_superpairs.json")
else:
    print("❌ No clear superpair identification method found")