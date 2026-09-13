import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"


def setup_logging(level: int = logging.INFO, log_to_file: bool = True, log_to_console: bool = False) -> None:
    """Configures application-wide logging with file and optional console handlers."""
    handlers = []

    # File Handler
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

    # Console Handler (enabled if log_to_console=True or in DEBUG mode)
    if log_to_console or level <= logging.DEBUG:
        console_handler = logging.StreamHandler(sys.stdout)
        console_formatter = logging.Formatter(
            "\033[90m[DEBUG] [%(name)s] %(message)s\033[0m"
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(level)
        handlers.append(console_handler)

    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True
    )
