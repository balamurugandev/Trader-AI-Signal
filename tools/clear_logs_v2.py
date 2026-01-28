import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client

project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
env_path = project_root / ".env"
load_dotenv(dotenv_path=env_path)

def clear_logs():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key: return

    try:
        supabase: Client = create_client(url, key)
        supabase.table("trade_logs").delete().neq("id", -1).execute()
        print("✅ Logs cleared.")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    clear_logs()
