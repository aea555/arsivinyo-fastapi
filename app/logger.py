"""
Centralized logging utility for the Media Downloader API.

In PRODUCTION mode (ENV=production), only ERROR and CRITICAL logs are emitted.
In DEVELOPMENT mode, all logs (DEBUG, INFO, WARNING, ERROR, CRITICAL) are emitted.

Usage:
    from app.logger import get_logger
    logger = get_logger(__name__)
    
    logger.debug("Only in dev")
    logger.info("Only in dev")
    logger.warning("Only in dev")
    logger.error("Always logged")
    logger.critical("Always logged")
"""

import logging
import os

# Determine environment once at module load
IS_PRODUCTION = os.getenv("ENV", "development").lower() == "production"


class ProductionFilter(logging.Filter):
    """Filter that only allows ERROR and CRITICAL in production."""
    
    def filter(self, record):
        if IS_PRODUCTION:
            return record.levelno >= logging.ERROR
        return True


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger configured for the current environment.
    
    In production: Only ERROR and CRITICAL are logged.
    In development: All levels are logged.
    """
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(levelname)s:%(name)s:%(message)s"
        )
        handler.setFormatter(formatter)
        handler.addFilter(ProductionFilter())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG if not IS_PRODUCTION else logging.ERROR)
    
    return logger


# Convenience: Pre-configured logger for quick imports
dev_logger = get_logger("app")
