import requests
import csv
import time
from datetime import datetime, timedelta
import os
from dateutil import parser
import re
import json
from playwright.sync_api import sync_playwright
import asyncio
import ipaddress
from typing import Dict, Set, Union

WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
WIKIPEDIA_DIFF_BASE_URL = "https://en.wikipedia.org/w/index.php"
STATE_FILE = "last_run_state.json"
SCREENSHOTS_DIR = "diff_screenshots"
GOV_IPS_FILE = "govedits - IP Address DB.csv"

params = {
    "action": "query",
    "list": "recentchanges",
    "rcprop": "title|ids|sizes|flags|user|timestamp|comment|revid|parentid",
    "rcshow": "!bot",
    "rclimit": 50,
    "format": "json",
}

class IPNetworkCache:
    def __init__(self):
        self.networks: Dict[str, Dict[Union[ipaddress.IPv4Network, ipaddress.IPv6Network], str]] = {
            'v4': {},
            'v6': {}
        }
        self.load_government_networks()

    def load_government_networks(self):
        with open(GOV_IPS_FILE, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    # Try to create network directly first
                    try:
                        network = ipaddress.ip_network(row['ip_address'], strict=False)  # Added strict=False
                        network_type = 'v6' if isinstance(network, ipaddress.IPv6Network) else 'v4'
                        self.networks[network_type][network] = row['organization']
                    except ValueError as e:
                        print(f"Skipping invalid IP network {row['ip_address']}: {e}")
                except Exception as e:
                    print(f"Error processing row {row}: {e}")

    def check_ip(self, ip_str: str) -> tuple[bool, str]:
        try:
            ip_addr = ipaddress.ip_address(ip_str)
            network_type = 'v6' if isinstance(ip_addr, ipaddress.IPv6Address) else 'v4'
            
            for network, org in self.networks[network_type].items():
                if ip_addr in network:
                    return True, org
            return False, ""
        except ValueError:
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

output_csv = "government_changes.csv"

def is_ip_address(user):
    # Check if the user is an IP address (IPv4 or IPv6)
    ipv4_pattern = r'^(\d{1,3}\.){3}\d{1,3}$'
    ipv6_pattern = r'^([0-9a-fA-F:]+)$'
    return re.match(ipv4_pattern, user) or re.match(ipv6_pattern, user)

def create_diff_url(rev_id, parent_id):
    return f"{WIKIPEDIA_DIFF_BASE_URL}?diff={rev_id}&oldid={parent_id}"

def fetch_recent_changes():
    response = requests.get(WIKIPEDIA_API_URL, params=params)
    response.raise_for_status()
    return response.json()

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
                viewport={'width': 1080, 'height': 1920}
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
                    'width': 1080,
                    'height': 1000  # Adjust this value to capture more or less
                }
            )
            
            browser.close()
        
        return filepath
    except Exception as e:
        print(f"Error taking screenshot for {title}: {str(e)}")
        return None

def save_to_csv(changes, ip_cache):
    file_exists = os.path.isfile(output_csv)
    with open(output_csv, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow([
                "Title", "IP Address", "Government Organization", "Timestamp", 
                "Edit ID", "Old Size", "New Size", "Revision ID", "Parent ID", 
                "Diff URL", "Comment", "Screenshot Path"
            ])

        for change in changes:
            diff_url = create_diff_url(change.get("revid"), change.get("parentid"))
            screenshot_path = take_screenshot(
                diff_url, 
                change.get("title"), 
                change.get("timestamp")
            )
            
            _, org = ip_cache.check_ip(change.get("user"))
            
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
                change.get("comment", ""),
                screenshot_path
            ])

def convert_timestamp(utc_timestamp):
    return parser.isoparse(utc_timestamp).strftime('%Y-%m-%d %H:%M:%S')

def poll_recent_changes_for_duration(duration_minutes=720, max_changes=1000):
    start_time = datetime.now()
    end_time = start_time + timedelta(minutes=duration_minutes)
    total_changes = 0
    processed_changes = set()
    ip_cache = IPNetworkCache()
    
    # Load the last timestamp from the previous run
    last_timestamp = load_state()
    if last_timestamp:
        params["rcstart"] = last_timestamp
        print(f"Continuing from last recorded timestamp: {last_timestamp}")
    
    print(f"Polling for {duration_minutes} minutes or until {max_changes} anonymous changes are found...")
    
    while datetime.now() < end_time and total_changes < max_changes:
        try:
            changes = fetch_recent_changes().get("query", {}).get("recentchanges", [])
            
            government_changes = [
                change for change in changes
                if is_ip_address(change.get("user", "")) 
                and ip_cache.check_ip(change.get("user", ""))[0]
                and change.get("rcid") not in processed_changes
            ]
            
            if government_changes:
                print("\nNew government changes detected:")
                print("-----------------------------")
                for change in government_changes:
                    _, org = ip_cache.check_ip(change.get("user"))
                    print(f"  • {change.get('title')}")
                    print(f"    - Editor: {change.get('user')}")
                    print(f"    - Organization: {org}")
                    print(f"    - Time: {convert_timestamp(change.get('timestamp'))}")
                    if change.get('comment'):
                        print(f"    - Comment: {change.get('comment')[:100]}...")
                print("-----------------------------")
                save_to_csv(government_changes, ip_cache) 
                
                for change in government_changes:
                    processed_changes.add(change.get("rcid"))
                
                # Update timestamp from the last anonymous change we processed
                last_timestamp = government_changes[-1]["timestamp"]
                save_state(last_timestamp)
                print(f"Updated timestamp to: {last_timestamp}")
                
                total_changes += len(government_changes)
                print(f"Total anonymous changes logged: {total_changes}")
            else:
                print("\nPolling for changes...", end='\r')
                
        except Exception as e:
            print(f"Error during polling: {e}")
        
        time.sleep(10)  # Adjust this interval if needed
    
    print("\nPolling session completed.")
    print(f"Total unique anonymous changes logged: {total_changes}")

if __name__ == "__main__":
    poll_recent_changes_for_duration()