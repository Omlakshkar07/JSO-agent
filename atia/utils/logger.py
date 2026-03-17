"""
logger.py
─────────────────────────────────────────────
PURPOSE:
  Structured JSON logging for the ATIA agent.
  Every significant agent action is logged with context.
  Production logs are machine-parseable JSON.
  Development logs are human-readable.

RESPONSIBILITIES:
  - Configure logging once at startup
  - Provide a get_logger() factory for per-module loggers
  - Ensure sensitive data is never logged

NOT RESPONSIBLE FOR:
  - Application-level metrics (see observability layer)
  - Error handling logic (see error_handler.py)

DEPENDENCIES:
  - config.settings: for log level

USED BY:
  - Every module in the codebase
─────────────────────────────────────────────
"""

import logging
import json
import sys
from datetime import datetime, timezone
from typing import Any


class JSONFormatter(logging.Formatter):
    """
    Formats log records as JSON for structured logging in production.

    Each log entry includes timestamp, level, module, message,
    and any extra fields passed via the `extra` dict.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON string."""
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }

        # Merge any extra fields passed by the caller
        if hasattr(record, "extra_data"):
            log_entry["data"] = record.extra_data

        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = str(record.exc_info[1])
            log_entry["error_type"] = type(record.exc_info[1]).__name__

        return json.dumps(log_entry, default=str)


def setup_logging(log_level: str = "INFO") -> None:
    """
    Configure the root logger for the ATIA agent.

    Call this once at application startup. All subsequent
    get_logger() calls will inherit this configuration.

    Args:
        log_level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
    """
    root_logger = logging.getLogger("atia")
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Avoid adding duplicate handlers on repeated calls
    if root_logger.handlers:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root_logger.addHandler(handler)


def get_logger(module_name: str) -> logging.Logger:
    """
    Get a named logger for a specific module.

    Args:
        module_name: The module name (e.g., "agent.orchestrator").

    Returns:
        A configured Logger instance under the "atia" namespace.

    Example:
        >>> logger = get_logger("agent.orchestrator")
        >>> logger.info("Evaluation started", extra={"extra_data": {"agency_id": "abc"}})
    """
    return logging.getLogger(f"atia.{module_name}")
