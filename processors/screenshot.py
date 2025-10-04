"""
Screenshot capture for Wikipedia diff pages
"""
import os
import logging
from playwright.sync_api import sync_playwright
from dateutil import parser
from config.settings import SCREENSHOTS_DIR, WIKIPEDIA_DIFF_BASE_URL


def sanitize_filename(filename: str) -> str:
    """Remove or replace invalid filename characters"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename


def create_diff_url(rev_id: int, parent_id: int) -> str:
    """Create Wikipedia diff URL"""
    return f"{WIKIPEDIA_DIFF_BASE_URL}?diff={rev_id}&oldid={parent_id}"


def take_screenshot(diff_url: str, title: str, timestamp: str) -> str:
    """
    Take screenshot of Wikipedia diff page

    Args:
        diff_url: URL to the Wikipedia diff page
        title: Article title for filename
        timestamp: ISO timestamp for organizing screenshots

    Returns:
        Path to saved screenshot, or None if failed
    """
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
