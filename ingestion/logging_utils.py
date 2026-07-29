"""Minimal logger setup shared by ingestion scripts, independent from backend/app."""
import logging
import os

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


NOISY_THIRD_PARTY_LOGGERS = ["pdfminer", "pdfplumber", "PIL", "httpx", "httpcore"]


def configure_logging() -> None:
    environment = os.getenv("ENVIRONMENT", "development")
    level = logging.DEBUG if environment == "development" else logging.INFO
    logging.basicConfig(level=level, format=DEFAULT_LOG_FORMAT)

    for logger_name in NOISY_THIRD_PARTY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
