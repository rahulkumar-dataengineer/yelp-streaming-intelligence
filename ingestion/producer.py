"""
Streams businesses and reviews to separate Redpanda topics in parallel using one
thread per topic. Messages are keyed by business_id, values are Avro-serialized.
"""

import sys
import threading

from confluent_kafka import KafkaException

from config.settings import settings
from ingestion.data_loader import load_businesses, load_reviews
from platform_commons.ingestion.producer import create_producer, produce_topic
from platform_commons.utils.logger import Logger
from platform_commons.utils.signals import register_signal_handlers
from schemas import BUSINESS_AVRO_SCHEMA, REVIEW_AVRO_SCHEMA

log = Logger.get(__name__)


def main() -> None:
    register_signal_handlers()
    log.info("Producer starting up...")

    try:
        biz_producer = create_producer(
            settings.kafka.BOOTSTRAP_SERVERS,
            settings.kafka.SCHEMA_REGISTRY_URL,
            BUSINESS_AVRO_SCHEMA,
        )
        review_producer = create_producer(
            settings.kafka.BOOTSTRAP_SERVERS,
            settings.kafka.SCHEMA_REGISTRY_URL,
            REVIEW_AVRO_SCHEMA,
        )
    except KafkaException as exc:
        log.critical(f"Failed to create Kafka producer: {exc}")
        sys.exit(1)

    biz_thread = threading.Thread(
        target=produce_topic,
        args=(
            biz_producer,
            settings.kafka.BUSINESS_TOPIC,
            load_businesses(),
            "business_id",
            "businesses",
            settings.kafka.PROGRESS_INTERVAL,
        ),
        daemon=True,
        name="producer-businesses",
    )

    review_thread = threading.Thread(
        target=produce_topic,
        args=(
            review_producer,
            settings.kafka.REVIEW_TOPIC,
            load_reviews(),
            "business_id",
            "reviews",
            settings.kafka.PROGRESS_INTERVAL,
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
