"""PySpark pipeline for all Presight event-stream files."""

from __future__ import annotations

import os
import time
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import MapType, StringType, StructField, StructType, TimestampType

REPO_ROOT = Path(__file__).resolve().parents[4]
EVENTS_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "datasets")) / "events_stream"
OUTPUT_DIR = Path(
    os.getenv(
        "OUTPUT_DIR",
        REPO_ROOT / "outputs" / "results" / "sanjay_subair" / "03_big_data",
    )
) / "spark"


def get_spark_session() -> SparkSession:
    spark = (
        SparkSession.builder.appName("PresightEventsProcessing")
        .master("local[*]")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.shuffle.partitions", "16")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def load_events(spark: SparkSession, events_dir: str | Path) -> DataFrame:
    schema = StructType([
        StructField("event_id", StringType(), True),
        StructField("event_type", StringType(), True),
        StructField("project_id", StringType(), True),
        StructField("user_id", StringType(), True),
        StructField("timestamp", TimestampType(), True),
        StructField("payload", MapType(StringType(), StringType()), True),
    ])
    event_pattern = (Path(events_dir) / "events_*.jsonl").as_posix()
    event_files = [path.as_posix() for path in sorted(Path(events_dir).glob("events_*.jsonl"))]
    if not event_files:
        raise FileNotFoundError(f"No event files found in {events_dir}")
    source = event_files if os.name == "nt" and not os.getenv("HADOOP_HOME") else event_pattern
    events = spark.read.schema(schema).json(source)
    print(f"Rows loaded: {events.count():,}")
    return events


def validate_events(events: DataFrame) -> DataFrame:
    before_required = events.count()
    valid = events.dropna(subset=["event_id", "user_id"])
    after_required = valid.count()
    print(
        "Required-key null drop: "
        f"before={before_required:,}, after={after_required:,}, "
        f"dropped={before_required - after_required:,}"
    )

    order = Window.partitionBy("event_id").orderBy(F.col("timestamp").asc_nulls_last())
    deduplicated = valid.withColumn("_event_order", F.row_number().over(order)).filter(
        F.col("_event_order") == 1
    ).drop("_event_order")
    after_deduplication = deduplicated.count()
    print(
        "Duplicate event_id drop: "
        f"before={after_required:,}, after={after_deduplication:,}, "
        f"dropped={after_required - after_deduplication:,}"
    )
    return (
        deduplicated
        .withColumn("event_date", F.to_date("timestamp"))
        .withColumn("event_hour", F.hour("timestamp"))
        .withColumn("event_month", F.date_format("timestamp", "yyyy-MM"))
    )


def project_activity_summary(events: DataFrame) -> DataFrame:
    return (
        events.filter(F.col("project_id").isNotNull())
        .groupBy("project_id")
        .agg(
            F.count("*").alias("total_events"),
            F.sum(F.when(F.col("event_type") == "escalation_raised", 1).otherwise(0)).alias("escalation_count"),
            F.sum(F.when(F.col("event_type") == "task_completed", 1).otherwise(0)).alias("task_completions"),
            F.sum(F.when(F.col("event_type") == "document_uploaded", 1).otherwise(0)).alias("document_uploads"),
            F.max("timestamp").alias("last_event_timestamp"),
            F.countDistinct("user_id").alias("unique_users"),
            F.countDistinct("event_type").alias("unique_event_types"),
        )
        .orderBy(F.desc("total_events"))
    )


def user_activity_summary(events: DataFrame) -> DataFrame:
    return (
        events.groupBy("user_id")
        .agg(
            F.sum(F.when(F.col("event_type") == "login", 1).otherwise(0)).alias("login_count"),
            F.sum(F.when(F.col("event_type") == "logout", 1).otherwise(0)).alias("logout_count"),
            F.sum(F.when(~F.col("event_type").isin("login", "logout"), 1).otherwise(0)).alias("actions_taken"),
            F.countDistinct("project_id").alias("projects_touched"),
            F.min("timestamp").alias("first_active"),
            F.max("timestamp").alias("last_active"),
            F.countDistinct("event_date").alias("active_days"),
        )
        .orderBy(F.desc("last_active"))
    )


def escalation_log(events: DataFrame) -> DataFrame:
    raised = events.filter(F.col("event_type") == "escalation_raised").select(
        F.col("event_id"),
        F.col("project_id"),
        F.col("user_id").alias("raised_by"),
        F.col("timestamp").alias("raised_at"),
        F.element_at("payload", "severity").alias("severity"),
    )
    resolved = events.filter(F.col("event_type") == "escalation_resolved").select(
        F.col("project_id").alias("resolved_project_id"),
        F.col("timestamp").alias("resolved_at"),
        F.element_at("payload", "resolved_by").alias("resolved_by"),
    )
    candidates = raised.join(
        resolved,
        (raised.project_id == resolved.resolved_project_id) & (resolved.resolved_at >= raised.raised_at),
        "left",
    )
    first_resolution = Window.partitionBy("event_id").orderBy(F.col("resolved_at").asc_nulls_last())
    return (
        candidates.withColumn("_resolution_order", F.row_number().over(first_resolution))
        .filter(F.col("_resolution_order") == 1)
        .select(
            "event_id", "project_id", "raised_by", "raised_at", "severity",
            F.col("resolved_at").isNotNull().alias("resolved"),
            "resolved_by", "resolved_at",
            ((F.col("resolved_at").cast("long") - F.col("raised_at").cast("long")) / 3600.0).alias("resolution_time_hours"),
        )
    )


def daily_event_volume(events: DataFrame) -> DataFrame:
    daily = events.groupBy("event_date", "event_type").agg(F.count("*").alias("event_count"))
    cumulative = Window.partitionBy("event_type").orderBy("event_date").rowsBetween(
        Window.unboundedPreceding, Window.currentRow
    )
    return daily.withColumn("cumulative_count", F.sum("event_count").over(cumulative)).orderBy(
        F.asc("event_date"), F.desc("event_count")
    )


def peak_usage_analysis(events: DataFrame) -> DataFrame:
    return (
        events.groupBy("event_date", "event_hour")
        .agg(
            F.count("*").alias("total_events"),
            F.countDistinct("user_id").alias("unique_users"),
            F.countDistinct("event_type").alias("event_types_per_hour"),
        )
        .orderBy(F.desc("total_events"))
        .limit(20)
    )


def write_parquet(table: DataFrame, name: str, output_dir: str | Path) -> None:
    writer_table = table.coalesce(1)
    writer = writer_table.write.mode("overwrite")
    if name == "daily_event_volume":
        writer = writer.partitionBy("event_date")
    elif name == "escalation_log":
        writer = writer.partitionBy("severity")
    path = str(Path(output_dir) / name)
    writer.parquet(path)
    print(f"Wrote {name}: {table.count():,} rows -> {path}")


def _materialize(name: str, builder, timings: dict[str, float]) -> DataFrame:
    started = time.time()
    table = builder().cache()
    table.count()
    timings[name] = time.time() - started
    return table


def run_pipeline() -> None:
    started = time.time()
    spark = get_spark_session()
    try:
        raw = load_events(spark, EVENTS_DIR)
        clean = validate_events(raw).cache()
        total_rows = clean.count()
        timings: dict[str, float] = {}
        tables = {
            "project_activity_summary": _materialize("project_activity_summary", lambda: project_activity_summary(clean), timings),
            "user_activity_summary": _materialize("user_activity_summary", lambda: user_activity_summary(clean), timings),
            "escalation_log": _materialize("escalation_log", lambda: escalation_log(clean), timings),
            "daily_event_volume": _materialize("daily_event_volume", lambda: daily_event_volume(clean), timings),
            "peak_usage_analysis": _materialize("peak_usage_analysis", lambda: peak_usage_analysis(clean), timings),
        }
        for name, table in tables.items():
            write_parquet(table, name, OUTPUT_DIR)
        elapsed = time.time() - started
        print(f"Aggregation timings (seconds): {timings}")
        print(f"Total rows processed: {total_rows:,}")
        print(f"Total execution time: {elapsed:.3f} seconds")
        print(f"Events processed per second: {total_rows / elapsed:,.2f}")
    finally:
        spark.stop()


if __name__ == "__main__":
    run_pipeline()
