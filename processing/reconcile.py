"""
Data quality reconciliation — identifies Bronze reviews that did not match
any business during the Silver stream-stream join and writes them to
silver.quarantine.

Enterprise pattern: run after the streaming pipeline catches up (Silver shows
rows=0) to capture unmatched rows that the inner join dropped. In production
this would be scheduled by Airflow/Dagster on a cadence or SLA trigger.

Usage:
    python -m processing.reconcile
"""

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, lit, to_date

from config.settings import settings
from processing.schemas import QUARANTINE_TABLE, REVIEW_TABLE, SILVER_TABLE
from platform_commons.logger import Logger
from utils.spark_helpers import create_spark_session

log = Logger.get(__name__)


BRONZE_DB: str = settings.hive.BRONZE_DB
SILVER_DB: str = settings.hive.SILVER_DB


def main() -> None:
    """Anti-join Bronze reviews against Silver reviews, write unmatched to quarantine."""

    log.info("Reconciliation starting...")
    spark: SparkSession = create_spark_session("YelpReconcile")

    try:
        bronze_reviews = f"{BRONZE_DB}.{REVIEW_TABLE}"
        silver_reviews = f"{SILVER_DB}.{SILVER_TABLE}"
        quarantine_table = f"{SILVER_DB}.{QUARANTINE_TABLE}"

        # Count current state
        bronze_count = spark.table(bronze_reviews).count()
        silver_count = spark.table(silver_reviews).count()
        quarantine_before = spark.table(quarantine_table).count()

        log.info(
            f"Current counts: bronze.reviews={bronze_count:,} | "
            f"silver.reviews={silver_count:,} | "
            f"silver.quarantine={quarantine_before:,}"
        )

        if bronze_count == 0:
            log.info("No Bronze reviews — nothing to reconcile.")
            return

        # Anti-join: Bronze reviews NOT IN Silver reviews
        bronze_df = spark.table(bronze_reviews)
        silver_ids = spark.table(silver_reviews).select("review_id").distinct()

        unmatched = (
            bronze_df.alias("b")
            .join(silver_ids.alias("s"), col("b.review_id") == col("s.review_id"), "left_anti")
        )

        unmatched_count = unmatched.count()
        log.info(f"Unmatched reviews found: {unmatched_count:,}")

        if unmatched_count == 0:
            log.info("All Bronze reviews matched — quarantine is clean.")
            return

        # Build quarantine DataFrame: raw Bronze columns + reason + metadata
        quarantine_df = unmatched.select(
            col("review_id"),
            col("user_id"),
            col("business_id"),
            col("stars"),
            col("useful"),
            col("funny"),
            col("cool"),
            col("text"),
            col("date"),
            lit("unmatched_business_id").alias("reason"),
            current_timestamp().alias("quarantine_timestamp"),
            to_date(col("ingestion_timestamp")).cast("string").alias("ingestion_date"),
        )

        # Write to quarantine table (positional match — columns in DDL order,
        # partition column ingestion_date last)
        quarantine_df.write.mode("append").insertInto(quarantine_table)

        quarantine_after = spark.table(quarantine_table).count()
        log.info(
            f"Reconciliation complete: {unmatched_count:,} reviews → {quarantine_table} | "
            f"quarantine total: {quarantine_after:,}"
        )

    except Exception as exc:
        log.error(f"Reconciliation failed: {exc}")
        raise

    finally:
        spark.stop()
        log.info("Reconciliation shut down.")


if __name__ == "__main__":
    main()
