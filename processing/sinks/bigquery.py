"""BigQuery sink — Load API ingestion for the Gold layer.

Two classes, consistent with qdrant_sink.py:
  - BigQueryManager — manages the client, dataset, table, and dedup view
  - BatchSink       — composes BigQueryManager to process foreachBatch micro-batches
"""

import shutil
import time
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account
from pyspark.sql import DataFrame

from config.settings import settings
from processing.schemas import Gold
from platform_commons.logger import Logger

log = Logger.get(__name__)


# -------------------------
# BigQueryManager
# -------------------------

class BigQueryManager:
    """Manages the BigQuery client, dataset, table, and dedup view."""

    def __init__(self) -> None:
        credentials = service_account.Credentials.from_service_account_file(
            settings.gcp.GOOGLE_APPLICATION_CREDENTIALS,
            scopes=["https://www.googleapis.com/auth/bigquery"],
        )
        self._client = bigquery.Client(
            project=settings.gcp.PROJECT_ID, credentials=credentials,
        )
        
        self._project = settings.gcp.PROJECT_ID
        self._dataset = settings.gcp.BIGQUERY_DATASET
        self._table = settings.gcp.BIGQUERY_TABLE
        self._table_ref = f"{self._project}.{self._dataset}.{self._table}"
        self._dedup_view = f"{self._table_ref}_deduped"
        self._dedup_sql = f"""
            SELECT * EXCEPT(row_num) FROM (
              SELECT *, ROW_NUMBER() OVER (
                PARTITION BY review_id ORDER BY ingestion_timestamp DESC
              ) AS row_num
              FROM `{self._table_ref}`
            ) WHERE row_num = 1
        """
        log.info(f"BigQueryManager created: project={self._project}")

    @property
    def client(self) -> bigquery.Client:
        """Exposes the raw client for direct queries (e.g. check_sinks.py)."""
        return self._client

    @property
    def table_ref(self) -> str:
        """Fully qualified table reference."""
        return self._table_ref

    def ensure_sink(self) -> None:
        """Creates BigQuery dataset and dedup view if they don't exist."""

        dataset = bigquery.Dataset(f"{self._project}.{self._dataset}")
        dataset.location = "US"
        self._client.create_dataset(dataset, exists_ok=True)
        log.info(f"BigQuery dataset ensured: {self._project}.{self._dataset}")

        self._ensure_dedup_view()

    def _ensure_dedup_view(self) -> None:
        """Creates the dedup view if the underlying table exists."""

        try:
            view = bigquery.Table(self._dedup_view)
            view.view_query = self._dedup_sql
            self._client.create_table(view, exists_ok=True)
            log.info(f"BigQuery dedup view ensured: {self._dedup_view}")
        except Exception as exc:
            log.warning(f"Dedup view creation deferred (table may not exist yet): {exc}")

    def load_dataframe(self, pandas_df) -> str:
        """Loads a pandas DataFrame into BigQuery via the Load API.

        Returns the BigQuery job ID.
        """

        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        )
        job = self._client.load_table_from_dataframe(
            pandas_df, self._table_ref, job_config=job_config,
        )
        job.result()  # Block until load completes
        return job.job_id
    
    def reset(self, checkpoint_path: str) -> None:
        """Deletes the BigQuery table, dedup view, and checkpoint for a clean rerun."""

        self._client.delete_table(self._dedup_view, not_found_ok=True)
        log.info(f"BigQuery view deleted (if existed): {self._dedup_view}")

        self._client.delete_table(self._table_ref, not_found_ok=True)
        log.info(f"BigQuery table deleted (if existed): {self._table_ref}")

        cp = Path(checkpoint_path)
        if cp.exists():
            shutil.rmtree(cp)
            log.info(f"Checkpoint directory deleted: {checkpoint_path}")


# -------------------------
# BatchSink
# -------------------------

class BatchSink:
    """Composes BigQueryManager to process foreachBatch micro-batches.

    Usage in gold.py:
        sink = BatchSink()
        sink.sink_batch(batch_df, batch_id)
    """

    def __init__(self) -> None:
        self._bq = BigQueryManager()
        self._dedup_view_created = False

    @property
    def bq(self) -> BigQueryManager:
        """Exposes BigQueryManager for setup/reset operations in gold.py."""
        return self._bq

    def sink_batch(self, batch_df: DataFrame, batch_id: int) -> None:
        """Loads a micro-batch into BigQuery via the Load API.

        Self-contained try/except — errors are logged but never propagated,
        so a BigQuery failure does not block the Qdrant branch.
        """
        try:
            start = time.time()

            pandas_df = batch_df.select(Gold.BIGQUERY_SELECT).toPandas()
            record_count = len(pandas_df)

            job_id = self._bq.load_dataframe(pandas_df)

            elapsed = time.time() - start
            log.info(
                f"Batch {batch_id}: BigQuery loaded {record_count} rows "
                f"in {elapsed:.1f}s | job_id={job_id}"
            )

            if not self._dedup_view_created:
                try:
                    self._bq._ensure_dedup_view()
                    self._dedup_view_created = True
                except Exception as view_exc:
                    log.warning(f"Dedup view creation failed: {view_exc}")

        except Exception as exc:
            log.error(f"Batch {batch_id}: BigQuery load failed: {exc}")
