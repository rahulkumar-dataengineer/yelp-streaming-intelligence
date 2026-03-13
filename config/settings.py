import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise EnvironmentError(
            f"\nMissing required environment variable: {key}\n"
        )
    return value


def _optional(key: str, default: str) -> str:
    return os.getenv(key, default).strip() or default



class GCPSettings:
    PROJECT_ID: str = _require("GCP_PROJECT_ID")
    BIGQUERY_DATASET: str = _require("GCP_BIGQUERY_DATASET")
    GOOGLE_APPLICATION_CREDENTIALS: str = _require("GOOGLE_APPLICATION_CREDENTIALS")


class QdrantSettings:
    HOST: str = _require("QDRANT_HOST")
    PORT: int = int(_require("QDRANT_PORT"))
    COLLECTION: str = _require("QDRANT_COLLECTION")


class GeminiSettings:
    API_KEY: str = _require("GEMINI_API_KEY")
    MODEL: str = _optional("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
    EMBEDDING_MODEL: str = _optional("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    EMBEDDING_DIMENSIONS: int = int(_optional("GEMINI_EMBEDDING_DIMENSIONS", "768"))


class YelpSettings:
    BUSINESS_JSON_PATH: str = _require("YELP_BUSINESS_JSON_PATH")
    REVIEW_JSON_PATH: str = _require("YELP_REVIEW_JSON_PATH")


class KafkaSettings:
    BOOTSTRAP_SERVERS: str = _optional("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    BUSINESS_TOPIC: str = _optional("KAFKA_BUSINESS_TOPIC", "yelp_businesses")
    REVIEW_TOPIC: str = _optional("KAFKA_REVIEW_TOPIC", "yelp_reviews")
    PROGRESS_INTERVAL: int = 10_000

class Settings:
    gcp    = GCPSettings()
    qdrant = QdrantSettings()
    gemini = GeminiSettings()
    yelp   = YelpSettings()
    kafka  = KafkaSettings()

settings = Settings()
