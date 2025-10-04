"""
Bluesky social media posting functionality
"""
import json
import logging
import os
import time
from typing import Dict, List
import piexif
import pytz
from dateutil import parser
from atproto import Client, models
from processors.screenshot import create_diff_url
from config.settings import CONFIG_FILE, ENABLE_BLUESKY_POSTING, BLUESKY_DELAY


def load_bluesky_credentials(config_file: str = CONFIG_FILE) -> Dict:
    """Load Bluesky credentials from a JSON config file"""
    try:
        with open(config_file) as f:
            return json.load(f)
    except FileNotFoundError:
        logging.error("Bluesky credentials file not found.")
        return None


def strip_exif(image_path: str):
    """Remove EXIF data from image"""
    try:
        piexif.remove(image_path)
    except Exception:
        pass  # Not all images have EXIF data


def upload_image(client: Client, image_path: str) -> dict:
    """Upload an image and return the blob"""
    if not os.path.exists(image_path):
        raise Exception(f"Image file not found: {image_path}")

    # Strip EXIF data
    strip_exif(image_path)

    with open(image_path, "rb") as f:
        img_bytes = f.read()

    # Check file size
    if len(img_bytes) > 1000000:
        raise Exception(f"Image too large: {len(img_bytes)} bytes. Maximum is 1,000,000 bytes")

    # Upload the image
    response = client.com.atproto.repo.upload_blob(img_bytes)
    return response.blob


def create_facets_for_url(text: str, url: str) -> List[Dict]:
    """Create facets for a URL in text on Bluesky"""
    # Convert text to bytes to get correct byte positions
    text_bytes = text.encode('utf-8')
    url_bytes = url.encode('utf-8')

    # Find the byte position of the URL in the text
    start_pos = text_bytes.find(url_bytes)
    if start_pos == -1:
        return []

    end_pos = start_pos + len(url_bytes)

    return [{
        "index": {
            "byteStart": start_pos,
            "byteEnd": end_pos
        },
        "features": [{
            "$type": "app.bsky.richtext.facet#link",
            "uri": url
        }]
    }]


def post_to_bluesky(changes: List[Dict], bluesky_credentials_file: str = CONFIG_FILE, delay: int = BLUESKY_DELAY):
    """
    Post changes to Bluesky if ENABLE_BLUESKY_POSTING is True

    Args:
        changes: List of change dictionaries with keys: title, organization, screenshot_path, change_data
        bluesky_credentials_file: Path to credentials JSON
        delay: Delay between posts in seconds
    """
    if not ENABLE_BLUESKY_POSTING:
        logging.info("Bluesky posting is disabled. No posts will be made.")
        return

    # Load Bluesky credentials
    bluesky_credentials = load_bluesky_credentials(bluesky_credentials_file)
    if not bluesky_credentials:
        logging.error("Bluesky credentials are missing. Skipping posting.")
        return

    # Initialize Bluesky client
    try:
        client = Client()
        client.login(bluesky_credentials['email'], bluesky_credentials['password'])
    except Exception as e:
        logging.error(f"Failed to log in to Bluesky: {e}")
        return

    # Post each change to Bluesky
    for change in changes:
        try:
            title = change.get("title")
            org = change.get("organization", "Unknown Organization")
            diff_url = create_diff_url(
                change.get("change_data", {}).get("revid"),
                change.get("change_data", {}).get("parentid")
            )
            screenshot_path = change.get("screenshot_path")

            # Format timestamp for display (convert to US Eastern Time)
            timestamp = change.get("change_data", {}).get("timestamp")
            if timestamp:
                utc_time = parser.isoparse(timestamp)
                eastern = pytz.timezone('America/New_York')
                local_time = utc_time.astimezone(eastern)
                edit_date = local_time.strftime('%b %d, %Y at %-I:%M %p %Z')
                text = f"{title} Wikipedia article edited anonymously from {org} on {edit_date}.\n\n{diff_url}"
            else:
                text = f"{title} Wikipedia article edited anonymously from {org}.\n\n{diff_url}"

            facets = create_facets_for_url(text, diff_url)

            if screenshot_path and os.path.exists(screenshot_path):
                try:
                    blob = upload_image(client, screenshot_path)
                    embed = {
                        "$type": "app.bsky.embed.images",
                        "images": [{"alt": f"Screenshot of edit for {title}", "image": blob}]
                    }
                    client.send_post(text=text, facets=facets, embed=embed)
                    logging.info(f"Posted to Bluesky with image: {text}")
                except Exception as e:
                    logging.warning(f"Failed to upload image for Bluesky post: {e}")
                    client.send_post(text=text, facets=facets)
                    logging.info(f"Posted to Bluesky without image: {text}")
            else:
                logging.warning(f"Screenshot missing for {title}. Posting text-only.")
                client.send_post(text=text, facets=facets)

            # Respect delay to avoid rate limiting
            time.sleep(delay)

        except Exception as e:
            logging.error(f"Error posting to Bluesky: {e}")
