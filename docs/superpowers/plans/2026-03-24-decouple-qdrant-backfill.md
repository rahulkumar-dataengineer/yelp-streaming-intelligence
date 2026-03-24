# Decouple Qdrant Backfill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple Qdrant embedding+upsert from the gold layer's foreachBatch, making gold BQ-only, and create a standalone backfill script that reads from BigQuery and upserts to Qdrant with bookmark-based resumability.

**Architecture:** Gold layer drops its Qdrant branch — `foreachBatch` only calls the BigQuery sink. A new `processing/backfill_qdrant.py` issues a single BQ query ordered by `review_id`, iterates rows client-side in pages of 5,000, embeds via `GeminiEmbedder`, upserts via `QdrantManager`, and updates a local JSON bookmark after each page. On crash, re-running resumes from the bookmark.

**Tech Stack:** BigQuery client (existing), Gemini Embedding API (existing `GeminiEmbedder`), Qdrant client (existing `QdrantManager`), `os.replace()` for atomic bookmark writes.

**Spec:** `docs/superpowers/specs/2026-03-24-decouple-qdrant-backfill-design.md`

---

### Task 1: Extract helper functions to module level in `qdrant_sink.py`

**Files:**
- Modify: `processing/sinks/qdrant_sink.py:241-261`

The three helper methods on `BatchSink` (`_review_id_to_uuid`, `_build_embedding_text`, `_build_payload`) are pure data transforms with no state. Extract them to module-level functions so the backfill script can import them directly.

- [ ] **Step 1: Extract `_review_id_to_uuid` to module-level function**

Move from `BatchSink` method to a module-level function above the `BatchSink` class. Same logic, new name without leading underscore:

```python
def review_id_to_uuid(review_id: str) -> str:
    """Deterministic UUID from review_id for idempotent Qdrant upserts."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, review_id))
```

- [ ] **Step 2: Extract `_build_embedding_text` to module-level function**

```python
def build_embedding_text(row: dict) -> str:
    """Concatenates embedding text fields: "business_name | categories | review_text"."""
    parts = [str(row.get(field, "") or "") for field in EMBEDDING_TEXT_FIELDS]
    return " | ".join(parts)
```

- [ ] **Step 3: Extract `_build_payload` to module-level function**

```python
def build_payload(row: dict) -> dict:
    """Extracts payload fields from a row, dropping None values."""
    payload = {}
    for field in PAYLOAD_FIELDS:
        value = row.get(field)
        if value is not None:
            payload[field] = value.item() if hasattr(value, "item") else value
    return payload
```

- [ ] **Step 4: Update `BatchSink.sink_batch` to call the module-level functions**

Replace `self._review_id_to_uuid(...)`, `self._build_embedding_text(...)`, and `self._build_payload(...)` with `review_id_to_uuid(...)`, `build_embedding_text(...)`, and `build_payload(...)`. Remove the three instance methods from `BatchSink`.

- [ ] **Step 5: Verify gold.py still works**

Run: `python -c "from processing.sinks.qdrant_sink import BatchSink, GeminiEmbedder, QdrantManager, review_id_to_uuid, build_embedding_text, build_payload; print('All imports OK')"`

Expected: `All imports OK` — confirms both classes and new module-level functions are importable.

- [ ] **Step 6: Commit**

```bash
git add processing/sinks/qdrant_sink.py
git commit -m "refactor: extract qdrant helper functions to module level for reuse"
```

---

### Task 2: Simplify gold.py to BQ-only

**Files:**
- Modify: `processing/gold.py:1-137`

Remove all Qdrant references. Gold becomes a single-sink BQ loader.

- [ ] **Step 1: Update module docstring**

Replace lines 1-10:

```python
"""
Gold layer — BigQuery sink via foreachBatch.
Reads the Silver reviews table as a streaming file source.

Qdrant vectorization is handled separately by processing.backfill_qdrant,
which reads from BigQuery after gold finishes loading.
"""
```

- [ ] **Step 2: Remove qdrant_sink import**

Remove line 21: `from processing.sinks import qdrant_sink as qd_sink`

- [ ] **Step 3: Simplify `_make_foreach_batch_fn` — remove Qdrant parameter and call**

Change the function to accept only `bq_batch_sink`:

```python
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
```

- [ ] **Step 4: Simplify `main()` — remove Qdrant sink creation, reset, and ensure**

In `main()`:
- Remove `qd_batch_sink = qd_sink.BatchSink()` (line 86)
- Remove `qd_batch_sink.qdrant.reset()` (line 93)
- Remove `qd_batch_sink.qdrant.ensure_collection()` (line 97)
- Update `--reset` help text to only mention BigQuery
- Update argparse description to `"Gold layer — BigQuery sink"`
- Update `_make_foreach_batch_fn(bq_batch_sink, qd_batch_sink)` → `_make_foreach_batch_fn(bq_batch_sink)`
- Update query name from `"gold_dual_sink"` to `"gold_bq_sink"` (line 108)
- Update log message from `"BigQuery + Qdrant"` to `"BigQuery"` (line 117)
- Update `main()` docstring to `"Reads Silver table and loads to BigQuery via foreachBatch."`

- [ ] **Step 5: Verify import works**

Run: `python -c "from processing.gold import main; print('gold.py import OK')"`

Expected: `gold.py import OK`

- [ ] **Step 6: Commit**

```bash
git add processing/gold.py
git commit -m "refactor: simplify gold layer to BQ-only sink, decouple Qdrant"
```

---

### Task 3: Create the backfill script

**Files:**
- Create: `processing/backfill_qdrant.py`

This is the core new file. One-shot script that reads from BigQuery, embeds, and upserts to Qdrant with bookmark resumability.

- [ ] **Step 1: Create `processing/backfill_qdrant.py` with imports and constants**

```python
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
```

- [ ] **Step 2: Add bookmark read/write functions**

```python
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
```

- [ ] **Step 3: Add the `_count_remaining` function**

`QueryJobConfig` and `ScalarQueryParameter` live on the `google.cloud.bigquery` module (imported as `bq_module` in Step 1), not on the client instance.

```python
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
```

- [ ] **Step 4: Add the `_fetch_rows` function**

```python
def _fetch_rows(bq_client, table_ref: str, last_review_id: str) -> "google.cloud.bigquery.table.RowIterator":
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
```

- [ ] **Step 5: Add the `_process_page` function**

```python
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
```

- [ ] **Step 6: Add `main()` function**

```python
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
```

- [ ] **Step 7: Verify script imports**

Run: `python -c "from processing.backfill_qdrant import main; print('backfill_qdrant imports OK')"`

Expected: `backfill_qdrant imports OK`

- [ ] **Step 8: Commit**

```bash
git add processing/backfill_qdrant.py
git commit -m "feat: add standalone Qdrant backfill script with bookmark resumability"
```

---

### Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

Update architecture references, commands, and directory structure to reflect the decoupled design.

- [ ] **Step 1: Update architecture diagram**

In the `## Architecture` section, change the pipeline diagram from:
```
  → PySpark Gold → BigQuery (Load API) + Qdrant (256-dim embeddings)
```
to:
```
  → PySpark Gold → BigQuery (Load API)
  → backfill_qdrant.py → BigQuery → Gemini Embed → Qdrant (256-dim embeddings)
```

- [ ] **Step 2: Update Medallion Rules — Gold section**

Change the Gold bullet from:
> **Gold**: Dual sink via `foreachBatch`. BigQuery via **Load API only**. Qdrant via Gemini Embedding batch upsert. Independent try/except per branch. Idempotent via `review_id`.

to:
> **Gold**: BigQuery sink via `foreachBatch`. BigQuery via **Load API only**. Idempotent via `review_id`. Qdrant vectorization is handled separately by `processing/backfill_qdrant.py`, which reads from BigQuery after gold finishes loading.

- [ ] **Step 3: Add backfill script to Commands section**

Add after the `python -m processing.gold` entry:
```bash
# Qdrant backfill (after gold completes)
python -m processing.backfill_qdrant          # resumes from bookmark
python -m processing.backfill_qdrant --reset  # clean rerun
```

- [ ] **Step 4: Add `processing/backfill_qdrant.py` to Directory Structure**

In the `processing/` section of the directory tree, add:
```
│   ├── backfill_qdrant.py       # Standalone BQ→Qdrant backfill with bookmark
```

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for decoupled Qdrant backfill architecture"
```

---

### Task 5: Update `docs/explanation.md`

**Files:**
- Modify: `docs/explanation.md`

Append a new section documenting the decoupling decision.

- [ ] **Step 1: Append Phase 5c section**

Add at the end of `docs/explanation.md`:

```markdown
## Phase 5c: Decoupling Qdrant from the Gold Layer

### What Changed
The gold layer originally ran BigQuery and Qdrant as parallel branches in a single `foreachBatch` callback. This created problems: a 3-hour embedding job blocked BQ loads, Qdrant failures couldn't resume without resetting the entire pipeline, and there was no way to rebuild the vector index independently.

### The Fix
Gold now only writes to BigQuery — fast, simple, no embedding dependency. A new standalone script (`processing/backfill_qdrant.py`) reads from BigQuery, embeds via Gemini, and upserts to Qdrant. It uses a local JSON bookmark (`checkpoints/qdrant_backfill.json`) to track progress. If it crashes, re-running picks up from the last successful page.

### Key Design Decisions
- **Single BQ query with client-side pagination** — BigQuery charges per bytes scanned, not per bytes returned. Issuing 200 paginated queries would scan the table 200 times. Instead, one query streams all rows, and the script iterates in pages of 5,000 client-side.
- **`review_id` as pagination key** — Already unique, already the dedup key. No surrogate key needed.
- **Atomic bookmark writes** — `os.replace()` on POSIX is atomic. No half-written bookmarks on crash.
- **BQ as source of truth for Qdrant** — The vector index is now a derived index that can be rebuilt from the authoritative store at any time. The right enterprise pattern.

### Enterprise Framing
In production, this pattern is common: the analytical store (warehouse/lake) is loaded first by a reliable, fast pipeline, and derived indexes (search, vector, cache) are populated by separate backfill jobs that can be re-run independently. This gives operational flexibility — you can rebuild any derived index without re-running the entire pipeline. The bookmark pattern is analogous to Kafka consumer offsets: track where you left off, resume from there.
```

- [ ] **Step 2: Commit**

```bash
git add -f docs/explanation.md
git commit -m "docs: append Phase 5c — Qdrant backfill decoupling explanation"
```

---

### Task 6: Update `docs/todo.md`

**Files:**
- Modify: `docs/todo.md`

Add the Phase 5c tasks to the task tracker.

- [ ] **Step 1: Add Phase 5c section to `docs/todo.md`**

Add after the Phase 5 section:

```markdown
## Phase 5c: Decouple Qdrant Backfill
- [ ] Extract `qdrant_sink.py` helper functions to module level
- [ ] Simplify `gold.py` to BQ-only sink
- [ ] Create `processing/backfill_qdrant.py` — standalone backfill with bookmark
- [ ] Update `CLAUDE.md` — architecture, commands, directory structure
- [ ] Update `docs/explanation.md` — append Phase 5c documentation
```

- [ ] **Step 2: Commit**

```bash
git add -f docs/todo.md
git commit -m "docs: add Phase 5c tasks to todo tracker"
```
