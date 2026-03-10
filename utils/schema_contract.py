"""
Kafka Message Schema Contract
──────────────────────────────
This module is the SINGLE SOURCE OF TRUTH for the yelp_stream topic schema.

Any change to field names or types must be made HERE ONLY.
Both producer.py and spark_stream.py derive their schema from this module.
"""

import json
import pandas as pd


FIELD_BUSINESS_ID = "business_id"
FIELD_NAME = "name"
FIELD_CITY = "city"
FIELD_STATE = "state"
FIELD_BUSINESS_STARS = "business_stars"
FIELD_CATEGORIES = "categories"
FIELD_REVIEW_ID = "review_id"
FIELD_REVIEW_STARS = "review_stars"
FIELD_REVIEW_TEXT = "review_text"
FIELD_REVIEW_DATE = "review_date"


def row_to_message(row: pd.Series) -> bytes:
    """
    Converts a joined DataFrame row into a UTF-8 encoded JSON Kafka payload.
    """
    payload = {
        FIELD_BUSINESS_ID:      row[FIELD_BUSINESS_ID],
        FIELD_NAME:             row[FIELD_NAME],
        FIELD_CITY:             row[FIELD_CITY],
        FIELD_STATE:            row[FIELD_STATE],
        FIELD_BUSINESS_STARS:   float(row[FIELD_BUSINESS_STARS]),
        FIELD_CATEGORIES:       row[FIELD_CATEGORIES],
        FIELD_REVIEW_ID:        row[FIELD_REVIEW_ID],
        FIELD_REVIEW_STARS:     int(row[FIELD_REVIEW_STARS]),
        FIELD_REVIEW_TEXT:      row[FIELD_REVIEW_TEXT],
        FIELD_REVIEW_DATE:      row[FIELD_REVIEW_DATE],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")
