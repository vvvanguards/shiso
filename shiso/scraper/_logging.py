"""
Centralized structlog configuration for shiso.

Call `configure_logging()` once at application startup.
All modules then use `structlog.get_logger()` — no per-module setup needed.
"""

import logging
import structlog


def configure_logging(level: int = logging.INFO) -> None:
    """
    Configure structlog for the entire process.

    Sets up JSON output with timestamp, level, logger name, and any
    bound context vars (e.g. trace_id).

    Call once at startup before any other shiso imports.
    """
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

    # Quiet noisy third-party loggers
    for name in (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "alembic",
        "alembic.runtime.plugins",
        "watchfiles",
        "httpcore",
        "httpx",
    ):
        logging.getLogger(name).setLevel(logging.WARNING)
