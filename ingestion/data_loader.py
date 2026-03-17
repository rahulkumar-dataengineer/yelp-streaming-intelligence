"""
Yelp data loaders
Both loaders stream line-by-line from newline-delimited JSON, yielding one dict
at a time with constant memory overhead regardless of file size.
"""

import json
import os
from itertools import islice
from typing import Generator

from config.settings import settings
from platform_commons.logger import Logger

log = Logger.get(__name__)


def _validate_path(path: str, label: str) -> None:
    """Raise FileNotFoundError if path does not exist."""

    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{label} JSON not found at: {path} — "
            f"check the corresponding path in your .env file."
        )


def _flatten(record: dict, sep: str = "_") -> dict:
    """Iteratively flatten nested dicts."""

    items: dict = {}
    stack = list(record.items())

    while stack:
        key, value = stack.pop()
        if isinstance(value, dict):
            for k, v in value.items():
                stack.append((f"{key}{sep}{k}", v))
        else:
            items[key] = value
    return items


def _clean_record(record: dict) -> dict:
    """Coerce all values to str (Avro schema is all-STRING), NaN/empty → None."""

    cleaned = {}
    for k, v in record.items():
        if v is None or v == "" or (isinstance(v, float) and v != v):
            cleaned[k] = None
        else:
            cleaned[k] = str(v)
    return cleaned


def load_businesses() -> Generator[dict, None, None]:
    """Loads Yelp businesses with flattened attributes_* and hours_* fields."""

    path = settings.yelp.BUSINESS_JSON_PATH
    _validate_path(path, "Business")
    log.info(f"Loading businesses from: {path}")

    count = 0

    with open(path) as f:
        for line in f:
            record = _flatten(json.loads(line))
            yield _clean_record(record)
            count += 1
    log.info(f"Loaded {count:,} business records.")


def load_reviews() -> Generator[dict, None, None]:
    """Loads Yelp reviews line-by-line from newline-delimited JSON.

    Capped at settings.yelp.REVIEW_LIMIT records (default 1,000,000).
    Set REVIEW_LIMIT=0 in .env to disable the cap and load all records.
    """

    path = settings.yelp.REVIEW_JSON_PATH
    _validate_path(path, "Review")
    limit = settings.yelp.REVIEW_LIMIT
    log.info(f"Loading reviews from: {path} (limit: {limit:,})")

    count = 0

    with open(path) as f:
        for line in islice(f, limit or None):
            record = json.loads(line)
            yield _clean_record(record)
            count += 1
    log.info(f"Loaded {count:,} review records.")
