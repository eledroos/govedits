import csv
import json
import logging
import os
import time
from collections import deque
import ipaddress
import re
from playwright.sync_api import sync_playwright
from datetime import datetime, timedelta, timezone
from typing import Deque, Dict, List, Set, Tuple

import requests
import requests.exceptions

from atproto import Client, models
from dateutil import parser

import colorama
colorama.init()
from typing import Optional

# Logging setup
def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    
    file_handler = logging.FileHandler(CONFIG['log_file'])
    formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(console_handler)

def detect_sensitive_content(text: str, known_ids: Set[str] = None) -> Tuple[bool, List[Tuple[str, str]]]:
    """Detect sensitive content in the provided text while excluding known IDs."""
    found_patterns = []
    known_ids = known_ids or set()

    # Phone number patterns
    for pattern in PHONE_PATTERNS:
        for match in re.finditer(pattern, text):
            matched = match.group()
            if matched not in known_ids:
                found_patterns.append(("phone_number", matched))

    # Address patterns
    for pattern in ADDRESS_PATTERNS:
        for match in re.finditer(pattern, text):
            found_patterns.append(("address", match.group()))

    return bool(found_patterns), found_patterns

def get_date_range(changes: List[Dict]) -> Optional[Tuple[datetime, datetime]]:
    """Extract the earliest and latest timestamps from a list of changes"""
    if not changes:
        return None
    
    timestamps = [parser.isoparse(c['timestamp']) for c in changes]
    return min(timestamps), max(timestamps)

def format_stats(changes: List[Dict]) -> str:
    """Generate statistics string for a batch of changes"""
    ip_count = sum(1 for c in changes if is_ip_address(c.get('user', '')))
    logged_in_count = len(changes) - ip_count
    return f"IP edits: {ip_count}, Logged-in edits: {logged_in_count}"

class ColoredFormatter(logging.Formatter):
    """Match your monitor script's colored logging"""
    COLORS = {
        logging.DEBUG: colorama.Fore.WHITE,
        logging.INFO: colorama.Fore.CYAN,
        logging.WARNING: colorama.Fore.YELLOW,
        logging.ERROR: colorama.Fore.RED,
        logging.CRITICAL: colorama.Fore.RED,
    }
    EMOJIS = {
        logging.DEBUG: "🐛 ",
        logging.INFO: "ℹ️ ",
        logging.WARNING: "⚠️ ",
        logging.ERROR: "❌ ",
        logging.CRITICAL: "💥 "
    }

    def format(self, record):
        emoji = self.EMOJIS.get(record.levelno, "🔍")
        color = self.COLORS.get(record.levelno, colorama.Fore.WHITE)
        message = super().format(record)
        return f"{color}{emoji} {message}{colorama.Style.RESET_ALL}"

# Configuration
CONFIG = {
    # Files
    "gov_ips_file": "govedits - db.csv",
    "output_csv": "historical_government_changes.csv",
    "sensitive_csv": "historical_sensitive_changes.csv",
    "state_file": "catchup_state.json",
    "log_file": "wikipedia_catchup.log",
    "screenshots_dir": "historical_screenshots",
    
    # Timing
    "days_to_fetch": 30,
    "api_delay": 1.2,        # Wikipedia API throttle
    "bluesky_delay": 15,     # Social post interval
    "queue_process_delay": 2,# Batch processing interval
    
    # API Limits
    "batch_size": 500,       # Max 500 per Wikipedia policy
    "max_retries": 5,
    
    # Features
    "enable_bluesky": True,
    "bluesky_credentials": "config.json"
}

# Add after CONFIG but before classes
PHONE_PATTERNS = [
    r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',
    r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b'
]
ADDRESS_PATTERNS = [
    r'\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b',
    r'\b(?:PO|P\.O\.) Box\s+\d+\b'
]

def sanitize_filename(filename):
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

class IPNetworkCache:
    def __init__(self):
        self.networks = {'v4': [], 'v6': []}
        self.load_government_networks()

    def normalize_ipv4(self, ip_str: str) -> str:
        """Remove leading zeros from IPv4 address octets"""
        try:
            ip_str = ip_str.strip()
            parts = ip_str.split('.')
            cleaned_parts = []
            
            for part in parts:
                part = part.strip()
                if not part:  # Handle empty octets
                    cleaned_parts.append('0')
                    continue
                    
                # Remove leading zeros and validate
                cleaned = str(int(part)) if part != '0' else '0'
                if not 0 <= int(cleaned) <= 255:
                    raise ValueError(f"Invalid octet value: {part}")
                    
                cleaned_parts.append(cleaned)
            
            if len(cleaned_parts) != 4:
                raise ValueError("Invalid IPv4 format")
                
            return '.'.join(cleaned_parts)
            
        except Exception as e:
            logging.debug(f"Error normalizing IPv4 '{ip_str}': {e}")
            return ip_str  # Return original for error tracking

    def normalize_ipv6(self, ip_str: str) -> str:
        """Normalize IPv6 addresses using ipaddress module"""
        try:
            ip_str = ip_str.strip()
            
            # Handle shorthand notation
            if '::' in ip_str:
                if ip_str.endswith('::'):
                    ip_str += '0'
                    
            # Normalize using Python's ipaddress module
            return str(ipaddress.IPv6Address(ip_str))
            
        except ValueError:
            # Fallback pattern matching for non-standard formats
            if 'ffff:ffff:ffff:ffff:ffff' in ip_str:
                return ip_str.replace('ffff:ffff:ffff:ffff:ffff', 'ffff:ffff:ffff:ffff:ffff')
            return ip_str
        except Exception as e:
            logging.debug(f"Error normalizing IPv6 '{ip_str}': {e}")
            return ip_str

    def load_government_networks(self):
        """Load and validate IP ranges from CSV"""
        try:
            with open(CONFIG['gov_ips_file'], 'r') as f:
                reader = csv.DictReader(f)
                valid_rows = 0
                
                for row in reader:
                    try:
                        org = row['organization'].strip()
                        start_ip = row['start_ip'].strip()
                        end_ip = row['end_ip'].strip()
                        
                        if not all([org, start_ip, end_ip]):
                            logging.warning(f"Skipping incomplete row: {row}")
                            continue

                        # Normalize and validate IPs
                        if ':' in start_ip:
                            start_ip = self.normalize_ipv6(start_ip)
                            end_ip = self.normalize_ipv6(end_ip)
                            start = int(ipaddress.IPv6Address(start_ip))
                            end = int(ipaddress.IPv6Address(end_ip))
                            self.networks['v6'].append((start, end, org))
                        else:
                            start_ip = self.normalize_ipv4(start_ip)
                            end_ip = self.normalize_ipv4(end_ip)
                            start = int(ipaddress.IPv4Address(start_ip))
                            end = int(ipaddress.IPv4Address(end_ip))
                            self.networks['v4'].append((start, end, org))
                            
                        valid_rows += 1
                        
                    except Exception as e:
                        logging.debug(f"Skipping invalid row for {org}: {e}")
                        continue
                        
            logging.info(
                f"{colorama.Fore.GREEN}✅ Successfully loaded government IP ranges: "
                f"{len(self.networks['v4'])} IPv4 and {len(self.networks['v6'])} IPv6"
                f"{colorama.Style.RESET_ALL}"
            )
                
        except Exception as e:
            logging.error(f"{colorama.Fore.RED}❌ Failed to load IP ranges: {e}{colorama.Style.RESET_ALL}")
            raise

    def check_ip(self, ip_str: str) -> Tuple[bool, str]:
        """Check IP against loaded ranges with normalization"""
        try:
            if ':' in ip_str:
                ip = ipaddress.IPv6Address(self.normalize_ipv6(ip_str))
                network_type = 'v6'
            else:
                ip = ipaddress.IPv4Address(self.normalize_ipv4(ip_str))
                network_type = 'v4'
                
            ip_int = int(ip)
            
            for start, end, org in self.networks[network_type]:
                if start <= ip_int <= end:
                    return True, org
            return False, ""
            
        except ValueError as e:
            logging.debug(f"Invalid IP format '{ip_str}': {e}")
            return False, ""
        except Exception as e:
            logging.warning(f"Error checking IP '{ip_str}': {e}")
            return False, ""

def is_ip_address(user: str) -> bool:
    try:
        ipaddress.ip_address(user)
        return True
    except ValueError:
        return False

def create_diff_url(rev_id, parent_id):
    return f"https://en.wikipedia.org/w/index.php?diff={rev_id}&oldid={parent_id}"

def take_screenshot(diff_url, title, timestamp):
    # Create screenshots directory if it doesn't exist
    if not os.path.exists(CONFIG['screenshots_dir']):
        os.makedirs(CONFIG['screenshots_dir'])
    
    # Create date-based subdirectory
    date_str = parser.isoparse(timestamp).strftime('%Y-%m-%d')
    date_dir = os.path.join(CONFIG['screenshots_dir'], date_str)
    if not os.path.exists(date_dir):
        os.makedirs(date_dir)
    
    # Create sanitized filename
    safe_title = sanitize_filename(title)
    timestamp_str = parser.isoparse(timestamp).strftime('%H%M%S')
    filename = f"{date_str} - {safe_title} - {timestamp_str}.png"
    filepath = os.path.join(date_dir, filename)
    
    try:
        with sync_playwright() as p:
            # Launch browser in headless mode
            browser = p.chromium.launch(headless=True)
            
            # Create context with viewport size
            context = browser.new_context(
                viewport={'width': 1000, 'height': 1920}
            )
            
            # Create page
            page = context.new_page()
            
            # Go to URL and wait for content to load
            page.goto(diff_url, wait_until="networkidle")
            
            # Wait a bit for any dynamic content
            page.wait_for_timeout(2000)
            
            # Take screenshot of top portion
            page.screenshot(
                path=filepath,
                clip={
                    'x': 0,
                    'y': 0,
                    'width': 1000,
                    'height': 1200  # Adjust this value to capture more or less
                }
            )
            
            browser.close()
        
        return filepath
    except Exception as e:
        logging.warning(f"Error taking screenshot for {title}: {str(e)}")
        return None
    
def create_facets(text: str, url: str) -> List[Dict]:
    """Create Bluesky post facets for URLs"""
    text_bytes = text.encode('utf-8')
    url_bytes = url.encode('utf-8')
    start_pos = text_bytes.find(url_bytes)
    
    if start_pos == -1:
        return []
        
    return [{
        "index": {
            "byteStart": start_pos,
            "byteEnd": start_pos + len(url_bytes)
        },
        "features": [{
            "$type": "app.bsky.richtext.facet#link",
            "uri": url
        }]
    }]

class HistoricalProcessor:
    def __init__(self):
        self.ip_cache = IPNetworkCache()
        self.state = self.load_state()

        # Validate state consistency
        if self.state["continue_token"] and not self.state["last_timestamp"]:
            logging.warning("Invalid state: continuation token without timestamp")
            self.state["continue_token"] = None

        self.queue = self.state["queue"]
        self.bluesky_client = self.init_bluesky()
        
    def init_bluesky(self):
        if not CONFIG['enable_bluesky']:
            return None
            
        try:
            with open(CONFIG['bluesky_credentials']) as f:
                creds = json.load(f)
            client = Client()
            client.login(creds['email'], creds['password'])
            return client
        except Exception as e:
            logging.error(f"Bluesky init failed: {e}")
            return None
        
    def log_batch_details(self, changes: List[Dict]):
        """Log detailed information about a batch of changes"""
        if not changes:
            logging.debug("No changes in this batch")
            return
            
        # Date range logging
        date_range = get_date_range(changes)
        if date_range:
            start, end = date_range
            logging.info(f"📅 Processing changes from {start.isoformat()} to {end.isoformat()}")
        
        # Statistics logging
        logging.info(f"📊 Batch stats: {format_stats(changes)}")
        
        # First 3 changes debug logging
        logging.debug("Sample changes (first 3):")
        for i, change in enumerate(changes[:3]):
            user_type = "IP" if is_ip_address(change.get('user', '')) else "Logged-in"
            logging.debug(f"  {i+1}. {change.get('title', '')} ({user_type}: {change.get('user', '')})")

        # First 3 IP checks debug logging
        ip_edits = [c for c in changes if is_ip_address(c.get('user', ''))]
        logging.debug("Sample IP checks (first 3):")
        for i, edit in enumerate(ip_edits[:3]):
            is_gov, org = self.ip_cache.check_ip(edit.get('user', ''))
            gov_status = colorama.Fore.GREEN + "GOV" if is_gov else colorama.Fore.RED + "NON-GOV"
            logging.debug(f"  {i+1}. {edit.get('user', '')}: {gov_status}{colorama.Style.RESET_ALL} → {org}")

    def load_state(self) -> Dict:
        default_state = {
            "last_timestamp": None,
            "processed_rcids": set(),
            "continue_token": None,
            "queue": []
        }
        
        try:
            with open(CONFIG['state_file'], 'r') as f:
                state = json.load(f)
                loaded_state = {
                    "last_timestamp": state.get("last_timestamp"),
                    "processed_rcids": set(state.get("processed_rcids", [])),
                    "continue_token": state.get("continue_token"),
                    "queue": deque(state.get("queue", []))
                }
                
                # Validate timestamp format
                if loaded_state["last_timestamp"]:
                    try:
                        parser.isoparse(loaded_state["last_timestamp"])
                    except:
                        logging.warning("Invalid timestamp in state, resetting")
                        loaded_state["last_timestamp"] = None
                
                # Validate token and timestamp coherence
                if loaded_state["continue_token"] and not loaded_state["last_timestamp"]:
                    logging.warning("Invalid state: token without timestamp, resetting")
                    loaded_state["continue_token"] = None 
                        
                return loaded_state
        except FileNotFoundError:
            return default_state
        except Exception as e:
            logging.error(f"State load error: {e}")
            return default_state

    def save_state(self):
        state = {
            "last_timestamp": self.state["last_timestamp"],
            "processed_rcids": list(self.state["processed_rcids"]),
            "continue_token": self.state["continue_token"],
            "queue": list(self.state["queue"])
        }
        
        with open(CONFIG['state_file'], 'w') as f:
            json.dump(state, f)

    def fetch_historical_changes(self) -> Tuple[List[Dict], str]:
        """Fetch changes with enhanced logging"""
        params = {
            "action": "query",
            "list": "recentchanges",
            "rcprop": "title|ids|sizes|flags|user|timestamp|comment|revid|parentid",
            "rcshow": "!bot",
            "rclimit": CONFIG['batch_size'],
            "format": "json",
            "rcdir": "newer",
            "rcstart": (parser.isoparse(self.state["last_timestamp"]) 
                    if self.state["last_timestamp"] 
                    else datetime.now(timezone.utc) - timedelta(days=CONFIG['days_to_fetch'])).isoformat(),
            "rcend": datetime.now(timezone.utc).isoformat(),
        }

        retries = 0
        max_retries = 3
        backoff_factor = 1.5
        
        while retries <= max_retries:
            try:
                response = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params=params,
                    timeout=60  # Increased timeout
                )
                response.raise_for_status()
                data = response.json()
                
                changes = data.get("query", {}).get("recentchanges", [])
                continue_token = data.get("continue", {}).get("rccontinue")
                
                # Save state immediately after successful fetch
                # Update BOTH timestamp and token atomically
                if changes:
                    logging.info(f"🌐 Fetched {len(changes)} changes")
                    new_timestamp = max(parser.isoparse(c['timestamp']) for c in changes)
                    self.state["last_timestamp"] = new_timestamp.isoformat()
                    self.state["continue_token"] = continue_token
                    self.save_state() 
                
                return changes, continue_token
                
            except requests.exceptions.Timeout as e:
                logging.error(f"⏳ Timeout fetching changes: {e}")
                # Clear continuation token as it may be invalid after timeout
                self.state["continue_token"] = None
                self.save_state()
                raise  # Re-raise to trigger retry logic
                
            except requests.exceptions.RequestException as e:
                logging.error(f"🌐 Network error: {e}")
                self.state["continue_token"] = None  # Reset token
                self.save_state()
                raise
                
            except Exception as e:
                logging.error(f"❌ Unexpected error: {e}")
                if 'last_timestamp' in self.state:
                    self.state["continue_token"] = None  # Clear potentially bad token
                    self.save_state()
                raise

    def process_changes(self, changes: List[Dict]):
        """Process a batch of changes with comprehensive logging"""
        # Log date range of this batch
        date_range = get_date_range(changes)
        if date_range:
            start, end = date_range
            logging.info(
                f"{colorama.Fore.CYAN}📅 Processing {len(changes)} changes from "
                f"{start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%Y-%m-%d %H:%M')}"
                f"{colorama.Style.RESET_ALL}"
            )

        # Calculate and log user statistics
        ip_edits = [c for c in changes if is_ip_address(c.get('user', ''))]
        logged_in_edits = len(changes) - len(ip_edits)
        logging.info(
            f"{colorama.Fore.MAGENTA}📊 User Statistics:{colorama.Style.RESET_ALL}\n"
            f"  • IP Address Edits: {colorama.Fore.YELLOW}{len(ip_edits)}{colorama.Style.RESET_ALL}\n"
            f"  • Logged-in User Edits: {colorama.Fore.YELLOW}{logged_in_edits}{colorama.Style.RESET_ALL}"
        )

        # Log sample changes
        if changes:
            logging.debug(f"{colorama.Fore.WHITE}🐛 Sample Changes (first 3):{colorama.Style.RESET_ALL}")
            for i, change in enumerate(changes[:3]):
                user_type = ("IP" if is_ip_address(change.get('user', '')) 
                            else "Logged-in")
                title = change.get('title', 'Untitled')
                user = change.get('user', 'Unknown')
                logging.debug(
                    f"  {i+1}. {colorama.Fore.CYAN}{title}{colorama.Style.RESET_ALL}\n"
                    f"     {colorama.Fore.MAGENTA}User:{colorama.Style.RESET_ALL} {user} ({user_type})\n"
                    f"     {colorama.Fore.YELLOW}Timestamp:{colorama.Style.RESET_ALL} {change.get('timestamp', '')}"
                )

        # Filter government edits
        gov_edits = []
        for change in changes:
            if str(change.get('rcid', '')) in self.state["processed_rcids"]:
                continue
                
            user = change.get('user', '')
            if is_ip_address(user):
                is_gov, org = self.ip_cache.check_ip(user)
                if is_gov:
                    gov_edits.append(change)

        # Government edit logging
        if gov_edits:
            self.log_government_edits(gov_edits)
            logging.info(
                f"{colorama.Fore.GREEN}✅ Found {len(gov_edits)} government edits "
                f"in this batch{colorama.Style.RESET_ALL}"
            )
        else:
            logging.info(
                f"{colorama.Fore.YELLOW}⚠️  No government edits found in this batch"
                f"{colorama.Style.RESET_ALL}"
            )

        # Log IP check samples
        if ip_edits:
            logging.debug(f"{colorama.Fore.WHITE}🔍 IP Check Samples (first 3):{colorama.Style.RESET_ALL}")
            for i, edit in enumerate(ip_edits[:3]):
                ip = edit.get('user', '')
                is_gov, org = self.ip_cache.check_ip(ip)
                status = (
                    f"{colorama.Fore.GREEN}GOVERNMENT{colorama.Style.RESET_ALL}"
                    if is_gov else 
                    f"{colorama.Fore.RED}NON-GOVERNMENT{colorama.Style.RESET_ALL}"
                )
                logging.debug(
                    f"  {i+1}. {colorama.Fore.CYAN}{ip}{colorama.Style.RESET_ALL}\n"
                    f"     {colorama.Fore.MAGENTA}Status:{colorama.Style.RESET_ALL} {status}\n"
                    f"     {colorama.Fore.BLUE}Organization:{colorama.Style.RESET_ALL} {org}"
                )

        # Add government edits to processing queue
        for edit in gov_edits:
            self.queue.append({
                "data": edit,
                "screenshot": None,
                "posted": False
            })

        # Update processed IDs and timestamp
        if gov_edits:
            self.state["processed_rcids"].update(str(e.get('rcid', '')) for e in gov_edits)
            timestamps = [parser.isoparse(e['timestamp']) for e in gov_edits]
            self.state["last_timestamp"] = max(timestamps).isoformat()

    def process_queue(self):
        total_processed = 0
        while self.queue:
            item = self.queue.popleft()
            total_processed += 1

            try:
                # Take screenshot
                if not item["screenshot"]:
                    diff_url = create_diff_url(
                        item["data"]["revid"], 
                        item["data"].get("parentid")
                    )
                    item["screenshot"] = take_screenshot(
                        diff_url,
                        item["data"]["title"],
                        item["data"]["timestamp"]
                    )
                
                # Save to CSV
                self.save_to_csv(item["data"])
                
                # Post to Bluesky
                if not item["posted"] and self.bluesky_client:
                    self.post_to_bluesky(item)
                    item["posted"] = True
                    time.sleep(CONFIG['bluesky_delay'])
                    
            except Exception as e:
                logging.error(f"Queue item failed: {e}")
                self.queue.appendleft(item)
                break
                
            total_processed += 1

            if total_processed % 10 == 0:
                logging.info(
                    f"{colorama.Fore.CYAN}📦 Queue progress: "
                    f"Processed {total_processed} items, {len(self.queue)} remaining"
                    f"{colorama.Style.RESET_ALL}"
                )

            # Update state periodically
            if len(self.queue) % 10 == 0:
                self.save_state()

    def log_government_edits(self, gov_edits: List[Dict]):
        if not gov_edits:
            return
        
        logging.info("\n🚨🚨🚨 HISTORICAL GOVERNMENT EDIT DETECTED 🚨🚨🚨")
        for change in gov_edits:
            ip = change.get('user', '')
            is_gov, org = self.ip_cache.check_ip(ip)
            timestamp = parser.isoparse(change.get('timestamp', '')).strftime('%Y-%m-%d %H:%M:%S')
            
            logging.info(
                f"{colorama.Fore.CYAN}📌 Title: {colorama.Style.RESET_ALL}{change.get('title', '')}\n"
                f"{colorama.Fore.MAGENTA}🖥️ IP: {colorama.Style.RESET_ALL}{ip}\n"
                f"{colorama.Fore.GREEN}🏢 Organization: {colorama.Style.RESET_ALL}{org}\n"
                f"{colorama.Fore.YELLOW}⏰ Time: {colorama.Style.RESET_ALL}{timestamp}\n"
                f"{colorama.Fore.BLUE}💬 Comment: {colorama.Style.RESET_ALL}{change.get('comment', '')[:100]}..."
            )
        logging.info("🔔🔔🔔 END OF GOVERNMENT ALERT 🔔🔔🔔\n")
    
    def save_to_csv(self, change: Dict):
        file_exists = os.path.exists(CONFIG['output_csv'])
        
        with open(CONFIG['output_csv'], 'a') as f, \
             open(CONFIG['sensitive_csv'], 'a') as s:
            
            writer = csv.writer(f)
            sensitive_writer = csv.writer(s)
            
            if not file_exists:
                writer.writerow([
                    "Title", "IP Address", "Government Organization", "Timestamp", 
                    "Edit ID", "Old Size", "New Size", "Revision ID", "Parent ID", 
                    "Diff URL", "Comment", "Screenshot Path", "Contains Sensitive Info"
                ])
                sensitive_writer.writerow([
                    "Title", "IP Address", "Government Organization", "Timestamp", 
                    "Edit ID", "Diff URL", "Comment", "Sensitive Content Types"
                ])
            
            comment = change.get("comment", "")
            known_ids = {str(change.get("revid", "")), str(change.get("parentid", ""))}
            is_sensitive, content_matches = detect_sensitive_content(comment, known_ids)

            screenshot_path = self.queue[0]["screenshot"] if self.queue else ""
            
            writer.writerow([
                change.get("title", ""),
                change.get("user", ""),
                self.ip_cache.check_ip(change.get("user", ""))[1],  # Organization
                change.get("timestamp", ""),
                change.get("rcid", ""),
                change.get("oldlen", ""),
                change.get("newlen", ""),
                change.get("revid", ""),
                change.get("parentid", ""),
                create_diff_url(change.get("revid", ""), change.get("parentid", "")),
                comment,
                screenshot_path,
                "Yes" if is_sensitive else "No"
            ])

            if is_sensitive:
                sensitive_writer.writerow([
                    change.get("title", ""),
                    change.get("user", ""),
                    self.ip_cache.check_ip(change.get("user", ""))[1],
                    change.get("timestamp", ""),
                    change.get("rcid", ""),
                    create_diff_url(change.get("revid", ""), change.get("parentid", "")),
                    comment,
                    ", ".join([m[0] for m in content_matches])
                ])
    def create_facets(text: str, url: str) -> List[Dict]:
        """Create Bluesky facets for URLs identical to monitor script's implementation"""
        facets = []
        text_bytes = text.encode('utf-8')
        url_bytes = url.encode('utf-8')
        
        # Find URL position in text
        start_pos = text_bytes.find(url_bytes)
        if start_pos != -1:
            facets.append({
                "index": {
                    "byteStart": start_pos,
                    "byteEnd": start_pos + len(url_bytes)
                },
                "features": [{
                    "$type": "app.bsky.richtext.facet#link",
                    "uri": url
                }]
            })
        
        return facets

    def post_to_bluesky(self, item: Dict):
        try:
            # Extract required fields
            change_data = item['data']
            title = change_data.get('title', 'Untitled')
            user_ip = change_data.get('user', '')
            rev_id = change_data.get('revid', '')
            parent_id = change_data.get('parentid', '')
            timestamp = change_data.get('timestamp', '')

            # Format the date
            try:
                edit_date = parser.isoparse(timestamp).strftime('%Y-%m-%d')
            except:
                edit_date = "unknown date"

            # Get organization from IP
            _, org = self.ip_cache.check_ip(user_ip)
            diff_url = create_diff_url(rev_id, parent_id)
            
            # Create post text
            text = (
                f"{title} Wikipedia article edited anonymously from {org} on {edit_date}.\n\n"
                f"{diff_url}"
            )
            
            facets = create_facets(text, diff_url)
            
            if item['screenshot'] and os.path.exists(item['screenshot']):
                try:
                    with open(item['screenshot'], "rb") as f:
                        img_data = f.read()
                    upload = self.bluesky_client.com.atproto.repo.upload_blob(img_data)
                    embed = models.AppBskyEmbedImages.Main(
                        images=[models.AppBskyEmbedImages.Image(
                            alt=f"Screenshot of edit for {title}",
                            image=upload.blob
                        )]
                    )
                    self.bluesky_client.send_post(text=text, facets=facets, embed=embed)
                except Exception as e:
                    logging.warning(f"Image upload failed: {e}")
                    self.bluesky_client.send_post(text=text, facets=facets)
            else:
                self.bluesky_client.send_post(text=text, facets=facets)
                
            logging.info(f"Posted to Bluesky: {text[:100]}...")
            
        except Exception as e:
            logging.error(f"Bluesky post failed: {e}")

    def run(self):
        setup_logging()
        logging.info(f"{colorama.Fore.CYAN}🚀 Starting historical processing (last 30 days){colorama.Style.RESET_ALL}")
        
        try:
            # Process existing queue first
            if self.queue:
                logging.info(f"Resuming with {len(self.queue)} queued items")
                self.process_queue()
            
            # Main processing loop
            while True:
                changes, continue_token = self.fetch_historical_changes()
                self.state["continue_token"] = continue_token
                
                if not changes:
                    logging.info("✅ No more changes found")
                    break
                
                self.process_changes(changes)
                self.process_queue()
                self.save_state()
                
                time.sleep(CONFIG['api_delay'])
                
                # Progress logging
                if self.state["last_timestamp"]:
                    processed_time = parser.isoparse(self.state["last_timestamp"])
                    time_diff = datetime.now(timezone.utc) - processed_time
                    logging.info(f"⏳ Processed up to {processed_time} ({time_diff.days} days remaining)")
                
                # Check if caught up
                if continue_token is None:
                    break

            # Cleanup
            if os.path.exists(CONFIG['state_file']):
                os.remove(CONFIG['state_file'])
                
            logging.info(
                f"{colorama.Fore.GREEN}✅ Historical processing complete! "
                f"Found {len(self.state['processed_rcids'])} government edits."
                f"{colorama.Style.RESET_ALL}"
            )

        except KeyboardInterrupt:
            logging.info("Interrupted - saving state")
            self.save_state()
        except Exception as e:
            logging.error(f"Fatal error: {e}")
            self.save_state()

if __name__ == "__main__":
    processor = HistoricalProcessor()
    processor.run()