"""
schema-as-contract pattern — Single Source of Truth
- Every Spark schema used by Bronze, Silver, and Gold layers is defined here.

Structure:
  - BronzeBusiness, BronzeReview: raw field names per entity, all StringType.
  - Silver: cleaned and renamed field.
  - Gold: sink-specific field selections for BigQuery and Qdrant.

Scales by adding new entity classes (BronzeCheckin, BronzeTip, etc.)
without touching existing ones.
"""

from pyspark.sql.types import (
    BooleanType,
    DateType,
    FloatType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)


# -------------
# BRONZE LAYER 
# -------------

class BronzeBusiness:

    BUSINESS_ID = "business_id"
    NAME = "name"
    ADDRESS = "address"
    CITY = "city"
    STATE = "state"
    POSTAL_CODE = "postal_code"
    LATITUDE = "latitude"
    LONGITUDE = "longitude"
    STARS = "stars"
    REVIEW_COUNT = "review_count"
    IS_OPEN = "is_open"
    CATEGORIES = "categories"

    INGESTION_TIMESTAMP = "ingestion_timestamp"
    INGESTION_DATE = "ingestion_date"

    ATTRIBUTE_KEYS = [
        "AcceptsInsurance",
        "Alcohol",
        "Ambience",
        "BYOB",
        "BYOBCorkage",
        "BestNights",
        "BikeParking",
        "BusinessAcceptsBitcoin",
        "BusinessAcceptsCreditCards",
        "BusinessParking",
        "ByAppointmentOnly",
        "Caters",
        "CoatCheck",
        "Corkage",
        "DogsAllowed",
        "DriveThru",
        "GoodForDancing",
        "GoodForKids",
        "GoodForMeal",
        "HairSpecializesIn",
        "HappyHour",
        "HasTV",
        "Music",
        "NoiseLevel",
        "Open24Hours",
        "OutdoorSeating",
        "RestaurantsAttire",
        "RestaurantsCounterService",
        "RestaurantsDelivery",
        "RestaurantsGoodForGroups",
        "RestaurantsPriceRange2",
        "RestaurantsReservations",
        "RestaurantsTableService",
        "RestaurantsTakeOut",
        "Smoking",
        "WheelchairAccessible",
        "WiFi",
    ]

    HOURS_KEYS = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]


BronzeBusiness.SCHEMA = StructType(
    [
        StructField(BronzeBusiness.BUSINESS_ID, StringType(), True),
        StructField(BronzeBusiness.NAME, StringType(), True),
        StructField(BronzeBusiness.ADDRESS, StringType(), True),
        StructField(BronzeBusiness.CITY, StringType(), True),
        StructField(BronzeBusiness.STATE, StringType(), True),
        StructField(BronzeBusiness.POSTAL_CODE, StringType(), True),
        StructField(BronzeBusiness.LATITUDE, StringType(), True),
        StructField(BronzeBusiness.LONGITUDE, StringType(), True),
        StructField(BronzeBusiness.STARS, StringType(), True),
        StructField(BronzeBusiness.REVIEW_COUNT, StringType(), True),
        StructField(BronzeBusiness.IS_OPEN, StringType(), True),
        StructField(BronzeBusiness.CATEGORIES, StringType(), True),
    ]
    + [
        StructField(f"attributes.{attr}", StringType(), True)
        for attr in BronzeBusiness.ATTRIBUTE_KEYS
    ]
    + [
        StructField(f"hours.{day}", StringType(), True)
        for day in BronzeBusiness.HOURS_KEYS
    ]
    + [
        StructField(BronzeBusiness.INGESTION_TIMESTAMP, StringType(), True),
        StructField(BronzeBusiness.INGESTION_DATE, StringType(), True),
    ]
)


class BronzeReview:

    REVIEW_ID = "review_id"
    USER_ID = "user_id"
    BUSINESS_ID = "business_id"
    STARS = "stars"
    USEFUL = "useful"
    FUNNY = "funny"
    COOL = "cool"
    TEXT = "text"
    DATE = "date"

    INGESTION_TIMESTAMP = "ingestion_timestamp"
    INGESTION_DATE = "ingestion_date"


BronzeReview.SCHEMA = StructType([
    StructField(BronzeReview.REVIEW_ID, StringType(), True),
    StructField(BronzeReview.USER_ID, StringType(), True),
    StructField(BronzeReview.BUSINESS_ID, StringType(), True),
    StructField(BronzeReview.STARS, StringType(), True),
    StructField(BronzeReview.USEFUL, StringType(), True),
    StructField(BronzeReview.FUNNY, StringType(), True),
    StructField(BronzeReview.COOL, StringType(), True),
    StructField(BronzeReview.TEXT, StringType(), True),
    StructField(BronzeReview.DATE, StringType(), True),
    StructField(BronzeReview.INGESTION_TIMESTAMP, StringType(), True),
    StructField(BronzeReview.INGESTION_DATE, StringType(), True),
])


# -----------------------
# SILVER LAYER — Cleaned
# -----------------------
class Silver:
    
    # Renamed fields
    BUSINESS_STARS = "business_stars"
    REVIEW_STARS = "review_stars"

    # Boolean attributes
    BIKE_PARKING = "bike_parking"
    BUSINESS_ACCEPTS_BITCOIN = "business_accepts_bitcoin"
    BUSINESS_ACCEPTS_CREDIT_CARDS = "business_accepts_credit_cards"
    BY_APPOINTMENT_ONLY = "by_appointment_only"
    BYOB = "byob"
    CATERS = "caters"
    DOGS_ALLOWED = "dogs_allowed"
    DRIVE_THRU = "drive_thru"
    GOOD_FOR_DANCING = "good_for_dancing"
    GOOD_FOR_KIDS = "good_for_kids"
    HAPPY_HOUR = "happy_hour"
    HAS_TV = "has_tv"
    OPEN_24_HOURS = "open_24_hours"
    OUTDOOR_SEATING = "outdoor_seating"
    RESTAURANTS_DELIVERY = "restaurants_delivery"
    RESTAURANTS_GOOD_FOR_GROUPS = "restaurants_good_for_groups"
    RESTAURANTS_RESERVATIONS = "restaurants_reservations"
    RESTAURANTS_TABLE_SERVICE = "restaurants_table_service"
    RESTAURANTS_TAKE_OUT = "restaurants_take_out"
    WHEELCHAIR_ACCESSIBLE = "wheelchair_accessible"

    # attributes.BusinessParking - boolean
    PARKING_GARAGE = "parking_garage"
    PARKING_STREET = "parking_street"
    PARKING_VALIDATED = "parking_validated"
    PARKING_LOT = "parking_lot"
    PARKING_VALET = "parking_valet"

    # attributes.Music - boolean
    MUSIC_DJ = "music_dj"
    MUSIC_BACKGROUND = "music_background"
    MUSIC_NO_MUSIC = "music_no_music"
    MUSIC_JUKEBOX = "music_jukebox"
    MUSIC_LIVE = "music_live"
    MUSIC_VIDEO = "music_video"
    MUSIC_KARAOKE = "music_karaoke"

    # String attributes
    ALCOHOL = "alcohol"                         
    NOISE_LEVEL = "noise_level"                 
    RESTAURANTS_ATTIRE = "restaurants_attire"   
    SMOKING = "smoking"                         
    WIFI = "wifi"                               

    # Integer attribute
    RESTAURANTS_PRICE_RANGE = "restaurants_price_range"
    
    # Hours
    HOURS_MONDAY = "hours_monday"
    HOURS_TUESDAY = "hours_tuesday"
    HOURS_WEDNESDAY = "hours_wednesday"
    HOURS_THURSDAY = "hours_thursday"
    HOURS_FRIDAY = "hours_friday"
    HOURS_SATURDAY = "hours_saturday"
    HOURS_SUNDAY = "hours_sunday"

    # Metadata
    INGESTION_TIMESTAMP = "ingestion_timestamp"
    INGESTION_DATE = "ingestion_date"


Silver.SCHEMA = StructType([
    # Business fields
    StructField(BronzeBusiness.BUSINESS_ID, StringType(), False),
    StructField(BronzeBusiness.NAME, StringType(), True),
    StructField(BronzeBusiness.ADDRESS, StringType(), True),
    StructField(BronzeBusiness.CITY, StringType(), True),
    StructField(BronzeBusiness.STATE, StringType(), True),
    StructField(BronzeBusiness.POSTAL_CODE, StringType(), True),
    StructField(Silver.BUSINESS_STARS, FloatType(), True),          
    StructField(BronzeBusiness.REVIEW_COUNT, IntegerType(), True),
    StructField(BronzeBusiness.IS_OPEN, BooleanType(), True),
    StructField(BronzeBusiness.CATEGORIES, StringType(), True),

    # Boolean attributes
    StructField(Silver.BIKE_PARKING, BooleanType(), True),
    StructField(Silver.BUSINESS_ACCEPTS_BITCOIN, BooleanType(), True),
    StructField(Silver.BUSINESS_ACCEPTS_CREDIT_CARDS, BooleanType(), True),
    StructField(Silver.BY_APPOINTMENT_ONLY, BooleanType(), True),
    StructField(Silver.BYOB, BooleanType(), True),
    StructField(Silver.CATERS, BooleanType(), True),
    StructField(Silver.DOGS_ALLOWED, BooleanType(), True),
    StructField(Silver.DRIVE_THRU, BooleanType(), True),
    StructField(Silver.GOOD_FOR_DANCING, BooleanType(), True),
    StructField(Silver.GOOD_FOR_KIDS, BooleanType(), True),
    StructField(Silver.HAPPY_HOUR, BooleanType(), True),
    StructField(Silver.HAS_TV, BooleanType(), True),
    StructField(Silver.OPEN_24_HOURS, BooleanType(), True),
    StructField(Silver.OUTDOOR_SEATING, BooleanType(), True),
    StructField(Silver.RESTAURANTS_DELIVERY, BooleanType(), True),
    StructField(Silver.RESTAURANTS_GOOD_FOR_GROUPS, BooleanType(), True),
    StructField(Silver.RESTAURANTS_RESERVATIONS, BooleanType(), True),
    StructField(Silver.RESTAURANTS_TABLE_SERVICE, BooleanType(), True),
    StructField(Silver.RESTAURANTS_TAKE_OUT, BooleanType(), True),
    StructField(Silver.WHEELCHAIR_ACCESSIBLE, BooleanType(), True),

    # parking booleans 
    StructField(Silver.PARKING_GARAGE, BooleanType(), True),
    StructField(Silver.PARKING_STREET, BooleanType(), True),
    StructField(Silver.PARKING_VALIDATED, BooleanType(), True),
    StructField(Silver.PARKING_LOT, BooleanType(), True),
    StructField(Silver.PARKING_VALET, BooleanType(), True),

    # music booleans 
    StructField(Silver.MUSIC_DJ, BooleanType(), True),
    StructField(Silver.MUSIC_BACKGROUND, BooleanType(), True),
    StructField(Silver.MUSIC_NO_MUSIC, BooleanType(), True),
    StructField(Silver.MUSIC_JUKEBOX, BooleanType(), True),
    StructField(Silver.MUSIC_LIVE, BooleanType(), True),
    StructField(Silver.MUSIC_VIDEO, BooleanType(), True),
    StructField(Silver.MUSIC_KARAOKE, BooleanType(), True),

    # String and integer attributes 
    StructField(Silver.ALCOHOL, StringType(), True),
    StructField(Silver.NOISE_LEVEL, StringType(), True),
    StructField(Silver.RESTAURANTS_ATTIRE, StringType(), True),
    StructField(Silver.SMOKING, StringType(), True),
    StructField(Silver.WIFI, StringType(), True),
    StructField(Silver.RESTAURANTS_PRICE_RANGE, IntegerType(), True),

    # Hours 
    StructField(Silver.HOURS_MONDAY, StringType(), True),
    StructField(Silver.HOURS_TUESDAY, StringType(), True),
    StructField(Silver.HOURS_WEDNESDAY, StringType(), True),
    StructField(Silver.HOURS_THURSDAY, StringType(), True),
    StructField(Silver.HOURS_FRIDAY, StringType(), True),
    StructField(Silver.HOURS_SATURDAY, StringType(), True),
    StructField(Silver.HOURS_SUNDAY, StringType(), True),

    # Review fields
    StructField(BronzeReview.REVIEW_ID, StringType(), False),
    StructField(BronzeReview.USER_ID, StringType(), True),
    StructField(Silver.REVIEW_STARS, IntegerType(), True),      
    StructField(BronzeReview.USEFUL, IntegerType(), True),
    StructField(BronzeReview.FUNNY, IntegerType(), True),
    StructField(BronzeReview.COOL, IntegerType(), True),
    StructField(BronzeReview.TEXT, StringType(), True),
    StructField(BronzeReview.DATE, TimestampType(), True),

    # Metadata
    StructField(Silver.INGESTION_TIMESTAMP, TimestampType(), True),
    StructField(Silver.INGESTION_DATE, DateType(), True),
])


# -----------------------
# GOLD LAYER — Sink-specific field selections
# -----------------------

class Gold:
    """Field selections for BigQuery (SQL analytics) and Qdrant (vector search)."""

    BIGQUERY_FIELDS = [f.name for f in Silver.SCHEMA.fields]

    QDRANT_FIELDS = {
        "embedding_text_fields": [
            BronzeBusiness.NAME,
            BronzeBusiness.CATEGORIES,
            BronzeReview.TEXT,
        ],
        "payload_fields": [
            # Identity
            BronzeReview.REVIEW_ID,
            BronzeBusiness.BUSINESS_ID,
            
            # Business context
            BronzeBusiness.NAME,
            BronzeBusiness.CITY,
            BronzeBusiness.STATE,
            BronzeBusiness.CATEGORIES,
            
            # Quality signals
            Silver.BUSINESS_STARS,
            Silver.REVIEW_STARS,
            BronzeBusiness.REVIEW_COUNT,
            BronzeBusiness.IS_OPEN,
            
            # Vibe/ambiance attributes
            Silver.ALCOHOL,
            Silver.NOISE_LEVEL,
            Silver.WIFI,
            Silver.OUTDOOR_SEATING,
            Silver.RESTAURANTS_PRICE_RANGE,
            
            # Review content
            BronzeReview.TEXT,
            BronzeReview.DATE,
        ],
    }


Gold.BIGQUERY_SCHEMA = Silver.SCHEMA
