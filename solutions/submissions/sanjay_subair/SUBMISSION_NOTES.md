# Submission Notes

## Scope

This submission implements all code-oriented requirements across the four pillars under `solutions/submissions/sanjay_subair/`. Root-level deployment files are included where the assessment explicitly requires them.

## Design decisions

- All source and output roots support `DATA_DIR` and `OUTPUT_DIR` environment variables.
- Pandas transformations use vectorized masks and validated many-to-one merges; no row iteration is used.
- Null transaction amounts remain null in the lineage-preserving `amount` field and become `0.0` only in `amount_aed`. A null approver means `is_approved=False`.
- Employee repairs are mask-based and logged. Invalid values are replaced with level-based defensible defaults rather than silently dropped; missing or duplicate employee keys are rejected.
- The warehouse SQL targets DuckDB and implements employee SCD Type 2 with contiguous, non-overlapping periods and a `9999-12-31` current sentinel.
- Spark uses an explicit schema, deterministic earliest-timestamp deduplication, five aggregate tables, required partitioning, and action-backed timing.
- Kafka consumers stop after 10 seconds without messages and forward only Critical raised escalations.
- Airflow passes row counts, DQ results, and file paths through XCom; DataFrames are staged as Parquet instead of being serialized into metadata storage.
- The DQ framework is config-driven and implements completeness, uniqueness, numeric validity, date validity, consistency, and referential integrity.

## Files

- `01_foundations/etl_pipeline.py`: project transformation and employee cleaning
- `01_foundations/data_model.sql`: star schema, SCD2 load, and integrity queries
- `02_sql_and_viz/etl_full.py`: full transaction ETL and summary
- `02_sql_and_viz/queries.sql`: six business queries
- `02_sql_and_viz/query_optimization.sql`: baseline/optimized plans and indexes
- `02_sql_and_viz/dashboard_mockup.py`: actual-data PDF dashboard generator
- `03_big_data/spark_pipeline.py`: five-table Spark pipeline
- `03_big_data/kafka_streaming.py`: topics, producer, consumer, forwarding, summary
- `03_big_data/airflow_dag.py`: scheduled DAG with DQ gate and XCom report
- `04_infrastructure/dq_framework.py`: reusable DQ framework
- `04_infrastructure/data_governance.md`: governance deliverable
- Root `Dockerfile`, `.dockerignore`, and `docker-compose.override.yml`: deployment

## Execution evidence

Per instruction, no code, SQL, container build, Kafka client, Spark job, Airflow DAG, or dashboard generator was run. Therefore generated CSV/Parquet/JSON/PDF artifacts, actual row-level DQ counts, query plans, timing measurements, and speedup factors are not claimed. `query_optimization.sql` marks these fields `[NOT RUN]` rather than fabricating evidence.
