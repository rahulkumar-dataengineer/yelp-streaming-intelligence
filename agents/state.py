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
