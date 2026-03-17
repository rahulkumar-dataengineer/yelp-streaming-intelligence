# Flask API + VM Deployment Design

**Date:** 2026-03-17
**Status:** Approved
**Depends on:** Phase 6 (LangGraph agent system) — complete and verified

## Overview

HTTP endpoint serving the LangGraph agent, containerized alongside Qdrant on the existing GCP e2-micro VM. Single module (`api.py`), no auth, no rate limiting — Gemini free tier limits are generous (4K RPM Flash Lite, 3K RPM embeddings) and portfolio traffic is minimal.

## Current State

- **Qdrant** is already running on the GCP VM as a standalone Docker container (port 6333, `on_disk=True`, populated with review embeddings)
- **BigQuery** is a managed GCP service — queried remotely via API
- **LangGraph agent** works end-to-end via CLI (`python graph.py "query"`)
- **No HTTP interface exists yet** — this phase adds it

## Production Request Flow

```
User → Firebase static site (your-project.web.app)
     → Cloudflare (CDN/proxy)
     → Flask API on GCP VM (port 5001)
     → LangGraph agent
         ├→ Router (Gemini Flash Lite) → classify SQL/VECTOR/HYBRID
         ├→ SQL Agent → BigQuery (remote, gold_reviews_deduped view)
         ├→ Vector Agent → Qdrant (same VM, localhost:6333)
         └→ Synthesizer (Gemini Flash Lite) → natural language answer
     → JSON response → Firebase UI
```

## API Design

### `POST /query`

Runs the LangGraph agent synchronously.

**Request:**
```json
{"query": "find cozy Italian restaurants in Phoenix"}
```

**Success response (200):**
```json
{
  "answer": "Based on reviews, here are some cozy Italian spots in Phoenix...",
  "route": "VECTOR",
  "sql_query": null,
  "sql_result": null,
  "vector_results": [
    {"business_name": "...", "score": 0.72, "city": "Phoenix", "snippet": "..."}
  ],
  "error": null
}
```

**Agent failure response (500):**
```json
{
  "answer": null,
  "route": "VECTOR",
  "sql_query": null,
  "sql_result": null,
  "vector_results": null,
  "error": "Gemini API returned 429: rate limit exceeded"
}
```

**Missing query key (400):**
```json
{"error": "Missing 'query' field in request body"}
```

**Transparency fields:** Every response includes `route`, `sql_query`, `sql_result`, `vector_results` regardless of which route was taken. Unused fields are `null`. This lets the frontend display the system's decision-making process.

**Validation:** Minimal — only reject if `query` key is missing from the JSON body. No max length, no content filtering. Let the agent system handle whatever comes in.

### `GET /health`

Pings both backends to verify the system is operational.

**Healthy response (200):**
```json
{"status": "ok", "qdrant": true, "bigquery": true}
```

**Degraded response (503):**
```json
{"status": "degraded", "qdrant": true, "bigquery": false}
```

**Health checks:**
- **Qdrant:** `qdrant_client.get_collections()` — confirms Qdrant is reachable on the same VM
- **BigQuery:** `client.query("SELECT 1")` — confirms BigQuery credentials and connectivity. Note: each call counts toward 1TB/month quota but is trivial (~10 bytes). Avoid calling `/health` at high frequency from monitoring tools.

## CORS Configuration

Configured via `CORS_ORIGIN` environment variable, loaded through `config/settings.py`, defaults to `*`.

- **Local dev:** `CORS_ORIGIN=*` (or `http://localhost:5000`)
- **GCP VM (prod):** `CORS_ORIGIN=https://your-project.web.app`

Implementation: `flask-cors` with `origins=[settings.api.CORS_ORIGIN]`.

**New dependencies:** `flask` and `flask-cors` must be added to `requirements.txt` (verify they're not already present).

Rationale for env var approach over hardcoded `*`: demonstrates environment-aware configuration — the pattern you'd use in production. The API is read-only with no sensitive data, so `*` would also be acceptable.

## Config Addition

One new setting in `config/settings.py`:

New class in `config/settings.py`, following the existing `_optional()` pattern:

```python
class APISettings:
    CORS_ORIGIN: str = _optional("CORS_ORIGIN", "*")

# Add to Settings class:
class Settings:
    ...
    api = APISettings()
```

Follows the existing pattern — all config via `settings.py`, never import `os.environ` directly.

## Deployment Architecture

### `build/Dockerfile`

- Base: `python:3.11-slim`
- Copies project code (agents/, config/, graph.py, api.py, utils/)
- Installs `requirements.txt`
- Exposes port 5001
- Entrypoint: Flask dev server with `threaded=True` (sufficient for portfolio traffic; gunicorn is an option if needed). Single-threaded Flask would block on agent calls (10-30s per HYBRID query); `threaded=True` allows concurrent requests.

### `build/docker-compose.yml`

Two services on a shared Docker network:

**`qdrant`** — migrates the existing standalone container into compose management:
- Image: `qdrant/qdrant:latest`
- Ports: `6333:6333`, `6334:6334`
- Volume: named volume for data persistence (preserves existing embeddings)
- Environment: default config with `on_disk=True`

**`api`** — the new Flask application:
- Build: from `build/Dockerfile`
- Ports: `5001:5001`
- Environment variables (via `.env` file or env block):
  - `QDRANT_HOST=qdrant` (Docker service name, not localhost)
  - `QDRANT_PORT=6333`
  - `QDRANT_COLLECTION=yelp_reviews`
  - `GEMINI_API_KEY` (from `.env`)
  - `GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`, `GEMINI_EMBEDDING_DIMENSIONS`
  - `GCP_PROJECT_ID`, `GCP_BIGQUERY_DATASET`, `GCP_BIGQUERY_TABLE`
  - `GOOGLE_APPLICATION_CREDENTIALS` (mount credentials file as Docker volume, set env var to mount path inside container)
  - `CORS_ORIGIN` (Firebase domain in prod)
- Depends on: `qdrant`

### Qdrant Migration (one-time)

The existing standalone Qdrant container must be stopped and replaced with the compose-managed one. Steps:
1. Stop existing container: `docker stop qdrant`
2. Identify the existing volume/bind mount for Qdrant data
3. Map the same data path in the compose volume definition
4. `docker compose up -d` — Qdrant starts with existing data intact
5. Verify: `curl http://localhost:6333/collections` confirms `yelp_reviews` collection is present

### RAM Budget

Per global CLAUDE.md: ~300MB max per project API, Qdrant gets ~400MB.
- **Flask + LangGraph + LangChain:** Well under 300MB — no ML models loaded locally. All inference is remote API calls (Gemini, BigQuery, Qdrant client).
- **Qdrant:** Already running, no change to resource usage.

## Gemini Rate Limits (as of 2026-03-17)

Verified from AI Studio:

| Model | RPM | TPM | RPD |
|-------|-----|-----|-----|
| Gemini 3.1 Flash Lite | 4,000 | 4M | 150,000 |
| Gemini Embedding 001 | 3,000 | 1M | Unlimited |

Each user query triggers ~3 Flash Lite calls + ~1 embedding call → theoretical max ~1,300 queries/minute. No application-level rate limiting needed for portfolio traffic.

Existing `tenacity` retry logic in agents handles transient 429s with exponential backoff.

## What Is NOT in Scope

- **Authentication / API keys** — read-only portfolio project, no sensitive data
- **Request queuing or throttling** — Gemini limits are generous
- **Gunicorn / production WSGI server** — Flask dev server is sufficient for portfolio traffic (can upgrade later if needed)
- **Nginx config on the VM** — the VM's nginx must be updated to reverse-proxy to `localhost:5001` for this project (e.g., by subdomain or path). The exact route depends on the Cloudflare/domain setup. This is a deployment step, not application code, but must not be forgotten.
- **Firebase chat UI** — separate phase
- **Streaming pipeline** — already complete, data is in BigQuery and Qdrant

## Verification Plan

1. **Local:** Run `api.py` locally, curl both endpoints with test queries covering all three routes
2. **Docker:** Build and run via `docker compose up`, verify API can reach Qdrant by service name
3. **VM:** Deploy to GCP VM, verify health check, test all three routes via curl
4. **Cross-origin:** Confirm CORS headers are present in responses

Test queries:
- SQL: `"what's the average rating for restaurants in Scottsdale"`
- VECTOR: `"find me cozy Italian restaurants in Phoenix"`
- HYBRID: `"best restaurants in the top 10 highest-rated cities"`

## Documentation

Append Phase 7 section to `docs/explanation.md` covering:
- What was deployed and why
- Request flow diagram
- Docker setup and Qdrant migration
- CORS and health check design decisions
- Gemini rate limit analysis