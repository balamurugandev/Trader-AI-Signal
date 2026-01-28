# 🚀 Scalp Trader Pro (Previously AI-Powered Signal)

A professional-grade, real-time web dashboard for scalping NIFTY 50 options. This tool interacts with Angel One's SmartAPI to calculate advanced metrics like **Synthetic Basis**, **Market Sentiment**, and **Straddle Decay** to generate high-probability trade signals.

## 📱 Mobile & PWA Support (New in v2.0)
- **Responsive Layout**: Optimized for Phones (OnePlus 13R) and Tablets (Xiaomi Pad 6).
- **PWA Ready**: Add to Home Screen for a native app experience.
- **Stacked View**: Clean single-column layout on mobile, 2-column on tablets.
- **Touch-Friendly**: Larger buttons, scrolling ticker, and optimized charts.

---

## 🚀 First-Time Setup

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

---

## ▶️ How to Run (Daily Usage)

This system is split into **Production** (Live Trading) and **Testing** (Simulation).

### 🟢 Run Production Server (Live Market)
```bash
python3 production/server.py
```
> **Open Dashboard:** [http://localhost:8000](http://localhost:8000)

### 🟡 Run Stress Test / Simulation
```bash
python3 testing/test_server.py
```
> **Open Test Dashboard:** [http://localhost:8001](http://localhost:8001)

**Control Scenarios via URL:**
- **Bull Run**: `http://localhost:8001/control?scenario=BULL_RUN&speed_ms=100`
- **Bear Trap**: `http://localhost:8001/control?scenario=BEAR_TRAP&speed_ms=100`
- **Budget Day**: `http://localhost:8001/control?scenario=BUDGET_DAY&regime=BUDGET_VOLATILITY`

---

## 🌟 Key Features

- **Real-Time Data**: Ultra-fast updates via SmartAPI WebSockets.
- **Dynamic ATM Tracking**: Automatically detects the current ATM strike and switches tokens.
- **3-Column Professional Layout**:
  1.  **Data Engine**: Future Price, Strike Prices, and **Market Bias Meter** (Glow Effect).
  2.  **Strategy Chart**: Large center chart tracking **Straddle Price** (CE+PE) trends.
  3.  **Signal Cockpit**: Clean panel with Buy/Sell recommendations and Signal Legends.
- **Advanced Logic (Velocity V6)**:
  - **Momentum-Based Signals**: Validates entry only when price velocity confirms direction.
  - **Synthetic Future Calculation**: `(ATM Strike + CE) - PE`.
  - **Straddle Trend**: Prevents trading into Theta Decay.
- **Smart Filters**:
  - **Trap Detection**: Identifies Bull/Bear traps using Price vs OI divergence.
  - **PCR Filter**: Avoids traps (e.g., Bull signal blocked if PCR < 0.6).
  - **Hysteresis**: Prevents ATM flicker when spot is at strike boundary.

---

## 🧠 Core Logic (The Secret Sauce)

This dashboard uses institutional-grade logic rather than simple moving averages.

### 1. Synthetic Future & Market Bias (Basis)
To solve the "Cost of Carry" permanent bull bias in Indian markets:
- **Old Standard**: `Synthetic - Spot` (Always positive).
- **New Pro Logic**: `Relative Sentiment = Current Basis - 5min Average Basis`.
- **Signal**:
  - `> +3`: 🟢 **BULLISH** (Institutional Long Buildup)
  - `< -3`: 🔴 **BEARISH** (Institutional Short Buildup)

### ⚡ Features

### 1. Velocity Momentum Bar (New)
Located under the Future Price, this tool measures the speed of price movement in **Points per Second (pts/s)**.
- **Visuals**: A dynamic bar that fills up as speed increases (Yellow -> Red intensity).
- **Label**: Shows exact speed (e.g., `⚡ 5.2 pts/s`).
- **Usage**:
    - **< 2.0 pts/s**: Low momentum (Chop/Sideways).
    - **> 5.0 pts/s**: High momentum (Strong Trend).
    - Use this to confirm "Fast Breakouts" vs "Slow Grinds".

### 2. Scalping Signals
- **BUY CALL**: Triggered when Price is ABOVE EMA + RSI < 30 (Oversold) + Rising Momentum.o decay.
- **RISING Straddle**: Momentum is increasing (Safe to enter).
- **FALLING Straddle**: Theta decay is dominant (Stay away).

### 2. Straddle Trend (Theta Protection)
We track the **Straddle Price** (`ATM CE + ATM PE`) to avoid trading into decay.
- **RISING Straddle**: Momentum is increasing (Safe to enter).
- **FALLING Straddle**: Theta decay is dominant (Stay away).

### 3. Velocity V6 Engine
Price changes are validated against time:
- **Fast Moves**: High Velocity = Genuine Breakout.
- **Slow Drift**: Low Velocity = Trap/Decay.

### 4. Smart Signal Matrix
Combines Sentiment + Trend + **OI Data** to generate signals:

| Sentiment | Trend | OI (PCR) | Signal | Suggestion |
|-----------|-------|----------|--------|------------|
| 🟢 BULLISH | 📈 RISING | Normal (>1.0) | **BUY CALL** | `BUY {ATM} CE` |
| 🔴 BEARISH | 📈 RISING | Normal (<0.7) | **BUY PUT** | `BUY {ATM} PE` |
| 🟢 BULLISH | 📈 RISING | < 0.6 | **⚠️ TRAP** | `AVOID - CALL WRITING` |
| 🔴 BEARISH | 📈 RISING | > 1.4 | **⚠️ TRAP** | `AVOID - PUT WRITING` |
| Any | 📉 FALLING | Any | **WAIT** | `WAIT - DECAY` |

---

## 🛠 Tech Stack

- **Backend**: Python (FastAPI, Uvicorn, Threading)
- **Data**: Angel One SmartAPI (WebSocket & REST)
- **Frontend**: Vanilla JavaScript (WebSockets), CSS3 (Dark Theme, Glassmorphism)
- **Charting**: Chart.js (Canvas-based high-performance rendering)
- **Architecture**: Modular (Separated Production & Testing Logic)

---

## ❓ Troubleshooting

### ⚠️ "Network Timeout fetching..."
If you see these errors in the terminal:
> `⚠️ Network Timeout fetching NIFTY27JAN2625050CE. Retrying...`
> `Max retries exceeded with url...`

**Solution:**
1.  **Check Internet**: Your connection to Angel One API is unstable.
2.  **Ignore**: The system automatically retries on the next poll (every 1 second). Pushing through occasional errors is normal.
3.  **VPN**: If consistent, try disabling/enabling VPN as some IPs are rate-limited by Angel One.

---
**Disclaimer**: This tool is for educational purposes only. Trading Options involves high risk. Use at your own discretion.
