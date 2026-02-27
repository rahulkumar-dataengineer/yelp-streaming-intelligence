from dotenv import load_dotenv
import os

load_dotenv()


class GCPSettings:
    PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    BIGQUERY_DATASET: str = os.getenv("GCP_BIGQUERY_DATASET", "")
    GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")


class PineconeSettings:
    API_KEY: str = os.getenv("PINECONE_API_KEY", "")
    INDEX_NAME: str = os.getenv("PINECONE_INDEX_NAME", "")
    HOST_URL: str = os.getenv("PINECONE_HOST_URL", "")


class GeminiSettings:
    API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    MODEL: str = os.getenv("GEMINI_MODEL", "")


class YelpSettings:
    BUSINESS_JSON_PATH: str = os.getenv("YELP_BUSINESS_JSON_PATH", "")
    REVIEW_JSON_PATH: str = os.getenv("YELP_REVIEW_JSON_PATH", "")


class KafkaSettings:
    BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    TOPIC: str = os.getenv("KAFKA_TOPIC", "")


class Settings:
    gcp     = GCPSettings()
    pinecone = PineconeSettings()
    gemini  = GeminiSettings()
    yelp    = YelpSettings()
    kafka   = KafkaSettings()

# Single shared instance
settings = Settings()
