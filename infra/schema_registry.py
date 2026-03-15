"""
Uses confluent-kafka SchemaRegistryClient 
— registers Avro schema in Redpanda's built-in registry
- sets BACKWARD compatibility mode
- enables server-side schema validation on topics.
"""

import json

from confluent_kafka.admin import AdminClient, ConfigResource, ResourceType
from confluent_kafka.schema_registry import Schema, SchemaRegistryClient

from config.settings import settings
from schemas import BUSINESS_AVRO_SCHEMA, REVIEW_AVRO_SCHEMA
from utils.logger import Logger

log = Logger.get(__name__)


def _create_registry_client() -> SchemaRegistryClient:
    return SchemaRegistryClient({"url": settings.kafka.SCHEMA_REGISTRY_URL})


def _register_subject(client: SchemaRegistryClient, subject: str, avro_schema: dict) -> int:
    """Registers an Avro schema under the given subject. Returns the schema ID."""
    schema = Schema(json.dumps(avro_schema), "AVRO")
    schema_id = client.register_schema(subject, schema)
    log.info(f"Schema registered: {subject} -> id={schema_id}")
    return schema_id


def _set_compatibility(client: SchemaRegistryClient, subject: str, level: str = "BACKWARD") -> None:
    client.set_compatibility(subject_name=subject, level=level)
    log.info(f"Compatibility set: {subject} -> {level}")


def _enable_topic_validation(topic: str) -> None:
    """Enables server-side schema validation on a Redpanda topic."""
    admin = AdminClient({"bootstrap.servers": settings.kafka.BOOTSTRAP_SERVERS})

    resource = ConfigResource(
        ResourceType.TOPIC,
        topic,
        set_config={
            "redpanda.value.schema.id.validation": "true",
        },
    )

    futures = admin.alter_configs([resource])
    for res, future in futures.items():
        future.result()
        log.info(f"Topic validation enabled: {res}")


def register_schemas() -> dict[str, int]:
    """Registers Avro schemas, sets compatibility, and enables topic validation."""
    
    client = _create_registry_client()

    subjects = {
        f"{settings.kafka.BUSINESS_TOPIC}-value": BUSINESS_AVRO_SCHEMA,
        f"{settings.kafka.REVIEW_TOPIC}-value": REVIEW_AVRO_SCHEMA,
    }

    registered: dict[str, int] = {}
    for subject, avro_schema in subjects.items():
        registered[subject] = _register_subject(client, subject, avro_schema)
        _set_compatibility(client, subject, "BACKWARD")

    # Enable server-side validation on both topics
    for topic in [settings.kafka.BUSINESS_TOPIC, settings.kafka.REVIEW_TOPIC]:
        _enable_topic_validation(topic)

    log.info(f"All schemas registered with BACKWARD compatibility: {registered}")
    return registered


def get_subjects() -> list[str]:
    """Lists all registered subjects in the schema registry."""
    client = _create_registry_client()
    return client.get_subjects()
