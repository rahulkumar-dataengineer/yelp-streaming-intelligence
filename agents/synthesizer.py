"""Synthesizer — generates natural language answers from agent results with routing transparency."""

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

_SYSTEM_PROMPT = """You are a Yelp restaurant expert. Synthesize the retrieved data into a helpful, conversational answer.

Rules:
1. Reference specific business names, ratings, and review quotes from the provided data.
2. Do NOT hallucinate businesses or details not present in the results.
3. Be concise: 3-5 sentences for simple queries, a short paragraph for complex ones.
4. If the data is empty, say you couldn't find matching results — don't make things up.
"""


def _is_retryable(exc: BaseException) -> bool:
    """Returns True for HTTP 429 and 5xx errors."""
    exc_str = str(exc).lower()
    return "429" in exc_str or "500" in exc_str or "503" in exc_str or "resource exhausted" in exc_str


def _build_context(state: AgentState) -> str:
    """Assembles context for the synthesizer based on route."""
    route = state["route"]
    parts = [f"User question: {state['query']}"]

    if route in ("SQL", "HYBRID"):
        sql_result = state.get("sql_result", "")
        if sql_result:
            parts.append(f"SQL analysis results:\n{sql_result}")

    if route in ("VECTOR", "HYBRID"):
        vector_results = state.get("vector_results", [])
        if vector_results:
            formatted = []
            for i, r in enumerate(vector_results, 1):
                formatted.append(
                    f"{i}. {r['name']} ({r['city']}, {r['state']}) — "
                    f"Business: {r['business_stars']}★, Review: {r['review_stars']}★, "
                    f"Categories: {r['categories']}\n"
                    f"   Review: \"{r['text'][:200]}...\"\n"
                    f"   Relevance: {r['score']}"
                )
            parts.append(f"Semantic search results:\n" + "\n".join(formatted))

    return "\n\n".join(parts)


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(4),
)
def _synthesize_llm(context: str) -> str:
    """Calls Gemini to synthesize the answer. Retries on 429/5xx."""
    llm = ChatGoogleGenerativeAI(
        model=settings.gemini.MODEL,
        google_api_key=settings.gemini.API_KEY,
        temperature=0.3,
    )
    response = llm.invoke(
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "human", "content": context},
        ],
    )
    return response.content.strip()


def run(state: AgentState) -> dict:
    """Generates a final natural language answer with routing transparency.

    Args:
        state: AgentState with query, route, and agent outputs populated.

    Returns:
        Partial state update with 'answer'.
    """
    route = state["route"]
    error = state.get("error", "")
    log.info(f"Synthesizer running: route={route}")

    # Handle error state
    if error:
        log.warning(f"Synthesizer received error: {error}")
        answer = (
            "I encountered a temporary issue while processing your query. "
            "Please try again in a moment."
            f"\n\n---\nRouted as: {route}"
        )
        return {"answer": answer}

    # Check for empty results
    sql_result = state.get("sql_result", "")
    vector_results = state.get("vector_results", [])

    if route == "SQL" and not sql_result:
        answer = f"I couldn't find data matching that query.\n\n---\nRouted as: {route}"
        return {"answer": answer}
    if route == "VECTOR" and not vector_results:
        answer = f"I couldn't find restaurants matching that description.\n\n---\nRouted as: {route}"
        return {"answer": answer}
    if route == "HYBRID" and not sql_result and not vector_results:
        answer = (
            "I couldn't find results from either the analytics or semantic search. "
            "Try rephrasing your query."
            f"\n\n---\nRouted as: {route}"
        )
        return {"answer": answer}

    # Generate answer via Gemini
    try:
        context = _build_context(state)
        answer_text = _synthesize_llm(context)
        answer = f"{answer_text}\n\n---\nRouted as: {route}"

        log.info(f"Synthesizer produced answer: {len(answer)} chars")
        return {"answer": answer}

    except Exception as exc:
        log.error(f"Synthesizer failed: {exc}")
        answer = (
            "I encountered an issue generating the answer. Please try again."
            f"\n\n---\nRouted as: {route}"
        )
        return {"answer": answer}
