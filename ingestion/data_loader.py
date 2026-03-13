"""
Yelp data loaders

- Businesses: json_normalize to flatten nested attributes.* and hours.* dicts matching the Bronze schema.
- Reviews: chunked iterator (10K rows) to avoid loading ~7M rows into memory at once.
"""

import json
import os
from datetime import datetime, timezone
from typing import Generator

import pandas as pd

from config.settings import settings
from utils.logger import Logger

log = Logger.get(__name__)

REVIEW_CHUNK_SIZE = 10_000


def _clean_record(record: dict) -> dict:
    """Replace pandas NaN/NaT values with None for JSON serialization."""

    cleaned = {}
    for k, v in record.items():
        try:
            cleaned[k] = None if pd.isna(v) else v
        except Exception:
            cleaned[k] = v
    return cleaned


def load_businesses() -> Generator[dict, None, None]:
    """Loads Yelp businesses with flattened attributes.* and hours.* fields."""

    path = settings.yelp.BUSINESS_JSON_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Business JSON not found at: {path} — "
            f"check YELP_BUSINESS_JSON_PATH in your .env file."
        )
    log.info(f"Loading businesses from: {path}")

    with open(path) as f:
        records = [json.loads(line) for line in f]
    log.debug(f"Read {len(records):,} raw business records.")

    timestamp = datetime.now(timezone.utc).isoformat()
    count = 0

    df_normalised = pd.json_normalize(records, sep=".")
    for record in df_normalised.to_dict(orient="records"):
        record = _clean_record(record)
        record["ingestion_timestamp"] = timestamp
        yield record
        count += 1
    log.info(f"Loaded {count:,} business records.")


def load_reviews() -> Generator[dict, None, None]:
    """Loads Yelp reviews using a chunked iterator."""
    
    path = settings.yelp.REVIEW_JSON_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Review JSON not found at: {path} — "
            f"check YELP_REVIEW_JSON_PATH in your .env file."
        )
    log.info(f"Loading reviews from: {path} (in batches, {REVIEW_CHUNK_SIZE:,} rows/batch)")

    count = 0
    chunks = pd.read_json(path, lines=True, chunksize=REVIEW_CHUNK_SIZE)

    for chunk in chunks:
        timestamp = datetime.now(timezone.utc).isoformat()
        for record in chunk.to_dict(orient="records"):
            record = _clean_record(record)
            record["ingestion_timestamp"] = timestamp
            yield record
            count += 1
    log.info(f"Loaded {count:,} review records.")
