"""Vector agent — function-based Qdrant semantic search with Gemini embeddings."""

import json

from google import genai
from google.genai import types as genai_types
from langchain_google_genai import ChatGoogleGenerativeAI
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    FieldCondition,
    Filter,
    MatchAny,
    MatchText,
    MatchValue,
)
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from agents.state import AgentState, extract_text
from config.settings import settings
from platform_commons.logger import Logger

log = Logger.get(__name__)

_FILTER_PROMPT = """You are a filter extractor for a Yelp restaurant vector search system.

Given a user query, extract structured filters from the available payload fields. Return ONLY a JSON object with matching fields. Omit fields that aren't mentioned or implied.

Available fields and their types:
- city (string): city name, e.g., "Phoenix", "Scottsdale"
- state (string): 2-letter state code, e.g., "AZ", "NV"
- categories (string): comma-separated, e.g., "Italian", "Pizza", "Sushi"
- restaurants_price_range (integer): 1-4 scale
- noise_level (string): "quiet", "average", "loud", "very_loud"
- alcohol (string): "none", "beer_and_wine", "full_bar"
- wifi (string): "no", "free", "paid"
- outdoor_seating (boolean): true/false
- business_stars (float): 1.0-5.0 business average rating
- review_stars (integer): 1-5 individual review rating

Example:
Query: "cozy Italian restaurants in Phoenix"
Response: {"city": "Phoenix", "categories": "Italian"}

Query: "loud bars with full bar in Scottsdale"
Response: {"city": "Scottsdale", "noise_level": "loud", "alcohol": "full_bar"}

Respond with ONLY the JSON object, no extra text.
"""


def _is_retryable(exc: BaseException) -> bool:
    """Returns True for HTTP 429 and 5xx errors."""
    exc_str = str(exc).lower()
    return "429" in exc_str or "500" in exc_str or "503" in exc_str or "resource exhausted" in exc_str


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=2, min=2, max=120),
    stop=stop_after_attempt(6),
)
def _embed_query(client: genai.Client, text: str) -> list[float]:
    """Embeds a single query text using Gemini Embedding API."""
    result = client.models.embed_content(
        model=settings.gemini.EMBEDDING_MODEL,
        contents=text,
        config=genai_types.EmbedContentConfig(
            output_dimensionality=settings.gemini.EMBEDDING_DIMENSIONS,
            task_type="RETRIEVAL_QUERY",
        ),
    )
    return list(result.embeddings[0].values)


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(4),
)
def _extract_filters_llm(query: str) -> dict:
    """Uses Gemini to extract structured filters from the query."""
    llm = ChatGoogleGenerativeAI(
        model=settings.gemini.MODEL,
        google_api_key=settings.gemini.API_KEY,
        temperature=0,
        thinking_level="minimal",
    )
    response = llm.invoke(
        [
            {"role": "system", "content": _FILTER_PROMPT},
            {"role": "human", "content": query},
        ],
    )
    return json.loads(extract_text(response.content))


def _build_qdrant_filter(filters: dict) -> Filter | None:
    """Converts extracted filter dict into a Qdrant Filter object."""
    conditions = []

    for key, value in filters.items():
        if value is None or value == "":
            continue

        if key in ("city", "state"):
            # No lowercasing — Qdrant stores original casing from silver layer
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=str(value)))
            )
        elif key == "categories":
            # Substring match for comma-separated field
            conditions.append(
                FieldCondition(key=key, match=MatchText(text=str(value)))
            )
        elif key == "restaurants_price_range":
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=int(value)))
            )
        elif key in ("noise_level", "alcohol", "wifi"):
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=str(value)))
            )
        elif key == "outdoor_seating":
            conditions.append(
                FieldCondition(key=key, match=MatchValue(value=bool(value)))
            )
        else:
            log.warning(f"Skipping unrecognized filter field: {key}")

    if not conditions:
        return None
    return Filter(must=conditions)


def _build_hybrid_filter(business_ids: list[str]) -> Filter:
    """Builds a Qdrant filter for HYBRID mode using business_ids from SQL agent."""
    return Filter(
        must=[
            FieldCondition(key="business_id", match=MatchAny(any=business_ids))
        ]
    )


def run(state: AgentState) -> dict:
    """Runs the vector agent — extract filters, embed query, search Qdrant.

    Args:
        state: AgentState with 'query' populated. For HYBRID, 'sql_business_ids' too.

    Returns:
        Partial state update with vector_results.
    """
    query = state["query"]
    route = state.get("route", "VECTOR")
    sql_business_ids = state.get("sql_business_ids", [])
    log.info(f"Vector agent running: route={route}, query={query}")

    try:
        # Phase 1: Build Qdrant filter
        if route == "HYBRID" and sql_business_ids:
            qdrant_filter = _build_hybrid_filter(sql_business_ids)
            log.info(f"HYBRID filter: {len(sql_business_ids)} business_ids")
        else:
            try:
                filters = _extract_filters_llm(query)
                log.info(f"Extracted filters: {filters}")
                qdrant_filter = _build_qdrant_filter(filters)
            except Exception as exc:
                log.warning(f"Filter extraction failed, searching without filters: {exc}")
                qdrant_filter = None

        # Phase 2: Embed query
        genai_client = genai.Client(api_key=settings.gemini.API_KEY)
        query_vector = _embed_query(genai_client, query)

        # Phase 3: Search Qdrant
        qdrant = QdrantClient(host=settings.qdrant.HOST, port=settings.qdrant.PORT)
        results = qdrant.search(
            collection_name=settings.qdrant.COLLECTION,
            query_vector=query_vector,
            query_filter=qdrant_filter,
            limit=10,
        )

        vector_results = [
            {
                "name": hit.payload.get("name", "Unknown"),
                "city": hit.payload.get("city", ""),
                "state": hit.payload.get("state", ""),
                "categories": hit.payload.get("categories", ""),
                "review_stars": hit.payload.get("review_stars", ""),
                "business_stars": hit.payload.get("business_stars", ""),
                "text": hit.payload.get("text", ""),
                "score": round(hit.score, 4),
            }
            for hit in results
        ]

        log.info(f"Vector agent returned {len(vector_results)} results")
        return {"vector_results": vector_results}

    except Exception as exc:
        log.error(f"Vector agent failed: {exc}")
        return {"error": f"Vector agent encountered an error: {exc}"}
