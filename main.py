#!/usr/bin/env python3
"""
Real-Time Nifty 50 Scalping Dashboard
======================================
A production-ready terminal-based scalping dashboard that:
- Connects to Angel One's SmartAPI WebSocket for live NIFTY 50 data
- Calculates RSI(14) and EMA(50) in real-time using pandas_ta
- Generates BUY/SELL signals based on scalping logic
- Displays everything in a beautiful Rich TUI

Author: AI-Powered-Signal
"""

import os
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import pyotp
import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

# =============================================================================
# LOAD ENVIRONMENT VARIABLES FROM .env FILE
# =============================================================================
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# =============================================================================
# CONFIGURATION - Loaded securely from .env file
# =============================================================================
API_KEY = os.getenv("API_KEY", "YOUR_API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID", "YOUR_CLIENT_ID")
PASSWORD = os.getenv("PASSWORD", "YOUR_PASSWORD")
TOTP_SECRET = os.getenv("TOTP_SECRET", "YOUR_TOTP_SECRET")

# =============================================================================
# INSTRUMENT CONFIGURATION
# =============================================================================
SYMBOL_TOKEN = "99926000"  # NIFTY 50 Index
EXCHANGE = "NSE"           # Exchange type for WebSocket
EXCHANGE_TYPE = 1          # 1 = NSE Cash/Index

# =============================================================================
# SCALPING PARAMETERS
# =============================================================================
PRICE_BUFFER_SIZE = 200    # Number of ticks to maintain in memory
RSI_PERIOD = 14            # RSI calculation period
EMA_PERIOD = 50            # EMA calculation period
RSI_OVERSOLD = 30          # RSI oversold threshold (BUY signal)
RSI_OVERBOUGHT = 70        # RSI overbought threshold (SELL signal)

from dataclasses import dataclass
from datetime import timedelta

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
        self.closed_candles: deque = deque(maxlen=200)  # Store last 200 candles
        
    def update(self, price: float, timestamp: datetime) -> bool:
        """
        Update with new tick. Returns True if a candle just closed.
        """
        # Round down to nearest minute
        candle_time = timestamp.replace(second=0, microsecond=0)
        
        candle_closed = False
        
        # If we have a current candle
        if self.current_candle:
            # Check if this tick belongs to a new candle
            if candle_time > self.current_candle.timestamp:
                # Close current candle
                self.current_candle.is_closed = True
                self.closed_candles.append(self.current_candle)
                candle_closed = True
                
                # Start new candle
                self.current_candle = Candle(
                    timestamp=candle_time,
                    open=price,
                    high=price,
                    low=price,
                    close=price
                )
            else:
                # Update current candle
                self.current_candle.high = max(self.current_candle.high, price)
                self.current_candle.low = min(self.current_candle.low, price)
                self.current_candle.close = price
        else:
            # First candle
            self.current_candle = Candle(
                timestamp=candle_time,
                open=price,
                high=price,
                low=price,
                close=price
            )
            
        return candle_closed

    def get_closes(self) -> pd.Series:
        """Get series of close prices (closed candles + current live candle)"""
        closes = [c.close for c in self.closed_candles]
        if self.current_candle:
            closes.append(self.current_candle.close)
        return pd.Series(closes)
        
    def get_count(self) -> int:
        return len(self.closed_candles) + (1 if self.current_candle else 0)

# =============================================================================
# GLOBAL STATE
# =============================================================================
console = Console()
candle_manager = CandleManager(timeframe_minutes=1)
tick_history: deque = deque(maxlen=20)  # For UI display
current_signal = "WAITING"
signal_color = "grey50"
last_rsi: Optional[float] = None
last_ema: Optional[float] = None
last_price: Optional[float] = None
ws_connected = False
market_status = "CONNECTING..."
total_ticks = 0
lock = threading.Lock()
sws = None


def generate_totp() -> str:
    """Generate TOTP token using pyotp."""
    totp = pyotp.TOTP(TOTP_SECRET)
    return totp.now()


def authenticate() -> tuple[SmartConnect, dict]:
    """
    Authenticate with Angel One SmartAPI.
    Returns the SmartConnect object and auth tokens.
    """
    console.print("[bold yellow]🔐 Authenticating with Angel One...[/bold yellow]")
    
    smart_api = SmartConnect(api_key=API_KEY)
    
    # Generate TOTP for 2FA
    totp_token = generate_totp()
    
    try:
        # Login with credentials and TOTP
        data = smart_api.generateSession(
            clientCode=CLIENT_ID,
            password=PASSWORD,
            totp=totp_token
        )
        
        if data.get("status"):
            auth_token = data["data"]["jwtToken"]
            refresh_token = data["data"]["refreshToken"]
            feed_token = smart_api.getfeedToken()
            
            console.print("[bold green]✅ Authentication successful![/bold green]")
            time.sleep(1) # Allow token to propagate/settle
            
            return smart_api, {
                "auth_token": auth_token,
                "refresh_token": refresh_token,
                "feed_token": feed_token
            }
        else:
            raise Exception(f"Login failed: {data.get('message', 'Unknown error')}")
            
    except Exception as e:
        console.print(f"[bold red]❌ Authentication failed: {e}[/bold red]")
        raise


def calculate_rsi(prices: pd.Series, period: int = 14) -> Optional[float]:
    """
    Calculate RSI (Relative Strength Index) manually.
    RSI = 100 - (100 / (1 + RS))
    RS = Average Gain / Average Loss
    """
    if len(prices) < period + 1:
        return None
    
    # Calculate price changes
    delta = prices.diff()
    
    # Separate gains and losses
    gains = delta.where(delta > 0, 0.0)
    losses = (-delta).where(delta < 0, 0.0)
    
    # Calculate average gains and losses using EMA
    avg_gain = gains.ewm(alpha=1/period, min_periods=period).mean().iloc[-1]
    avg_loss = losses.ewm(alpha=1/period, min_periods=period).mean().iloc[-1]
    
    if avg_loss == 0:
        return 100.0  # No losses means RSI is 100
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return float(rsi)


def calculate_ema(prices: pd.Series, period: int = 50) -> Optional[float]:
    """
    Calculate EMA (Exponential Moving Average) manually.
    """
    if len(prices) < period:
        return None
    
    ema = prices.ewm(span=period, adjust=False).mean().iloc[-1]
    return float(ema)


def calculate_indicators() -> tuple[Optional[float], Optional[float]]:
    """
    Calculate RSI(14) and EMA(50) from the candle buffer.
    Returns (rsi, ema) tuple.
    """
    # Get sufficient data check
    # We need enough closed candles for accurate calculation
    # For EMA(50), we need at least 50 points
    if candle_manager.get_count() < max(RSI_PERIOD, EMA_PERIOD):
        return None, None
    
    # Get series of close prices
    prices = candle_manager.get_closes()
    
    # Calculate RSI using manual implementation
    rsi = calculate_rsi(prices, RSI_PERIOD)
    
    # Calculate EMA using manual implementation
    ema = calculate_ema(prices, EMA_PERIOD)
    
    return rsi, ema


def generate_signal(price: float, rsi: Optional[float], ema: Optional[float]) -> tuple[str, str]:
    """
    Generate trading signal based on scalping logic.
    
    BUY SIGNAL (BUY CALL): RSI < 30 AND Price > EMA(50)
    SELL SIGNAL (BUY PUT): RSI > 70 AND Price < EMA(50)
    
    Returns (signal_text, signal_color) tuple.
    """
    if rsi is None or ema is None:
        return "WAITING", "grey50"
    
    # BUY CALL condition: Oversold + Price above EMA (bullish reversal)
    if rsi < RSI_OVERSOLD and price > ema:
        return "BUY CALL", "green"
    
    # BUY PUT condition: Overbought + Price below EMA (bearish reversal)
    if rsi > RSI_OVERBOUGHT and price < ema:
        return "BUY PUT", "red"
    
    return "WAITING", "grey50"


def on_data(ws, message: dict):
    """
    Callback for incoming WebSocket data.
    Processes the tick and updates global state.
    """
    global current_signal, signal_color, last_rsi, last_ema, last_price
    global total_ticks, market_status
    
    try:
        # Extract LTP (Last Traded Price) from the message
        # SmartWebSocketV2 sends data in a specific format
        if isinstance(message, dict):
            ltp = message.get("last_traded_price")
            last_trade_time = message.get("last_traded_time") or int(time.time())
            
            if ltp is not None:
                # Angel One sends price in paise for equity, but index is in actual value
                # For NIFTY 50 index, the price is usually divided by 100
                price = ltp / 100.0  # Convert from paise to rupees
                
                # Convert timestamp if needed or use current time
                current_time = datetime.now()
                
                with lock:
                    total_ticks += 1
                    last_price = price
                    market_status = "LIVE"
                    
                    # Update Candle Manager
                    # This builds 1-min candles from ticks
                    candle_manager.update(price, current_time)
                    
                    # Add to tick history for display (keep this for visual flow)
                    tick_entry = {
                        "time": current_time.strftime("%H:%M:%S.%f")[:-3],
                        "price": price,
                        "change": 0.0
                    }
                    
                    if len(tick_history) > 0:
                        prev_price = tick_history[-1]["price"]
                        tick_entry["change"] = price - prev_price
                    
                    tick_history.append(tick_entry)
                    
                    # Calculate indicators (on every tick to show live status, 
                    # but calculation uses Candle Closes)
                    rsi, ema = calculate_indicators()
                    last_rsi = rsi
                    last_ema = ema
                    
                    # Generate signal
                    current_signal, signal_color = generate_signal(price, rsi, ema)
                    
    except Exception as e:
        # Don't print error for every tick to avoid spam, just log if needed
        pass


# Global WebSocket wrapper instance
sws = None


def on_open(ws):
    """Callback when WebSocket connection opens."""
    global ws_connected, market_status, sws
    ws_connected = True
    market_status = "CONNECTED"
    
    # Subscribe to NIFTY 50 index
    # Mode 1 = LTP, Mode 2 = Quote, Mode 3 = Snap Quote
    correlation_id = "nifty50_stream"
    mode = 3  # Revert to Mode 3 (Snap Quote) which worked previously
    
    token_list = [
        {
            "exchangeType": EXCHANGE_TYPE,
            "tokens": [SYMBOL_TOKEN]
        }
    ]
    
    try:
        if sws:
            sws.subscribe(correlation_id, mode, token_list)
            market_status = "SUBSCRIBED"
        else:
            market_status = "Error: sws not initialized"
            
    except Exception as e:
        market_status = f"Sub failed: {str(e)[:20]}"


def on_error(ws, error):
    """Callback for WebSocket errors."""
    global market_status
    market_status = f"ERROR: {str(error)[:30]}"


def on_close(ws):
    """Callback when WebSocket connection closes."""
    global ws_connected, market_status
    ws_connected = False
    market_status = "Connection closed"


import websocket

def start_websocket(auth_tokens: dict):
    """
    Start the WebSocket connection.
    Simple implementation without complex retry loops.
    """
    global ws_connected, market_status, sws
    
    # Disable verbose logging to keep it simple
    # websocket.enableTrace(True) 
    
    try:
        market_status = "Connecting..."
        sws = SmartWebSocketV2(
            auth_token=auth_tokens["auth_token"],
            api_key=API_KEY,
            client_code=CLIENT_ID,
            feed_token=auth_tokens["feed_token"]
        )
        
        # Set callbacks
        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close
        
        # Connect
        sws.connect()
        
    except Exception as e:
        market_status = f"Error: {str(e)[:20]}"


def create_header() -> Panel:
    """Create the header panel with market status."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    header_text = Text()
    header_text.append("📈 NIFTY 50 REAL-TIME SCALPING DASHBOARD", style="bold white")
    header_text.append("\n")
    header_text.append(f"Time: {now}", style="dim")
    header_text.append(" | ")
    
    # Market status with color
    if market_status == "LIVE" or market_status == "SUBSCRIBED":
        header_text.append("● ", style="bold green")
        header_text.append(market_status, style="bold green")
        
    elif market_status == "CONNECTED":
        header_text.append("● ", style="bold yellow")
        header_text.append("CONNECTED", style="bold yellow")
    elif "ERROR" in market_status or "Error" in market_status or "failed" in market_status:
        header_text.append("● ", style="bold red")
        header_text.append(market_status, style="bold red")
    else:
        header_text.append("● ", style="bold grey50")
        header_text.append(market_status, style="grey50")
    
    header_text.append(" | ")
    header_text.append(f"Ticks: {total_ticks}", style="cyan")
    header_text.append(" | ")
    
    # Candle buffer status
    candles_count = candle_manager.get_count()
    header_text.append(f"Candles: {candles_count}/200", style="magenta")
    
    return Panel(header_text, style="blue", title="[bold]Dashboard[/bold]")


def create_tick_table() -> Panel:
    """Create the table showing last 20 ticks."""
    table = Table(
        title="Last 20 Ticks",
        show_header=True,
        header_style="bold cyan",
        border_style="blue",
        expand=True
    )
    
    table.add_column("Time", style="dim", width=12)
    table.add_column("Price", justify="right", style="white", width=12)
    table.add_column("Change", justify="right", width=10)
    
    with lock:
        for tick in list(tick_history)[-20:]:
            change = tick["change"]
            if change > 0:
                change_style = "green"
                change_str = f"+{change:.2f}"
            elif change < 0:
                change_style = "red"
                change_str = f"{change:.2f}"
            else:
                change_style = "dim"
                change_str = "0.00"
            
            table.add_row(
                tick["time"],
                f"₹{tick['price']:.2f}",
                Text(change_str, style=change_style)
            )
    
    return Panel(table, title="[bold cyan]Tick History[/bold cyan]", border_style="cyan")


def create_indicators_panel() -> Panel:
    """Create panel showing current indicators."""
    with lock:
        price = last_price
        rsi = last_rsi
        ema = last_ema
    
    content = Text()
    content.append("📊 INDICATORS (1-Min Timeframe)\n\n", style="bold white")
    
    # Price
    if price is not None:
        content.append("NIFTY 50: ", style="dim")
        content.append(f"₹{price:.2f}\n", style="bold white")
    else:
        content.append("NIFTY 50: ", style="dim")
        content.append("Waiting...\n", style="grey50")
    
    content.append("\n")
    
    # RSI
    content.append(f"RSI({RSI_PERIOD}): ", style="dim")
    if rsi is not None:
        rsi_color = "green" if rsi < RSI_OVERSOLD else ("red" if rsi > RSI_OVERBOUGHT else "yellow")
        content.append(f"{rsi:.2f}\n", style=f"bold {rsi_color}")
        
        # RSI interpretation
        if rsi < RSI_OVERSOLD:
            content.append("  ↳ OVERSOLD\n", style="green")
        elif rsi > RSI_OVERBOUGHT:
            content.append("  ↳ OVERBOUGHT\n", style="red")
        else:
            content.append("  ↳ NEUTRAL\n", style="yellow")
    else:
        content.append("Calculating...\n", style="grey50")
    
    content.append("\n")
    
    # EMA
    content.append(f"EMA({EMA_PERIOD}): ", style="dim")
    if ema is not None:
        content.append(f"₹{ema:.2f}\n", style="bold cyan")
        
        # Price vs EMA
        if price is not None:
            if price > ema:
                content.append("  ↳ Price ABOVE EMA\n", style="green")
            else:
                content.append("  ↳ Price BELOW EMA\n", style="red")
    else:
        content.append("Calculating...\n", style="grey50")
    
    return Panel(content, title="[bold magenta]Indicators[/bold magenta]", border_style="magenta")


def create_signal_box() -> Panel:
    """Create the signal box panel with dynamic coloring."""
    with lock:
        signal = current_signal
        color = signal_color
    
    # Create large, prominent signal text
    # detailed signal info
    signal_text = Text(justify="center")
    signal_text.append("\n\n")
    
    if signal == "BUY CALL":
        signal_text.append("🟢 BUY CALL 🟢", style="bold white")
        signal_text.append("\n\n")
        signal_text.append("RSI Oversold + Price Above EMA", style="white")
        signal_text.append("\n")
        signal_text.append("BULLISH REVERSAL EXPECTED", style="bold white")
        box_style = "bold white on green"
        border_style = "green"
    elif signal == "BUY PUT":
        signal_text.append("🔴 BUY PUT 🔴", style="bold white")
        signal_text.append("\n\n")
        signal_text.append("RSI Overbought + Price Below EMA", style="white")
        signal_text.append("\n")
        signal_text.append("BEARISH REVERSAL EXPECTED", style="bold white")
        box_style = "bold white on red"
        border_style = "red"
    else:
        signal_text.append("⏳ WAITING ⏳", style="bold white")
        signal_text.append("\n\n")
        signal_text.append("Analyzing market conditions...", style="dim white")
        signal_text.append("\n")
        waiting_points = max(RSI_PERIOD, EMA_PERIOD) - candle_manager.get_count()
        msg = f"Need {waiting_points} more candles" if candle_manager.get_count() < max(RSI_PERIOD, EMA_PERIOD) else "No signal conditions met"
        signal_text.append(msg, style="dim white")
        box_style = "white on grey30"
        border_style = "grey50"
    
    signal_text.append("\n\n")
    
    return Panel(
        signal_text,
        title="[bold]🎯 TRADING SIGNAL[/bold]",
        style=box_style,
        border_style=border_style,
        padding=(1, 2)
    )


def create_layout() -> Layout:
    """Create the main layout for the dashboard."""
    layout = Layout()
    
    # Main vertical split
    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="body"),
        Layout(name="signal", size=12)
    )
    
    # Body split into left and right
    layout["body"].split_row(
        Layout(name="ticks", ratio=2),
        Layout(name="indicators", ratio=1)
    )
    
    return layout


def update_layout(layout: Layout) -> Layout:
    """Update the layout with current data."""
    layout["header"].update(create_header())
    layout["ticks"].update(create_tick_table())
    layout["indicators"].update(create_indicators_panel())
    layout["signal"].update(create_signal_box())
    return layout


def main():
    """Main entry point for the scalping dashboard."""
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]🚀 NIFTY 50 REAL-TIME SCALPING DASHBOARD 🚀[/bold cyan]\n"
        "[dim]Powered by Angel One SmartAPI & Rich Terminal UI[/dim]",
        border_style="cyan"
    ))
    console.print()
    
    # Validate configuration
    if API_KEY == "YOUR_API_KEY" or CLIENT_ID == "YOUR_CLIENT_ID":
        console.print("[bold red]❌ ERROR: Please configure your API credentials![/bold red]")
        console.print("[yellow]Edit the configuration variables at the top of main.py:[/yellow]")
        console.print("  • API_KEY")
        console.print("  • CLIENT_ID")
        console.print("  • PASSWORD")
        console.print("  • TOTP_SECRET")
        return
    
    try:
        # Step 1: Authenticate
        smart_api, auth_tokens = authenticate()
        
        # Step 2: Start WebSocket in daemon thread
        console.print("[bold yellow]🔌 Starting WebSocket connection...[/bold yellow]")
        ws_thread = threading.Thread(
            target=start_websocket,
            args=(auth_tokens,),
            daemon=True
        )
        ws_thread.start()
        
        # Give WebSocket time to connect
        time.sleep(2)
        
        # Step 3: Start the Rich Live display
        console.print("[bold green]🎨 Starting dashboard...[/bold green]")
        time.sleep(1)
        console.clear()
        
        layout = create_layout()
        
        with Live(layout, console=console, refresh_per_second=4, screen=True) as live:
            while True:
                try:
                    layout = update_layout(layout)
                    time.sleep(0.25)  # Update 4 times per second
                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[red]Display error: {e}[/red]")
                    time.sleep(1)
        
        console.print("\n[bold yellow]👋 Dashboard stopped. Goodbye![/bold yellow]")
        
    except KeyboardInterrupt:
        console.print("\n[bold yellow]👋 Interrupted by user. Goodbye![/bold yellow]")
    except Exception as e:
        console.print(f"\n[bold red]❌ Fatal error: {e}[/bold red]")
        raise


if __name__ == "__main__":
    main()
