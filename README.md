# yelp-streaming-intelligence

Ask *"find me a cozy Italian spot on a rainy evening"* and get results backed by 1 million real Yelp reviews. A real-time streaming pipeline with a LangGraph multi-agent router that combines BigQuery SQL analytics and Qdrant semantic vector search.

## Architecture

```
Yelp JSON (1M reviews)
     │
     ▼
┌─────────────────┐
│   producer.py   │  Streams businesses + reviews to Redpanda as Avro messages
└────────┬────────┘  keyed by business_id (co-partitioned for stream-stream join)
         │ Kafka (port 9092)
         ▼
┌─────────────────┐
│    Redpanda     │  Kafka-compatible broker, local Docker
│   (Docker)      │  Topics: yelp_businesses, yelp_reviews
└────────┬────────┘
         │ PySpark Structured Streaming
         ▼
┌──────────────────────────────────────────┐
│  Bronze  →  Silver  →  Gold (foreachBatch) │
│  Raw Avro   Cleaned +   Dual-sink         │
│  Parquet    stream join  BigQuery+Qdrant  │
└──────────────────────────────────────────┘
         │                    │
         ▼                    ▼
  ┌────────────┐     ┌──────────────────┐
  │  BigQuery  │     │  Qdrant          │
  │  Sandbox   │     │  (GCP e2-micro)  │
  │  SQL sink  │     │  768-dim vectors │
  └─────┬──────┘     └────────┬─────────┘
        └──────────┬──────────┘
                   ▼
     ┌─────────────────────────────┐
     │  LangGraph Multi-Agent      │
     │  Router → SQL | Vector |    │
     │           HYBRID            │
     │  Synthesizer (Gemini)       │
     └──────────────┬──────────────┘
                    ▼
          ┌──────────────────┐
          │  Flask API       │  /query  /health
          │  Firebase Chat   │  Static frontend
          └──────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| Message broker | Redpanda (Docker, Kafka-compatible) |
| Stream processing | PySpark 3.5 Structured Streaming (Bronze/Silver/Gold) |
| Structured sink | BigQuery Sandbox — Load API only |
| Vector sink | Qdrant (self-hosted, on_disk=True, 768-dim cosine) |
| Embeddings | Gemini Embedding (`gemini-embedding-001`, 768-dim MRL) |
| LLM | Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite-preview`) |
| Agent framework | LangGraph + LangChain |
| API | Flask |
| Frontend | Firebase Hosting (Spark plan — static only) |

## Prerequisites

**Software:**
- Python 3.11+
- Docker Desktop

**Cloud accounts (all free tier):**
- Google Cloud Platform — BigQuery Sandbox, service account with BigQuery Editor role
- Google AI Studio — Gemini API key
- Qdrant — self-hosted on GCP e2-micro VM (or `localhost:6333` for local dev)

**Data:**
- Yelp Open Dataset: `yelp_academic_dataset_business.json` + `yelp_academic_dataset_review.json`

---

## Running the Pipeline

### 1. Start local infrastructure

```bash
# Start Redpanda + Hive Metastore (shared infra from platform-commons)
infra-up
# or:
docker compose -f ../portfolio-platform-commons/src/platform_commons/docker/docker-compose.yml up -d
```

### 2. Provision schemas and metastore (run once)

```bash
python -m infra
```

### 3. Validate all connections (9-point health check)

```bash
python -m tests.validate_connections
```

### 4. Run the pipeline — each in its own terminal

```bash
# Terminal 1 — produce 1M reviews + 150K businesses to Redpanda
python -m ingestion.producer

# Terminal 2 — Bronze: Avro from Kafka → raw Parquet
python -m processing.bronze

# Terminal 3 — Silver: type-cast, clean, stream-stream join on business_id
python -m processing.silver

# Terminal 4 — Gold: dual-sink to BigQuery + Qdrant (embeddings via Gemini)
python -m processing.gold
```

### 5. Verify sinks

```bash
python check_sinks.py
```

### 6. Run the agent API

```bash
python api.py
```

### 7. Test the agent directly

```bash
python graph.py "find me cozy Italian restaurants in Phoenix"
python graph.py "what's the average rating for restaurants in Scottsdale"
python graph.py "best restaurants in the top 10 highest-rated cities"
```

---

## Reset Scenarios

### Scenario 1: Recreate Local Infrastructure Only

Use this when local Redpanda or Hive Metastore is in a bad state, topics are polluted, or you want a clean broker without touching BigQuery or Qdrant.

```bash
# Step 1 — tear down local containers + volumes (Redpanda, Hive Metastore, PostgreSQL)
docker compose -f ../portfolio-platform-commons/src/platform_commons/docker/docker-compose.yml down -v

# Step 2 — bring them back fresh
infra-up

# Step 3 — re-register Avro schemas + recreate Hive tables
python -m infra

# Step 4 — delete Spark checkpoints (old offsets no longer exist in Redpanda)
rm -rf checkpoints/bronze checkpoints/silver checkpoints/gold

# Step 5 — re-run the pipeline from the top (terminals 1–4 in Running the Pipeline)
```

> BigQuery and Qdrant data on GCP are **unaffected** by this reset — use Scenario 2 if you also want to wipe those.

---

### Scenario 2: Full Reset (Local + BigQuery + Qdrant)

Use this to wipe everything and re-run the complete pipeline end-to-end from raw JSON files.

```bash
# Step 1 — wipe BigQuery table+view, Qdrant collection, and Gold checkpoint
python -m processing.gold --reset

# Step 2 — delete Bronze and Silver checkpoints
rm -rf checkpoints/bronze checkpoints/silver

# Step 3 — tear down and recreate local infrastructure
docker compose -f ../portfolio-platform-commons/src/platform_commons/docker/docker-compose.yml down -v
infra-up
python -m infra

# Step 4 — re-run the pipeline from the top (terminals 1–4 in Running the Pipeline)
```

> `--reset` deletes: `gold_reviews` table, `gold_reviews_deduped` view, Qdrant `yelp_reviews` collection, and `checkpoints/gold/`.

---

## Resuming After Interruption

Spark checkpoints make resumption automatic. If a process dies mid-run:

| Stopped stage | How to resume |
|---|---|
| **Producer** | Restart `python -m ingestion.producer` — Redpanda retains unconsumed messages |
| **Bronze** | Restart `python -m processing.bronze` — picks up from its Kafka offset checkpoint |
| **Silver** | Restart `python -m processing.silver` — picks up from its Parquet file checkpoint |
| **Gold** | Restart `python -m processing.gold` — picks up from its file checkpoint, Qdrant upserts are idempotent via deterministic UUIDs |

**Do not delete checkpoints unless you intend a full reset** — they are the resume markers.

If Gold stopped mid-batch and you see duplicate rows in BigQuery, that is expected — the `gold_reviews_deduped` view handles deduplication automatically via `ROW_NUMBER() OVER (PARTITION BY review_id)`.

---

## Partial Reset (one sink only)

If only one sink is corrupted or you want to rebuild just Qdrant or just BigQuery:

```bash
# Reset only Qdrant (keep BigQuery intact)
python - <<'EOF'
from processing.sinks.qdrant_sink import QdrantManager
QdrantManager().reset()
EOF

# Reset only BigQuery table + dedup view (keep Qdrant intact)
python - <<'EOF'
from processing.sinks.bigquery import BigQueryManager
from config.settings import settings
BigQueryManager().reset(settings.spark.GOLD_CHECKPOINT)
EOF
```

After a partial reset, restart only `python -m processing.gold --reset` is cleaner — but the above works if you need surgical control.

---

## Firebase Frontend

```bash
cd firebase && firebase serve     # local preview
cd firebase && firebase deploy    # deploy to Firebase Hosting
```
