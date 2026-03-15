"""
Infrastructure provisioning — schema registry + Hive metastore.

Run once before starting any pipeline:
    python -m infra

Execution order:
    1. Schema Registry — registers Avro schemas, sets BACKWARD compatibility,
       enables server-side validation on topics. Non-fatal if Redpanda is down.
    2. Hive Metastore (requires SparkSession) — fatal if metastore is unreachable
"""

from infra.metastore_init import init_metastore
from infra.schema_registry import register_schemas
from platform_commons.utils.logger import Logger
from utils.spark_helpers import create_spark_session

log = Logger.get(__name__)


def main() -> None:
    log.info("Infrastructure provisioning starting...")

    # 1. Schema Registry — Avro registration + compatibility + topic validation, non-fatal
    try:
        registered = register_schemas()
        log.info(f"Schema registry complete: {registered}")
    except Exception as exc:
        log.warning(f"Schema registry failed (non-fatal, Redpanda may not be up): {exc}")

    # 2. Hive Metastore — needs Spark, fatal on failure
    spark = create_spark_session("InfraInit")
    try:
        init_metastore(spark)
    finally:
        spark.stop()

    log.info("Infrastructure provisioning finished.")


if __name__ == "__main__":
    main()
