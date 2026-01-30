"""
NIFTY 50 Real-Time Scalping Dashboard - Web Server
FastAPI backend with WebSocket for real-time data streaming
"""

import asyncio
import json
import orjson # Optimized JSON library
import threading
import time
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime
import calendar
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import pandas as pd
import pyotp
from dotenv import load_dotenv
import os

import logging
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
from logger import trade_logger  # Trade Logger Integration
from news_engine import start_news_engine, latest_news_str  # News Ticker Integration
import news_engine # To access the global variable dynamically


# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s:     %(message)s')
# Silence heavy loggers
logging.getLogger("smartConnect").setLevel(logging.ERROR)
logging.getLogger("urllib3").setLevel(logging.ERROR)
logging.getLogger("requests").setLevel(logging.ERROR)

# =============================================================================
# LOAD ENVIRONMENT VARIABLES
# =============================================================================
env_path = Path(__file__).parent.parent / ".env"
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
SCALPING_POLL_INTERVAL = 0.5  # Reduced to 0.5s to ensure reliable 1Hz updates (Global Standard)

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
last_logged_signal = None  # To prevent log spam
real_basis: Optional[float] = None  # Synthetic Future - Spot
sentiment = "NEUTRAL"  # BULLISH, BEARISH, NEUTRAL
straddle_trend = "FLAT"  # RISING, FALLING, FLAT
straddle_sma3: Optional[float] = None  # 3-period SMA of straddle
current_atm_strike: Optional[int] = None  # Current ATM for frontend display
current_ce_symbol: str = ""  # Full CE symbol name (e.g., NIFTY27JAN2525050CE)
current_pe_symbol: str = ""  # Full PE symbol name (e.g., NIFTY27JAN2525050PE)
trade_suggestion = "WAIT"  # Current trade suggestion
momentum_buffer: deque = deque(maxlen=20) # V6: Velocity Buffer
last_price_for_velocity: float = 0.0 # V6: For tracking change

# Anomaly Detection Globals
raw_basis_history: deque = deque(maxlen=300)  # For Z-Score (300 ticks ~ 5 mins)
pcr_value: float = 1.0
last_pcr_update: float = time.time()  # Initialize to now (show age from server start)
is_trap = False
last_tick_timestamp: float = 0.0  # Time of last received tick (for latency)
current_latency_ms: float = 0.0 # Smoothed RTT Latency (Stable Metric)
current_latency_ms: float = 0.0 # Smoothed RTT Latency (Stable Metric)
points_per_sec: float = 0.0  # Current velocity (points/sec)
ema_trend_history: deque = deque(maxlen=20) # 3PM Filter: EMA Trend Buffer

# =============================================================================
# INDEX TOKENS & REAL-TIME DATA (NEW)
# =============================================================================
# Map to store real-time data for all tickers
ticker_data = {
    "nifty": {"price": 0.0, "change": 0.0, "p_change": 0.0, "s_price": 0.0}
}
# Map to store resolved tokens: {"99926000": "nifty", ...}
# Pre-populate with KNOWN Index Tokens for Accuracy
token_map = {
    "99926000": "nifty",       # Nifty 50
    "99926009": "banknifty",   # Bank Nifty
    "99919000": "sensex",      # Sensex
    "99926074": "midcpnifty",  # Nifty Midcap 100
    "99926017": "indiavix"     # India VIX
}

def lookup_and_subscribe_indices(smart_api):
    """
    Robustly find and subscribe to all required indices.
    """
    global token_map, ws_connected, sws
    
    # We only need to search for Smallcap or verify hardcoded ones
    targets = [
        {"key": "niftysmallcap", "queries": ["NIFTY SMALLCAP 100", "NIFTYSMLCAP100"], "exch": "NSE"}
    ]
    
    tokens_to_sub = list(token_map.keys())
    
    print("\n🔎 Verifying/Resolving Index Tokens...")
    
    # 1. Fetch Initial LTP for Hardcoded Tokens
    for token, key in token_map.items():
        try:
            exch = "BSE" if key == "sensex" else "NSE"
            symbol = key.upper() # Approx symbol for log
            ltp = fetch_ltp(smart_api, exch, symbol, token)
            if ltp:
                ticker_data[key] = {
                    "price": ltp,
                    "change": 0.0,
                    "p_change": 0.0
                }
                print(f"   ✅ {key.upper()}: Initial LTP {ltp}")
                
                # CRITICAL: Initialize global last_price for Scalping Module
                if key == "nifty":
                    global last_price
                    last_price = ltp
        except: pass

    # 2. Search for missing targets (Smallcap)
    for target in targets:
        found = False
        for query in target['queries']:
            try:
                time.sleep(0.5) # Rate limit
                results = smart_api.searchScrip(target['exch'], query)
                if results and 'data' in results:
                    for item in results['data']:
                        # strict match
                        if item['tradingsymbol'] == query or item['symboltoken'] == query:
                            token = item['symboltoken']
                            token_map[token] = target['key']
                            tokens_to_sub.append(token)
                            found = True
                            
                            # Fetch LTP
                            try:
                                ltp = fetch_ltp(smart_api, target['exch'], item['tradingsymbol'], token)
                                if ltp:
                                    ticker_data[target['key']] = {"price": ltp, "change": 0.0, "p_change": 0.0}
                                    print(f"   ✅ {target['key'].upper()}: {item['tradingsymbol']} -> {token} (LTP: {ltp})")
                            except: pass
                            break
                        
                        # Fallback
                        if query in item['tradingsymbol'] and not found:
                             token = item['symboltoken']
                             token_map[token] = target['key']
                             tokens_to_sub.append(token)
                             found = True
                             try:
                                ltp = fetch_ltp(smart_api, target['exch'], item['tradingsymbol'], token)
                                if ltp:
                                    ticker_data[target['key']] = {"price": ltp, "change": 0.0, "p_change": 0.0}
                                    print(f"   ✅ {target['key'].upper()}: {item['tradingsymbol']} -> {token} (LTP: {ltp})")
                             except: pass
                             break
            except Exception: pass
            if found: break
        
        if not found:
            print(f"   ⚠️ Could not resolve {target['key']}")

    # SUBSCRIBE
    if sws and ws_connected:
        try:
             # NSE Tokens
            nse_tokens = [t for t in tokens_to_sub if request_exchange_type(t) == 1]
            bse_tokens = [t for t in tokens_to_sub if request_exchange_type(t) == 3] 
            
            token_list = []
            if nse_tokens: token_list.append({"exchangeType": 1, "tokens": nse_tokens})
            if bse_tokens: token_list.append({"exchangeType": 3, "tokens": bse_tokens})
            
            if token_list:
                sws.subscribe("indices_stream", 3, token_list)
                print(f"📡 Subscribing to: {len(nse_tokens)} NSE, {len(bse_tokens)} BSE tokens")
            
        except Exception as e:
            print(f"Error subscribing to indices: {e}")
            
    return tokens_to_sub

# Use a set to track actively subscribed scalping tokens to avoid duplicates
active_scalping_tokens = set()

def update_scalping_subscriptions(future_tok, ce_tok, pe_tok):
    """
    Dynamically subscribe to new scalping tokens (Future, CE, PE).
    This ensures TRUE real-time data via WebSocket (Mode 3).
    """
    global active_scalping_tokens, sws, ws_connected
    
    # 1. Identify valid tokens
    current_tokens = set()
    if future_tok: current_tokens.add(future_tok)
    if ce_tok: current_tokens.add(ce_tok)
    if pe_tok: current_tokens.add(pe_tok)
    
    print(f"📡 DEBUG: Calculating new tokens. Current: {current_tokens}, Active: {active_scalping_tokens}")
    # 2. Determine NEW tokens that need subscription
    new_tokens = current_tokens - active_scalping_tokens
    
    if not new_tokens: return
    
    print(f"📡 Real-Time Socket: Subscribing to {new_tokens}")
    
    # 3. Subscribe if WebSocket is active
    if sws and ws_connected:
        try:
            # NFO Exchange Type is 2
            # Use Mode 3 (Full Quote) for reliability as Mode 1 (LTP) might be silent
            token_list = [{"exchangeType": 2, "tokens": list(new_tokens)}]
            sws.subscribe("scalping_quote", 3, token_list)
            
            # Update active set
            active_scalping_tokens.update(new_tokens)
            
            # CRITICAL: Update token_map so on_data processes these messages!
            # Map token_id -> token_id (Self-mapping for lookup)
            for t in new_tokens:
                 token_map[t] = t
                 
            print(f"✅ Subscribed (Mode 3) successfully to {len(new_tokens)} options/futures")
        except Exception as e:
            print(f"⚠️ Subscription Failed: {e}")
            # Do not update active_set so we retry next time
    else:
        print(f"⚠️ Warning: WebSocket not connected (sws={sws}, connected={ws_connected})")


def request_exchange_type(token):
    # Heuristic: BSE tokens likely stored separately or mapped?
    # For now, simplistic approach:
    # If token in map and key is sensex -> BSE (3)
    # Else NSE (1)
    key = token_map.get(token)
    if key == 'sensex': return 3
    return 1


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

def get_ema_trend(current_spot: float) -> str:
    """
    Helper for 3:00 PM Safety Filter.
    Returns 'UP', 'DOWN', or 'SIDEWAYS' based on immediate EMA trend.
    """
    global ema_trend_history
    
    if current_spot and current_spot > 0:
        ema_trend_history.append(current_spot)
    
    if len(ema_trend_history) < 5:
        return "SIDEWAYS" # Not enough data
        
    # Calculate Simple Mean (close enough to EMA for short burst) or proper EMA
    # Using Simple Mean of last 20 ticks for resilience
    avg_price = sum(ema_trend_history) / len(ema_trend_history)
    
    if current_spot > avg_price + 2:
        return "UP"
    elif current_spot < avg_price - 2:
        return "DOWN"
    else:
        return "SIDEWAYS"

# =============================================================================
# INSTRUMENT MASTER FILE CACHE (For reliable token lookup)
# =============================================================================
_instrument_cache = None
_instrument_cache_date = None

def get_nfo_instruments():
    """
    Download and cache the Angel One NFO instrument master file.
    This is more reliable than searchScrip API and avoids rate limits.
    """
    global _instrument_cache, _instrument_cache_date
    import requests
    from datetime import date
    
    today = date.today()
    
    # Return cached data if valid (same day)
    if _instrument_cache and _instrument_cache_date == today:
        return _instrument_cache
    
    print("📥 Downloading NFO instrument master file...")
    
    try:
        # Angel One provides instrument master at this URL
        url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        all_instruments = response.json()
        
        # Filter for NFO (NIFTY options and futures)
        nfo_instruments = [
            inst for inst in all_instruments 
            if inst.get('exch_seg') == 'NFO' and 'NIFTY' in inst.get('name', '').upper()
        ]
        
        print(f"✅ Downloaded {len(all_instruments)} instruments, filtered to {len(nfo_instruments)} NFO NIFTY instruments")
        
        _instrument_cache = nfo_instruments
        _instrument_cache_date = today
        
        return nfo_instruments
        
    except Exception as e:
        print(f"⚠️ Failed to download instrument master: {e}")
        return []

def search_token_via_api(smart_api, exchange, symbol):
    """
    Fallback mechanism: Retrieve token directly from Broker API 
    when Instrument Master File is unavailable.
    """
    try:
        # print(f"🔎 Searching API for {symbol}...")
        # Note: Angel One searchScrip method signature usually: searchScrip(exchange, searchscrip)
        response = smart_api.searchScrip(exchange=exchange, searchscrip=symbol)
        
        if response and response.get('status') and response.get('data'):
            for item in response['data']:
                # Strict Match on Trading Symbol
                if item.get('symbol') == symbol or item.get('tradingsymbol') == symbol:
                    # print(f"✅ API Found: {symbol} -> {item['symboltoken']}")
                    return item['symboltoken']
                    
            # Relaxation: If only one result, take it?
            if len(response['data']) == 1:
                return response['data'][0]['symboltoken']
                
    except Exception as e:
        print(f"⚠️ API Search Error for {symbol}: {e}")
    
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
    from datetime import datetime, timedelta, time as dt_time
    from concurrent.futures import ThreadPoolExecutor # For parallel API calls
    import calendar # Import strictly here
    
    try:
        scalping_status = "Fetching instrument tokens..."
        
        # Round spot to nearest 50 for ATM strike
        atm_strike = int(round(spot_price / 50) * 50)
        
        # 🟢 IST TIMEZONE FIX (UTC + 5:30)
        # Ensure we always select expiry based on INDIAN STANDARD TIME
        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        today = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff_time = dt_time(15, 30) # Market Close Check
        
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
            # SMART EXPIRY CALCULATION: Find next Thursday (weekly expiry)
            days_until_thursday = (3 - today.weekday()) % 7  # 3 = Thursday
            if days_until_thursday == 0 and ist_now.time() > cutoff_time:
                days_until_thursday = 7  # Move to next Thursday if market closed
            next_thursday = today + timedelta(days=days_until_thursday)
            
            # Format expiry for symbol construction: DDMMMYY (e.g., 05FEB26)
            expiry_str = next_thursday.strftime("%d%b%y").upper()
            tokens['expiry_date'] = next_thursday
            
            print(f"📅 CALCULATED EXPIRY: {next_thursday.strftime('%d-%b-%Y (%A)')}")
            print(f"📝 Expiry String for Symbols: {expiry_str}")
            
            # Construct exact symbol names
            ce_symbol_name = f"NIFTY{expiry_str}{atm_strike}CE"
            pe_symbol_name = f"NIFTY{expiry_str}{atm_strike}PE"
            
            # For futures, find nearest MONTHLY expiry (last Thursday of month)
            current_month = today.month
            current_year = today.year
            
            last_day = calendar.monthrange(current_year, current_month)[1]
            last_date = datetime(current_year, current_month, last_day)
            days_back = (last_date.weekday() - 3) % 7
            monthly_expiry = last_date - timedelta(days=days_back)
            
            if monthly_expiry < today or (monthly_expiry == today and ist_now.time() > cutoff_time):
                next_month = current_month + 1 if current_month < 12 else 1
                next_year = current_year if current_month < 12 else current_year + 1
                last_day = calendar.monthrange(next_year, next_month)[1]
                last_date = datetime(next_year, next_month, last_day)
                days_back = (last_date.weekday() - 3) % 7
                monthly_expiry = last_date - timedelta(days=days_back)
            
            fut_expiry_str = monthly_expiry.strftime("%d%b%y").upper()
            fut_symbol_name = f"NIFTY{fut_expiry_str}FUT"
            
            print(f"🔍 Looking for symbols:")
            print(f"   CE: {ce_symbol_name}")
            print(f"   PE: {pe_symbol_name}")
            print(f"   FUT: {fut_symbol_name}")
            
            # CRITICAL FIX: Define instruments!
            instruments = get_nfo_instruments()
            
            tokens['ce_symbol'] = ce_symbol_name
            tokens['pe_symbol'] = pe_symbol_name
            tokens['future_symbol'] = fut_symbol_name
            
            # FALLBACK LOGIC: If Master File fails OR logic fails to populate tokens
            # We use a BROAD SEARCH to discover the actual available expiries (handling holidays automatically)
            
            missing_tokens = []
            if not instruments: missing_tokens = ['future', 'ce', 'pe']
            else:
                 if not tokens['future']: missing_tokens.append('future')
                 if not tokens['ce']: missing_tokens.append('ce')
                 if not tokens['pe']: missing_tokens.append('pe')
            
            if missing_tokens:
                print(f"⚠️ Tokens missing ({missing_tokens}). Initiating BROAD API DISCOVERY...")
                
                try:
                    # Broad search for all NIFTY contracts
                    # This avoids manual date calculation errors (e.g. holidays) by seeing what actually exists
                    search_res = smart_api.searchScrip(exchange="NFO", searchscrip="NIFTY")
                    
                    if search_res and search_res.get('status') and search_res.get('data'):
                        print(f"✅ Broad Search found {len(search_res['data'])} items. Parsing for nearest expiry...")
                        
                        api_futures = []
                        api_options = []
                        
                        import re
                        
                        for item in search_res['data']:
                            sym = item['tradingsymbol']
                            # Filter junk
                            if "NXT50" in sym or "BANK" in sym or "FIN" in sym or "MID" in sym:
                                continue
                                
                            # Parse Future
                            if sym.startswith("NIFTY") and sym.endswith("FUT"):
                                # Extract date: NIFTY24FEB26FUT
                                match = re.match(r'NIFTY(\d{2}[A-Z]{3}\d{2})FUT', sym)
                                if match:
                                    d_str = match.group(1)
                                    try:
                                        d_obj = datetime.strptime(d_str, "%d%b%y")
                                        if d_obj >= today:
                                            api_futures.append({
                                                'date': d_obj,
                                                'token': item['symboltoken'],
                                                'symbol': sym,
                                                'd_str': d_str
                                            })
                                    except: pass
                                    
                            # Parse CE/PE
                            elif sym.startswith("NIFTY") and ("CE" in sym or "PE" in sym):
                                # NIFTY26FEB2625000CE
                                match = re.match(r'NIFTY(\d{2}[A-Z]{3}\d{2})(\d+)(CE|PE)', sym)
                                if match:
                                    d_str = match.group(1)
                                    strk = int(match.group(2)) # Extract strike
                                    typ = match.group(3)
                                    try:
                                        d_obj = datetime.strptime(d_str, "%d%b%y")
                                        if d_obj >= today:
                                            api_options.append({
                                                'date': d_obj,
                                                'strike': strk,
                                                'type': typ,
                                                'token': item['symboltoken'],
                                                'symbol': sym,
                                                'd_str': d_str
                                            })
                                    except: pass

                        # Logic to pick tokens
                        if api_futures:
                            # Sort by date
                            api_futures.sort(key=lambda x: x['date'])
                            # Pick nearest monthly future (usually the first one returned for FUT)
                            # Actually futures are monthly. The list will have Feb, Mar, Apr.
                            # We want the nearest one.
                            nearest_fut = api_futures[0]
                            tokens['future'] = nearest_fut['token']
                            tokens['future_symbol'] = nearest_fut['symbol']
                            print(f"✅ Discovered Future: {nearest_fut['symbol']}")
                            
                        if api_options:
                            # Sort options by date then strike
                            # Find indices nearest date
                            # We want Weekly expiry (nearest date)
                            # Get all unique dates
                            dates = sorted(list(set(o['date'] for o in api_options)))
                            if dates:
                                nearest_opt_date = dates[0]
                                tokens['expiry_date'] = nearest_opt_date
                                d_str_target = nearest_opt_date.strftime("%d%b%y").upper()
                                print(f"✅ Discovered Expiry: {d_str_target}")
                                
                                # Now find ATM CE/PE for this date
                                # We need specific ATM strike 
                                target_ce = None
                                target_pe = None
                                
                                # Exact match check
                                for opt in api_options:
                                    if opt['date'] == nearest_opt_date and opt['strike'] == atm_strike:
                                        if opt['type'] == 'CE': target_ce = opt
                                        if opt['type'] == 'PE': target_pe = opt
                                
                                if target_ce: 
                                    tokens['ce'] = target_ce['token']
                                    tokens['ce_symbol'] = target_ce['symbol']
                                    print(f"✅ Discovered CE: {target_ce['symbol']}")
                                    
                                if target_pe:
                                    tokens['pe'] = target_pe['token']
                                    tokens['pe_symbol'] = target_pe['symbol']
                                    print(f"✅ Discovered PE: {target_pe['symbol']}")
                                    
                    else:
                        print("❌ Broad API Search returned no data.")
                        
                except Exception as e:
                    print(f"❌ API Discovery Error: {e}")
                
                return tokens
            
            # Fallthrough to Master File Search logic if Broad Search logic didn't return
            # (Or if Broad Search failed and we caught exception)
            import re
            
            nifty50_options = []
            for inst in instruments:
                symbol = inst.get('symbol') or inst.get('tradingsymbol', '')
                
                # Match NIFTY50 weekly options: NIFTY{DDMMMYY}{STRIKE}CE/PE
                # Exclude BANKNIFTY, FINNIFTY, MIDCPNIFTY, NIFTYNXT50
                if symbol.startswith('NIFTY') and (symbol.endswith('CE') or symbol.endswith('PE')):
                    if 'BANK' not in symbol and 'FIN' not in symbol and 'MIDCP' not in symbol and 'NXT50' not in symbol:
                        # Extract expiry date: NIFTY{DDMMMYY}...
                        match = re.match(r'NIFTY(\d{2}[A-Z]{3}\d{2})', symbol)
                        if match:
                            expiry_str_found = match.group(1)
                            try:
                                expiry_date = datetime.strptime(expiry_str_found, "%d%b%y")
                                if expiry_date >= today:  # Only future expiries
                                    nifty50_options.append({
                                        'symbol': symbol,
                                        'token': inst.get('token') or inst.get('symboltoken'),
                                        'expiry': expiry_date,
                                        'expiry_str': expiry_str_found
                                    })
                            except:
                                pass
            
            # Also find futures
            nifty50_futures = []
            for inst in instruments:
                symbol = inst.get('symbol') or inst.get('tradingsymbol', '')
                if symbol.startswith('NIFTY') and symbol.endswith('FUT') and 'BANK' not in symbol:
                    match = re.match(r'NIFTY(\d{2}[A-Z]{3}\d{2})FUT', symbol)
                    if match:
                        expiry_str_found = match.group(1)
                        try:
                            expiry_date = datetime.strptime(expiry_str_found, "%d%b%y")
                            if expiry_date >= today:
                                nifty50_futures.append({
                                    'symbol': symbol,
                                    'token': inst.get('token') or inst.get('symboltoken'),
                                    'expiry': expiry_date,
                                    'expiry_str': expiry_str_found
                                })
                        except:
                            pass
            
            print(f"📋 Found {len(nifty50_options)} NIFTY50 options, {len(nifty50_futures)} futures with future expiries")
            
            if not nifty50_options:
                print("⚠️ No NIFTY50 options found in instrument master")
                return tokens
            
            # Step 2: Find unique expiry dates and select nearest
            unique_expiries = sorted(set(opt['expiry'] for opt in nifty50_options))
            if unique_expiries:
                nearest_expiry = unique_expiries[0]
                nearest_expiry_str = nearest_expiry.strftime("%d%b%y").upper()
                tokens['expiry_date'] = nearest_expiry
                print(f"✅ NEAREST AVAILABLE EXPIRY: {nearest_expiry.strftime('%d-%b-%Y (%A)')}")
                
                # Update expected symbol names with actual expiry
                ce_symbol_name = f"NIFTY{nearest_expiry_str}{atm_strike}CE"
                pe_symbol_name = f"NIFTY{nearest_expiry_str}{atm_strike}PE"
                print(f"🔍 Updated search targets:")
                print(f"   CE: {ce_symbol_name}")
                print(f"   PE: {pe_symbol_name}")
            
            # Step 3: Find ATM options with nearest expiry
            for opt in nifty50_options:
                if opt['expiry'] == nearest_expiry:
                    if opt['symbol'] == ce_symbol_name and not tokens['ce']:
                        tokens['ce'] = opt['token']
                        tokens['ce_symbol'] = opt['symbol']
                        print(f"✅ ATM CE: {opt['symbol']} -> {opt['token']}")
                    elif opt['symbol'] == pe_symbol_name and not tokens['pe']:
                        tokens['pe'] = opt['token']
                        tokens['pe_symbol'] = opt['symbol']
                        print(f"✅ ATM PE: {opt['symbol']} -> {opt['token']}")
                    
                    if tokens['ce'] and tokens['pe']:
                        break
            
            # Step 4: Find nearest future
            if nifty50_futures:
                nearest_future = min(nifty50_futures, key=lambda x: x['expiry'])
                tokens['future'] = nearest_future['token']
                tokens['future_symbol'] = nearest_future['symbol']
                print(f"✅ Future: {nearest_future['symbol']} -> {nearest_future['token']}")
            
            # Debug: If options still not found, show available strikes for nearest expiry
            if not (tokens['ce'] and tokens['pe']):
                print(f"⚠️ ATM tokens not found for strike {atm_strike}")
                available_strikes = set()
                for opt in nifty50_options:
                    if opt['expiry'] == nearest_expiry:
                        match = re.match(r'NIFTY\d{2}[A-Z]{3}\d{2}(\d+)', opt['symbol'])
                        if match:
                            available_strikes.add(int(match.group(1)))
                
                if available_strikes:
                    sorted_strikes = sorted(available_strikes)
                    # Find closest available strike
                    closest = min(sorted_strikes, key=lambda x: abs(x - atm_strike))
                    print(f"📋 Closest available strike: {closest} (ATM was {atm_strike})")
                    
                    # Try with closest strike
                    for opt in nifty50_options:
                        if opt['expiry'] == nearest_expiry:
                            if f"{closest}CE" in opt['symbol'] and not tokens['ce']:
                                tokens['ce'] = opt['token']
                                tokens['ce_symbol'] = opt['symbol']
                                tokens['atm_strike'] = closest
                                print(f"✅ Closest CE: {opt['symbol']} -> {opt['token']}")
                            elif f"{closest}PE" in opt['symbol'] and not tokens['pe']:
                                tokens['pe'] = opt['token']
                                tokens['pe_symbol'] = opt['symbol']
                                tokens['atm_strike'] = closest
                                print(f"✅ Closest PE: {opt['symbol']} -> {opt['token']}")
                
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
        # time.sleep(0.2)  # Removed for parallel optimization
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
    Fetches REAL-TIME OI for ATM CE and PE tokens to calculate PCR.
    Runs every 30 seconds to save bandwidth.
    """
    global pcr_value, is_trap, current_ce_symbol, current_pe_symbol, atm_ce_token, atm_pe_token, last_pcr_update
    print("🛡️ OI Trap Filter thread started (Live PCR)")
    
    while True:
        try:
            if 'current_ce_symbol' in globals() and current_ce_symbol and \
               'atm_ce_token' in globals() and atm_ce_token and \
               'current_pe_symbol' in globals() and current_pe_symbol and \
               'atm_pe_token' in globals() and atm_pe_token and \
               smart_api:
                
                try:
                    # Use getMarketData with mode "FULL" to get OI
                    # Signature: getMarketData(mode, exchangeTokens)
                    # mode: "FULL" | "OHLC" | "LTP"
                    # exchangeTokens: {"NFO": ["token1", "token2"]}
                    
                    exchange_tokens = {"NFO": [atm_ce_token, atm_pe_token]}
                    market_data = smart_api.getMarketData("FULL", exchange_tokens)
                    
                    ce_oi = 0
                    pe_oi = 0
                    
                    if market_data and market_data.get('status') and market_data.get('data'):
                        fetched_list = market_data['data'].get('fetched', [])
                        for item in fetched_list:
                            token = str(item.get('symbolToken', ''))
                            # OI key could be 'opnInterest', 'oi', etc.
                            oi_val = 0
                            for key in ['opnInterest', 'oi', 'openInterest']:
                                if key in item:
                                    oi_val = float(str(item[key]).replace(',', ''))
                                    break
                            
                            if token == str(atm_ce_token):
                                ce_oi = oi_val
                            elif token == str(atm_pe_token):
                                pe_oi = oi_val
                    
                    if ce_oi > 0:
                        raw_pcr = pe_oi / ce_oi
                        pcr_value = round(raw_pcr, 2)
                        last_pcr_update = time.time()  # Track update timestamp
                        
                        is_trap = False 
                        if pcr_value > 2.0: is_trap = True
                        elif pcr_value < 0.5: is_trap = True
                             
                        print(f"📊 PCR UPDATED: {pcr_value} (CE_OI: {ce_oi}, PE_OI: {pe_oi})")
                    else:
                        # Log raw response for debugging
                        print(f"⚠️ Zero CE OI. Raw response: {market_data}")
                    

                        
                except Exception as api_err:
                    print(f"⚠️ OI API Error: {api_err}")
                    if "getQuote" in str(api_err):
                         # List all methods to find the right one
                         methods = [m for m in dir(smart_api) if not m.startswith('_')]
                         print(f"🔍 AVAILABLE METHODS: {methods}")
            else:
               pass
            
            time.sleep(10) # Poll every 10s
            
        except Exception as e:
            print(f"⚠️ OI Fetch error: {e}")
            time.sleep(10)

def update_scalping_data():
    """
    Background thread to poll Future/Options prices and calculate Basis/Straddle.
    """
    global future_token, atm_ce_token, atm_pe_token
    global last_future_price, last_ce_price, last_pe_price
    global last_basis, straddle_price, scalping_signal, scalping_status
    global current_atm_strike, real_basis, sentiment, straddle_trend, straddle_sma3, trade_suggestion
    global is_trap, raw_basis_history, pcr_value, smart_api_global, market_status
    global momentum_buffer, last_price_for_velocity # V6 Fix: Added missing globals
    global current_ce_symbol, current_pe_symbol  # Full symbol names for UI
    global last_tick_timestamp, points_per_sec, current_latency_ms # V7: Health Checks
    global last_logged_signal # Prevent log spam
    global active_scalping_tokens, current_expiry # CRITICAL FIX: Ensure scoping
    
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
    future_token = None
    atm_ce_token = None
    atm_pe_token = None
    
    try:
        tokens = get_option_tokens(smart_api_global, last_price)
        
        if tokens:
            future_token = tokens.get("future") or tokens.get("future_token")
            atm_ce_token = tokens.get("ce") or tokens.get("ce_token")
            atm_pe_token = tokens.get("pe") or tokens.get("pe_token")
            
            # DEBUG: Explicitly check tokens
            if not future_token and not atm_ce_token:
                 print(f"⚠️ DEBUG: Tokens are None! Futures: {future_token}, CE: {atm_ce_token}")
        else:
            scalping_status = "Token Discovery Failed"
            print("⚠️ Initial token discovery failed, starting loop anyway...")
            
    except Exception as e:
        print(f"Token fetch error: {e}")
        time.sleep(2)
        return update_scalping_data() # Retry setup
    future_symbol = tokens.get('future_symbol', '')
    ce_symbol = tokens.get('ce_symbol', '')
    pe_symbol = tokens.get('pe_symbol', '')
    current_atm_strike = tokens.get('atm_strike', 0)
    current_ce_symbol = ce_symbol  # Set global for UI
    current_pe_symbol = pe_symbol  # Set global for UI
    current_expiry = tokens.get('expiry_date')
    last_token_refresh_date = datetime.utcnow().date() # Track refresh date for rollover
    
    # DYNAMIC SUBSCRIPTION (V11): Subscribe to NFO tokens for Real-Time WebSocket Data!
    update_scalping_subscriptions(future_token, atm_ce_token, atm_pe_token)
    
    print(f"📈 Scalping ready: ATM={current_atm_strike}, Expiry={current_expiry}")
    
    last_straddle_prices = deque(maxlen=5)  # For trend detection
    raw_basis_history = deque(maxlen=20) # For Z-Score calculation
    last_straddle_price = None # CRITICAL FIX: Initialize for forward fill
    atm_shift_count = 0
    poll_count = 0
    
    # OPTIMIZATION: Persistent Thread Pool
    executor = ThreadPoolExecutor(max_workers=3)
    
    while True:
        try:
            # CRITICAL: Record loop start time for precise 1Hz timing
            loop_start_time = time.time()
            
            # Check Auth Status dynamically
            if smart_api_global is None:
                scalping_status = market_status
                time.sleep(1)
                continue
            
            
            spot = last_price
            if spot is None:
                continue
            
            # DYNAMIC ATM TRACKING: Check on EVERY tick
            # Standard rounding: int((x / step) + 0.5) * step handles .5 consistently up
            new_atm = int((spot / 50) + 0.5) * 50
            
            should_switch = False
            
            if current_atm_strike is None or current_atm_strike == 0:
                 should_switch = True
            elif new_atm != current_atm_strike:
                # Hysteresis Check:
                # Reduced buffer to match broker standards (more responsive).
                # Midpoint is 25 pts. Buffer is 5 pts. Switch at >= 30 pts diff.
                dist = abs(spot - current_atm_strike)
                if dist >= 30:
                    should_switch = True
            
            # DATE ROLLOVER CHECK (Fix for Overnight Server Run)
            # If date changed since last token fetch, force refresh to pick next expiry
            current_date = datetime.utcnow().date()
            if current_date > last_token_refresh_date:
                 print("\n📅 DATE CHANGED! Refreshing tokens for new expiry...")
                 should_switch = True
                 last_token_refresh_date = current_date

            # Trigger refresh when ATM changes based on Hysteresis OR Date Change
            if should_switch:
                current_atm = new_atm
                # Only increment count if it's an ATM shift, not just date refresh
                if new_atm != current_atm_strike: 
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
                current_expiry = tokens.get('expiry_date') # Update expiry global
                current_atm = new_atm
                
                # CRITICAL: Update globals for API responses
                current_ce_symbol = ce_symbol
                current_pe_symbol = pe_symbol
                
                # DYNAMIC SUBSCRIPTION (V11): Subscribe to new ATM tokens
                update_scalping_subscriptions(future_token, atm_ce_token, atm_pe_token)
                
                # Clear straddle history on ATM change
                if new_atm != current_atm_strike:
                    last_straddle_prices.clear()
                
                print(f"✅ Subscribed to new ATM: CE={ce_symbol}, PE={pe_symbol}, Expiry={current_expiry}")
            else:
                current_atm = current_atm_strike
            
            # HYBRID DATA FETCHING (V10 Optimization)
            # 1. Check WebSocket Cache (0ms Latency) - if available
            # 2. Parallel Polling (~200ms Latency) - Fetch ALL missing tokens concurrently
            
            fetch_start_time = time.time() # Measure RTT
            
            fut_ltp = ticker_data.get(future_token, {}).get('price') if future_token else None
            ce_ltp = ticker_data.get(atm_ce_token, {}).get('price') if atm_ce_token else None
            pe_ltp = ticker_data.get(atm_pe_token, {}).get('price') if atm_pe_token else None
            
            # Identify which tokens need fetching (not in WS cache)
            to_fetch = []
            if not fut_ltp and future_token: to_fetch.append(('fut', future_symbol, future_token))
            if not ce_ltp and atm_ce_token: to_fetch.append(('ce', ce_symbol, atm_ce_token))
            if not pe_ltp and atm_pe_token: to_fetch.append(('pe', pe_symbol, atm_pe_token))

            if to_fetch:
                # OPTIMIZATION: Parallel Fetch (Global Standard)
                # Fetch all missing tokens in parallel using persistent executor
                futures_map = {
                    item[0]: executor.submit(fetch_ltp, smart_api_global, "NFO", item[1], item[2]) 
                    for item in to_fetch
                }
                
                # Wait for all to complete (or timeout handled by fetch_ltp)
                for key, future in futures_map.items():
                    try:
                        result = future.result()
                        if result:
                            if key == 'fut':
                                fut_ltp = result
                                last_future_price = result
                            elif key == 'ce':
                                ce_ltp = result
                                last_ce_price = result
                            elif key == 'pe':
                                pe_ltp = result
                                last_pe_price = result
                    except Exception as e:
                        print(f"⚠️ Parallel fetch error for {key}: {e}")
            
            # CRITICAL FIX: Ensure Global Variables are updated from Cache/Poll
            if fut_ltp: last_future_price = fut_ltp
            if ce_ltp: last_ce_price = ce_ltp
            if pe_ltp: last_pe_price = pe_ltp
                            
            # FORWARD FILL: Ensure we always have values for calculation
            # If we didn't fetch it this tick, use the last known value
            if not fut_ltp and last_future_price: fut_ltp = last_future_price
            if not ce_ltp and last_ce_price: ce_ltp = last_ce_price
            if not pe_ltp and last_pe_price: pe_ltp = last_pe_price
            
            # Update RTT Latency (Updates every second)
            fetch_end_time = time.time()
            # Update RTT Latency (Updates every second)
            fetch_end_time = time.time()
            # Calculate RTT in MS
            rtt_ms = (fetch_end_time - fetch_start_time) * 1000
            
            # Smooth the latency (EMA)
            if 'current_latency_ms' not in globals() or current_latency_ms == 0:
                 current_latency_ms = rtt_ms
            else:
                 current_latency_ms = (current_latency_ms * 0.7) + (rtt_ms * 0.3)
                 
            poll_count += 1
            if poll_count % 10 == 1:  # Log every 10th poll
                # Format symbols for log: Strip "NIFTY" to keep it concise but readable
                c_lbl = ce_symbol.replace('NIFTY', '') if ce_symbol else '--'
                p_lbl = pe_symbol.replace('NIFTY', '') if pe_symbol else '--'
                source = "WS-CACHE" if not to_fetch else f"NETWORK({len(to_fetch)})"
                print(f"📊 Poll #{poll_count} [{source}]: ATM={current_atm} [{c_lbl}|{p_lbl}], FUT={fut_ltp}, CE={ce_ltp}, PE={pe_ltp}, Lat={rtt_ms:.1f}ms")

            if to_fetch and poll_count % 5 == 0:
                 print(f"⚠️ MISSING IN CACHE: {to_fetch}")

            # ============================================================
            # V6 VELOCITY ENGINE (Momentum Calculation)
            # ============================================================
            current_velocity = 0.0
            if spot and last_price_for_velocity > 0:
                 change = spot - last_price_for_velocity
                 momentum_buffer.append(change)
                 if len(momentum_buffer) > 0:
                     current_velocity = sum(momentum_buffer) / len(momentum_buffer)
            
            last_price_for_velocity = spot if spot else 0.0 # Update for next tick

            
            with scalping_lock:
                last_future_price = fut_ltp
                last_ce_price = ce_ltp
                last_pe_price = pe_ltp
                current_atm_strike = current_atm
                
                # Health Checks (V7)
                last_tick_timestamp = time.time()
                if 'current_velocity' in locals():
                    points_per_sec = round(current_velocity, 2)
                
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
                # Calculate Straddle Price (Synthetic Future)
                # Forward Fill Logic: If data missing, use last known to prevent Graph Lag
                straddle_price = None
                straddle_sma3 = None
                straddle_trend = "FLAT"

                if ce_ltp and pe_ltp:
                    straddle_price = round((ce_ltp + pe_ltp) / 2, 2)  # Averaging Price (intentional)
                    last_straddle_price = straddle_price
                elif last_straddle_price is not None:
                    straddle_price = last_straddle_price
                
                # Update moving averages
                if straddle_price is not None:
                    last_straddle_prices.append(straddle_price) # Append to deque for SMA calculation
                    if len(last_straddle_prices) >= 3:
                        straddle_sma3 = round(sum(list(last_straddle_prices)[-3:]) / 3, 2)
                
                # Determine Trend
                if straddle_sma3 is not None and straddle_price is not None:
                    if straddle_price > straddle_sma3:
                        straddle_trend = "RISING"
                    elif straddle_price < straddle_sma3:
                        straddle_trend = "FALLING"
                    else:
                        straddle_trend = "FLAT"
                else:
                    straddle_sma3 = None
                    straddle_trend = "FLAT"
                
                # ============================================================
                # V6 UNIFIED SIGNAL LOGIC (Velocity + PCR + Basis)
                # ============================================================
                
                # DEFAULT: WAIT
                scalping_signal = "WAIT"
                trade_suggestion = "Waiting for Setup..."
                is_trap = False

                # 1. VELOCITY CHECK (Primary Driver)
                # Max physics drift was 0.8, so threshold 0.4 is robust.
                
                # BUY CALL LOGIC
                if current_velocity > 0.4:
                     if pcr_value >= 1.0: # Confirmed Bullish Data
                          if real_basis > -50: # Avoid deep discounts (extreme fear)
                               scalping_signal = "BUY CALL"
                               trade_suggestion = f"🚀 MOMENTUM UP ({current_velocity:.2f}) - BUY CE"
                          else:
                               scalping_signal = "WAIT"
                               trade_suggestion = "⚠️ Price Rising but Basis Crashed (Trap?)"
                     
                     # --- FILTER: PCR TRAP (Calibrated Squeeze Override V7) ---
                     # REPAIR: Velocity threshold lowered to 0.4 based on actual log data.
                     # Logic: Block Bullish trades if PCR is low (Bearish OI).
                     # EXCEPTION: If Sentiment > 5.0 (Panic Buying) AND Velocity > 0.4 (Real Momentum), 
                     # we assume a Short Squeeze and OVERRIDE the trap.
                     elif pcr_value < 0.6:
                          is_short_squeeze = (sentiment_score > 5.0) and (current_velocity > 0.4)
                          
                          if is_short_squeeze:
                               # OVERRIDE: Squeeze detected. Ignore PCR.
                               scalping_signal = "BUY CALL"
                               is_trap = False
                               trade_suggestion = f"🚀 SHORT SQUEEZE (Sent {sentiment_score:.1f} + Vel {current_velocity:.2f})"
                          else:
                               # NORMAL: Block due to Bearish OI
                               scalping_signal = "TRAP"
                               is_trap = True
                               trade_suggestion = f"⚠️ BULL TRAP! Bearish OI (PCR {pcr_value:.2f})\n📈 Price Rising but Smart Money SELLING"
                     
                     else:
                          # PCR between 0.6 and 1.0 (Neutral Zone) - Treat as Trap
                          scalping_signal = "TRAP"
                          is_trap = True
                          trade_suggestion = f"⚠️ Weak OI Support (PCR={pcr_value:.2f})"
                          
                          
                # BUY PUT LOGIC
                elif current_velocity < -0.4:
                     if pcr_value <= 1.0: # Confirmed Bearish Data
                          scalping_signal = "BUY PUT"
                          trade_suggestion = f"🩸 MOMENTUM DOWN ({current_velocity:.2f}) - BUY PE"
                     else:
                          # Drop but High PCR = Divergence (Dip Buy?)
                          scalping_signal = "TRAP"
                          is_trap = True
                          trade_suggestion = f"⚠️ BEAR TRAP! PCR={pcr_value:.2f} (HIGH)\n📉 Price Falling but Bullish OI\n🎯 Smart Money BUYING"
                
                # SIDEWAYS
                # SIDEWAYS
                elif abs(current_velocity) < 0.2:
                     trade_suggestion = "⚪ SIDEWAYS - Scalping Zone"
                     
                # --- FINAL CHECK: 3:00 PM TREND LOCK (Active ONLY after 14:55) ---
                # Purpose: At 3:00 PM, Short Covering often causes Basis to drop while Price rises.
                # We must trust the EMA Price Trend over the Basis during this specific time.
                
                now = datetime.now()
                # Check if time is past 2:55 PM (14:55)
                if now.hour >= 15 or (now.hour == 14 and now.minute >= 55):
                    market_trend = get_ema_trend(spot)
                    
                    # LOGIC PATCH V7: STRICT 3PM SAFETY (Block SIDEWAYS too)

                    # Rule 1: Never Short a Rising OR Sideways Market at 3 PM
                    # (Even if Basis says Sell, if Price > EMA or Flat, we WAIT)
                    if scalping_signal == "BUY PUT" and market_trend in ["UP", "SIDEWAYS"]:
                        scalping_signal = "WAIT"
                        is_trap = True
                        trade_suggestion = f"⚠️ 3PM SAFETY: Price Trend is {market_trend}\nBlocking Bearish Signal (Need DOWN)"
                        
                    # Rule 2: Never Buy a Falling OR Sideways Market at 3 PM
                    elif scalping_signal == "BUY CALL" and market_trend in ["DOWN", "SIDEWAYS"]:
                        scalping_signal = "WAIT"
                        is_trap = True
                        trade_suggestion = f"⚠️ 3PM SAFETY: Price Trend is {market_trend}\nBlocking Bullish Signal (Need UP)"
                
                # Determine status
                # Keep LIVE if we have current OR cached data (Safe check for None)
                # Check straddle price since that's what's displayed in the chart
                has_cached_data = ((last_future_price or 0) > 0) or ((last_ce_price or 0) > 0) or ((last_straddle_price or 0) > 0)
                if fut_ltp or ce_ltp or pe_ltp or has_cached_data:
                    scalping_status = "LIVE"
                elif future_token or atm_ce_token or atm_pe_token:
                    scalping_status = "Tokens found, awaiting data..."
                else:
                    scalping_status = "No tokens available"
                
                # LOG VALID TRADES (Fire-and-Forget)
                # LOG VALID TRADES (Fire-and-Forget)
                # LOG VALID TRADES (State Change Only)
                # Only log if the signal is diff from last logged state AND it's a trade signal
                if scalping_signal != last_logged_signal:
                    if scalping_signal not in ["WAIT", "NEUTRAL"]:
                        trade_logger.log_trade(
                            spot=spot,
                            basis=real_basis,
                            pcr=pcr_value if pcr_value else 0.0,
                            signal=scalping_signal,
                            trap_reason=trade_suggestion,
                            ce_symbol=current_ce_symbol,
                            pe_symbol=current_pe_symbol,
                            ce_price=ce_ltp,
                            pe_price=pe_ltp
                        )
                        last_logged_signal = scalping_signal
                    elif scalping_signal == "WAIT":
                         # Reset logic if needed, or just track WAIT so next BUY triggers log
                         last_logged_signal = scalping_signal
                
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
            
        # PRECISE 1Hz TIMING: Compensate for variable API/processing time
        # Target: Exactly 1 second between loop starts
        elapsed = time.time() - loop_start_time
        sleep_time = max(0.1, 1.0 - elapsed)  # Minimum 0.1s, target 1.0s interval
        time.sleep(sleep_time)


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
def on_data(ws, message):
    global current_signal, signal_color, last_price, total_ticks, market_status
    global ticker_data, token_map
    
    try:
        # Handle Mode 3 (List of dicts) vs Mode 1 (Single Dict)
        ticks = [message] if isinstance(message, dict) else message
        if not isinstance(ticks, list): return

        current_time = datetime.now()

        for tick in ticks:
            if not isinstance(tick, dict): continue
            
            token = tick.get("token")
            ltp = tick.get("last_traded_price")
            
            if ltp is None: continue
            price = ltp / 100.0
            
            # DEBUG: Trace scalping tokens
            if token in active_scalping_tokens:
                 print(f"📥 DEBUG: Data received for SCALPING token: {token} | Price: {price}")

            with lock:
                # 1. Identify which ticker this is
                key = token_map.get(token)
                if not key: continue
                
                # 2. Update Context Specific Logic
                if key == "nifty": # Primary Context
                    total_ticks += 1
                    last_price = price
                    market_status = "LIVE"
                    
                    candle_manager.update(price, current_time)
                    
                    tick_entry = {
                        "time": current_time.strftime("%I:%M:%S %p"),
                        "price": price,
                        "change": 0.0
                    }
                    if len(tick_history) > 0:
                        tick_entry["change"] = price - tick_history[-1]["price"]
                        
                    tick_history.append(tick_entry)
                    
                    rsi, ema = calculate_indicators()
                # 3. Update SCALPING Global Variables (Critical for UI)
                # Map token back to internal keys (fut, ce, pe)
                # This ensures the API endpoint serves live data from the socket
                global last_future_price, last_ce_price, last_pe_price
                global future_token, atm_ce_token, atm_pe_token # CRITICAL FIX: Explicit Scope
                
                # Use GLOBAL token IDs (populated by update_scalping_data thread)
                # Enforce STRING comparison to avoid type mismatches
                str_token = str(token)
                
                if str_token == str(future_token):
                    last_future_price = price
                    print(f"✅ DEBUG: Global FUTURE updated: {price}")
                elif str_token == str(atm_ce_token):
                    last_ce_price = price
                    print(f"✅ DEBUG: Global CE updated: {price}")
                elif str_token == str(atm_pe_token):
                    last_pe_price = price
                    print(f"✅ DEBUG: Global PE updated: {price}")
                
                # Update Ticker Data Store
                ticker_data[str_token] = {
                    "price": price,
                    # ...
                }
                # 3. Update Ticker Data Store
                # Calculate change (approximate vs close or previous tick if no close)
                # For real close, we rely on API "close_price" if available, else 0
                close_price = tick.get("close_price", 0) / 100.0
                
                change = 0.0
                p_change = 0.0
                
                if close_price > 0:
                    change = price - close_price
                    p_change = (change / close_price) * 100
                
                ticker_data[key] = {
                    "price": price,
                    "change": change,
                    "p_change": p_change
                }

    except Exception as e:
        # print(f"Processing Error: {e}")
        pass

# =============================================================================
# FASTAPI APPLICATION
# =============================================================================
def on_open(ws):
    global ws_connected, market_status, sws, token_map
    ws_connected = True
    market_status = "CONNECTED"
    
    correlation_id = "indices_stream"
    mode = 3 # Full mode
    
    # Collect all tokens to subscribe
    # Group by exchange type
    nse_tokens = [t for t in token_map.keys() if request_exchange_type(t) == 1]
    bse_tokens = [t for t in token_map.keys() if request_exchange_type(t) == 3]
    
    token_list = []
    if nse_tokens:
        token_list.append({"exchangeType": 1, "tokens": nse_tokens})
    if bse_tokens:
        token_list.append({"exchangeType": 3, "tokens": bse_tokens})
        
    print(f"📡 Subscribing to: {len(nse_tokens)} NSE, {len(bse_tokens)} BSE tokens")
    
    try:
        if sws and token_list:
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
            "pcr_age": int(time.time() - last_pcr_update) if last_pcr_update > 0 else -1,  # Staleness in seconds
            "atm_strike": current_atm_strike,  # Current ATM Strike
            "ce_symbol": current_ce_symbol,  # Full CE Symbol Name
            "pe_symbol": current_pe_symbol,  # Full PE Symbol Name
            "latency_ms": int(current_latency_ms), # RTT Latency (Smoothed)
            "velocity": points_per_sec, # Velocity in points/sec
            "history": list(scalping_history)[-50:]
        }


@app.get("/api/logs")
async def get_trade_logs(limit: int = 100, date: Optional[str] = None):
    """
    Fetch recent trade logs from Supabase.
    Supports filtering by date (YYYY-MM-DD).
    CRITICAL: Runs in a separate thread to prevent blocking the WebSocket loop.
    """
    try:
        if not trade_logger.is_active or not trade_logger.supabase:
            return {"error": "Logger inactive or Supabase not connected"}

        # Run blocking Supabase query in a thread
        def fetch_query():
            query = trade_logger.supabase.table('trade_logs') \
                .select("*") \
                .order('timestamp', desc=True) \
                .limit(limit)
            
            if date:
                # Filter by specific date (whole day)
                # Assumes timestamp column is compatible with ISO strings
                start_ts = f"{date}T00:00:00"
                end_ts = f"{date}T23:59:59"
                query = query.gte('timestamp', start_ts).lte('timestamp', end_ts)
            
            return query.execute()

        response = await asyncio.to_thread(fetch_query)
        return response.data
    except Exception as e:
        print(f"❌ Error fetching logs: {e}")
        return {"error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.add(websocket)
    
    try:
        while True:
            with lock:
                # Get scalping data for context
                scalping_info = {}
                with scalping_lock:
                    scalping_info = {
                        "pcr": pcr_value,
                        "sentiment": sentiment,
                         "trend": straddle_trend
                    }

                # Construct payload using REAL-TIME ticker_data
                # Fallbacks strictly for 'nifty' if not yet populated
                nifty_data = ticker_data.get("nifty", {"price": 0.0, "change": 0.0, "p_change": 0.0})
                
                with scalping_lock:
                    full_scalping_data = {
                        "status": scalping_status,
                        "future_price": last_future_price,
                        "ce_price": last_ce_price,
                        "pe_price": last_pe_price,
                        "straddle_price": straddle_price,
                        "basis": round(last_basis, 2) if last_basis else 0.0,
                        "real_basis": round(real_basis, 2) if real_basis else 0.0,
                        "sentiment": sentiment,
                        "trend": straddle_trend,
                        "pcr": pcr_value,
                        "pcr_age": int(time.time() - last_pcr_update) if last_pcr_update > 0 else -1,  # Staleness in seconds
                        "atm_strike": current_atm_strike, # Added for UI Labels
                        "ce_symbol": current_ce_symbol,   # Added for UI Labels
                        "pe_symbol": current_pe_symbol,   # Added for UI Labels
                        "signal": scalping_signal if 'scalping_signal' in globals() else "WAIT",
                        "suggestion": trade_suggestion if 'trade_suggestion' in globals() else "Initializing...",
                        "latency_ms": int(current_latency_ms),
                        "velocity": points_per_sec, 
                        "history": list(scalping_history)[-50:]
                    }

                    # DEBUG PAYLOAD
                    if last_future_price or last_ce_price:
                         print(f"📤 WS SENDING: FUT={last_future_price}, CE={last_ce_price}, PE={last_pe_price}")
                    else:
                         print(f"⚠️ WS SENDING EMPTY: FUT={last_future_price}")

                data = {
                    "market_status": market_status,
                    "total_ticks": total_ticks,
                    "candles_count": candle_manager.get_count(),
                    "last_price": last_price, # Main Nifty Price
                    "rsi": round(last_rsi, 2) if last_rsi else None,
                    "ema": round(last_ema, 2) if last_ema else None,
                    "signal": current_signal,
                    "signal_color": signal_color,
                    # SCALPING DATA (Sync with Indices)
                    "scalping": full_scalping_data,
                    
                    "tick_history": list(tick_history)[-10:],
                    
                    # REAL TIME TICKERS
                    "tickers": {
                        k: ticker_data.get(k, {"price": 0.0, "change": 0.0, "p_change": 0.0}) 
                        for k in ["nifty", "sensex", "banknifty", "midcpnifty", "niftysmallcap", "indiavix"]
                    },
                    # vvv NEWS ENGINE INTEGRATION vvv
                    "news": news_engine.latest_news_str
                    # ^^^ NEWS ENGINE INTEGRATION ^^^
                }
            # OPTIMIZATION: Use orjson for faster serialization
            # await websocket.send_json(data)
            # FIX: Decode bytes to utf-8 string to send as TEXT frame (Frontend compatibility)
            await websocket.send_text(orjson.dumps(data).decode('utf-8'))
            await asyncio.sleep(0.05)  # 50ms update (20Hz) - GLOBAL STANDARD
    except WebSocketDisconnect:
        connected_clients.discard(websocket)
    except Exception:
        connected_clients.discard(websocket)

def on_open(ws):
    global ws_connected, market_status, sws, token_map
    ws_connected = True
    market_status = "CONNECTED"
    
    correlation_id = "indices_stream"
    mode = 3 # Full mode
    
    # Collect all tokens to subscribe
    # Group by exchange type
    nse_tokens = [t for t in token_map.keys() if request_exchange_type(t) == 1]
    bse_tokens = [t for t in token_map.keys() if request_exchange_type(t) == 3]
    
    token_list = []
    if nse_tokens:
        token_list.append({"exchangeType": 1, "tokens": nse_tokens})
    if bse_tokens:
        token_list.append({"exchangeType": 3, "tokens": bse_tokens})
        
    print(f"📡 Subscribing to: {len(nse_tokens)} NSE, {len(bse_tokens)} BSE tokens")
    
    try:
        if sws and token_list:
            sws.subscribe(correlation_id, mode, token_list)
            market_status = "SUBSCRIBED"
    except Exception as e:
        market_status = f"Sub failed: {str(e)[:20]}"

# ... (on_error, on_close unchanged) ...

# UPDATE STARTUP
@app.on_event("startup")
async def startup_event():
    # Start News Engine (Background Daemon)
    start_news_engine()
    
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
                
                # 2. Check if auth succeeded
                if not smart_api_global:
                    raise Exception("Auth returned None")
                    
                # 3. Resolve Indices Tokens (NEW)
                market_status = "Resolving Indices..."
                lookup_and_subscribe_indices(smart_api_global)

                market_status = "Connecting to WebSocket..."
                start_websocket(auth_tokens)
                
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
                retry_delay = min(retry_delay * 2, 30)
    
    def run_scalping_module():
        update_scalping_data()
    
    thread = threading.Thread(target=run_angel_websocket, daemon=True)
    thread.start()
    
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
