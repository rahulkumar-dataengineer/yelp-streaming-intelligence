"""
Processing layer schemas
"""

import json

from schemas import BUSINESS_AVRO_SCHEMA, REVIEW_AVRO_SCHEMA


# ------------------------
# Bronze — Avro JSON strings
# ------------------------

BUSINESS_AVRO_JSON: str = json.dumps(BUSINESS_AVRO_SCHEMA)
REVIEW_AVRO_JSON: str = json.dumps(REVIEW_AVRO_SCHEMA)

BUSINESS_TABLE: str = "businesses"
REVIEW_TABLE: str = "reviews"
SILVER_TABLE: str = "reviews"


# ------------------------
# Silver — cleaned/renamed field names
# ------------------------

class Silver:
    """Field name constants for the Silver joined table."""

    # Renamed fields (avoid collision between business.stars and review.stars)
    BUSINESS_STARS: str = "business_stars"
    REVIEW_STARS: str = "review_stars"

    # Boolean attributes (20)
    BIKE_PARKING: str = "bike_parking"
    BUSINESS_ACCEPTS_BITCOIN: str = "business_accepts_bitcoin"
    BUSINESS_ACCEPTS_CREDIT_CARDS: str = "business_accepts_credit_cards"
    BY_APPOINTMENT_ONLY: str = "by_appointment_only"
    BYOB: str = "byob"
    CATERS: str = "caters"
    DOGS_ALLOWED: str = "dogs_allowed"
    DRIVE_THRU: str = "drive_thru"
    GOOD_FOR_DANCING: str = "good_for_dancing"
    GOOD_FOR_KIDS: str = "good_for_kids"
    HAPPY_HOUR: str = "happy_hour"
    HAS_TV: str = "has_tv"
    OPEN_24_HOURS: str = "open_24_hours"
    OUTDOOR_SEATING: str = "outdoor_seating"
    RESTAURANTS_DELIVERY: str = "restaurants_delivery"
    RESTAURANTS_GOOD_FOR_GROUPS: str = "restaurants_good_for_groups"
    RESTAURANTS_RESERVATIONS: str = "restaurants_reservations"
    RESTAURANTS_TABLE_SERVICE: str = "restaurants_table_service"
    RESTAURANTS_TAKE_OUT: str = "restaurants_take_out"
    WHEELCHAIR_ACCESSIBLE: str = "wheelchair_accessible"

    # attributes_BusinessParking — boolean
    PARKING_GARAGE: str = "parking_garage"
    PARKING_STREET: str = "parking_street"
    PARKING_VALIDATED: str = "parking_validated"
    PARKING_LOT: str = "parking_lot"
    PARKING_VALET: str = "parking_valet"

    # attributes_Music — boolean
    MUSIC_DJ: str = "music_dj"
    MUSIC_BACKGROUND: str = "music_background"
    MUSIC_NO_MUSIC: str = "music_no_music"
    MUSIC_JUKEBOX: str = "music_jukebox"
    MUSIC_LIVE: str = "music_live"
    MUSIC_VIDEO: str = "music_video"
    MUSIC_KARAOKE: str = "music_karaoke"

    # String attributes
    ALCOHOL: str = "alcohol"
    NOISE_LEVEL: str = "noise_level"
    RESTAURANTS_ATTIRE: str = "restaurants_attire"
    SMOKING: str = "smoking"
    WIFI: str = "wifi"

    # Integer attribute
    RESTAURANTS_PRICE_RANGE: str = "restaurants_price_range"

    # Hours
    HOURS_MONDAY: str = "hours_monday"
    HOURS_TUESDAY: str = "hours_tuesday"
    HOURS_WEDNESDAY: str = "hours_wednesday"
    HOURS_THURSDAY: str = "hours_thursday"
    HOURS_FRIDAY: str = "hours_friday"
    HOURS_SATURDAY: str = "hours_saturday"
    HOURS_SUNDAY: str = "hours_sunday"


# ------------------------
# Gold — sink field selections
# ------------------------

class Gold:
    """Field selections for BigQuery (SQL analytics) and Qdrant (vector search)."""

    BIGQUERY_SELECT: list[str] = ["*"]

    QDRANT_FIELDS: dict = {
        "embedding_text_fields": [
            "name",
            "categories",
            "text",
        ],
        "payload_fields": [
            # Identity
            "review_id",
            "business_id",

            # Business context
            "name",
            "city",
            "state",
            "categories",

            # Quality signals
            Silver.BUSINESS_STARS,
            Silver.REVIEW_STARS,
            "review_count",
            "is_open",

            # Vibe/ambiance attributes
            Silver.ALCOHOL,
            Silver.NOISE_LEVEL,
            Silver.WIFI,
            Silver.OUTDOOR_SEATING,
            Silver.RESTAURANTS_PRICE_RANGE,

            # Review content
            "text",
            "date",
        ],
    }
