# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers for screenshot functionality
playwright install

# Real-time monitoring (default: federal agencies)
python main.py monitor

# Real-time monitoring with different filters
python main.py monitor --filter all        # All government agencies (1,749)
python main.py monitor --filter federal    # Federal only (372) [DEFAULT]
python main.py monitor --filter congress   # Congress only (House + Senate)

# Historical scan (default: 30 days, federal agencies)
python main.py historical

# Historical scan with custom days and filters
python main.py historical --days 90 --filter all      # Last 90 days, all agencies
python main.py historical --days 7 --filter congress  # Last 7 days, Congress only

# Legacy scripts (deprecated, use main.py instead)
python gov/wikipedia_monitor.py      # Old real-time monitor
python gov/wikipedia-catchup.py      # Old historical script
```

## Project Architecture (Refactored)

**Government Wikipedia Edit Monitor** - A modular Python tool that monitors Wikipedia edits from government IP addresses and posts findings to Bluesky.

### New Modular Structure

```
govedits/
├── config/
│   ├── settings.py          # Centralized configuration
│   └── ip_database.py        # IP range loading (future)
├── core/
│   ├── scanner.py            # Wikipedia API polling
│   ├── ip_matcher.py         # IPNetworkCache class
│   └── filters.py            # Government level filters
├── processors/
│   ├── screenshot.py         # Playwright screenshots
│   ├── csv_handler.py        # CSV operations
│   ├── bluesky_poster.py     # Social media posting
│   └── content_detector.py   # Sensitive content detection
├── modes/
│   ├── realtime.py           # Real-time monitoring
│   └── historical.py         # Historical scanning
├── utils/
│   ├── logging_config.py     # Colored logging
│   └── helpers.py            # Shared utilities
└── main.py                   # CLI entry point
```

### Core Components

1. **main.py** - Unified CLI entry point:
   - `monitor` mode: Real-time monitoring
   - `historical` mode: Historical scanning
   - `--filter` option: all/federal/congress
   - `--days` option: Configurable history window

2. **core/ip_matcher.py** - IP matching with 3-tier filtering:
   - IPNetworkCache class with filter_level parameter
   - Supports: all, federal, congress filters
   - Handles IPv4 and IPv6 normalization

3. **core/scanner.py** - Shared Wikipedia API logic:
   - fetch_recent_changes()
   - filter_ip_changes()
   - filter_government_changes()

4. **processors/** - Modular processing pipeline:
   - screenshot.py: Playwright automation
   - csv_handler.py: CSV read/write
   - bluesky_poster.py: Social media integration
   - content_detector.py: Sensitive content filtering

5. **modes/** - Operating modes:
   - realtime.py: Continuous polling (replaces wikipedia_monitor.py)
   - historical.py: Batch processing (replaces wikipedia-catchup.py)

### Key Features

- **3-Tier Government Filtering**:
  - **All** (1,749 agencies): All government levels
  - **Federal** (372 agencies): Federal agencies only [DEFAULT]
  - **Congress**: House of Representatives + Senate only

- **Configurable Time Ranges**: Scan last N days (--days flag)
- **Sensitive Content Detection**: Filters personal information before posting
- **Screenshot Automation**: Playwright-based diff capture
- **State Management**: Crash recovery and resume capability
- **Dual Output**: CSV files + optional Bluesky posting

### Configuration Files

- `gov/govedits - db.csv` - Government IP ranges database (required)
- `config.json` - Bluesky credentials (optional, for social posting)
- `last_run_state.json` - Monitor mode state
- `catchup_state.json` - Historical mode state
- `config/settings.py` - All configuration constants

### Important Settings (config/settings.py)

- `ENABLE_BLUESKY_POSTING` - Toggle social media posting (True/False)
- `FILTER_ALL` / `FILTER_FEDERAL` / `FILTER_CONGRESS` - Filter level constants
- `DEFAULT_FILTER` - Default filter level (federal)
- `DEFAULT_DAYS_TO_FETCH` - Default historical window (30 days)
- `PHONE_PATTERNS` / `ADDRESS_PATTERNS` - Content filtering regex

### Government Filter Details

The database includes an `is_federal` column:
- **Federal agencies** (372): U.S. Departments, bureaus, military, postal service
- **State/Local agencies** (1,377): State depts, cities, counties, schools
- **Congress subset**: House of Representatives + Senate (subset of federal)

### Data Flow

1. CLI invokes mode (monitor or historical) with filter level
2. Scanner fetches Wikipedia Recent Changes
3. Filter for anonymous (IP) editors
4. IP matcher checks against government ranges (with filter)
5. Content detector scans for sensitive information
6. Screenshot processor captures diff images
7. CSV handler saves to files
8. Bluesky poster publishes to social media (if enabled)
9. State files updated for crash recovery

### Migration Notes

- **Old scripts** (gov/wikipedia_monitor.py, gov/wikipedia-catchup.py) are deprecated
- **New CLI**: Use `python main.py monitor|historical` with --filter and --days options
- **Shared code**: ~80% reduction in duplication
- **Better testing**: Modular components are easier to test
- **Extensibility**: Easy to add new filters or output formats

The refactored architecture prioritizes maintainability, testability, and flexibility while preserving all original functionality.