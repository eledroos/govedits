"""
IP Network Matching for Government Agencies
"""
import csv
import ipaddress
import logging
from typing import Tuple
from config.settings import GOV_IPS_FILE, FILTER_ALL, FILTER_FEDERAL, FILTER_CONGRESS


class IPNetworkCache:
    """Loads and matches IP addresses against government IP ranges"""

    def __init__(self, filter_level: str = FILTER_FEDERAL):
        """
        Initialize IP matcher with specified filter level

        Args:
            filter_level: One of 'all', 'federal', or 'congress'
        """
        self.networks = {
            'v4': [],  # List of tuples: (start_ip, end_ip, organization, is_federal, is_congress)
            'v6': []
        }
        self.filter_level = filter_level
        self.load_government_networks()

    def normalize_ipv4(self, ip_str: str) -> str:
        """Remove leading zeros from IPv4 address octets"""
        try:
            ip_str = ip_str.strip()
            parts = ip_str.split('.')
            cleaned_parts = []

            for part in parts:
                if part.strip() == '':
                    cleaned_parts.append('0')
                else:
                    cleaned_parts.append(str(int(part)))

            return '.'.join(cleaned_parts)
        except Exception as e:
            logging.debug(f"Error normalizing IPv4 address '{ip_str}': {e}")
            return ip_str

    def normalize_ipv6(self, ip_str: str) -> str:
        """Normalize IPv6 addresses"""
        try:
            ip_str = ip_str.strip()

            if ip_str.endswith('::'):
                ip_str = ip_str + '0'

            if 'ffff:ffff:ffff:ffff:ffff' in ip_str:
                return ip_str.replace('ffff:ffff:ffff:ffff:ffff', 'ffff:ffff:ffff:ffff:ffff')

            try:
                normalized = str(ipaddress.IPv6Address(ip_str))
                return normalized
            except:
                return ip_str

            return ip_str
        except Exception as e:
            logging.warning(f"Error normalizing IPv6 address {ip_str}: {e}")
            return ip_str

    def load_government_networks(self):
        """Load IP ranges from CSV based on filter level"""
        try:
            total_loaded = {'v4': 0, 'v6': 0}
            federal_loaded = {'v4': 0, 'v6': 0}
            congress_loaded = {'v4': 0, 'v6': 0}

            with open(GOV_IPS_FILE, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        start_ip = row.get('start_ip', '').strip()
                        end_ip = row.get('end_ip', '').strip()
                        org = row.get('organization', '').strip()
                        is_federal = row.get('is_federal', 'no').strip().lower() == 'yes'

                        if not start_ip or not end_ip or not org:
                            logging.warning(f"Skipping row with missing data: {row}")
                            continue

                        # Check if it's U.S. federal government (Congress, White House, Supreme Court, Executive agencies)
                        org_lower = org.lower()
                        is_congress = (
                            # Legislative Branch
                            'u.s. senate' in org_lower or
                            'united states senate' in org_lower or
                            'u.s. house of representatives' in org_lower or
                            'united states congress' in org_lower or
                            'congressional budget office' in org_lower or
                            'united states capitol police' in org_lower or
                            org_lower == 'senate' or
                            org_lower == 'house of representatives' or
                            # Executive Branch - White House
                            'white house' in org_lower or
                            'executive office of the president' in org_lower or
                            # Judicial Branch
                            'supreme court' in org_lower and 'u.s.' in org_lower or  # Exclude state supreme courts
                            'u.s. district court' in org_lower or
                            'united states district court' in org_lower or
                            'u.s. probation' in org_lower or
                            # Major Executive Departments (Cabinet-level)
                            'department of state' in org_lower or
                            'department of defense' in org_lower or
                            'department of justice' in org_lower or
                            'department of the treasury' in org_lower or
                            'department of homeland security' in org_lower or
                            'department of agriculture' in org_lower or
                            'department of commerce' in org_lower or
                            'department of labor' in org_lower or
                            'department of education' in org_lower or
                            'department of energy' in org_lower or
                            'department of health and human services' in org_lower or
                            'department of housing and urban development' in org_lower or
                            'department of the interior' in org_lower or
                            'department of transportation' in org_lower or
                            'department of veterans affairs' in org_lower or
                            # Major Federal Agencies
                            'federal bureau of investigation' in org_lower or
                            'fbi' in org_lower or
                            'federal aviation administration' in org_lower or
                            'federal communications commission' in org_lower or
                            'federal election commission' in org_lower or
                            'federal emergency management agency' in org_lower or
                            'federal energy regulatory commission' in org_lower or
                            'federal highway administration' in org_lower or
                            'federal trade commission' in org_lower or
                            'federal reserve' in org_lower or
                            'federal retirement thrift investment board' in org_lower or
                            'food and drug administration' in org_lower or
                            'united states postal service' in org_lower or
                            'united states mint' in org_lower or
                            'united states patent and trademark office' in org_lower or
                            'nuclear regulatory commission' in org_lower or
                            'united states air force' in org_lower or
                            'united states coast guard' in org_lower or
                            'department of the air force' in org_lower
                        )

                        # Apply filter
                        if self.filter_level == FILTER_CONGRESS and not is_congress:
                            continue
                        elif self.filter_level == FILTER_FEDERAL and not is_federal:
                            continue
                        # FILTER_ALL includes everything

                        # Check if it's IPv6 (contains ::)
                        if '::' in start_ip:
                            try:
                                start = ipaddress.IPv6Address(self.normalize_ipv6(start_ip))
                                end = ipaddress.IPv6Address(self.normalize_ipv6(end_ip))
                                self.networks['v6'].append((int(start), int(end), org, is_federal, is_congress))
                                total_loaded['v6'] += 1
                                if is_federal:
                                    federal_loaded['v6'] += 1
                                if is_congress:
                                    congress_loaded['v6'] += 1
                            except Exception as e:
                                logging.warning(f"Error processing IPv6 range for {org}: {start_ip} - {end_ip}: {e}")
                        else:
                            # Handle IPv4 addresses
                            try:
                                start_ip = self.normalize_ipv4(start_ip)
                                end_ip = self.normalize_ipv4(end_ip)

                                start = ipaddress.IPv4Address(start_ip)
                                end = ipaddress.IPv4Address(end_ip)
                                self.networks['v4'].append((int(start), int(end), org, is_federal, is_congress))
                                total_loaded['v4'] += 1
                                if is_federal:
                                    federal_loaded['v4'] += 1
                                if is_congress:
                                    congress_loaded['v4'] += 1
                            except Exception as e:
                                logging.warning(f"Error processing IPv4 range for {org}: {start_ip} - {end_ip}: {e}")

                    except Exception as e:
                        logging.warning(f"Error processing IP range: {e}")

            filter_msg = f" ({self.filter_level} only)"
            logging.info(f"Loaded {total_loaded['v4']} IPv4 ranges and {total_loaded['v6']} IPv6 ranges{filter_msg}")

            if self.filter_level == FILTER_ALL:
                logging.info(f"Federal agencies: {federal_loaded['v4']} IPv4 and {federal_loaded['v6']} IPv6 ranges")
                logging.info(f"Congress: {congress_loaded['v4']} IPv4 and {congress_loaded['v6']} IPv6 ranges")

        except Exception as e:
            logging.error(f"Error loading government networks: {e}")

    def check_ip(self, ip_str: str) -> Tuple[bool, str]:
        """Check if an IP is within any of our ranges"""
        try:
            # Try to normalize the IP address
            try:
                if ':' in ip_str:  # IPv6
                    ip_str = self.normalize_ipv6(ip_str)
                else:  # IPv4
                    ip_str = self.normalize_ipv4(ip_str)
            except:
                pass

            ip = ipaddress.ip_address(ip_str)
            ip_int = int(ip)

            # Choose the correct network list based on IP version
            network_list = self.networks['v6'] if isinstance(ip, ipaddress.IPv6Address) else self.networks['v4']

            # Check if IP falls within any range
            for start_ip, end_ip, org, is_federal, is_congress in network_list:
                if start_ip <= ip_int <= end_ip:
                    return True, org

            return False, ""
        except ValueError as e:
            logging.warning(f"Invalid IP address format: {ip_str} - {e}")
            return False, ""
        except Exception as e:
            logging.warning(f"Error checking IP {ip_str}: {e}")
            return False, ""
