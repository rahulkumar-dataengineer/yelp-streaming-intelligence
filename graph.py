"""LangGraph StateGraph — pure wiring, no business logic. CLI entry point."""

import sys

from langgraph.graph import StateGraph, END

from agents.state import AgentState
from agents.router import classify
from agents.sql_agent import run as sql_agent_run
from agents.vector_agent import run as vector_agent_run
from agents.synthesizer import run as synthesizer_run


def _route_after_router(state: AgentState) -> str:
    """Conditional edge: routes to the appropriate agent after classification."""
    route = state["route"]
    if route == "SQL":
        return "sql_agent"
    elif route == "VECTOR":
        return "vector_agent"
    else:  # HYBRID
        return "sql_agent"


def _route_after_sql(state: AgentState) -> str:
    """Conditional edge: after SQL, go to synthesizer (SQL) or vector (HYBRID)."""
    if state["route"] == "HYBRID":
        return "vector_agent"
    return "synthesizer"


def build_graph() -> StateGraph:
    """Builds and compiles the LangGraph agent graph."""
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("router", classify)
    graph.add_node("sql_agent", sql_agent_run)
    graph.add_node("vector_agent", vector_agent_run)
    graph.add_node("synthesizer", synthesizer_run)

    # Add edges
    graph.set_entry_point("router")

    graph.add_conditional_edges("router", _route_after_router, {
        "sql_agent": "sql_agent",
        "vector_agent": "vector_agent",
    })

    graph.add_conditional_edges("sql_agent", _route_after_sql, {
        "vector_agent": "vector_agent",
        "synthesizer": "synthesizer",
    })

    graph.add_edge("vector_agent", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile()


def main() -> None:
    """CLI entry point: python graph.py 'your query here'"""
    if len(sys.argv) < 2:
        print("Usage: python graph.py \"your query here\"")
        sys.exit(1)

    query = sys.argv[1]
    app = build_graph()

    result = app.invoke({
        "query": query,
        "route": "",
        "sql_query": "",
        "sql_result": "",
        "sql_business_ids": [],
        "vector_results": [],
        "error": "",
        "answer": "",
    })

    print(result["answer"])


if __name__ == "__main__":
    main()
