"""Verify both Gold layer sinks: BigQuery row count + Qdrant vector count.

Also runs a test similarity search against Qdrant to confirm vectors
are searchable.

Usage:
    python check_sinks.py
"""

from google.cloud import bigquery
from google.oauth2 import service_account
from google import genai
from google.genai import types as genai_types
from qdrant_client import QdrantClient

from config.settings import settings


# -------------------------
# BigQuery check
# -------------------------

def check_bigquery() -> int:
    """Returns the row count in the Gold BigQuery table."""

    print("\n--- BigQuery ---")
    credentials = service_account.Credentials.from_service_account_file(
        settings.gcp.GOOGLE_APPLICATION_CREDENTIALS,
        scopes=["https://www.googleapis.com/auth/bigquery"],
    )
    client = bigquery.Client(
        project=settings.gcp.PROJECT_ID, credentials=credentials,
    )

    table_ref = (
        f"{settings.gcp.PROJECT_ID}.{settings.gcp.BIGQUERY_DATASET}"
        f".{settings.gcp.BIGQUERY_TABLE}"
    )

    try:
        table = client.get_table(table_ref)
        print(f"  Table:      {table_ref}")
        print(f"  Row count:  {table.num_rows:,}")
        print(f"  Size:       {table.num_bytes / 1024 / 1024:.1f} MB")
        return table.num_rows
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 0


# -------------------------
# Qdrant check
# -------------------------

def check_qdrant() -> int:
    """Returns the vector count in the Qdrant collection."""

    print("\n--- Qdrant ---")
    client = QdrantClient(
        host=settings.qdrant.HOST,
        port=settings.qdrant.PORT,
        timeout=10,
    )

    collection = settings.qdrant.COLLECTION

    try:
        if not client.collection_exists(collection_name=collection):
            print(f"  Collection '{collection}' does not exist")
            return 0

        info = client.get_collection(collection_name=collection)
        print(f"  Collection:  {collection}")
        print(f"  Vectors:     {info.points_count:,}")
        print(f"  Status:      {info.status}")
        return info.points_count
    except Exception as exc:
        print(f"  ERROR: {exc}")
        return 0


# -------------------------
# Similarity search test
# -------------------------

def test_similarity_search() -> None:
    """Runs a sample similarity search to verify vectors are queryable."""

    print("\n--- Similarity Search Test ---")
    collection = settings.qdrant.COLLECTION

    qd_client = QdrantClient(
        host=settings.qdrant.HOST,
        port=settings.qdrant.PORT,
        timeout=10,
    )

    if not qd_client.collection_exists(collection_name=collection):
        print("  SKIPPED: collection does not exist")
        return

    info = qd_client.get_collection(collection_name=collection)
    if info.points_count == 0:
        print("  SKIPPED: collection is empty")
        return

    # Embed a sample query using RETRIEVAL_QUERY task type
    genai_client = genai.Client(api_key=settings.gemini.API_KEY)
    query_text = "cozy Italian restaurant with great pasta and wine"

    print(f"  Query: \"{query_text}\"")

    result = genai_client.models.embed_content(
        model=settings.gemini.EMBEDDING_MODEL,
        contents=query_text,
        config=genai_types.EmbedContentConfig(
            output_dimensionality=settings.gemini.EMBEDDING_DIMENSIONS,
            task_type="RETRIEVAL_QUERY",
        ),
    )
    query_vector = list(result.embeddings[0].values)

    # Search
    hits = qd_client.search(
        collection_name=collection,
        query_vector=query_vector,
        limit=5,
        with_payload=True,
        with_vectors=False,
    )

    print(f"  Results: {len(hits)} hits\n")
    for i, hit in enumerate(hits, 1):
        payload = hit.payload
        print(f"  {i}. score={hit.score:.4f}")
        print(f"     business: {payload.get('name', 'N/A')} ({payload.get('city', 'N/A')}, {payload.get('state', 'N/A')})")
        print(f"     stars:    biz={payload.get('business_stars', 'N/A')} review={payload.get('review_stars', 'N/A')}")
        text = str(payload.get("text", ""))[:150]
        print(f"     review:   {text}...")
        print()


# -------------------------
# Main
# -------------------------

def main() -> None:
    """Check both sinks and run a test search."""

    print("=" * 60)
    print("Gold Layer Sink Verification")
    print("=" * 60)

    bq_count = check_bigquery()
    qd_count = check_qdrant()

    print("\n--- Summary ---")
    print(f"  BigQuery rows:   {bq_count:,}")
    print(f"  Qdrant vectors:  {qd_count:,}")

    if bq_count > 0 and qd_count > 0:
        print("  Status:          BOTH SINKS ACTIVE")
    elif bq_count > 0:
        print("  Status:          BigQuery only (Qdrant empty)")
    elif qd_count > 0:
        print("  Status:          Qdrant only (BigQuery empty)")
    else:
        print("  Status:          BOTH SINKS EMPTY")

    if qd_count > 0:
        test_similarity_search()

    print("=" * 60)


if __name__ == "__main__":
    main()
