# 🚀 NIFTY 50 Real-Time Scalping Dashboard

A production-ready terminal-based scalping dashboard for NIFTY 50 index using Angel One SmartAPI.

## Quick Start

```bash
# Navigate to the project directory
cd /Users/balamurugans/Developer/AI-Powered-Signal

# Run the dashboard
python3 main.py
```

## First Time Setup

### 1. Install Dependencies
```bash
pip3 install -r requirements.txt
```

### 2. Configure Credentials
Edit `.env` file with your Angel One credentials:
```
API_KEY=your_api_key
CLIENT_ID=your_client_id
PASSWORD=your_password
TOTP_SECRET=your_totp_secret
```

## Controls

| Key | Action |
|-----|--------|
| `Ctrl+C` | Stop the dashboard |

## Signal Legend

| Signal | Color | Meaning |
|--------|-------|---------|
| 🟢 BUY CALL | Green | RSI < 30 AND Price > EMA(50) → Bullish reversal expected |
| 🔴 BUY PUT | Red | RSI > 70 AND Price < EMA(50) → Bearish reversal expected |
| ⏳ WAITING | Grey | Collecting data or no signal conditions met |

## Troubleshooting

### Connection Timeout
- Ensure your IP is whitelisted in [SmartAPI Portal](https://smartapi.angelone.in)
- Check your internet connection

### Market Hours
- NSE trading hours: **9:15 AM - 3:30 PM IST**
- Dashboard works best during market hours
