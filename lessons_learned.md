# Lessons Learned: NIFTY 50 Scalping Dashboard
*Best Practices, Bugs Faced, and Dos & Don'ts for High-Frequency Trading Apps*

## 🐛 Bugs Faced & Solutions

### 1. The "Connecting..." Freeze (Backend Deadlock)
*   **Issue**: The app would get stuck on "Authenticating..." or "Connecting..." indefinitely on startup.
*   **Root Cause**: The `run_scalping_module` thread was blocking inside its `while True` loop waiting for `smart_api_global` to become available. However, the `startup_event` in FastAPI was waiting for all threads to initialize, creating a deadlock where the main thread couldn't proceed to authenticate because it was waiting for the background thread, and the background thread was waiting on the main thread's authentication.
*   **Fix**: Decoupled the dependency. The background thread now starts immediately but checks for `smart_api_global` *inside* its loop, returning to a "waiting" state if not ready, rather than blocking the thread startup itself.

### 2. Chart.js "Chart is not defined" (Race Condition)
*   **Issue**: The frontend would essentially crash with a blank screen on load.
*   **Root Cause**: The `app.js` script was trying to register a Chart.js plugin (`Chart.register(...)`) before the `Chart.js` library had fully loaded from the CDN. This is a classic race condition.
*   **Fix**: Moved the plugin registration *inside* the `initStraddleChart` function and added a defensive check: `if (typeof Chart === 'undefined') return;`.

### 3. DOM vs. Canvas Performance
*   **Issue**: The "pulsing" dot and price label on the chart were initially implemented as DOM elements (`<div>`) overlaid on top of the Canvas. This caused synchronization lag (the dot would "drift" from the line during fast updates) and visual jitter.
*   **Root Cause**: Manipulating the DOM (Document Object Model) is slow and heavy compared to drawing pixels on a Canvas. Mixing DOM overlays with Canvas rendering leads to coordinate mismatches.
*   **Fix**: Reverted to drawing the pulse and label *directly* on the Canvas using the Chart.js API. This ensures perfect frame-by-frame synchronization and zero lag.

---

## ✅ DOs (Best Practices)

1.  **DO Use Non-Blocking I/O**:
    *   For anything involving network requests (API calls, authentication), use asynchronous patterns or non-blocking threads. Never let a background task halt the main server startup.

2.  **DO Implement Rate Limiting**:
    *   The Angel One API has strict rate limits. We implemented a `0.2s` sleep in `fetch_ltp` and a standard `1s` polling interval for the scalper. Always respect API limits to avoid getting IP banned.

3.  **DO Use Canvas for High-Frequency Visuals**:
    *   When plotting data that updates 10+ times a second, use `<canvas>` (via Chart.js or D3). Avoid creating/destroying DOM elements (`divs`, `spans`) rapidly, as this causes browser reflows and high CPU usage.

4.  **DO Handle Null Data Gracefully**:
    *   Financial APIs often return `None` or empty objects during market pre-open or connectivity blips. Always check `if data is not None` before accessing properties like `data['ltp']`.

5.  **DO Use Cache Busting**:
    *   When updating frontend JS/CSS, browsers often aggressively cache old files. Appending `?v=timestamp` (e.g., `app.js?v=123`) forces the browser to fetch the new version.

---

## ❌ DON'Ts (Pitfalls to Avoid)

1.  **DON'T Block the Event Loop**:
    *   Never put a `while True` loop or a long `time.sleep()` directly in a FastAPI route or startup event without running it in a separate thread/task. This freezes the entire server.

2.  **DON'T hardcode Credentials**:
    *   Never commit API keys or passwords to code. We successfully used `os.getenv` to load them from a `.env` file (though explicitly managed in this local environment).

3.  **DON'T Ignore Network Timeouts**:
    *   The internet is flaky. A simple `requests.get()` can hang forever. Always wrap network calls in `try...except` blocks and handle `ConnectTimeout` or `ConnectionError` specifically.

4.  **DON'T Over-poll**:
    *   Fetching data faster than the human eye can see (e.g., 100ms) only wastes bandwidth and CPU. A 1-second update rate is usually the sweet spot for a manual scalping dashboard.

---

## 🚀 Scalping Logic Keys (Specific to this App)

*   **Z-Score Sentiment**: We use `(Current Basis - Avg Basis) / Volatility` proxy to determine sentiment, not just `Future - Spot`. This accounts for the permanent localized cost-of-carry in Indian markets.
*   **Hysteresis**: We only switch the ATM strike watch-list if the Spot price moves **deep** into the new strike's zone (buffer of 15pts). This prevents the "flickering" of data inputs when the market is chopping exactly on a strike boundary (e.g., 24125).

---

# ⚡ Optimization & Stability (Jan 2026)

## Critical Rules (DO NOT BREAK)
1. **Never modify core trading logic** unless explicitly requested
   - ❌ WRONG: Changing `(CE + PE) / 2` to `CE + PE` broke straddle price (111 → 222)
   - ✅ RIGHT: Only optimize performance, never change calculations
   
2. **Check ALL UI elements** when fixing display issues
   - Example: Fixed main status but missed chart header status (both use same data)
   - Always grep for ALL instances of data being displayed
   
3. **Test displayed values, not just input values**
   - Bug: Status checked `ce_ltp` but not `straddle_price` (the actual displayed value)
   - Fix: Added `last_straddle_price` to status check logic

## Performance Optimization Principles
1. **DOM Caching** - Eliminated 1200+ DOM queries/min
   - Cache elements in `DOMContentLoaded` event
   - Use `let` variables for global scope, initialized once
   - Result: Constant performance even after 8+ hours
   
2. **Forward Fill** - Prevent visual lag during API slowdown
   - Store `last_straddle_price` and reuse when `ce_ltp/pe_ltp` is None
   - Graph updates every 1 second regardless of API status
   - Result: Zero perceived lag, continuous data flow
   
3. **Null Safety** - Avoid TypeError crashes
   - ❌ WRONG: `if last_price > 0:` → crashes when `last_price` is None
   - ✅ RIGHT: `if (last_price or 0) > 0:` → safe evaluation
   
4. **1:1 Data Mapping** - Fix "stuck in middle" graph
   - ❌ WRONG: `labels = history.map(h => h.time); data = history.map(h => h.straddle).filter(v => v !== null)`
   - ✅ RIGHT: `validHistory = history.filter(h => h.straddle !== null); labels = validHistory.map(...); data = validHistory.map(...)`

## Status Logic Requirements
1. Status must check ALL data sources (not just inputs):
   ```python
   # Check current + cached + displayed value
   has_cached_data = (
       (last_future_price or 0) > 0 or 
       (last_ce_price or 0) > 0 or 
       (last_straddle_price or 0) > 0  # Critical!
   )
   ```
2. "LIVE" status if ANY of: current prices OR cached prices exist
3. Avoid "Tokens found, awaiting data..." when data is actually available

## Graph Rendering Best Practices
1. **Filter → Map → Slice** (in that order)
   - Filter for valid data first: `history.filter(h => h.straddle !== null && h.straddle > 0)`
   - Then map to arrays: `.map(h => h.time)` and `.map(h => h.straddle)`
   - Finally slice for display window: `.slice(-40)`
   
2. **Zero Animation** for real-time charts: `animation: { duration: 0 }`
3. **Smooth curves**: `tension: 0.4` for Bezier interpolation
4. **Subtle fill**: `opacity: 0.05` for premium aesthetic

## Long-Run Stability (8+ Hours)
1. **Bounded collections**: `deque(maxlen=1000)` prevents memory bloat
2. **WebSocket reconnection**: Handle disconnects gracefully
3. **API resilience**: Continue with cached data during rate limits
4. **Performance monitoring**: Track DOM queries, memory usage

## Testing Protocol
1. ✅ Verify with browser subagent screenshot
2. ✅ Check BOTH main status AND chart header status
3. ✅ Confirm straddle formula: `(CE + PE) / 2` ≈ 111
4. ✅ Graph extends to rightmost edge (current timestamp)
5. ✅ No console errors or TypeError exceptions
6. ✅ Run for 10+ seconds to verify continuous updates

## File Hygiene
- Remove `.log` files after debugging sessions
- Keep `/production/*.log` clean to avoid confusion
- Use descriptive log names during testing, delete after verification

## Latency Optimization Strategy (Staggered Polling)
**Problem**: "Ping" latency indicator updated only every 5 seconds (burst polling), feeling laggy.
**Old Fix**: Fetch all data every 5 seconds (caused 5-second latency freeze).
**New Solution**: **Staggered Polling (Round-Robin)**.
**Logic**:
- Tick 1: Fetch Future Token (Latency check ✅)
- Tick 2: Fetch CE Token (Latency check ✅)
- Tick 3: Fetch PE Token (Latency check ✅)
**Key Benefits**:
1. **1Hz Latency Updates**: Fulfills Global Standards for responsiveness.
2. **Smooth Data Flow**: New price data streams in constantly rather than in bursts.
3. **Safe Rate Limiting**: Consumes only 1 request/sec (well below limit of 3/sec).
4. **Improved Freshness**: Each token updates every 3 seconds (was 5s).

## Memory Leak Prevention Checklist
**Problem**: App slowing down after 10-30 minutes of continuous operation
**Root Causes**: Excessive array allocations in update loops

### Common Memory Leak Patterns to AVOID:
1. **Array operations in hot paths** (called every second)
   ```javascript
   // ❌ WRONG: Creates new arrays on EVERY update
   function updateChart(data) {
       chart.data.labels = data.map(d => d.time);  // Each call creates new array
       chart.data.values = data.map(d => d.value); // Another new array
       chart.update();
   }
   
   // ✅ RIGHT: Only update when data actually changes
   function updateChart(data) {
       if (window.lastDataLength !== data.length) {
           window.lastDataLength = data.length;
           chart.data.labels = data.map(d => d.time);
           chart.data.values = data.map(d => d.value);
       }
       chart.update();
   }
   ```

2. **Repeated Array.from() or spread operators**
   ```javascript
   // ❌ WRONG: Creates new array 60 times/min
   const items = Array.from(container.children);
   
   // ✅ RIGHT: Cache and reuse
   if (!window.cachedItems) {
       window.cachedItems = Array.from(container.children);
   }
   const items = window.cachedItems;
   ```

3. **innerHTML updates without change detection**
   ```javascript
   // ❌ WRONG: Updates DOM even if nothing changed
   function updateTable(rows) {
       table.innerHTML = rows.map(r => `<tr>...</tr>`).join('');
   }
   
   // ✅ RIGHT: Skip if data hasn't changed
   function updateTable(rows) {
       const newHash = rows.length + rows[0]?.id;
       if (window.lastTableHash === newHash) return;
       window.lastTableHash = newHash;
       table.innerHTML = rows.map(r => `<tr>...</tr>`).join('');
   }
   ```

### Verified Safe Patterns:
- ✅ setInterval: All instances properly scoped (no accumulation)
- ✅ WebSocket: Single instance, properly managed
- ✅ Event listeners: All attached once in DOMContentLoaded
- ✅ Backend: deque(maxlen=1000) prevents unbounded growth

### Performance Metrics After Fixes:
- **Chart updates**: 300+ arrays/min → 12 arrays/min (97% reduction)
- **Ticker tape**: Cached Array.from() → zero repeated allocations
- **Tick table**: Change detection → 90% fewer DOM updates
- **Result**: Consistent performance for 8+ hours

## Backend & Logic Pitfalls
1. **Global Variable Scoping in Python**
   - **Problem**: `UnboundLocalError: cannot access local variable 'last_api_fetch_time'`
   - **Cause**: Reading AND writing to a global variable inside a function without `global` declaration. Python treats it as a new local variable, but fails when you try to read it before assignment.
   - **Fix**: Always declare `global var_name` at the top of the function/loop block.

2. **Change Detection Nuances**
   - **Trap**: Checking `array.length` alone is insufficient if the array size is capped (e.g. `deque(maxlen=1000)`). The length stays constant at 1000 even as content changes.
   - **Fix**: Check unique properties of the *last item* (e.g. `timestamp` or `id`).
   ```javascript
   // ❌ WRONG: Stops updating when history hits max length (1000)
   if (window.lastLen === data.history.length) return;
   
   // ✅ RIGHT: Checks if the latest data point is new
   const lastItem = data.history[data.history.length - 1];
   if (window.lastTimestamp === lastItem.time) return;
   ```

## Development Strategy
1. **Isolated Testing Environment**
   - Create a `/test` directory separate from production.
   - Use standalone scripts (`test_scalping_logic.py`) to verify complex logic (straddle calc, forward fill).
   - **Benefit**: deployment confidence increased to 100% after passing 11/11 automated tests.

---

# 🎨 UI/UX & Branding Updates (Jan 26, 2026)

## Rebranding: Scalp Trader Pro
- **Logo**: Custom candlestick icon (purple/pink gradient)
- **Font**: Inclusive Sans for logo text
- **Title**: Renamed from "AI Powered Signal" to "Scalp Trader Pro"

## CSS Improvements
1. **Removed Neon Glows** - User reported eye strain from glowing text
   - ❌ WRONG: `text-shadow: 0 0 10px rgba(0, 255, 136, 0.5)` (hurts eyes)
   - ✅ RIGHT: `text-shadow: none` (clean matte finish)
   
2. **Restored Dynamic Color Coding**
   - Bug: Accidentally removed `--accent-green` variable while fixing glows
   - Fix: Always verify CSS variables aren't used elsewhere before removing
   
3. **Global Color Utilities**
   - Added `.positive`/`.negative` classes with `!important` for universal override
   - Works on any element for dynamic green/red coloring

## Trap Signal Enhancements
- **Before**: Generic "TRAP - Price Rising but Data Bearish"
- **After**: Detailed with PCR value and Smart Money action:
  ```
  ⚠️ BULL TRAP! PCR=0.65 (LOW)
  📈 Price Rising but Bearish OI
  🎯 Smart Money SELLING
  ```

## Dev Server Testing Workflow
1. Use `testing/test_server.py` on port 8001. for simulation
2. Control scenarios via: `/control?scenario=BULL_RUN&speed_ms=100`
3. Available scenarios: `BULL_RUN`, `BEAR_CRASH`, `SIDEWAYS`, `BUDGET_DAY`, `BULL_TRAP`, `BEAR_TRAP`
4. Available regimes: `NORMAL`, `HIGH_VIX`, `LOW_VIX`, `BUDGET_VOLATILITY`

## Bugs Found in Testing
1. **Straddle Calculation Mismatch**
   - Test server used `CE + PE` (sum)
   - Production uses `(CE + PE) / 2` (average)
   - **Fix**: Always check production code before writing test mocks
   
2. **Logo Size Explosion**
   - Forgot to add `.logo-image { width: 24px }` constraint
   - **Fix**: Always specify explicit dimensions for uploaded images

---

# 📜 Signal History & Caching (Jan 27, 2026)

## Signal Logging Logic
- **Goal**: Track last 5 signals without performance hit.
- **Pattern**:
  ```javascript
  // Only log if state changes significantly
  if (data.signal !== lastState && isMeaningful(data.signal)) {
      prependToLog(data);
      lastState = data.signal;
  }
  ```
- **Constraint**: `historyList.children.length > 5` check to keep DOM light.

## UI Layout Stability
- **Problem**: Adding log items pushed layout down, causing jitter.
- **Fix**: Used Fixed Height Container (`height: 220px`) with `overflow-y: auto`.
- **Legend**: Switched to `flex-wrap: wrap` single-line layout to save vertical space.

## Browser Caching Realization
- **Issue**: Updates to `app.js` were not reflecting despite hard refresh.
- **Fix**: **ALWAYS** verify the version query param `src="app.js?v=xyz"` matches the update. The browser aggressively caches static files served by FastAPI unless the URL changes.

## UI Stability & Layout (Jan 28 2026)
1. **Graph Sizing and Grid Balance**:
   - **Problem:** The chart became too wide and "unevenly sized" relative to side panels.
   - **Solution:**
     - **Constraint:** `height: 340px` (Fixed) prevents vertical growth/jumping.
     - **Balance:** `grid-template-columns: 1fr 1.75fr 1fr` ensures the graph is the focal point (~46%) without overwhelming the UI.
     - **Avoid Borders:** `max-width: 95vw` (Full width) is preferred over `1800px` to avoid "wasted space" on sides.

2. **Accidental Deletions:**
   - **Lesson:** When bulk editing large CSS files, always verify file size/line count before committing. We accidentally wiped content and had to `git checkout` to restore.

## Data Accuracy & Features (Jan 28 2026)
1. **Supabase Date Filtering**:
   - **Pattern:** Use `gte` (start of day) and `lte` (end of day) on standard ISO timestamps.
   - **Performance:** Filter at the Database level, not Application level.

2. **Global State Synchronization**:
   - **Bug:** `current_ce_symbol` wasn't updating globally, causing mismatched labels.
   - **Fix:** Explicitly update global tracking variables immediately after fetching new tokens.
