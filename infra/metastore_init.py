"""Metastore initialisation — creates Yelp databases and tables."""

from pyspark.sql import SparkSession

from config.settings import settings
from infra.hive_ddl import BRONZE_BUSINESSES_DDL, BRONZE_REVIEWS_DDL, SILVER_REVIEWS_DDL
from platform_commons.infra.metastore import init_metastore as _init_metastore


def init_metastore(spark: SparkSession) -> None:
    """Creates Bronze, Silver, and Gold databases and registers all Yelp tables."""
    _init_metastore(
        spark=spark,
        databases=[
            settings.hive.BRONZE_DB,
            settings.hive.SILVER_DB,
            settings.hive.GOLD_DB,
        ],
        tables=[
            (f"{settings.hive.BRONZE_DB}.businesses", BRONZE_BUSINESSES_DDL.format(db=settings.hive.BRONZE_DB)),
            (f"{settings.hive.BRONZE_DB}.reviews", BRONZE_REVIEWS_DDL.format(db=settings.hive.BRONZE_DB)),
            (f"{settings.hive.SILVER_DB}.reviews", SILVER_REVIEWS_DDL.format(db=settings.hive.SILVER_DB)),
        ],
    )


if __name__ == "__main__":
    from utils.spark_helpers import create_spark_session

    spark = create_spark_session("MetastoreInit")
    try:
        init_metastore(spark)
    finally:
        spark.stop()
