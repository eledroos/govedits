"""
Government level filtering utilities
"""
from config.settings import FILTER_ALL, FILTER_FEDERAL, FILTER_CONGRESS


def get_filter_description(filter_level: str) -> str:
    """Get human-readable description of filter level"""
    descriptions = {
        FILTER_ALL: "All Government Agencies (1,749 total)",
        FILTER_FEDERAL: "Federal Agencies Only (372 total)",
        FILTER_CONGRESS: "Congressional IPs Only (House + Senate)"
    }
    return descriptions.get(filter_level, "Unknown filter")


def validate_filter(filter_level: str) -> bool:
    """Validate if filter level is valid"""
    return filter_level in [FILTER_ALL, FILTER_FEDERAL, FILTER_CONGRESS]


def is_congress_org(org_name: str) -> bool:
    """Check if organization name indicates Congress"""
    org_lower = org_name.lower()
    return 'senate' in org_lower or 'house of representatives' in org_lower
