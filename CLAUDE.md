# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers for screenshot functionality
playwright install

# Run the main Wikipedia monitor (real-time monitoring)
# IMPORTANT: Run from project root directory
python gov/wikipedia_monitor.py

# Run historical catchup script (process past 30 days)
# IMPORTANT: Run from project root directory  
python gov/wikipedia-catchup.py

# Test IP matching functionality
# Uncomment test_ip_matching() call in wikipedia_monitor.py:733
python -c "import gov.wikipedia_monitor as m; m.test_ip_matching()"
```

## Project Architecture

**Government Wikipedia Edit Monitor** - A Python tool that monitors Wikipedia edits from government IP addresses and posts findings to Bluesky.

### Core Components

1. **wikipedia_monitor.py** - Real-time monitoring script that:
   - Polls Wikipedia's Recent Changes API continuously
   - Matches anonymous editor IPs against government IP ranges
   - Takes screenshots of edit diffs using Playwright
   - Posts findings to Bluesky with screenshots
   - Logs all activity and maintains state for restart recovery

2. **wikipedia-catchup.py** - Historical processing script that:
   - Processes past edits (configurable days, default 30)
   - Uses similar IP matching but optimized for batch processing
   - Maintains queue-based processing with state persistence
   - Handles API pagination and rate limiting

3. **IPNetworkCache Class** - Shared IP range matching system:
   - Loads government IP ranges from `govedits - db.csv`
   - Handles both IPv4 and IPv6 address normalization
   - Efficiently matches IPs against loaded ranges using integer comparison

### Key Features

- **Sensitive Content Detection**: Filters out personal information (phone numbers, addresses) from edit comments before posting
- **Screenshot Automation**: Uses Playwright to capture Wikipedia diff pages automatically
- **State Management**: Both scripts maintain state files for crash recovery and resume capability
- **Dual Output**: Saves to CSV files and optionally posts to Bluesky social media

### Configuration Files

- `govedits - db.csv` - Government IP ranges database (required)
- `config.json` - Bluesky credentials (optional, required for social posting)
- `last_run_state.json` - Monitor script state persistence
- `catchup_state.json` - Catchup script state persistence

### Important Constants

- `ENABLE_BLUESKY_POSTING` in wikipedia_monitor.py controls social media posting
- `FEDERAL_ONLY` in wikipedia_monitor.py filters for federal agencies only (True/False)
- `CONFIG['federal_only']` in wikipedia-catchup.py filters for federal agencies only (True/False)
- `CONFIG['days_to_fetch']` in wikipedia-catchup.py sets historical processing window
- Phone/address regex patterns in both scripts prevent doxxing

### Federal Agency Filtering

The database includes an `is_federal` column that categorizes agencies:
- **Federal agencies** (372 total): U.S. Departments, Federal bureaus, military, postal service, etc.
- **State/Local agencies** (1377 total): State departments, cities, counties, school districts, etc.

Toggle federal-only filtering by setting:
- `FEDERAL_ONLY = True` in wikipedia_monitor.py for real-time monitoring
- `CONFIG['federal_only'] = True` in wikipedia-catchup.py for historical processing

### Data Flow

1. Scripts poll Wikipedia Recent Changes API
2. Filter for anonymous (IP address) editors
3. Check IPs against government ranges database
4. Detect sensitive content in edit comments
5. Take screenshots of edit diffs
6. Save to CSV and optionally post to Bluesky
7. Update state files for recovery

The project prioritizes transparency while preventing misuse of personal information through content filtering and responsible disclosure practices.