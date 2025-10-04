"""
Centralized configuration for Government Wikipedia Edit Monitor
"""
import os

# File Paths
GOV_IPS_FILE = os.path.join(os.path.dirname(__file__), "govedits - db.csv")
CONFIG_FILE = "config.json"
SCREENSHOTS_DIR = "data/screenshots"

# Wikipedia API
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_DIFF_BASE_URL = "https://en.wikipedia.org/w/index.php"

# API Parameters
WIKIPEDIA_RC_PARAMS = {
    "action": "query",
    "list": "recentchanges",
    "rcprop": "title|ids|sizes|flags|user|timestamp|comment|revid|parentid",
    "rcshow": "!bot",
    "rclimit": 500,
    "format": "json",
    "rcdir": "newer",
}

# Timing
API_DELAY = 1.2  # Wikipedia API throttle
BLUESKY_DELAY = 15  # Social post interval
QUEUE_PROCESS_DELAY = 2  # Batch processing interval
REALTIME_POLL_INTERVAL = 10  # Real-time monitoring interval (seconds)

# Features
ENABLE_BLUESKY_POSTING = True

# Content Detection Patterns
PHONE_PATTERNS = [
    r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # US/Canada: 123-456-7890
    r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b'  # (123) 456-7890
]

ADDRESS_PATTERNS = [
    r'\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b',
    r'\b(?:PO|P\.O\.) Box\s+\d+\b'
]

# Government Filter Levels
FILTER_ALL = "all"  # All government agencies (1,749 total)
FILTER_FEDERAL = "federal"  # Federal agencies only (372 total)
FILTER_CONGRESS = "congress"  # Congressional IPs only (House + Senate)

# Default Settings
DEFAULT_FILTER = FILTER_FEDERAL
DEFAULT_DAYS_TO_FETCH = 30
