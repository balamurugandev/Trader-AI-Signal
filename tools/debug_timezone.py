from datetime import datetime, timedelta, timezone
import time

def debug_time():
    print("--- Timezone Debug ---")
    
    # 1. Naive Now
    naive_now = datetime.now()
    print(f"Naive Now: {naive_now}")
    
    # 2. UTC Now
    utc_now = datetime.utcnow()
    print(f"UTC Now:   {utc_now}")
    
    # 3. IST using my previous logic
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    my_logic = datetime.now(ist_tz)
    print(f"Logger Logic: {my_logic}")
    
    # 4. UTC -> IST conversion (Robust way)
    robust_ist = datetime.now(timezone.utc).astimezone(ist_tz)
    print(f"Robust IST:   {robust_ist}")
    
    # Check offsets
    if my_logic.hour > naive_now.hour + 4:
         print("⚠️  WARNING: 'Logger Logic' seems to be ~5.5h ahead of Naive Now!")
         print("   This happens if system is ALREADY IST, and we ask for IST again in a specific way?")

if __name__ == "__main__":
    debug_time()
