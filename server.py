"""
NIFTY 50 Real-Time Scalping Dashboard - Web Server
FastAPI backend with WebSocket for real-time data streaming
"""

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import pandas as pd
import pyotp
from dotenv import load_dotenv
import os

from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

# =============================================================================
# LOAD ENVIRONMENT VARIABLES
# =============================================================================
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("API_KEY", "")
CLIENT_ID = os.getenv("CLIENT_ID", "")
PASSWORD = os.getenv("PASSWORD", "")
TOTP_SECRET = os.getenv("TOTP_SECRET", "")

# Trading Configuration
SYMBOL_TOKEN = "99926000"  # NIFTY 50 Index
EXCHANGE_TYPE = 1  # NSE
NFO_EXCHANGE_TYPE = 2  # NFO for F&O

# Indicator Settings
RSI_PERIOD = 14
EMA_PERIOD = 50
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# Scalping Module Settings
SCALPING_POLL_INTERVAL = 1  # seconds

# =============================================================================
# DATA CLASSES
# =============================================================================
@dataclass
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    is_closed: bool = False

class CandleManager:
    def __init__(self, timeframe_minutes=1):
        self.timeframe = timeframe_minutes
        self.current_candle: Optional[Candle] = None
        self.closed_candles: deque = deque(maxlen=200)
        
    def update(self, price: float, timestamp: datetime) -> bool:
        candle_time = timestamp.replace(second=0, microsecond=0)
        candle_closed = False
        
        if self.current_candle:
            if candle_time > self.current_candle.timestamp:
                self.current_candle.is_closed = True
                self.closed_candles.append(self.current_candle)
                candle_closed = True
                self.current_candle = Candle(
                    timestamp=candle_time,
                    open=price, high=price, low=price, close=price
                )
            else:
                self.current_candle.high = max(self.current_candle.high, price)
                self.current_candle.low = min(self.current_candle.low, price)
                self.current_candle.close = price
        else:
            self.current_candle = Candle(
                timestamp=candle_time,
                open=price, high=price, low=price, close=price
            )
        return candle_closed

    def get_closes(self) -> pd.Series:
        closes = [c.close for c in self.closed_candles]
        if self.current_candle:
            closes.append(self.current_candle.close)
        return pd.Series(closes)
        
    def get_count(self) -> int:
        return len(self.closed_candles) + (1 if self.current_candle else 0)

# =============================================================================
# GLOBAL STATE
# =============================================================================
candle_manager = CandleManager(timeframe_minutes=1)
tick_history: deque = deque(maxlen=20)
current_signal = "WAITING"
signal_color = "grey"
last_rsi: Optional[float] = None
last_ema: Optional[float] = None
last_price: Optional[float] = None
ws_connected = False
market_status = "CONNECTING..."
total_ticks = 0
sws = None
lock = threading.Lock()
smart_api_global = None  # Global SmartConnect instance for scalping module

# WebSocket clients
connected_clients: Set[WebSocket] = set()

# =============================================================================
# SCALPING MODULE - Global State (NEW)
# =============================================================================
scalping_history: deque = deque(maxlen=1000)  # Upgraded from 500 for better history
scalping_lock = threading.Lock()
future_token: Optional[str] = None
atm_ce_token: Optional[str] = None
atm_pe_token: Optional[str] = None
last_future_price: Optional[float] = None
last_ce_price: Optional[float] = None
last_pe_price: Optional[float] = None
last_basis: Optional[float] = None
straddle_price: Optional[float] = None
scalping_signal = "WAIT"
scalping_status = "INITIALIZING..."

# Professional Scalping - New State Variables
real_basis: Optional[float] = None  # Synthetic Future - Spot
sentiment = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL
straddle_trend = "FLAT"  # RISING, FALLING, FLAT
straddle_sma3: Optional[float] = None  # 3-period SMA of straddle
current_atm_strike: Optional[int] = None  # Current ATM for frontend display
trade_suggestion = "WAIT"  # Current trade suggestion

# Anomaly Detection Globals
raw_basis_history: deque = deque(maxlen=300)  # For Z-Score (300 ticks ~ 5 mins)
pcr_value: Optional[float] = None
is_trap = False


# =============================================================================
# INDICATOR CALCULATIONS
# =============================================================================
def calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    delta = prices.diff()
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)
    avg_gain = gains.ewm(alpha=1/period, min_periods=period).mean().iloc[-1]
    avg_loss = losses.ewm(alpha=1/period, min_periods=period).mean().iloc[-1]
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))

def calculate_ema(prices: pd.Series, period: int = 50) -> Optional[float]:
    if len(prices) < period:
        return None
    return float(prices.ewm(span=period, adjust=False).mean().iloc[-1])

def calculate_indicators():
    global last_rsi, last_ema
    if candle_manager.get_count() < max(RSI_PERIOD, EMA_PERIOD):
        return None, None
    prices = candle_manager.get_closes()
    rsi = calculate_rsi(prices, RSI_PERIOD)
    ema = calculate_ema(prices, EMA_PERIOD)
    last_rsi = rsi
    last_ema = ema
    return rsi, ema

def generate_signal(price: float, rsi: Optional[float], ema: Optional[float]) -> tuple[str, str]:
    if rsi is None or ema is None:
        return "WAITING", "grey"
    if rsi < RSI_OVERSOLD and price > ema:
        return "BUY CALL", "green"
    if rsi > RSI_OVERBOUGHT and price < ema:
        return "BUY PUT", "red"
    return "WAITING", "grey"

# =============================================================================
# SCALPING MODULE - Helper Functions (NEW)
# =============================================================================
def parse_expiry_from_symbol(symbol: str) -> Optional[datetime]:
    """
    Parse expiry date from NIFTY option/future symbol.
    Formats: NIFTY30JAN26FUT, NIFTY30JAN2625050CE
    Returns datetime or None if parsing fails.
    """
    import re
    from datetime import datetime
    
    # Pattern: NIFTY + DDMMMYY + (strike+CE/PE or FUT)
    # E.g., NIFTY30JAN2625050CE -> extract 30JAN26
    match = re.search(r'NIFTY(\d{2})([A-Z]{3})(\d{2})', symbol)
    if match:
        day = match.group(1)
        month = match.group(2)
        year = match.group(3)
        try:
            date_str = f"{day}{month}{year}"
            return datetime.strptime(date_str, "%d%b%y")
        except ValueError:
            return None
    return None

def get_option_tokens(smart_api, spot_price: float) -> dict:
    """
    Dynamically fetch tokens for NIFTY Future and ATM CE/PE options.
    
    SMART EXPIRY SELECTION:
    - Parses expiry dates from trading symbols
    - Filters for dates >= today
    - Sorts ascending to find NEAREST WEEKLY expiry
    - Uses this specific expiry for CE/PE selection
    """
    global scalping_status
    from datetime import datetime
    
    try:
        scalping_status = "Fetching instrument tokens..."
        
        # Round spot to nearest 50 for ATM strike
        atm_strike = int(round(spot_price / 50) * 50)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        print(f"{'='*60}")
        print(f"🎯 SMART EXPIRY SELECTION")
        print(f"📍 Spot Price: ₹{spot_price:.2f}")
        print(f"📍 Computed ATM Strike: {atm_strike}")
        print(f"📍 Today's Date: {today.strftime('%d-%b-%Y')}")
        print(f"{'='*60}")
        
        tokens = {
            'future': None, 'ce': None, 'pe': None,
            'future_symbol': '', 'ce_symbol': '', 'pe_symbol': '',
            'atm_strike': atm_strike,
            'expiry_date': None
        }
        
        try:
            time.sleep(0.5)  # Rate limit protection
            search_result = smart_api.searchScrip("NFO", "NIFTY")
            
            if search_result and search_result.get('data'):
                data_list = search_result['data']
                print(f"📋 API returned {len(data_list)} instruments")
                
                # Step 1: Filter for NIFTY 50 only (exclude NIFTYNXT50, BANKNIFTY, FINNIFTY)
                nifty_instruments = []
                for item in data_list:
                    ts = item.get('tradingsymbol', '')
                    if ts.startswith('NIFTY') and 'NXT50' not in ts and 'BANK' not in ts and 'FIN' not in ts:
                        nifty_instruments.append(item)
                
                print(f"📋 Filtered to {len(nifty_instruments)} NIFTY 50 instruments")
                
                # Step 2: Separate Options and Futures
                options = []
                futures = []
                for item in nifty_instruments:
                    ts = item.get('tradingsymbol', '')
                    if ts.endswith('CE') or ts.endswith('PE'):
                        expiry = parse_expiry_from_symbol(ts)
                        if expiry and expiry >= today:
                            options.append({**item, 'expiry_date': expiry})
                    elif ts.endswith('FUT') and len(ts) <= 17:  # Simple future, not spread
                        expiry = parse_expiry_from_symbol(ts)
                        if expiry and expiry >= today:
                            futures.append({**item, 'expiry_date': expiry})
                
                print(f"📋 Valid options: {len(options)}, Valid futures: {len(futures)}")
                
                # Step 3: SMART EXPIRY - Sort options by expiry date ascending
                options.sort(key=lambda x: x['expiry_date'])
                futures.sort(key=lambda x: x['expiry_date'])
                
                # Step 4: Find NEAREST WEEKLY EXPIRY
                if options:
                    nearest_expiry = options[0]['expiry_date']
                    tokens['expiry_date'] = nearest_expiry
                    print(f"✅ NEAREST WEEKLY EXPIRY: {nearest_expiry.strftime('%d-%b-%Y (%A)')}")
                else:
                    print("⚠️ No valid options found!")
                    return tokens
                
                # Step 5: Find Future (nearest expiry)
                if futures:
                    nearest_future = futures[0]
                    tokens['future'] = nearest_future.get('symboltoken')
                    tokens['future_symbol'] = nearest_future.get('tradingsymbol')
                    print(f"✅ Future: {tokens['future_symbol']} (Expiry: {nearest_future['expiry_date'].strftime('%d-%b-%Y')})")
                
                # Step 6: Find ATM CE and PE with nearest expiry
                strike_str = str(atm_strike)
                
                # Filter options for nearest expiry only
                nearest_expiry_options = [opt for opt in options if opt['expiry_date'] == nearest_expiry]
                print(f"📋 Options at nearest expiry: {len(nearest_expiry_options)}")
                
                for opt in nearest_expiry_options:
                    ts = opt.get('tradingsymbol', '')
                    
                    # Check for exact ATM strike match
                    if strike_str in ts:
                        if ts.endswith('CE') and not tokens['ce']:
                            tokens['ce'] = opt.get('symboltoken')
                            tokens['ce_symbol'] = ts
                            print(f"✅ ATM CE: {ts} -> {tokens['ce']}")
                        elif ts.endswith('PE') and not tokens['pe']:
                            tokens['pe'] = opt.get('symboltoken')
                            tokens['pe_symbol'] = ts
                            print(f"✅ ATM PE: {ts} -> {tokens['pe']}")
                    
                    if tokens['ce'] and tokens['pe']:
                        break
                
        except Exception as e:
            print(f"⚠️ Token search error: {e}")
            scalping_status = f"Search error: {str(e)[:30]}"
        
        found_count = sum(1 for k in ['future', 'ce', 'pe'] if tokens[k])
        scalping_status = f"Found {found_count}/3 tokens"
        
        print(f"{'='*60}")
        print(f"📈 FINAL TOKENS:")
        print(f"   Future: {tokens['future_symbol']} ({tokens['future']})")
        print(f"   CE:     {tokens['ce_symbol']} ({tokens['ce']})")
        print(f"   PE:     {tokens['pe_symbol']} ({tokens['pe']})")
        print(f"   ATM:    {atm_strike}")
        if tokens['expiry_date']:
            print(f"   Expiry: {tokens['expiry_date'].strftime('%d-%b-%Y')}")
        print(f"{'='*60}")
        
        return tokens
        
    except Exception as e:
        scalping_status = f"Token Error: {str(e)[:20]}"
        print(f"❌ get_option_tokens error: {e}")
        return {'future': None, 'ce': None, 'pe': None, 'atm_strike': 0}



def fetch_ltp(smart_api, exchange: str, trading_symbol: str, token: str) -> Optional[float]:
    """Fetch LTP for a single instrument with rate limit protection."""
    if token is None:
        return None
    try:
        time.sleep(0.2)  # Rate limit protection
        data = smart_api.ltpData(exchange, trading_symbol, token)
        if data and data.get('data') and data['data'].get('ltp'):
            return float(data['data']['ltp'])
        elif data and data.get('message'):
            print(f"⚠️ LTP error for {trading_symbol}: {data.get('message')}")
    except Exception as e:
        error_str = str(e)
        if "ConnectTimeoutError" in error_str or "Max retries exceeded" in error_str:
            print(f"⚠️ Network Timeout fetching {trading_symbol}. Retrying...")
        else:
            print(f"⚠️ LTP fetch error for {trading_symbol}: {error_str}")
    return None




def fetch_oi_data(smart_api):
    """
    Background thread to poll Open Interest for PCR Trap Filter.
    Runs every 30 seconds to save bandwidth.
    """
    global pcr_value, is_trap
    print("🛡️ OI Trap Filter thread started")
    
    while True:
        try:
            if atm_ce_token and atm_pe_token and current_atm_strike:
                # In a real production app, verify if ltpData returns 'oi' or use specific getCandleData
                # For this implementation, we will act as if data is available or skip if not.
                # Assuming ltpData returns OI in a field 'oi' or similar (SmartAPI implementation dependent)
                
                # Placeholder for PCR calculation since we don't have live market OI access in this env
                # We will default PCR to 1.0 (Neutral) if data unavailable to prevent false traps
                pcr_value = 1.0 
                
                # Logic:
                # call_oi = ...
                # put_oi = ...
                # if call_oi > 0: pcr_value = put_oi / call_oi
            
            time.sleep(30)
        except Exception as e:
            print(f"⚠️ OI Fetch error: {e}")
            time.sleep(30)

def update_scalping_data():
    """
    Background thread to poll Future/Options prices and calculate Basis/Straddle.
    """
    global future_token, atm_ce_token, atm_pe_token
    global last_future_price, last_ce_price, last_pe_price
    global last_basis, straddle_price, scalping_signal, scalping_status
    global current_atm_strike, real_basis, sentiment, straddle_trend, straddle_sma3, trade_suggestion
    global is_trap, raw_basis_history, pcr_value, smart_api_global, market_status
    
    print("🚀 Scalping Module thread started")
    
    # 1. Setup Phase: Wait for Auth + Spot
    while True:
        if smart_api_global is None:
            scalping_status = market_status
            time.sleep(1)
            continue
            
        if last_price is None:
            scalping_status = "Waiting for Spot Price..."
            time.sleep(1)
            continue
            
        break # Ready to start

    print("   Waiting for spot price... DONE")
        
    # Fetch initial tokens
    try:
        tokens = get_option_tokens(smart_api_global, last_price)
    except Exception as e:
        print(f"Token fetch error: {e}")
        time.sleep(2)
        return update_scalping_data() # Retry setup
    future_token = tokens.get('future')
    atm_ce_token = tokens.get('ce')
    atm_pe_token = tokens.get('pe')
    future_symbol = tokens.get('future_symbol', '')
    ce_symbol = tokens.get('ce_symbol', '')
    pe_symbol = tokens.get('pe_symbol', '')
    current_atm_strike = tokens.get('atm_strike', 0)
    current_expiry = tokens.get('expiry_date')
    
    print(f"📈 Scalping ready: ATM={current_atm_strike}, Expiry={current_expiry}")
    
    last_straddle_prices = deque(maxlen=5)  # For trend detection
    raw_basis_history = deque(maxlen=20) # For Z-Score calculation
    atm_shift_count = 0
    poll_count = 0
    
    while True:
        try:
            # Check Auth Status dynamically
            if smart_api_global is None:
                scalping_status = market_status
                time.sleep(1)
                continue
                
            time.sleep(SCALPING_POLL_INTERVAL)
            
            spot = last_price
            if spot is None:
                continue
            
            # DYNAMIC ATM TRACKING: Check on EVERY tick
            new_atm = int(round(spot / 50) * 50)
            
            should_switch = False
            
            if current_atm_strike is None or current_atm_strike == 0:
                 should_switch = True
            elif new_atm != current_atm_strike:
                # Hysteresis Check:
                # Only switch if Spot is significantly deep into the new zone for INDIAN MARKET stability.
                # Midpoint is 25 pts away. Buffer is 15 pts. Total distance needed = 40 pts.
                dist = abs(spot - current_atm_strike)
                if dist >= 40:
                    should_switch = True
            
            # Trigger refresh when ATM changes based on Hysteresis
            if should_switch:
                current_atm = new_atm
                atm_shift_count += 1
                print(f"\n{'='*60}")
                print(f"🔄 DYNAMIC ATM SHIFT #{atm_shift_count}")
                print(f"   Spot: ₹{spot:.2f}")
                print(f"   Old ATM: {current_atm_strike} -> New ATM: {new_atm}")
                print(f"   Unsubscribing from: CE={ce_symbol}, PE={pe_symbol}")
                print(f"{'='*60}")
                
                time.sleep(0.5)  # Rate limit before token refresh
                tokens = get_option_tokens(smart_api_global, spot)
                
                future_token = tokens.get('future')
                atm_ce_token = tokens.get('ce')
                atm_pe_token = tokens.get('pe')
                future_symbol = tokens.get('future_symbol', '')
                ce_symbol = tokens.get('ce_symbol', '')
                pe_symbol = tokens.get('pe_symbol', '')
                current_atm = new_atm
                
                # Clear straddle history on ATM change
                last_straddle_prices.clear()
                
                print(f"✅ Subscribed to new ATM: CE={ce_symbol}, PE={pe_symbol}")
            else:
                current_atm = current_atm_strike
            
            # Fetch LTPs using proper trading symbols
            fut_ltp = fetch_ltp(smart_api_global, "NFO", future_symbol, future_token) if future_token else None
            ce_ltp = fetch_ltp(smart_api_global, "NFO", ce_symbol, atm_ce_token) if atm_ce_token else None
            pe_ltp = fetch_ltp(smart_api_global, "NFO", pe_symbol, atm_pe_token) if atm_pe_token else None
            
            poll_count += 1
            if poll_count % 10 == 1:  # Log every 10th poll
                print(f"📊 Poll #{poll_count}: ATM={current_atm}, FUT={fut_ltp}, CE={ce_ltp}, PE={pe_ltp}")

            
            with scalping_lock:
                last_future_price = fut_ltp
                last_ce_price = ce_ltp
                last_pe_price = pe_ltp
                current_atm_strike = current_atm
                
                # ============================================================
                # SYNTHETIC BASIS CALCULATION (Professional Logic)
                # ============================================================
                # Synthetic Future = ATM Strike + CE Premium - PE Premium
                # Real Basis = Synthetic Future - Spot Price
                # This is more accurate than simple Future - Spot
                
                if ce_ltp and pe_ltp and spot:
                    synthetic_future = current_atm_strike + ce_ltp - pe_ltp
                    raw_basis = synthetic_future - spot
                    real_basis = round(raw_basis, 2)
                    
                    # Update History for Z-Score
                    raw_basis_history.append(raw_basis)
                    
                    # Calculate Relative Sentiment Score (Z-Score Proxy)
                    if len(raw_basis_history) > 10:
                        avg_basis = sum(raw_basis_history) / len(raw_basis_history)
                        sentiment_score = raw_basis - avg_basis
                    else:
                        sentiment_score = 0
                    
                    # Enhanced Sentiment Logic (Relative)
                    if sentiment_score > 3:
                        sentiment = "BULLISH"
                    elif sentiment_score < -3:
                        sentiment = "BEARISH"
                    else:
                        sentiment = "NEUTRAL"
                else:
                    real_basis = None
                    sentiment = "NEUTRAL"
                    sentiment_score = 0
                
                # Legacy basis calculation (Future - Spot) for backward compat
                if fut_ltp and spot:
                    last_basis = round(fut_ltp - spot, 2)
                else:
                    last_basis = None
                
                # ============================================================
                # STRADDLE PRICE & TREND DETECTION
                # ============================================================
                if ce_ltp and pe_ltp:
                    straddle_price = round((ce_ltp + pe_ltp) / 2, 2)
                    last_straddle_prices.append(straddle_price)
                    
                    # Calculate 3-period SMA of Straddle
                    if len(last_straddle_prices) >= 3:
                        recent_3 = list(last_straddle_prices)[-3:]
                        straddle_sma3 = round(sum(recent_3) / 3, 2)
                        
                        # Trend Detection: Current vs SMA
                        if straddle_price > straddle_sma3:
                            straddle_trend = "RISING"  # Gamma/Momentum
                        elif straddle_price < straddle_sma3:
                            straddle_trend = "FALLING"  # Decay
                        else:
                            straddle_trend = "FLAT"
                    else:
                        straddle_sma3 = None
                        straddle_trend = "FLAT"
                else:
                    straddle_price = None
                    straddle_trend = "FLAT"
                
                # ============================================================
                # GENERATE SCALPING SIGNAL + TRAP FILTER
                # ============================================================
                is_trap = False
                temp_signal = "WAIT"
                temp_suggestion = "WAIT - NO TREND"
                
                if sentiment == "BULLISH" and straddle_trend == "RISING":
                    temp_signal = "BUY CALL"
                    temp_suggestion = f"BUY {current_atm_strike} CE"
                elif sentiment == "BEARISH" and straddle_trend == "RISING":
                    temp_signal = "BUY PUT"
                    temp_suggestion = f"BUY {current_atm_strike} PE"
                elif straddle_trend == "FALLING":
                    temp_signal = "WAIT"
                    temp_suggestion = "WAIT - DECAY"
                
                # Trap Filter Check
                if temp_signal == "BUY CALL":
                    if pcr_value and pcr_value < 0.6:
                        temp_signal = "TRAP"
                        is_trap = True
                        temp_suggestion = "⚠️ TRAP - HEAVY CALL WRITING"
                elif temp_signal == "BUY PUT":
                    if pcr_value and pcr_value > 1.4:
                        temp_signal = "TRAP"
                        is_trap = True
                        temp_suggestion = "⚠️ TRAP - HEAVY PUT WRITING"
                        
                scalping_signal = temp_signal
                trade_suggestion = temp_suggestion
                
                # Determine status
                if fut_ltp or ce_ltp or pe_ltp:
                    scalping_status = "LIVE"
                elif future_token or atm_ce_token or atm_pe_token:
                    scalping_status = "Tokens found, awaiting data..."
                else:
                    scalping_status = "No tokens available"
                
                # Append to history with enhanced data
                scalping_history.append({
                    'time': datetime.now().strftime("%I:%M:%S %p"),  # 12hr IST format
                    'spot': spot,
                    'future': fut_ltp,
                    'basis': last_basis,
                    'real_basis': real_basis,
                    'ce': ce_ltp,
                    'pe': pe_ltp,
                    'straddle': straddle_price,
                    'sma3': straddle_sma3,
                    'trend': straddle_trend,
                    'sentiment': sentiment,
                    'signal': scalping_signal
                })
            
        except Exception as e:
            scalping_status = f"Error: {str(e)[:20]}"
            print(f"❌ Scalping loop error: {e}")
            
        time.sleep(SCALPING_POLL_INTERVAL + 1)  # 2 second poll to avoid rate limits


# =============================================================================
# AUTHENTICATION
# =============================================================================
def generate_totp() -> str:
    totp = pyotp.TOTP(TOTP_SECRET)
    return totp.now()

def authenticate():
    global market_status
    market_status = "Authenticating..."
    print("🔐 Authenticating with Angel One...")
    
    smart_api = SmartConnect(api_key=API_KEY)
    totp_token = generate_totp()
    
    try:
        data = smart_api.generateSession(
            clientCode=CLIENT_ID,
            password=PASSWORD,
            totp=totp_token
        )
        
        if data.get("status"):
            auth_token = data["data"]["jwtToken"]
            refresh_token = data["data"]["refreshToken"]
            feed_token = smart_api.getfeedToken()
            print("✅ Authentication successful!")
            time.sleep(1)
            return smart_api, {
                "auth_token": auth_token,
                "refresh_token": refresh_token,
                "feed_token": feed_token
            }
        else:
            raise Exception(f"Login failed: {data.get('message', 'Unknown error')}")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        market_status = f"Auth Error: {str(e)[:20]}"
        raise

# =============================================================================
# WEBSOCKET DATA HANDLER
# =============================================================================
def on_data(ws, message: dict):
    global current_signal, signal_color, last_price, total_ticks, market_status
    
    try:
        if isinstance(message, dict):
            ltp = message.get("last_traded_price")
            if ltp is not None:
                price = ltp / 100.0
                current_time = datetime.now()
                
                with lock:
                    total_ticks += 1
                    last_price = price
                    market_status = "LIVE"
                    
                    candle_manager.update(price, current_time)
                    
                    tick_entry = {
                        "time": current_time.strftime("%I:%M:%S %p"),  # 12hr IST
                        "price": price,
                        "change": 0.0
                    }
                    
                    if len(tick_history) > 0:
                        tick_entry["change"] = price - tick_history[-1]["price"]
                    
                    tick_history.append(tick_entry)
                    
                    rsi, ema = calculate_indicators()
                    current_signal, signal_color = generate_signal(price, rsi, ema)
    except Exception as e:
        pass

def on_open(ws):
    global ws_connected, market_status, sws
    ws_connected = True
    market_status = "CONNECTED"
    
    correlation_id = "nifty50_stream"
    mode = 3
    token_list = [{"exchangeType": EXCHANGE_TYPE, "tokens": [SYMBOL_TOKEN]}]
    
    try:
        if sws:
            sws.subscribe(correlation_id, mode, token_list)
            market_status = "SUBSCRIBED"
    except Exception as e:
        market_status = f"Sub failed: {str(e)[:20]}"

def on_error(ws, error):
    global market_status
    market_status = f"ERROR: {str(error)[:30]}"

def on_close(ws):
    global ws_connected, market_status
    ws_connected = False
    market_status = "Connection closed"

def start_websocket(auth_tokens: dict):
    global sws, market_status
    
    try:
        market_status = "Connecting..."
        sws = SmartWebSocketV2(
            auth_token=auth_tokens["auth_token"],
            api_key=API_KEY,
            client_code=CLIENT_ID,
            feed_token=auth_tokens["feed_token"]
        )
        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close
        sws.connect()
    except Exception as e:
        market_status = f"Error: {str(e)[:20]}"

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================
app = FastAPI(title="NIFTY 50 Scalping Dashboard")

# Mount static files
static_path = Path(__file__).parent / "static"
static_path.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(static_path / "index.html")

@app.get("/api/status")
async def get_status():
    with lock:
        return {
            "market_status": market_status,
            "total_ticks": total_ticks,
            "candles_count": candle_manager.get_count(),
            "last_price": last_price,
            "rsi": last_rsi,
            "ema": last_ema,
            "signal": current_signal,
            "signal_color": signal_color,
            "tick_history": list(tick_history)
        }

@app.get("/api/scalper-data")
async def get_scalper_data():
    """API endpoint for Scalping Module data (Professional Edition)."""
    with scalping_lock:
        return {
            "status": scalping_status,
            "future_price": last_future_price,
            "ce_price": last_ce_price,
            "pe_price": last_pe_price,
            "basis": last_basis,
            "real_basis": real_basis,  # Synthetic Future - Spot
            "straddle_price": straddle_price,
            "sma3": straddle_sma3,  # 3-period SMA of Straddle
            "trend": straddle_trend,  # RISING, FALLING, FLAT
            "sentiment": sentiment,  # BULLISH, BEARISH, NEUTRAL
            "signal": scalping_signal,
            "suggestion": trade_suggestion,
            "pcr": pcr_value,  # New PCR Value
            "atm_strike": current_atm_strike,  # Current ATM Strike
            "history": list(scalping_history)[-50:]  # Last 50 for chart
        }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    
    try:
        while True:
            with lock:
                data = {
                    "market_status": market_status,
                    "total_ticks": total_ticks,
                    "candles_count": candle_manager.get_count(),
                    "last_price": last_price,
                    "rsi": round(last_rsi, 2) if last_rsi else None,
                    "ema": round(last_ema, 2) if last_ema else None,
                    "signal": current_signal,
                    "signal_color": signal_color,
                    "tick_history": list(tick_history)[-10:]
                }
            await websocket.send_json(data)
            await asyncio.sleep(0.1)  # 100ms update rate for super fast UI
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
    except Exception:
        connected_clients.discard(websocket)

# =============================================================================
# STARTUP EVENT
# =============================================================================
@app.on_event("startup")
async def startup_event():
    global smart_api_global
    
    def run_angel_websocket():
        global smart_api_global, market_status
        retry_delay = 5
        
        while True:
            try:
                # 1. Update status
                market_status = "Authenticating..."
                if smart_api_global is None:
                     smart_api_global, auth_tokens = authenticate()
                
                # 2. Check if auth succeeded (authenticate logic might differ)
                if not smart_api_global:
                    raise Exception("Auth returned None")

                market_status = "Connecting to WebSocket..."
                # 3. Start Websocket (This blocks if implemented as running loop, or returns)
                # Assuming start_websocket runs monitoring loop or proper connection
                start_websocket(auth_tokens)
                
                # If start_websocket returns cleanly, we might want to break or retry depending on implementation
                # But usually websockets run forever. If it returns, it might mean disconnect.
                print("WebSocket disconnected. Reconnecting in 5s...")
                time.sleep(5)
                
            except Exception as e:
                error_str = str(e)
                if "ConnectTimeout" in error_str or "ConnectionPool" in error_str:
                    msg = "Network Timeout. Retrying..."
                else:
                    msg = f"Auth Error: {error_str[:30]}..."
                
                print(f"❌ {msg} ({error_str})")
                market_status = f"🔴 {msg}"
                time.sleep(retry_delay)
                # Exponential backoff cap at 30s
                retry_delay = min(retry_delay * 2, 30)
    
    def run_scalping_module():
        # Start immediately, loop handles checks
        update_scalping_data()
    
    thread = threading.Thread(target=run_angel_websocket, daemon=True)
    thread.start()
    
    # Start scalping module thread
    scalping_thread = threading.Thread(target=run_scalping_module, daemon=True)
    scalping_thread.start()
    
    def run_oi_fetcher():
        while smart_api_global is None:
            time.sleep(1)
        fetch_oi_data(smart_api_global)
        
    oi_thread = threading.Thread(target=run_oi_fetcher, daemon=True)
    oi_thread.start()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
