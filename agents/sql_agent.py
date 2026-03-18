"""SQL agent — ReAct agent using LangChain SQL toolkit against BigQuery deduped view."""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from sqlalchemy import create_engine, text
from agents.state import AgentState, extract_text
from config.settings import settings
from platform_commons.logger import Logger

log = Logger.get(__name__)


_DEDUPED_VIEW = "gold_reviews_deduped"

_SYSTEM_PROMPT = """
You are a SQL analyst querying a Yelp restaurant reviews database in BigQuery.

Table: {table_name}
This table has approximately 7 million rows. Be efficient with queries.

Rules:
1. NEVER use SELECT * — only select columns relevant to the question.
2. ALWAYS include LIMIT 50 unless the user explicitly asks for more results.
3. When route is HYBRID, include business_id in SELECT and use LIMIT 200.
4. Use WHERE clauses and aggregations to narrow results before returning.
5. Column names use underscores (e.g., business_stars, review_stars, restaurants_price_range, noise_level).
6. The 'categories' column is comma-separated text (e.g., "Restaurants, Italian, Pizza").
7. For category filtering, use LIKE with wildcards (e.g., WHERE categories LIKE '%Italian%').
"""


def _build_engine() -> "sqlalchemy.engine.Engine":
    """Builds a SQLAlchemy engine for BigQuery."""
    connection_string = (
        f"bigquery://{settings.gcp.PROJECT_ID}/{settings.gcp.BIGQUERY_DATASET}"
        f"?credentials_path={settings.gcp.GOOGLE_APPLICATION_CREDENTIALS}"
    )
    return create_engine(connection_string)


def _build_db() -> SQLDatabase:
    """Builds a SQLDatabase pointing to the deduped view only."""
    engine = _build_engine()
    return SQLDatabase(
        engine=engine,
        include_tables=[_DEDUPED_VIEW],
        view_support=True,
    )


def _extract_sql_from_steps(intermediate_steps: list) -> str:
    """Extracts the last SQL query from agent intermediate steps for transparency.

    Handles both legacy AgentAction (tool_input is a string) and tool-calling
    agent format (tool_input may be a dict like {"query": "SELECT ..."}).
    """
    for step in reversed(intermediate_steps):
        if hasattr(step, '__len__') and len(step) >= 2:
            action = step[0]
            if hasattr(action, 'tool') and action.tool == 'sql_db_query':
                tool_input = action.tool_input
                if isinstance(tool_input, str):
                    return tool_input
                if isinstance(tool_input, dict):
                    return tool_input.get("query", str(tool_input))
                return str(tool_input)
    log.warning(f"No sql_db_query found in {len(intermediate_steps)} intermediate steps")
    return ""


def _extract_business_ids(db: SQLDatabase, intermediate_steps: list) -> list[str]:
    """Re-executes the agent's SQL to extract business_ids from structured rows.

    Takes the SQL query the agent already generated (from intermediate_steps),
    re-executes it via raw SQLAlchemy to get structured rows, and pulls the
    business_id column by name. Avoids a second LLM call.

    Args:
        db: SQLDatabase instance with an active engine.
        intermediate_steps: Agent intermediate steps containing sql_db_query actions.

    Returns:
        List of business_id strings. Empty list if extraction fails.
    """
    sql = _extract_sql_from_steps(intermediate_steps)
    if not sql:
        log.warning("No SQL query found in intermediate steps for business_id extraction")
        return []

    try:
        with db._engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())

            if "business_id" not in columns:
                log.warning(f"business_id not in SELECT columns: {columns}")
                return []

            bid_idx = columns.index("business_id")
            ids = [row[bid_idx] for row in result if row[bid_idx]]

        return ids

    except Exception as exc:
        log.warning(f"Business_id extraction failed: {exc}")
        return []


def run(state: AgentState) -> dict:
    """Runs the SQL agent against BigQuery.

    Args:
        state: AgentState with 'query' and 'route' populated.

    Returns:
        Partial state update with sql_query, sql_result, and optionally sql_business_ids.
    """
    query = state["query"]
    route = state["route"]
    log.info(f"SQL agent running: route={route}, query={query}")

    try:
        db = _build_db()
        llm = ChatGoogleGenerativeAI(
            model=settings.gemini.MODEL,
            google_api_key=settings.gemini.API_KEY,
            temperature=0,
        )

        system_prompt = _SYSTEM_PROMPT.format(table_name=_DEDUPED_VIEW)
        if route == "HYBRID":
            system_prompt += "\nThis is a HYBRID query. Include business_id in SELECT and use LIMIT 200."

        agent_executor = create_sql_agent(
            llm=llm,
            db=db,
            agent_type="tool-calling",
            verbose=False,
            prefix=system_prompt,
            agent_executor_kwargs={"return_intermediate_steps": True},
        )

        result = agent_executor.invoke({"input": query})
        raw_output = result.get("output", "")
        output = extract_text(raw_output) if not isinstance(raw_output, str) else raw_output
        intermediate_steps = result.get("intermediate_steps", [])

        log.info(f"SQL agent result length: {len(output)} chars")
        tools_used = [
            step[0].tool for step in intermediate_steps
            if hasattr(step, '__len__') and len(step) >= 2 and hasattr(step[0], 'tool')
        ]
        log.info(f"SQL agent tools used: {tools_used}")

        sql_query = _extract_sql_from_steps(intermediate_steps)
        log.info(f"Extracted SQL query: {sql_query[:200] if sql_query else '(empty)'}")

        update = {
            "sql_query": sql_query,
            "sql_result": output,
        }

        # For HYBRID: re-execute the agent's SQL to extract structured business_ids
        if route == "HYBRID":
            business_ids = _extract_business_ids(db, intermediate_steps)
            update["sql_business_ids"] = business_ids
            log.info(f"SQL agent extracted {len(business_ids)} business_ids for HYBRID")

        return update

    except Exception as exc:
        log.error(f"SQL agent failed: {exc}")
        return {"error": f"SQL agent encountered an error: {exc}"}


