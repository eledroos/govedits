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

    p = None
    browser = None
    context = None
    page = None

    try:
        logging.debug(f"Starting Playwright for {title}")
        p = sync_playwright().start()
        logging.debug("Playwright started")

        # Try Firefox first, fallback to Chromium
        try:
            browser = p.firefox.launch(headless=True)
            logging.debug(f"Firefox browser launched for {title}")
        except Exception as e:
            logging.debug(f"Firefox launch failed: {e}, trying Chromium")
            browser = p.chromium.launch(headless=True)
            logging.debug(f"Chromium browser launched for {title}")

        # Create context with viewport size
        context = browser.new_context(
            viewport={'width': 1000, 'height': 1920}
        )
        logging.debug("Context created")

        # Create page
        page = context.new_page()
        logging.debug("Page created")

        # Go to URL and wait for content to load (increased timeout)
        logging.debug(f"Loading URL: {diff_url}")
        page.goto(diff_url, wait_until="networkidle", timeout=30000)
        logging.debug("Page loaded")

        # Wait a bit for any dynamic content
        page.wait_for_timeout(2000)
        logging.debug("Waited for dynamic content")

        # Take screenshot of top portion
        logging.debug(f"Taking screenshot to: {filepath}")
        page.screenshot(
            path=filepath,
            clip={
                'x': 0,
                'y': 0,
                'width': 1000,
                'height': 1200
            }
        )
        logging.debug(f"Screenshot saved successfully: {filepath}")

        return filepath

    except Exception as e:
        logging.warning(f"Error taking screenshot for {title}: {str(e)}")
        import traceback
        logging.debug(f"Full traceback: {traceback.format_exc()}")
        return None

    finally:
        # Explicit cleanup in reverse order
        try:
            if page:
                page.close()
                logging.debug("Page closed")
        except Exception as e:
            logging.debug(f"Error closing page: {e}")
        try:
            if context:
                context.close()
                logging.debug("Context closed")
        except Exception as e:
            logging.debug(f"Error closing context: {e}")
        try:
            if browser:
                browser.close()
                logging.debug("Browser closed")
        except Exception as e:
            logging.debug(f"Error closing browser: {e}")
        try:
            if p:
                p.stop()
                logging.debug("Playwright stopped")
        except Exception as e:
            logging.debug(f"Error stopping Playwright: {e}")
