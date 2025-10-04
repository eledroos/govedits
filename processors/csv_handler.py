"""
CSV file handling for government edits
"""
import csv
import os
import logging
from typing import Dict, List, Set, Tuple
from dateutil import parser
from processors.content_detector import detect_sensitive_content
from processors.screenshot import create_diff_url


def convert_timestamp(utc_timestamp: str) -> str:
    """Convert UTC timestamp to readable format"""
    return parser.isoparse(utc_timestamp).strftime('%Y-%m-%d %H:%M:%S')


def save_to_csv(changes: List[Dict], ip_cache, output_csv: str = "government_changes.csv",
                sensitive_csv: str = "sensitive_content_changes.csv", screenshot_path: str = None):
    """
    Save government changes to CSV files

    Args:
        changes: List of Wikipedia change dictionaries
        ip_cache: IPNetworkCache instance for organization lookup
        output_csv: Path to main output CSV file
        sensitive_csv: Path to sensitive content CSV file
        screenshot_path: Optional path to screenshot
    """
    file_exists = os.path.isfile(output_csv)
    sensitive_exists = os.path.isfile(sensitive_csv)

    with open(output_csv, mode="a", newline="", encoding="utf-8") as file, \
         open(sensitive_csv, mode="a", newline="", encoding="utf-8") as sensitive_file:

        writer = csv.writer(file)
        sensitive_writer = csv.writer(sensitive_file)

        if not file_exists:
            writer.writerow([
                "Title", "IP Address", "Government Organization", "Timestamp",
                "Edit ID", "Old Size", "New Size", "Revision ID", "Parent ID",
                "Diff URL", "Comment", "Screenshot Path", "Contains Sensitive Info"
            ])

        if not sensitive_exists:
            sensitive_writer.writerow([
                "Title", "IP Address", "Government Organization", "Timestamp",
                "Edit ID", "Diff URL", "Comment", "Sensitive Content Types"
            ])

        for change in changes:
            comment = change.get("comment", "")
            known_ids = {str(change.get("revid", "")), str(change.get("parentid", ""))}
            is_sensitive, content_matches = detect_sensitive_content(comment, known_ids=known_ids)

            diff_url = create_diff_url(change.get("revid"), change.get("parentid"))

            _, org = ip_cache.check_ip(change.get("user"))

            # Save to main CSV
            writer.writerow([
                change.get("title"),
                change.get("user"),
                org,
                convert_timestamp(change.get("timestamp")),
                change.get("rcid"),
                change.get("oldlen", ""),
                change.get("newlen", ""),
                change.get("revid"),
                change.get("parentid"),
                diff_url,
                comment,
                screenshot_path or "",
                "Yes" if is_sensitive else "No"
            ])

            # If sensitive, save to separate CSV
            if is_sensitive:
                matched_types = [match[0] for match in content_matches]
                matched_content = [match[1] for match in content_matches]
                sensitive_writer.writerow([
                    change.get("title"),
                    change.get("user"),
                    org,
                    convert_timestamp(change.get("timestamp")),
                    change.get("rcid"),
                    diff_url,
                    comment,
                    ", ".join(matched_types),
                    "; ".join(matched_content)
                ])
                logging.warning(f"Sensitive content detected in edit by {change.get('user')} "
                    f"({org}) to {change.get('title')} with matches: {', '.join(matched_content)}")
