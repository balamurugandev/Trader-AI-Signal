
from datetime import datetime, timedelta

def parse_expiry_from_symbol(symbol: str):
    import re
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

def check_expiry():
    # TEST CASE 1: 27 JAN 2026 (Expired)
    symbol_expired = "NIFTY27JAN2625050CE"
    expiry_expired = parse_expiry_from_symbol(symbol_expired)
    
    # TEST CASE 2: 05 FEB 2026 (Future)
    symbol_future = "NIFTY05FEB2625050CE"
    expiry_future = parse_expiry_from_symbol(symbol_future)

    # CURRENT MOCK TIME: 28 Jan 2026 00:15 IST
    mock_now_utc = datetime(2026, 1, 27, 18, 45) # 27 Jan 18:45 UTC
    ist_now = mock_now_utc + timedelta(hours=5, minutes=30) # 28 Jan 00:15 IST
    
    print(f"MOCK IST NOW: {ist_now.strftime('%d-%b-%Y %H:%M:%S')}")
    
    today_midnight = ist_now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # LOGIC CHECK
    print(f"\n--- 27 JAN CHECK ---")
    print(f"Expiry: {expiry_expired}")
    is_valid = expiry_expired >= today_midnight
    print(f"Is Valid (>= Today): {is_valid}") # Should be FALSE
    
    print(f"\n--- 05 FEB CHECK ---")
    print(f"Expiry: {expiry_future}")
    is_valid = expiry_future >= today_midnight
    print(f"Is Valid (>= Today): {is_valid}") # Should be TRUE

if __name__ == "__main__":
    check_expiry()
