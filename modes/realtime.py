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

    # Spinner animation frames
    spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    spinner_idx = 0

    # Enhanced terminal display with box drawing
    print(f"\n{colorama.Fore.CYAN}╔{'═'*58}╗{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL} {colorama.Fore.CYAN}📡 Wikipedia Government Edit Monitor{colorama.Style.RESET_ALL}{' '*22}{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}╠{'═'*58}╣{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}Filter:{colorama.Style.RESET_ALL} {colorama.Fore.YELLOW}{filter_level}{colorama.Style.RESET_ALL}{' '*(51-len(filter_level))}{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}Ranges:{colorama.Style.RESET_ALL} {colorama.Fore.GREEN}{len(ip_cache.networks['v4'])} IPv4 + {len(ip_cache.networks['v6'])} IPv6{colorama.Style.RESET_ALL}{' '*(51-len(str(len(ip_cache.networks['v4'])))-len(str(len(ip_cache.networks['v6'])))-12)}{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}╚{'═'*58}╝{colorama.Style.RESET_ALL}\n")

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

                logging.debug(f"Fetching changes from {last_timestamp or 'beginning'} to {params['rcend']}")

                data = fetch_recent_changes(params)
                changes = data.get("query", {}).get("recentchanges", [])

                # Log sample changes to file only
                if changes:
                    logging.debug(f"Sample changes (showing first 3):")
                    for i, change in enumerate(changes[:3]):
                        logging.debug(f"Change {i+1}: Title={change.get('title')}, User={change.get('user')}")

                government_changes = filter_government_changes(changes, ip_cache, processed_changes)

                if government_changes:
                    # Clear the polling line and show alerts
                    print(f"\r{' '*80}\r", end="")  # Clear line
                    print(f"\n{colorama.Fore.RED}╔{'═'*58}╗{colorama.Style.RESET_ALL}")
                    print(f"{colorama.Fore.RED}║{colorama.Style.RESET_ALL} {colorama.Fore.RED}🚨 GOVERNMENT EDIT DETECTED{colorama.Style.RESET_ALL}{' '*26}{colorama.Fore.RED}║{colorama.Style.RESET_ALL}")
                    print(f"{colorama.Fore.RED}╚{'═'*58}╝{colorama.Style.RESET_ALL}\n")

                    for change in government_changes:
                        _, org = ip_cache.check_ip(change.get("user"))
                        timestamp_str = convert_timestamp(change.get('timestamp'))

                        # Determine org color based on type
                        org_lower = org.lower()
                        if any(x in org_lower for x in ['senate', 'house of representatives', 'congress']):
                            org_color = colorama.Fore.MAGENTA
                        elif any(x in org_lower for x in ['department', 'white house', 'executive']):
                            org_color = colorama.Fore.BLUE
                        elif 'court' in org_lower:
                            org_color = colorama.Fore.CYAN
                        else:
                            org_color = colorama.Fore.YELLOW

                        # Create clickable link (works in modern terminals)
                        diff_url = create_diff_url(change.get("revid"), change.get("parentid"))
                        clickable_url = f"\033]8;;{diff_url}\033\\{diff_url}\033]8;;\033\\"

                        print(f"{colorama.Fore.WHITE}╭─ {colorama.Fore.CYAN}{change.get('title')}{colorama.Style.RESET_ALL}")
                        print(f"{colorama.Fore.WHITE}├─ {colorama.Fore.YELLOW}Organization: {org_color}{org}{colorama.Style.RESET_ALL}")
                        print(f"{colorama.Fore.WHITE}├─ {colorama.Fore.YELLOW}IP Address: {colorama.Fore.WHITE}{change.get('user')}{colorama.Style.RESET_ALL}")
                        print(f"{colorama.Fore.WHITE}├─ {colorama.Fore.YELLOW}Time: {colorama.Fore.WHITE}{timestamp_str}{colorama.Style.RESET_ALL}")
                        print(f"{colorama.Fore.WHITE}├─ {colorama.Fore.YELLOW}Diff URL: {colorama.Fore.BLUE}{clickable_url}{colorama.Style.RESET_ALL}")

                        comment = change.get('comment', '')[:80]
                        if comment:
                            print(f"{colorama.Fore.WHITE}╰─ {colorama.Fore.YELLOW}Comment: {colorama.Fore.WHITE}{comment}...{colorama.Style.RESET_ALL}\n")
                        else:
                            print(f"{colorama.Fore.WHITE}╰{colorama.Style.RESET_ALL}\n")

                    logging.info("GOVERNMENT EDIT DETECTED")
                    for change in government_changes:
                        _, org = ip_cache.check_ip(change.get("user"))
                        logging.info(f"Title: {change.get('title')} | IP: {change.get('user')} | Org: {org} | Time: {convert_timestamp(change.get('timestamp'))} | Comment: {change.get('comment','')[:100]}")

                    # Save and post changes
                    save_and_post_changes(government_changes, ip_cache)

                    for change in government_changes:
                        processed_changes.add(change.get("rcid"))

                    total_changes += len(government_changes)
                    print(f"{colorama.Fore.GREEN}✅ Processed and posted {len(government_changes)} edit(s) | Total: {total_changes}{colorama.Style.RESET_ALL}\n")
                else:
                    # Show animated polling status on same line
                    if changes:
                        current_time = datetime.now().strftime('%H:%M:%S')
                        spinner = spinner_frames[spinner_idx % len(spinner_frames)]
                        spinner_idx += 1
                        print(f"\r{colorama.Fore.CYAN}{spinner} Polling... {colorama.Fore.WHITE}[{current_time}] {colorama.Fore.YELLOW}Checked {len(changes)} changes{colorama.Style.RESET_ALL}", end="", flush=True)

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
        print(f"\n\n{colorama.Fore.YELLOW}╔{'═'*58}╗{colorama.Style.RESET_ALL}")
        print(f"{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL} {colorama.Fore.YELLOW}⏸️  Shutting down gracefully...{colorama.Style.RESET_ALL}{' '*26}{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL}")
        print(f"{colorama.Fore.YELLOW}╚{'═'*58}╝{colorama.Style.RESET_ALL}")
        shutdown_timestamp = datetime.now(timezone.utc).isoformat()
        save_state(STATE_FILE, shutdown_timestamp)
        print(f"\n{colorama.Fore.GREEN}✅ Final total: {total_changes} government edits detected{colorama.Style.RESET_ALL}")
        print(f"{colorama.Fore.CYAN}╚{'═'*58}╝{colorama.Style.RESET_ALL}\n")
        logging.info(f"Shutting down... Recorded shutdown timestamp: {shutdown_timestamp}")
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
