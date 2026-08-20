"""Full Pandas ETL for the 50,000-row transaction source."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parents[3]
FOUNDATIONS_DIR = THIS_DIR.parent / "01_foundations"
sys.path.insert(0, str(FOUNDATIONS_DIR))

from etl_pipeline import clean_employees, load_employees, load_projects, transform_projects  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(os.getenv("DATA_DIR", REPO_ROOT / "datasets"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", REPO_ROOT / "outputs" / "results" / "sanjay_subair" / "02_sql_and_viz"))


def load_transactions(filepath: str | Path) -> pd.DataFrame:
    """Flatten transaction JSON and apply documented null decisions."""
    with Path(filepath).open(encoding="utf-8") as source:
        records = json.load(source)
    transactions = pd.json_normalize(records)
    transactions["transaction_date"] = pd.to_datetime(
        transactions["transaction_date"], errors="coerce"
    )
    # Unknown amounts are retained in `amount` for lineage and represented as zero
    # in `amount_aed`, preventing nulls from breaking arithmetic without inventing spend.
    transactions["amount"] = pd.to_numeric(transactions["amount"], errors="coerce")
    # A null approver means unapproved; it remains null and drives is_approved=False.
    transactions["approved_by"] = transactions["approved_by"].astype("string")
    logger.info("Loaded %d transaction rows", len(transactions))
    return transactions


def enrich_transactions(
    transactions: pd.DataFrame,
    projects: pd.DataFrame,
    employees: pd.DataFrame,
) -> pd.DataFrame:
    """Join dimension context without changing the transaction grain."""
    project_lookup = projects[["project_id", "project_name", "department"]].drop_duplicates("project_id")
    employee_lookup = (
        employees[["employee_id", "full_name"]]
        .drop_duplicates("employee_id")
        .rename(columns={"employee_id": "approved_by", "full_name": "approver_full_name"})
    )
    enriched = transactions.merge(
        project_lookup, on="project_id", how="left", validate="many_to_one"
    ).merge(
        employee_lookup, on="approved_by", how="left", validate="many_to_one"
    )
    if len(enriched) != len(transactions):
        raise ValueError("Enrichment changed transaction grain")
    enriched["is_approved"] = enriched["approved_by"].notna()
    enriched["amount_aed"] = enriched["amount"].fillna(0.0).astype(float)
    enriched["transaction_year_month"] = enriched["transaction_date"].dt.strftime("%Y-%m")
    return enriched


def write_outputs(
    projects: pd.DataFrame,
    employees: pd.DataFrame,
    transactions: pd.DataFrame,
    raw_counts: dict[str, int],
    employee_quality: dict[str, int],
    elapsed_seconds: float,
) -> list[str]:
    """Write all clean tables and the required run summary."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        "projects": OUTPUT_DIR / "projects_clean.csv",
        "employees": OUTPUT_DIR / "employees_clean.csv",
        "transactions": OUTPUT_DIR / "transactions_clean.csv",
    }
    projects.to_csv(outputs["projects"], index=False, date_format="%Y-%m-%d")
    employees.to_csv(outputs["employees"], index=False, date_format="%Y-%m-%d")
    transactions.to_csv(outputs["transactions"], index=False, date_format="%Y-%m-%d")

    clean_counts = {
        "projects": len(projects),
        "employees": len(employees),
        "transactions": len(transactions),
    }
    summary_lines = [
        f"Run timestamp (UTC): {datetime.now(timezone.utc).isoformat()}",
        f"Execution time seconds: {elapsed_seconds:.3f}",
        "",
        "Row counts (raw -> clean):",
        *[
            f"- {name}: {raw_counts[name]} -> {clean_counts[name]}"
            for name in ("projects", "employees", "transactions")
        ],
        "",
        "Data quality decisions:",
        "- Null transaction amounts remain null in amount and become 0.0 in amount_aed.",
        "- Null approved_by values remain null and produce is_approved=False.",
        "- Invalid transaction dates are retained as null for traceability.",
        f"- Employee fixes: {json.dumps(employee_quality, sort_keys=True)}",
    ]
    summary_path = OUTPUT_DIR / "pipeline_summary.txt"
    summary_path.write_text("\n".join(summary_lines) + "\n", encoding="utf-8")
    return [str(path) for path in outputs.values()] + [str(summary_path)]


def run_pipeline() -> dict[str, object]:
    """Execute load, transform, enrichment, and output stages."""
    started = time.perf_counter()
    raw_projects = load_projects(DATA_DIR / "projects.csv")
    raw_employees = load_employees(DATA_DIR / "employees.csv")
    raw_transactions = load_transactions(DATA_DIR / "transactions.json")
    raw_counts = {
        "projects": len(raw_projects),
        "employees": len(raw_employees),
        "transactions": len(raw_transactions),
    }

    projects = transform_projects(raw_projects)
    employees, employee_quality = clean_employees(raw_employees)
    transactions = enrich_transactions(raw_transactions, projects, employees)
    elapsed = time.perf_counter() - started
    files = write_outputs(
        projects,
        employees,
        transactions,
        raw_counts,
        employee_quality,
        elapsed,
    )
    logger.info("Pipeline completed in %.3f seconds", elapsed)
    return {"raw_counts": raw_counts, "clean_counts": {
        "projects": len(projects), "employees": len(employees), "transactions": len(transactions)
    }, "files": files, "elapsed_seconds": elapsed}


if __name__ == "__main__":
    run_pipeline()
