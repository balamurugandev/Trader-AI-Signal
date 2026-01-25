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
