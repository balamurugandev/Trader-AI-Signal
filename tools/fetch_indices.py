import os
from pathlib import Path
from dotenv import load_dotenv
import pyotp
from SmartApi import SmartConnect

# Load Env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

API_KEY = os.getenv("API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
PASSWORD = os.getenv("PASSWORD")
TOTP_SECRET = os.getenv("TOTP_SECRET")

def generate_totp():
    return pyotp.TOTP(TOTP_SECRET).now()

def main():
    print("🔐 Authenticating...")
    smart_api = SmartConnect(api_key=API_KEY)
    data = smart_api.generateSession(CLIENT_ID, PASSWORD, generate_totp())
    
    if not data['status']:
        print(f"❌ Auth Failed: {data['message']}")
        return

    print("✅ Authenticated. Searching for indices...")
    
    indices_to_find = [
        ("NSE", "Nifty 50"), 
        ("NSE", "Nifty Bank"),
        ("BSE", "SENSEX"),
        ("NSE", "NIFTY MIDCAP 100"), # Or MIDCPNIFTY
        ("NSE", "NIFTY SMALLCAP 100"),
        ("NSE", "INDIA VIX")
    ]

    # Search Logic
    # Indices often have specific trading symbols like 'Nifty 50', 'Nifty Bank' on NSE.
    # Note: NSE Indices token is usually 99926000 for Nifty 50.
    
    # Let's try to search specifically
    # Updated queries based on likely API symbols
    queries = [
        ("NSE", "Nifty 50"),
        ("NSE", "BANKNIFTY"),
        ("BSE", "SENSEX"),
        ("NSE", "MIDCPNIFTY"), 
        ("NSE", "NIFTY SMALLCAP 100"), 
        ("NSE", "Niftysmlcap100"), # Try variations
        ("NSE", "INDIA VIX")
    ]

    import time

    for exchange, query in queries:
        try:
            time.sleep(2.0) # Increased delay to 2s
            print(f"\n🔍 Searching for '{query}' on {exchange}...")
            results = smart_api.searchScrip(exchange, query)
            
            if results and 'data' in results:
                found = False
                for item in results['data']:
                    # Look for Index type symbols often starting with 999 or explicitly named
                    print(f"   - Match: {item['tradingsymbol']} ({item['symboltoken']})")
                    found = True
                
                if not found:
                    print("   No matches found.")
            else:
                print("   No data returned.")
                
        except Exception as e:
            print(f"   Error: {e}")

if __name__ == "__main__":
    main()
