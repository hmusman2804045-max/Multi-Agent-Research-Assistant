import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"


class ColoredConsoleFormatter(logging.Formatter):
    """Format console output with subtle colors for debug and warnings."""
    
    COLORS = {
        logging.DEBUG: "\033[90m[DEBUG]\033[0m",
        logging.INFO: "\033[36m[INFO]\033[0m",
        logging.WARNING: "\033[33m[WARNING]\033[0m",
        logging.ERROR: "\033[31m[ERROR]\033[0m",
        logging.CRITICAL: "\033[41m[CRITICAL]\033[0m"
    }

    def format(self, record: logging.LogRecord) -> str:
        level_tag = self.COLORS.get(record.levelno, f"[{record.levelname}]")
        return f"{level_tag} [{record.name}] {record.getMessage()}"


def setup_logging(level: int = logging.INFO, log_to_file: bool = True, log_to_console: bool = True) -> None:
    """Configures application-wide logging with file and live console handlers."""
    handlers = []

    # 1. File Handler (captures all events with timestamp and lineno)
    if log_to_file:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOGS_DIR / "research_assistant.log", encoding="utf-8")
        file_formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(level)
        handlers.append(file_handler)

    # 2. Live Console Stream Handler
    if log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ColoredConsoleFormatter())
        console_handler.setLevel(level)
        handlers.append(console_handler)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True
    )


def get_logger(name: str = __name__) -> logging.Logger:
    """Return a configured logger instance for the given module name."""
    return logging.getLogger(name)

