"""
Streaming Wikipedia monitoring mode using EventStreams API
"""
import logging
import json
import colorama
from datetime import datetime, timezone, timedelta
from dateutil import parser
import sseclient
import requests
from core.ip_matcher import IPNetworkCache
from core.scanner import filter_government_changes
from processors.screenshot import take_screenshot, create_diff_url
from processors.csv_handler import save_to_csv
from processors.bluesky_poster import post_to_bluesky
from utils.helpers import load_state, save_state, convert_timestamp, is_ip_address
from utils.logging_config import setup_logging
from config.settings import DEFAULT_FILTER

STATE_FILE = "streaming_state.json"
OUTPUT_CSV = "government_changes.csv"
SENSITIVE_CSV = "sensitive_content_changes.csv"
LOG_FILE = "wikipedia_streaming.log"
STREAM_URL = "https://stream.wikimedia.org/v2/stream/recentchange"
USER_AGENT = "GovEditsBot/1.0 (https://github.com/yourusername/govedits; contact@example.com)"


def format_timestamp(dt: datetime) -> str:
    """
    Format datetime to YYYY-MM-DDTHH:MM:SSZ (no microseconds)

    Args:
        dt: Datetime object

    Returns:
        Formatted timestamp string with Z suffix
    """
    return dt.strftime('%Y-%m-%dT%H:%M:%SZ')


def check_gap_and_run_catchup(last_timestamp: str) -> bool:
    """
    Check if there's a >31 day gap and run historical catchup if needed

    Args:
        last_timestamp: Last processed timestamp string

    Returns:
        True if catchup was needed and run, False otherwise
    """
    if not last_timestamp:
        return False

    try:
        last_time = parser.isoparse(last_timestamp)
        now = datetime.now(timezone.utc)
        gap = now - last_time

        if gap.days > 31:
            logging.warning(f"Gap of {gap.days} days detected. Running historical catchup first...")
            print(f"\n{colorama.Fore.YELLOW}╔{'═'*58}╗{colorama.Style.RESET_ALL}")
            print(f"{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL} {colorama.Fore.YELLOW}⚠️  Gap of {gap.days} days detected{colorama.Style.RESET_ALL}{' '*(58-len(f'Gap of {gap.days} days detected')-4)}{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL}")
            print(f"{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}Running historical catchup first...{colorama.Style.RESET_ALL}{' '*21}{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL}")
            print(f"{colorama.Fore.YELLOW}╚{'═'*58}╝{colorama.Style.RESET_ALL}\n")

            # Import and run historical catchup
            from modes.historical import run_historical_scan
            run_historical_scan(days=gap.days)

            return True
    except Exception as e:
        logging.error(f"Error checking gap: {e}")

    return False


def run_streaming_monitor(filter_level: str = DEFAULT_FILTER):
    """
    Run streaming Wikipedia monitoring using EventStreams API

    Args:
        filter_level: Government filter level ('all', 'federal', or 'congress')
    """
    setup_logging(LOG_FILE)

    total_changes = 0
    processed_changes = set()
    ip_cache = IPNetworkCache(filter_level=filter_level)

    logging.info(f"Loaded {len(ip_cache.networks['v4'])} IPv4 ranges and {len(ip_cache.networks['v6'])} IPv6 ranges")

    last_timestamp = load_state(STATE_FILE)

    # Check for gaps and run catchup if needed
    if check_gap_and_run_catchup(last_timestamp):
        # Reload state after catchup
        last_timestamp = load_state(STATE_FILE)

    # Spinner animation frames
    spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    spinner_idx = 0

    # Enhanced terminal display with box drawing
    # Note: emoji 📡 takes 2 character widths, so adjust spacing accordingly
    print(f"\n{colorama.Fore.CYAN}╔{'═'*58}╗{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL} 📡 Wikipedia Government Edit Monitor (Streaming){' '*8}{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL}")
    print(f"{colorama.Fore.CYAN}╠{'═'*58}╣{colorama.Style.RESET_ALL}")

    filter_text = f"Filter: {filter_level}"
    filter_padding = 58 - len(filter_text) - 1
    print(f"{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}{filter_text}{colorama.Style.RESET_ALL}{' '*filter_padding}{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL}")

    ranges_text = f"Ranges: {len(ip_cache.networks['v4'])} IPv4 + {len(ip_cache.networks['v6'])} IPv6"
    ranges_padding = 58 - len(ranges_text) - 1
    print(f"{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}{ranges_text}{colorama.Style.RESET_ALL}{' '*ranges_padding}{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL}")

    stream_text = "Mode: EventStreams (Real-time)"
    stream_padding = 58 - len(stream_text) - 1
    print(f"{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}{stream_text}{colorama.Style.RESET_ALL}{' '*stream_padding}{colorama.Fore.CYAN}║{colorama.Style.RESET_ALL}")

    print(f"{colorama.Fore.CYAN}╚{'═'*58}╝{colorama.Style.RESET_ALL}\n")

    logging.info("Connecting to EventStreams API...")

    # Detect if we're resuming from the past
    is_catching_up = False
    catchup_start_time = None
    catchup_end_time = None

    if last_timestamp:
        try:
            last_dt = parser.isoparse(last_timestamp)
            now_dt = datetime.now(timezone.utc)
            gap = now_dt - last_dt
            gap_seconds = gap.total_seconds()

            if gap_seconds > 300:  # More than 5 minutes
                is_catching_up = True
                catchup_start_time = last_dt
                catchup_end_time = now_dt

                # Format the gap nicely
                if gap.days > 0:
                    gap_str = f"{gap.days} day{'s' if gap.days != 1 else ''}"
                elif gap_seconds >= 3600:
                    hours = int(gap_seconds // 3600)
                    gap_str = f"{hours} hour{'s' if hours != 1 else ''}"
                else:
                    minutes = int(gap_seconds // 60)
                    gap_str = f"{minutes} minute{'s' if minutes != 1 else ''}"

                print(f"{colorama.Fore.YELLOW}⏳ Catching up from: {colorama.Fore.CYAN}{last_timestamp}{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}({gap_str} ago){colorama.Style.RESET_ALL}")
            else:
                print(f"{colorama.Fore.GREEN}▶️  Resuming from: {colorama.Fore.CYAN}{last_timestamp}{colorama.Style.RESET_ALL} {colorama.Fore.WHITE}(live){colorama.Style.RESET_ALL}")
        except Exception as e:
            logging.error(f"Error parsing timestamp: {e}")

    # Auto-reconnect loop
    while True:
        try:
            # Connect to EventStreams
            headers = {'User-Agent': USER_AGENT}
            response = requests.get(STREAM_URL, stream=True, headers=headers, timeout=None)
            response.raise_for_status()

            client = sseclient.SSEClient(response)

            logging.info("Connected to EventStreams - monitoring for government edits...")
            print(f"{colorama.Fore.GREEN}✅ Connected to EventStreams{colorama.Style.RESET_ALL}\n")

            for event in client.events():
                try:
                    # Parse event data
                    if event.data:
                        data = json.loads(event.data)

                    # Filter for English Wikipedia edits only
                    if data.get('wiki') != 'enwiki':
                        continue

                    # Skip bot edits
                    if data.get('bot', False):
                        continue

                    # Only process edits from IP addresses (anonymous users)
                    user = data.get('user', '')
                    if not is_ip_address(user):
                        continue

                    # Convert EventStreams format to our expected format
                    change = {
                        'title': data.get('title', ''),
                        'user': user,
                        'timestamp': data.get('timestamp'),
                        'comment': data.get('comment', ''),
                        'revid': data.get('revision', {}).get('new') if isinstance(data.get('revision'), dict) else data.get('id'),
                        'parentid': data.get('revision', {}).get('old') if isinstance(data.get('revision'), dict) else None,
                        'rcid': data.get('id'),
                        'type': data.get('type'),
                    }

                    # Update spinner for visual feedback
                    spinner = spinner_frames[spinner_idx % len(spinner_frames)]
                    spinner_idx += 1

                    # Check if this is a government edit
                    government_changes = filter_government_changes([change], ip_cache, processed_changes)

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
                        # Show animated streaming status on same line
                        current_time = datetime.now().strftime('%H:%M:%S')

                        # Check if we're in catchup mode
                        if is_catching_up and change.get('timestamp'):
                            # Get event timestamp
                            ts_value = change['timestamp']
                            if isinstance(ts_value, int):
                                event_dt = datetime.fromtimestamp(ts_value, tz=timezone.utc)
                            else:
                                event_dt = parser.isoparse(str(ts_value))
                                if event_dt.tzinfo is None:
                                    event_dt = event_dt.replace(tzinfo=timezone.utc)

                            # Calculate progress
                            total_gap = (catchup_end_time - catchup_start_time).total_seconds()
                            progress = (event_dt - catchup_start_time).total_seconds()
                            percent = min(100, int((progress / total_gap) * 100)) if total_gap > 0 else 100

                            # Check if we're caught up (within 30 seconds of now)
                            now = datetime.now(timezone.utc)
                            lag = (now - event_dt).total_seconds()

                            if lag < 30:
                                # We've caught up!
                                print(f"\r{' '*80}\r", end="")
                                print(f"{colorama.Fore.GREEN}✅ Caught up! Now streaming live...{colorama.Style.RESET_ALL}")
                                is_catching_up = False
                            else:
                                # Still catching up - show progress
                                event_time_str = event_dt.strftime('%H:%M:%S')
                                print(f"\r{colorama.Fore.YELLOW}{spinner} Catching up... {colorama.Fore.WHITE}[{event_time_str}] {colorama.Fore.CYAN}{percent}% {colorama.Fore.YELLOW}Latest: {change.get('title', 'N/A')[:20]}{colorama.Style.RESET_ALL}", end="", flush=True)
                        else:
                            # Normal streaming mode
                            print(f"\r{colorama.Fore.CYAN}{spinner} Streaming... {colorama.Fore.WHITE}[{current_time}] {colorama.Fore.YELLOW}Latest: {change.get('title', 'N/A')[:30]}{colorama.Style.RESET_ALL}", end="", flush=True)

                    # Update timestamp - format as YYYY-MM-DDTHH:MM:SSZ
                    if change.get('timestamp'):
                        # EventStreams may provide timestamp as int (Unix timestamp) or string (ISO format)
                        ts_value = change['timestamp']
                        if isinstance(ts_value, int):
                            ts = datetime.fromtimestamp(ts_value, tz=timezone.utc)
                        else:
                            ts = parser.isoparse(str(ts_value))
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=timezone.utc)
                        last_timestamp = format_timestamp(ts)
                        save_state(STATE_FILE, last_timestamp)

                except json.JSONDecodeError as e:
                    logging.debug(f"Failed to parse event data: {e}")
                    continue
                except Exception as e:
                    logging.error(f"Error processing event: {e}", exc_info=True)
                    continue

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError) as e:
            # Connection dropped - reconnect automatically
            logging.warning(f"Connection lost: {e}. Reconnecting in 5 seconds...")
            print(f"\n{colorama.Fore.YELLOW}⚠️  Connection lost. Reconnecting in 5 seconds...{colorama.Style.RESET_ALL}")
            import time
            time.sleep(5)
            continue  # Retry the while True loop

        except KeyboardInterrupt:
            print(f"\n\n{colorama.Fore.YELLOW}╔{'═'*58}╗{colorama.Style.RESET_ALL}")
            print(f"{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL} {colorama.Fore.YELLOW}⏸️  Shutting down gracefully...{colorama.Style.RESET_ALL}{' '*26}{colorama.Fore.YELLOW}║{colorama.Style.RESET_ALL}")
            print(f"{colorama.Fore.YELLOW}╚{'═'*58}╝{colorama.Style.RESET_ALL}")
            shutdown_timestamp = format_timestamp(datetime.now(timezone.utc))
            save_state(STATE_FILE, shutdown_timestamp)
            print(f"\n{colorama.Fore.GREEN}✅ Final total: {total_changes} government edits detected{colorama.Style.RESET_ALL}")
            print(f"{colorama.Fore.CYAN}╚{'═'*58}╝{colorama.Style.RESET_ALL}\n")
            logging.info(f"Shutting down... Recorded shutdown timestamp: {shutdown_timestamp}")
            logging.info(f"Final total of government changes logged: {total_changes}")
            break  # Exit the while loop


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
    run_streaming_monitor()
