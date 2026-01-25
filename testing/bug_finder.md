# Bug Finder & Test Log

## Active Bugs
*(None currently active - previous ones fixed)*

## Resolved Bugs
1. **[Critical] Zero Velocity Signal Failure**
   - **Scenario**: `BUDGET_DAY`
   - **Symptom**: Signals stuck on "TRAP" / "WAIT". No "BUY" signals.
   - **Cause**: `last_price` variable in `test_server.py` loop was never updated, resulting in `0.00` calculated velocity.
   - **Fix**: Added `last_price = price` at end of loop.
   - **Status**: ✅ Fixed

2. **[Major] Unreachable Signal Thresholds**
   - **Scenario**: `BUDGET_DAY`
   - **Symptom**: Good visual trends but no signals.
   - **Cause**: Signal threshold `1.2` was higher than the physics engine's max drift `0.8`.
   - **Fix**: Lowered threshold to `0.4` and added PCR confirmation.
   - **Status**: ✅ Fixed

## Test Log: Trending Scenarios
### 1. Bull Run (Rising Trend)
- **Goal**: Verify "BUY CALL" signals during sustained rise.
- **Status**: ✅ **Passed**
- **Evidence**: Price +700pts, Signal "BUY CALL", PCR 1.31.

### 2. Bear Crash (Falling Trend)
- **Goal**: Verify "BUY PUT" signals during sustained drop.
- **Status**: ✅ **Passed**
- **Evidence**: Price -2700pts, Signal "BUY PUT", PCR 0.59.

### 3. Market Bias Logic Failure
- **Bug**: Basis remains Positive (Bullish) during Bear Crash.
- **Cause**: Basis was calculated as `50 * Multiplier`. High Volatility = High Positive Basis.
- **Fix**: Implemented "Greed/Fear" logic. Bear scenarios now contract basis to negative (Discount).
- **Status**: ✅ **Fixed**

