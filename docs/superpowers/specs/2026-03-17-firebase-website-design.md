# Firebase Website Design Spec

**Date:** 2026-03-17
**Status:** Draft
**Depends on:** Phase 7 Flask API (deployed and working)

## Overview

Portfolio showcase + live chat interface deployed on Firebase Hosting (Spark plan, static only). A single `index.html` file with inline CSS and vanilla JS — zero dependencies, zero build step.

**Target audience:** Hiring managers for Lead/Principal Data Engineer roles. They spend 2-3 minutes max. The page must impress in 5 seconds and give them something to interact with immediately.

**Core narrative:** "I'm a data engineer who builds the infrastructure that makes AI work."

## Architecture

```
firebase/public/index.html  →  Firebase Hosting (Spark plan)
                                    ↓
                            User's browser
                                    ↓ fetch()
                        https://34-10-46-213.sslip.io/query   (POST)
                        https://34-10-46-213.sslip.io/health  (GET)
```

Static HTML served from Firebase. All interactivity is client-side JS hitting the Flask API on the GCP VM via HTTPS.

## Page Layout

### Chat-Forward Design

The chat interface IS the landing page. No hero section, no scrolling past content to find the demo. The hiring manager lands and can immediately start asking questions.

```
┌──────────────────────────────────────────────────┐
│  [≡ About]    Yelp Streaming Intelligence    [?] │  ← Slim header bar
├──────────────────────────────────────────────────┤
│                                                  │
│         Welcome message + 3 example              │
│         queries as clickable chips               │
│                                                  │
│    "cozy Italian restaurants in Phoenix"          │
│    "average rating in Scottsdale"                 │
│    "best restaurants in top-rated cities"         │
│                                                  │
│  ┌─────────────────────────────────────────────┐ │
│  │  Chat messages scroll here                  │ │
│  │                                             │ │
│  │  [User bubble — right-aligned]              │ │
│  │  [Bot bubble + route badge — left-aligned]  │ │
│  │    ▸ Show how this was answered             │ │
│  │                                             │ │
│  └─────────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────┐ ┌────┐ │
│  │  Ask about Yelp businesses…         │ │ ➤  │ │  ← Input pinned to bottom
│  └─────────────────────────────────────┘ └────┘ │
└──────────────────────────────────────────────────┘
```

### Behaviors

- **Example chips** disappear after the first message is sent
- **Welcome message** briefly explains what this is (one sentence) and what kinds of questions work
- **Chat auto-scrolls** to newest message
- **Loading state:** Animated pulsing dots while API responds (queries take 5-30s)
- **Input disabled** while waiting for response
- **Enter** to send, **Shift+Enter** for newline
- **Empty query** is ignored (no send)

### Slide-Out Drawer (≡ About)

Triggered by the "≡ About" button in the header. Slides in from the left. Chat is dimmed behind it.

```
┌─────────────────────┬────────────────────────────┐
│  ✕ About            │  (chat dimmed behind)      │
│                     │                            │
│  One-liner pitch    │                            │
│                     │                            │
│  Architecture       │                            │
│  Diagram (CSS)      │                            │
│                     │                            │
│  Tech Stack Grid    │                            │
│                     │                            │
│  Why This Matters   │                            │
│  • 4 bullets        │                            │
│                     │                            │
│  GitHub link        │                            │
└─────────────────────┴────────────────────────────┘
```

## Chat Message Anatomy

### User Messages
Right-aligned bubbles, lighter background (`#252540`).

### Bot Messages — Three Layers

**1. Answer bubble** — Synthesizer's natural language response. Dark card (`#1a1a2e`) with light text, left-aligned.

**2. Route badge** — Small pill at the bottom of the answer:
- `SQL` — blue (`#3b82f6`)
- `VECTOR` — purple (`#8b5cf6`)
- `HYBRID` — cyan-to-purple gradient (`#00d4ff → #8b5cf6`)

**3. Expandable details** — "▸ Show how this was answered" toggle below the bubble. Collapsed by default. When expanded, shows:

- **Route label** (e.g., "Routed as: HYBRID")
- **SQL Query** (if present) — monospace code block with the generated SQL
- **SQL Result** (if present) — the agent's summary text
- **Vector Matches** (if present) — cards showing:
  - Business name, city, star rating
  - Similarity score
  - Review text snippet (truncated)

### Error State
If the API returns an error or the `error` field in the response is populated:
- Red-tinted bubble with the error message
- "Try again" button that re-sends the last query

## About Drawer Content

### One-Liner Pitch
> "A real-time streaming platform that builds the data infrastructure AI agents need — medallion pipelines feeding dual sinks, with an agentic layer that decides how to answer."

### Architecture Diagram
CSS-rendered flow diagram (not an image — stays crisp at any size):

```
Yelp Data → Redpanda → Bronze → Silver → Gold ──→ BigQuery (SQL)
                                              └──→ Qdrant (Vectors)
                                                        ↓
                                    User ← Synthesizer ← Agent Router
```

Simplified pipeline view. Nodes as rounded boxes with connecting lines/arrows. Cyan accent color for arrows.

### Tech Stack Grid

| Layer | Tech |
|-------|------|
| Streaming | Redpanda (Kafka), PySpark |
| Structured Store | BigQuery (free tier) |
| Vector Store | Qdrant (self-hosted) |
| LLM / Embeddings | Gemini Flash-Lite, gemini-embedding-001 |
| Agent Orchestration | LangGraph + LangChain |
| API | Flask on GCP e2-micro |
| Frontend | Firebase Hosting (static) |

Compact 2-column layout. No logos (avoid asset management for a single-file approach) — just clean text with subtle styling.

### "Why This Matters" — 4 Bullets

1. **Medallion architecture for AI-ready data** — Bronze/Silver/Gold streaming pipeline that cleans, joins, and shapes 1M+ reviews into formats both SQL engines and vector databases can serve. The AI layer doesn't wrangle data — it consumes clean, typed, deduplicated outputs.

2. **Dual-sink design** — A single streaming job fans out to BigQuery (structured analytics) and Qdrant (semantic search) independently. The agent decides which sink to query — I made sure both are always current and consistent.

3. **Agentic routing over structured + unstructured data** — An explicit LLM router classifies queries into SQL, Vector, or Hybrid paths. Not a free-form ReAct agent — a deliberate, cost-controlled routing decision. Hybrid runs sequentially: SQL narrows candidates, Vector ranks semantically.

4. **Zero-cost production deployment** — The entire platform runs at $0/month on GCP free tier. 1GB RAM VM serving Qdrant + Flask, BigQuery sandbox for analytics, Gemini free tier for LLM + embeddings. Engineering within constraints, not throwing money at problems.

### Footer
GitHub repo link.

## Visual Style

**Theme:** Dark + data/AI (Databricks/Snowflake/Qdrant marketing aesthetic).

### Colors

| Element | Color | Hex |
|---------|-------|-----|
| Background | Near-black | `#0a0a0f` |
| Background pattern | Subtle dot grid | `#1a1a2e` at low opacity |
| Card / bubble (bot) | Dark grey | `#1a1a2e` |
| Card border | Subtle | `#2a2a4a` |
| User bubble | Slightly lighter | `#252540` |
| Primary accent | Electric cyan | `#00d4ff` |
| Secondary accent | Soft purple | `#8b5cf6` |
| Body text | Light grey | `#e0e0e0` |
| Heading text | Bright white | `#f0f0f0` |
| Code blocks | Darker background | `#0d0d1a` |
| SQL badge | Blue | `#3b82f6` |
| VECTOR badge | Purple | `#8b5cf6` |
| HYBRID badge | Gradient | `#00d4ff → #8b5cf6` |
| Error | Red-tinted | `#ff4444` at low opacity bg |

### Typography

- **Body:** System font stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`)
- **Code / SQL:** Monospace (`'SF Mono', 'Fira Code', 'Cascadia Code', monospace`)
- **Sizes:** 14px body, 13px code, 12px badges, 16px headings

### Animations

- **New messages:** Subtle fade-in
- **Drawer:** Smooth slide from left (300ms ease)
- **Loading dots:** Pulsing animation
- **Expandable details:** Smooth height transition
- **Example chips:** Fade out on first message send

## API Integration

### Query Endpoint

```
POST https://34-10-46-213.sslip.io/query
Content-Type: application/json

{"query": "cozy Italian restaurants in Phoenix"}
```

**Response fields used:**
- `answer` — displayed in the chat bubble
- `route` — determines badge color (SQL / VECTOR / HYBRID)
- `sql_query` — shown in expandable details (if present)
- `sql_result` — shown in expandable details (if present)
- `vector_results` — shown as match cards in expandable details (if present)
- `error` — triggers error state display

### Health Endpoint

```
GET https://34-10-46-213.sslip.io/health
```

Not exposed in the UI. Could optionally show a status indicator in the header, but not required for v1.

### Answer Text Cleanup

The synthesizer appends `\n\n---\nRouted as: {route}` to the `answer` field for transparency. Since the UI displays the route as a separate badge, the frontend must strip this suffix before rendering the answer text. Match and remove the trailing `---\nRouted as: ...` block.

### Error Handling

- **Network error** (API unreachable): Show error bubble with "The API is currently unavailable. Please try again later."
- **API error** (error field populated): Show the error message from the response
- **Timeout:** No explicit client-side timeout — the loading dots persist until the API responds or the connection drops. Queries can legitimately take 30s+ for HYBRID routes.

## Prerequisites

### Firebase Project Setup (manual, one-time)

1. Create a Firebase project on the **Spark (free) plan** — either via [Firebase console](https://console.firebase.google.com) or `firebase projects:create <project-id>`
2. Run `firebase use <project-id>` inside the `firebase/` directory to link the local config to the project
3. Verify with `firebase projects:list` — the new project should appear
4. No Blaze upgrade needed — Spark plan provides 1GB storage + 10GB transfer/month for static hosting, which is all we use

This project does NOT use Cloud Functions, Firestore, Auth, or any other Firebase service — just Hosting.

## File Structure

```
firebase/
├── public/
│   ├── index.html    ← Single file: HTML + inline CSS + inline JS
│   └── 404.html      ← Already exists, keep as-is
└── firebase.json      ← Already exists, update if needed
```

Everything lives in `index.html`. No external CSS files, no JS files, no images, no build step.

## Firebase Configuration

Current `firebase.json` is sufficient:
```json
{
  "hosting": {
    "public": "public",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"]
  }
}
```

No changes needed unless we add SPA routing (not planned).

## Constraints

- **Firebase Spark plan:** 1GB storage, 10GB transfer/month. A single HTML file is ~20-50KB — well within limits.
- **No Firebase SDK needed:** The current `index.html` loads Firebase SDK scripts — these should be removed. We don't use Auth, Firestore, Functions, or any Firebase backend services. Pure static hosting.
- **No Cloud Functions:** All dynamic behavior is client-side JS hitting the external Flask API.
- **CORS:** The Flask API has `CORS_ORIGIN` configured. May need to set it to the Firebase Hosting domain after deployment.
- **API URL:** Hardcoded to `https://34-10-46-213.sslip.io`. If the VM IP changes, the HTML must be updated and redeployed.

## Out of Scope

- Authentication / user sessions
- Chat history persistence (refreshing the page clears chat)
- Mobile-optimized layout (should be responsive but not the primary target)
- Analytics / tracking
- Rate limiting on the frontend
- Health status indicator in the UI
