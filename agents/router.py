"""Query classifier — routes to SQL, VECTOR, or HYBRID via a single Gemini call."""

import json

from langchain_google_genai import ChatGoogleGenerativeAI
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

_SYSTEM_PROMPT = """
You are a query router for a Yelp restaurant search system. Classify the user's query into exactly one route.

ROUTES:

SQL — The query requires structured data operations that only a database can perform: aggregations (COUNT, AVG, SUM), rankings (TOP N), numeric thresholds (rating > 4.5), or sorting by metrics (review_count, stars).
Examples:
- "average rating for restaurants in Phoenix" → SQL
- "how many 5-star businesses in Arizona" → SQL
- "top 10 cities by review count" → SQL
- "restaurants with more than 500 reviews" → SQL

VECTOR — The query involves subjective qualities, vibes, ambiance, or personal recommendations. Simple metadata filters like city, state, category, or price range do NOT make a query SQL or HYBRID — the vector search handles these filters natively.
Examples:
- "cozy Italian place with great wine" → VECTOR
- "romantic dinner spot with quiet atmosphere" → VECTOR
- "best brunch vibes in town" → VECTOR
- "find me cozy Italian restaurants in Phoenix" → VECTOR (city + category are metadata filters, "cozy" is the semantic intent)
- "trendy bars in Scottsdale" → VECTOR (city is a metadata filter, "trendy" is the semantic intent)

HYBRID — The query combines an SQL-requiring operation (aggregation, ranking, numeric threshold) AND a subjective/semantic component. Simple metadata filters (city, category, price range) do NOT trigger HYBRID — only operations that require SQL analytics do.
Examples:
- "most romantic spots among the top 50 highest-rated restaurants" → HYBRID (SQL: top 50 by rating; semantic: romantic)
- "best atmosphere in restaurants with over 500 reviews in Phoenix" → HYBRID (SQL: review_count > 500; semantic: best atmosphere)
- "coziest places in the top 10 most reviewed cities" → HYBRID (SQL: top 10 cities by review count; semantic: coziest)

DECISION RULE: If the query needs aggregation, ranking, or numeric thresholds → SQL. If the query is about subjective qualities (even with city/category/price filters) → VECTOR. If it needs BOTH SQL analytics AND semantic understanding → HYBRID.

Respond with ONLY this JSON object, no other text: {"route": "SQL"} or {"route": "VECTOR"} or {"route": "HYBRID"}
"""


def _is_retryable(exc: BaseException) -> bool:
    """Returns True for HTTP 429 and 5xx errors."""
    exc_str = str(exc).lower()
    return "429" in exc_str or "500" in exc_str or "503" in exc_str or "resource exhausted" in exc_str


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(4),
)
def _classify_llm(query: str) -> str:
    """Calls Gemini to classify the query. Retries on 429/5xx."""
    llm = ChatGoogleGenerativeAI(
        model=settings.gemini.MODEL,
        google_api_key=settings.gemini.API_KEY,
        temperature=0,
        thinking_level="minimal",
    )
    response = llm.invoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "human", "content": query},
        ],
    )
    return extract_text(response.content)


def classify(state: AgentState) -> dict:
    """Classifies the user query into SQL, VECTOR, or HYBRID.

    Args:
        state: AgentState with 'query' populated.

    Returns:
        Partial state update: {"route": "SQL" | "VECTOR" | "HYBRID"}.
    """
    query = state["query"]
    log.info(f"Router classifying: {query}")

    try:
        raw = _classify_llm(query)
        result = json.loads(raw)
        route = result["route"].upper()

        if route not in ("SQL", "VECTOR", "HYBRID"):
            log.warning(f"Router returned unexpected route '{route}', falling back to HYBRID")
            route = "HYBRID"

    except Exception as exc:
        log.warning(f"Router failed to parse response, falling back to HYBRID: {exc}")
        route = "HYBRID"

    log.info(f"Router decision: {route}")
    return {"route": route}
