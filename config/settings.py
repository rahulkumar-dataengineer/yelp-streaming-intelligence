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
    BIGQUERY_TABLE: str = _optional("GCP_BIGQUERY_TABLE", "gold_reviews")
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


class APISettings:
    CORS_ORIGIN: str = _optional("CORS_ORIGIN", "*")


class YelpSettings:
    BUSINESS_JSON_PATH: str = _require("YELP_BUSINESS_JSON_PATH")
    REVIEW_JSON_PATH: str = _require("YELP_REVIEW_JSON_PATH")
    REVIEW_LIMIT: int = int(_optional("REVIEW_LIMIT", "1000000"))


class KafkaSettings:
    BOOTSTRAP_SERVERS: str = _optional("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    SCHEMA_REGISTRY_URL: str = _optional("SCHEMA_REGISTRY_URL", "http://localhost:8081")
    BUSINESS_TOPIC: str = _optional("KAFKA_BUSINESS_TOPIC", "yelp_businesses")
    REVIEW_TOPIC: str = _optional("KAFKA_REVIEW_TOPIC", "yelp_reviews")
    PROGRESS_INTERVAL: int = 10_000

class HiveSettings:
    METASTORE_URI: str = _optional("HIVE_METASTORE_URI", "thrift://localhost:9083")
    WAREHOUSE_DIR: str = _optional("HIVE_WAREHOUSE_DIR", "/tmp/spark-warehouse")
    BRONZE_DB: str = "bronze"
    SILVER_DB: str = "silver"
    GOLD_DB: str = "gold"


class SparkSettings:
    KAFKA_PACKAGE: str = "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.4"
    AVRO_PACKAGE: str = "org.apache.spark:spark-avro_2.12:3.5.4"

    BRONZE_BUSINESS_CHECKPOINT: str = _optional("BRONZE_BUSINESS_CHECKPOINT", "checkpoints/bronze/businesses")
    BRONZE_REVIEW_CHECKPOINT: str = _optional("BRONZE_REVIEW_CHECKPOINT", "checkpoints/bronze/reviews")
    SILVER_CHECKPOINT: str = _optional("SILVER_CHECKPOINT", "checkpoints/silver")
    GOLD_CHECKPOINT: str = _optional("GOLD_CHECKPOINT", "checkpoints/gold")


class Settings:
    gcp    = GCPSettings()
    qdrant = QdrantSettings()
    gemini = GeminiSettings()
    api    = APISettings()
    kafka  = KafkaSettings()
    hive   = HiveSettings()
    spark  = SparkSettings()

    @property
    def yelp(self):
        if not hasattr(self, '_yelp'):
            self._yelp = YelpSettings()
        return self._yelp

settings = Settings()
