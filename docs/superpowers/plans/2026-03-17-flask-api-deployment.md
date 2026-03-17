# Flask API + VM Deployment Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wrap the LangGraph agent in a Flask API with health checks, containerize alongside Qdrant for GCP VM deployment.

**Architecture:** Single `api.py` module calls `graph.build_graph().invoke()`. Two endpoints: `POST /query` (agent execution) and `GET /health` (backend pings). Dockerized with compose managing both Qdrant and Flask API.

**Tech Stack:** Flask 3.1, flask-cors, Docker, docker-compose, existing LangGraph agent system

**Spec:** `docs/superpowers/specs/2026-03-17-flask-api-deployment-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `config/settings.py` | Modify | Add `APISettings` class, make `YelpSettings` lazy |
| `api.py` | Create | Flask app with `/query` and `/health` endpoints |
| `build/Dockerfile` | Create | Python 3.11 slim image for the API |
| `build/docker-compose.yml` | Create | Qdrant + Flask API services |
| `requirements.txt` | Modify | Add `flask-cors` |
| `docs/explanation.md` | Modify | Append Phase 7 documentation |

---

### Task 1: Add `flask-cors` dependency

**Files:**
- Modify: `requirements.txt:33`

- [ ] **Step 1: Add flask-cors to requirements.txt**

Add `flask-cors` under the existing `flask` line in the Web API section:

```
# Web API
flask==3.1.0
flask-cors==5.0.1
```

- [ ] **Step 2: Install and verify**

Run: `pip install flask-cors==5.0.1`
Expected: Successfully installed

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "deps: add flask-cors for API CORS support"
```

---

### Task 2: Update `config/settings.py` — APISettings + lazy YelpSettings

**Files:**
- Modify: `config/settings.py:41-80`

- [ ] **Step 1: Add APISettings class**

Add after `GeminiSettings` (line 39), before `YelpSettings`:

```python
class APISettings:
    CORS_ORIGIN: str = _optional("CORS_ORIGIN", "*")
```

- [ ] **Step 2: Make YelpSettings lazy in Settings class**

Replace the `Settings` class (lines 71-80) with:

```python
class Settings:
    gcp    = GCPSettings()
    qdrant = QdrantSettings()
    gemini = GeminiSettings()
    api    = APISettings()
    kafka  = KafkaSettings()
    hive   = HiveSettings()
    spark  = SparkSettings()

    @property
    def yelp(self):
        if not hasattr(self, '_yelp'):
            self._yelp = YelpSettings()
        return self._yelp

settings = Settings()
```

- [ ] **Step 3: Verify existing imports still work**

Run: `python -c "from config.settings import settings; print(settings.gemini.MODEL)"`
Expected: `gemini-3.1-flash-lite-preview`

Run: `python -c "from config.settings import settings; print(settings.yelp.BUSINESS_JSON_PATH)"`
Expected: prints the path from `.env` (confirms lazy access still works)

- [ ] **Step 4: Verify API settings work**

Run: `python -c "from config.settings import settings; print(settings.api.CORS_ORIGIN)"`
Expected: `*` (default, since `CORS_ORIGIN` not in `.env` yet)

- [ ] **Step 5: Commit**

```bash
git add config/settings.py
git commit -m "config: add APISettings, make YelpSettings lazy for container compatibility"
```

---

### Task 3: Create `api.py` — Flask application

**Files:**
- Create: `api.py`

- [ ] **Step 1: Create api.py with health check and query endpoint**

```python
"""Flask API serving the LangGraph agent. Single module, two endpoints."""

from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import bigquery
from qdrant_client import QdrantClient

from config.settings import settings
from graph import build_graph

from platform_commons.logger import Logger

logger = Logger("api")

app = Flask(__name__)
CORS(app, origins=[settings.api.CORS_ORIGIN])

# Build graph once at startup
agent = build_graph()


@app.route("/health", methods=["GET"])
def health():
    """Pings Qdrant and BigQuery to verify system is operational."""
    qdrant_ok = False
    bigquery_ok = False

    try:
        client = QdrantClient(host=settings.qdrant.HOST, port=settings.qdrant.PORT)
        client.get_collections()
        qdrant_ok = True
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")

    try:
        bq_client = bigquery.Client(project=settings.gcp.PROJECT_ID)
        list(bq_client.query("SELECT 1").result())
        bigquery_ok = True
    except Exception as e:
        logger.error(f"BigQuery health check failed: {e}")

    status = "ok" if (qdrant_ok and bigquery_ok) else "degraded"
    code = 200 if status == "ok" else 503

    return jsonify({"status": status, "qdrant": qdrant_ok, "bigquery": bigquery_ok}), code


@app.route("/query", methods=["POST"])
def query():
    """Runs the LangGraph agent and returns the result with transparency fields."""
    body = request.get_json(silent=True)
    if not body or "query" not in body:
        return jsonify({"error": "Missing 'query' field in request body"}), 400

    user_query = body["query"]
    logger.info(f"Received query: {user_query}")

    try:
        result = agent.invoke({
            "query": user_query,
            "route": "",
            "sql_query": "",
            "sql_result": "",
            "sql_business_ids": [],
            "vector_results": [],
            "error": "",
            "answer": "",
        })

        return jsonify({
            "answer": result.get("answer"),
            "route": result.get("route"),
            "sql_query": result.get("sql_query") or None,
            "sql_result": result.get("sql_result") or None,
            "vector_results": result.get("vector_results") or None,
            "error": result.get("error") or None,
        })

    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        return jsonify({
            "answer": None,
            "route": None,
            "sql_query": None,
            "sql_result": None,
            "vector_results": None,
            "error": str(e),
        }), 500


if __name__ == "__main__":
    logger.info(f"Starting API server (CORS origin: {settings.api.CORS_ORIGIN})")
    app.run(host="0.0.0.0", port=5001, threaded=True)
```

- [ ] **Step 2: Commit**

```bash
git add api.py
git commit -m "feat: add Flask API with /query and /health endpoints"
```

---

### Task 4: Verify API locally

**Files:**
- None (manual verification)

- [ ] **Step 1: Start the API server**

Run in a terminal: `python api.py`
Expected: Server starts on `http://0.0.0.0:5001`

- [ ] **Step 2: Test health endpoint**

Run in another terminal:
```bash
curl http://localhost:5001/health
```
Expected: `{"bigquery": true, "qdrant": true, "status": "ok"}` with HTTP 200

- [ ] **Step 3: Test missing query (400)**

```bash
curl -X POST http://localhost:5001/query -H "Content-Type: application/json" -d '{}'
```
Expected: `{"error": "Missing 'query' field in request body"}` with HTTP 400

- [ ] **Step 4: Test SQL route**

```bash
curl -X POST http://localhost:5001/query -H "Content-Type: application/json" -d '{"query": "what is the average rating for restaurants in Scottsdale"}'
```
Expected: JSON response with `"route": "SQL"`, `"sql_query"` populated, `"answer"` with a natural language response

- [ ] **Step 5: Test VECTOR route**

```bash
curl -X POST http://localhost:5001/query -H "Content-Type: application/json" -d '{"query": "find me cozy Italian restaurants in Phoenix"}'
```
Expected: JSON response with `"route": "VECTOR"` or `"HYBRID"`, `"vector_results"` populated, `"answer"` present

- [ ] **Step 6: Test HYBRID route**

```bash
curl -X POST http://localhost:5001/query -H "Content-Type: application/json" -d '{"query": "best restaurants in the top 10 highest-rated cities"}'
```
Expected: JSON response with `"route": "HYBRID"`, both `"sql_result"` and `"vector_results"` populated

- [ ] **Step 7: Test CORS headers**

```bash
curl -I -X OPTIONS http://localhost:5001/query -H "Origin: http://example.com" -H "Access-Control-Request-Method: POST"
```
Expected: Response includes `Access-Control-Allow-Origin` header

---

### Task 5: Create `build/Dockerfile`

**Files:**
- Create: `build/Dockerfile`

- [ ] **Step 1: Create the Dockerfile**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cache layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (only what the API needs)
COPY config/ config/
COPY agents/ agents/
COPY utils/ utils/
COPY graph.py .
COPY api.py .

EXPOSE 5001

CMD ["python", "api.py"]
```

- [ ] **Step 2: Commit**

```bash
mkdir -p build
git add build/Dockerfile
git commit -m "build: add Dockerfile for Flask API container"
```

---

### Task 6: Create `build/docker-compose.yml`

**Files:**
- Create: `build/docker-compose.yml`

- [ ] **Step 1: Create the compose file**

```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    restart: unless-stopped

  api:
    build:
      context: ..
      dockerfile: build/Dockerfile
    ports:
      - "5001:5001"
    env_file:
      - ../.env
    environment:
      - QDRANT_HOST=qdrant
      - GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-credentials.json
    volumes:
      - ${GOOGLE_APPLICATION_CREDENTIALS}:/app/gcp-credentials.json:ro
    depends_on:
      - qdrant
    restart: unless-stopped

volumes:
  qdrant_data:
```

Note: `env_file: ../.env` loads all env vars. The `environment:` block overrides two values: `QDRANT_HOST=qdrant` (Docker service name instead of the host's value) and `GOOGLE_APPLICATION_CREDENTIALS=/app/gcp-credentials.json` (container path, not the host path from `.env`). The GCP credentials file is mounted as a read-only volume.

- [ ] **Step 2: Commit**

```bash
git add build/docker-compose.yml
git commit -m "build: add docker-compose for Qdrant + Flask API"
```

---

### Task 7: Verify Docker Compose locally

**Files:**
- None (manual verification)

- [ ] **Step 1: Build and start services**

```bash
docker compose -f build/docker-compose.yml up --build -d
```
Expected: Both `qdrant` and `api` containers start successfully

- [ ] **Step 2: Test health endpoint via Docker**

```bash
curl http://localhost:5001/health
```
Expected: `{"bigquery": true, "qdrant": true, "status": "ok"}` with HTTP 200

- [ ] **Step 3: Test query endpoint via Docker**

```bash
curl -X POST http://localhost:5001/query -H "Content-Type: application/json" -d '{"query": "find me cozy Italian restaurants in Phoenix"}'
```
Expected: JSON response with answer and transparency fields

- [ ] **Step 4: Stop containers**

```bash
docker compose -f build/docker-compose.yml down
```

---

### Task 8: Append Phase 7 to `docs/explanation.md`

**Files:**
- Modify: `docs/explanation.md` (append at end)

- [ ] **Step 1: Append Phase 7 documentation**

Append the following to the end of `docs/explanation.md`:

```markdown

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

### ### Deployment Checklist (on GCP VM via SSH)
After the Docker artifacts are ready, these manual steps are needed on the VM:

1. **Qdrant migration:** Stop the standalone Qdrant container, note its data volume path (`docker inspect qdrant | grep -A 10 Mounts`), update the compose volume to match, then `docker compose up -d`. Verify with `curl http://localhost:6333/collections`.
2. **Nginx update:** Add a reverse-proxy rule to forward traffic to `localhost:5001` for this project's subdomain/path. Without this, the API is not reachable from the internet.
3. **Cloudflare:** Ensure DNS points to the VM for the API subdomain.

### RAM Budget
Flask + LangGraph + LangChain fits well under 300MB — no ML models loaded locally, all inference is remote API calls to Gemini, BigQuery, and Qdrant.
```

- [ ] **Step 2: Commit**

```bash
git add -f docs/explanation.md
git commit -m "docs: append Phase 7 Flask API + deployment to explanation.md"
```

---

## Summary

| Task | What | Files |
|------|------|-------|
| 1 | Add flask-cors dependency | `requirements.txt` |
| 2 | APISettings + lazy YelpSettings | `config/settings.py` |
| 3 | Flask API module | `api.py` |
| 4 | Local verification (curl all endpoints) | — |
| 5 | Dockerfile | `build/Dockerfile` |
| 6 | Docker Compose | `build/docker-compose.yml` |
| 7 | Docker Compose local verification | — |
| 8 | Phase 7 documentation | `docs/explanation.md` |

Tasks 1-4 are sequential (each builds on the previous). Tasks 5-6 are independent of each other but depend on Task 3. Task 7 depends on Tasks 5-6. Task 8 is independent.
