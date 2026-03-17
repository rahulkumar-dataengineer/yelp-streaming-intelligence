# Yelp Hybrid Streaming Agentic Platform — Project Documentation

## Phase 0: Infrastructure & Foundation

### What We're Building
A real-time dual-pipeline system that processes the Yelp Open Dataset (~150K businesses, ~7M reviews) through a streaming medallion architecture (Bronze → Silver → Gold), landing data in two complementary sinks: Google BigQuery for structured SQL analytics (ratings, locations, categories) and Qdrant for semantic vector search (review sentiment, vibe, ambiance). A LangGraph multi-agent system routes natural language queries to the appropriate sink — SQL for structured questions ("top-rated Italian restaurants in Phoenix"), vector search for subjective ones ("cozy spot for a rainy evening"), or both for hybrid queries. The entire platform runs on Google's free tier, deployed as a Firebase static website with a Flask agent API on a GCP e2-micro VM.

### Why This Use Case
Yelp data is uniquely suited for demonstrating why hybrid search matters. The dataset contains both highly structured fields (star ratings, GPS coordinates, business categories, operating hours, attributes like WiFi/parking) and deeply unstructured text (millions of free-form reviews expressing subjective experiences). Neither SQL nor vector search alone can serve all query types well:

- **SQL alone** can answer "4+ star Italian restaurants in Phoenix open on Sundays" perfectly, but fails at "find me somewhere with a chill vibe and great pasta" — there's no column for "vibe."
- **Vector search alone** can find semantically similar reviews to "chill vibe and great pasta," but can't efficiently filter by city, star rating, or operating hours — it would search all 7M reviews unnecessarily.
- **The hybrid approach** uses SQL as a precision filter (cheap, exact) and vector search as a semantic ranker (expensive, runs on a smaller filtered set). This mirrors real production architectures where predicate pushdown reduces the search space before expensive operations.

The LLM agent router decides which path to take, demonstrating that the architecture choice isn't just technical — it's about building systems smart enough to pick the right tool for each query.

### The Zero-Cost Constraint
This entire platform runs at $0/month. Every component uses a genuinely free tier — no free trials, no credit-card-required services, no "first 90 days free" offers. This is an intentional engineering constraint that demonstrates resourcefulness and deep understanding of cloud economics:

| Component | Free Tier Used | Key Limits |
|-----------|---------------|------------|
| **Compute** | GCP e2-micro VM (Always Free) | 1 vCPU, 1 GB RAM, 30 GB disk. Must be in us-central1, us-west1, or us-east1. |
| **Analytical DB** | BigQuery Sandbox | 1 TB queries/month, 10 GB storage. No streaming inserts, no DML — Load API only. |
| **Vector DB** | Qdrant (self-hosted on VM) | Open source, no license cost. Uses `on_disk=True` to fit in 1 GB RAM. |
| **LLM** | Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite-preview`, free API tier) | Preview-tier RPM/RPD limits (check AI Studio). Two calls per query (router + synthesizer). |
| **Embeddings** | Gemini `gemini-embedding-001` (free tier) | 100 RPM, 1000 requests/day. 768-dim via Matryoshka (reduced from 3072). |
| **Frontend** | Firebase Hosting (Spark plan) | 1 GB storage, 10 GB transfer/month. Static files only — no Cloud Functions. |
| **Message Broker** | Redpanda (local Docker) | Open source, Kafka-compatible. Dev-only, not deployed to cloud. |
| **Stream Processing** | PySpark Structured Streaming | Open source, runs locally during data processing. |
| **CDN** | Cloudflare (free plan) | Shields VM from direct egress (1 GB/month GCP limit). Free SSL. |

The 1 GB RAM constraint on the VM is the tightest bottleneck: Qdrant gets ~400 MB (with on-disk storage), the Flask API gets ~300 MB, and the OS/nginx gets ~200 MB. This forces disciplined resource allocation — no bloated frameworks, no in-memory models, no unnecessary dependencies.

### Infrastructure Decisions

**What was validated:**
- **BigQuery**: Connected successfully. Project `yelp-streaming-intelligence`, dataset `yelp_analytics` exists (empty, ready for Gold layer data). Queries work. Sandbox mode confirmed — Load API available, streaming inserts blocked.
- **Firebase CLI**: Installed (v15.9.1). Two existing projects found. A new Firebase project needs to be created for this project on the Spark (free) plan.
- **Docker**: Installed (v29.2.1) but daemon not running. Required for Redpanda during local development.
- **Python**: 3.11 via pyenv (virtualenv `yelp-streaming-3-11`).
- **Yelp Data**: Both files present — `yelp_academic_dataset_business.json` (119 MB) and `yelp_academic_dataset_review.json` (5.3 GB).

**What needs setup before proceeding:**
1. **Gemini API Key** — current key is invalid/revoked. Must generate a new one at aistudio.google.com.
2. **GCP VM + Qdrant** — no VM exists yet. Need to create an e2-micro instance in an Always Free region and deploy Qdrant via Docker.
3. **Firebase project** — need to create a project linked to `yelp-streaming-intelligence` on the Spark plan.
4. **Docker Desktop** — needs to be started for local Redpanda development.
5. **gcloud CLI** — not installed. Required for VM creation and management.

**What needs to change in existing code (from prior iteration):**
The codebase was previously built with Pinecone (vector DB) and sentence-transformers (local embeddings). Per the updated architecture:
- Pinecone → Qdrant (self-hosted, zero cost, no credit card)
- sentence-transformers/MiniLM-L6-v2 (384-dim, 256 token limit) → Gemini Embedding API (768-dim, 2048 token input, state-of-the-art quality)
- Single Kafka topic (pre-joined) → Dual topics (`yelp_businesses` + `yelp_reviews`) for proper stream-stream join in Silver layer
- Streamlit → Firebase Hosting (static) + Flask API
- Monolithic `spark_stream.py` → Medallion layers: `bronze.py`, `silver.py`, `gold.py`

## Phase 1: Docker Infrastructure & Schema Contracts

> **Note:** The schema architecture described in this phase was later restructured in Phase 4.6 (enterprise team separation) and Phase 5 (Avro enforcement). Docker infrastructure was consolidated into the shared `portfolio-platform-commons` library. See those phases for the current design.

### Docker Infrastructure (Redpanda)
Redpanda runs as a single-broker Kafka-compatible cluster in Docker for local development. Docker Compose services are defined in the shared `portfolio-platform-commons` library and include:

- **Redpanda broker** (port 9092): Kafka-compatible message broker with separate internal (9093) and external (9092) listeners. Runs in `dev-container` mode with `--smp 1` and `--memory 512M` to stay lightweight on a dev machine. Schema registry is bound to non-default ports (18081/18082) to avoid conflicts with other local services.
- **Redpanda Console** (port 8080): Web UI for topic inspection, consumer group monitoring, and message browsing. Depends on the broker's healthcheck passing before starting.

Neither service is deployed to the GCP VM — Redpanda is for local development only. The VM runs Qdrant + Flask API via a separate `vm-docker-compose.yml`.

### Schema Contract Design
All Spark schemas live in a single file: `utils/schema_contract.py`. This is the **schema-as-contract** pattern borrowed from enterprise data engineering — every processing module imports its schema from one source of truth. If a field is renamed or removed, downstream modules fail at import time rather than silently producing corrupt data at runtime.

**Class-as-namespace pattern:** The file uses Python classes as namespaces to visually group field constants by layer: `BronzeBusiness`, `BronzeReview`, `Silver`, `Gold`. This makes field ownership immediately clear — `BronzeBusiness.NAME` vs `Silver.BUSINESS_STARS` — and shows data lineage at a glance. The Silver schema references both `BronzeBusiness.CITY` (unchanged field carried through) and `Silver.BIKE_PARKING` (new field introduced by Silver), so you can see provenance without reading transformation code. Schemas are attached after class definitions (`BronzeBusiness.SCHEMA = StructType(...)`) due to Python 3's class-body comprehension scoping limitation.

**Why Bronze is all-string:** The Bronze layer preserves raw data exactly as it arrives from Kafka. Every field is `StringType`, including numbers, booleans, and timestamps. This guarantees zero data loss from type coercion — if a `stars` field occasionally contains `"N/A"` instead of `"4.5"`, Bronze stores it faithfully. Cleaning and casting happen in Silver, where data quality rules are explicit and logged. Bronze has two separate schemas: `BronzeBusiness.SCHEMA` (58 fields: 12 top-level + 37 raw CamelCase attributes + 7 hours + 2 metadata) and `BronzeReview.SCHEMA` (11 fields). The two entities are kept independent — shared fields like `business_id` and `stars` are defined in both classes, so adding a new entity (BronzeCheckin, BronzeTip) never touches existing ones.

**What Silver produces (65 fields):** The Silver layer performs a stream-stream inner join on `business_id` between Bronze businesses and Bronze reviews. The output is a denormalised record with:
- Typed business fields (FloatType for stars, IntegerType for review_count, BooleanType for is_open). Latitude/longitude removed — users query by city/state in the chat interface, not coordinates.
- 20 boolean attributes normalised from mixed `'True'`/`'False'`/`None` strings (bike_parking, caters, outdoor_seating, good_for_kids, etc.)
- 5 parking booleans flattened from the `BusinessParking` nested dict string (garage, street, validated, lot, valet)
- 7 music booleans flattened from the `Music` nested dict string (dj, background, no_music, jukebox, live, video, karaoke)
- 5 string attributes with `u'...'` prefix stripped (alcohol, noise_level, restaurants_attire, smoking, wifi)
- 1 integer attribute (restaurants_price_range)
- 7 hours fields with `"0:0-0:0"` (closed) converted to null
- Typed review fields with renamed conflicts (`business_stars` as FloatType vs `review_stars` as IntegerType — business stars have 0.5 increments as averages, review stars are whole numbers 1–5)
- Ingestion metadata: `ingestion_timestamp` (TimestampType) and `ingestion_date` (DateType) carried forward from Bronze

**How Gold branches for BigQuery vs Qdrant:**
- **BigQuery** receives ALL 65 Silver fields (`Gold.BIGQUERY_SCHEMA = Silver.SCHEMA`). With 10 GB free storage, excluding fields only limits SQL query richness for zero cost savings. The `BIGQUERY_FIELDS` list is dynamically derived from `Silver.SCHEMA.fields`, so any future Silver field additions automatically flow into BigQuery with no manual sync. The `review_id` serves as the dedup key.
- **Qdrant** receives a lean payload of 17 fields designed for the 1 GB RAM VM constraint. Embedding text is constructed by concatenating business name + categories + review text for rich semantic content. The payload includes identity fields (review_id, business_id), business context (name, city, state, categories), quality signals (business_stars, review_stars, review_count, is_open), vibe/ambiance attributes (alcohol, noise_level, wifi, outdoor_seating, restaurants_price_range), and review content (text, date). Fields like individual parking/music booleans are excluded — semantic search on review text already captures "great parking" or "live music" more naturally than boolean filters. The `review_id` is hashed to a UUID for the Qdrant point ID.

This dual-sink design means a single streaming query (Gold `foreachBatch`) fans out to both destinations independently — if BigQuery fails, Qdrant still succeeds, and vice versa. The schema contract ensures both branches always agree on field names and types.

## Phase 2: Data Ingestion

### Data Ingestion Design

The ingestion layer converts the static Yelp Open Dataset into a live stream flowing through Redpanda (Kafka-compatible broker) — the entry point for the entire medallion pipeline.

**Line-by-line generators (not pandas, not Spark):** Both data loaders (`ingestion/data_loader.py`) stream newline-delimited JSON files one line at a time using `json.loads`, yielding one dict per record via Python generators. This gives constant memory overhead regardless of file size — critical for the 5.3 GB review dataset (~7M rows). Spark is designed for distributed stream processing, not one-time file reads. Pandas would work but requires either loading everything into memory or managing chunked iterators. Raw `json.loads` with generators is the simplest approach: zero dependencies, zero memory scaling, and each record is immediately available for Kafka production.

**Iterative flattening for businesses:** The Yelp business JSON has nested objects (`attributes: {BikeParking: "True", ...}` and `hours: {Monday: "11:0-21:0", ...}`). An iterative `_flatten()` function uses a stack to flatten nested dicts into underscore-separated keys (`attributes_BikeParking`, `hours_Monday`) that directly match the Avro schema field names. Underscores avoid the ambiguity of dots in Spark column names (where dots normally mean nested struct access). Reviews have no nested structures and skip flattening.

**String coercion at the boundary:** `_clean_record()` coerces all non-None values to `str` before they reach the Avro serializer. The Avro schemas define all fields as `["null", "string"]` (the Bronze all-string principle), but `json.loads` returns native Python types (`float` for `stars`/`latitude`, `int` for `review_count`). The serializer rightfully rejects type mismatches — coercion at the data loader boundary is the correct fix. `NaN` and empty strings are mapped to `None`.

**Avro serialization via `confluent-kafka[avro]`:** The producer (`ingestion/producer.py`) uses `confluent-kafka`'s `SerializingProducer` with `AvroSerializer` — the industry-standard Kafka serialization stack. Each topic gets its own producer instance bound to its schema (business: 56 fields, review: 9 fields) via the shared `schemas/` package. Messages use Confluent wire format (1 magic byte + 4-byte schema ID + Avro payload), which enables server-side schema validation and efficient binary encoding. Producer creation and topic production are delegated to `platform_commons.kafka` helper functions.

**Threaded producer (parallelism):** The producer runs one thread per topic — `yelp_businesses` and `yelp_reviews` — sending records simultaneously. Since businesses are faster to load and fewer (150K vs 7M), the business thread finishes well before the review thread. Threading keeps the business topic populated early so the Bronze layer can start consuming immediately, without waiting for the slower review loading. Each thread gets its own `SerializingProducer` instance (required because each is bound to a different Avro schema). Graceful shutdown is coordinated through `platform_commons.kafka.register_signal_handlers()`, and both threads are daemonized so KeyboardInterrupt cleanly terminates the process after flushing producer buffers.

**Why `business_id` as Kafka key (co-partitioning):** Every message on both topics is keyed by `business_id` (UTF-8 encoded). Kafka's default partitioner hashes the key to determine the target partition. Since both topics use the same key, all reviews for a given business land on the same partition number as that business's record. This is the **co-partitioning** pattern — an enterprise prerequisite for stream-stream joins. In the Silver layer, PySpark performs a stream-stream inner join on `business_id` between the two topics. If records weren't co-partitioned, the join would require an expensive cross-partition shuffle. With co-partitioning, each Spark task can join records locally within its assigned partition, dramatically reducing network I/O and memory usage. For a single-partition local dev setup (Redpanda default), co-partitioning is trivially satisfied. In a production multi-partition deployment, the same key-based partitioning would scale correctly without code changes.

**Verified behaviour:** Both topics confirmed active in Redpanda with valid Avro-encoded messages. Business messages contain all top-level fields plus flattened `attributes_*` (37 attributes) and `hours_*` (7 days). Review messages contain 9 fields: `review_id`, `user_id`, `business_id`, `stars`, `useful`, `funny`, `cool`, `text`, `date`. Full business run completed: **150,346 records sent, 0 errors**. Review streaming verified at 270K+ records before intentional SIGTERM — throughput ~10K records/sec. Consumer verification confirmed proper `business_id` keying, Avro deserialization, and correct field counts from both topics.

## Phase 3: Bronze Layer (Raw Persistence)

### What Was Built
The Bronze layer (`processing/bronze.py`) runs two independent PySpark Structured Streaming queries that consume from Redpanda topics (`yelp_businesses` and `yelp_reviews`), deserialize Avro payloads (stripping the 5-byte Confluent wire format header via `from_avro()`), and write to Hive-managed Bronze tables partitioned by `ingestion_date`. It performs zero data transformation — all fields remain as `StringType`, preserving raw data exactly as it arrived from the producer.

### Architecture Decisions

**Two independent queries, not one:** Each topic gets its own streaming query with its own checkpoint. This means the business stream and review stream operate at independent speeds — businesses (150K records) complete long before reviews (7M records). If they shared a single query, we'd need complex multi-topic parsing logic and couldn't checkpoint independently. Separate queries also mean a failure in one doesn't affect the other's progress.

**Metadata enrichment:** Bronze adds `ingestion_timestamp` (via Spark's `current_timestamp()`) and `ingestion_date` (derived via `to_date()`) to each record, reflecting when records were *processed* by the Bronze layer. All records in the same micro-batch share the same timestamp, ensuring consistent metadata. The original Kafka message timestamp is available via Kafka's built-in message metadata if latency analysis is needed.

**Backpressure via `maxOffsetsPerTrigger`:** Without this, the first trigger would attempt to consume all 7M review messages at once, likely exceeding driver memory. Setting it to 10,000 per trigger keeps each micro-batch at a predictable size (~10K records), matching the producer's chunk size and keeping memory usage stable.

**All-StringType persistence:** Bronze stores every field as a string, including numbers (`stars`, `review_count`), booleans (`is_open`), and timestamps. This guarantees zero data loss from type coercion — a `stars` field containing `"N/A"` is stored faithfully rather than failing or becoming null. Type casting and validation are Silver's responsibility.

**Partitioning by `ingestion_date`:** Creates Hive-style directories (`ingestion_date=2026-03-13/`) enabling partition pruning in Silver. For the initial historical load, all records share the same date (today). In production with daily incremental loads, this partitioning provides efficient time-bounded reads.

**Graceful shutdown:** Signal handlers (SIGINT/SIGTERM) set a shared boolean flag. The main loop polls this flag every 5 seconds. On shutdown, each query finishes its current micro-batch before stopping — no data is lost or partially written. Checkpoints are committed, so restarting resumes from exactly where processing left off.

### How It Runs
```bash
# Prerequisites: Redpanda running, topics populated
python -m processing.bronze
# Ctrl+C to stop gracefully (finishes current micro-batch, commits checkpoint)
```

Bronze writes to Hive-managed tables (`bronze.businesses` and `bronze.reviews`) as Parquet in `spark-warehouse/`, partitioned by `ingestion_date`. Checkpoints are stored in `checkpoints/bronze/{businesses,reviews}/` — on restart, processing resumes from the last committed offset.

## Phase 4: Silver Layer (Cleaned, Typed, Joined)

### What Was Built
The Silver layer (`processing/silver.py`) reads Bronze Hive tables for both businesses and reviews as streaming sources, applies all data cleaning and type casting, performs a stream-stream inner join on `business_id`, and writes a 65-column typed Hive table (`silver.reviews`) partitioned by `state` and `ingestion_date`. This is the most transformation-heavy step in the pipeline — it takes raw StringType data and produces a fully typed, denormalised dataset ready for the Gold sinks.

### Shared Utilities Extraction
Before building Silver, common Spark patterns were extracted from Bronze into `utils/spark_helpers.py`:
- **`create_spark_session()`** — configurable app name, optional JAR packages (Kafka + Avro for Bronze), Hive support enabled
- **`read_table_stream()`** — streaming read from Hive metastore tables
- **`start_table_sink()`** — streaming write to Hive tables via `toTable()` with partitioning and checkpointing
- **`run_until_shutdown()`** — polling loop with signal-based graceful shutdown

Bronze was refactored to use these utilities, eliminating ~60 lines of duplicated boilerplate. Silver, and eventually Gold, import the same functions — ensuring consistent behaviour across all three layers (same shuffle partitions, same trigger patterns, same shutdown semantics).

### Stream-Stream Join Design

**Why a stream-stream join (not batch):** The pipeline is designed for production-style incremental processing. When new reviews arrive via Kafka, they flow through Bronze as new Parquet files. Silver's streaming file source detects them and joins against the business stream automatically. A batch join would require re-reading all business data on every run; the stream-stream join holds business records in Spark's state store and matches reviews as they arrive.

**Watermark strategy (24 hours):** Spark requires watermarks on both sides of a stream-stream join to bound state and determine when late data can no longer arrive. The 24-hour window is deliberately generous because:
1. For the initial historical load, all Bronze records share the same `ingestion_timestamp` (today). A tight watermark would work fine here.
2. In a production scenario with daily incremental loads, a 24-hour window accommodates late-arriving data (e.g., a delayed review batch) without dropping records.
3. The trade-off is state size — Spark must hold unmatched records in memory until the watermark advances past the 24-hour window. With 150K businesses (~small) and reviews arriving continuously, the business side of state fills quickly and reviews match immediately, keeping memory usage bounded.

**Join semantics (inner):** Only reviews with matching businesses produce Silver records. Reviews for unknown businesses (data quality issue in the source dataset, or businesses not yet ingested) are silently dropped. This is intentional — downstream consumers (BigQuery SQL, Qdrant vector search) expect every review to have complete business context (name, city, categories, attributes).

**Column conflict resolution:** Both streams have `business_id` and `ingestion_timestamp`. After the join:
- `business_id` is taken from the business side (identical due to join condition)
- `ingestion_timestamp` is the `greatest()` of both sides — the joined record is only complete when both the business and its review have been processed
- `ingestion_date` is derived from this merged `ingestion_timestamp` via `to_date()`

### Data Cleaning — The Yelp Dataset's Quirks

The Yelp Open Dataset stores attribute values in ways that reflect its evolution over time. The same logical field appears in multiple serialisation formats depending on when the business was last updated:

**Nested dict strings (BusinessParking, Music):** Attributes like `BusinessParking` contain Python dict literals as strings:
```
"{'garage': False, 'street': True, 'validated': False, 'lot': False, 'valet': False}"
"{u'valet': False, u'garage': None, u'street': None, u'lot': None, u'validated': False}"
"None"
```
The `u'...'` prefix is a Python 2 unicode string artifact — Yelp's ingestion pipeline apparently used Python 2 at some point. Some records have partial dicts (e.g., `{'dj': False}` with only one key). The whole field can also be the string `"None"` meaning no parking data at all.

**Solution:** A PySpark UDF using `ast.literal_eval` — Python's built-in parser for Python literals. It handles `u'...'` prefixes, mixed `True`/`False`/`None` values, and partial dicts natively. The UDF parses the dict once into a `MapType(StringType(), BooleanType())`, then individual keys are extracted from the map. Missing keys naturally return Spark null. This approach is deterministic and avoids fragile regex patterns.

BusinessParking → 5 boolean columns (`parking_garage`, `parking_street`, `parking_validated`, `parking_lot`, `parking_valet`). Music → 7 boolean columns (`music_dj`, `music_background`, `music_no_music`, `music_jukebox`, `music_live`, `music_video`, `music_karaoke`). Note: the source key `background_music` maps to Silver's `music_background` — the mapping is defined in a data-driven tuple list to keep the code maintainable.

**String attributes with wrapper artifacts (Alcohol, NoiseLevel, WiFi, Smoking, RestaurantsAttire):** Values appear as `"u'full_bar'"`, `"'none'"`, or `"None"`. A second UDF using `ast.literal_eval` cleanly strips these wrappers: `ast.literal_eval("u'full_bar'")` → `"full_bar"`, `ast.literal_eval("None")` → Python `None` → Spark null.

**Simple boolean attributes (20 fields like BikeParking, GoodForKids, Caters):** Stored as string `"True"`, `"False"`, or `"None"`. A pure Spark `when` chain maps these to actual `BooleanType` — no UDF needed.

**Hours sentinel value:** The value `"0:0-0:0"` means the business is closed on that day. Silver converts this to null — downstream queries can filter on `hours_monday IS NOT NULL` to find businesses open on Mondays.

**Stars rename:** Both businesses and reviews have a `stars` field. Business stars are averages with 0.5 increments (1.0, 1.5, ..., 5.0) → `business_stars` as `FloatType`. Review stars are whole numbers (1-5) → `review_stars` as `IntegerType`. The rename makes the distinction explicit in the Silver schema.

### Data-Driven Mapping Architecture

To avoid 44+ repetitive `withColumn` calls, all attribute transformations are defined as mapping tables — lists of `(bronze_column, silver_column)` tuples:
- `_BOOLEAN_ATTR_MAP`: 20 simple boolean attributes
- `_PARKING_KEY_MAP`: 5 BusinessParking dict keys
- `_MUSIC_KEY_MAP`: 7 Music dict keys
- `_STRING_ATTR_MAP`: 5 string attributes with wrapper artifacts
- `_HOURS_MAP`: 7 day-of-week hours

Each mapping is applied in a loop with the appropriate cleaning function. Adding a new attribute to Silver requires only: (1) add the field constant to the `Silver` class in `processing/schemas.py`, (2) add the DDL column to `infra/hive_ddl.py`, and (3) add one tuple to the relevant mapping list. No transformation code changes needed.

### Verified Behaviour
Silver successfully processes Bronze Parquet and produces 65-column output partitioned by `state` + `ingestion_date`. Verified on 50,000 joined records across 8,026 distinct businesses and 17 states:
- **Types correct:** `business_stars` is FloatType (0.5 increments), `review_stars` is IntegerType (1-5), `is_open` is BooleanType, `date` is TimestampType
- **Booleans are actual booleans:** `bike_parking`, `good_for_kids`, etc. are `True`/`False`/`None` — not strings
- **Parking/Music dict extraction works:** All 12 dict-extracted booleans have correct `True`/`False`/`None` values including handling of partial dicts and `u'...'` keys
- **String attrs cleaned:** `alcohol` shows `full_bar`, `none`, `beer_and_wine` — no `u'...'` or `'...'` wrappers
- **Hours cleaned:** Zero `"0:0-0:0"` values in any hours column (all converted to null)
- **No latitude/longitude:** Dropped as designed — users query by city/state in the chat interface

### How It Runs
```bash
# Prerequisites: Bronze Parquet populated
python -m processing.silver
# Ctrl+C to stop gracefully
```

Silver writes to the Hive-managed table `silver.reviews`, partitioned by `state` and `ingestion_date`. Checkpoints at `checkpoints/silver/` — restarting picks up where processing left off, including stream-stream join state.

### Schema Management: Hive Metastore as Centralised Catalog

**The enterprise landscape:** In production Spark environments, schemas are managed by a centralised catalog — a metadata service that stores table definitions, column types, partition layouts, and statistics separately from the data files:

| Catalog | Used By | What It Provides |
|---------|---------|------------------|
| **Hive Metastore** | Traditional Spark/Hadoop shops | MySQL/Postgres-backed schema registry. `spark.sql("SELECT * FROM silver.reviews")` resolves table location, schema, and partitions automatically. |
| **Unity Catalog** | Databricks | Hive Metastore successor with RBAC, lineage tracking, cross-workspace governance. |
| **AWS Glue Data Catalog** | AWS-native stacks | Managed Hive-compatible metastore. Integrates with Athena, EMR, Redshift Spectrum. |
| **Confluent Schema Registry** | Kafka-centric architectures | Stores Avro/Protobuf/JSON schemas for Kafka topics. Enforces compatibility on schema evolution. |
| **Apache Iceberg / Delta Lake catalogs** | Modern lakehouse architectures | Table-format-level schema management with ACID transactions, time travel, and schema evolution. |

**What we implemented:** A PostgreSQL-backed Hive Metastore running as a Docker service alongside Redpanda. This is the enterprise-standard approach — the metastore is the single source of truth for all table schemas, locations, and partition layouts. Every SparkSession connects to the metastore on port 9083 via the Thrift protocol. PostgreSQL was chosen over MySQL because the Apache Hive 4.0 Docker image bundles the PostgreSQL JDBC driver natively, avoiding manual driver JAR management.

**Why PostgreSQL, not Derby:** The simplest Hive Metastore uses Apache Derby as its embedded database. Derby is single-process — only one JVM can connect at a time. Since Bronze and Silver run as separate Python processes (separate JVMs), Derby would prevent running them simultaneously. PostgreSQL supports concurrent connections, enabling the full multi-process streaming pipeline that enterprise Spark shops require.

**Architecture — DDL-as-contract pattern:**
```
schema_contract.py          metastore_init.py           Processing layers
(DDL definition)     →      (DDL execution)      →     (read/write via table names)

BronzeBusiness.ddl()        init_metastore(spark)       read_table_stream("bronze.businesses")
BronzeReview.ddl()          CREATE DATABASE IF NOT      start_table_sink("silver.reviews")
Silver.ddl()                EXISTS bronze/silver/gold
```

This mirrors enterprise separation of concerns: schema definitions live in `schema_contract.py` (analogous to migration files in Flyway/Alembic), execution happens in `metastore_init.py` (analogous to running migrations), and processing layers only perform DML (SELECT/INSERT) against registered tables. Field name constants (`Silver.BIKE_PARKING`, etc.) remain in `schema_contract.py` to prevent string literal typos in Python transformation code.

**Why managed tables:** Tables are created with `USING PARQUET` and no explicit `LOCATION` — the metastore controls where Parquet files are stored (in `spark-warehouse/`). This is the cleaner enterprise pattern: the metastore fully owns the data lifecycle. Processing layers reference table names (`bronze.businesses`, `silver.reviews`), never file paths. The alternative — external tables with explicit `LOCATION` — is more common in data lake architectures where multiple tools (Spark, Presto, Hive) share the same data, but adds path management complexity we don't need.

**What the metastore replaces:**
- Python `StructType` schemas → SQL DDL in `schema_contract.py` classmethods
- `read_parquet_stream(path, schema)` → `read_table_stream(table_name)` — metastore provides both path and schema
- `start_parquet_sink(path)` → `start_table_sink(table_name)` — writes via `toTable()`
- Manual partition column filtering (the `exclude ingestion_date from read schema` hack) → automatic partition handling by the metastore

**Metastore lifecycle:** The metastore only runs locally during data processing (Bronze → Silver → Gold). It does not deploy to the GCP VM. End users query BigQuery and Qdrant through the Flask API — neither sink requires the metastore at query time. Once Gold finishes pushing data to both sinks, the entire local infrastructure (Redpanda, PostgreSQL, Hive Metastore) can be shut down with no impact on the live application.

**Avro parse schema:** Bronze uses `from_avro()` (from `pyspark.sql.avro.functions`) to deserialize Kafka messages. The Avro schema JSON strings are defined in `processing/schemas.py` (derived from the canonical `.avsc` files in the `schemas/` package). This keeps schema definitions DRY — the `.avsc` files are the single source of truth, and `processing/schemas.py` converts them to the JSON strings that PySpark's `from_avro()` requires.

### Phase 4.6: Enterprise Team Boundary Separation

> **Note:** The intermediate file layout described below (`infra/schema_contract.py`, `infra/metastore_init.py`, `infra/schema_registry.py`) was later consolidated in Phase 5 (Avro enforcement). In the current codebase, Avro schemas live in the `schemas/` package as `.avsc` files, DDL lives in `infra/hive_ddl.py`, and shared infrastructure functions (metastore init, schema registration) are in the `portfolio-platform-commons` library. The team boundary principle described here remains in effect.

#### What Was Built
The codebase was restructured to mirror how enterprise data teams actually operate — with clear ownership boundaries between the platform team (infrastructure provisioning) and the data engineering team (pipeline code). Three files were moved from `utils/` to a new `infra/` package, a unified provisioning entry point was created, and the processing layer was given its own independent schema definitions.

#### Why This Restructuring Matters
In enterprise environments, the platform/infrastructure team and the data engineering team are separate organisations with different responsibilities:

- **Platform team** owns schema registry registration, metastore DDL creation, and infrastructure provisioning. They define the "contract" — what tables exist, what schemas are registered — and run provisioning scripts independently.
- **Data engineering team** owns the streaming pipelines. They write Bronze/Silver/Gold processing code, define their own runtime schemas (StructType for Kafka parsing, field constants for transformations), and never touch infrastructure provisioning code.
- **Producing team** owns message production. They send data to Kafka topics and don't concern themselves with downstream schema registration or table creation.

Previously, these concerns were mixed: `bronze.py` called `init_metastore()`, `producer.py` called `register_schemas()`, and everyone imported from the same `utils/schema_contract.py`. This made it impossible to tell what belonged to which team.

#### The Hybrid Schema Approach
The restructuring uses independent schema definitions rather than a shared contract:

- **`infra/schema_contract.py`** — the platform team's schema definitions. Contains StructType schemas with DDL generation (`ddl()` classmethods) and JSON Schema generation (`json_schema()` classmethods) for the Redpanda schema registry. Used exclusively by `infra/metastore_init.py` and `infra/schema_registry.py`.

- **`processing/schemas.py`** — the data engineer's own schema definitions. Contains Bronze Avro JSON strings (for `from_avro()` deserialization), table name constants, Silver field name constants (30+ renamed/cleaned fields), and Gold field selections (BigQuery + Qdrant). No DDL generation — just what the pipeline code needs at runtime.

This mirrors enterprise reality: schema registry schemas (JSON/Avro), metastore DDL (SQL), and application code schemas (StructType/dataclass) are defined separately by different teams. They describe the same data but serve different purposes and are maintained independently.

#### What Changed

| Component | Before | After |
|-----------|--------|-------|
| `utils/schema_contract.py` | Shared by everyone | Moved to `infra/schema_contract.py` — platform team only |
| `utils/metastore_init.py` | Called by Bronze/Silver on startup | Moved to `infra/metastore_init.py` — run once via `python -m infra` |
| `utils/schema_registry.py` | Called by producer on startup | Moved to `infra/schema_registry.py` — run once via `python -m infra` |
| `processing/schemas.py` | Did not exist | NEW — data engineer's own StructType + field constants |
| `infra/__main__.py` | Did not exist | NEW — unified provisioning: schema registry (HTTP, non-fatal) then metastore (Spark, fatal) |
| `processing/bronze.py` | Imported from `utils.schema_contract`, called `init_metastore()` | Imports from `processing.schemas`, no infra calls |
| `processing/silver.py` | Imported from `utils.schema_contract`, called `init_metastore()` | Imports from `processing.schemas`, no infra calls |
| `ingestion/producer.py` | Called `register_schemas()` on startup | Just produces messages — no infra calls |

#### Dependency Rule
```
infra/schema_contract.py         ← platform team's schema definitions
  ↑
infra/metastore_init.py          ← infra uses infra's own schemas
infra/schema_registry.py         ← infra uses infra's own schemas

processing/schemas.py            ← data engineer's OWN schemas (independent)
  ↑
processing/bronze.py             ← app uses app's own schemas
processing/silver.py             ← app uses app's own schemas

processing/ ✗→ infra/            (NEVER)
ingestion/  ✗→ infra/            (NEVER)
```

#### Enterprise Workflow
```bash
# Platform team provisions (once, or on schema changes):
python -m infra

# Producing team:
python -m ingestion.producer

# Data engineering team:
python -m processing.bronze
python -m processing.silver
python -m processing.gold
```

#### Key Simplification
With `processing/schemas.py` defining parse schemas directly (data fields only, no metadata columns), Bronze no longer needs the `_parse_schema()` function that filtered metadata fields out of the metastore schema. The parse schema is defined exactly as the Kafka JSON looks — cleaner and more intuitive.

## Phase 5: Enterprise Schema Enforcement (Avro + Server-Side Validation + Compatibility)

### What Was Built
The schema registry was upgraded from advisory-only (JSON Schema, no enforcement) to a full enterprise enforcement layer with three capabilities:

1. **Avro serialization on the wire** — messages are now Avro-encoded using `confluent-kafka`'s `AvroSerializer` with the Confluent wire format (1 magic byte + 4-byte schema ID + Avro payload). Schema violations are caught at the producer before messages reach the broker.
2. **Server-side schema validation** — Redpanda rejects any message whose value doesn't conform to the registered schema (`redpanda.value.schema.id.validation=true` on each topic). Even rogue producers that bypass the serializer are caught at the broker level.
3. **BACKWARD compatibility mode** — set on each registry subject. New schemas can read data written with the old schema, but not vice versa. This is the Kafka ecosystem default — consumers are always ahead of or at the same version as producers.

### Why This Matters

In the previous architecture, the schema registry was metadata-only: schemas were registered as JSON Schemas for documentation, but neither the producer nor Redpanda validated messages against them. A producer bug (wrong field names, missing fields, type mismatches) would silently flow through to Bronze, where PySpark's `from_json()` would either drop unknown fields or null-out missing ones — silent data loss.

Enterprise Kafka deployments use schema enforcement as a critical data quality gate. The three layers provide defence in depth:

| Layer | What It Catches | Failure Mode |
|-------|----------------|--------------|
| **AvroSerializer** (producer-side) | Schema mismatch at serialization time | `SerializationError` — message never sent |
| **Server-side validation** (broker-side) | Rogue producers bypassing the serializer | Redpanda rejects the message (produce request fails) |
| **BACKWARD compatibility** (registry-side) | Breaking schema changes | Schema registration fails — can't deploy the new schema |

### Architecture Decisions

**Why `confluent-kafka[avro]` (not `kafka-python-ng` + `fastavro`):** The previous producer used `kafka-python-ng` with plain `json.dumps()` serialization. Two approaches were considered:

1. **Keep `kafka-python-ng`, add `fastavro`** — implement Confluent wire format manually (5-byte header prepended to Avro bytes), write a custom schema registry client using HTTP.
2. **Switch to `confluent-kafka[avro]`** — use `SerializingProducer` + `AvroSerializer` + `SchemaRegistryClient`, which handle wire format, schema ID caching, and registry interaction automatically.

Option 2 was chosen because `confluent-kafka` is the industry standard — every enterprise Kafka shop (Confluent, AWS MSK, Redpanda Cloud) uses it or its JVM equivalent. The wire format is a solved problem; reimplementing it with `fastavro` would demonstrate protocol knowledge but add maintenance burden for no functional benefit. `confluent-kafka` is open-source (Apache 2.0), free, and built on `librdkafka` (battle-tested C library).

**Why Avro (not Protobuf or JSON Schema):** Avro is the Kafka ecosystem standard for schema-enforced serialization. It has first-class support in Confluent's SerDe libraries, compact binary encoding (no field names on the wire — just values), and built-in schema evolution with compatibility rules. Protobuf is an excellent alternative (better for cross-language services), but the tooling integration with `confluent-kafka` and PySpark is more mature for Avro. JSON Schema enforcement is possible but lacks binary encoding efficiency.

**Why all fields are nullable `["null", "string"]`:** The Yelp dataset has heavy null prevalence — most attribute fields are null for most businesses. Avro requires explicit null unions for nullable fields. Making every field nullable with `default: null` ensures that:
- Records with missing fields serialize without error
- Schema evolution can add new optional fields without breaking existing data
- The Bronze layer's all-StringType principle is preserved (Avro stores the string values, Bronze doesn't type-cast)

**Shared schema repository pattern:** The Avro schemas are needed by three independent modules: `infra/` (registration), `ingestion/` (serialization), `processing/` (deserialization). The team boundary rule says `processing/` and `ingestion/` never import from `infra/`. The solution is the `schemas/` package — a shared schema artifact containing `.avsc` files loaded via `platform_commons.kafka.load_avsc()`. All teams import from `schemas`. In an enterprise org, this would be a separate git repo (a "schema repository") consumed as a versioned package via Artifactory or a private PyPI registry. Here, the `schemas/` package serves that role.

**PySpark Avro deserialization with header stripping:** PySpark's `from_avro()` (from `pyspark.sql.avro.functions`) expects raw Avro bytes, but Kafka messages include the 5-byte Confluent wire format header. Bronze strips this with `expr("substring(value, 6)")` (1-indexed, skips bytes 1-5) before passing to `from_avro()`. This is the standard approach documented in Databricks and Confluent's PySpark integration guides.

**One `SerializingProducer` per topic:** Unlike `kafka-python-ng` where one producer handles all topics, `confluent-kafka`'s `SerializingProducer` is bound to a single `AvroSerializer` (and thus a single schema). The producer creates two instances — one for businesses (55-field schema) and one for reviews (9-field schema). Each thread gets its own producer. This is the correct pattern: in enterprise deployments, producers are typically dedicated to a single topic/schema for clarity and error isolation.

### What Changed

| File | Before | After |
|------|--------|-------|
| `requirements.txt` | `kafka-python-ng==2.2.3` | `confluent-kafka[avro]==2.6.1` |
| `schemas/` package | Did not exist | `.avsc` files + `__init__.py` — canonical Avro schema dicts (shared across all teams) |
| `infra/` | `schema_contract.py` with `json_schema()` + `schema_registry.py` with raw HTTP | Consolidated into `infra/__main__.py` + `infra/hive_ddl.py`; schema registration via `platform_commons.kafka.register_all()` with `SchemaRegistryClient` + BACKWARD compatibility + topic validation |
| `ingestion/producer.py` | `KafkaProducer` + `json.dumps()` | `SerializingProducer` + `AvroSerializer` + delivery callbacks |
| `processing/schemas.py` | StructType parse schemas only | Added `BUSINESS_AVRO_JSON` / `REVIEW_AVRO_JSON` for `from_avro()` |
| `processing/bronze.py` | `from_json(col("value"), schema)` | `from_avro(expr("substring(value, 6)"), avro_json)` + `spark-avro` package |
| `tests/validate_connections.py` | `from kafka import KafkaConsumer` | `from confluent_kafka.admin import AdminClient` |

### Gotchas
- **Delete `checkpoints/bronze/`** before first Avro run — existing checkpoints expect JSON wire format. The offset positions are still valid, but the deserializer expects Avro bytes now.
- **`spark-avro` JAR** is pulled via `spark.jars.packages` at SparkSession creation time, not as a pip dependency. It's downloaded from Maven Central on first run.

### Schema Ownership — Who Owns What in Enterprise

A common question in schema-enforced architectures: who defines the schema, and how do teams consume it?

**The shared schema repository pattern:** The `schemas/` package acts as a shared schema repo — analogous to a separate Git repository (or Maven/pip artifact) that the platform team publishes and all teams depend on. It's a top-level package (not inside `infra/`, `ingestion/`, or `processing/`) because it crosses team boundaries.

| Team | Responsibility | Relationship to Schema |
|------|---------------|----------------------|
| **Platform (`infra/`)** | Registers schemas in the registry, sets compatibility mode, enables server-side validation, creates metastore tables | Imports from `schemas/` package, manages lifecycle |
| **Ingestion** | Serializes messages using `AvroSerializer` — must know the schema to populate fields correctly | Imports from `schemas/` package, uses at serialization time |
| **Processing** | Deserializes messages using `from_avro()` — needs the schema to parse binary Avro back into columns | Imports from `schemas/` package, converts to JSON strings in `processing/schemas.py` |

**Why producers need the schema locally (not just from the registry):** The `AvroSerializer` requires the schema string at construction time — it must know what fields to serialize. In theory, a producer could fetch the schema from the registry at startup, but this creates a runtime dependency on registry availability. The shared repo pattern gives producers the schema at import time (compile-time equivalent), so a registry outage doesn't prevent message production. The registry's real job is **enforcement and evolution** — ensuring producers can't silently change the wire format — not schema discovery for producers.

**Alternative pattern — registry-first discovery:** Some enterprise setups have producers fetch the latest schema from the registry on startup. This is useful when schemas change frequently and you want producers to auto-adopt new versions without redeployment. The trade-off is a hard dependency on registry availability at startup time. For this project, schemas are stable (the Yelp dataset doesn't change), so the shared repo pattern is simpler and more resilient.

### Why Avro on the Wire (Not Plain JSON)

It's not because we need the compression at portfolio scale — 150K businesses and 7M reviews would work fine with JSON. It's because this project demonstrates enterprise patterns. In a real pipeline doing millions of events/second, JSON serialization cost and payload size become a real problem. Avro + schema registry is the industry standard for exactly that reason.

The trade-off you see in Bronze — the wire format header stripping (`substring(value, 6)`), the Avro schema JSON plumbing, the `from_avro()` deserialization — is the complexity cost of enterprise schema enforcement. In production, that cost is invisible because shared libraries and internal SDKs handle it. Here it's visible because we're building those layers ourselves.

**TL;DR:** JSON for prototypes and low-volume systems. Avro for production pipelines where schema safety and throughput matter. We use Avro here to showcase the enterprise pattern.

### Bug Found During End-to-End Testing

**Problem:** Every record from both producers failed Avro serialization with errors like `"34.4266787 (type <class 'float'>) do not match ['null', 'string'] on field latitude"` and `"3.0 (type <class 'float'>) do not match ['null', 'string'] on field stars"`.

**Root cause:** The Avro schemas (`yelp_business.avsc`, `yelp_review.avsc`) define all fields as `["null", "string"]` — the Bronze layer stores everything as raw strings with zero transforms. But `json.loads()` in `data_loader.py` produces native Python types: `float` for `latitude`, `longitude`, `stars`; `int` for `review_count`, `useful`, `funny`, `cool`. The `AvroSerializer` rightfully rejected these type mismatches.

**Fix:** Added `str(v)` coercion in `_clean_record()` (`ingestion/data_loader.py`), converting all non-None values to strings before they reach the serializer. This is the correct place for the conversion — the data loader is the boundary between raw JSON and the Avro contract, so type coercion belongs there, not in the producer or schema.

**Lesson:** When your Avro schema is all-STRING (common for Bronze "raw landing" layers), the producer-side code must enforce that contract. `json.loads()` will always return native types — the coercion must be explicit. In enterprise settings, this is typically handled by a shared serialization SDK that the platform team provides. Here, `_clean_record()` serves that role.

---

## Phase 5: Gold Layer — BigQuery Sink

### What Was Built
The first branch of the Gold layer: a streaming `foreachBatch` pipeline that reads the Silver `reviews` table and loads data into BigQuery via the Load API. This is the structured analytics half of the dual-sink Gold layer — the vector search branch (Qdrant + Gemini Embedding) will be added in the next phase.

### Architecture Decision: `foreachBatch` for Dual-Sink
Bronze and Silver use Spark's built-in `toTable()` sink, writing to a single Hive-managed table. Gold needs to write to two external systems (BigQuery + Qdrant) from the same stream. The `foreachBatch` API provides a static DataFrame per micro-batch, allowing arbitrary processing logic — including calling external APIs like BigQuery's Load API and Qdrant's batch upsert. Each sink branch runs in an independent `try/except` block so that a failure in one does not block the other.

### Why Load API, Not Streaming Inserts
BigQuery offers two data loading patterns:

1. **Streaming inserts** (`insertAll` / `insert_rows_json`): sub-second latency, but costs $0.01/200MB on paid tiers and is **not available in BigQuery Sandbox** (the free tier without a credit card).
2. **Load API** (`load_table_from_dataframe`): batch-oriented, creates a load job per call (~5-30s latency), but is **completely free** — no per-byte charges, no Sandbox restrictions.

For this portfolio project running on a $0 budget, Load API is the only viable option. The 60-second trigger interval accounts for the per-job overhead. In enterprise, you'd typically use streaming inserts for true real-time and Load API for batch/micro-batch — the `foreachBatch` pattern supports either by swapping the client call.

### Idempotency Trade-off
The Gold layer uses `review_id` as the natural dedup key. The ideal approach would be a BigQuery `MERGE` (upsert) statement on each batch. However, **BigQuery Sandbox does not support DML** — no `MERGE`, `INSERT`, `UPDATE`, or `DELETE` statements.

**What we do instead:**
- **Write path:** Append-only loads with `WRITE_APPEND` disposition. Spark checkpointing guarantees exactly-once delivery within a continuous run — the checkpoint tracks which Silver files have been processed, so restarting from a valid checkpoint never re-processes data.
- **Read path:** A dedup VIEW (`gold_reviews_deduped`) provides a clean interface using `ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY ingestion_timestamp DESC)`. Consumers query the view and get exactly one row per review.
- **Cross-restart scenario:** If the checkpoint is lost or reset, data already in BigQuery will be re-loaded, creating duplicates in the raw table. The dedup view handles this transparently. A `--reset` CLI flag is provided for development to drop the table, view, and checkpoint for clean reruns.

**Enterprise parallel:** In production BigQuery (paid tier), you'd use `MERGE` for upserts or `WRITE_TRUNCATE` per partition for full reloads. The append + dedup-view pattern is a well-known workaround for immutable/append-only stores (also common with S3/Parquet data lakes) and is valid even at enterprise scale for cost optimization.

### PySpark to BigQuery: The Pandas Bridge
BigQuery's Python SDK (`google-cloud-bigquery`) provides `load_table_from_dataframe()` which accepts a pandas DataFrame. The flow is:

```
PySpark batch_df → .toPandas() → pandas DataFrame → load_table_from_dataframe() → BigQuery
```

This works well because `foreachBatch` micro-batches are bounded by `maxFilesPerTrigger=5`, keeping batch sizes in the thousands of rows (not millions). The pandas conversion is a driver-side collect, which is safe at this scale. For truly large batches in production, you'd use the Spark BigQuery Connector (`spark-bigquery-connector`) to write directly from Spark executors — but that adds a heavy dependency and is unnecessary for this project's data volumes.

### Verification Results
- **7 batches processed**, 27,573 rows loaded into `yelp_analytics.gold_reviews`
- **Column types correct:** `FLOAT64` for business_stars, `INT64` for review_stars/useful/funny/cool, `BOOL` for 20+ boolean attributes, `STRING` for text fields, `TIMESTAMP` for dates
- **Load API confirmed:** every batch logged a `job_id` (BigQuery load job identifier), not streaming insert confirmations
- **Dedup view operational:** `gold_reviews_deduped` returns the same count (no duplicates in this run)

## Phase 5b: Gold Layer — Qdrant Embedding Sink

### What We Built
The second branch of the Gold layer's dual-sink architecture: a Gemini-powered embedding pipeline that converts Silver review data into 768-dimensional vectors and upserts them to Qdrant for semantic search. This completes the dual-sink pattern — every `foreachBatch` micro-batch now flows independently to both BigQuery (structured analytics) and Qdrant (semantic search).

### Architecture: Dual-Sink foreachBatch

The Gold layer's `foreachBatch` callback delegates to two self-contained sink modules:

```
foreachBatch(batch_df, batch_id):
    bq_sink.sink_batch(batch_df, batch_id)      # Branch 1: BigQuery Load API
    qdrant_sink.sink_batch(batch_df, batch_id)   # Branch 2: Gemini Embed + Qdrant Upsert
```

Each sink module lives under `processing/sinks/` — `bigquery.py` and `qdrant_sink.py`. Each has its own `BatchSink` class with independent `try/except` error handling. A failure in Qdrant (rate limit exhaustion, network timeout, embedding API error) never blocks BigQuery, and vice versa. The orchestrator (`gold.py`) stays slim — it creates clients, wires them together, and starts the stream.

**Enterprise framing:** In production, these sinks would likely be separate Spark jobs writing to different topics/queues, or a single job with circuit breakers per sink. The `foreachBatch` pattern with independent error boundaries achieves the same reliability guarantee at portfolio scale without the operational overhead of separate deployment units.

### Embedding Strategy: Why Gemini over Local Models

The GCP e2-micro VM has 1GB RAM. Local embedding models (sentence-transformers, ONNX) require 200-500MB just for the model weights, leaving nothing for Qdrant, the API, or the OS. API-based embeddings are the only viable option under this constraint.

**Model choice:** `gemini-embedding-001` (Google's latest embedding model) with these characteristics:
- **768 dimensions** via Matryoshka Representation Learning (MRL) — the model natively supports dimensionality reduction through the `output_dimensionality` parameter. The full model produces 3072 dimensions, but MRL allows truncation to 768 with minimal quality loss. This is not a post-hoc PCA reduction — the model is trained with MRL so that leading dimensions carry the most information.
- **Task type distinction:** `RETRIEVAL_DOCUMENT` for ingestion (the reviews being indexed) vs `RETRIEVAL_QUERY` for search queries. This asymmetric encoding improves retrieval quality because the model learns to encode documents and queries differently — documents capture comprehensive content while queries capture intent.
- **Free tier:** 3,000 RPM (requests per minute) with batching up to 100+ texts per request.

**Embedding input:** Concatenation of `business_name | categories | review_text`. This gives the vector semantic signal from all three dimensions — what the business is, what type it is, and what the reviewer experienced. A pure review-text embedding would miss business context; a pure business embedding would miss subjective experience.

### Rate Limiting & Backoff

The Gemini free tier allows 3,000 RPM for embeddings. Our pipeline processes micro-batches of 2,000-5,000 rows, each requiring 20-50 API calls (at 100 texts per call). A single batch easily stays under the limit, but consecutive batches from the previous run's quota window can trigger 429s.

**Defense strategy (two layers):**

1. **Sliding-window rate limiter** — tracks timestamps of the last N API calls in a deque. Before each call, checks if the window is full; if so, sleeps until a slot opens. Set to 2,900 RPM (staying under the 3,000 limit). This prevents burst-induced 429s.

2. **Exponential backoff via tenacity** — if a 429 still slips through (quota window overlap, concurrent usage), the `@retry` decorator retries with exponential backoff: 2s → 4s → 8s → 16s → 32s → 64s → 120s → fail. The `before_sleep` callback logs every retry with the exception details, so rate limit events are always visible in logs.

**Observed behavior:** Batch 0 (2,356 texts) completes in ~40s with no rate limiting. Batch 1 (4,202 texts) sometimes hits a 429 at ~600 calls when residual quota from batch 0's window hasn't expired. The backoff recovers within 8-15s and continues. By batch 2+, the window has rotated and batches flow smoothly.

### Throughput Estimate

At 100 texts per API call and ~1.5s per call (network latency to Google's API):
- **~67 calls/minute** sustained (well under 3,000 RPM)
- **~6,700 texts/minute** embedded
- **Full 7M dataset: ~17 hours** of continuous embedding

For the portfolio demo, a few thousand vectors demonstrate the semantic search capability. The pipeline resumes from Spark checkpoints, so the full dataset can be embedded over multiple runs.

### Qdrant Collection Design

```
Collection: yelp_reviews
  Vectors:   size=768, distance=Cosine, on_disk=True
  Point ID:  uuid5(NAMESPACE_URL, review_id) — deterministic for idempotent upserts
  Payload:   17 fields (identity, business context, quality signals, vibe attributes, review text)
```

**`on_disk=True`:** Vectors are stored on disk with memory-mapped access. At 768 dims × 4 bytes × 7M vectors = ~21GB, this data cannot fit in the VM's 1GB RAM. On-disk storage with mmap lets Qdrant serve queries by paging vectors from disk, trading latency for memory. For a portfolio demo with moderate query load, this is the right trade-off.

**Deterministic point IDs:** `uuid5(NAMESPACE_URL, review_id)` produces the same UUID for the same review_id every time. This makes upserts idempotent — re-running the pipeline on the same data overwrites existing points rather than creating duplicates. Combined with Spark's checkpoint-based exactly-once guarantee, the pipeline can be stopped and resumed without data quality concerns.

**Payload fields (17):**
- Identity: `review_id`, `business_id`
- Business context: `name`, `city`, `state`, `categories`
- Quality signals: `business_stars`, `review_stars`, `review_count`, `is_open`
- Vibe attributes: `alcohol`, `noise_level`, `wifi`, `outdoor_seating`, `restaurants_price_range`
- Content: `text`, `date`

These payload fields serve two purposes: (1) they're returned with search results so the agent can synthesize answers without a BigQuery round-trip, and (2) they support Qdrant's payload filtering — the vector agent can pre-filter by city, state, or star rating before computing similarity, dramatically reducing the search space.

### Code Organization: Sink Modules

The refactoring from monolithic `gold.py` to `processing/sinks/{bigquery.py, qdrant_sink.py}` follows the enterprise pattern of separation by responsibility:

```
processing/
├── gold.py              # Slim orchestrator — streaming setup, foreachBatch wiring
├── schemas.py           # Field selections for each sink
└── sinks/
    ├── __init__.py
    ├── bigquery.py      # BQ client, provisioning, batch load, reset
    └── qdrant_sink.py   # Qdrant client, Gemini embedding, batch upsert, reset
```

Each sink module owns its client creation, provisioning (ensure_sink/ensure_collection), batch processing, and reset logic. The orchestrator creates clients at startup and passes them to `BatchSink` instances. This makes each sink independently testable and replaceable — in a production system, you could swap Qdrant for Pinecone or BigQuery for Snowflake by implementing the same interface.

### Verification Results
- **3 batches processed** before stopping: 2,356 + 4,202 + 485 = 7,043 vectors in Qdrant, 12,477 rows in BigQuery (BQ processed more batches since it's faster)
- **Dual-sink independence confirmed:** BigQuery batch loads complete in ~5-9s while Qdrant embedding takes 8-112s per batch. BQ never waits for Qdrant.
- **Rate limit recovery confirmed:** 429 errors at batch 1 recovered via exponential backoff (2s → 4s → 8s), pipeline resumed embedding within 15s
- **Similarity search verified:** Query "cozy Italian restaurant with great pasta and wine" returned 5 semantically relevant results — Italian restaurants with reviews mentioning cozy atmosphere, great food, and authentic experience (scores 0.68-0.73)

## Phase 6: LangGraph Agent System

### What We Built
A multi-agent pipeline that routes natural language queries to the right data source — BigQuery for structured analytics, Qdrant for semantic search, or both sequentially for hybrid queries. A Gemini-powered router classifies each query, specialized agents execute against the appropriate sink, and a synthesizer produces conversational answers with routing transparency.

### Architecture: Why Explicit Routing Over Tool Selection
Enterprise systems favor explicit routing for cost control and predictability. A single Gemini classification call with `thinking_level="minimal"` is cheaper and more debuggable than letting a ReAct agent decide freely across tools. The router makes the system's decision-making transparent and testable — every answer shows which route was chosen.

The flat graph topology:
```
START → Router → SQL Agent ──────────────────→ Synthesizer → END
               → Vector Agent ───────────────→ Synthesizer → END
               → SQL Agent → Vector Agent ──→ Synthesizer → END (HYBRID)
```

### Why Sequential HYBRID, Not Parallel
A query like "best restaurants in the top 10 highest-rated cities" needs SQL to identify candidates first (which cities? which businesses?), then Vector to rank them semantically. The `business_id` is the universal join key between BigQuery and Qdrant. Parallel execution would return independent, uncorrelated results — you'd get an average rating AND a list of vibes, not vibes for the right businesses.

### Why Function-Based Vector Agent, Not ReAct
The vector agent's steps are always identical: extract filters from the query → embed the query → search Qdrant → return results. There's no branching logic that benefits from multi-step LLM reasoning. A function is faster, cheaper, and more predictable than a ReAct loop. The filter extraction uses a single Gemini call with `thinking_level="minimal"` to parse structured fields (city, categories, price range, etc.) from natural language.

### The Deduped View Strategy
The gold layer appends via BigQuery's Load API, which can produce duplicates on reprocessing. A `gold_reviews_deduped` view uses `ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY ingestion_timestamp DESC)` to keep only the latest version of each review. The SQL agent queries this view exclusively — never the raw table — so aggregations aren't inflated by duplicates.

### Modules
| Module | Responsibility | Key Design Choice |
|--------|---------------|-------------------|
| `agents/state.py` | AgentState TypedDict (8 fields) | Flat state, nodes read/write what they need |
| `agents/router.py` | Gemini classifier → SQL/VECTOR/HYBRID | `thinking_level="minimal"`, HYBRID fallback on parse failure |
| `agents/sql_agent.py` | ReAct SQL toolkit against BigQuery | `view_support=True`, LIMIT 50/200 guardrails, dedicated business_id extraction for HYBRID |
| `agents/vector_agent.py` | Filter extraction → Gemini embedding → Qdrant search | `google-genai` SDK (not langchain), `RETRIEVAL_QUERY` task type, tenacity retry |
| `agents/synthesizer.py` | Gemini answer generation | References specific data, routing transparency on every answer |
| `graph.py` | LangGraph StateGraph wiring + CLI | Pure wiring, no business logic |

### Challenges
- **`thinking_level` response format:** When `thinking_level` is set on `ChatGoogleGenerativeAI`, `response.content` returns a list of content blocks instead of a plain string. Required an `extract_text()` helper to normalize both formats across all modules.
- **HYBRID business_id extraction:** `create_sql_agent` returns summarized text, not raw SQL results. A dedicated follow-up LLM call generates a business_id-only query executed directly via SQLAlchemy. Requires schema context in the prompt to avoid column name errors.
- **Router classification boundaries:** "cozy Italian restaurants in Tucson" routes HYBRID (not VECTOR) because the router sees both a structured filter (city, category) and subjective intent (cozy). This is actually reasonable — the HYBRID path produces excellent results since SQL narrows candidates and vector ranks them semantically.

### Verification Results
All three routes produce sensible answers with routing transparency:
- **SQL:** "average rating for restaurants in Tucson" → 3.84 average, clean factual answer
- **HYBRID (vibe query):** "cozy Italian restaurants in Tucson" → SQL finds 1 business, vector returns 6 results with specific restaurant names, ratings, and review quotes
- **HYBRID (complex):** "best restaurants in the top 5 highest-rated cities" → SQL provides 1743 chars of context, vector adds semantic results, comprehensive multi-city answer

---

## Phase 7: Flask API + VM Deployment

### What Was Built
A Flask HTTP API (`api.py`) that wraps the LangGraph agent system from Phase 6, making it accessible over the network. Two endpoints serve the agent and provide operational visibility.

### Request Flow
```
Firebase static site → Cloudflare → Flask API (GCP VM, port 5001)
  → LangGraph Router → SQL Agent (BigQuery) / Vector Agent (Qdrant) → Synthesizer
  → JSON response with transparency fields (route, SQL query, vector results)
```

### API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/query` | POST | Accepts `{"query": "..."}`, runs the LangGraph agent, returns answer + transparency fields (route, sql_query, sql_result, vector_results) |
| `/health` | GET | Pings Qdrant (`get_collections`) and BigQuery (`SELECT 1`), returns status per backend |

### Deployment Architecture
- **Docker Compose** manages two services on the GCP e2-micro VM: Qdrant (existing, migrated from standalone container) and the Flask API
- **Qdrant** was already running on the VM — compose adoption preserves existing data via volume mapping
- **GCP credentials** mounted as a read-only Docker volume into the API container
- **CORS** configured via `CORS_ORIGIN` env var (defaults to `*`, set to Firebase domain in production)
- **Threading:** `threaded=True` on Flask dev server prevents blocking during agent calls (10-30s per HYBRID query)

### Design Decisions
- **No rate limiting:** Gemini free tier provides 4K RPM (Flash Lite) and 3K RPM (Embeddings) — each query uses ~3 LLM + ~1 embedding call, giving ~1,300 queries/minute theoretical capacity. Portfolio traffic won't approach this.
- **No auth:** Read-only API over public Yelp data. CORS origin restriction is configurable but the real protection boundary would be API keys (not needed for portfolio).
- **Lazy YelpSettings:** `settings.py` eagerly instantiated all config classes, but the API container doesn't have ingestion-only env vars (`YELP_*_JSON_PATH`). Made `YelpSettings` a lazy `@property` so import doesn't crash.
- **Transparency fields:** Every response includes the route taken, SQL query generated, and vector results — lets the frontend show the system's decision-making process.
- **Health check pings real backends:** Not just `{"status": "ok"}` — actually validates Qdrant and BigQuery connectivity. Useful for debugging after VM restarts.

### Deployment Checklist (on GCP VM via SSH)
After the Docker artifacts are ready, these manual steps are needed on the VM:

1. **Qdrant migration:** Stop the standalone Qdrant container, note its data volume path (`docker inspect qdrant | grep -A 10 Mounts`), update the compose volume to match, then `docker compose up -d`. Verify with `curl http://localhost:6333/collections`.
2. **Nginx update:** Add a reverse-proxy rule to forward traffic to `localhost:5001` for this project's subdomain/path. Without this, the API is not reachable from the internet.
3. **Cloudflare:** Ensure DNS points to the VM for the API subdomain.

### RAM Budget
Flask + LangGraph + LangChain fits well under 300MB — no ML models loaded locally, all inference is remote API calls to Gemini, BigQuery, and Qdrant.
