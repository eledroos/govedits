"""
Real-time Wikipedia monitoring mode
"""
import logging
import time
import colorama
from datetime import datetime, timezone
from core.ip_matcher import IPNetworkCache
from core.scanner import fetch_recent_changes, filter_government_changes
from processors.screenshot import take_screenshot, create_diff_url
from processors.csv_handler import save_to_csv
from processors.bluesky_poster import post_to_bluesky
from utils.helpers import load_state, save_state, convert_timestamp
from utils.logging_config import setup_logging
from config.settings import REALTIME_POLL_INTERVAL, DEFAULT_FILTER

STATE_FILE = "last_run_state.json"
OUTPUT_CSV = "government_changes.csv"
SENSITIVE_CSV = "sensitive_content_changes.csv"
LOG_FILE = "wikipedia_monitor.log"


def run_realtime_monitor(filter_level: str = DEFAULT_FILTER):
    """
    Run real-time Wikipedia monitoring

    Args:
        filter_level: Government filter level ('all', 'federal', or 'congress')
    """
    setup_logging(LOG_FILE)

    total_changes = 0
    processed_changes = set()
    ip_cache = IPNetworkCache(filter_level=filter_level)

    logging.info(f"Loaded {len(ip_cache.networks['v4'])} IPv4 ranges and {len(ip_cache.networks['v6'])} IPv6 ranges")

    last_timestamp = load_state(STATE_FILE)

    logging.info("Starting indefinite polling for government changes...")

    try:
        while True:
            try:
                # Update timestamps for this iteration
                current_time_utc = datetime.now(timezone.utc)
                params = {
                    "action": "query",
                    "list": "recentchanges",
                    "rcprop": "title|ids|sizes|flags|user|timestamp|comment|revid|parentid",
                    "rcshow": "!bot",
                    "rclimit": 500,
                    "format": "json",
                    "rcdir": "newer",
                    "rcend": current_time_utc.isoformat()
                }

                if last_timestamp:
                    params["rcstart"] = last_timestamp

                logging.info(f"⏳ Fetching changes from {last_timestamp or 'beginning'} to {params['rcend']}")

                data = fetch_recent_changes(params)
                changes = data.get("query", {}).get("recentchanges", [])

                # Log some change samples for debugging
                if changes:
                    logging.info(f"Sample changes (showing first 3):")
                    for i, change in enumerate(changes[:3]):
                        logging.info(f"Change {i+1}: Title={change.get('title')}, User={change.get('user')}")

                government_changes = filter_government_changes(changes, ip_cache, processed_changes)

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

                    # Save and post changes
                    save_and_post_changes(government_changes, ip_cache)

                    for change in government_changes:
                        processed_changes.add(change.get("rcid"))

                    total_changes += len(government_changes)
                    logging.info(f"Total government changes logged: {total_changes}")

                # Always update timestamp to avoid infinite loops
                if changes:
                    latest_timestamp = max(change["timestamp"] for change in changes)
                    last_timestamp = latest_timestamp
                    save_state(STATE_FILE, last_timestamp)
                    logging.debug(f"Updated timestamp to: {last_timestamp}")

            except Exception as e:
                logging.error(f"Error during polling: {e}", exc_info=True)

            time.sleep(REALTIME_POLL_INTERVAL)

    except KeyboardInterrupt:
        shutdown_timestamp = datetime.now(timezone.utc).isoformat()
        save_state(STATE_FILE, shutdown_timestamp)
        logging.info(f"\nShutting down... Recorded shutdown timestamp: {shutdown_timestamp}")
        logging.info(f"Final total of government changes logged: {total_changes}")


def save_and_post_changes(changes, ip_cache):
    """Save changes to CSV and optionally post to Bluesky"""
    # Save to CSV
    save_to_csv(changes, ip_cache, OUTPUT_CSV, SENSITIVE_CSV)

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


if __name__ == "__main__":
    run_realtime_monitor()
