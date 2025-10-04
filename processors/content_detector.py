"""
Sensitive content detection in edit comments
"""
import re
import logging
from typing import List, Set, Tuple
from config.settings import PHONE_PATTERNS, ADDRESS_PATTERNS


def detect_sensitive_content(text: str, known_ids: Set[str] = None) -> Tuple[bool, List[Tuple[str, str]]]:
    """
    Detect sensitive content in the provided text while excluding known IDs.

    Args:
        text (str): The text to analyze.
        known_ids (Set[str]): Set of known IDs (e.g., revision IDs) to exclude from detection.

    Returns:
        Tuple[bool, List[Tuple[str, str]]]: A tuple where the first element indicates if sensitive
                                             content was found, and the second is a list of
                                             tuples containing the type and the matched content.
    """
    found_patterns = []
    known_ids = known_ids or set()

    # Log known IDs for debugging
    logging.debug(f"Known IDs to exclude: {known_ids}")

    # Check for phone numbers
    for pattern in PHONE_PATTERNS:
        for match in re.finditer(pattern, text):
            matched_content = match.group()
            if matched_content not in known_ids:
                logging.debug(f"Matched phone number: {matched_content}")
                found_patterns.append(("phone_number", matched_content))
            else:
                logging.debug(f"Excluded known ID: {matched_content}")

    # Check for addresses
    for pattern in ADDRESS_PATTERNS:
        for match in re.finditer(pattern, text):
            matched_content = match.group()
            found_patterns.append(("address", matched_content))

    return bool(found_patterns), found_patterns
