
import random
import math
import time
from dataclasses import dataclass
from typing import List, Dict, Generator

@dataclass
class MarketRegime:
    name: str
    vix: float
    volatility_multiplier: float
    option_premium_multiplier: float
    decay_speed: float

class ScenarioEngine:
    def __init__(self):
        # Initial State (NIFTY)
        self.spot_price = 25000.0
        self.strike_price = 25000
        
        # Default Regime: Normal
        self.regime = MarketRegime("NORMAL", 14.0, 1.0, 1.0, 1.0)
        
        # Option Greeks (Simplified for Simulation)
        self.delta_ce = 0.5
        self.delta_pe = -0.5
        self.theta = 2.0 # Decay per tick approx
        
        # Current Prices
        self.ce_price = 150.0
        self.pe_price = 150.0
        self.future_price = 25050.0
        
        # OI Data
        self.pcr = 1.0
        
    def set_regime(self, regime_type: str):
        """Sets the market regime (volatility, VIX, premiums)."""
        if regime_type == "HIGH_VIX":
            self.regime = MarketRegime("HIGH_VIX", 24.0, 2.5, 1.8, 0.5) # Fast moves, expensive options
        elif regime_type == "LOW_VIX":
             self.regime = MarketRegime("LOW_VIX", 11.0, 0.4, 0.6, 2.0) # Slow moves, cheap options, fast decay
        elif regime_type == "BUDGET_VOLATILITY":
             self.regime = MarketRegime("BUDGET_VOLATILITY", 35.0, 4.5, 2.5, 0.2) # Extreme Moves, Ultra Expensive, Low Decay
        else:
             self.regime = MarketRegime("NORMAL", 14.0, 1.0, 1.0, 1.0)
             
        print(f"🔄 Switched to Regime: {self.regime.name} (VIX: {self.regime.vix})")

    def generate_scenario(self, scenario_type: str, duration_ticks: int = 100) -> Generator[Dict, None, None]:
        """
        Generates a stream of market data ticks based on the scenario.
        yields: dict with market interaction data
        """
        print(f"🎬 Starting Scenario: {scenario_type} [{duration_ticks} ticks]")
        
        for i in range(duration_ticks):
            # 1. Determine Spot Move based on Scenario + Regime
            move = 0
            noise = random.uniform(-2, 2) * self.regime.volatility_multiplier
            
            if scenario_type == "BULL_RUN":
                # V4 PHYSICS: Strong Positive Drift
                move = random.uniform(0.5, 1.5) * self.regime.volatility_multiplier
                # Less noise in strong trend
                noise = random.uniform(-0.5, 0.5) 
            elif scenario_type == "BEAR_CRASH":
                # V4 PHYSICS: Strong Negative Drift + Panic Spikes
                move = random.uniform(-2.0, -0.8) * self.regime.volatility_multiplier
                # High noise in crash
                noise = random.uniform(-1.0, 1.0)
            elif scenario_type == "SIDEWAYS":
                move = random.uniform(-1, 1) * 0.5 # Choppy
            elif scenario_type == "BULL_TRAP":
                 # Rise first, then mild drop, but PCR implies Bearish
                 if i < duration_ticks * 0.7:
                     move = random.uniform(1, 3) 
                 else:
                     move = random.uniform(-2, 0)
            elif scenario_type == "BEAR_TRAP":
                 if i < duration_ticks * 0.7:
                     move = random.uniform(-3, -1) 
                 else:
                     move = random.uniform(0, 2)
            elif scenario_type == "BUDGET_DAY":
                 # REALISTIC BUDGET DAY V4 (Refined)
                 # Physics: Micro-Trends + Mean Reversion + High Noise
                 # Goal: Choppy, Whippy, but not "Fast Forward"
                 
                 # Initialize State
                 if not hasattr(self, 'budget_trend_duration'):
                     self.budget_trend_duration = 0
                     self.budget_drift = 0
                     self.budget_bias_target = 20.0
                 
                 # 1. New Micro-Trend (Every 2-5 seconds = 20-50 ticks)
                 if self.budget_trend_duration <= 0:
                     self.budget_trend_duration = random.randint(20, 50)
                     
                     # Lower Drift Magnitude: 0.2 - 0.8 (multiplied by 4.5 later)
                     # approx 1-3 points per tick = 10-30 points/sec (Fast but realistic)
                     direction = 1 if random.random() > 0.5 else -1
                     self.budget_drift = random.uniform(0.2, 0.8) * direction
                     
                     # Variable Basis Target (Premium/Discount flips)
                     self.budget_bias_target = random.uniform(-30, 80)
                     
                 self.budget_trend_duration -= 1
                 
                 # 2. Add Heavy Noise (Uncertainty)
                 jitter = random.gauss(0, 1.5) 
                 
                 # Total Move
                 move = self.budget_drift + jitter
            
            # Apply Move
            self.spot_price += (move + noise)
            
            # 2. Update Future (Spot + Premium/Discount)
            # DYNAMIC BASIS LOGIC (Greed vs Fear)
            if scenario_type == "BUDGET_DAY":
                # Smoothly interpolate basis (already implemented V4)
                current_basis = self.future_price - self.spot_price
                new_basis = current_basis + (self.budget_bias_target - current_basis) * 0.1
                future_basis = new_basis
            elif scenario_type == "BULL_RUN":
                 # High Demand = High Premium (Greed)
                 future_basis = (50 + random.uniform(20, 50)) * self.regime.volatility_multiplier
            elif scenario_type == "BEAR_CRASH":
                 # Panic Selling = Discount or Collapsing Premium (Fear)
                 future_basis = (10 - random.uniform(0, 30)) * self.regime.volatility_multiplier # Can go negative
            else:
                 # Normal
                 future_basis = 50 * self.regime.volatility_multiplier
            
            self.future_price = self.spot_price + future_basis + random.uniform(-2, 2)
            
            # 3. Update Options (Delta + Gamma + Theta)
            # Delta Effect
            ce_change = move * self.delta_ce
            pe_change = move * self.delta_pe
            
            # Gamma Effect (Acceleration) - High VIX = Higher Gamma
            # Simplified: As price moves away, delta changes
            if move > 0:
                self.delta_ce = min(0.9, self.delta_ce + 0.01)
                self.delta_pe = max(-0.1, self.delta_pe + 0.01)
            else:
                self.delta_ce = max(0.1, self.delta_ce - 0.01)
                self.delta_pe = min(-0.9, self.delta_pe - 0.01)

            # Theta Effect (Decay)
            decay = 0.1 * self.regime.decay_speed
            
            self.ce_price += ce_change - decay
            self.pe_price += pe_change - decay
            
            # Ensure non-negative
            self.ce_price = max(0.05, self.ce_price)
            self.pe_price = max(0.05, self.pe_price)
            
            # 4. PCR / OI Logic (Crucial for Traps)
            if scenario_type == "BULL_TRAP":
                self.pcr = 0.5 # Bearish OI despite price rise
            elif scenario_type == "BEAR_TRAP":
                self.pcr = 1.5 # Bullish OI despite price drop
            elif scenario_type == "BULL_RUN":
                self.pcr = 1.3
            elif scenario_type == "BEAR_CRASH":
                self.pcr = 0.6
            elif scenario_type == "BEAR_CRASH":
                self.pcr = 0.6
            elif scenario_type == "BUDGET_DAY":
                # Dynamic PCR for Budget Day (Correlated to drift)
                # If Drift is positive (Bullish), PCR should rise > 1
                # If Drift is negative (Bearish), PCR should fall < 1
                target_pcr = 1.0 + (self.budget_drift * 2.0) # drift 0.5 -> pcr 2.0
                self.pcr += (target_pcr - self.pcr) * 0.1 # Smooth transition
                self.pcr = max(0.4, min(2.5, self.pcr)) # Clamp
            else:
                 # Default randomization for normal/sideways
                 self.pcr = 1.0 + random.uniform(-0.1, 0.1)
                 
            # PCR FOLLOWS TREND (Crucial for Signals)
            if scenario_type == "BULL_RUN":
                self.pcr = min(2.5, self.pcr + 0.01) # Slowly rising
            elif scenario_type == "BEAR_CRASH":
                self.pcr = max(0.4, self.pcr - 0.01) # Slowly falling

            # Yield Tick
            yield {
                "token": "99926000", # NIFTY Token
                "symbol": "NIFTY 50",
                "last_traded_price": self.spot_price * 100, # API format
                "close_price": 25000.0 * 100,
                
                # Context Data (Sent separately or injected)
                "_extra": {
                    "regime": self.regime.name,
                    "scenario": scenario_type,
                    "future": self.future_price,
                    "ce": self.ce_price,
                    "pe": self.pe_price,
                    "pcr": self.pcr,
                    "vix": self.regime.vix + random.uniform(-0.5, 0.5)
                }
            }
