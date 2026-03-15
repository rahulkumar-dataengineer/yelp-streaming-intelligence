"""
Registers Yelp Avro schemas in Redpanda's built-in registry
using the platform_commons schema registry utilities.
"""

from config.settings import settings
from platform_commons.infra.schema_registry import get_subjects, register_all
from schemas import BUSINESS_AVRO_SCHEMA, REVIEW_AVRO_SCHEMA


def register_schemas() -> dict[str, int]:
    """Registers Yelp Avro schemas, sets compatibility, and enables topic validation."""
    return register_all(
        registry_url=settings.kafka.SCHEMA_REGISTRY_URL,
        bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
        subject_schemas={
            f"{settings.kafka.BUSINESS_TOPIC}-value": BUSINESS_AVRO_SCHEMA,
            f"{settings.kafka.REVIEW_TOPIC}-value": REVIEW_AVRO_SCHEMA,
        },
    )
