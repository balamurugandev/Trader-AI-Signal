import time
from collections import deque
import random

class ScalperSimulation:
    def __init__(self):
        # State variables matching server.py
        self.raw_basis_history = deque(maxlen=20)
        self.last_straddle_prices = deque(maxlen=5)
        self.atm_strike = 24000  # Default for sim
        
        # Current State
        self.sentiment = "NEUTRAL"
        self.straddle_trend = "FLAT"
        self.signal = "WAIT"
        self.suggestion = "WAIT"
        self.is_trap = False

    def update(self, spot, future, ce_price, pe_price, pcr_value=1.0):
        """
        Runs one tick of the scalping logic.
        """
        # 1. Calculate Basis & Sentiment (Z-Score Logic)
        synthetic_future = self.atm_strike + ce_price - pe_price
        raw_basis = synthetic_future - spot
        
        self.raw_basis_history.append(raw_basis)
        
        if len(self.raw_basis_history) > 10:
            avg_basis = sum(self.raw_basis_history) / len(self.raw_basis_history)
            # Simplified Z-Score (using absolute deviation for simplicity in sim)
            sentiment_score = raw_basis - avg_basis
        else:
            sentiment_score = 0
            
        if sentiment_score > 3:
            self.sentiment = "BULLISH"
        elif sentiment_score < -3:
            self.sentiment = "BEARISH"
        else:
            self.sentiment = "NEUTRAL"
            
        # 2. Straddle Trend
        straddle_price = (ce_price + pe_price) / 2
        self.last_straddle_prices.append(straddle_price)
        
        straddle_sma3 = 0
        if len(self.last_straddle_prices) >= 3:
            recent_3 = list(self.last_straddle_prices)[-3:]
            straddle_sma3 = sum(recent_3) / 3
            
            if straddle_price > straddle_sma3:
                self.straddle_trend = "RISING"
            elif straddle_price < straddle_sma3:
                self.straddle_trend = "FALLING"
            else:
                self.straddle_trend = "FLAT"
        else:
            self.straddle_trend = "FLAT"
            
        # 3. Signal Generation
        temp_signal = "WAIT"
        temp_suggestion = "WAIT - NO TREND"
        
        if self.sentiment == "BULLISH" and self.straddle_trend == "RISING":
            temp_signal = "BUY CALL"
            temp_suggestion = f"BUY {self.atm_strike} CE"
        elif self.sentiment == "BEARISH" and self.straddle_trend == "RISING":
            temp_signal = "BUY PUT"
            temp_suggestion = f"BUY {self.atm_strike} PE"
        elif self.straddle_trend == "FALLING":
            temp_signal = "WAIT"
            temp_suggestion = "WAIT - DECAY"
            
        # 4. Trap Filter
        self.is_trap = False
        if temp_signal == "BUY CALL":
            if pcr_value < 0.6:
                temp_signal = "TRAP"
                self.is_trap = True
                temp_suggestion = "⚠️ TRAP - HEAVY CALL WRITING"
        elif temp_signal == "BUY PUT":
            if pcr_value > 1.4:
                temp_signal = "TRAP"
                self.is_trap = True
                temp_suggestion = "⚠️ TRAP - HEAVY PUT WRITING"
                
        self.signal = temp_signal
        self.suggestion = temp_suggestion
        
        return {
            "spot": spot,
            "basis": round(raw_basis, 2),
            "sentiment_score": round(sentiment_score, 2),
            "sentiment": self.sentiment,
            "straddle": straddle_price,
            "trend": self.straddle_trend,
            "signal": self.signal,
            "suggestion": self.suggestion
        }

def run_scenario(name, ticks):
    print(f"\n{'='*60}")
    print(f"🧪 RUNNING SCENARIO: {name}")
    print(f"{'='*60}")
    
    sim = ScalperSimulation()
    
    for i, tick in enumerate(ticks):
        result = sim.update(
            spot=tick['spot'],
            future=tick['future'],
            ce_price=tick['ce'],
            pe_price=tick['pe'],
            pcr_value=tick.get('pcr', 1.0)
        )
        
        # Only print every few ticks or if signal changes to avoid spam
        status_icon = "⚪"
        if result['signal'] == "BUY CALL": status_icon = "🟢"
        elif result['signal'] == "BUY PUT": status_icon = "🔴"
        elif result['signal'] == "TRAP": status_icon = "⚠️"
        
        print(f"Tick {i+1:02d} | Spot: {result['spot']} | Sent: {result['sentiment']} ({result['sentiment_score']}) | Trend: {result['trend']} | {status_icon} Signal: {result['signal']}")
        
        time.sleep(0.05) # fast forward

# =============================================================================
# SCENARIOS
# =============================================================================

# Scenario 1: Range Bound (Choppy)
# Spot moves little, options decay, basis stable
ticks_range = []
spot = 24000
for i in range(20):
    change = random.choice([-2, 2, 0])
    spot += change
    ticks_range.append({
        'spot': spot,
        'future': spot + 50,
        'ce': 100 - (i*0.5), # Decay
        'pe': 100 - (i*0.5)  # Decay
    })

# Scenario 2: Bull Run (Momentum)
# Spot flies up, CE explodes, PE drops, Basis expands (sentiment)
ticks_bull = []
spot = 24000
base_ce = 100
base_pe = 100
for i in range(20):
    spot += 10 # Fast rise
    base_ce += 8 # Gamma spike
    base_pe -= 3 # Delta drop
    ticks_bull.append({
        'spot': spot,
        'future': spot + 60 + (i*2), # Future expands premium
        'ce': base_ce,
        'pe': base_pe
    })
    
# Scenario 3: Bear Crash (Momentum)
# Spot tanks, PE explodes, CE drops, Basis contracts (sentiment)
ticks_bear = []
spot = 24000
base_ce = 100
base_pe = 100
for i in range(20):
    spot -= 10 # Fast drop
    base_ce -= 3 
    base_pe += 8 # Gamma spike
    ticks_bear.append({
        'spot': spot,
        'future': spot + 40 - (i*2), # Future discount
        'ce': base_ce,
        'pe': base_pe
    })

# Scenario 4: Bull Trap (High Call Writing)
# Price rising, but PCR is very low (< 0.6)
ticks_trap = []
spot = 24000
base_ce = 100
base_pe = 100
for i in range(20):
    spot += 10 
    base_ce += 8 
    base_pe -= 3
    ticks_trap.append({
        'spot': spot,
        'future': spot + 60 + (i*2),
        'ce': base_ce,
        'pe': base_pe,
        'pcr': 0.4  # TRAP CONDITION
    })

if __name__ == "__main__":
    run_scenario("Range Bound (Expect WAIT)", ticks_range)
    run_scenario("Bull Run (Expect BUY CALL)", ticks_bull)
    run_scenario("Bear Crash (Expect BUY PUT)", ticks_bear)
    run_scenario("Bull Trap (Expect TRAP)", ticks_trap)
