"""Logging setup: writes to stdout (for `docker logs`) and a rotating file."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

LOGGER_NAME = "ado_backup"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level="INFO", file=None, max_bytes=10 * 1024 * 1024,
                  backup_count=5):
    """Configure the shared 'ado_backup' logger. Returns the logger."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    if file:
        directory = os.path.dirname(file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        file_handler = RotatingFileHandler(
            file, maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger():
    """Return the shared logger (may be unconfigured if setup_logging not called)."""
    return logging.getLogger(LOGGER_NAME)
