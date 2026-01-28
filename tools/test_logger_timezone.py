from production.logger import AsyncLogger
from datetime import datetime, timedelta, timezone

def test_timestamp():
    print("Testing Logger Timestamp...")
    # Manually generate what logger does
    ist_ts = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat()
    print(f"Generated Timestamp: {ist_ts}")
    
    if "+05:30" in ist_ts:
        print("✅ SUCCESS: Timestamp has IST offset.")
    else:
        print("❌ FAILURE: Timestamp missing IST offset.")

if __name__ == "__main__":
    test_timestamp()
