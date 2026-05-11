"""
Loguru-based logging for Remedi.

Development : coloured console, DEBUG level, file + line shown.
Production  : JSON to logs/remedi.log, INFO level, 100 MB rotation, 30-day retention.

Call order in main.py:
    load_dotenv()          ← must happen first so ENVIRONMENT is in os.environ
    from utils.logger import logger   ← this module auto-configures on first import
"""
import logging
import os
import sys
from pathlib import Path

from loguru import logger


class InterceptHandler(logging.Handler):
    """Route standard-library logging (uvicorn, APScheduler, etc.) through loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = logging.currentframe(), 2
        while frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _setup(environment: str) -> None:
    logger.remove()  # Drop loguru's default stderr sink

    if environment == "production":
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        logger.add(
            log_dir / "remedi.log",
            level="INFO",
            serialize=True,       # JSON output
            rotation="100 MB",
            retention="30 days",
            enqueue=True,         # thread-safe, async-friendly
        )
        logger.add(
            sys.stderr,
            level="INFO",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        )
    else:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format=(
                "<green>{time:HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{line}</cyan> — "
                "<level>{message}</level>"
            ),
            colorize=True,
        )

    # Intercept uvicorn / fastapi / APScheduler standard-library logging
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for _name in ("uvicorn", "uvicorn.error", "uvicorn.access",
                  "fastapi", "apscheduler"):
        _log = logging.getLogger(_name)
        _log.handlers = [InterceptHandler()]
        _log.propagate = False


_setup(os.getenv("ENVIRONMENT", "development"))

__all__ = ["logger"]
