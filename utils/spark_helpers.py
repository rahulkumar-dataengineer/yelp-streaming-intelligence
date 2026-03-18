"""Shared Spark utilities for Bronze, Silver and Gold layers."""

import time
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.streaming import StreamingQuery

from config.settings import settings
from platform_commons.logger import Logger
from platform_commons.kafka import get_running

log = Logger.get(__name__)


def create_spark_session(
    app_name: str,
    extra_packages: list[str] | None = None,
    master: str = "local[1]",
    shuffle_partitions: int = 2,
    driver_memory: str = "1g",
) -> SparkSession:
    """Creates a Hive-enabled SparkSession with standard config."""

    builder = (
        SparkSession.builder
        .appName(app_name)
        .master(master)
        .config("spark.sql.streaming.forceDeleteTempCheckpointLocation", "true")
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.driver.memory", driver_memory)
        .config("spark.sql.catalogImplementation", "hive")
        .config("hive.metastore.uris", settings.hive.METASTORE_URI)
        .config("spark.sql.warehouse.dir", settings.hive.WAREHOUSE_DIR)
        .enableHiveSupport()
    )

    if extra_packages:
        builder = builder.config(
            "spark.jars.packages", ",".join(extra_packages)
        )

    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    log.info(f"SparkSession created: app={spark.sparkContext.appName}")
    return spark


def read_table_stream(
    spark: SparkSession,
    table_name: str,
    max_files_per_trigger: int = 5,
) -> DataFrame:
    """Reads a streaming table source from Hive metastore."""

    df: DataFrame = (
        spark.readStream
        .option("maxFilesPerTrigger", max_files_per_trigger)
        .table(table_name)
    )
    log.info(f"Table stream opened: {table_name} | maxFiles={max_files_per_trigger}")
    return df


def start_table_sink(
    df: DataFrame,
    query_name: str,
    table_name: str,
    checkpoint_path: str,
    partition_cols: list[str],
    trigger_interval: str = "10 seconds",
) -> StreamingQuery:
    """Starts a streaming write to a Hive metastore table."""

    Path(checkpoint_path).mkdir(parents=True, exist_ok=True)

    query: StreamingQuery = (
        df.writeStream
        .queryName(query_name)
        .outputMode("append")
        .option("checkpointLocation", checkpoint_path)
        .partitionBy(*partition_cols)
        .trigger(processingTime=trigger_interval)
        .toTable(table_name)
    )

    log.info(
        f"Table sink started: {query_name} → {table_name} | "
        f"checkpoint={checkpoint_path} | partitions={partition_cols}"
    )
    return query


def run_until_shutdown(
    queries: list[StreamingQuery],
    poll_seconds: int = 5,
    progress_interval: int = 10,
) -> None:
    """Polls streaming queries until shutdown signal or query failure.

    Logs progress metrics every *progress_interval* seconds so the operator
    can see that the pipeline is alive and how fast it's moving.
    """

    log.info(f"Monitoring {len(queries)} query(ies). Polling every {poll_seconds}s, progress every {progress_interval}s.")

    last_progress_log = time.time()
    cumulative_rows: dict[str, int] = {q.name: 0 for q in queries}

    while get_running():
        for q in queries:
            if not q.isActive:
                exception = q.exception()
                if exception:
                    log.error(f"Query '{q.name}' failed: {exception}")
                else:
                    log.warning(f"Query '{q.name}' stopped unexpectedly.")
                for other in queries:
                    if other.isActive:
                        other.stop()
                return

        # --- Progress logging ---
        now = time.time()
        if now - last_progress_log >= progress_interval:
            for q in queries:
                _log_query_progress(q, cumulative_rows)
            last_progress_log = now

        time.sleep(poll_seconds)


def _log_query_progress(
    q: StreamingQuery,
    cumulative_rows: dict[str, int],
) -> None:
    """Logs the latest progress of a single streaming query."""

    progress = q.lastProgress
    if not progress:
        log.info(f"[{q.name}] Waiting for first batch...")
        return

    batch_id = progress.get("batchId", "?")
    num_rows = progress.get("numInputRows", 0)
    input_rps = progress.get("inputRowsPerSecond", 0)
    proc_rps = progress.get("processedRowsPerSecond", 0)

    cumulative_rows[q.name] = cumulative_rows.get(q.name, 0) + num_rows

    # Source-specific offset info
    sources = progress.get("sources", [])
    offset_info = ""
    for src in sources:
        end_offset = src.get("endOffset")
        if not end_offset or not isinstance(end_offset, dict):
            continue
        # Kafka offsets: {topic: {partition: offset}}
        if all(isinstance(v, dict) for v in end_offset.values()):
            parts = []
            for topic, partitions in end_offset.items():
                for part_id, offset in partitions.items():
                    parts.append(f"{topic}[{part_id}]={offset}")
            if parts:
                offset_info = f" | offsets: {', '.join(parts)}"
        # File source offsets: {"logOffset": N}
        elif "logOffset" in end_offset:
            offset_info = f" | fileOffset={end_offset['logOffset']}"

    log.info(
        f"[{q.name}] batch={batch_id} | rows={num_rows} | "
        f"total={cumulative_rows[q.name]} | "
        f"in={input_rps:.0f} rows/s | proc={proc_rps:.0f} rows/s"
        f"{offset_info}"
    )