"""Structured logging configuration for STC using Rich and standard logging."""

import logging

from rich.logging import RichHandler


def get_logger(name: str = "stc") -> logging.Logger:
    """Returns a configured logger instance with Rich formatting."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = RichHandler(
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_path=False,
        )
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger
