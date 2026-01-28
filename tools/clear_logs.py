import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

# Add parent directory to path to find .env if needed, though we load directly below
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))

# Load .env
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

def clear_logs():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")

    if not url or not key:
        print("❌ Error: SUPABASE_URL or SUPABASE_KEY missing in .env")
        return

    try:
        supabase: Client = create_client(url, key)
        print("🔌 Connected to Supabase...")
        
        # Delete all rows from 'trade_logs'
        # Note: .delete().neq("id", 0) is a common way to delete all if logic requires a filter
        # Or .delete().grid() depending on library version, but usually filter is needed.
        # "id" > -1 covers all positives. 
        # Assuming 'id' column exists.
        
        print("🗑️  Clearing 'trade_logs' table...")
        response = supabase.table("trade_logs").delete().neq("id", -1).execute()
        
        # Determine count of deleted items if possible, or just success
        # Response format depends on supabase-py version.
        try:
             # Check if response has data
             if hasattr(response, 'data'):
                 count = len(response.data)
                 print(f"✅ Successfully cleared {count} log entries.")
             else:
                 print("✅ Logs cleared (No data returned count).")
        except:
             print("✅ Logs cleared.")

    except Exception as e:
        print(f"❌ Error clearing logs: {e}")

if __name__ == "__main__":
    confirm = input("⚠️  Are you sure you want to DELETE ALL trade logs? (y/n): ")
    if confirm.lower() == 'y':
        clear_logs()
    else:
        print("Operation cancelled.")
