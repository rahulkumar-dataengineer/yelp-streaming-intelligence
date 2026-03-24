# Decouple Qdrant from Gold Layer — Backfill Script Design

**Date:** 2026-03-24
**Status:** Approved
**Scope:** Gold layer simplification + new standalone Qdrant backfill script

---

## Problem Statement

The current gold layer runs BigQuery Load API and Qdrant embedding+upsert as parallel branches in a single `foreachBatch` callback. This coupling creates four problems:

1. **Coupling a 3-hour job to a seconds-fast job.** If Qdrant embedding fails mid-batch, Spark's checkpoint has already advanced past those rows (BQ succeeded). The only recovery is resetting the entire gold checkpoint and re-running from scratch.

2. **No resumability for Qdrant.** There's no record of which reviews were successfully embedded. A crash means `--reset` and start over from zero.

3. **No operational flexibility.** Qdrant can only be populated by running the Spark pipeline. There's no way to rebuild the vector index from the authoritative store (BigQuery) independently.

4. **Resource contention.** Embedding 1M reviews takes ~3.3 hours of sustained Gemini API calls with rate limiting sleeps. During this time, Spark's `foreachBatch` trigger is blocked — new Silver rows pile up waiting.

## Solution

Decouple the two sinks:
- **Gold layer** becomes BQ-only (fast, simple, no embedding dependency)
- **New backfill script** reads from BigQuery, embeds via Gemini, upserts to Qdrant with bookmark-based resumability

## Architecture

### Before (coupled dual-sink)
```
Silver Table → PySpark foreachBatch → ┬─ BigQuery Load API
                                      └─ Gemini Embed → Qdrant Upsert
```

### After (decoupled)
```
Silver Table → PySpark foreachBatch → BigQuery Load API

BigQuery gold_reviews → backfill_qdrant.py → Gemini Embed → Qdrant Upsert
                        (bookmark-resumable)
```

## Design Details

### Gold Layer Changes (`processing/gold.py`)

Remove all Qdrant references:
- Remove `qdrant_sink` import and `qd_batch_sink` instantiation
- Remove `qd_batch_sink.qdrant.ensure_collection()` call
- Remove `--reset` Qdrant branch (BQ reset stays)
- `foreachBatch` callback calls only `bq_batch_sink.sink_batch()`
- Update docstrings from "dual-sink" to "BigQuery sink"

No changes to `processing/sinks/bigquery.py`.

Minor refactor in `processing/sinks/qdrant_sink.py`: extract `_review_id_to_uuid`, `_build_embedding_text`, and `_build_payload` from `BatchSink` into module-level functions. These are pure data transforms with no state — they belong at module scope so both `BatchSink` (unchanged behavior) and the backfill script can reuse them. `BatchSink` methods become thin wrappers or are removed in favor of direct calls.

### Backfill Script (`processing/backfill_qdrant.py`)

Standalone Python script — no Spark dependency. Entry point: `python -m processing.backfill_qdrant`

**Core loop:**
```
Query total rows remaining (COUNT WHERE review_id > @bookmark)
  → Log: "N rows to process, estimated ~X hours"
  → Single BQ query: SELECT [payload_fields] FROM gold_reviews
                     WHERE review_id > @bookmark ORDER BY review_id
  → Iterate result rows client-side in pages of 5,000
  → For each page:
      → Embed texts via GeminiEmbedder (reused from qdrant_sink.py)
      → Upsert to Qdrant via QdrantManager (reused from qdrant_sink.py)
      → Update bookmark to last review_id in page
      → Log: "Page N/M complete, X rows upserted, elapsed: Ys"
```

**Single BQ query, client-side pagination.** BigQuery charges by bytes scanned, not bytes returned. A `WHERE review_id > @bookmark ORDER BY review_id LIMIT 5000` query scans ALL rows to evaluate the WHERE clause — 200 such queries would scan the table 200 times, potentially consuming the entire 1TB/month free quota. Instead, issue one query (one full scan) and iterate the result set client-side in pages of 5,000 rows using the BigQuery client's row iterator.

**Page size:** 5,000 rows per client-side page. At 100 embeddings per Gemini API call, that's 50 API calls per page — well within rate limits, keeps memory low. The BQ client streams rows on demand, so only one page is in memory at a time.

**Bookmark file:** `checkpoints/qdrant_backfill.json`
```json
{
  "last_review_id": "abc123XYZ",
  "total_upserted": 50000,
  "updated_at": "2026-03-24T14:30:00Z"
}
```
Written atomically after each successful Qdrant upsert: write to a temp file in the same directory, then `os.replace()` (POSIX-atomic) to the bookmark path.

**Queries raw `gold_reviews` table** (not the dedup view). Rationale: the dedup view forces an additional full table scan per query. Since Qdrant upserts are idempotent via UUID5 on `review_id`, occasional duplicate rows from BQ reprocessing are harmless and self-correcting.

**Pagination key:** `review_id` (string). Already unique across all rows — serves as the natural primary key. The single BQ query uses `WHERE review_id > @last_review_id ORDER BY review_id` — the bookmark provides the resume point, and client-side iteration provides the paging.

**BQ access:** Uses `BigQueryManager.client` property (already exposed) to call `client.query()` directly. No new methods needed — the backfill is the only consumer, and adding a generic query abstraction for one caller would be over-engineering.

**Failure behavior:**
- Qdrant upsert is the last step before bookmark update
- If upsert fails, bookmark is NOT updated — next run re-reads the same page
- Safe because Qdrant upserts are idempotent (deterministic UUID5 from review_id)
- On failure: logs last successful `review_id`, total upserted, and the error
- Exits with non-zero status code

**`--reset` flag:** Deletes the Qdrant collection and bookmark file for clean reruns.

**Class and function reuse:**
- `GeminiEmbedder` from `processing.sinks.qdrant_sink` — embedding with rate limiting and retry
- `QdrantManager` from `processing.sinks.qdrant_sink` — collection management and upsert
- `review_id_to_uuid()`, `build_embedding_text()`, `build_payload()` — extracted to module-level functions in `qdrant_sink.py` (see Gold Layer Changes section)
- `BigQueryManager.client` from `processing.sinks.bigquery` — raw BQ client for queries

**Progress logging:** Before starting, queries BQ for `COUNT(*)` of remaining rows. Logs page-level progress: page N of M, rows upserted, elapsed time, estimated remaining.

### Fields Selected from BigQuery

The script selects the same payload fields defined in `processing.schemas.Gold.QDRANT_FIELDS`:

**Embedding text fields** (concatenated as `"name | categories | text"`):
- `name`, `categories`, `text`

**Payload fields** (stored in Qdrant point payload):
- `review_id`, `business_id`, `name`, `city`, `state`, `categories`
- `business_stars`, `review_stars`, `review_count`, `is_open`
- `alcohol`, `noise_level`, `wifi`, `outdoor_seating`, `restaurants_price_range`
- `text`, `date`

## File Changes

| File | Change |
|------|--------|
| `processing/gold.py` | Remove Qdrant imports, sink, `--reset` Qdrant branch. BQ-only. |
| `processing/backfill_qdrant.py` | **New file.** One-shot backfill with bookmark resumability. |
| `processing/sinks/qdrant_sink.py` | Extract `_review_id_to_uuid`, `_build_embedding_text`, `_build_payload` to module-level functions. `BatchSink` calls them instead of its own methods. |
| `processing/sinks/bigquery.py` | No changes. |
| `config/settings.py` | No changes. |
| `CLAUDE.md` | Update architecture diagram, commands, directory structure. |
| `docs/explanation.md` | Append section documenting the decoupling. |

## BQ Query Cost Budget

Single query approach: one full table scan per backfill run. 1M rows × ~17 columns ≈ 2-5GB scanned per run. Even with 10 reruns, total is ~50GB — well within the 1TB/month free quota. The initial `COUNT(*)` query scans only the `review_id` column (~20MB).

## Operational Workflow

```bash
# 1. Run gold layer (BQ-only now, fast)
python -m processing.gold

# 2. After gold finishes, backfill Qdrant
python -m processing.backfill_qdrant

# 3. If backfill crashes, just re-run — resumes from bookmark
python -m processing.backfill_qdrant

# 4. Full reset (clean rerun)
python -m processing.backfill_qdrant --reset
python -m processing.backfill_qdrant
```

## What Does NOT Change

- `processing/sinks/qdrant_sink.py` — `GeminiEmbedder`, `QdrantManager` stay as-is; helper functions extracted to module level (minor refactor, no behavior change)
- `processing/sinks/bigquery.py` — no changes
- Agent layer (`agents/`) — no changes
- Bronze, Silver, reconciliation — no changes
- Schemas (`processing/schemas.py`) — no changes
- Config (`config/settings.py`) — no changes
