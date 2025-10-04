#!/usr/bin/env python3
"""
Government Wikipedia Edit Monitor - Main CLI Entry Point

Monitor Wikipedia edits from government IP addresses and post to Bluesky.
"""
import argparse
import sys
from core.filters import get_filter_description, validate_filter
from config.settings import FILTER_ALL, FILTER_FEDERAL, FILTER_CONGRESS, DEFAULT_FILTER, DEFAULT_DAYS_TO_FETCH


def main():
    parser = argparse.ArgumentParser(
        description="Monitor Wikipedia edits from government IP addresses",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Real-time monitoring with federal filter (default)
  python main.py monitor

  # Real-time monitoring with all government agencies
  python main.py monitor --filter all

  # Real-time monitoring with Congress only
  python main.py monitor --filter congress

  # Historical scan of last 30 days (default) with federal filter
  python main.py historical

  # Historical scan of last 90 days with all government
  python main.py historical --days 90 --filter all

  # Historical scan of last 7 days with Congress only
  python main.py historical --days 7 --filter congress

Filter Options:
  all      - All Government Agencies (1,749 total)
  federal  - Federal Agencies Only (372 total) [DEFAULT]
  congress - Congressional IPs Only (House + Senate)
        """
    )

    subparsers = parser.add_subparsers(dest='mode', help='Operating mode', required=True)

    # Monitor (real-time) mode
    monitor_parser = subparsers.add_parser(
        'monitor',
        help='Real-time monitoring mode',
        description='Continuously monitor Wikipedia for government edits'
    )
    monitor_parser.add_argument(
        '--filter',
        choices=[FILTER_ALL, FILTER_FEDERAL, FILTER_CONGRESS],
        default=DEFAULT_FILTER,
        help=f'Government filter level (default: {DEFAULT_FILTER})'
    )

    # Historical mode
    historical_parser = subparsers.add_parser(
        'historical',
        help='Historical scanning mode',
        description='Scan past Wikipedia edits for government activity'
    )
    historical_parser.add_argument(
        '--days',
        type=int,
        default=DEFAULT_DAYS_TO_FETCH,
        help=f'Number of days to scan backwards (default: {DEFAULT_DAYS_TO_FETCH})'
    )
    historical_parser.add_argument(
        '--filter',
        choices=[FILTER_ALL, FILTER_FEDERAL, FILTER_CONGRESS],
        default=DEFAULT_FILTER,
        help=f'Government filter level (default: {DEFAULT_FILTER})'
    )

    args = parser.parse_args()

    # Validate filter
    if not validate_filter(args.filter):
        print(f"Error: Invalid filter '{args.filter}'")
        sys.exit(1)

    # Display configuration
    print(f"\n{'='*60}")
    print(f"Government Wikipedia Edit Monitor")
    print(f"{'='*60}")
    print(f"Mode: {args.mode.upper()}")
    print(f"Filter: {get_filter_description(args.filter)}")
    if args.mode == 'historical':
        print(f"Days to scan: {args.days}")
    print(f"{'='*60}\n")

    # Run appropriate mode
    if args.mode == 'monitor':
        from modes.realtime import run_realtime_monitor
        run_realtime_monitor(filter_level=args.filter)
    elif args.mode == 'historical':
        from modes.historical import run_historical_scan
        run_historical_scan(filter_level=args.filter, days=args.days)


if __name__ == "__main__":
    main()
