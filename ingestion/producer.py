# ingestion/producer.py
"""
Yelp Stream Producer — thin orchestration layer.

Responsibilities:
    1. Register graceful shutdown handlers (utils.signals)
    2. Load the joined Yelp dataset    (ingestion.data_loader)
    3. Connect to the Redpanda broker
    4. Stream records at the configured rate

This module contains NO business logic:
    Data loading    → ingestion/data_loader.py
    Serialisation   → utils/schema_contract.py
    Shutdown        → utils/signals.py
    Configuration   → config/settings.py

Usage:
    python -m ingestion.producer
"""

import sys
import time

from kafka import KafkaProducer
from kafka.errors import KafkaError

from config.settings import settings
from ingestion.data_loader import build_joined_dataset
from utils.schema_contract import row_to_message
from utils.signals import get_running, register_signal_handlers
from utils.logger import Logger

log = Logger.get(__name__)


# ─── Kafka Producer Factory ───────────────────────────────────────────────────

def create_producer() -> KafkaProducer:
    """
    Creates and returns a configured KafkaProducer instance.

    Returns:
        KafkaProducer connected to settings.kafka.BOOTSTRAP_SERVERS.

    Raises:
        KafkaError: If the broker is unreachable after 10 seconds.
    """
    log.debug("Connecting to Kafka broker at %s...", settings.kafka.BOOTSTRAP_SERVERS)

    producer = KafkaProducer(
        bootstrap_servers=settings.kafka.BOOTSTRAP_SERVERS,
        acks="all",           # Broker must acknowledge before continuing
        retries=3,            # Retry up to 3 times on transient failures
        max_block_ms=10_000,  # Raise after 10s if broker is unreachable
    )

    log.info("Kafka producer connected → %s", settings.kafka.BOOTSTRAP_SERVERS)
    return producer


# ─── Stream Loop ──────────────────────────────────────────────────────────────

def stream_records(producer: KafkaProducer, df) -> None:
    """
    Iterates over the joined DataFrame and streams records to Kafka.

    Rate control: sends BATCH_SIZE messages then sleeps SLEEP_INTERVAL seconds.
    Default: 50 msgs / 0.1s = ~500 msgs/sec.

    Checks get_running() before every batch — exits cleanly on SIGINT/SIGTERM.

    Args:
        producer: An active KafkaProducer instance.
        df:       Joined business+review DataFrame from build_joined_dataset().
    """
    total_sent: int = 0
    total_rows: int = len(df)

    log.info(
        "Stream starting → topic '%s' | records: %s | batch: %s | "
        "sleep: %ss | target: ~%s msgs/sec",
        settings.kafka.TOPIC,
        f"{total_rows:,}",
        settings.kafka.BATCH_SIZE,
        settings.kafka.SLEEP_INTERVAL,
        int(settings.kafka.BATCH_SIZE / settings.kafka.SLEEP_INTERVAL),
    )

    for batch_start in range(0, total_rows, settings.kafka.BATCH_SIZE):
        if not get_running():
            log.info("Shutdown flag detected — exiting stream loop.")
            break

        batch = df.iloc[batch_start : batch_start + settings.kafka.BATCH_SIZE]
        log.debug("Dispatching batch starting at row %s.", batch_start)

        for _, row in batch.iterrows():
            if not get_running():
                break
            try:
                producer.send(settings.kafka.TOPIC, value=row_to_message(row))
                total_sent += 1

                if total_sent % settings.kafka.PROGRESS_INTERVAL == 0:
                    log.info(
                        "Progress: %s / %s messages sent.",
                        f"{total_sent:,}",
                        f"{total_rows:,}",
                    )

            except KafkaError as exc:
                log.warning(
                    "Failed to send message (review_id=%s): %s",
                    row.get("review_id", "?"),
                    exc,
                )

        time.sleep(settings.kafka.SLEEP_INTERVAL)

    log.debug("Flushing producer buffer...")
    producer.flush()
    log.info("Stream complete — total messages sent: %s", f"{total_sent:,}")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    """Registers shutdown handlers, loads data, and starts the stream."""
    register_signal_handlers()
    log.info("Producer starting up...")

    try:
        df = build_joined_dataset()
    except (FileNotFoundError, ValueError) as exc:
        log.critical("Failed to load dataset: %s", exc)
        sys.exit(1)

    try:
        producer = create_producer()
    except KafkaError as exc:
        log.critical("Failed to connect to Kafka: %s", exc)
        log.critical("Is Redpanda running? → docker compose up -d")
        sys.exit(1)

    try:
        stream_records(producer, df)
    finally:
        producer.close()
        log.info("Producer closed cleanly.")


if __name__ == "__main__":
    main()
