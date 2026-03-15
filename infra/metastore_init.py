"""Metastore initialisation — creates databases and tables."""

from pyspark.sql import SparkSession

from config.settings import settings
from utils.logger import Logger
from infra.hive_ddl import BRONZE_BUSINESSES_DDL, BRONZE_REVIEWS_DDL, SILVER_REVIEWS_DDL

log = Logger.get(__name__)


def init_metastore(spark: SparkSession) -> None:
    """Creates Bronze, Silver, and Gold databases and registers all tables."""

    for db in [
        settings.hive.BRONZE_DB,
        settings.hive.SILVER_DB,
        settings.hive.GOLD_DB,
    ]:
        spark.sql(f"CREATE DATABASE IF NOT EXISTS {db}")
        log.info(f"Database ensured: {db}")

    tables = [
        ("businesses", BRONZE_BUSINESSES_DDL, settings.hive.BRONZE_DB),
        ("reviews", BRONZE_REVIEWS_DDL, settings.hive.BRONZE_DB),
        ("reviews", SILVER_REVIEWS_DDL, settings.hive.SILVER_DB),
    ]

    for table_name, ddl_template, db in tables:
        spark.sql(ddl_template.format(db=db))
        log.info(f"Table ensured: {db}.{table_name}")

    log.info("Metastore initialisation complete.")


if __name__ == "__main__":
    from utils.spark_helpers import create_spark_session

    spark = create_spark_session("MetastoreInit")
    try:
        init_metastore(spark)
    finally:
        spark.stop()
