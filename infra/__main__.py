"""
Infrastructure provisioning — schema registry + Hive metastore.

Run once before starting any pipeline:
    python -m infra

Execution order:
    1. Schema Registry — registers Avro schemas, sets BACKWARD compatibility,
       enables server-side validation on topics. Non-fatal if Redpanda is down.
    2. Hive Metastore (requires SparkSession) — fatal if metastore is unreachable
"""

from config.settings import settings
from infra.hive_ddl import BRONZE_BUSINESSES_DDL, BRONZE_REVIEWS_DDL, SILVER_REVIEWS_DDL, SILVER_QUARANTINE_DDL
from platform_commons.hive import init_metastore
from platform_commons.kafka import register_all
from platform_commons.logger import Logger
from schemas import BUSINESS_AVRO_SCHEMA, REVIEW_AVRO_SCHEMA
from utils.spark_helpers import create_spark_session

log = Logger.get(__name__)


def main() -> None:
    log.info("Infrastructure provisioning starting...")

    # 1. Schema Registry — Avro registration + compatibility + topic validation, non-fatal
    try:
        registered = register_all(
            registry_url=settings.kafka.SCHEMA_REGISTRY_URL,
            bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
            subject_schemas={
                f"{settings.kafka.BUSINESS_TOPIC}-value": BUSINESS_AVRO_SCHEMA,
                f"{settings.kafka.REVIEW_TOPIC}-value": REVIEW_AVRO_SCHEMA,
            },
        )
        log.info(f"Schema registry complete: {registered}")
    except Exception as exc:
        log.warning(f"Schema registry failed (non-fatal, Redpanda may not be up): {exc}")

    # 2. Hive Metastore — needs Spark, fatal on failure
    spark = create_spark_session("InfraInit")
    try:
        init_metastore(
            spark=spark,
            databases=[settings.hive.BRONZE_DB, settings.hive.SILVER_DB, settings.hive.GOLD_DB],
            tables=[
                (f"{settings.hive.BRONZE_DB}.businesses", BRONZE_BUSINESSES_DDL.format(db=settings.hive.BRONZE_DB)),
                (f"{settings.hive.BRONZE_DB}.reviews", BRONZE_REVIEWS_DDL.format(db=settings.hive.BRONZE_DB)),
                (f"{settings.hive.SILVER_DB}.reviews", SILVER_REVIEWS_DDL.format(db=settings.hive.SILVER_DB)),
                (f"{settings.hive.SILVER_DB}.quarantine", SILVER_QUARANTINE_DDL.format(db=settings.hive.SILVER_DB)),
            ],
        )
    finally:
        spark.stop()

    log.info("Infrastructure provisioning finished.")


if __name__ == "__main__":
    main()
