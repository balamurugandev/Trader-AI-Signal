import threading
import queue
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables relative to this file
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# Configure logger for this module
logger = logging.getLogger("TradeLogger")
logger.setLevel(logging.INFO)

class AsyncLogger:
    """
    "Fire-and-Forget" Trade Logger.
    
    Design Features:
    1. Bounded Queue: maxsize=100 Limits RAM usage.
    2. Non-Blocking: Uses put_nowait() to drop logs if queue is full.
    3. Background Worker: Daemon thread handles Supabase inserts.
    4. Fail-Safe: Survived Supabase connection failures.
    """
    def __init__(self):
        self.log_queue = queue.Queue(maxsize=100)
        self.supabase = None
        self.is_active = False
        
        # Initialize Supabase (Fail-Safe)
        self._init_supabase()
        
        # Start Background Worker
        self.worker_thread = threading.Thread(target=self._worker, daemon=True, name="LoggerWorker")
        self.worker_thread.start()
        
    def _init_supabase(self):
        """Attempts to connect to Supabase. Fails gracefully."""
        try:
            from supabase import create_client, Client
            
            url = os.environ.get("SUPABASE_URL")
            key = os.environ.get("SUPABASE_KEY")
            
            if not url or not key:
                logger.warning("⚠️ TradeLogger: SUPABASE_URL or SUPABASE_KEY missing. Logging disabled.")
                return

            self.supabase: Client = create_client(url, key)
            self.is_active = True
            logger.info("✅ TradeLogger: Connected to Supabase.")
            
        except ImportError as e:
            logger.error(f"❌ TradeLogger: 'supabase' library missing or broken. Error: {e}")
        except Exception as e:
            logger.error(f"❌ TradeLogger: Connection failed - {e}")

    def log_trade(self, spot: float, basis: float, pcr: float, signal: str, trap_reason: str,
                  ce_symbol: str = None, pe_symbol: str = None, ce_price: float = None, pe_price: float = None):
        """
        Non-blocking log entry.
        """
        if not self.is_active:
            return

        payload = {
            "timestamp": datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(),
            "spot_price": spot,
            "basis": basis,
            "pcr": pcr,
            "signal": signal,
            "trap_reason": trap_reason,
            "ce_symbol": ce_symbol,
            "pe_symbol": pe_symbol,
            "ce_price": ce_price,
            "pe_price": pe_price
        }

        try:
            # FIRE AND FORGET: If queue is full, DROP the data.
            # Do NOT block the main thread.
            self.log_queue.put_nowait(payload)
        except queue.Full:
            # Queue is full (Database slow or Network down).
            # Silently drop the log to save the Trading Engine.
            pass

    def _worker(self):
        """Background thread to process logs."""
        while True:
            try:
                # Block here, waiting for items
                payload = self.log_queue.get()
                
                if payload is None:
                    break

                # Sync Insert (Allowed here, as we are in a background thread)
                if self.supabase:
                    self.supabase.table('trade_logs').insert(payload).execute()
                
                self.log_queue.task_done()
                
            except Exception as e:
                logger.error(f"⚠️ TradeLogger Worker Error: {e}")

# Global Instance
trade_logger = AsyncLogger()
