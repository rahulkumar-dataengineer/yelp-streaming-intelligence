"""
Gold layer — BigQuery sink via foreachBatch.
Reads the Silver reviews table as a streaming file source.

Qdrant vectorization is handled separately by processing.backfill_qdrant,
which reads from BigQuery after gold finishes loading.
"""

import argparse
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.streaming import StreamingQuery

from config.settings import settings
from processing.schemas import SILVER_TABLE
from processing.sinks import bigquery as bq_sink
from platform_commons.logger import Logger
from platform_commons.kafka import register_signal_handlers
from utils.spark_helpers import (
    create_spark_session,
    read_table_stream,
    run_until_shutdown,
)

log = Logger.get(__name__)


SILVER_DB: str = settings.hive.SILVER_DB
SILVER_TABLE_FQ: str = f"{SILVER_DB}.{SILVER_TABLE}"
GOLD_CHECKPOINT: str = settings.spark.GOLD_CHECKPOINT

MAX_FILES_PER_TRIGGER: int = 5
TRIGGER_INTERVAL: str = "60 seconds"


# -------------------------
# foreachBatch callback
# -------------------------

def _make_foreach_batch_fn(
    bq_batch_sink: bq_sink.BatchSink,
) -> callable:
    """Returns a foreachBatch callback that sinks to BigQuery."""

    def _process_batch(batch_df: DataFrame, batch_id: int) -> None:
        record_count = batch_df.count()
        if record_count == 0:
            log.info(f"Batch {batch_id}: empty, skipping")
            return

        log.info(f"Batch {batch_id}: processing {record_count} rows")
        bq_batch_sink.sink_batch(batch_df, batch_id)

    return _process_batch



def main() -> None:
    """Reads Silver table and loads to BigQuery via foreachBatch."""

    parser = argparse.ArgumentParser(description="Gold layer — BigQuery sink")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete BigQuery table/view and checkpoints before starting",
    )
    args = parser.parse_args()

    register_signal_handlers()
    log.info("Gold layer starting up...")

    # --- Create sinks ---
    spark: SparkSession = create_spark_session("YelpGold")
    bq_batch_sink = bq_sink.BatchSink()

    try:
        # --- Reset (dev convenience) ---
        if args.reset:
            log.info("--reset flag: clearing BigQuery sink and checkpoints")
            bq_batch_sink.bq.reset(GOLD_CHECKPOINT)

        # --- Ensure sinks exist ---
        bq_batch_sink.bq.ensure_sink()

        # --- Start streaming ---
        silver_df: DataFrame = read_table_stream(
            spark, SILVER_TABLE_FQ, MAX_FILES_PER_TRIGGER,
        )

        Path(GOLD_CHECKPOINT).mkdir(parents=True, exist_ok=True)

        query: StreamingQuery = (
            silver_df.writeStream
            .queryName("gold_bq_sink")
            .outputMode("append")
            .option("checkpointLocation", GOLD_CHECKPOINT)
            .trigger(processingTime=TRIGGER_INTERVAL)
            .foreachBatch(_make_foreach_batch_fn(bq_batch_sink))
            .start()
        )

        log.info(
            f"Gold streaming started: {SILVER_TABLE_FQ} → BigQuery "
            f"| trigger={TRIGGER_INTERVAL} | checkpoint={GOLD_CHECKPOINT}"
        )

        run_until_shutdown([query])

    except Exception as exc:
        log.error(f"Gold layer failed: {exc}")
        raise

    finally:
        log.info("Stopping Gold streaming query...")
        for q in spark.streams.active:
            log.info(f"Stopping query: {q.name}")
            q.stop()
        spark.stop()
        log.info("Gold layer shut down cleanly.")


if __name__ == "__main__":
    main()
