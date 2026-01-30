import os
from SmartApi import SmartConnect
import pyotp
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
PASSWORD = os.getenv("PASSWORD")
TOTP_SECRET = os.getenv("TOTP_SECRET")

def debug_search():
    print(f"🔌 Connecting...")
    smart_api = SmartConnect(api_key=API_KEY)
    totp = pyotp.TOTP(TOTP_SECRET).now()
    data = smart_api.generateSession(CLIENT_ID, PASSWORD, totp)
    
    if not data or not data.get('status'):
        print(f"❌ Login Failed")
        return

    print("✅ Search: 'NIFTY' (Futures)")
    # Search for NIFTY Futures
    try:
        # Try finding the Feb Future
        response = smart_api.searchScrip(exchange="NFO", searchscrip="NIFTY")
        
        if response and response.get('status') and response.get('data'):
            print(f"✅ Found {len(response['data'])} results. NIFTY Futures:")
            
            for item in response['data']:
                sym = item['tradingsymbol']
                # Filter for core NIFTY futures (exclude patterns like NIFTYNXT50, BANKNIFTY, FINNIFTY)
                if sym.startswith("NIFTY") and "FUT" in sym:
                    if "NXT50" not in sym and "BANK" not in sym and "FIN" not in sym and "MID" not in sym:
                         print(f"   MATCH: {sym} -> {item['symboltoken']}")
                         
            print("\n✅ NIFTY Options (Sample):")
            count = 0
            for item in response['data']:
                sym = item['tradingsymbol']
                if sym.startswith("NIFTY") and ("CE" in sym or "PE" in sym):
                     if "NXT50" not in sym and "BANK" not in sym:
                         print(f"   MATCH: {sym} -> {item['symboltoken']}")
                         count += 1
                         if count > 5: break
                         
        else:
            print("❌ Search returned no data.")
            
    except Exception as e:
        print(f"❌ Search Error: {e}")

if __name__ == "__main__":
    debug_search()
