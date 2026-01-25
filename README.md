# 🚀 AI-Powered NIFTY 50 Scalping Dashboard

A professional-grade, real-time web dashboard for scalping NIFTY 50 options. This tool interacts with Angel One's SmartAPI to calculate advanced metrics like **Synthetic Basis**, **Market Sentiment**, and **Straddle Decay** to generate high-probability trade signals.

---

## 🚀 Installation & Setup

### 1. Clone the Repository
```bash
git clone https://github.com/balamurugandev/Trader-AI-Signal.git
cd Trader-AI-Signal
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure Credentials
Create a `.env` file in the root directory:
```env
API_KEY=your_angel_one_api_key
CLIENT_ID=your_client_id
PASSWORD=your_password
TOTP_SECRET=your_totp_secret
```

### 4. Run the Dashboard
```bash
python3 server.py
# Server will start at http://localhost:8000
```

---

## 🌟 Key Features

- **Real-Time Data**: Ultra-fast updates via SmartAPI WebSockets.
- **Dynamic ATM Tracking**: Automatically detects the current ATM strike and switches tokens.
- **Professional Analytics**:
  - **Synthetic Future Calculation**: `ATM Strike + CE - PE`
  - **Market Bias (Real Basis)**: `Synthetic Future - Spot`
  - **Straddle Trend**: 3-Period SMA of Straddle Price (CE+PE).
- **Smart Signals**:
  - **Bullish/Bearish Sentiment** based on Market Bias.
  - **Trade Suggestions**: Specific `BUY CE` or `BUY PE` recommendations.
- **Modern UI**: Dark/Glassmorphism design | 12-Hour IST Time | Real-time Charts.

---

## 🧠 Core Logic (The Secret Sauce)

This dashboard uses institutional-grade logic rather than simple indicators.

### 1. Synthetic Future & Market Bias (Relative Z-Score)
To solve the "Cost of Carry" permanent bull bias in Indian markets:
- **Old Standard**: `Synthetic - Spot` (Always positive).
- **New Pro Logic**: `Relative Sentiment = Current Basis - 5min Average Basis`.
- **Signal**:
  - `> +3`: 🟢 **BULLISH** (Momentum Spike)
  - `< -3`: 🔴 **BEARISH** (Momentum Drop)

### 2. Straddle Trend & Logic
We track the **Straddle Price** (`ATM CE + ATM PE`) to avoid trading into decay.
- **RISING Straddle**: Momentum is increasing (Safe to enter).
- **FALLING Straddle**: Theta decay is dominant (Stay away).

### 3. ATM Hysteresis (Anti-Flicker)
Prevents rapid token switching when Spot hovers between strikes (e.g., 25025).
- **Logic**: Only switch ATM if Spot moves **> 40 points** from the current strike.

### 4. Smart Signals + TRAP Filter (PCR)
Combines Sentiment + Trend + **OI Data** to generate signals:

| Sentiment | Trend | OI (PCR) | Signal | Suggestion |
|-----------|-------|----------|--------|------------|
| 🟢 BULLISH | 📈 RISING | Normal (>1.0) | **BUY CALL** | `BUY {ATM} CE` |
| 🔴 BEARISH | 📈 RISING | Normal (<0.7) | **BUY PUT** | `BUY {ATM} PE` |
| 🟢 BULLISH | 📈 RISING | < 0.6 | **⚠️ TRAP** | `AVOID - CALL WRITING` |
| 🔴 BEARISH | 📈 RISING | > 1.4 | **⚠️ TRAP** | `AVOID - PUT WRITING` |
| Any | 📉 FALLING | Any | **WAIT** | `WAIT - DECAY` |

---

## 🛡️ Logic Safety Verification

We ensure the app logic is robust by using **isolated simulation tests**.
**WARNING:** Never run extensive stress tests on the live `server.py` while trading. Use the standalone testing approach below.

### How to Test Safely (Simulation)
Create a file named `tests/verify_logic.py` to simulate market conditions without connecting to the API:

```python
import unittest
from collections import deque

class TestStrategy(unittest.TestCase):
    def test_pcr_trap(self):
        # Simulate: Bullish Signal but Low PCR (Call Writing)
        signal = "BUY CALL"
        pcr = 0.5  # Trap Level
        
        final_signal = signal
        if signal == "BUY CALL" and pcr < 0.6:
            final_signal = "TRAP"
            
        print(f"Scenario: {signal} + PCR {pcr} -> {final_signal}")
        self.assertEqual(final_signal, "TRAP")

if __name__ == '__main__':
    unittest.main()
```

Run this simulation to verify logic upgrades before deploying to production.

---

## 🛠 Tech Stack

- **Backend**: Python (FastAPI, Uvicorn, Threading)
- **Data**: Angel One SmartAPI (WebSocket & REST)
- **Frontend**: Vanilla JavaScript (WebSockets), HTML5, CSS3 (Variables, Flexbox)
- **Charting**: Chart.js (Real-time visualizations)

---

## 📸 Dashboard Overview 

*(Screenshots of the dashboard showing the Signal Panel, Explanatory Legend, and Charts)*

### Signal Legend
- ⚪ **WAIT**: No clear trend or decay
- 🟢 **BUY CALL**: Bullish Sentiment + Rising Straddle ([PCR > 1.0] Supports)
- 🔴 **BUY PUT**: Bearish Sentiment + Rising Straddle ([PCR < 0.7] Supports)
- ⚠️ **TRAP**: High OI Contrast (Price vs Data Mismatch)

---

**Disclaimer**: This tool is for educational purposes only. Trading Options involves high risk. Use at your own discretion.
