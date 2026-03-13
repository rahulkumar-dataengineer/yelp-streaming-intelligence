"""
Validation Script

Tests connectivity to all external services independently.
Each test prints PASS or FAIL with a clear error message.

Services tested:
    1. Docker        — daemon is running
    2. Redpanda      — Kafka broker reachable, topics accessible
    3. BigQuery      — dataset exists, Load API available
    4. Qdrant        — reachable on configured host:port
    5. Gemini LLM    — generation call succeeds
    6. Gemini Embed  — embedding call returns correct dimensions

Usage:
    python -m tests.validate_connections
"""

import subprocess
import sys

from config.settings import settings


def _pass(service: str, detail: str = "") -> None:
    msg = f"----- PASS ----- [{service}]"
    if detail:
        msg += f" {detail}"
    print(msg)


def _fail(service: str, error: str) -> None:
    print(f"xxxxx FAIL xxxxx [{service}] : {error}")


# ── 1. Docker ──────────────────────────────────────────────────────────────

def test_docker() -> bool:
    """Verify Docker daemon is running."""
    print("\n1. Testing Docker...")
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        if result.returncode != 0:
            _fail("Docker", "Docker daemon is not running. Start Docker Desktop.")
            return False
        _pass("Docker", "daemon is running")
        return True
    except FileNotFoundError:
        _fail("Docker", "Docker CLI not found. Install Docker Desktop.")
        return False
    except subprocess.TimeoutExpired:
        _fail("Docker", "Docker command timed out")
        return False


# ── 2. Redpanda / Kafka ───────────────────────────────────────────────────

def test_redpanda() -> bool:
    """Verify Kafka broker is reachable and list topics."""
    print("\n2. Testing Redpanda (Kafka broker)...")
    try:
        from kafka import KafkaConsumer

        consumer = KafkaConsumer(
            bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
            request_timeout_ms=5000,
        )
        topics = consumer.topics()
        consumer.close()

        print(f"   Broker: {settings.kafka.BOOTSTRAP_SERVERS}")
        print(f"   Topics: {sorted(topics) if topics else '(none yet)'}")
        _pass("Redpanda")
        return True
    except Exception as exc:
        _fail("Redpanda", f"Cannot reach broker at {settings.kafka.BOOTSTRAP_SERVERS} — {exc}")
        return False


# ── 3. BigQuery ────────────────────────────────────────────────────────────

def test_bigquery() -> bool:
    """Verify BigQuery connectivity and dataset existence."""
    print("\n3. Testing BigQuery...")
    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=settings.gcp.PROJECT_ID)

        # Check dataset exists
        dataset_ref = f"{settings.gcp.PROJECT_ID}.{settings.gcp.BIGQUERY_DATASET}"
        dataset = client.get_dataset(dataset_ref)
        print(f"   Project:  {settings.gcp.PROJECT_ID}")
        print(f"   Dataset:  {dataset.dataset_id}")
        print(f"   Location: {dataset.location}")

        # Verify query works
        query = f"SELECT 1 AS test"
        result = list(client.query(query).result())
        print(f"   Query:    test query returned {result[0].test}")

        _pass("BigQuery")
        return True
    except Exception as exc:
        _fail("BigQuery", str(exc))
        return False


# ── 4. Qdrant ──────────────────────────────────────────────────────────────

def test_qdrant() -> bool:
    """Verify Qdrant is reachable and list collections."""
    print("\n4. Testing Qdrant...")
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


# ── 5. Gemini LLM ─────────────────────────────────────────────────────────

def test_gemini_llm() -> bool:
    """Verify Gemini LLM generation works."""
    print("\n5. Testing Gemini LLM...")
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


# ── 6. Gemini Embedding ───────────────────────────────────────────────────

def test_gemini_embedding() -> bool:
    """Verify Gemini embedding works with correct dimensions."""
    print("\n6. Testing Gemini Embedding...")
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


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    """Run all connectivity tests and print summary."""
    print("=" * 60)
    print("  Yelp Streaming Intelligence — Connection Validation")
    print("=" * 60)

    tests = [
        ("Docker", test_docker),
        ("Redpanda", test_redpanda),
        ("BigQuery", test_bigquery),
        ("Qdrant", test_qdrant),
        ("Gemini LLM", test_gemini_llm),
        ("Gemini Embedding", test_gemini_embedding),
    ]

    results = {}
    for name, test_fn in tests:
        results[name] = test_fn()

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    all_passed = True
    for service, passed in results.items():
        if passed:
            _pass(service)
        else:
            _fail(service, "see details above")
            all_passed = False

    if all_passed:
        print("\nAll services connected.")
    else:
        print("\nFix the FAIL(s) above before proceeding.")

    print("=" * 60)
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
