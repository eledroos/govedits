# Government Edits, on Bluesky

A Python-based tool to monitor anonymous edits on Wikipedia from government organizations, schools, and public institutions. This project is designed for researchers, journalists, and transparency advocates interested in how public entities interact with Wikipedia. [It posts updates automatically on Bluesky](https://bsky.app/profile/govedits.bsky.social) from a list that you create and provide.

## Features

1. **Real-Time Monitoring**:
   - Continuously polls Wikipedia's Recent Changes feed using the MediaWiki API.
   - Detects edits from IP addresses belonging to known government organizations and public institutions from the [Whois ARIN](https://whois.arin.net) database.

2. **Content Analysis**:
   - Flags potential sensitive information such as phone numbers and addresses within edit comments to prevent doxxing and misuse.

3. **Comprehensive Logging and Reporting**:
   - Saves all detected changes to a CSV file, including metadata such as the IP address, organization name, and edit timestamp.
   - Flags sensitive edits in a separate CSV for focused analysis.

4. **Screenshot Capture**:
   - Captures a visual representation of each Wikipedia edit (diff view) and organizes screenshots by date.

5. **Bluesky Integration** (Optional):
   - Automatically posts detected changes to Bluesky with a formatted message and optional screenshots.
   - Configurable to enable or disable Bluesky posting.

6. **Error Handling**:
   - Logs all errors for debugging and continues operation without crashing.
   - Automatically resumes from the last monitored timestamp upon restart.

---

## Getting Started

### Prerequisites

- Python 3.8 or higher
- Required Python packages (see `requirements.txt`)
- [Playwright](https://playwright.dev/python/docs/intro) for screenshot functionality
- Bluesky account (optional) with credentials for posting detected changes

### Installation

1. Clone the repository:

2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

3. Install Playwright and its browser dependencies:
   ```bash
   playwright install
   ```

4. Set up your `govedits - db.csv` file:
   - This CSV should contain IP address ranges and organization names for detecting edits. An example format:
     ```
     start_ip,end_ip,organization
     203.0.113.0,203.0.113.255,Example Government Organization
     ```

5. Add a `config.json` file for Bluesky (optional):
   ```json
   {
       "email": "your_bluesky_email",
       "password": "your_bluesky_password"
   }
   ```

---

## Usage

### Run the Monitor
Start the script to begin monitoring:

```bash
python gov/gov-poll-wikipedia.py
```

### Key Outputs
1. **Log File**: 
   - `wikipedia_monitor.log` contains detailed logs of all activity.
2. **Screenshots**:
   - Saved in the `diff_screenshots/` directory, organized by date.
3. **CSV Reports**:
   - `government_changes.csv`: All detected changes.
   - `sensitive_content_changes.csv`: Changes flagged for sensitive content.

### Configurations
- Enable or disable Bluesky posting in the script by setting:
  ```python
  ENABLE_BLUESKY_POSTING = True  # Set to False to disable Bluesky integration
  ```

---

## How It Works

1. **Polling Wikipedia**:
   - The script uses the MediaWiki API to fetch the latest anonymous edits.
   - It compares the editors' IP addresses against a database of known government IP ranges.

2. **Analyzing Content**:
   - Comments are scanned for phone numbers, addresses, and other potentially sensitive content.
   - Revision IDs and Diff IDs are dynamically excluded to prevent false positives.

3. **Logging and Reporting**:
   - All edits are logged in a CSV file for further analysis.
   - Sensitive edits are flagged and saved to a separate CSV.

4. **Screenshot Capture**:
   - Playwright automates the browser to capture a screenshot of the Wikipedia diff page for each detected change.

5. **Bluesky Posting**:
   - Detected changes are optionally posted to Bluesky, formatted as:
     ```
     [Article Title] Wikipedia article edited anonymously from [Organization].
     ```

---

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

---

## Acknowledgments

- [Wikipedia MediaWiki API](https://www.mediawiki.org/wiki/API:Main_page) for providing the data source.
- [Playwright](https://playwright.dev/) for automated screenshot capture.
- [Bluesky](https://bsky.app/) for their API and platform.

---