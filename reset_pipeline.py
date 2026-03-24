"""
Full pipeline reset — deletes ALL state so you can start from scratch.

Deletes:
  1. Kafka topics (yelp_businesses, yelp_reviews) and recreates them
  2. Hive Metastore databases (bronze, silver, gold) — DROP CASCADE + recreate
  3. Spark warehouse data (/tmp/spark-warehouse/*)
  4. Spark checkpoints (checkpoints/bronze, checkpoints/silver, checkpoints/gold)
     and Qdrant backfill bookmark (checkpoints/qdrant_backfill.json)
  5. BigQuery table + dedup view
  6. Qdrant collection

Usage:
    python reset_pipeline.py          # interactive — prompts before each step
    python reset_pipeline.py --yes    # skip confirmation, reset everything

After reset, run in order:
    python -m infra                   # re-register schemas + recreate Hive tables
    python -m ingestion.producer      # produce messages to Kafka
    python -m processing.bronze       # consume Kafka → Bronze Parquet
    python -m processing.silver       # Bronze → cleaned/joined Silver
    python -m processing.gold         # Silver → BigQuery
    python -m processing.backfill_qdrant  # BigQuery → Qdrant
"""

import argparse
import shutil
import sys
from pathlib import Path

from platform_commons.logger import Logger

log = Logger.get(__name__)

PROJECT_ROOT = Path(__file__).parent


def _confirm(msg: str, auto_yes: bool) -> bool:
    """Returns True if the user confirms (or auto_yes is set)."""
    if auto_yes:
        return True
    answer = input(f"{msg} [y/N] ").strip().lower()
    return answer in ("y", "yes")


def reset_kafka() -> None:
    """Delete and recreate Kafka topics."""
    from confluent_kafka.admin import AdminClient, NewTopic
    from config.settings import settings

    admin = AdminClient({"bootstrap.servers": settings.kafka.BOOTSTRAP_SERVERS})
    topics = [settings.kafka.BUSINESS_TOPIC, settings.kafka.REVIEW_TOPIC]

    existing = [t for t in topics if t in admin.list_topics(timeout=5).topics]
    if existing:
        log.info(f"Deleting Kafka topics: {existing}")
        futures = admin.delete_topics(existing, operation_timeout=10)
        for topic, future in futures.items():
            try:
                future.result()
                log.info(f"  Deleted: {topic}")
            except Exception as exc:
                log.warning(f"  Failed to delete {topic}: {exc}")

        # Wait for deletion to propagate
        import time
        time.sleep(3)

    log.info(f"Creating Kafka topics: {topics}")
    new_topics = [NewTopic(t, num_partitions=1, replication_factor=1) for t in topics]
    futures = admin.create_topics(new_topics)
    for topic, future in futures.items():
        try:
            future.result()
            log.info(f"  Created: {topic}")
        except Exception as exc:
            log.warning(f"  Failed to create {topic}: {exc}")


def reset_hive_metastore() -> None:
    """Drop and recreate Hive databases via Spark SQL."""
    from pyspark.sql import SparkSession
    from config.settings import settings

    spark = (
        SparkSession.builder
        .appName("ResetHiveMetastore")
        .master("local[1]")
        .config("spark.sql.catalogImplementation", "hive")
        .config("hive.metastore.uris", settings.hive.METASTORE_URI)
        .config("spark.sql.warehouse.dir", settings.hive.WAREHOUSE_DIR)
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("ERROR")

    for db in [settings.hive.BRONZE_DB, settings.hive.SILVER_DB, settings.hive.GOLD_DB]:
        log.info(f"Dropping Hive database: {db}")
        spark.sql(f"DROP DATABASE IF EXISTS {db} CASCADE")

    spark.stop()
    log.info("Hive databases dropped. Run 'python -m infra' to recreate.")


def reset_spark_warehouse() -> None:
    """Delete all data in the Spark warehouse directory."""
    from config.settings import settings

    warehouse = Path(settings.hive.WAREHOUSE_DIR)
    if warehouse.exists():
        for child in warehouse.iterdir():
            if child.is_dir():
                log.info(f"Deleting warehouse dir: {child}")
                shutil.rmtree(child)
        log.info("Spark warehouse cleaned.")
    else:
        log.info("Spark warehouse directory does not exist — nothing to clean.")


def reset_checkpoints() -> None:
    """Delete all Spark checkpoint directories and the Qdrant backfill bookmark."""
    cp_root = PROJECT_ROOT / "checkpoints"
    if cp_root.exists():
        for child in cp_root.iterdir():
            if child.is_dir():
                log.info(f"Deleting checkpoint: {child}")
                shutil.rmtree(child)
            elif child.is_file():
                log.info(f"Deleting checkpoint file: {child}")
                child.unlink()
        log.info("All checkpoints deleted.")
    else:
        log.info("No checkpoints directory — nothing to clean.")


def reset_bigquery() -> None:
    """Delete BigQuery table and dedup view."""
    from google.cloud import bigquery
    from google.oauth2 import service_account
    from config.settings import settings

    credentials = service_account.Credentials.from_service_account_file(
        settings.gcp.GOOGLE_APPLICATION_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    client = bigquery.Client(project=settings.gcp.PROJECT_ID, credentials=credentials)

    table_ref = f"{settings.gcp.PROJECT_ID}.{settings.gcp.BIGQUERY_DATASET}.{settings.gcp.BIGQUERY_TABLE}"
    view_ref = f"{table_ref}_deduped"

    client.delete_table(view_ref, not_found_ok=True)
    log.info(f"BigQuery view deleted: {view_ref}")

    client.delete_table(table_ref, not_found_ok=True)
    log.info(f"BigQuery table deleted: {table_ref}")


def reset_qdrant() -> None:
    """Delete Qdrant collection."""
    from qdrant_client import QdrantClient
    from config.settings import settings

    client = QdrantClient(
        host=settings.qdrant.HOST,
        port=settings.qdrant.PORT,
        timeout=10,
    )

    collection = settings.qdrant.COLLECTION
    if client.collection_exists(collection_name=collection):
        client.delete_collection(collection_name=collection)
        log.info(f"Qdrant collection deleted: {collection}")
    else:
        log.info(f"Qdrant collection does not exist: {collection}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Full pipeline reset — clean slate")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip confirmation prompts")
    args = parser.parse_args()

    print("\n=== FULL PIPELINE RESET ===")
    print("This will delete ALL data: Kafka topics, Hive tables, checkpoints,")
    print("BigQuery table/view, and Qdrant collection.\n")

    if not _confirm("Proceed with full reset?", args.yes):
        print("Aborted.")
        sys.exit(0)

    steps = [
        ("Kafka topics", reset_kafka),
        ("Spark checkpoints", reset_checkpoints),
        ("Spark warehouse data", reset_spark_warehouse),
        ("Hive Metastore databases", reset_hive_metastore),
        ("BigQuery table + view", reset_bigquery),
        ("Qdrant collection", reset_qdrant),
    ]

    for name, fn in steps:
        if _confirm(f"  Reset {name}?", args.yes):
            try:
                fn()
            except Exception as exc:
                log.error(f"Failed to reset {name}: {exc}")
                if not _confirm("  Continue with remaining steps?", args.yes):
                    sys.exit(1)
        else:
            log.info(f"Skipped: {name}")

    print("\n=== RESET COMPLETE ===")
    print("Next steps:")
    print("  1. python -m infra                  # recreate schemas + Hive tables")
    print("  2. python -m ingestion.producer      # produce to Kafka")
    print("  3. python -m processing.bronze       # Bronze layer")
    print("  4. python -m processing.silver       # Silver layer")
    print("  5. python -m processing.gold         # Gold layer (BQ only)")
    print("  6. python -m processing.backfill_qdrant  # Qdrant backfill")
    print()


if __name__ == "__main__":
    main()
