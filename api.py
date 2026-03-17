"""Flask API serving the LangGraph agent. Single module, two endpoints."""

from flask import Flask, request, jsonify
from flask_cors import CORS
from google.cloud import bigquery
from qdrant_client import QdrantClient

from config.settings import settings
from graph import build_graph

from platform_commons.logger import Logger

logger = Logger.get(__name__)

app = Flask(__name__)
CORS(app, origins=[settings.api.CORS_ORIGIN])

# Build graph once at startup
agent = build_graph()


@app.route("/health", methods=["GET"])
def health():
    """Pings Qdrant and BigQuery to verify system is operational."""
    qdrant_ok = False
    bigquery_ok = False

    try:
        client = QdrantClient(host=settings.qdrant.HOST, port=settings.qdrant.PORT)
        client.get_collections()
        qdrant_ok = True
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")

    try:
        bq_client = bigquery.Client(project=settings.gcp.PROJECT_ID)
        list(bq_client.query("SELECT 1").result())
        bigquery_ok = True
    except Exception as e:
        logger.error(f"BigQuery health check failed: {e}")

    status = "ok" if (qdrant_ok and bigquery_ok) else "degraded"
    code = 200 if status == "ok" else 503

    return jsonify({"status": status, "qdrant": qdrant_ok, "bigquery": bigquery_ok}), code


@app.route("/query", methods=["POST"])
def query():
    """Runs the LangGraph agent and returns the result with transparency fields."""
    body = request.get_json(silent=True)
    if not body or "query" not in body:
        return jsonify({"error": "Missing 'query' field in request body"}), 400

    user_query = body["query"]
    logger.info(f"Received query: {user_query}")

    try:
        result = agent.invoke({
            "query": user_query,
            "route": "",
            "sql_query": "",
            "sql_result": "",
            "sql_business_ids": [],
            "vector_results": [],
            "error": "",
            "answer": "",
        })

        return jsonify({
            "answer": result.get("answer"),
            "route": result.get("route"),
            "sql_query": result.get("sql_query") or None,
            "sql_result": result.get("sql_result") or None,
            "vector_results": result.get("vector_results") or None,
            "error": result.get("error") or None,
        })

    except Exception as e:
        logger.error(f"Agent invocation failed: {e}")
        return jsonify({
            "answer": None,
            "route": None,
            "sql_query": None,
            "sql_result": None,
            "vector_results": None,
            "error": str(e),
        }), 500


if __name__ == "__main__":
    logger.info(f"Starting API server (CORS origin: {settings.api.CORS_ORIGIN})")
    app.run(host="0.0.0.0", port=5001, threaded=True)
