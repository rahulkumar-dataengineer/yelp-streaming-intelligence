"""Query classifier — routes to SQL, VECTOR, or HYBRID via a single Gemini call."""

import json

from langchain_google_genai import ChatGoogleGenerativeAI
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from agents.state import AgentState
from config.settings import settings
from platform_commons.logger import Logger

log = Logger.get(__name__)

_SYSTEM_PROMPT = """You are a query router for a Yelp restaurant search system. Classify the user's query into exactly one route.

Routes:
- SQL: Aggregations, counts, averages, rankings by numeric fields, structured filters.
  Examples: "average rating for restaurants in Phoenix", "how many 5-star businesses in Arizona", "top 10 cities by review count"
- VECTOR: Vibe, ambiance, sentiment, subjective quality, recommendations, experience-based queries.
  Examples: "cozy Italian place with great wine", "romantic dinner spot with quiet atmosphere", "best brunch vibes"
- HYBRID: Combines structured filtering with subjective/semantic intent. Also use when uncertain.
  Examples: "best restaurants in the top 10 highest-rated cities", "most romantic spots among highly-rated Italian restaurants"

Respond with ONLY a JSON object: {"route": "SQL"} or {"route": "VECTOR"} or {"route": "HYBRID"}
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
    return response.content.strip()


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

    except (json.JSONDecodeError, KeyError, Exception) as exc:
        log.warning(f"Router failed to parse response, falling back to HYBRID: {exc}")
        route = "HYBRID"

    log.info(f"Router decision: {route}")
    return {"route": route}
