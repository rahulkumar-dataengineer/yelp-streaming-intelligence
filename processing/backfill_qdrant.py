"""Qdrant backfill — reads from BigQuery, embeds via Gemini, upserts to Qdrant.

Standalone script (no Spark dependency). Reads gold_reviews from BigQuery,
iterates rows client-side in pages, embeds text via GeminiEmbedder, and
upserts to Qdrant via QdrantManager. A local JSON bookmark enables resume
on failure.

Entry point: python -m processing.backfill_qdrant
"""

import argparse
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from google.cloud import bigquery as bq_module
from qdrant_client.http.models import PointStruct

from config.settings import settings
from processing.sinks.bigquery import BigQueryManager
from processing.sinks.qdrant_sink import (
    GeminiEmbedder,
    QdrantManager,
    build_embedding_text,
    build_payload,
    review_id_to_uuid,
    PAYLOAD_FIELDS,
)
from platform_commons.logger import Logger

log = Logger.get(__name__)

BOOKMARK_PATH: str = "checkpoints/qdrant_backfill.json"
PAGE_SIZE: int = 5_000


def _load_bookmark() -> dict:
    """Loads the bookmark file, returning defaults if it doesn't exist."""
    path = Path(BOOKMARK_PATH)
    if not path.exists():
        return {"last_review_id": "", "total_upserted": 0, "updated_at": ""}
    with open(path) as f:
        return json.load(f)


def _save_bookmark(last_review_id: str, total_upserted: int) -> None:
    """Atomically writes the bookmark via temp file + os.replace()."""
    path = Path(BOOKMARK_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)

    bookmark = {
        "last_review_id": last_review_id,
        "total_upserted": total_upserted,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(bookmark, f, indent=2)
        os.replace(tmp_path, path)
    except Exception:
        os.unlink(tmp_path)
        raise


def _count_remaining(bq_client, table_ref: str, last_review_id: str) -> int:
    """Queries BQ for the count of rows remaining after the bookmark."""
    if last_review_id:
        query = f"SELECT COUNT(*) as cnt FROM `{table_ref}` WHERE review_id > @last_id"
        job_config = bq_module.QueryJobConfig(
            query_parameters=[
                bq_module.ScalarQueryParameter("last_id", "STRING", last_review_id),
            ]
        )
    else:
        query = f"SELECT COUNT(*) as cnt FROM `{table_ref}`"
        job_config = None

    result = bq_client.query(query, job_config=job_config).result()
    return list(result)[0].cnt


def _fetch_rows(bq_client, table_ref: str, last_review_id: str) -> "bq_module.table.RowIterator":
    """Issues a single BQ query for all rows after the bookmark, ordered by review_id.

    Returns a RowIterator that streams rows on demand (client-side pagination).
    """
    columns = ", ".join(PAYLOAD_FIELDS)

    if last_review_id:
        query = f"SELECT {columns} FROM `{table_ref}` WHERE review_id > @last_id ORDER BY review_id"
        job_config = bq_module.QueryJobConfig(
            query_parameters=[
                bq_module.ScalarQueryParameter("last_id", "STRING", last_review_id),
            ]
        )
    else:
        query = f"SELECT {columns} FROM `{table_ref}` ORDER BY review_id"
        job_config = None

    return bq_client.query(query, job_config=job_config).result()


def _process_page(
    page: list[dict],
    page_num: int,
    total_pages: int,
    embedder: GeminiEmbedder,
    qdrant: QdrantManager,
    total_upserted: int,
    start_time: float,
) -> tuple[str, int]:
    """Embeds and upserts a single page of rows. Returns (last_review_id, new_total_upserted)."""

    texts = [build_embedding_text(row) for row in page]
    embeddings = embedder.embed_batch(texts, page_num)

    points = [
        PointStruct(
            id=review_id_to_uuid(row["review_id"]),
            vector=embeddings[idx],
            payload=build_payload(row),
        )
        for idx, row in enumerate(page)
    ]

    qdrant.upsert_points(points)

    new_total = total_upserted + len(page)
    last_id = page[-1]["review_id"]
    elapsed = time.time() - start_time
    rate = new_total / elapsed if elapsed > 0 else 0
    remaining = ((total_pages - page_num) * PAGE_SIZE) / rate if rate > 0 else 0

    log.info(
        f"Page {page_num}/{total_pages}: upserted {len(page)} vectors | "
        f"total={new_total} | elapsed={elapsed:.0f}s | "
        f"rate={rate:.0f} rows/s | est_remaining={remaining:.0f}s"
    )

    return last_id, new_total


def main() -> None:
    """Backfills Qdrant from BigQuery gold_reviews with bookmark resumability."""

    parser = argparse.ArgumentParser(description="Qdrant backfill from BigQuery")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete Qdrant collection and bookmark, then start fresh",
    )
    args = parser.parse_args()

    bq_mgr = BigQueryManager()
    qdrant = QdrantManager()

    # --- Reset ---
    if args.reset:
        log.info("--reset: deleting Qdrant collection and bookmark")
        qdrant.reset()
        bookmark_path = Path(BOOKMARK_PATH)
        if bookmark_path.exists():
            bookmark_path.unlink()
            log.info(f"Bookmark deleted: {BOOKMARK_PATH}")
        return

    # --- Load bookmark ---
    bookmark = _load_bookmark()
    last_review_id = bookmark["last_review_id"]
    total_upserted = bookmark["total_upserted"]

    if last_review_id:
        log.info(f"Resuming from bookmark: last_review_id={last_review_id}, total_upserted={total_upserted}")
    else:
        log.info("No bookmark found — starting from beginning")

    # --- Count remaining ---
    remaining_count = _count_remaining(bq_mgr.client, bq_mgr.table_ref, last_review_id)
    if remaining_count == 0:
        log.info("No rows to process — Qdrant is up to date with BigQuery")
        return

    total_pages = math.ceil(remaining_count / PAGE_SIZE)
    est_hours = remaining_count / 5000 / 60  # ~5K embeddings/min
    log.info(
        f"Rows to process: {remaining_count} | pages: {total_pages} | "
        f"estimated time: {est_hours:.1f} hours"
    )

    # --- Ensure collection ---
    qdrant.ensure_collection()

    # --- Fetch and process ---
    embedder = GeminiEmbedder()
    row_iterator = _fetch_rows(bq_mgr.client, bq_mgr.table_ref, last_review_id)

    page: list[dict] = []
    page_num = 1
    start_time = time.time()

    try:
        for row in row_iterator:
            page.append(dict(row))

            if len(page) >= PAGE_SIZE:
                last_review_id, total_upserted = _process_page(
                    page, page_num, total_pages, embedder, qdrant,
                    total_upserted, start_time,
                )
                _save_bookmark(last_review_id, total_upserted)
                page = []
                page_num += 1

        # Final partial page
        if page:
            last_review_id, total_upserted = _process_page(
                page, page_num, total_pages, embedder, qdrant,
                total_upserted, start_time,
            )
            _save_bookmark(last_review_id, total_upserted)

    except Exception as exc:
        log.error(
            f"Backfill failed at page {page_num}: {exc} | "
            f"last_successful_review_id={last_review_id} | "
            f"total_upserted={total_upserted}"
        )
        sys.exit(1)

    elapsed = time.time() - start_time
    log.info(
        f"Backfill complete: {total_upserted} total vectors | "
        f"elapsed={elapsed:.0f}s ({elapsed/3600:.1f} hours)"
    )


if __name__ == "__main__":
    main()
