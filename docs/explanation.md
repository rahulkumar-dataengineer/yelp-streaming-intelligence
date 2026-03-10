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
| **LLM** | Gemini 2.5 Flash (free API tier) | 10 RPM, 250 requests/day. Two calls per query (router + synthesizer). |
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
