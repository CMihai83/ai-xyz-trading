#!/usr/bin/env python3
"""Check surplus dump status on all live positions"""

import ccxt
import json
from datetime import datetime

# Initialize exchange
exchange = ccxt.bitget({
    'apiKey': 'bg_f483546274ffb2bfa567328e98dba6c0',
    'secret': '387cd492982a12f906a040a984d0fb3396277750f778543e869790ce4fcb2bb0',
    'password': '2609Luiza',
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap',
        'defaultMarginMode': 'isolated'
    }
})

def check_surplus_eligibility(position):
    """Check if position is eligible for surplus dump"""
    upnl = position.get('unrealizedPnl', 0)
    pct = position.get('percentage', 0)
    
    # Surplus dump rules:
    # 1. UPNL must be > $0.15
    # 2. Position must have averaging history (simulated here)
    # 3. Track peak UPNL for dump thresholds
    
    result = {
        'symbol': position['symbol'],
        'side': position['side'],
        'contracts': position['contracts'],
        'entry_price': position.get('entryPrice', 0),
        'current_price': position.get('markPrice', 0),
        'upnl': upnl,
        'percentage': pct,
        'eligible': False,
        'reason': '',
        'dump_actions': []
    }
    
    # Check if in profit zone
    if upnl > 0.15:
        result['eligible'] = True
        result['reason'] = 'UPNL > $0.15 - IN SURPLUS DUMP ZONE'
        
        # Calculate dump thresholds (assuming this is peak for now)
        peak_upnl = upnl  # In real system, would track historical peak
        
        # First dump at 85% of peak
        threshold_85 = peak_upnl * 0.85
        # Second dump at 50% of peak  
        threshold_50 = peak_upnl * 0.50
        
        result['dump_actions'].append({
            'trigger': 'When UPNL drops to 85% of peak',
            'threshold': f'${threshold_85:.4f}',
            'action': 'Dump 50% of position',
            'size_to_dump': position['contracts'] * 0.5
        })
        
        result['dump_actions'].append({
            'trigger': 'When UPNL drops to 50% of peak',
            'threshold': f'${threshold_50:.4f}',
            'action': 'Dump remaining 50%',
            'size_to_dump': position['contracts'] * 0.5
        })
        
        # Check if we should execute now
        # For testing, assume we have averaging history
        result['averaging_history'] = 'Assumed 2 averaging steps (for testing)'
        result['peak_upnl'] = peak_upnl
        result['current_vs_peak'] = f'{(upnl/peak_upnl)*100:.1f}%'
        
    elif upnl > 0:
        result['reason'] = f'UPNL ${upnl:.4f} - Need ${0.15 - upnl:.4f} more profit for surplus zone'
    else:
        result['reason'] = f'UPNL ${upnl:.4f} - Position is negative, need ${0.15 - upnl:.4f} profit'
    
    return result

def execute_surplus_dump(position, dump_percentage):
    """Execute a surplus dump on a position"""
    try:
        symbol = position['symbol']
        contracts = position['contracts']
        side = position['side']
        
        # Calculate dump size
        dump_size = contracts * dump_percentage
        
        # Determine close side
        close_side = 'sell' if side == 'long' else 'buy'
        
        print(f"\n🔄 Executing surplus dump...")
        print(f"  Symbol: {symbol}")
        print(f"  Dumping: {dump_size:.4f} contracts ({dump_percentage*100:.0f}%)")
        
        # Execute partial close
        order = exchange.create_order(
            symbol=symbol,
            type='market',
            side=close_side,
            amount=dump_size,
            params={'reduceOnly': True}
        )
        
        print(f"  ✅ Surplus dump executed!")
        print(f"  Order ID: {order['id']}")
        
        return {
            'success': True,
            'order_id': order['id'],
            'size_dumped': dump_size,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"  ❌ Surplus dump failed: {e}")
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

def main():
    print("="*70)
    print("SURPLUS DUMP CHECK ON LIVE POSITIONS")
    print("="*70)
    print(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Get all positions
    positions = exchange.fetch_positions()
    active_positions = [p for p in positions if p['contracts'] > 0]
    
    print(f"\n📊 Found {len(active_positions)} active positions")
    
    surplus_report = {
        'timestamp': datetime.now().isoformat(),
        'positions_checked': len(active_positions),
        'eligible_for_surplus': 0,
        'positions': []
    }
    
    for i, pos in enumerate(active_positions, 1):
        print(f"\n{'='*50}")
        print(f"Position #{i}: {pos['symbol']}")
        
        # Check surplus eligibility
        result = check_surplus_eligibility(pos)
        surplus_report['positions'].append(result)
        
        # Display results
        print(f"  Side: {result['side'].upper()}")
        print(f"  Size: {result['contracts']} contracts")
        print(f"  Entry: {result['entry_price']:.5f}")
        print(f"  Current: {result['current_price']:.5f}")
        print(f"  UPNL: ${result['upnl']:.4f} ({result['percentage']:.2f}%)")
        
        if result['eligible']:
            surplus_report['eligible_for_surplus'] += 1
            print(f"\n  🟢 ELIGIBLE FOR SURPLUS DUMP!")
            print(f"  Reason: {result['reason']}")
            print(f"  Peak UPNL: ${result['peak_upnl']:.4f}")
            print(f"  Current vs Peak: {result['current_vs_peak']}")
            
            print(f"\n  📋 Dump Actions:")
            for action in result['dump_actions']:
                print(f"    • {action['trigger']}")
                print(f"      Threshold: {action['threshold']}")
                print(f"      Action: {action['action']}")
                print(f"      Size: {action['size_to_dump']:.4f} contracts")
            
            # Ask if should execute
            if result['upnl'] >= result['peak_upnl'] * 0.85:
                print(f"\n  ⚠️ READY FOR IMMEDIATE DUMP (at 85% of peak)")
                print(f"  Would dump: {result['contracts'] * 0.5:.4f} contracts")
                
                # Auto-execute for testing (comment out for manual control)
                # dump_result = execute_surplus_dump(pos, 0.5)
                # if dump_result['success']:
                #     surplus_report['positions'][-1]['dump_executed'] = dump_result
        else:
            print(f"\n  🟡 NOT ELIGIBLE for surplus dump")
            print(f"  Reason: {result['reason']}")
    
    # Summary
    print(f"\n{'='*70}")
    print("SURPLUS DUMP SUMMARY")
    print(f"  Total Positions: {len(active_positions)}")
    print(f"  Eligible for Surplus: {surplus_report['eligible_for_surplus']}")
    
    if surplus_report['eligible_for_surplus'] > 0:
        print(f"\n✅ {surplus_report['eligible_for_surplus']} position(s) ready for surplus dump!")
        print("  Execute dumps when UPNL drops to threshold levels")
    else:
        print(f"\n⚠️ No positions currently eligible for surplus dump")
        print("  All positions need UPNL > $0.15 to enter surplus zone")
    
    # Check zone distribution
    neutral_count = sum(1 for p in active_positions if -0.15 < p.get('unrealizedPnl', 0) <= 0.15)
    averaging_count = sum(1 for p in active_positions if p.get('unrealizedPnl', 0) <= -0.15)
    surplus_count = sum(1 for p in active_positions if p.get('unrealizedPnl', 0) > 0.15)
    
    print(f"\nZone Distribution:")
    print(f"  🔴 Averaging Zone (UPNL ≤ -$0.15): {averaging_count}")
    print(f"  🟡 Neutral Zone (-$0.15 < UPNL ≤ $0.15): {neutral_count}")
    print(f"  🟢 Surplus Zone (UPNL > $0.15): {surplus_count}")
    
    # Balance check
    balance = exchange.fetch_balance()
    usdt = balance.get('USDT', {})
    print(f"\n💰 Account Balance: ${usdt.get('total', 0):.2f} USDT")
    print(f"   Free: ${usdt.get('free', 0):.2f}")
    print(f"   Used: ${usdt.get('used', 0):.2f}")
    
    # Save report
    with open('surplus_check_report.json', 'w') as f:
        json.dump(surplus_report, f, indent=2)
    
    print(f"\n📄 Report saved to: surplus_check_report.json")
    print("="*70)

if __name__ == "__main__":
    main()