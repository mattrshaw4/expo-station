"""Shared helpers for the kitchen services: menu, JSON logging, connection settings."""

import json
import logging
import os
import sys
import time

# The menu. Each dish has a (min, max) cook time in seconds for the line worker.
MENU = {
    "burger": (1.0, 3.0),
    "fries": (0.5, 1.5),
    "salad": (0.5, 1.5),
    "steak": (3.0, 6.0),
    "risotto": (4.0, 8.0),
}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, so Loki/Alloy can parse fields later (Phase 3)."""

    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname.lower(),
            "service": self.service,
            "msg": record.getMessage(),
        }
        payload.update(getattr(record, "fields", {}))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def get_logger(service: str) -> logging.Logger:
    logger = logging.getLogger(service)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(service))
        logger.addHandler(handler)
        logger.propagate = False
    logger.setLevel(os.getenv("LOG_LEVEL", "info").upper())
    return logger


def log(logger: logging.Logger, level: int, msg: str, **fields) -> None:
    """Log with structured fields, e.g. log(logger, logging.INFO, "ticket fired", order_id=42)."""
    logger.log(level, msg, extra={"fields": fields})


def _read_secret(path_env: str, fallback_env: str) -> str:
    """Prefer a Docker secret file (*_FILE); fall back to a plain env var for local runs."""
    path = os.getenv(path_env)
    if path:
        with open(path, encoding="utf-8") as f:
            return f.read().strip()
    return os.getenv(fallback_env, "")


def db_conninfo() -> dict:
    return {
        "host": os.getenv("POSTGRES_HOST", "db"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "kitchen"),
        "user": os.getenv("POSTGRES_USER", "chef"),
        "password": _read_secret("POSTGRES_PASSWORD_FILE", "POSTGRES_PASSWORD"),
    }


REDIS_URL = os.getenv("REDIS_URL", "redis://rail:6379/0")
RAIL_KEY = "rail"  # the Redis list tickets wait on, like the ticket rail in a kitchen
