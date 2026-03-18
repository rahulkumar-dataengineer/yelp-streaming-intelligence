"""
Silver layer — cleaned, typed, and joined dataset from Bronze tables.
Reads Bronze business and review tables from Hive metastore as streaming
sources, applies type casting / cleaning / dict parsing, performs a
stream-stream inner join on business_id, and writes to the Silver
managed table partitioned by state and ingestion_date.
"""

import ast

from pyspark.sql import Column, DataFrame, SparkSession
from pyspark.sql.functions import (
    col,
    greatest,
    lit,
    to_date,
    udf,
    when,
)
from pyspark.sql.types import (
    BooleanType,
    FloatType,
    IntegerType,
    MapType,
    StringType,
    TimestampType,
)

from config.settings import settings
from processing.schemas import BUSINESS_TABLE, REVIEW_TABLE, SILVER_TABLE, Silver
from platform_commons.logger import Logger
from platform_commons.kafka import register_signal_handlers
from utils.spark_helpers import (
    create_spark_session,
    read_table_stream,
    run_until_shutdown,
    start_table_sink,
)

log = Logger.get(__name__)


BRONZE_DB: str = settings.hive.BRONZE_DB
SILVER_DB: str = settings.hive.SILVER_DB
SILVER_CHECKPOINT: str = settings.spark.SILVER_CHECKPOINT

WATERMARK_DELAY: str = "24 hours"
MAX_FILES_PER_TRIGGER: int = 5


# -----------------------
# Cleaning Functions
# -----------------------
@udf(returnType=MapType(StringType(), BooleanType()))
def _parse_bool_dict(
    dict_str: str,
    business_id: str,
    field_name: str
) -> dict | None:
    """
    Parses a Python dict string into {str: bool}.
    attributes_BusinessParking and attributes_Music are dictionaries but within string.
    """
    if dict_str is None or dict_str == "None":
        return None
    try:
        parsed = ast.literal_eval(dict_str)
        if not isinstance(parsed, dict):
            return None
        return {str(k): v for k, v in parsed.items() if isinstance(v, bool)}
    except Exception:
        log.warning(f"Failed to parse {field_name} for business_id={business_id}")
        return None


@udf(returnType=StringType())
def _parse_string_literal(
    value: str,
    business_id: str,
    field_name: str
) -> str | None:
    """Strips Python string literal wrappers: u'none' → none, 'full_bar' → full_bar."""
    if value is None:
        return None
    try:
        result = ast.literal_eval(value)
        return str(result) if result is not None else None
    except Exception:
        log.warning(f"Failed to parse {field_name} for business_id={business_id}")
        return None


def _clean_boolean(col_name: str) -> Column:
    """Maps string 'True'/'False'/'None' to BooleanType."""
    c = col(col_name)
    return (
        when(c == "True", lit(True))
        .when(c == "False", lit(False))
        .otherwise(lit(None).cast(BooleanType()))
    )


def _clean_hours(col_name: str) -> Column:
    """Replaces '0:0-0:0' (closed) with null, keeps valid hours."""
    c = col(col_name)
    return when(c == "0:0-0:0", lit(None).cast(StringType())).otherwise(c)



# ----------------------------------
# Bronze → Silver Column Mappings
# ----------------------------------

_BOOLEAN_ATTR_MAP: list[tuple[str, str]] = [
    ("attributes_BikeParking", Silver.BIKE_PARKING),
    ("attributes_BusinessAcceptsBitcoin", Silver.BUSINESS_ACCEPTS_BITCOIN),
    ("attributes_BusinessAcceptsCreditCards", Silver.BUSINESS_ACCEPTS_CREDIT_CARDS),
    ("attributes_ByAppointmentOnly", Silver.BY_APPOINTMENT_ONLY),
    ("attributes_BYOB", Silver.BYOB),
    ("attributes_Caters", Silver.CATERS),
    ("attributes_DogsAllowed", Silver.DOGS_ALLOWED),
    ("attributes_DriveThru", Silver.DRIVE_THRU),
    ("attributes_GoodForDancing", Silver.GOOD_FOR_DANCING),
    ("attributes_GoodForKids", Silver.GOOD_FOR_KIDS),
    ("attributes_HappyHour", Silver.HAPPY_HOUR),
    ("attributes_HasTV", Silver.HAS_TV),
    ("attributes_Open24Hours", Silver.OPEN_24_HOURS),
    ("attributes_OutdoorSeating", Silver.OUTDOOR_SEATING),
    ("attributes_RestaurantsDelivery", Silver.RESTAURANTS_DELIVERY),
    ("attributes_RestaurantsGoodForGroups", Silver.RESTAURANTS_GOOD_FOR_GROUPS),
    ("attributes_RestaurantsReservations", Silver.RESTAURANTS_RESERVATIONS),
    ("attributes_RestaurantsTableService", Silver.RESTAURANTS_TABLE_SERVICE),
    ("attributes_RestaurantsTakeOut", Silver.RESTAURANTS_TAKE_OUT),
    ("attributes_WheelchairAccessible", Silver.WHEELCHAIR_ACCESSIBLE),
]

_PARKING_KEY_MAP: list[tuple[str, str]] = [
    ("garage", Silver.PARKING_GARAGE),
    ("street", Silver.PARKING_STREET),
    ("validated", Silver.PARKING_VALIDATED),
    ("lot", Silver.PARKING_LOT),
    ("valet", Silver.PARKING_VALET),
]

_MUSIC_KEY_MAP: list[tuple[str, str]] = [
    ("dj", Silver.MUSIC_DJ),
    ("background_music", Silver.MUSIC_BACKGROUND),
    ("no_music", Silver.MUSIC_NO_MUSIC),
    ("jukebox", Silver.MUSIC_JUKEBOX),
    ("live", Silver.MUSIC_LIVE),
    ("video", Silver.MUSIC_VIDEO),
    ("karaoke", Silver.MUSIC_KARAOKE),
]

_STRING_ATTR_MAP: list[tuple[str, str]] = [
    ("attributes_Alcohol", Silver.ALCOHOL),
    ("attributes_NoiseLevel", Silver.NOISE_LEVEL),
    ("attributes_RestaurantsAttire", Silver.RESTAURANTS_ATTIRE),
    ("attributes_Smoking", Silver.SMOKING),
    ("attributes_WiFi", Silver.WIFI),
]

_HOURS_MAP: list[tuple[str, str]] = [
    ("hours_Monday", Silver.HOURS_MONDAY),
    ("hours_Tuesday", Silver.HOURS_TUESDAY),
    ("hours_Wednesday", Silver.HOURS_WEDNESDAY),
    ("hours_Thursday", Silver.HOURS_THURSDAY),
    ("hours_Friday", Silver.HOURS_FRIDAY),
    ("hours_Saturday", Silver.HOURS_SATURDAY),
    ("hours_Sunday", Silver.HOURS_SUNDAY),
]


# ------------------------
# Stream builders
# ------------------------

def _build_business_stream(spark: SparkSession) -> DataFrame:
    """Reads Bronze business table from metastore and applies all cleaning transforms."""

    df: DataFrame = read_table_stream(
        spark,
        f"{BRONZE_DB}.{BUSINESS_TABLE}",
        MAX_FILES_PER_TRIGGER,
    )

    # Cast ingestion_timestamp for watermarking
    df = df.withColumn("ingestion_timestamp", col("ingestion_timestamp").cast(TimestampType()))


    df = df.withColumn(Silver.BUSINESS_STARS, col("stars").cast(FloatType()))
    df = df.withColumn("review_count", col("review_count").cast(IntegerType()))
    df = df.withColumn(
        "is_open",
        when(col("is_open") == "1", lit(True))
        .when(col("is_open") == "0", lit(False))
        .otherwise(lit(None).cast(BooleanType())),
    )

    # Boolean attributes
    for bronze_col, silver_col in _BOOLEAN_ATTR_MAP:
        df = df.withColumn(silver_col, _clean_boolean(bronze_col))

    # BusinessParking
    df = df.withColumn(
        "_parking",
        _parse_bool_dict(
            col("attributes_BusinessParking"),
            col("business_id"),
            lit("attributes_BusinessParking"),
        ),
    )
    for dict_key, silver_col in _PARKING_KEY_MAP:
        df = df.withColumn(silver_col, col("_parking")[dict_key])
    df = df.drop("_parking")

    #  Music - 7 booleans 
    df = df.withColumn(
        "_music",
        _parse_bool_dict(
            col("attributes_Music"),
            col("business_id"),
            lit("attributes_Music"),
        ),
    )
    for dict_key, silver_col in _MUSIC_KEY_MAP:
        df = df.withColumn(silver_col, col("_music")[dict_key])
    df = df.drop("_music")

    #  String attributes (5) 
    for bronze_col, silver_col in _STRING_ATTR_MAP:
        df = df.withColumn(
            silver_col,
            _parse_string_literal(col(bronze_col), col("business_id"), lit(bronze_col)),
        )

    #  RestaurantsPriceRange2 → IntegerType 
    df = df.withColumn(
        Silver.RESTAURANTS_PRICE_RANGE,
        when(col("attributes_RestaurantsPriceRange2") == "None", lit(None).cast(IntegerType()))
        .otherwise(col("attributes_RestaurantsPriceRange2").cast(IntegerType())),
    )

    #  Hours (7) — replace "0:0-0:0" with null 
    for bronze_col, silver_col in _HOURS_MAP:
        df = df.withColumn(silver_col, _clean_hours(bronze_col))

    # Select only the columns Silver needs from business side
    biz_columns = [
        col("business_id"),
        col("name"),
        col("address"),
        col("city"),
        col("state"),
        col("postal_code"),
        col(Silver.BUSINESS_STARS),
        col("review_count"),
        col("is_open"),
        col("categories"),
        
        # 20 boolean attrs
        *[col(silver_col) for _, silver_col in _BOOLEAN_ATTR_MAP],
        
        # 5 parking
        *[col(silver_col) for _, silver_col in _PARKING_KEY_MAP],
        
        # 7 music
        *[col(silver_col) for _, silver_col in _MUSIC_KEY_MAP],
        
        # 5 string attrs + 1 integer attr
        *[col(silver_col) for _, silver_col in _STRING_ATTR_MAP],
        
        col(Silver.RESTAURANTS_PRICE_RANGE),
        
        # 7 hours
        *[col(silver_col) for _, silver_col in _HOURS_MAP],
        
        # metadata
        col("ingestion_timestamp"),
    ]

    df = df.select(*biz_columns)
    log.info(f"Business stream built: {len(df.columns)} columns")
    return df


def _build_review_stream(spark: SparkSession) -> DataFrame:
    """Reads Bronze review table from metastore and applies type casts."""

    df: DataFrame = read_table_stream(
        spark,
        f"{BRONZE_DB}.{REVIEW_TABLE}",
        MAX_FILES_PER_TRIGGER,
    )

    # Cast ingestion_timestamp for watermarking
    df = df.withColumn("ingestion_timestamp", col("ingestion_timestamp").cast(TimestampType()))

    # Type casts
    df = df.withColumn(Silver.REVIEW_STARS, col("stars").cast(IntegerType()))
    df = df.withColumn("useful", col("useful").cast(IntegerType()))
    df = df.withColumn("funny", col("funny").cast(IntegerType()))
    df = df.withColumn("cool", col("cool").cast(IntegerType()))
    df = df.withColumn("date", col("date").cast(TimestampType()))

    rev_columns = [
        col("business_id"),
        col("review_id"),
        col("user_id"),
        col(Silver.REVIEW_STARS),
        col("useful"),
        col("funny"),
        col("cool"),
        col("text"),
        col("date"),
        col("ingestion_timestamp"),
    ]

    df = df.select(*rev_columns)
    log.info(f"Review stream built: {len(df.columns)} columns")
    return df


# ------------------------
# Main
# ------------------------

def main() -> None:
    """Joins business and review streams, writes cleaned Silver table."""

    register_signal_handlers()
    log.info("Silver layer starting up...")

    spark: SparkSession = create_spark_session("YelpSilver")
    # Allow multiple stateful operators (watermark + dropDuplicatesWithinWatermark after join)
    spark.conf.set("spark.sql.streaming.statefulOperator.allowMultiple", "true")

    try:
        biz_df = _build_business_stream(spark)
        rev_df = _build_review_stream(spark)

        # Watermark both streams for state management
        biz_wm = biz_df.withWatermark("ingestion_timestamp", WATERMARK_DELAY)
        rev_wm = rev_df.withWatermark("ingestion_timestamp", WATERMARK_DELAY)

        # Stream-stream inner join on business_id
        joined: DataFrame = (
            biz_wm.alias("biz")
            .join(
                rev_wm.alias("rev"),
                col("biz.business_id") == col("rev.business_id"),
                "inner",
            )
        )

        # Resolve column conflicts and build Silver output
        silver_df: DataFrame = joined.select(
            
            # Business fields
            col("biz.business_id").alias("business_id"),
            col("biz.name"),
            col("biz.address"),
            col("biz.city"),
            col("biz.state"),
            col("biz.postal_code"),
            col(f"biz.{Silver.BUSINESS_STARS}"),
            col("biz.review_count"),
            col("biz.is_open"),
            col("biz.categories"),
            
            # 20 boolean attrs
            *[col(f"biz.{silver_col}") for _, silver_col in _BOOLEAN_ATTR_MAP],
            
            # 5 parking
            *[col(f"biz.{silver_col}") for _, silver_col in _PARKING_KEY_MAP],
            
            # 7 music
            *[col(f"biz.{silver_col}") for _, silver_col in _MUSIC_KEY_MAP],
            
            # 5 string attrs + 1 integer attr
            *[col(f"biz.{silver_col}") for _, silver_col in _STRING_ATTR_MAP],
            col(f"biz.{Silver.RESTAURANTS_PRICE_RANGE}"),
            
            # 7 hours
            *[col(f"biz.{silver_col}") for _, silver_col in _HOURS_MAP],
            
            # Review fields
            col("rev.review_id"),
            col("rev.user_id"),
            col(f"rev.{Silver.REVIEW_STARS}"),
            col("rev.useful"),
            col("rev.funny"),
            col("rev.cool"),
            col("rev.text"),
            col("rev.date"),
            
            # Metadata: take the later timestamp from both sides
            greatest(col("biz.ingestion_timestamp"), col("rev.ingestion_timestamp")).alias("ingestion_timestamp"),
            to_date(
                greatest(col("biz.ingestion_timestamp"), col("rev.ingestion_timestamp"))
            ).alias("ingestion_date"),
        )

        # Dedup within the watermark window — bounded state, no unbounded growth.
        # Cross-run duplicates (checkpoint reset) are handled by Gold's dedup VIEW.
        silver_df = silver_df.dropDuplicatesWithinWatermark(["review_id"])

        log.info(f"Silver DataFrame columns: {len(silver_df.columns)}")

        silver_table = f"{SILVER_DB}.{SILVER_TABLE}"
        query = start_table_sink(
            df=silver_df,
            query_name="silver_joined",
            table_name=silver_table,
            checkpoint_path=SILVER_CHECKPOINT,
            partition_cols=["state", "ingestion_date"],
        )

        run_until_shutdown([query])

    except Exception as exc:
        log.error(f"Silver layer failed: {exc}")
        raise

    finally:
        log.info("Stopping Silver streaming query...")
        for q in spark.streams.active:
            log.info(f"Stopping query: {q.name}")
            q.stop()
        spark.stop()
        log.info("Silver layer shut down cleanly.")


if __name__ == "__main__":
    main()
