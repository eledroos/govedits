import asyncio
import csv
import ipaddress
import json
import logging
import os
import piexif
import re
import requests
import time
from atproto import Client, models
from datetime import datetime, timedelta, timezone
from dateutil import parser
from playwright.sync_api import sync_playwright
from typing import Dict, Set, Union
from typing import List, Tuple
import colorama

colorama.init()

# Add this class definition near the top
class ColoredFormatter(logging.Formatter):
    """Adds colors and emojis to console logging"""
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

# Suppress HTTP request logging
logging.getLogger("httpx").setLevel(logging.WARNING)  # If `httpx` is used by the library
logging.getLogger("urllib3").setLevel(logging.WARNING)  # If `urllib3` is used

CONFIG_FILE = "config.json"
GOV_IPS_FILE = "govedits - db.csv"
LOG_FILE = "wikipedia_monitor.log"
OUTPUT_CSV = "government_changes.csv"
SCREENSHOTS_DIR = "diff_screenshots"
SENSITIVE_CHANGES_CSV = "sensitive_content_changes.csv"
STATE_FILE = "last_run_state.json"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_DIFF_BASE_URL = "https://en.wikipedia.org/w/index.php"

# Enable or disable posting to Bluesky
ENABLE_BLUESKY_POSTING = False

# Content Detection Patterns
PHONE_PATTERNS = [
    r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b',  # US/Canada: 123-456-7890
    r'\b\(\d{3}\)\s*\d{3}[-.]?\d{4}\b'  # (123) 456-7890
]
ADDRESS_PATTERNS = [
    r'\b\d+\s+[A-Za-z\s]+(?:Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Lane|Ln|Drive|Dr)\b',
    r'\b(?:PO|P\.O\.) Box\s+\d+\b'
]

# Wikipedia RC API Params
params = {
    "action": "query",
    "list": "recentchanges",
    "rcprop": "title|ids|sizes|flags|user|timestamp|comment|revid|parentid",
    "rcshow": "!bot",
    "rclimit": 500,
    "format": "json",
    "rcdir": "newer",
}

def setup_logging():
    """Configure logging with both file and colored console output"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # File handler (plain text)
    file_handler = logging.FileHandler(LOG_FILE)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler (colored)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(ColoredFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(console_handler)

def detect_sensitive_content(text: str, known_ids: Set[str] = None) -> Tuple[bool, List[Tuple[str, str]]]:
    """
    Detect sensitive content in the provided text while excluding known IDs.

    Args:
        text (str): The text to analyze.
        known_ids (Set[str]): Set of known IDs (e.g., revision IDs) to exclude from detection.

    Returns:
        Tuple[bool, List[Tuple[str, str]]]: A tuple where the first element indicates if sensitive
                                             content was found, and the second is a list of
                                             tuples containing the type and the matched content.
    """
    found_patterns = []
    known_ids = known_ids or set()

    # Log known IDs for debugging
    logging.debug(f"Known IDs to exclude: {known_ids}")

    # Check for phone numbers
    for pattern in PHONE_PATTERNS:
        for match in re.finditer(pattern, text):
            matched_content = match.group()
            if matched_content not in known_ids:
                logging.debug(f"Matched phone number: {matched_content}")
                found_patterns.append(("phone_number", matched_content))
            else:
                logging.debug(f"Excluded known ID: {matched_content}")

    # Check for addresses
    for pattern in ADDRESS_PATTERNS:
        for match in re.finditer(pattern, text):
            matched_content = match.group()
            found_patterns.append(("address", matched_content))

    return bool(found_patterns), found_patterns

class IPNetworkCache:
    def __init__(self):
        self.networks = {
            'v4': [],  # List of tuples: (start_ip, end_ip, organization)
            'v6': []
        }
        self.load_government_networks()

    def normalize_ipv4(self, ip_str: str) -> str:
        """Remove leading zeros from IPv4 address octets"""
        try:
            # First, handle any potential format issues
            ip_str = ip_str.strip()
            
            # Replace multiple zeros with single zeros
            parts = ip_str.split('.')
            
            # Ensure all parts are valid numbers
            cleaned_parts = []
            for part in parts:
                if part.strip() == '':
                    cleaned_parts.append('0')  # Replace empty parts with '0'
                else:
                    # Remove leading zeros and ensure it's a valid number
                    cleaned_parts.append(str(int(part)))
                    
            return '.'.join(cleaned_parts)
        except Exception as e:
            logging.debug(f"Error normalizing IPv4 address '{ip_str}': {e}")
            return ip_str  # Return original if normalization fails


    def normalize_ipv6(self, ip_str: str) -> str:
        """Normalize IPv6 addresses"""
        try:
            # Remove any spaces
            ip_str = ip_str.strip()
            
            # If it ends with :: add zeros
            if ip_str.endswith('::'):
                ip_str = ip_str + '0'
                
            # Handle ffff format
            if 'ffff:ffff:ffff:ffff:ffff' in ip_str:
                return ip_str.replace('ffff:ffff:ffff:ffff:ffff', 'ffff:ffff:ffff:ffff:ffff')
            
            # Try to normalize using ipaddress module
            try:
                normalized = str(ipaddress.IPv6Address(ip_str))
                return normalized
            except:
                return ip_str  # Return original if can't normalize with ipaddress
                
            return ip_str
        except Exception as e:
            logging.warning(f"Error normalizing IPv6 address {ip_str}: {e}")
            return ip_str  # Return original if can't normalize

    def load_government_networks(self):
        try:
            with open(GOV_IPS_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        start_ip = row.get('start_ip', '').strip()
                        end_ip = row.get('end_ip', '').strip()
                        org = row.get('organization', '').strip()

                        if not start_ip or not end_ip or not org:
                            logging.warning(f"Skipping row with missing data: {row}")
                            continue

                        # Check if it's IPv6 (contains ::)
                        if '::' in start_ip:
                            try:
                                start = ipaddress.IPv6Address(self.normalize_ipv6(start_ip))
                                end = ipaddress.IPv6Address(self.normalize_ipv6(end_ip))
                                self.networks['v6'].append((int(start), int(end), org))
                            except Exception as e:
                                logging.warning(f"Error processing IPv6 range for {org}: {start_ip} - {end_ip}: {e}")
                        else:
                            # Handle IPv4 addresses
                            try:
                                # Remove leading zeros from octets
                                start_ip = self.normalize_ipv4(start_ip)
                                end_ip = self.normalize_ipv4(end_ip)
                                
                                start = ipaddress.IPv4Address(start_ip)
                                end = ipaddress.IPv4Address(end_ip)
                                self.networks['v4'].append((int(start), int(end), org))
                            except Exception as e:
                                logging.warning(f"Error processing IPv4 range for {org}: {start_ip} - {end_ip}: {e}")

                    except Exception as e:
                        logging.warning(f"Error processing IP range: {e}")
                        
            logging.info(f"Loaded {len(self.networks['v4'])} IPv4 ranges and {len(self.networks['v6'])} IPv6 ranges")
        except Exception as e:
            logging.error(f"Error loading government networks: {e}")


    def check_ip(self, ip_str: str) -> tuple[bool, str]:
        """Check if an IP is within any of our ranges"""
        try:
            # Try to normalize the IP address
            try:
                if ':' in ip_str:  # IPv6
                    ip_str = self.normalize_ipv6(ip_str)
                else:  # IPv4
                    ip_str = self.normalize_ipv4(ip_str)
            except:
                pass  # Use original if normalization fails
                
            ip = ipaddress.ip_address(ip_str)
            ip_int = int(ip)
            
            # Choose the correct network list based on IP version
            network_list = self.networks['v6'] if isinstance(ip, ipaddress.IPv6Address) else self.networks['v4']
            
            # Check if IP falls within any range
            for start_ip, end_ip, org in network_list:
                if start_ip <= ip_int <= end_ip:
                    return True, org
            
            return False, ""
        except ValueError as e:
            logging.warning(f"Invalid IP address format: {ip_str} - {e}")
            return False, ""
        except Exception as e:
            logging.warning(f"Error checking IP {ip_str}: {e}")
            return False, ""

def save_state(last_timestamp):
    with open(STATE_FILE, 'w') as f:
        json.dump({'last_timestamp': last_timestamp}, f)

def load_state():
    try:
        with open(STATE_FILE, 'r') as f:
            data = json.load(f)
            return data.get('last_timestamp')
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def is_ip_address(user):
    # Some basic validation before attempting regex matching
    if not user or not isinstance(user, str):
        return False
        
    # Check if the user is an IP address (IPv4 or IPv6)
    try:
        ipaddress.ip_address(user)
        return True
    except ValueError:
        return False

def create_diff_url(rev_id, parent_id):
    return f"{WIKIPEDIA_DIFF_BASE_URL}?diff={rev_id}&oldid={parent_id}"

def fetch_recent_changes():
    try:
        logging.info(f"Making request with params: {params}")
        response = requests.get(WIKIPEDIA_API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        logging.info(f"📦 Received {len(data.get('query', {}).get('recentchanges', []))} recent changes")
        return data
    except requests.RequestException as e:
        logging.warning(f"Network error while fetching changes: {e}")
        return {"query": {"recentchanges": []}}

def sanitize_filename(filename):
    # Remove or replace invalid filename characters
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename

def take_screenshot(diff_url, title, timestamp):
    # Create screenshots directory if it doesn't exist
    if not os.path.exists(SCREENSHOTS_DIR):
        os.makedirs(SCREENSHOTS_DIR)
    
    # Create date-based subdirectory
    date_str = parser.isoparse(timestamp).strftime('%Y-%m-%d')
    date_dir = os.path.join(SCREENSHOTS_DIR, date_str)
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

def load_bluesky_credentials(config_file=CONFIG_FILE):
    """Load Bluesky credentials from a JSON config file."""
    try:
        with open(config_file) as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("Bluesky credentials file not found.")
        return None
    
def upload_image(client: Client, image_path: str) -> dict:
    """Upload an image and return the blob"""
    if not os.path.exists(image_path):
        raise Exception(f"Image file not found: {image_path}")
    
    # Strip EXIF data
    strip_exif(image_path)
    
    with open(image_path, "rb") as f:
        img_bytes = f.read()
    
    # Check file size
    if len(img_bytes) > 1000000:
        raise Exception(f"Image too large: {len(img_bytes)} bytes. Maximum is 1,000,000 bytes")
    
    # Upload the image
    response = client.com.atproto.repo.upload_blob(img_bytes)
    return response.blob

def strip_exif(image_path: str):
    """Remove EXIF data from image"""
    try:
        piexif.remove(image_path)
    except Exception:
        pass  # Not all images have EXIF data

def create_facets_for_url(text: str, url: str) -> List[Dict]:
    """Create facets for a URL in text on Bluesky"""
    # Convert text to bytes to get correct byte positions
    text_bytes = text.encode('utf-8')
    url_bytes = url.encode('utf-8')
    
    # Find the byte position of the URL in the text
    start_pos = text_bytes.find(url_bytes)
    if start_pos == -1:
        return []
        
    end_pos = start_pos + len(url_bytes)
    
    return [{
        "index": {
            "byteStart": start_pos,
            "byteEnd": end_pos
        },
        "features": [{
            "$type": "app.bsky.richtext.facet#link",
            "uri": url
        }]
    }]

def post_to_bluesky(changes, bluesky_credentials_file="config.json", delay=10):
    """Post changes to Bluesky if ENABLE_BLUESKY_POSTING is True."""
    if not ENABLE_BLUESKY_POSTING:
        logging.info("Bluesky posting is disabled. No posts will be made.")
        return

    # Load Bluesky credentials
    bluesky_credentials = load_bluesky_credentials(bluesky_credentials_file)
    if not bluesky_credentials:
        logging.error("Bluesky credentials are missing. Skipping posting.")
        return

    # Initialize Bluesky client
    try:
        client = Client()
        client.login(bluesky_credentials['email'], bluesky_credentials['password'])
    except Exception as e:
        logging.error(f"Failed to log in to Bluesky: {e}")
        return

    # Post each change to Bluesky
    for change in changes:
        try:
            title = change.get("title")
            org = change.get("organization", "Unknown Organization")
            diff_url = create_diff_url(
                change.get("change_data", {}).get("revid"),
                change.get("change_data", {}).get("parentid")
                )
            screenshot_path = change.get("screenshot_path")
            text = f"{title} Wikipedia article edited anonymously from {org}.\n\n{diff_url}"

            facets = create_facets_for_url(text, diff_url)

            if screenshot_path and os.path.exists(screenshot_path):
                try:
                    blob = upload_image(client, screenshot_path)
                    embed = {
                        "$type": "app.bsky.embed.images",
                        "images": [{"alt": f"Screenshot of edit for {title}", "image": blob}]
                    }
                    client.send_post(text=text, facets=facets, embed=embed)
                    logging.info(f"Posted to Bluesky with image: {text}")
                except Exception as e:
                    logging.warning(f"Failed to upload image for Bluesky post: {e}")
                    client.send_post(text=text, facets=facets)
                    logging.info(f"Posted to Bluesky without image: {text}")
            else:
                logging.warning(f"Screenshot missing for {title}. Posting text-only.")
                client.send_post(text=text)
                client.send_post(text=text, facets=facets)

            # Respect delay to avoid rate limiting
            time.sleep(delay)

        except Exception as e:
            logging.error(f"Error posting to Bluesky: {e}")

def save_to_csv_and_post_to_bluesky(changes, ip_cache):
    """Save changes to CSV and optionally post to Bluesky."""
    save_to_csv(changes, ip_cache)  # Save to CSV as before

    # Prepare changes for posting to Bluesky
    formatted_changes = []
    for change in changes:
        _, org = ip_cache.check_ip(change.get("user"))
        screenshot_path = take_screenshot(
            create_diff_url(change.get("revid"), change.get("parentid")),
            change.get("title"),
            change.get("timestamp"),
        )
        formatted_changes.append({
            "title": change.get("title"),
            "organization": org,
            "screenshot_path": screenshot_path,
            "change_data": change
        })

    # Post changes to Bluesky
    post_to_bluesky(formatted_changes)

def save_to_csv(changes, ip_cache):
    file_exists = os.path.isfile(OUTPUT_CSV)
    sensitive_exists = os.path.isfile(SENSITIVE_CHANGES_CSV)

    with open(OUTPUT_CSV, mode="a", newline="", encoding="utf-8") as file, \
         open(SENSITIVE_CHANGES_CSV, mode="a", newline="", encoding="utf-8") as sensitive_file:
        writer = csv.writer(file)
        sensitive_writer = csv.writer(sensitive_file)

        if not file_exists:
            writer.writerow([
                "Title", "IP Address", "Government Organization", "Timestamp", 
                "Edit ID", "Old Size", "New Size", "Revision ID", "Parent ID", 
                "Diff URL", "Comment", "Screenshot Path", "Contains Sensitive Info"
            ])

        if not sensitive_exists:
            sensitive_writer.writerow([
                "Title", "IP Address", "Government Organization", "Timestamp", 
                "Edit ID", "Diff URL", "Comment", "Sensitive Content Types"
            ])

        for change in changes:
            comment = change.get("comment", "")
            known_ids = {str(change.get("revid", "")), str(change.get("parentid", ""))}
            is_sensitive, content_matches = detect_sensitive_content(comment, known_ids=known_ids)

            # debug
            logging.debug(f"Known IDs passed for exclusion: {known_ids}")
            logging.debug(f"Analyzing text: {comment}")
            logging.debug(f"Sensitive matches: {content_matches}")

            diff_url = create_diff_url(change.get("revid"), change.get("parentid"))
            screenshot_path = take_screenshot(
                diff_url, 
                change.get("title"), 
                change.get("timestamp")
            )
            
            _, org = ip_cache.check_ip(change.get("user"))
            
            # Save to main CSV
            writer.writerow([
                change.get("title"),
                change.get("user"),
                org,
                convert_timestamp(change.get("timestamp")),
                change.get("rcid"),
                change.get("oldlen", ""),
                change.get("newlen", ""),
                change.get("revid"),
                change.get("parentid"),
                diff_url,
                comment,
                screenshot_path,
                "Yes" if is_sensitive else "No"
            ])

            # If sensitive, save to separate CSV
            if is_sensitive:
                matched_types = [match[0] for match in content_matches]
                matched_content = [match[1] for match in content_matches]
                sensitive_writer.writerow([
                    change.get("title"),
                    change.get("user"),
                    org,
                    convert_timestamp(change.get("timestamp")),
                    change.get("rcid"),
                    diff_url,
                    comment,
                    ", ".join(matched_types),
                    "; ".join(matched_content)
                ])
                logging.warning(f"Sensitive content detected in edit by {change.get('user')} "
                f"({org}) to {change.get('title')} with matches: {', '.join(matched_content)}")

def convert_timestamp(utc_timestamp):
    return parser.isoparse(utc_timestamp).strftime('%Y-%m-%d %H:%M:%S')

def poll_recent_changes():
    total_changes = 0
    processed_changes = set()
    ip_cache = IPNetworkCache()
    
    # Debug information about loaded IP ranges
    logging.info(f"Loaded {len(ip_cache.networks['v4'])} IPv4 ranges and {len(ip_cache.networks['v6'])} IPv6 ranges")
    
    last_timestamp = load_state()
    if last_timestamp:
        params["rcstart"] = last_timestamp
        current_time = datetime.now(timezone.utc)
        params["rcend"] = current_time.isoformat()
        logging.info(f"⏳ Fetching changes between {last_timestamp} and {params['rcend']}")
    
    logging.info("Starting indefinite polling for government changes...")
    
    try:
        while True:
            try:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                logging.info(f"Polling for changes... {current_time}")
                changes = fetch_recent_changes().get("query", {}).get("recentchanges", [])
                
                # Log some change samples for debugging
                if changes:
                    logging.info(f"Sample changes (showing first 3):")
                    for i, change in enumerate(changes[:3]):
                        logging.info(f"Change {i+1}: Title={change.get('title')}, User={change.get('user')}")
                
                ip_changes = [
                    change for change in changes
                    if is_ip_address(change.get("user", ""))
                ]
                
                if ip_changes:
                    logging.info(f"Found {len(ip_changes)} changes from IP addresses")
                    
                    # Log some IP checks for debugging
                    for i, change in enumerate(ip_changes[:3]):
                        user_ip = change.get("user", "")
                        is_gov, org = ip_cache.check_ip(user_ip)
                        logging.info(f"IP check for {user_ip}: is_government={is_gov}, org={org}")
                
                government_changes = [
                    change for change in ip_changes
                    if is_ip_address(change.get("user", "")) 
                    and ip_cache.check_ip(change.get("user", ""))[0]
                    and change.get("rcid") not in processed_changes
                ]
                
                if government_changes:
                    logging.info("\n🚨🚨🚨 GOVERNMENT EDIT DETECTED 🚨🚨🚨")
                    for change in government_changes:
                        _, org = ip_cache.check_ip(change.get("user"))
                        logging.info(f"""
                        📌 Title: {change.get('title')}
                        👤 Editor: {change.get('user')}
                        🏢 Organization: {colorama.Fore.MAGENTA}{org}{colorama.Style.RESET_ALL}
                        🕒 Time: {convert_timestamp(change.get('timestamp'))}
                        💬 Comment: {change.get('comment','')[:100]}...""")
                    logging.info("🔔🔔🔔 END OF GOVERNMENT ALERT 🔔🔔🔔")
                    save_to_csv_and_post_to_bluesky(government_changes, ip_cache)
                    
                    for change in government_changes:
                        processed_changes.add(change.get("rcid"))
                    
                    last_timestamp = government_changes[-1]["timestamp"]
                    save_state(last_timestamp)
                    logging.info(f"Updated timestamp to: {last_timestamp}")
                    
                    total_changes += len(government_changes)
                    logging.info(f"Total government changes logged: {total_changes}")
                
            except Exception as e:
                logging.error(f"Error during polling: {e}", exc_info=True)  # Added exc_info for stack trace
            
            time.sleep(10)

    except KeyboardInterrupt:
        shutdown_timestamp = datetime.now(timezone.utc).isoformat()
        save_state(shutdown_timestamp)
        logging.info(f"\nShutting down... Recorded shutdown timestamp: {shutdown_timestamp}")
        logging.info(f"Final total of government changes logged: {total_changes}")

def test_ip_matching():
    ip_cache = IPNetworkCache()
    
    # Test with different formats from your CSV
    test_ips = [
        "23.90.88.5",         # Should match City Of Anacortes
        "023.090.088.005",    # Same as above with leading zeros
        "23.134.224.10",      # Should match Pa House Of Representatives
        "56.15.255.254",      # Should match US Postal Service
        "192.168.1.1",        # Should not match any government org
        "2620:127:9000::1",   # IPv6 - Should match Academy School District 20 if in your data
        "156.033.123.123",     # Should match US Senate
        "161.160.123.123"     # U.S. Department Of The Interior
    ]
    
    print("\nTesting IP matching:")
    print("====================")
    for ip in test_ips:
        is_gov, org = ip_cache.check_ip(ip)
        print(f"IP: {ip}")
        print(f"  Is Government: {is_gov}")
        print(f"  Organization: {org}")
        print()
    
    # Test with actual IPs from your database
    print("Testing sample IPs from the database:")
    print("====================================")
    sample_count = 0
    for protocol in ['v4', 'v6']:
        for start_ip, end_ip, org in ip_cache.networks[protocol][:3]:  # Get the first 3 of each type
            # Convert int back to IP address
            if protocol == 'v4':
                ip_obj = ipaddress.IPv4Address(start_ip)
            else:
                ip_obj = ipaddress.IPv6Address(start_ip)
                
            ip_str = str(ip_obj)
            is_gov, matched_org = ip_cache.check_ip(ip_str)
            print(f"IP: {ip_str}")
            print(f"  Should match: {org}")
            print(f"  Is Government: {is_gov}")
            print(f"  Matched Organization: {matched_org}")
            print(f"  Correct match: {org == matched_org}")
            print()
            sample_count += 1
            
            if sample_count >= 6:  # Limit to 6 samples total
                break

if __name__ == "__main__":
    setup_logging()
    
    # Uncomment to test IP matching
    # test_ip_matching()

    # poll_recent_changes()