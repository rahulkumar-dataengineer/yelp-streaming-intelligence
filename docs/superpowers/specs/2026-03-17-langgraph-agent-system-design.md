# LangGraph Agent System Design

## Overview

Multi-agent pipeline for the Yelp Hybrid Streaming Agentic Platform. A Gemini-powered router classifies user queries into three paths — SQL analytics (BigQuery), semantic vector search (Qdrant), or a sequential hybrid pipeline — then a synthesizer produces a final natural language answer with routing transparency.

## Architecture

```
START → Router → ┬─ SQL ────→ SQL Agent ──────────────────→ Synthesizer → END
                 ├─ VECTOR ─→ Vector Agent ───────────────→ Synthesizer → END
                 └─ HYBRID ─→ SQL Agent → Vector Agent ──→ Synthesizer → END
```

**Design approach:** Flat graph (Approach A) with tool-based SQL agent (Approach C element). The router provides explicit, predictable classification at the top level. The SQL agent internally uses LangChain's ReAct-style SQL toolkit for flexible query generation. The vector agent is a simpler function-based node with fixed steps. This combination gives controlled routing with flexible execution where it adds value.

## Modules

**Package:** `agents/__init__.py` required for package imports (e.g., `from agents.router import classify` in `graph.py`).

### 1. `agents/state.py` — AgentState

TypedDict that flows through every node. Nodes read what they need, write their output.

```python
class AgentState(TypedDict):
    query: str                      # User's original question
    route: str                      # "SQL" | "VECTOR" | "HYBRID"
    sql_query: str                  # Generated SQL (transparency)
    sql_result: str                 # Formatted query results
    sql_business_ids: list[str]     # HYBRID: passed to vector agent
    vector_results: list[dict]      # Top-K matches with payload + scores
    error: str                      # Error message if an agent fails
    answer: str                     # Final natural language answer
```

**Data flow by route:**

- **SQL:** router sets `route="SQL"` → sql_agent fills `sql_query` + `sql_result` → synthesizer reads `sql_result`, produces `answer`
- **VECTOR:** router sets `route="VECTOR"` → vector_agent fills `vector_results` → synthesizer reads `vector_results`, produces `answer`
- **HYBRID:** router sets `route="HYBRID"` → sql_agent fills `sql_result` + `sql_business_ids` → vector_agent reads `sql_business_ids` as Qdrant filter, fills `vector_results` → synthesizer reads both, produces `answer`
- **Error flow:** If any agent fails, it sets `error` with a brief message. The synthesizer checks `error` first — distinguishes "no results found" from "agent encountered a temporary issue, please try again."

### 2. `agents/router.py` — Query Classifier

Single Gemini call. Cheapest node — one LLM call with `thinking_level="minimal"`.

**Input:** `query` from state
**Output:** `route` ("SQL" / "VECTOR" / "HYBRID")

- Uses `ChatGoogleGenerativeAI` from `langchain-google-genai` with model ID from `config/settings.py`
- System prompt defines three routes with examples:
  - **SQL** — aggregations, counts, averages, rankings by numeric fields, structured filters (e.g., "average rating for restaurants in Phoenix", "how many 5-star businesses in Arizona")
  - **VECTOR** — vibe, ambiance, sentiment, subjective quality, recommendations (e.g., "cozy Italian place with great wine", "romantic dinner spot with quiet atmosphere")
  - **HYBRID** — combines subjective intent with complex structured filtering, or router is uncertain (e.g., "best restaurants in the top 10 highest-rated cities")
- LLM returns JSON: `{"route": "SQL" | "VECTOR" | "HYBRID"}`
- Falls back to HYBRID if parsing fails (safe default — covers both paths)

### 3. `agents/sql_agent.py` — BigQuery SQL Agent

ReAct-style agent using LangChain's SQL toolkit. Most autonomous node — LLM reasons about schema, writes SQL, executes, interprets.

**Input:** `query`, `route`
**Output:** `sql_query`, `sql_result`, optionally `sql_business_ids` (HYBRID)

**Setup:**

- `SQLDatabase` wraps SQLAlchemy engine via `sqlalchemy-bigquery` dialect
- Points to deduped view (`gold_reviews_deduped`) only — avoids duplicates inflating aggregations
- **Critical:** `SQLDatabase` must be initialized with `view_support=True` since `gold_reviews_deduped` is a view, not a table. Without this, LangChain's `get_table_names()` won't find it and raises `ValueError`.
- `SQLDatabaseToolkit` provides tools: `sql_db_list_tables`, `sql_db_schema`, `sql_db_query`, `sql_db_query_checker` (validates SQL before execution — useful safety layer for 7M rows)
- Agent created via `create_sql_agent()` with Gemini LLM
- **Import:** `from langchain_community.agent_toolkits.sql.base import create_sql_agent` — returns a legacy `AgentExecutor`. Call via `.invoke({"input": query})`. If this causes issues during implementation, fall back to building the agent manually with SQL toolkit tools directly.

**Guardrails (7M rows):**

- **View-only:** `SQLDatabase` initialized with `include_tables=["gold_reviews_deduped"]` and `view_support=True`
- **Row limit:** System prompt requires `LIMIT 50` on all queries unless explicitly asked for more
- **Column selection:** System prompt forbids `SELECT *` — only select columns relevant to the question
- **Cost awareness:** System prompt states table has ~7M rows, emphasizes `WHERE` clauses and aggregations over raw row returns. Note: the deduped view forces a full table scan. With 1TB/month free query quota, budget approximately 200-500 queries/month depending on column selection. Sufficient for portfolio traffic.
- **HYBRID behavior:** When `route == "HYBRID"`, system prompt instructs the agent to include `business_id` in SELECT and extract IDs into `sql_business_ids`. Safety net: `LIMIT 200` on HYBRID queries to keep Qdrant `MatchAny` filter performant on `on_disk=True` storage. The SQL agent's `WHERE` clause should narrow naturally, but the limit prevents accidental blowup.

### 4. `agents/vector_agent.py` — Qdrant Semantic Search

Function-based node (not ReAct). Steps are always the same: extract filters, embed, search, return.

**Input:** `query`, optionally `sql_business_ids` (HYBRID)
**Output:** `vector_results` (list of dicts with payload + similarity scores)

**Phase 1 — Filter extraction:**

- Single Gemini call to extract structured filters from natural language
- System prompt lists the 17 available payload fields and their types/possible values
- LLM returns JSON like `{"city": "Phoenix", "categories": "Italian", "restaurants_price_range": 2}`
- If HYBRID: skips LLM extraction, uses `sql_business_ids` as sole Qdrant filter (SQL already filtered)

**Retry strategy:** Both the filter-extraction LLM call and the embedding call use `tenacity` with exponential backoff (matching the gold layer's `GeminiEmbedder` pattern) for 429/5xx errors.

**Phase 2 — Qdrant search:**

- Embed query using `google-genai` SDK directly (`from google import genai`) — matches the gold layer's `GeminiEmbedder` pattern and authentication path via `settings.gemini.API_KEY`. Do NOT use `langchain-google-genai` embeddings here.
- `task_type=RETRIEVAL_QUERY` and `output_dimensionality=768`
- Build Qdrant `Filter` from extracted fields (or `business_id` IN list for HYBRID)
- `client.search()` with `limit=10`
- Return results as list of dicts: `{name, city, state, categories, review_stars, business_stars, text, score}`

**Filter matching:**

- `city`, `state`: exact match (case-insensitive)
- `categories`: substring match via Qdrant `MatchText` (categories is comma-separated, e.g., "Restaurants, Italian, Pizza")
- `restaurants_price_range`: exact numeric match
- `noise_level`, `alcohol`, `wifi`: exact string match
- Unrecognized/empty filters: skip, let cosine similarity rank alone

### 5. `agents/synthesizer.py` — Answer Generation

Single Gemini call turning raw agent outputs into a conversational answer.

**Input:** `query`, `route`, `sql_query`, `sql_result`, `vector_results`, `error`
**Output:** `answer`

- System prompt: "You are a Yelp restaurant expert. Synthesize the retrieved data into a helpful, conversational answer."
- User message assembled dynamically by route:
  - **SQL:** includes `sql_result`
  - **VECTOR:** includes `vector_results` (names, ratings, review snippets, scores)
  - **HYBRID:** includes both — SQL context + vector-ranked recommendations
- Instructions:
  - Reference specific business names, ratings, review quotes from the data
  - Do not hallucinate businesses not in the results
  - Concise: 3-5 sentences for simple queries, short paragraph for complex
- **Routing transparency:** Appended to every answer: `\n\n---\nRouted as: {route}`

**Edge cases:**

- `error` is set: synthesizer returns a user-friendly error message (e.g., "I encountered a temporary issue, please try again") — distinguishes from "no results"
- Empty `sql_result` (no error): "I couldn't find data matching that query"
- Empty `vector_results` (no error): honest "no results" response
- Both empty (HYBRID both failed): graceful fallback message

### 6. `graph.py` — LangGraph StateGraph

Pure wiring — no business logic. Compiles the graph and provides CLI entry point.

**Nodes:**

| Node | Function |
|------|----------|
| `router` | `agents.router.classify` |
| `sql_agent` | `agents.sql_agent.run` |
| `vector_agent` | `agents.vector_agent.run` |
| `synthesizer` | `agents.synthesizer.run` |

**Edges:**

```
START → router

router → conditional:
  SQL    → sql_agent
  VECTOR → vector_agent
  HYBRID → sql_agent

sql_agent → conditional:
  SQL    → synthesizer
  HYBRID → vector_agent

vector_agent → synthesizer
synthesizer  → END
```

**CLI entry point:**

```bash
python graph.py "find me cozy Italian restaurants in Phoenix"
# Expected: routes VECTOR, returns vibe-based results

python graph.py "what's the average rating for restaurants in Scottsdale"
# Expected: routes SQL, returns aggregation
```

## Key Design Decisions

### Why explicit router over LLM tool selection

Enterprise systems favor explicit routing for cost control and predictability. A single classification call with `thinking_level="minimal"` is cheaper and more debuggable than letting a ReAct agent decide freely across tools. The router makes the system's decision-making transparent and testable.

### Why HYBRID is sequential, not parallel

A query like "best Italian restaurants in Phoenix" (when the filter field isn't in Qdrant) needs SQL to identify candidates first, then Vector to rank them semantically. `business_id` is the universal join key. Parallel execution would return independent results that can't be meaningfully combined — you'd get an average rating AND a list of vibes, not vibes for the right businesses.

### Why vector agent is function-based, not ReAct

The steps are always identical: extract filters → embed → search → return. There's no branching logic that benefits from multi-step LLM reasoning. A function is faster, cheaper, and more predictable.

### Why deduped view for SQL

The `gold_reviews_deduped` view uses `ROW_NUMBER() OVER (PARTITION BY review_id ORDER BY ingestion_timestamp DESC)` to keep only the latest version of each review. Without this, aggregations on 7M rows would be inflated by duplicate records from reprocessing.

### HYBRID business_id safety net

With 7M rows, an unfiltered `SELECT DISTINCT business_id` could return hundreds of thousands of IDs. The `LIMIT 200` safety net keeps Qdrant `MatchAny` filter performant on `on_disk=True` storage. The SQL agent's `WHERE` clause should narrow this naturally, but the limit prevents accidental blowup.

## Dependencies

All already pinned in `requirements.txt`:

- `langchain==1.0.1` — core framework
- `langchain-core==1.2.16` — base abstractions
- `langchain-community==0.4.1` — community integrations
- `langchain-google-genai==4.2.1` — Gemini LLM + embeddings
- `langgraph==1.0.9` — graph orchestration
- `google-genai==1.65.0` — Gemini API client
- `google-cloud-bigquery==3.27.0` — BigQuery client
- `qdrant-client==1.12.1` — vector DB client
- `sqlalchemy==2.0.38` + `sqlalchemy-bigquery==1.12.0` — SQL toolkit backend
- `flask==3.1.0` — API server (Phase 3)
- `tenacity==9.0.0` — retry/backoff

## Configuration

All model IDs and connection details sourced from `config/settings.py`. No hardcoded strings.

- LLM: `settings.gemini.MODEL` (`gemini-3.1-flash-lite-preview`)
- Embedding: `settings.gemini.EMBEDDING_MODEL` (`gemini-embedding-001`)
- Embedding dimensions: `settings.gemini.EMBEDDING_DIMENSIONS` (768)
- BigQuery: `settings.gcp.PROJECT_ID`, `settings.gcp.BIGQUERY_DATASET`, `settings.gcp.BIGQUERY_TABLE`
- Qdrant: `settings.qdrant.HOST`, `settings.qdrant.PORT`, `settings.qdrant.COLLECTION`

## Verification

```bash
# Vector route — subjective/vibe query
python graph.py "find me cozy Italian restaurants in Phoenix"

# SQL route — aggregation query
python graph.py "what's the average rating for restaurants in Scottsdale"

# Hybrid route (optional) — complex mixed query
python graph.py "best restaurants in the top 10 highest-rated cities"
```

Each should print: the final answer + routing transparency line (`Routed as: SQL/VECTOR/HYBRID`).
