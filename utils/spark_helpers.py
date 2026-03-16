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
    master: str = "local[2]",
    shuffle_partitions: int = 4,
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
    trigger_interval: str = "30 seconds",
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
) -> None:
    """Polls streaming queries until shutdown signal or query failure."""

    log.info(f"Monitoring {len(queries)} query(ies). Polling every {poll_seconds}s.")

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

        time.sleep(poll_seconds)