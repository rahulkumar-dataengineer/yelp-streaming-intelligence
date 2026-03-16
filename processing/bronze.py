"""
Bronze layer — raw persistence of Kafka messages as Parquet.
Reads from two Redpanda topics (yelp_businesses, yelp_reviews),
deserializes Avro payloads (Confluent wire format), and writes to
Hive-managed Bronze tables partitioned by ingestion_date.
"""

from pyspark.sql import DataFrame
from pyspark.sql.avro.functions import from_avro
from pyspark.sql.functions import (
    current_timestamp,
    expr,
    to_date,
)
from pyspark.sql.streaming import StreamingQuery

from config.settings import settings
from processing.schemas import BUSINESS_AVRO_JSON, BUSINESS_TABLE, REVIEW_AVRO_JSON, REVIEW_TABLE
from platform_commons.logger import Logger
from platform_commons.kafka import register_signal_handlers
from utils.spark_helpers import (
    create_spark_session,
    run_until_shutdown,
    start_table_sink,
)

log = Logger.get(__name__)


MAX_OFFSETS_PER_TRIGGER: int = 10_000
STARTING_OFFSETS: str = "earliest"

# Confluent wire format: 1 magic byte + 4-byte schema ID = 5 bytes prefix
_WIRE_FORMAT_HEADER_SIZE: int = 5


def _build_kafka_stream(
    spark,
    topic: str,
    avro_schema_json: str,
) -> DataFrame:
    """Reads a Kafka topic, deserializes Avro (stripping Confluent wire format
    header), and enriches with metadata."""

    raw_df: DataFrame = (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", settings.kafka.BOOTSTRAP_SERVERS)
        .option("subscribe", topic)
        .option("startingOffsets", STARTING_OFFSETS)
        .option("maxOffsetsPerTrigger", MAX_OFFSETS_PER_TRIGGER)
        .option("failOnDataLoss", "false")
        .load()
    )

    # Strip 5-byte Confluent wire format header, then deserialize Avro payload
    # substring(value, 6) = bytes from position 6 onward (1-indexed, skips 5-byte header)
    parsed_df: DataFrame = (
        raw_df
        .select(
            from_avro(
                expr(f"substring(value, {_WIRE_FORMAT_HEADER_SIZE + 1})"),
                avro_schema_json,
            ).alias("parsed")
        )
        .select("parsed.*")
    )

    # Add metadata with Spark processing timestamp
    enriched_df: DataFrame = (
        parsed_df
        .withColumn("ingestion_timestamp", current_timestamp().cast("string"))
        .withColumn("ingestion_date", to_date(current_timestamp()).cast("string"))
    )

    log.info(f"Kafka stream built: topic={topic}")
    return enriched_df


def main() -> None:
    """Starts Bronze streaming queries for businesses and reviews."""

    register_signal_handlers()
    log.info("Bronze layer starting up...")

    spark = create_spark_session(
        "YelpBronze",
        extra_packages=[settings.spark.KAFKA_PACKAGE, settings.spark.AVRO_PACKAGE],
    )

    try:
        biz_table = f"{settings.hive.BRONZE_DB}.{BUSINESS_TABLE}"
        rev_table = f"{settings.hive.BRONZE_DB}.{REVIEW_TABLE}"

        biz_df = _build_kafka_stream(spark, settings.kafka.BUSINESS_TOPIC, BUSINESS_AVRO_JSON)
        rev_df = _build_kafka_stream(spark, settings.kafka.REVIEW_TOPIC, REVIEW_AVRO_JSON)

        business_query: StreamingQuery = start_table_sink(
            df=biz_df,
            query_name="bronze_businesses",
            table_name=biz_table,
            checkpoint_path=settings.spark.BRONZE_BUSINESS_CHECKPOINT,
            partition_cols=["ingestion_date"],
        )

        review_query: StreamingQuery = start_table_sink(
            df=rev_df,
            query_name="bronze_reviews",
            table_name=rev_table,
            checkpoint_path=settings.spark.BRONZE_REVIEW_CHECKPOINT,
            partition_cols=["ingestion_date"],
        )

        run_until_shutdown([business_query, review_query])

    except Exception as exc:
        log.error(f"Bronze layer failed: {exc}")
        raise

    finally:
        log.info("Stopping Bronze streaming queries...")
        for q in spark.streams.active:
            log.info(f"Stopping query: {q.name}")
            q.stop()
        spark.stop()
        log.info("Bronze layer shut down cleanly.")


if __name__ == "__main__":
    main()
