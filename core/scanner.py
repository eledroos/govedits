"""
Wikipedia Recent Changes API scanner
"""
import logging
import requests
from typing import Dict, List
from config.settings import WIKIPEDIA_API_URL, WIKIPEDIA_RC_PARAMS


def fetch_recent_changes(params: Dict = None) -> Dict:
    """
    Fetch recent changes from Wikipedia API

    Args:
        params: Optional custom parameters (defaults to WIKIPEDIA_RC_PARAMS)

    Returns:
        API response JSON as dict
    """
    if params is None:
        params = WIKIPEDIA_RC_PARAMS.copy()

    try:
        logging.info(f"Making request with params: {params}")
        response = requests.get(WIKIPEDIA_API_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        changes_count = len(data.get('query', {}).get('recentchanges', []))
        logging.info(f"Received {changes_count} recent changes")

        return data
    except requests.RequestException as e:
        logging.warning(f"Network error while fetching changes: {e}")
        return {"query": {"recentchanges": []}}


def filter_ip_changes(changes: List[Dict]) -> List[Dict]:
    """
    Filter changes to only those from IP addresses

    Args:
        changes: List of Wikipedia change dictionaries

    Returns:
        Filtered list containing only IP-based edits
    """
    from utils.helpers import is_ip_address

    return [
        change for change in changes
        if is_ip_address(change.get("user", ""))
    ]


def filter_government_changes(changes: List[Dict], ip_cache, processed_ids: set = None) -> List[Dict]:
    """
    Filter changes to only those from government IPs

    Args:
        changes: List of Wikipedia change dictionaries
        ip_cache: IPNetworkCache instance for IP matching
        processed_ids: Optional set of already processed rcids to skip

    Returns:
        Filtered list containing only government edits
    """
    from utils.helpers import is_ip_address

    if processed_ids is None:
        processed_ids = set()

    government_changes = []

    for change in changes:
        # Skip if already processed
        if change.get("rcid") in processed_ids:
            continue

        user = change.get("user", "")
        if is_ip_address(user):
            is_gov, org = ip_cache.check_ip(user)
            if is_gov:
                government_changes.append(change)

    return government_changes
