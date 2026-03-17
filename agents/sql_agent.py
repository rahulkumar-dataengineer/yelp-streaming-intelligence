"""SQL agent — ReAct agent using LangChain SQL toolkit against BigQuery deduped view."""

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits.sql.base import create_sql_agent
from sqlalchemy import create_engine, text
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


def _is_retryable(exc: BaseException) -> bool:
    """Returns True for HTTP 429 and 5xx errors."""
    exc_str = str(exc).lower()
    return "429" in exc_str or "500" in exc_str or "503" in exc_str or "resource exhausted" in exc_str


_DEDUPED_VIEW = "gold_reviews_deduped"

_SYSTEM_PROMPT = """You are a SQL analyst querying a Yelp restaurant reviews database in BigQuery.

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
    """Extracts the last SQL query from agent intermediate steps for transparency."""
    for step in reversed(intermediate_steps):
        if hasattr(step, '__len__') and len(step) >= 2:
            action = step[0]
            if hasattr(action, 'tool') and action.tool == 'sql_db_query':
                return action.tool_input if isinstance(action.tool_input, str) else str(action.tool_input)
    return ""


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
            return_intermediate_steps=True,
        )

        result = agent_executor.invoke({"input": query})
        raw_output = result.get("output", "")
        output = extract_text(raw_output) if not isinstance(raw_output, str) else raw_output
        intermediate_steps = result.get("intermediate_steps", [])

        log.info(f"SQL agent result length: {len(output)} chars")

        update = {
            "sql_query": _extract_sql_from_steps(intermediate_steps),
            "sql_result": output,
        }

        # For HYBRID: run a dedicated query to get business_ids reliably
        if route == "HYBRID":
            business_ids = _fetch_business_ids(db, query, llm)
            update["sql_business_ids"] = business_ids
            log.info(f"SQL agent extracted {len(business_ids)} business_ids for HYBRID")

        return update

    except Exception as exc:
        log.error(f"SQL agent failed: {exc}")
        return {"error": f"SQL agent encountered an error: {exc}"}


@retry(
    retry=retry_if_exception(_is_retryable),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(4),
)
def _generate_id_query(llm: ChatGoogleGenerativeAI, query: str) -> str:
    """Generates a SQL query for extracting business_ids. Retries on 429/5xx."""
    id_prompt = (
        f"Based on this question: '{query}'\n"
        f"Write a SQL query against {_DEDUPED_VIEW} that returns ONLY the "
        f"DISTINCT business_id values matching the criteria. Use LIMIT 200.\n"
        f"Key columns: business_id, name, city, state, categories (comma-separated text), "
        f"business_stars (1.0-5.0), review_stars (1-5), restaurants_price_range (1-4), "
        f"noise_level, alcohol, wifi, text (review text).\n"
        f"Return ONLY the SQL query, nothing else."
    )
    response = llm.invoke([{"role": "human", "content": id_prompt}])
    return extract_text(response.content).strip("`").replace("sql\n", "").strip()


def _fetch_business_ids(db: SQLDatabase, query: str, llm: ChatGoogleGenerativeAI) -> list[str]:
    """Runs a dedicated SQL query to extract business_ids for HYBRID routing.

    Uses a second, focused agent call that asks specifically for business_ids,
    then executes the SQL directly to get raw results (not summarized text).
    """
    try:
        sql = _generate_id_query(llm, query)

        # Execute the SQL directly via the engine
        with db._engine.connect() as conn:
            result = conn.execute(text(sql))
            ids = [row[0] for row in result if row[0]]

        return ids[:200]

    except Exception as exc:
        log.warning(f"Dedicated business_id query failed: {exc}")
        return []
