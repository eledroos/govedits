"""
Historical Wikipedia scanning mode
"""
import json
import logging
import os
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple
import colorama
import requests
from dateutil import parser

from core.ip_matcher import IPNetworkCache
from core.scanner import filter_government_changes
from processors.screenshot import take_screenshot, create_diff_url
from processors.csv_handler import save_to_csv
from processors.bluesky_poster import post_to_bluesky, load_bluesky_credentials
from atproto import Client, models
from utils.helpers import convert_timestamp
from utils.logging_config import setup_logging
from config.settings import DEFAULT_DAYS_TO_FETCH, DEFAULT_FILTER, API_DELAY, BLUESKY_DELAY

STATE_FILE = "catchup_state.json"
OUTPUT_CSV = "historical_government_changes.csv"
SENSITIVE_CSV = "historical_sensitive_changes.csv"
LOG_FILE = "wikipedia_catchup.log"


class HistoricalProcessor:
    def __init__(self, filter_level: str = DEFAULT_FILTER, days_to_fetch: int = DEFAULT_DAYS_TO_FETCH):
        """
        Initialize historical processor

        Args:
            filter_level: Government filter level ('all', 'federal', or 'congress')
            days_to_fetch: Number of days of history to process
        """
        self.filter_level = filter_level
        self.days_to_fetch = days_to_fetch
        self.ip_cache = IPNetworkCache(filter_level=filter_level)
        self.state = self.load_state()

        # Validate state consistency
        if self.state["continue_token"] and not self.state["last_timestamp"]:
            logging.warning("Invalid state: continuation token without timestamp")
            self.state["continue_token"] = None

        self.queue = deque(self.state["queue"]) if isinstance(self.state["queue"], list) else self.state["queue"]
        self.bluesky_client = self.init_bluesky()

    def init_bluesky(self):
        """Initialize Bluesky client if enabled"""
        try:
            creds = load_bluesky_credentials()
            if not creds:
                return None

            client = Client()
            client.login(creds['email'], creds['password'])
            return client
        except Exception as e:
            logging.error(f"Bluesky init failed: {e}")
            return None

    def load_state(self) -> Dict:
        """Load processing state from file"""
        default_state = {
            "last_timestamp": None,
            "processed_rcids": set(),
            "continue_token": None,
            "queue": []
        }

        try:
            with open(STATE_FILE, 'r') as f:
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
        """Save processing state to file"""
        state = {
            "last_timestamp": self.state["last_timestamp"],
            "processed_rcids": list(self.state["processed_rcids"]),
            "continue_token": self.state["continue_token"],
            "queue": list(self.queue)
        }

        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)

    def fetch_historical_changes(self) -> Tuple[List[Dict], str]:
        """Fetch changes from Wikipedia API"""
        params = {
            "action": "query",
            "list": "recentchanges",
            "rcprop": "title|ids|sizes|flags|user|timestamp|comment|revid|parentid",
            "rcshow": "!bot",
            "rclimit": 500,
            "format": "json",
            "rcdir": "newer",
            "rcstart": (parser.isoparse(self.state["last_timestamp"])
                    if self.state["last_timestamp"]
                    else datetime.now(timezone.utc) - timedelta(days=self.days_to_fetch)).isoformat(),
            "rcend": datetime.now(timezone.utc).isoformat(),
        }

        headers = {
            'User-Agent': 'GovEditsBot/1.0 (Wikipedia government edit monitor; educational/transparency project)'
        }

        try:
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params=params,
                headers=headers,
                timeout=60
            )
            response.raise_for_status()
            data = response.json()

            changes = data.get("query", {}).get("recentchanges", [])
            continue_token = data.get("continue", {}).get("rccontinue")

            # Save state immediately after successful fetch
            if changes:
                logging.info(f"🌐 Fetched {len(changes)} changes")
                new_timestamp = max(parser.isoparse(c['timestamp']) for c in changes)
                self.state["last_timestamp"] = new_timestamp.isoformat()
                self.state["continue_token"] = continue_token
                self.save_state()

            return changes, continue_token

        except requests.exceptions.Timeout as e:
            logging.error(f"⏳ Timeout fetching changes: {e}")
            self.state["continue_token"] = None
            self.save_state()
            raise

        except requests.exceptions.RequestException as e:
            logging.error(f"🌐 Network error: {e}")
            self.state["continue_token"] = None
            self.save_state()
            raise

        except Exception as e:
            logging.error(f"❌ Unexpected error: {e}")
            if 'last_timestamp' in self.state:
                self.state["continue_token"] = None
                self.save_state()
            raise

    def process_changes(self, changes: List[Dict]):
        """Process a batch of changes"""
        if not changes:
            return

        logging.info(
            f"{colorama.Fore.CYAN}📅 Processing {len(changes)} changes"
            f"{colorama.Style.RESET_ALL}"
        )

        # Filter government edits
        gov_edits = filter_government_changes(changes, self.ip_cache, self.state["processed_rcids"])

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
        """Process queued changes"""
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
                save_to_csv([item["data"]], self.ip_cache, OUTPUT_CSV, SENSITIVE_CSV, item["screenshot"])

                # Post to Bluesky
                if not item["posted"] and self.bluesky_client:
                    _, org = self.ip_cache.check_ip(item["data"].get("user"))
                    formatted_change = {
                        "title": item["data"].get("title"),
                        "organization": org,
                        "screenshot_path": item["screenshot"],
                        "change_data": item["data"]
                    }
                    post_to_bluesky([formatted_change])
                    item["posted"] = True
                    time.sleep(BLUESKY_DELAY)

            except Exception as e:
                logging.error(f"Queue item failed: {e}")
                self.queue.appendleft(item)
                break

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
        """Log government edits with formatting"""
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

    def run(self):
        """Main processing loop"""
        setup_logging(LOG_FILE)
        logging.info(
            f"{colorama.Fore.CYAN}🚀 Starting historical processing "
            f"(last {self.days_to_fetch} days, filter: {self.filter_level})"
            f"{colorama.Style.RESET_ALL}"
        )

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

                time.sleep(API_DELAY)

                # Progress logging
                if self.state["last_timestamp"]:
                    processed_time = parser.isoparse(self.state["last_timestamp"])
                    time_diff = datetime.now(timezone.utc) - processed_time
                    logging.info(f"⏳ Processed up to {processed_time} ({time_diff.days} days remaining)")

                # Check if caught up
                if continue_token is None:
                    break

            # Cleanup
            if os.path.exists(STATE_FILE):
                os.remove(STATE_FILE)

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


def run_historical_scan(filter_level: str = DEFAULT_FILTER, days: int = DEFAULT_DAYS_TO_FETCH):
    """
    Run historical Wikipedia scan

    Args:
        filter_level: Government filter level ('all', 'federal', or 'congress')
        days: Number of days of history to process
    """
    processor = HistoricalProcessor(filter_level=filter_level, days_to_fetch=days)
    processor.run()


if __name__ == "__main__":
    run_historical_scan()
