"""
Shared utility functions
"""
import ipaddress
import json
import logging
from dateutil import parser


def is_ip_address(user: str) -> bool:
    """
    Check if a string is a valid IP address

    Args:
        user: String to check

    Returns:
        True if valid IP address, False otherwise
    """
    if not user or not isinstance(user, str):
        return False

    try:
        ipaddress.ip_address(user)
        return True
    except ValueError:
        return False


def save_state(state_file: str, last_timestamp: str):
    """
    Save state to JSON file

    Args:
        state_file: Path to state file
        last_timestamp: Last processed timestamp
    """
    with open(state_file, 'w') as f:
        json.dump({'last_timestamp': last_timestamp}, f)


def load_state(state_file: str) -> str:
    """
    Load state from JSON file

    Args:
        state_file: Path to state file

    Returns:
        Last processed timestamp or None if not found
    """
    try:
        with open(state_file, 'r') as f:
            data = json.load(f)
            return data.get('last_timestamp')
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def convert_timestamp(utc_timestamp: str) -> str:
    """
    Convert UTC timestamp to readable format

    Args:
        utc_timestamp: ISO format UTC timestamp

    Returns:
        Formatted timestamp string
    """
    return parser.isoparse(utc_timestamp).strftime('%Y-%m-%d %H:%M:%S')
