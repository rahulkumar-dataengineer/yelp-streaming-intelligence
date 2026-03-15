"""
Validation Script

Tests connectivity to all external services independently.
Each test prints PASS or FAIL with a clear error message.

Services tested:
    1. Docker           — daemon is running
    2. Redpanda         — Kafka broker reachable, topics accessible
    3. Schema Registry  — Redpanda schema registry reachable
    4. PostgreSQL       — metastore backing store reachable
    5. Hive Metastore   — Thrift service reachable, databases exist
    6. BigQuery         — dataset exists, Load API available
    7. Qdrant           — reachable on configured host:port
    8. Gemini LLM       — generation call succeeds
    9. Gemini Embed     — embedding call returns correct dimensions

Usage:
    python -m tests.validate_connections
"""

import sys

from config.settings import settings
from platform_commons.testing.validators import (
    _fail,
    _pass,
    run_all,
    test_docker,
    test_hive_metastore,
    test_kafka,
    test_postgresql,
    test_schema_registry,
)


#  6. BigQuery (project-specific)

def test_bigquery() -> bool:
    """Verify BigQuery connectivity and dataset existence."""
    print("\nTesting BigQuery...")
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=settings.gcp.PROJECT_ID)

        dataset_ref = f"{settings.gcp.PROJECT_ID}.{settings.gcp.BIGQUERY_DATASET}"
        dataset = client.get_dataset(dataset_ref)
        print(f"   Project:  {settings.gcp.PROJECT_ID}")
        print(f"   Dataset:  {dataset.dataset_id}")
        print(f"   Location: {dataset.location}")

        query = "SELECT 1 AS test"
        result = list(client.query(query).result())
        print(f"   Query:    test query returned {result[0].test}")

        _pass("BigQuery")
        return True
    except Exception as exc:
        _fail("BigQuery", str(exc))
        return False


#  7. Qdrant (project-specific)

def test_qdrant() -> bool:
    """Verify Qdrant is reachable and list collections."""
    print("\nTesting Qdrant...")
    try:
        from qdrant_client import QdrantClient

        client = QdrantClient(
            host=settings.qdrant.HOST,
            port=settings.qdrant.PORT,
            timeout=5,
        )
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]

        print(f"   Host:        {settings.qdrant.HOST}:{settings.qdrant.PORT}")
        print(f"   Collections: {collection_names if collection_names else '(none yet)'}")
        _pass("Qdrant")
        return True
    except Exception as exc:
        _fail("Qdrant", f"Cannot reach Qdrant at {settings.qdrant.HOST}:{settings.qdrant.PORT} — {exc}")
        return False


#  8. Gemini LLM (project-specific)

def test_gemini_llm() -> bool:
    """Verify Gemini LLM generation works."""
    print("\nTesting Gemini LLM...")
    try:
        from google import genai

        client = genai.Client(api_key=settings.gemini.API_KEY)
        response = client.models.generate_content(
            model=settings.gemini.MODEL,
            contents="Reply with exactly one word: OK",
        )
        reply = response.text.strip()

        print(f"   Model:    {settings.gemini.MODEL}")
        print(f"   Response: '{reply}'")
        _pass("Gemini LLM")
        return True
    except Exception as exc:
        _fail("Gemini LLM", str(exc))
        return False


#  9. Gemini Embedding (project-specific)

def test_gemini_embedding() -> bool:
    """Verify Gemini embedding works with correct dimensions."""
    print("\nTesting Gemini Embedding...")
    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=settings.gemini.API_KEY)
        result = client.models.embed_content(
            model=settings.gemini.EMBEDDING_MODEL,
            contents="test embedding connectivity",
            config=types.EmbedContentConfig(
                output_dimensionality=settings.gemini.EMBEDDING_DIMENSIONS,
                task_type="RETRIEVAL_DOCUMENT",
            ),
        )
        dims = len(result.embeddings[0].values)

        print(f"   Model:      {settings.gemini.EMBEDDING_MODEL}")
        print(f"   Dimensions: {dims} (expected {settings.gemini.EMBEDDING_DIMENSIONS})")

        if dims != settings.gemini.EMBEDDING_DIMENSIONS:
            _fail("Gemini Embedding", f"Got {dims} dims, expected {settings.gemini.EMBEDDING_DIMENSIONS}")
            return False

        _pass("Gemini Embedding")
        return True
    except Exception as exc:
        _fail("Gemini Embedding", str(exc))
        return False


#  Main

def main() -> None:
    """Run all connectivity tests and print summary."""
    print("=" * 60)
    print("  Yelp Streaming Intelligence — Connection Validation")
    print("=" * 60)

    # Shared infra tests (from platform_commons) + project-specific tests
    tests = [
        ("Docker", test_docker),
        ("Redpanda", lambda: test_kafka(settings.kafka.BOOTSTRAP_SERVERS)),
        ("Schema Registry", lambda: test_schema_registry(settings.kafka.SCHEMA_REGISTRY_URL)),
        ("PostgreSQL", test_postgresql),
        ("Hive Metastore", lambda: test_hive_metastore(
            settings.hive.METASTORE_URI,
            settings.hive.WAREHOUSE_DIR,
            [settings.hive.BRONZE_DB, settings.hive.SILVER_DB, settings.hive.GOLD_DB],
        )),
        ("BigQuery", test_bigquery),
        ("Qdrant", test_qdrant),
        ("Gemini LLM", test_gemini_llm),
        ("Gemini Embedding", test_gemini_embedding),
    ]

    all_passed = run_all(tests)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
