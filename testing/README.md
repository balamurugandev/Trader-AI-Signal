# 🧪 Stress Test Suite for NIFTY Scalper

This folder contains a comprehensive testing suite to simulate various market regimes and specific scenarios (Bull/Bear/Traps) without risking the production server.

## Components

### 1. `scenario_engine.py`
A robust market simulation engine that generates realistic tick data including:
- **Price Action**: Trends, Mean Reversion, Random Walk.
- **Option Greeks**: Simulates Delta, Gamma, Theta decay based on price movement.
- **VIX Regimes**:
    - **NORMAL**: Standard behavior.
    - **HIGH_VIX**: Fast moves, expensive premiums, high Gamma risk.
    - **LOW_VIX**: Slow moves, cheap premiums, high Theta decay.

### 2. `test_server.py`
A standalone FastAPI server that mimics the production backend.
- **Port**: `8001` (Separate from Main App on 8000).
- **Endpoint**: Streams data via `/ws` WebSocket.
- **Control**: Allows dynamic scenario switching via HTTP API.
- **Frontend**: Serves the shared UI from `../production/static`.

## How to Run

1. **Start the Test Server**:
   ```bash
   python3 testing/test_server.py
   ```

2. **Open Dashboard**:
   Navigate to [http://localhost:8001](http://localhost:8001).

3. **Control Scenarios**:
   You can switch scenarios dynamically using the `/control` endpoint.

   **Examples:**
   - **Bull Run**: `http://localhost:8001/control?scenario=BULL_RUN&speed_ms=10`
   - **Bear Crash**: `http://localhost:8001/control?scenario=BEAR_CRASH&regime=HIGH_VIX`
   - **Control Panel**: Use the buttons in the Test UI (if implemented) or browser console fetch.

## Verified Scenarios
- `BULL_RUN`: Confirmed "BUY CALL" signal generation.
- `BULL_TRAP`: Confirmed "TRAP" signal logic logic (Price UP, PCR < 0.6).
- `BEAR_CRASH`: Confirmed "BUY PUT" signal generation.
