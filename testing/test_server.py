
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
import asyncio
import time
import json
from pathlib import Path
from scenario_engine import ScenarioEngine

# Paths
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR.parent / "production" / "static"

app = FastAPI(title="Scalping Dashboard - STRESS TEST SERVER")

# Mount Static Files (Serve same frontend)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# State
engine = ScenarioEngine()
active_scenario = "SIDEWAYS"
tick_speed_ms = 100 # Default 100ms (10 ticks/sec)
connected_clients = set()

# Scalping State (Shared between WS and API)
scalping_state = {
    "status": "LIVE",
    "future_price": 0.0,
    "ce_price": 0.0,
    "pe_price": 0.0,
    "basis": 0.0,
    "real_basis": 0.0,
    "straddle_price": 0.0,
    "trend": "FLAT",
    "sentiment": "NEUTRAL",
    "signal": "WAIT",
    "suggestion": "WAITING...",
    "pcr": 1.0,
    "history": [] 
}

@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse(STATIC_DIR / "index.html")

@app.get("/api/scalper-data")
async def get_scalper_data():
    """Mock API for Scalping Module"""
    return scalping_state

@app.get("/control")
async def control_panel(scenario: str = "SIDEWAYS", speed_ms: int = 100, regime: str = "NORMAL"):
    """
    Control Endpoint to switch scenarios dynamically.
    Example: /control?scenario=BULL_RUN&speed_ms=10&regime=HIGH_VIX
    """
    global active_scenario, tick_speed_ms
    active_scenario = scenario
    tick_speed_ms = max(10, speed_ms) # Cap at 10ms (100 ticks/sec)
    engine.set_regime(regime)
    return {
        "status": "UPDATED",
        "scenario": active_scenario,
        "speed_ms": tick_speed_ms,
        "regime": engine.regime.name
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global scalping_state
    await websocket.accept()
    connected_clients.add(websocket)
    print("🔌 Client Connected to Stress Test Stream")
    
    try:
        # Scenario Generator
        generator = None
        current_type = ""
        
        while True:
            # 1. Check if scenario changed, reset generator
            if active_scenario != current_type:
                current_type = active_scenario
                generator = engine.generate_scenario(current_type, duration_ticks=100000)
            
            # 2. Get Next Tick
            try:
                tick = next(generator)
            except StopIteration:
                generator = engine.generate_scenario(current_type, duration_ticks=100000)
                tick = next(generator)
                
            # 3. Construct Payload (Mimic server.py structure)
            extra = tick["_extra"]
            price = tick["last_traded_price"] / 100.0
            
            # Mock Signal Logic (Simplified extraction from Extra)
            # In real app, this is calculated. Here we pass through simulation result
            signal = "WAIT"
            color = "#808080"
            suggestion = "WAIT - No Trend"
            
            if extra["scenario"] in ["BULL_RUN"]:
                 if extra["pcr"] > 1:
                     signal = "BUY CALL"
                     color = "#00ff00"
                     suggestion = "BUY CE - Momentum"
                 elif extra["pcr"] < 0.6: # Trap Logic from Engine
                     signal = "TRAP"
                     color = "#ffa500"
                     suggestion = "⚠️ TRAP - Price Rising but LOW PCR"
                     
            if extra["scenario"] in ["BEAR_CRASH"]:
                 if extra["pcr"] < 1:
                     signal = "BUY PUT"
                     color = "#ff0000"
                     suggestion = "BUY PE - Momentum"
                 elif extra["pcr"] > 1.4: # Trap Logic
                     signal = "TRAP"
                     color = "#ffa500"
                     suggestion = "⚠️ TRAP - Price Falling but HIGH PCR"
                     
            if extra["scenario"] == "BUDGET_DAY":
                # MOMENTUM-BASED SIGNALS (More Reactive)
                # Track last 10 ticks for short-term momentum
                if "momentum_buffer" not in scalping_state:
                     scalping_state["momentum_buffer"] = []
                
                change = price - last_price if 'last_price' in locals() else 0
                scalping_state["momentum_buffer"].append(change)
                if len(scalping_state["momentum_buffer"]) > 20: # 2 seconds window
                    scalping_state["momentum_buffer"].pop(0)
                
                # Calculate Avg Velocity (Points per tick)
                avg_velocity = sum(scalping_state["momentum_buffer"]) / len(scalping_state["momentum_buffer"]) if scalping_state["momentum_buffer"] else 0
                
                signal = "TRAP"
                color = "#ffa500"
                suggestion = "⚠️ CHOPPY - High Volatility"
                
                # Adjusted Thresholds for "Realistic" Speed (Max drift is 0.8)
                # Lower threshold to detect the micro-trends reliably
                # Threshold should be < 0.8 but > 0 (noise)
                
                if avg_velocity > 0.4 and extra["pcr"] > 1.0: # Sustained Upward Move + Data Confirmation
                    signal = "BUY CALL"
                    color = "#00ff00"
                    suggestion = "🚀 MOMENTUM UP - Trend Catching"
                elif avg_velocity < -0.4 and extra["pcr"] < 1.0: # Sustained Downward Move + Data Confirmation
                    signal = "BUY PUT"
                    color = "#ff0000"
                    suggestion = "🩸 MOMENTUM DOWN - Trend Catching"
                elif abs(avg_velocity) > 0.4: # Momentum without PCR support
                      signal = "TRAP"
                      color = "#ffa500"
                      suggestion = "⚠️ FAKE BREAKOUT - Data Divergence"
                elif abs(avg_velocity) < 0.2:
                      suggestion = "⚪ SIDEWAYS - Scalping Zone"
            
            # DETAILED TRAP SIGNALS WITH EXPLANATIONS
            if extra["scenario"] == "BULL_TRAP":
                signal = "TRAP" 
                color = "#ffa500"
                pcr_val = extra["pcr"]
                suggestion = f"⚠️ BULL TRAP DETECTED!\n📈 Price RISING but PCR={pcr_val:.2f} (LOW)\n💡 Bearish OI dominance = Reversal Risk\n🎯 Smart Money is SELLING into strength"
            elif extra["scenario"] == "BEAR_TRAP":
                signal = "TRAP" 
                color = "#ffa500"
                pcr_val = extra["pcr"]
                suggestion = f"⚠️ BEAR TRAP DETECTED!\n📉 Price FALLING but PCR={pcr_val:.2f} (HIGH)\n💡 Bullish OI dominance = Reversal Risk\n🎯 Smart Money is BUYING the dip"
            
            # UPDATE SHARED SCALPING STATE
            future = extra["future"]
            ce = extra["ce"]
            pe = extra["pe"]
            # FIXED: Straddle Price = AVERAGE of CE + PE (matches production server.py line 835)
            straddle = round((ce + pe) / 2, 2)
            basis = future - price
            
            # Dynamic ATM Strike Calculation
            atm_strike = round(price / 50) * 50

            # Update History (Keep last 50)
            # FIX: app.js expects 'straddle' key, not 'price'
            history_entry = {"time": time.strftime("%H:%M:%S"), "straddle": straddle}
            if len(scalping_state["history"]) > 50:
                scalping_state["history"].pop(0)
            scalping_state["history"].append(history_entry)
            
            scalping_state.update({
                "future_price": future,
                "atm_strike": atm_strike, # ADDED: Missing in original
                "ce_price": ce,
                "pe_price": pe,
                "pcr": extra["pcr"],
                "basis": basis,
                "real_basis": basis, # Simulating they are same
                "straddle_price": straddle,
                "sentiment": "BULLISH" if basis > 5 else "BEARISH" if basis < -5 else "NEUTRAL",
                "trend": "RISING" if active_scenario in ["BULL_RUN", "BEAR_CRASH"] else "FLAT", # Vol expands in both runs
                "signal": signal,
                "suggestion": suggestion
            })

            payload = {
                "market_status": f"TEST: {active_scenario} ({engine.regime.name})",
                "total_ticks": int(time.time() * 1000) % 1000000, # Mock tick count
                "candles_count": "100/200",
                "last_price": price,
                "rsi": 50 + (price - 25000)/10, # Mock Indicator
                "ema": price - 10, # Bullish bias mock
                "signal": signal,
                "signal_color": color,
                "tick_history": [], # Empty for bandwidth in stress test
                
                # Full Ticker Map
                "tickers": {
                    "nifty": {
                        "price": price,
                        "change": price - 25000,
                        "p_change": (price - 25000)/25000 * 100
                    },
                    "indiavix": {
                        "price": extra["vix"],
                        "change": 0,
                        "p_change": 0
                    },
                     "sensex": {"price": price * 3.2, "change": 0, "p_change": 0}, # Mock relation
                     "banknifty": {"price": price * 2.1, "change": 0, "p_change": 0}
                }
            }
            
            # 4. Stream
            await websocket.send_json(payload)
            
            # 5. Speed Control
            await asyncio.sleep(tick_speed_ms / 1000.0)
            
            # CRITICAL FIX: Update last_price for next iteration
            last_price = price
            
    except Exception as e:
        print(f"❌ Error: {e}")
        connected_clients.discard(websocket)
    except WebSocketDisconnect:
        print("📴 Client Disconnected")
        connected_clients.discard(websocket)

if __name__ == "__main__":
    import uvicorn
    print("🚀 STARTING STRESS TEST SERVER ON PORT 8001")
    print("👉 Control URL: http://localhost:8001/control?scenario=BULL_RUN&speed_ms=10")
    uvicorn.run(app, host="0.0.0.0", port=8001)
