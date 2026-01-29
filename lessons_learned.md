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

## 3:00 PM Safety Protocol (Jan 28 2026)
- **Problem**: Short Covering @ 3:00 PM creates "Fake Breakouts" where Price rises but Strike Premiums/Basis drop due to rapid decay/square-off.
- **Solution**: "Trust the Trend, not the Math".
    - Added `get_ema_trend(spot)` using 20-tick simple mean.
    - **Rule 1**: If Spot > EMA (Trend UP) → BLOCK all Bearish signals.
    - **Rule 2**: If Spot < EMA (Trend DOWN) → BLOCK all Bullish signals.
    - **Note**: Trend-following trades (e.g., BUY PUT when Trend is DOWN) are **ALLOWED**. Verified 3:05 PM simulation.
- **Active Window**: 14:55 to 15:30 only.

## UI Cleanups (Jan 28 2026)
- **Problem**: Index Ticker "Day Change" values were static/inaccurate because the API doesn't provide them in the lightweight stream.
- **Solution**: Removed Change/Percentage from the ticker. Now displays only **Name** and **Price** for a cleaner look.
- **Optimization**: Removed `NIFTY SMALLCAP` to declutter the bar, updated grid to 5 columns for perfect spacing.
- **Aesthetics**: Switched ticker font from Monospace/Bold to `Inter` (Regular/Medium) and Centered alignment to match modern UI references.
- **Bug**: Found `ticker.css` was overriding `style.css` with `justify-content: flex-start`, causing left alignment. Fixed by updating `ticker.css`.

## ⚡ Performance Optimization (Jan 30 2026)
1. **The `orjson` Binary Frame Trap**
   - **Issue**: Switched to `orjson` for speed, but frontend disconnected with "Connect Error".
   - **Root Cause**: `orjson.dumps()` returns **bytes** (Binary Frame). The browser's `WebSocket.onmessage` receives a `Blob` instead of text, which standard `JSON.parse` cannot decode.
   - **Fix**: Explicitly decode to string before sending: `await websocket.send_text(orjson.dumps(data).decode('utf-8'))`. This retains serialization speed while ensuring frontend compatibility.

2. **Persistent ThreadPools**
   - **Bad Pattern**: Creating `ThreadPoolExecutor()` inside a `while True` loop (1Hz) generates massive overhead (thread creation/destruction).
   - **Good Pattern**: Initialize `executor = ThreadPoolExecutor()` *once* outside the loop and reuse it via `executor.submit()`.

## 🧠 Logic Calibration Insights (V7)
1. **Velocity vs. Premium**
   - **Mistake**: Setting Velocity threshold to `3.0 pts/s` (too high). NIFTY moves gradually, often `0.5 - 0.7 pts/s` during trends.
   - **Adjustment**: Lowered to `0.4 pts/s`. This captures real momentum without filtering out valid Scalping Zones.

2. **The "Short Covering" Illusion**
   - **Observation**: At 3:00 PM, prices often rise due to square-offs, but premiums decay rapidly.
   - **Defense**: Implemented **Strict Trend Lock**: If Market Trend (EMA20) is SIDEWAYS/DOWN, block ALL Bullish signals, regardless of momentum.

---

# 🏗️ Project Setup from GitHub (Jan 30, 2026)

## Fresh Setup Checklist
When cloning/recovering the project from GitHub to a new machine:

### 1. Clone Repository
```bash
git clone https://github.com/balamurugandev/Trader-AI-Signal.git
cd Trader-AI-Signal
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```
**Key packages**: `fastapi`, `uvicorn`, `pyotp`, `python-dotenv`, `pandas`, `orjson`, `smartapi-python`, `requests`

### 3. Create `.env` File
The `.env` file is **not committed to Git** (security). Create it manually:
```bash
# Copy from template
cp .env.example .env
```

**Required variables:**
```env
API_KEY=your_angel_one_api_key
CLIENT_ID=your_angel_one_client_id
PASSWORD=your_angel_one_password
TOTP_SECRET=your_totp_secret_key
# Optional for trade logging:
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
```

### 4. Angel One API Setup
1. **Create SmartAPI App**: Go to [Angel One SmartAPI](https://smartapi.angelbroking.com/)
2. **Get API Key**: Create app with Redirect URL `https://127.0.0.1`
3. **TOTP Secret**: Enable TOTP in Angel One app → get the **alphanumeric secret key** (not the 6-digit code)

### 5. Run Server
```bash
cd production
python3 server.py
```

### 6. Common Startup Issues
| Error | Cause | Fix |
|-------|-------|-----|
| `Invalid totp` (AB1050) | Wrong TOTP_SECRET | Use alphanumeric key from authenticator setup |
| `Address already in use` | Port 8000 occupied | `pkill -f "server.py"` then restart |
| `ModuleNotFoundError` | Missing packages | `pip install -r requirements.txt` |

---

# 🔧 Angel One Token Resolution (Jan 30, 2026)

## The Problem: `searchScrip` API Failures
- **Symptom**: ATM strike prices showed `--` in Scalping Module
- **API Error**: "No matching trading symbols found for the given query"
- **Rate Limit Error**: "Access denied because of exceeding access rate"

## Why `searchScrip` Fails
1. **Rate Limits**: Angel One limits to ~1 request/second. Server startup makes multiple calls, hitting limits.
2. **Unreliable Search**: Broad searches like `"NIFTY"` return empty or incomplete results.
3. **Exact Symbol Matching**: Searching for `"NIFTY05FEB2625400CE"` returns "no match" even when the contract exists.

## The Solution: Instrument Master File
Instead of API calls, download the **complete instrument master file**:

```python
def get_nfo_instruments():
    """Download and cache Angel One instrument master."""
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    response = requests.get(url, timeout=30)
    all_instruments = response.json()  # ~231,000 instruments
    
    # Filter for NFO NIFTY only
    nfo_instruments = [
        inst for inst in all_instruments 
        if inst.get('exch_seg') == 'NFO' and 'NIFTY' in inst.get('name', '').upper()
    ]
    return nfo_instruments  # ~4,000 instruments
```

### Key Benefits
1. **No API Rate Limits**: Downloads once per day, cached in memory
2. **Reliable Token Lookup**: Exact symbol matching against 231K instruments
3. **Dynamic Expiry Discovery**: Parses actual available expiries from data
4. **Offline Capability**: Works even if API is down

## Dynamic Expiry Discovery
**Problem**: Calculated expiry (Feb 5) may not have listed contracts yet.

**Solution**: Parse available expiries from instrument master:
```python
# Extract all NIFTY50 options
nifty50_options = [inst for inst in instruments if matches_nifty50_pattern(inst)]

# Find unique expiry dates
unique_expiries = sorted(set(opt['expiry'] for opt in nifty50_options))

# Use nearest available expiry
nearest_expiry = unique_expiries[0]  # e.g., Feb 3 instead of Feb 5
```

## Instrument Master JSON Format
```json
{
  "token": "49801",
  "symbol": "NIFTY03FEB2625400CE",
  "name": "NIFTY",
  "expiry": "03FEB2026",
  "strike": "25400.000000",
  "lotsize": "25",
  "instrumenttype": "OPTIDX",
  "exch_seg": "NFO"
}
```

## Fallback: Closest Strike Matching
If exact ATM strike (e.g., 25400) isn't listed, find the closest available:
```python
available_strikes = {25300, 25350, 25450, 25500}  # From instrument master
atm_strike = 25400
closest = min(available_strikes, key=lambda x: abs(x - atm_strike))  # Returns 25350 or 25450
```

---

# 📊 Supabase Trade Logger Setup (Jan 30, 2026)

## Purpose
Logs all trade signals to Supabase for historical analysis and performance tracking.

## Setup Steps

### 1. Get Credentials from Supabase Dashboard
1. Go to [supabase.com](https://supabase.com) → Your Project
2. Navigate to **Project Settings** → **API**
3. Copy:
   - **URL**: `https://xxxxx.supabase.co`
   - **anon public key**: `eyJhbGciOiJIUzI1NiI...`

### 2. Add to `.env` File
```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-public-key
```

### 3. Verify Connection
```bash
# Quick test (run from project root)
python3 -c "
from supabase import create_client
import os
from dotenv import load_dotenv
load_dotenv('.env')
client = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_KEY'])
result = client.table('trade_logs').select('*').limit(1).execute()
print('✅ Connected! Records:', len(result.data))
"
```

## Table Schema
The `trade_logs` table should have these columns:
```sql
CREATE TABLE trade_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    spot_price DECIMAL(10,2),
    basis DECIMAL(10,2),
    pcr DECIMAL(5,2),
    signal VARCHAR(50),
    trap_reason TEXT,
    ce_symbol VARCHAR(50),
    pe_symbol VARCHAR(50),
    ce_price DECIMAL(10,2),
    pe_price DECIMAL(10,2)
);
```

## How the Logger Works
- **Async Queue**: Logs are added to a bounded queue (maxsize=100)
- **Non-Blocking**: Uses `put_nowait()` - drops logs if queue full (never blocks trading)
- **Background Worker**: Daemon thread processes queue and inserts to Supabase
- **Fail-Safe**: If Supabase is down, trading continues unaffected

## Troubleshooting
| Issue | Cause | Fix |
|-------|-------|-----|
| `SUPABASE_URL missing` warning | `.env` not loaded | Check file path, restart server |
| `supabase library missing` | Package not installed | `pip install supabase` |
| Connection timeout | Network issue | Check internet, try again |
| `relation "trade_logs" does not exist` | Table not created | Run CREATE TABLE SQL above |

---

# 📋 Quick Reference Commands

```bash
# Kill existing server
pkill -f "server.py"

# Start server
cd production && python3 server.py

# Check if port is in use
lsof -i :8000

# View server logs
tail -f production/logs/*/app.log

# Git: Restore from remote
git fetch origin && git reset --hard origin/main

# Reinstall dependencies
pip install -r requirements.txt
```

