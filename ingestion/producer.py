"""
Streams businesses and reviews to separate Redpanda topics in parallel using one
thread per topic. Messages are keyed by business_id, values are Avro-serialized.
"""

import json
import sys
import threading
from typing import Generator

from confluent_kafka import KafkaException
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import StringSerializer
from confluent_kafka import SerializingProducer

from config.settings import settings
from ingestion.data_loader import load_businesses, load_reviews
from schemas import BUSINESS_AVRO_SCHEMA, REVIEW_AVRO_SCHEMA
from utils.logger import Logger
from utils.signals import get_running, register_signal_handlers

log = Logger.get(__name__)


_POLL_INTERVAL: int = 1_000


def _delivery_report(err, msg) -> None:
    if err is not None:
        log.warning(f"Delivery failed for {msg.topic()}[{msg.partition()}]: {err}")


def _create_registry_client() -> SchemaRegistryClient:
    return SchemaRegistryClient({"url": settings.kafka.SCHEMA_REGISTRY_URL})


def create_producer(avro_schema: dict) -> SerializingProducer:
    """Creates a SerializingProducer with AvroSerializer for values."""
    registry_client = _create_registry_client()

    avro_serializer = AvroSerializer(
        schema_registry_client=registry_client,
        schema_str=json.dumps(avro_schema),
    )

    producer_config = {
        "bootstrap.servers": settings.kafka.BOOTSTRAP_SERVERS,
        "key.serializer": StringSerializer("utf_8"),
        "value.serializer": avro_serializer,
    }

    producer = SerializingProducer(producer_config)
    log.info(f"SerializingProducer created -> {settings.kafka.BOOTSTRAP_SERVERS}")
    return producer


def _produce_topic(
    producer: SerializingProducer,
    topic: str,
    records: Generator[dict, None, None],
    entity_name: str,
) -> None:
    
    sent = 0
    errors = 0
    log.info(f"[{entity_name}] Starting production -> topic '{topic}'")

    for record in records:
        if not get_running():
            log.info(f"[{entity_name}] Shutdown flag detected — stopping.")
            break

        try:
            producer.produce(
                topic=topic,
                key=record.get("business_id", ""),
                value=record,
                on_delivery=_delivery_report,
            )
            sent += 1

            # Periodic poll to trigger delivery callbacks and free buffer memory
            if sent % _POLL_INTERVAL == 0:
                producer.poll(0)

            if sent % settings.kafka.PROGRESS_INTERVAL == 0:
                log.info(f"[{entity_name}] Progress: {sent:,} records sent.")

        except KafkaException as exc:
            errors += 1
            log.warning(
                f"[{entity_name}] Failed to send record "
                f"(business_id={record.get('business_id', '?')}): {exc}"
            )
        except BufferError:
            # Internal buffer full — poll to flush and retry
            producer.poll(1)
            try:
                producer.produce(
                    topic=topic,
                    key=record.get("business_id", ""),
                    value=record,
                    on_delivery=_delivery_report,
                )
                sent += 1
            except Exception as exc:
                errors += 1
                log.warning(f"[{entity_name}] Retry failed: {exc}")

    log.info(f"[{entity_name}] Done — {sent:,} sent, {errors} errors.")


def main() -> None:
    register_signal_handlers()
    log.info("Producer starting up...")

    try:
        biz_producer = create_producer(BUSINESS_AVRO_SCHEMA)
        review_producer = create_producer(REVIEW_AVRO_SCHEMA)
    except KafkaException as exc:
        log.critical(f"Failed to create Kafka producer: {exc}")
        sys.exit(1)

    biz_thread = threading.Thread(
        target=_produce_topic,
        args=(
            biz_producer,
            settings.kafka.BUSINESS_TOPIC,
            load_businesses(),
            "businesses",
        ),
        daemon=True,
        name="producer-businesses",
    )

    review_thread = threading.Thread(
        target=_produce_topic,
        args=(
            review_producer,
            settings.kafka.REVIEW_TOPIC,
            load_reviews(),
            "reviews",
        ),
        daemon=True,
        name="producer-reviews",
    )

    biz_thread.start()
    review_thread.start()

    log.info("Both producer threads started.")

    try:
        biz_thread.join()
        review_thread.join()
    except KeyboardInterrupt:
        log.info("KeyboardInterrupt — waiting for threads to finish...")
        biz_thread.join(timeout=5)
        review_thread.join(timeout=5)

    log.debug("Flushing producer buffers...")
    biz_producer.flush()
    review_producer.flush()
    log.info("Producer closed cleanly.")


if __name__ == "__main__":
    main()
