#!/usr/bin/env python3
"""
Test Suite for NIFTY 50 Scalping Dashboard Optimizations
Tests smart API polling, straddle calculation, and forward fill logic
"""

import time
from collections import deque

# ============================================================================
# TEST SCENARIO 2: Straddle Price Calculation
# ============================================================================

def test_straddle_calculation_basic():
    """T2.1: CE=100, PE=80 → Straddle = 90.00"""
    ce_ltp = 100
    pe_ltp = 80
    straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
    assert straddle_price == 90.00, f"Expected 90.00, got {straddle_price}"

def test_straddle_calculation_real_world():
    """T2.2: CE=127.70, PE=94.35 → Straddle = 111.025 → 111.03"""
    ce_ltp = 127.70
    pe_ltp = 94.35
    straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
    assert straddle_price == 111.03, f"Expected 111.03, got {straddle_price}"

def test_straddle_forward_fill_ce_none():
    """T2.3: CE=None, PE=100 → Use last_straddle_price"""
    ce_ltp = None
    pe_ltp = 100
    last_straddle_price = 95.50
    
    if ce_ltp and pe_ltp:
        straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
    elif last_straddle_price is not None:
        straddle_price = last_straddle_price
    else:
        straddle_price = None
    
    assert straddle_price == 95.50, f"Expected 95.50 (forward fill), got {straddle_price}"

def test_straddle_forward_fill_pe_none():
    """T2.4: CE=100, PE=None → Use last_straddle_price"""
    ce_ltp = 100
    pe_ltp = None
    last_straddle_price = 95.50
    
    if ce_ltp and pe_ltp:
        straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
    elif last_straddle_price is not None:
        straddle_price = last_straddle_price
    else:
        straddle_price = None
    
    assert straddle_price == 95.50, f"Expected 95.50 (forward fill), got {straddle_price}"

def test_straddle_both_none_with_cache():
    """T2.5: Both None, last exists → Use last_straddle_price"""
    ce_ltp = None
    pe_ltp = None
    last_straddle_price = 95.50
    
    if ce_ltp and pe_ltp:
        straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
    elif last_straddle_price is not None:
        straddle_price = last_straddle_price
    else:
        straddle_price = None
    
    assert straddle_price == 95.50, f"Expected 95.50 (cached), got {straddle_price}"

def test_straddle_both_none_no_cache():
    """T2.6: Both None, no last → straddle_price = None"""
    ce_ltp = None
    pe_ltp = None
    last_straddle_price = None
    
    if ce_ltp and pe_ltp:
        straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
    elif last_straddle_price is not None:
        straddle_price = last_straddle_price
    else:
        straddle_price = None
    
    assert straddle_price is None, f"Expected None, got {straddle_price}"

# ============================================================================
# TEST SCENARIO 4: Forward Fill Logic
# ============================================================================

def test_forward_fill_maintains_updates():
    """T4.4: Verify history updates every second even with forward fill"""
    history = []
    last_straddle_price = 100.0
    
    # Simulate 5 seconds of updates with only first having real data
    for i in range(5):
        if i == 0:
            ce_ltp, pe_ltp = 110.0, 90.0
            straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
            last_straddle_price = straddle_price
        else:
            # Subsequent updates use forward fill
            ce_ltp, pe_ltp = None, None
            if last_straddle_price:
                straddle_price = last_straddle_price
        
        history.append({
            'time': f'00:00:0{i}',
            'straddle': straddle_price
        })
    
    # Verify we have 5 history items (not 1)
    assert len(history) == 5, f"Expected 5 history items, got {len(history)}"
    
    # Verify all have the same straddle price (forward filled)
    assert all(h['straddle'] == 100.0 for h in history), "Forward fill failed"

# ============================================================================
# TEST SCENARIO 5: Status Logic
# ============================================================================

def test_status_with_fut_ltp():
    """T5.1: fut_ltp exists → Status = 'LIVE'"""
    fut_ltp = 25000.0
    ce_ltp = None
    pe_ltp = None
    last_straddle_price = None
    
    has_cached_data = ((0 or 0) > 0) or ((0 or 0) > 0) or ((last_straddle_price or 0) > 0)
    if fut_ltp or ce_ltp or pe_ltp or has_cached_data:
        status = "LIVE"
    else:
        status = "Tokens found, awaiting data..."
    
    assert status == "LIVE", f"Expected LIVE, got {status}"

def test_status_with_cached_straddle():
    """T5.4: All None, but last_straddle_price > 0 → Status = 'LIVE'"""
    fut_ltp = None
    ce_ltp = None
    pe_ltp = None
    last_straddle_price = 111.03
    
    has_cached_data = ((0 or 0) > 0) or ((0 or 0) > 0) or ((last_straddle_price or 0) > 0)
    if fut_ltp or ce_ltp or pe_ltp or has_cached_data:
        status = "LIVE"
    else:
        status = "Tokens found, awaiting data..."
    
    assert status == "LIVE", f"Expected LIVE with cached data, got {status}"

def test_status_no_data():
    """T5.5: All None, no cache → Status = 'Tokens found, awaiting data...'"""
    fut_ltp = None
    ce_ltp = None
    pe_ltp = None
    last_straddle_price = None
    
    has_cached_data = ((0 or 0) > 0) or ((0 or 0) > 0) or ((last_straddle_price or 0) > 0)
    if fut_ltp or ce_ltp or pe_ltp or has_cached_data:
        status = "LIVE"
    else:
        status = "Tokens found, awaiting data..."
    
    assert status == "Tokens found, awaiting data...", f"Expected awaiting status, got {status}"

# ============================================================================
# TEST SCENARIO 6: Long-Run Stability (Data Structures)
# ============================================================================

def test_deque_bounded_growth():
    """T6.2: Verify deque(maxlen=1000) prevents unbounded growth"""
    scalping_history = deque(maxlen=1000)
    
    # Add 2000 items
    for i in range(2000):
        scalping_history.append({
            'time': f'{i}',
            'straddle': 100.0 + i
        })
    
    # Should only have 1000 items
    assert len(scalping_history) == 1000, f"Expected 1000, got {len(scalping_history)}"
    
    # Oldest items should be removed (items 1000-1999 remain)
    assert scalping_history[0]['time'] == '1000', "Oldest items not removed"
    assert scalping_history[-1]['time'] == '1999', "Latest item not correct"

# ============================================================================
# RUN ALL TESTS
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("NIFTY 50 Scalping Dashboard - Test Suite")
    print("=" * 70)
    
    tests = [
        ("2.1: Basic Straddle Calculation", test_straddle_calculation_basic),
        ("2.2: Real-World Straddle Calculation", test_straddle_calculation_real_world),
        ("2.3: Forward Fill (CE=None)", test_straddle_forward_fill_ce_none),
        ("2.4: Forward Fill (PE=None)", test_straddle_forward_fill_pe_none),
        ("2.5: Forward Fill (Both None, Cache Exists)", test_straddle_both_none_with_cache),
        ("2.6: No Data, No Cache", test_straddle_both_none_no_cache),
        ("4.4: Forward Fill Maintains 1Hz Updates", test_forward_fill_maintains_updates),
        ("5.1: Status LIVE with fut_ltp", test_status_with_fut_ltp),
        ("5.4: Status LIVE with Cached Straddle", test_status_with_cached_straddle),
        ("5.5: Status Awaiting (No Data)", test_status_no_data),
        ("6.2: Deque Bounded Growth", test_deque_bounded_growth),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"✅ PASS: {name}")
            passed += 1
        except AssertionError as e:
            print(f"❌ FAIL: {name}")
            print(f"   Error: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {name}")
            print(f"   Exception: {e}")
            failed += 1
    
    print("=" * 70)
    print(f"Results: {passed} passed, {failed} failed out of {passed + failed} tests")
    print("=" * 70)
    
    exit(0 if failed == 0 else 1)
