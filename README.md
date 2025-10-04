# Government Edits, on Bluesky

A Python-based tool to monitor anonymous edits on Wikipedia from government organizations, schools, and public institutions. This project is designed for researchers, journalists, and transparency advocates interested in how public entities interact with Wikipedia. [It posts updates automatically on Bluesky](https://bsky.app/profile/govedits.bsky.social).

## Features

1. **Three Monitoring Modes**:
   - **Stream Mode** (Recommended): Uses Wikipedia's EventStreams API for guaranteed delivery with automatic reconnection
   - **Monitor Mode**: Polls Wikipedia's API every 10 seconds with continuation support to ensure no edits are missed
   - **Historical Mode**: Scans past edits (configurable days backward) to catch up on missed activity

2. **Government Filter Levels**:
   - **All** (1,749 agencies): All government organizations
   - **Federal** (372 agencies): Federal agencies only (default)
   - **Congress**: Congressional IPs only (House + Senate)

3. **Content Analysis**:
   - Flags potential sensitive information such as phone numbers and addresses within edit comments to prevent doxxing

4. **Comprehensive Logging and Reporting**:
   - Saves all detected changes to CSV files with full metadata
   - Flags sensitive edits in a separate CSV for focused analysis

5. **Screenshot Capture**:
   - Captures visual representation of each Wikipedia edit (diff view)
   - Organizes screenshots by date

6. **Bluesky Integration** (Optional):
   - Automatically posts detected changes to Bluesky with formatted messages and screenshots
   - Configurable posting delay to respect rate limits

7. **Crash Recovery**:
   - All modes maintain state files for automatic resumption
   - Stream mode detects gaps >31 days and runs historical catchup automatically

---

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Required Python packages (see `requirements.txt`)
- [Playwright](https://playwright.dev/python/docs/intro) for screenshot functionality
- Bluesky account (optional) with credentials for posting detected changes

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/govedits.git
   cd govedits
   ```

2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright and its browser dependencies:
   ```bash
   playwright install
   ```

4. The IP ranges database is included at `config/govedits - db.csv`
   - Contains IP address ranges from the [Whois ARIN](https://whois.arin.net) database
   - Format: `organization,start_ip,end_ip,is_federal`

5. (Optional) Add a `config.json` file for Bluesky posting:
   ```json
   {
       "email": "your_bluesky_email",
       "password": "your_bluesky_password"
   }
   ```

---

## Usage

### Stream Mode (Recommended)

Monitor Wikipedia in real-time using EventStreams with guaranteed delivery:

```bash
# Federal agencies only (default)
python main.py stream

# All government agencies
python main.py stream --filter all

# Congressional IPs only
python main.py stream --filter congress
```

**Features:**
- True real-time monitoring via Server-Sent Events
- Automatic reconnection if connection drops
- Catchup progress tracking with percentage display
- Resumes from last timestamp on restart
- Falls back to historical mode if gap >31 days

### Monitor Mode (Polling)

Poll Wikipedia's API every 10 seconds with continuation support:

```bash
# Federal agencies only (default)
python main.py monitor

# All government agencies
python main.py monitor --filter all

# Congressional IPs only
python main.py monitor --filter congress
```

**Features:**
- API continuation ensures no missed edits even if >500 changes occur
- 10-second polling interval
- Simpler and more stable than streaming (no connection drops)
- Shows batch count when fetching multiple batches

### Historical Mode

Scan past Wikipedia edits:

```bash
# Scan last 30 days (default, federal filter)
python main.py historical

# Scan last 90 days with all government agencies
python main.py historical --days 90 --filter all

# Scan last 7 days with Congress only
python main.py historical --days 7 --filter congress
```

**Features:**
- Processes past edits in batches
- Maintains queue with state persistence
- Rate-limited to respect Wikipedia API guidelines

---

## Output Files

### Log Files
- `wikipedia_monitor.log` - Realtime/Monitor mode logs
- `wikipedia_streaming.log` - Stream mode logs
- `historical_wikipedia_monitor.log` - Historical mode logs

### CSV Reports
- `government_changes.csv` - All detected changes from Monitor/Stream mode
- `sensitive_content_changes.csv` - Changes flagged for sensitive content
- `historical_government_changes.csv` - Historical mode changes
- `historical_sensitive_changes.csv` - Historical sensitive changes

### State Files
- `last_run_state.json` - Monitor mode state
- `streaming_state.json` - Stream mode state
- `catchup_state.json` - Historical mode state

### Screenshots
- Saved in `data/screenshots/` directory
- Organized by date (YYYY-MM-DD format)

---

## Configuration

### Filter Levels

Configured via command-line `--filter` option:
- `all` - All Government Agencies (1,749 total)
- `federal` - Federal Agencies Only (372 total) [DEFAULT]
- `congress` - Congressional IPs Only (House + Senate)

### Bluesky Posting

Enable/disable in `config/settings.py`:
```python
ENABLE_BLUESKY_POSTING = True  # Set to False to disable
```

Configure posting delay:
```python
BLUESKY_DELAY = 15  # Seconds between posts
```

### Polling Interval (Monitor Mode)

Configure in `config/settings.py`:
```python
REALTIME_POLL_INTERVAL = 10  # Seconds between polls
```

---

## How It Works

### Stream Mode
1. Connects to Wikipedia's EventStreams API (Server-Sent Events)
2. Receives real-time feed of all Wikipedia edits
3. Filters for English Wikipedia anonymous (IP) edits
4. Checks IPs against government ranges database
5. Takes screenshots and posts to Bluesky
6. Saves state every event for crash recovery
7. Auto-reconnects if connection drops

### Monitor Mode
1. Polls Wikipedia's Recent Changes API every 10 seconds
2. Uses continuation tokens to fetch all results (handles >500 edits)
3. Filters for anonymous editors from government IP ranges
4. Scans comments for sensitive content
5. Captures screenshots of diff pages
6. Optionally posts to Bluesky
7. Saves timestamp state for resumption

### Historical Mode
1. Fetches Wikipedia edits from configurable days backward
2. Processes in batches with queue management
3. Maintains state for interruption recovery
4. Same filtering and posting as other modes

---

## Project Structure

```
govedits/
├── main.py                 # CLI entry point
├── modes/
│   ├── streaming.py       # EventStreams monitoring
│   ├── realtime.py        # API polling monitoring
│   └── historical.py      # Historical scanning
├── core/
│   ├── ip_matcher.py      # IP range matching
│   ├── scanner.py         # Wikipedia API interaction
│   └── filters.py         # Filter level management
├── processors/
│   ├── screenshot.py      # Playwright screenshot capture
│   ├── csv_handler.py     # CSV output management
│   └── bluesky_poster.py  # Bluesky integration
├── config/
│   ├── settings.py        # Configuration constants
│   └── govedits - db.csv  # IP ranges database
└── utils/
    ├── helpers.py         # State management utilities
    └── logging_config.py  # Colored logging setup
```

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Acknowledgments

- [Wikipedia MediaWiki API](https://www.mediawiki.org/wiki/API:Main_page) for providing the data source
- [Wikipedia EventStreams](https://wikitech.wikimedia.org/wiki/Event_Platform/EventStreams) for real-time event streaming
- [Playwright](https://playwright.dev/) for automated screenshot capture
- [Bluesky](https://bsky.app/) for their API and platform
- [ARIN Whois](https://whois.arin.net) for IP range data

---

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

---

## Support

For questions or issues, please open an issue on GitHub.
