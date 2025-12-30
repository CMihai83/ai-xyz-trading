#!/usr/bin/env python3
"""
Scanner v4.0 Test Script
Tests all functionality before deploying to production
"""

import ccxt
import time
from scanner_v4 import ScannerV4
from opportunity_filters import OpportunityFilter
import os
from dotenv import load_dotenv

load_dotenv()

def test_opportunity_filter():
    """Test the multi-indicator opportunity filter"""
    print("\n" + "="*80)
    print("TEST 1: Opportunity Filter Module")
    print("="*80)

    import pandas as pd
    import numpy as np

    # Create sample data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='5T')
    sample_data = pd.DataFrame({
        'timestamp': dates,
        'open': np.linspace(100, 120, 100) + np.random.randn(100) * 0.5,
        'high': np.linspace(101, 121, 100) + np.random.randn(100) * 0.5,
        'low': np.linspace(99, 119, 100) + np.random.randn(100) * 0.5,
        'close': np.linspace(100, 120, 100) + np.random.randn(100) * 0.5,
        'volume': np.random.randn(100) * 1000 + 5000
    })

    # Add volume spike at end
    sample_data.loc[sample_data.index[-5:], 'volume'] = 15000

    filter_engine = OpportunityFilter()
    result = filter_engine.calculate_opportunity_score(sample_data)

    print(f"✅ Opportunity Score: {result['total_score']:.3f}")
    print(f"✅ Primary Indicator: {result['primary_indicator']}")
    print(f"✅ Direction: {result['direction']}")
    print(f"\n💡 Breakdown:")
    for indicator, data in result['breakdown'].items():
        print(f"   {indicator:20s}: Score={data['score']:.3f}, Signal={data.get('signal', 'N/A')}")

    return True


def test_scanner_initialization():
    """Test Scanner v4.0 initialization"""
    print("\n" + "="*80)
    print("TEST 2: Scanner v4.0 Initialization")
    print("="*80)

    try:
        exchange = ccxt.bitget({
            'apiKey': os.getenv('BITGET_API_KEY'),
            'secret': os.getenv('BITGET_SECRET'),
            'password': os.getenv('BITGET_PASSWORD'),
            'enableRateLimit': True,
            'options': {'defaultType': 'swap'}
        })

        scanner = ScannerV4(exchange=exchange)
        print("✅ Scanner v4.0 initialized successfully")
        print(f"✅ Timeframes: {scanner.timeframes}")
        print(f"✅ Cache TTLs configured: {len(scanner.cache)} cache types")

        return scanner

    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return None


def test_market_fetching(scanner):
    """Test fetching all USDT futures"""
    print("\n" + "="*80)
    print("TEST 3: Fetch All USDT Futures")
    print("="*80)

    try:
        all_markets = scanner._get_all_usdt_futures()
        print(f"✅ Found {len(all_markets)} USDT perpetual futures")

        # Display first 10
        print("\n📋 Sample markets:")
        for i, symbol in enumerate(all_markets[:10], 1):
            print(f"   {i}. {symbol}")

        return True

    except Exception as e:
        print(f"❌ Market fetching failed: {e}")
        return False


def test_quick_filter(scanner):
    """Test Stage 1 quick filter"""
    print("\n" + "="*80)
    print("TEST 4: Stage 1 Quick Filter")
    print("="*80)

    try:
        start_time = time.time()
        candidates = scanner._stage1_quick_filter()
        elapsed = time.time() - start_time

        print(f"✅ Quick filter completed in {elapsed:.1f}s")
        print(f"✅ Found {len(candidates)} candidates from {scanner.stats['total_markets']} total markets")
        print(f"✅ Filter rate: {(len(candidates)/scanner.stats['total_markets']*100):.1f}% passed")

        # Display top 10 candidates
        print("\n🏆 Top 10 Candidates:")
        for i, candidate in enumerate(candidates[:10], 1):
            print(f"   {i}. {candidate['symbol']:20s} - "
                  f"Score: {candidate['quick_score']:.3f}, "
                  f"Change: {candidate['price_change_24h']:+.2f}%, "
                  f"Vol: ${candidate['volume_usd_24h']:,.0f}, "
                  f"Type: {candidate['opportunity_type']}")

        return candidates

    except Exception as e:
        print(f"❌ Quick filter failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_deep_analysis(scanner, candidates):
    """Test Stage 2 deep analysis"""
    print("\n" + "="*80)
    print("TEST 5: Stage 2 Deep Analysis (Top 5 Candidates)")
    print("="*80)

    if not candidates:
        print("⚠️ No candidates for deep analysis")
        return []

    try:
        start_time = time.time()
        opportunities = scanner._stage2_deep_analysis(candidates[:5])
        elapsed = time.time() - start_time

        print(f"\n✅ Deep analysis completed in {elapsed:.1f}s")
        print(f"✅ Analyzed {min(5, len(candidates))} candidates")
        print(f"✅ Found {len(opportunities)} high-quality opportunities")

        # Display opportunities
        print("\n✨ Opportunities Found:")
        for i, opp in enumerate(opportunities, 1):
            print(f"\n   {i}. {opp['symbol']} - {opp['direction']}")
            print(f"      Final Score: {opp['final_score']:.3f}")
            print(f"      Primary Indicator: {opp['primary_indicator']}")
            print(f"      Breakdown:")
            print(f"         VSA: {opp['breakdown']['vsa']:.3f}")
            print(f"         ML Prediction: {opp['breakdown']['ml_prediction']:.3f}")
            print(f"         Opportunity Indicators: {opp['breakdown']['opportunity_indicators']:.3f}")
            print(f"         Sharpe: {opp['breakdown']['sharpe']:.3f}")
            print(f"         Sortino: {opp['breakdown']['sortino']:.3f}")
            print(f"         MTF Confirmation: {opp['breakdown']['mtf_confirmation']:.3f}")

        return opportunities

    except Exception as e:
        print(f"❌ Deep analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return []


def test_full_scan(scanner):
    """Test complete scan cycle"""
    print("\n" + "="*80)
    print("TEST 6: Full Scan Cycle (ALL Markets)")
    print("="*80)

    try:
        start_time = time.time()
        opportunities = scanner.scan_market(max_deep_analysis=10)
        elapsed = time.time() - start_time

        print(f"\n🎉 FULL SCAN COMPLETE!")
        print(f"⏱️  Total Time: {elapsed:.1f}s")
        print(f"📊 Statistics:")
        print(f"   Total Markets: {scanner.stats['total_markets']}")
        print(f"   Stage 1 Filtered: {scanner.stats['stage1_filtered']}")
        print(f"   Stage 2 Analyzed: {scanner.stats['stage2_analyzed']}")
        print(f"   Opportunities Found: {scanner.stats['opportunities_found']}")
        print(f"   API Calls: {scanner.stats['api_calls']}")

        print(f"\n🏆 TOP 5 OPPORTUNITIES:")
        for i, opp in enumerate(opportunities[:5], 1):
            print(f"\n   {i}. {opp['symbol']} - {opp['direction']}")
            print(f"      Score: {opp['final_score']:.3f}")
            print(f"      Price: ${opp['current_price']:.4f}")
            print(f"      Volume 24h: ${opp['volume_24h']:,.0f}")
            print(f"      Change 24h: {opp['price_change_24h']:+.2f}%")

        # Performance check
        if elapsed < 60:
            print(f"\n✅ PERFORMANCE: Excellent! ({elapsed:.1f}s < 60s target)")
        elif elapsed < 90:
            print(f"\n⚠️ PERFORMANCE: Acceptable ({elapsed:.1f}s, target < 60s)")
        else:
            print(f"\n❌ PERFORMANCE: Needs optimization ({elapsed:.1f}s > 90s)")

        return True

    except Exception as e:
        print(f"❌ Full scan failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_compatibility():
    """Test compatibility with main trading system interface"""
    print("\n" + "="*80)
    print("TEST 7: Trading System Compatibility")
    print("="*80)

    try:
        scanner = ScannerV4()

        # Test scan_for_opportunities() method (used by main system)
        opportunities = scanner.scan_for_opportunities()

        print(f"✅ scan_for_opportunities() returned {len(opportunities)} opportunities")

        # Verify format
        if opportunities:
            opp = opportunities[0]
            required_fields = ['symbol', 'direction', 'signal_quality', 'primary_factor', 'current_price']

            all_present = all(field in opp for field in required_fields)

            if all_present:
                print("✅ Output format compatible with trading system")
                print(f"\n   Sample output:")
                for field in required_fields:
                    print(f"      {field}: {opp[field]}")
            else:
                missing = [field for field in required_fields if field not in opp]
                print(f"❌ Missing fields: {missing}")
                return False

        return True

    except Exception as e:
        print(f"❌ Compatibility test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests"""
    print("\n" + "="*100)
    print(" "*35 + "SCANNER V4.0 TEST SUITE")
    print("="*100)

    results = {}

    # Test 1: Opportunity Filter
    results['filter'] = test_opportunity_filter()

    # Test 2: Scanner Initialization
    scanner = test_scanner_initialization()
    if not scanner:
        print("\n❌ CRITICAL: Scanner initialization failed. Cannot proceed.")
        return

    # Test 3: Market Fetching
    results['markets'] = test_market_fetching(scanner)

    # Test 4: Quick Filter
    candidates = test_quick_filter(scanner)
    results['quick_filter'] = len(candidates) > 0

    # Test 5: Deep Analysis
    opportunities = test_deep_analysis(scanner, candidates)
    results['deep_analysis'] = len(opportunities) > 0

    # Test 6: Full Scan
    results['full_scan'] = test_full_scan(scanner)

    # Test 7: Compatibility
    results['compatibility'] = test_compatibility()

    # Summary
    print("\n" + "="*100)
    print(" "*40 + "TEST SUMMARY")
    print("="*100)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name:20s}: {status}")

    print(f"\n{'='*100}")
    print(f"   OVERALL: {passed}/{total} tests passed ({passed/total*100:.0f}%)")
    print(f"{'='*100}")

    if passed == total:
        print("\n🎉 ALL TESTS PASSED! Scanner v4.0 is ready for production.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review errors above.")


if __name__ == "__main__":
    main()
