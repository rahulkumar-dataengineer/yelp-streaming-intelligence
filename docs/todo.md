# Yelp Streaming Intelligence — Task Tracker

## Phase 4: Silver Layer
- [x] Create `utils/spark_helpers.py` — shared Spark utilities (session, parquet source/sink, shutdown loop)
- [x] Refactor `processing/bronze.py` — replace inline implementations with shared utils
- [x] Add Silver paths to `config/settings.py` (SILVER_OUTPUT, SILVER_CHECKPOINT)
- [x] Create `processing/silver.py` — full cleaning + stream-stream join logic
- [x] Run Bronze → populate Parquet from Redpanda topics
- [x] Run Silver → verify 65-column output with correct types, cleaned attributes, partitioning
- [x] Append Phase 4 documentation to `docs/explanation.md`

## Phase 4.5: Hive Metastore Integration
- [x] Add PostgreSQL + Hive Metastore services to `build/docker-compose.yml`
- [x] Create `build/hive/Dockerfile` — custom image with PostgreSQL JDBC driver
- [x] Add `HiveSettings` to `config/settings.py`, move checkpoint paths to `SparkSettings`
- [x] Add `enableHiveSupport()` + `read_table_stream()` + `start_table_sink()` to `utils/spark_helpers.py`
- [x] Refactor `utils/schema_contract.py` — remove StructType schemas, add DDL classmethods
- [x] Create `utils/metastore_init.py` — enterprise DDL execution (databases + tables)
- [x] Modify `processing/bronze.py` — derive JSON parse schema from metastore, write via `toTable()`
- [x] Modify `processing/silver.py` — read from metastore tables, write via `toTable()`
- [x] Update `docs/explanation.md` and `CLAUDE.md` for metastore architecture
- [x] Verify end-to-end: metastore init → Bronze (40K each) → Silver (40K joined)

## Phase 5: Gold Layer
- [x] Implement `processing/gold.py` — `foreachBatch` streaming structure
- [x] BigQuery Load API integration (`load_table_from_dataframe`, `WRITE_APPEND`)
- [x] Idempotency: dedup VIEW (`gold_reviews_deduped`) + `--reset` CLI flag
- [x] Add `GOLD_CHECKPOINT` to `config/settings.py`
- [x] Verify: 27,573 rows loaded, column types correct, Load API job IDs confirmed
- [x] Extract BQ helpers to `processing/sinks/bigquery.py` with `BatchSink` class
- [x] Create `processing/sinks/qdrant_sink.py` — Gemini embedding + Qdrant upsert with rate limiter + exponential backoff
- [x] Refactor `processing/gold.py` as slim orchestrator delegating to sink modules
- [x] Create `check_sinks.py` — verify both BQ + Qdrant sinks + test similarity search
- [x] `--reset` clears both sinks (BQ table/view + Qdrant collection + checkpoints)
- [x] Verify: 12,477 BQ rows + 7,043 Qdrant vectors, similarity search returns relevant results
- [x] Append Phase 5b documentation to `docs/explanation.md`

## Phase 6: LangGraph Agent System
- [x] Task 1: `agents/__init__.py` + `agents/state.py` — AgentState TypedDict + package init
- [x] Task 2: `agents/router.py` — Gemini classifier (SQL/VECTOR/HYBRID) with thinking_level="minimal", tenacity retry
- [x] Task 3: `agents/sql_agent.py` — ReAct SQL toolkit against BigQuery deduped view, HYBRID business_id extraction
- [x] Task 4: `agents/vector_agent.py` — Function-based Qdrant search with Gemini embeddings, filter extraction, tenacity retry
- [x] Task 5: `agents/synthesizer.py` — Gemini answer generation with routing transparency, tenacity retry
- [x] Task 6: `graph.py` — LangGraph StateGraph wiring + CLI entry point
- [x] Task 7: Verify BigQuery `gold_reviews_deduped` view exists
- [x] Task 8: End-to-end verification (SQL, HYBRID routes verified with live data)
- [x] Task 9: Append agent architecture to `docs/explanation.md`
