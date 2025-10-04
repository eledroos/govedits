"""
Logging configuration with colored console output
"""
import logging
import colorama

colorama.init()


class ColoredFormatter(logging.Formatter):
    """Adds colors and emojis to console logging"""
    COLORS = {
        logging.DEBUG: colorama.Fore.WHITE,
        logging.INFO: colorama.Fore.CYAN,
        logging.WARNING: colorama.Fore.YELLOW,
        logging.ERROR: colorama.Fore.RED,
        logging.CRITICAL: colorama.Fore.RED,
    }
    EMOJIS = {
        logging.DEBUG: "🐛 ",
        logging.INFO: "ℹ️ ",
        logging.WARNING: "⚠️ ",
        logging.ERROR: "❌ ",
        logging.CRITICAL: "💥 "
    }

    def format(self, record):
        emoji = self.EMOJIS.get(record.levelno, "🔍")
        color = self.COLORS.get(record.levelno, colorama.Fore.WHITE)
        message = super().format(record)
        return f"{color}{emoji} {message}{colorama.Style.RESET_ALL}"


def setup_logging(log_file: str = "wikipedia_monitor.log"):
    """
    Configure logging with both file and colored console output

    Args:
        log_file: Path to log file
    """
    # Suppress HTTP request logging
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)

    # File handler (plain text)
    file_handler = logging.FileHandler(log_file)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler (colored) - only show warnings/errors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(ColoredFormatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    logger.addHandler(console_handler)
