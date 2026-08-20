"""Kafka producer/consumer with critical-escalation forwarding."""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from kafka import KafkaAdminClient, KafkaConsumer, KafkaProducer
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "datasets"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", REPO_ROOT / "outputs" / "results" / "sanjay_subair" / "03_big_data")) / "kafka"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_EVENTS = "presight.project.events"
TOPIC_ESCALATIONS = "presight.escalations.critical"


def create_topics() -> None:
    admin = KafkaAdminClient(bootstrap_servers=KAFKA_BOOTSTRAP, client_id="presight-topic-admin")
    topics = [
        NewTopic(TOPIC_EVENTS, num_partitions=3, replication_factor=1),
        NewTopic(TOPIC_ESCALATIONS, num_partitions=1, replication_factor=1),
    ]
    try:
        admin.create_topics(new_topics=topics, validate_only=False)
        logger.info("Created Kafka topics")
    except TopicAlreadyExistsError:
        logger.info("Kafka topics already exist")
    finally:
        admin.close()


def build_producer() -> KafkaProducer:
    return KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        key_serializer=lambda value: value.encode("utf-8"),
        value_serializer=lambda value: json.dumps(value).encode("utf-8"),
        acks="all",
        retries=3,
        request_timeout_ms=30_000,
    )


def run_producer(
    producer: KafkaProducer,
    events_file: str | Path,
    delay_seconds: float = 0.05,
) -> int:
    sent = 0
    with Path(events_file).open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            event = json.loads(line)
            event["produced_at"] = datetime.now(timezone.utc).isoformat()
            producer.send(TOPIC_EVENTS, key=event["event_type"], value=event)
            sent += 1
            if sent % 100 == 0:
                logger.info("Produced %d messages; latest=%s", sent, event["event_id"])
            time.sleep(delay_seconds)
    producer.flush()
    producer.close()
    logger.info("Producer completed: %d messages", sent)
    return sent


def build_consumer(topic: str) -> KafkaConsumer:
    return KafkaConsumer(
        topic,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id="presight-assessment-consumer",
        auto_offset_reset="earliest",
        enable_auto_commit=True,
        value_deserializer=lambda value: json.loads(value.decode("utf-8")),
        consumer_timeout_ms=10_000,
    )


def run_consumer(consumer: KafkaConsumer) -> dict[str, object]:
    started = time.perf_counter()
    counts: Counter[str] = Counter()
    consumed = 0
    forwarded = 0
    forwarding_producer = build_producer()
    try:
        for message in consumer:
            event = message.value
            event_type = event.get("event_type", "unknown")
            counts[event_type] += 1
            consumed += 1
            if consumed % 100 == 0:
                logger.info("Consumed %d messages; latest=%s", consumed, event.get("event_id"))
            severity = (event.get("payload") or {}).get("severity")
            if event_type == "escalation_raised" and severity == "Critical":
                forwarding_producer.send(TOPIC_ESCALATIONS, key=event_type, value=event)
                forwarded += 1
        forwarding_producer.flush()
    finally:
        forwarding_producer.close()
        consumer.close()

    elapsed = max(time.perf_counter() - started, 1e-9)
    summary: dict[str, object] = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "total_messages_consumed": consumed,
        "count_per_event_type": dict(sorted(counts.items())),
        "critical_escalations_forwarded": forwarded,
        "throughput_messages_per_second": round(consumed / elapsed, 2),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info("Consumer completed: consumed=%d forwarded=%d", consumed, forwarded)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["producer", "consumer", "both"], default="both")
    parser.add_argument("--delay", type=float, default=0.05)
    arguments = parser.parse_args()
    create_topics()
    events_file = DATA_DIR / "events_stream" / "events_2025_01.jsonl"
    if arguments.mode in {"producer", "both"}:
        run_producer(build_producer(), events_file, arguments.delay)
    if arguments.mode in {"consumer", "both"}:
        run_consumer(build_consumer(TOPIC_EVENTS))


if __name__ == "__main__":
    main()
