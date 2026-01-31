import time
import threading
import feedparser
import ssl

# Bypass SSL verification for legacy macOS Python environments
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

# Global variable to store the latest news string
# Accessed by server.py to include in WebSocket broadcast
latest_news_str = "⌛ Initializing News Feed..."
latest_news_timestamp = 0  # Epoch timestamp of last successful fetch

# Configuration
RSS_URL = "https://news.google.com/rss/search?q=(Nifty+OR+Sensex+OR+Bank+Nifty)+AND+(RBI+OR+GDP+OR+Budget+OR+Quarterly+Results+OR+Q3+Results+OR+Earnings)&hl=en-IN&gl=IN&ceid=IN:en"
FETCH_INTERVAL = 60  # 1 Minute (Dynamic Updates)

def fetch_news():
    """
    Background task to fetch news from RSS feed.
    Updates the global `latest_news_str` safely.
    """
    global latest_news_str
    
    while True:
        try:
            print(f"📰 [NewsEngine] Fetching latest market news...")
            # Use `agent` parameter to prevent 403 Forbidden from Google
            feed = feedparser.parse(RSS_URL, agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            if not feed.entries:
                print("⚠️ [NewsEngine] No entries found in RSS feed.")
                # Keep previous news or set generic message if empty for too long? 
                # Better to keep previous if transient failure, but if fresh start, maybe "No major news".
                # For now, just skip update if empty to preserve old data if exists.
                if latest_news_str == "⌛ Initializing News Feed...":
                     latest_news_str = "Market is Quiet. No major headlines."
            else:
                # Extract Top 5 Unique Headlines
                headlines = []
                seen_titles = set()
                
                for entry in feed.entries:
                    title = entry.title
                    source = "Unknown Source"
                    
                    # Google News often puts source at the end: "Headline - SourceName"
                    if " - " in title:
                        parts = title.rsplit(" - ", 1)
                        title = parts[0]
                        source = parts[1]
                    elif hasattr(entry, 'source') and hasattr(entry.source, 'title'):
                        source = entry.source.title
                    
                    # Cleanup: Remove HTML tags if any (basic check)
                    title = title.replace("<b>", "").replace("</b>", "")
                    
                    # Deduplication
                    if title not in seen_titles:
                        # Store as "Headline###Source" for frontend parsing
                        headlines.append(f"{title}###{source}")
                        seen_titles.add(title)
                    
                    if len(headlines) >= 10: # Increased to 10
                        break
                
                # Format: "HEADLINE|SOURCE  ✦  HEADLINE|SOURCE..."
                if headlines:
                    new_news_str = "  ✦  ".join(headlines)
                    
                    global latest_news_timestamp
                    latest_news_str = new_news_str
                    latest_news_timestamp = time.time()
                    print(f"✅ [NewsEngine] Updated {len(headlines)} headlines at {time.ctime(latest_news_timestamp)}.")
                else:
                    print("⚠️ [NewsEngine] Parsed feed but found no valid headlines.")

        except Exception as e:
            print(f"❌ [NewsEngine] Error fetching news: {e}")
            # Fail silently, keep old news or "Error" state?
            # Requirement: "fail silently". Keep old news.
            pass
        
        # Sleep for 5 minutes
        time.sleep(FETCH_INTERVAL)

def start_news_engine():
    """
    Starts the news fetching engine in a background daemon thread.
    This ensures it does not block the main server loop.
    """
    news_thread = threading.Thread(target=fetch_news, daemon=True)
    news_thread.name = "NewsFetcherThread"
    news_thread.start()
    print("🚀 [NewsEngine] Started Background Service.")

if __name__ == "__main__":
    # Test Run
    start_news_engine()
    while True:
        print(f"Current News: {latest_news_str}")
        time.sleep(10)
