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
- `outputs/results/sanjay_subair/02_sql_and_viz/Presight Spend Performance.pbix`: one-page Power BI executive dashboard
- `03_big_data/spark_pipeline.py`: five-table Spark pipeline
- `03_big_data/kafka_streaming.py`: topics, producer, consumer, forwarding, summary
- `03_big_data/airflow_dag.py`: scheduled DAG with DQ gate and XCom report
- `04_infrastructure/dq_framework.py`: reusable DQ framework
- `04_infrastructure/data_governance.md`: governance deliverable
- Root `Dockerfile`, `.dockerignore`, and `docker-compose.override.yml`: deployment

## Execution evidence

The submission has been exercised against the supplied datasets and local Docker services. Generated artifacts are stored under `outputs/results/sanjay_subair/`.

- Foundations outputs are present for 500 projects and 1,000 employees, including the employee quality summary.
- The full Pandas ETL processed 50,000 transactions and wrote cleaned project, employee, and transaction CSV files plus `pipeline_summary.txt`.
- `query_optimization.sql` records measured DuckDB `EXPLAIN ANALYZE` results: 12.9 ms before and 9.1 ms after optimization, a 1.42x speedup.
- The Power BI deliverable is present as `outputs/results/sanjay_subair/02_sql_and_viz/Presight Spend Performance.pbix`.
- The Spark pipeline produced all five required Parquet tables under `03_big_data/spark/`, including the required `event_date` and `severity` partitioning.
- Kafka was run end to end against the Docker broker. It produced and consumed 8,333 January events, forwarded 14 Critical escalations, and wrote `03_big_data/kafka/summary.json`.
- The Airflow DAG was parsed and tested in Docker. All nine tasks completed successfully, including the DQ gate, transformations, output load, XCom exchanges, and pipeline report generation.
- Docker Compose services for Kafka, Zookeeper, Kafka UI, PostgreSQL, and Airflow were started and validated. The Python ETL image contains the dependencies installed from `requirements.txt`.
- The DQ framework was exercised through the Airflow gate across projects, employees, and transactions; detailed DQ results are included in the generated pipeline report.

No separate `outputs/results/sanjay_subair/04_infrastructure/` directory is currently generated. Pillar 4 source deliverables are stored under `solutions/submissions/sanjay_subair/04_infrastructure/`.
