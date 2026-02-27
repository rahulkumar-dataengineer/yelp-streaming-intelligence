# yelp-streaming-intelligence
Ask "find me a cozy Italian spot on a rainy evening" and get results. A real-time Yelp streaming pipeline with an AI agent that combines SQL analytics and semantic vector search.


## Architecture Overview

### Data Flow

```
Yelp JSON Files
     │
     ▼
┌─────────────────┐
│  producer.py    │  Reads business.json + review.json, joins on business_id,
│  (kafka-python) │  streams ~500 msg/sec as JSON payloads
└────────┬────────┘
         │ Kafka Protocol (port 9092)
         ▼
┌─────────────────┐
│   Redpanda      │  Kafka-compatible message broker running in Docker.
│  (Docker)       │  Topic: yelp_stream
└────────┬────────┘
         │ Spark Kafka Source
         ▼
┌──────────────────────────────────────────────┐
│         spark_stream.py (PySpark)            │
│         Structured Streaming + foreachBatch  │
└────────────┬─────────────────────┬───────────┘
             │                     │
     Branch A│                     │Branch B
             ▼                     ▼
   ┌──────────────────┐   ┌──────────────────────┐
   │  Google BigQuery  │   │  Pinecone Serverless  │
   │  (yelp_analytics) │   │  (yelp-reviews index) │
   │  Structured rows  │   │  384-dim embeddings   │
   └────────┬──────────┘   └──────────┬────────────┘
            │                         │
            └────────────┬────────────┘
                         │
                         ▼
          ┌───────────────────────────────┐
          │  LangGraph Multi-Agent System │
          │  ┌──────────┐                 │
          │  │  Router  │ (Gemini Flash)  │
          │  └────┬─────┘                 │
          │  ┌────┴──────────────┐        │
          │  │                   │        │
          │  ▼                   ▼        │
          │ SQL Agent      Vector Agent   │
          │ (BigQuery)     (Pinecone)     │
          │        └────┬────┘            │
          │             ▼                 │
          │       Synthesizer             │
          │       (Gemini Flash)          │
          └──────────────┬────────────────┘
                         │
                         ▼
            ┌─────────────────────────┐
            │  Streamlit Web App      │
            │  (Streamlit Cloud)      │
            └─────────────────────────┘
```

### Technologies Used

| Technology | Role |
|---|---|
| **Redpanda** | Kafka-compatible message broker. Runs locally in Docker with zero JVM overhead |
| **kafka-python-ng** | Python producer client that streams Yelp records at ~500 msg/sec |
| **PySpark Structured Streaming** | Distributed stream processor consuming from Redpanda with exactly-once semantics |
| **Google BigQuery** | Cloud analytical data warehouse storing structured business and review data |
| **Pinecone Serverless** | Vector database storing 384-dim semantic embeddings for similarity search |
| **sentence-transformers (all-MiniLM-L6-v2)** | Local embedding model producing 384-dim float vectors — no API cost |
| **Google Gemini 2.5 Flash** | LLM powering the router, SQL agent, and answer synthesizer |
| **LangGraph** | Stateful multi-agent orchestration framework managing query routing and agent execution |
| **LangChain** | Abstractions for SQL agent, vector store integration, and LLM connectors |
| **Streamlit** | Python-native web framework for the recruiter-facing chat interface |
| **Streamlit Community Cloud** | Free public deployment target — provides a permanent HTTPS URL |

### Prerequisites

**Software:**
- Python 3.11
- Docker Desktop (for Redpanda)
- Git

**Cloud Accounts (all free tier):**
- Google Cloud Platform — BigQuery enabled, service account with BigQuery Editor role
- Pinecone — Serverless index named `yelp-reviews` (384 dims, cosine metric)
- Google AI Studio — Gemini API key

**Data:**
- Yelp Open Dataset: `yelp_academic_dataset_business.json` + `yelp_academic_dataset_review.json`
- Download from: https://www.yelp.com/dataset
