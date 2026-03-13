"""
Streams businesses and reviews to separate Redpanda topics in parallel using one thread per topic. 
Messages are keyed by business_id
"""

import json
import sys
import threading
from typing import Generator

from kafka import KafkaProducer
from kafka.errors import KafkaError

from config.settings import settings
from ingestion.data_loader import load_businesses, load_reviews
from utils.logger import Logger
from utils.signals import get_running, register_signal_handlers

log = Logger.get(__name__)


def create_producer() -> KafkaProducer:
    log.debug(f"Connecting to Kafka at {settings.kafka.BOOTSTRAP_SERVERS}")
    producer = KafkaProducer(
        bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
        acks="all",
        retries=3,
        max_block_ms=10_000,
    )
    log.info(f"Kafka producer connected → {settings.kafka.BOOTSTRAP_SERVERS}")
    return producer


def _produce_topic(
    producer: KafkaProducer,
    topic: str,
    records: Generator[dict, None, None],
    entity_name: str,
) -> None:
    """Produces records from a generator to a single Kafka topic."""
    
    sent = 0
    errors = 0
    log.info(f"[{entity_name}] Starting production → topic '{topic}'")

    for record in records:
        if not get_running():
            log.info(f"[{entity_name}] Shutdown flag detected — stopping.")
            break

        try:
            key = record.get("business_id", "").encode("utf-8")
            value = json.dumps(record, default=str).encode("utf-8")
            producer.send(topic, key=key, value=value)
            sent += 1

            if sent % settings.kafka.PROGRESS_INTERVAL == 0:
                log.info(f"[{entity_name}] Progress: {sent:,} records sent.")

        except Exception as exc:
            errors += 1
            log.warning(
                f"[{entity_name}] Failed to send record "
                f"(business_id={record.get('business_id', '?')}): {exc}"
            )

    log.info(f"[{entity_name}] Done — {sent:,} sent, {errors} errors.")


def main() -> None:
    """Entry point: starts dual-topic threaded production."""
    
    register_signal_handlers()
    log.info("Producer starting up...")

    try:
        producer = create_producer()
    except KafkaError as exc:
        log.critical(f"Failed to connect to Kafka: {exc}")
        sys.exit(1)

    biz_thread = threading.Thread(
        target=_produce_topic,
        args=(
            producer,
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
            producer,
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

    log.debug("Flushing producer buffer...")
    producer.flush()
    producer.close()
    log.info("Producer closed cleanly.")


if __name__ == "__main__":
    main()
