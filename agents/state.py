"""Agent state definition — TypedDict flowing through every LangGraph node."""

from typing import TypedDict


class AgentState(TypedDict):
    query: str                      # User's original question
    route: str                      # "SQL" | "VECTOR" | "HYBRID"
    sql_query: str                  # Generated SQL (transparency)
    sql_result: str                 # Formatted query results
    sql_business_ids: list[str]     # HYBRID: passed to vector agent
    vector_results: list[dict]      # Top-K matches with payload + scores
    error: str                      # Error message if an agent fails
    answer: str                     # Final natural language answer


def extract_text(content: str | list) -> str:
    """Extracts text from a LangChain response content field.

    When thinking_level is set, ChatGoogleGenerativeAI returns content as a
    list of content blocks instead of a plain string. This helper normalizes
    both formats to a plain string.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [block["text"] for block in content if isinstance(block, dict) and "text" in block]
        return "\n".join(parts).strip()
    return str(content).strip()
