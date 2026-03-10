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


class PineconeSettings:
    API_KEY: str = _require("PINECONE_API_KEY")
    INDEX_NAME: str = _require("PINECONE_INDEX_NAME")
    HOST_URL: str = _require("PINECONE_HOST_URL")


class GeminiSettings:
    API_KEY: str = _require("GEMINI_API_KEY")
    MODEL: str = _optional("GEMINI_MODEL", "gemini-2.5-flash-lite")


class YelpSettings:
    BUSINESS_JSON_PATH: str = _require("YELP_BUSINESS_JSON_PATH")
    REVIEW_JSON_PATH: str = _require("YELP_REVIEW_JSON_PATH")


class KafkaSettings:
    BOOTSTRAP_SERVERS: str = _optional("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    TOPIC: str = _require("KAFKA_TOPIC")
    BATCH_SIZE: int = int(_optional("BATCH_SIZE", "50"))
    SLEEP_INTERVAL: float = float(_optional("SLEEP_INTERVAL", "0.1"))
    PROGRESS_INTERVAL: int = 1000

class Settings:
    gcp      = GCPSettings()
    pinecone = PineconeSettings()
    gemini   = GeminiSettings()
    yelp     = YelpSettings()
    kafka    = KafkaSettings()

settings = Settings()
