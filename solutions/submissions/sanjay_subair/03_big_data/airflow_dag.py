"""Daily 06:00 Asia/Dubai Presight ETL DAG."""

from __future__ import annotations

import json
import os
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd
import pendulum
from airflow import DAG
from airflow.operators.empty import EmptyOperator
from airflow.operators.python import PythonOperator

THIS_DIR = Path(__file__).resolve().parent
DEFAULT_ROOT = THIS_DIR.parents[3] if len(THIS_DIR.parents) > 3 else Path("/opt/airflow")
REPO_ROOT = Path(os.getenv("REPO_ROOT", DEFAULT_ROOT))
SUBMISSION_DIR = Path(os.getenv("SUBMISSION_DIR", THIS_DIR.parent))
ETL_DIR = SUBMISSION_DIR / "02_sql_and_viz"
DQ_DIR = SUBMISSION_DIR / "04_infrastructure"
sys.path[:0] = [str(ETL_DIR), str(DQ_DIR)]

from dq_framework import run_data_quality_checks  # noqa: E402
from etl_full import (  # noqa: E402
    OUTPUT_DIR,
    clean_employees,
    enrich_transactions,
    load_employees,
    load_projects,
    load_transactions,
    transform_projects,
    write_outputs,
)

DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "datasets"))
STAGING_DIR = Path(os.getenv("AIRFLOW_STAGING_DIR", REPO_ROOT / "outputs" / "airflow_staging"))


def _push_count(context: dict, key: str, frame: pd.DataFrame) -> str:
    context["ti"].xcom_push(key=key, value=len(frame))
    return f"{key}={len(frame)}"


def task_extract_projects(**context) -> str:
    return _push_count(context, "projects_raw_count", load_projects(DATA_DIR / "projects.csv"))


def task_extract_employees(**context) -> str:
    return _push_count(context, "employees_raw_count", load_employees(DATA_DIR / "employees.csv"))


def task_extract_transactions(**context) -> str:
    return _push_count(context, "transactions_raw_count", load_transactions(DATA_DIR / "transactions.json"))


def task_validate_data_quality(**context) -> None:
    projects = load_projects(DATA_DIR / "projects.csv")
    employees = load_employees(DATA_DIR / "employees.csv")
    transactions = load_transactions(DATA_DIR / "transactions.json")
    references = {"projects": projects, "employees": employees, "transactions": transactions}
    results = {
        name: run_data_quality_checks(frame, name, references, write_report=False)
        for name, frame in references.items()
    }
    critical_failures = []
    for name, frame in references.items():
        key_columns = {
            "projects": ["project_id"],
            "employees": ["employee_id"],
            "transactions": ["transaction_id", "project_id"],
        }[name]
        for column in key_columns:
            completeness = float(frame[column].notna().mean())
            if completeness < 0.80:
                critical_failures.append(f"{name}.{column} completeness={completeness:.1%}")
    context["ti"].xcom_push(key="dq_results", value=results)
    if critical_failures:
        raise ValueError("Critical DQ gate failure: " + "; ".join(critical_failures))


def task_transform_and_enrich(**context) -> None:
    projects = transform_projects(load_projects(DATA_DIR / "projects.csv"))
    employees, employee_quality = clean_employees(load_employees(DATA_DIR / "employees.csv"))
    transactions = enrich_transactions(
        load_transactions(DATA_DIR / "transactions.json"), projects, employees
    )
    STAGING_DIR.mkdir(parents=True, exist_ok=True)
    paths = {
        "projects": STAGING_DIR / "projects.parquet",
        "employees": STAGING_DIR / "employees.parquet",
        "transactions": STAGING_DIR / "transactions.parquet",
    }
    projects.to_parquet(paths["projects"], index=False)
    employees.to_parquet(paths["employees"], index=False)
    transactions.to_parquet(paths["transactions"], index=False)
    task_instance = context["ti"]
    for name, frame in (("projects", projects), ("employees", employees), ("transactions", transactions)):
        task_instance.xcom_push(key=f"{name}_clean_count", value=len(frame))
    task_instance.xcom_push(key="employee_quality", value=employee_quality)
    task_instance.xcom_push(key="staging_paths", value={key: str(value) for key, value in paths.items()})


def task_load_to_output(**context) -> None:
    task_instance = context["ti"]
    paths = task_instance.xcom_pull(task_ids="transform_and_enrich", key="staging_paths")
    projects = pd.read_parquet(paths["projects"])
    employees = pd.read_parquet(paths["employees"])
    transactions = pd.read_parquet(paths["transactions"])
    raw_counts = {
        name: task_instance.xcom_pull(task_ids=f"extract_{name}", key=f"{name}_raw_count")
        for name in ("projects", "employees", "transactions")
    }
    employee_quality = task_instance.xcom_pull(task_ids="transform_and_enrich", key="employee_quality")
    files = write_outputs(projects, employees, transactions, raw_counts, employee_quality, 0.0)
    task_instance.xcom_push(key="files_written", value=files)


def task_generate_pipeline_report(**context) -> str:
    task_instance = context["ti"]
    logical_date = context["logical_date"]
    lines = [f"Presight ETL report: {logical_date.isoformat()}", "", "Raw -> clean row counts:"]
    for name in ("projects", "employees", "transactions"):
        raw = task_instance.xcom_pull(task_ids=f"extract_{name}", key=f"{name}_raw_count")
        clean = task_instance.xcom_pull(task_ids="transform_and_enrich", key=f"{name}_clean_count")
        lines.append(f"- {name}: {raw} -> {clean}")
    dq_results = task_instance.xcom_pull(task_ids="validate_data_quality", key="dq_results")
    lines.extend(["", "DQ results:", json.dumps(dq_results, indent=2, default=str), "", "Files written:"])
    files = task_instance.xcom_pull(task_ids="load_to_output", key="files_written") or []
    lines.extend(f"- {path}" for path in files)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / f"pipeline_report_{logical_date.date()}.txt"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(report_path)


def log_failure(context: dict) -> None:
    task = context.get("task_instance")
    exception = context.get("exception")
    print(f"Task failure: {task.task_id if task else 'unknown'}: {exception}")


default_args = {
    "owner": "sanjay_subair",
    "depends_on_past": False,
    "start_date": pendulum.datetime(2025, 1, 1, tz="Asia/Dubai"),
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
    "on_failure_callback": log_failure,
}

with DAG(
    dag_id="presight_etl_pipeline",
    default_args=default_args,
    description="Daily ETL pipeline for Presight project management data",
    schedule="0 6 * * *",
    catchup=False,
    max_active_runs=1,
    tags=["presight", "etl", "assessment"],
) as dag:
    start = EmptyOperator(task_id="start")
    extract_projects = PythonOperator(task_id="extract_projects", python_callable=task_extract_projects)
    extract_employees = PythonOperator(task_id="extract_employees", python_callable=task_extract_employees)
    extract_transactions = PythonOperator(task_id="extract_transactions", python_callable=task_extract_transactions)
    validate_data_quality = PythonOperator(task_id="validate_data_quality", python_callable=task_validate_data_quality)
    transform_and_enrich = PythonOperator(task_id="transform_and_enrich", python_callable=task_transform_and_enrich)
    load_to_output = PythonOperator(task_id="load_to_output", python_callable=task_load_to_output)
    generate_pipeline_report = PythonOperator(task_id="generate_pipeline_report", python_callable=task_generate_pipeline_report)
    end = EmptyOperator(task_id="end")

    extracts = [extract_projects, extract_employees, extract_transactions]
    start >> extracts >> validate_data_quality >> transform_and_enrich >> load_to_output >> generate_pipeline_report >> end
