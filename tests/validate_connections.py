"""
Validation Script

Tests connectivity to all three cloud services independently.
Each test prints PASS or FAIL with a clear error message.

Usage:
    python validate_connections.py
"""

import os
import sys
from config.settings import settings


def _pass(service: str) -> None:
    print(f"----- PASS ----- [{service}]")

def _fail(service: str, error: str) -> None:
    print(f"xxxxx FAIL xxxxx [{service}] : {error}")



def test_bigquery() -> bool:
    print("\nTesting BigQuery connectivity......")

    project_id = settings.gcp.PROJECT_ID
    key_path = settings.gcp.GOOGLE_APPLICATION_CREDENTIALS

    if not project_id:
        _fail("BigQuery", "GCP_PROJECT_ID is not set in .env")
        return False
    if not key_path:
        _fail("BigQuery", "GCP_SERVICE_ACCOUNT_KEY_PATH is not set in .env")
        return False
    if not os.path.exists(key_path):
        _fail("BigQuery", f"Service account key file not found at: {key_path}")
        return False

    try:
        from google.cloud import bigquery

        client = bigquery.Client(project=project_id)
        datasets = list(client.list_datasets())
        dataset_names = [d.dataset_id for d in datasets]

        print(f"Found {len(dataset_names)} dataset(s): {dataset_names}")
        
        _pass("BigQuery")
        return True

    except Exception as exc:
        _fail("BigQuery", str(exc))
        return False



def test_pinecone() -> bool:
    print("\nTesting Pinecone connectivity......")
    
    api_key = settings.pinecone.API_KEY
    index_name = settings.pinecone.INDEX_NAME

    if not api_key:
        _fail("Pinecone", "PINECONE_API_KEY is not set in .env")
        return False

    try:
        from pinecone import Pinecone

        pc = Pinecone(api_key=api_key)

        # List all indexes to verify the connection
        indexes = pc.list_indexes()
        index_names = [idx.name for idx in indexes]
        print(f"Available indexes: {index_names}")

        if index_name not in index_names:
            _fail(
                "Pinecone",
                f"Index '{index_name}' not found. "
                f"Please create it at app.pinecone.io with 384 dims + cosine metric. "
                f"Available indexes: {index_names}"
            )
            return False

        # Connect to the specific index and fetch stats
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        print(f"Index '{index_name}' stats: total_vector_count={stats.total_vector_count}, dimension={stats.dimension}")

        _pass("Pinecone")
        return True

    except Exception as exc:
        _fail("Pinecone", str(exc))
        return False



def test_gemini() -> bool:
    print("\nTesting Gemini API connectivity......")
    api_key = settings.gemini.API_KEY

    if not api_key:
        _fail("Gemini", "GEMINI_API_KEY is not set in .env")
        return False

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import HumanMessage

        llm = ChatGoogleGenerativeAI(
            model=settings.gemini.MODEL,
            google_api_key=api_key,
            temperature=0,
            max_tokens=50,
        )

        response = llm.invoke([HumanMessage(content="Reply with exactly: CONNECTION_OK")])
        reply = response.content.strip()
        print(f"Gemini response: '{reply}'")

        _pass("Gemini")
        return True

    except Exception as exc:
        _fail("Gemini", str(exc))
        return False



def main() -> None:
    """Runs all three connectivity tests and prints a summary."""
    print("=" * 60)
    print("  Yelp Hybrid Streaming Agentic Platform Connection Test")
    print("=" * 60)

    results = {
        "BigQuery": test_bigquery(),
        "Pinecone": test_pinecone(),
        "Gemini":   test_gemini(),
    }

    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    all_passed = True
    for service, passed in results.items():
        if passed:
            _pass(service)
        else:
            _fail(service, "See details above")
            all_passed = False

    if all_passed:
        print("\n All services connected.")
        sys.exit(0)
    else:
        print("\n Fix the FAIL(s).")
        sys.exit(1)

    print("=" * 60)

if __name__ == "__main__":
    main()