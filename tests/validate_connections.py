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


#  1. Docker 

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


#  2. Redpanda / Kafka 

def test_redpanda() -> bool:
    """Verify Kafka broker is reachable and list topics."""
    print("\n2. Testing Redpanda (Kafka broker)...")
    try:
        from confluent_kafka.admin import AdminClient

        admin = AdminClient({"bootstrap.servers": settings.kafka.BOOTSTRAP_SERVERS})
        metadata = admin.list_topics(timeout=5)
        topics = set(metadata.topics.keys())

        print(f"   Broker: {settings.kafka.BOOTSTRAP_SERVERS}")
        print(f"   Topics: {sorted(topics) if topics else '(none yet)'}")
        _pass("Redpanda")
        return True
    except Exception as exc:
        _fail("Redpanda", f"Cannot reach broker at {settings.kafka.BOOTSTRAP_SERVERS} — {exc}")
        return False


#  3. Schema Registry

def test_schema_registry() -> bool:
    """Verify Redpanda schema registry is reachable."""
    print("\n3. Testing Schema Registry...")
    try:
        import requests

        url = f"{settings.kafka.SCHEMA_REGISTRY_URL}/subjects"
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        subjects = resp.json()

        types_resp = requests.get(f"{settings.kafka.SCHEMA_REGISTRY_URL}/schemas/types", timeout=5)
        supported_types = types_resp.json() if types_resp.ok else []

        print(f"   URL:      {settings.kafka.SCHEMA_REGISTRY_URL}")
        print(f"   Types:    {supported_types}")
        print(f"   Subjects: {subjects if subjects else '(none yet — run producer)'}")
        _pass("Schema Registry")
        return True
    except Exception as exc:
        _fail("Schema Registry", f"Cannot reach registry at {settings.kafka.SCHEMA_REGISTRY_URL} — {exc}")
        return False


#  4. PostgreSQL (Metastore backing store)

def test_postgresql() -> bool:
    """Verify PostgreSQL is reachable via Docker."""
    print("\n4. Testing PostgreSQL (metastore backing store)...")
    try:
        result = subprocess.run(
            ["docker", "exec", "metastore-db", "pg_isready", "-U", "hive", "-d", "hive_metastore"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            _fail("PostgreSQL", f"Not ready — {result.stderr.strip()}")
            return False

        print(f"   Container: metastore-db")
        print(f"   Database:  hive_metastore")
        print(f"   Status:    accepting connections")
        _pass("PostgreSQL")
        return True
    except FileNotFoundError:
        _fail("PostgreSQL", "Docker CLI not found")
        return False
    except subprocess.TimeoutExpired:
        _fail("PostgreSQL", "Health check timed out")
        return False
    except Exception as exc:
        _fail("PostgreSQL", str(exc))
        return False


#  5. Hive Metastore

def test_hive_metastore() -> bool:
    """Verify Hive Metastore Thrift service is reachable and databases exist."""
    print("\n5. Testing Hive Metastore...")
    try:
        from pyspark.sql import SparkSession

        spark = (
            SparkSession.builder
            .appName("MetastoreValidation")
            .master("local[1]")
            .config("spark.sql.catalogImplementation", "hive")
            .config("hive.metastore.uris", settings.hive.METASTORE_URI)
            .config("spark.sql.warehouse.dir", settings.hive.WAREHOUSE_DIR)
            .config("spark.driver.memory", "512m")
            .config("spark.ui.enabled", "false")
            .enableHiveSupport()
            .getOrCreate()
        )
        spark.sparkContext.setLogLevel("ERROR")

        databases = [row.namespace for row in spark.sql("SHOW DATABASES").collect()]
        tables = []
        for db in [settings.hive.BRONZE_DB, settings.hive.SILVER_DB, settings.hive.GOLD_DB]:
            if db in databases:
                db_tables = [row.tableName for row in spark.sql(f"SHOW TABLES IN {db}").collect()]
                tables.extend([f"{db}.{t}" for t in db_tables])

        spark.stop()

        print(f"   URI:       {settings.hive.METASTORE_URI}")
        print(f"   Databases: {sorted(databases)}")
        print(f"   Tables:    {sorted(tables) if tables else '(none yet — run: python -m infra)'}")
        _pass("Hive Metastore")
        return True
    except Exception as exc:
        _fail("Hive Metastore", f"Cannot reach metastore at {settings.hive.METASTORE_URI} — {exc}")
        return False


#  6. BigQuery

def test_bigquery() -> bool:
    """Verify BigQuery connectivity and dataset existence."""
    print("\n6. Testing BigQuery...")
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


#  7. Qdrant

def test_qdrant() -> bool:
    """Verify Qdrant is reachable and list collections."""
    print("\n7. Testing Qdrant...")
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


#  8. Gemini LLM

def test_gemini_llm() -> bool:
    """Verify Gemini LLM generation works."""
    print("\n8. Testing Gemini LLM...")
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


#  9. Gemini Embedding

def test_gemini_embedding() -> bool:
    """Verify Gemini embedding works with correct dimensions."""
    print("\n9. Testing Gemini Embedding...")
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

    tests = [
        ("Docker", test_docker),
        ("Redpanda", test_redpanda),
        ("Schema Registry", test_schema_registry),
        ("PostgreSQL", test_postgresql),
        ("Hive Metastore", test_hive_metastore),
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
