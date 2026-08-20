"""Foundations ETL for projects and employees.

Run from the repository root with:
    python solutions/submissions/sanjay_subair/01_foundations/etl_pipeline.py
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    )
)
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "datasets"))
OUTPUT_DIR = os.getenv(
    "OUTPUT_DIR",
    os.path.join(
        BASE_DIR,
        "outputs",
        "results",
        "sanjay_subair",
        "01_foundations",
    ),
)

STATUS_CATEGORY = {
    "In Progress": "Active",
    "Completed": "Closed",
    "Not Started": "Pending",
    "On Hold": "Pending",
}
LEVEL_SALARY_RANGES = {
    "Junior": (10000, 22000),
    "Mid": (15000, 32000),
    "Senior": (25000, 48000),
    "Lead": (35000, 65000),
    "Executive": (50000, 100000),
}
LEVEL_EXPERIENCE_RANGES = {
    "Junior": (0, 4),
    "Mid": (2, 10),
    "Senior": (5, 20),
    "Lead": (8, 30),
    "Executive": (10, 50),
}
PROJECT_DATE_COLUMNS = ["start_date", "end_date"]
EMPLOYEE_REQUIRED_COLUMNS = [
    "employee_id",
    "full_name",
    "email",
    "department",
    "role",
    "level",
    "hire_date",
    "salary",
    "manager_id",
    "region",
    "status",
    "years_experience",
]

# ==============================================================================
# TASK 1.1 — Load and transform projects.csv
# ==============================================================================


def load_projects(filepath: str) -> pd.DataFrame:
    """Load projects with explicit source dtypes and parsed dates."""
    projects = pd.read_csv(
        filepath,
        dtype={
            "project_id": "string",
            "project_name": "string",
            "department": "string",
            "status": "string",
            "project_manager_id": "string",
            "priority": "string",
            "region": "string",
        },
    )
    # Parse dates separately so malformed source values become nulls that can be
    # handled by downstream quality checks instead of stopping the whole load.
    for column in PROJECT_DATE_COLUMNS:
        projects[column] = pd.to_datetime(projects[column], errors="coerce")
    projects["budget"] = pd.to_numeric(projects["budget"], errors="coerce")
    projects["actual_cost"] = pd.to_numeric(projects["actual_cost"], errors="coerce")
    logger.info("Loaded %d project rows", len(projects))
    return projects


def transform_projects(projects: pd.DataFrame) -> pd.DataFrame:
    """Standardize and derive project attributes."""
    clean = projects.copy()
    clean["status"] = clean["status"].str.strip().str.title()
    clean["priority"] = clean["priority"].str.strip().str.title()
    # Null financial values are treated as zero, as required by Task 1.1.
    # This means a project with a missing budget and a positive actual cost
    # is marked as over budget because its cleaned budget is zero.
    clean[["budget", "actual_cost"]] = clean[["budget", "actual_cost"]].fillna(0.0)

    clean["budget_variance"] = clean["actual_cost"] - clean["budget"]
    clean["is_over_budget"] = clean["actual_cost"].gt(clean["budget"])
    clean["duration_days"] = (clean["end_date"] - clean["start_date"]).dt.days.astype("Int64")
    clean["budget_utilisation_pct"] = np.where(
        clean["budget"].gt(0),
        clean["actual_cost"].div(clean["budget"]).mul(100),
        np.nan,
    ).round(2)
    clean["status_category"] = clean["status"].map(STATUS_CATEGORY).fillna("Pending")

    high_risk = clean["priority"].eq("Critical") | clean["is_over_budget"]
    medium_risk = clean["priority"].eq("High") | clean["budget_utilisation_pct"].gt(90)
    clean["risk_level"] = np.where(
        high_risk,
        "High",
        np.where(
            medium_risk,
            "Medium",
            "Low",
        ),
    )
    return clean

# ==============================================================================
# TASK 1.3 — Data quality issues in employees.csv
# ==============================================================================

def load_employees(filepath: str) -> pd.DataFrame:
    """
    Load employees.csv and identify data quality issues.
    Initially loads every column as text.
    This is useful because malformed source values remain available for quality detection.
    """
    employees = pd.read_csv(filepath, dtype="string", keep_default_na=True)
    missing_columns = sorted(set(EMPLOYEE_REQUIRED_COLUMNS) - set(employees.columns))
    if missing_columns:
        raise ValueError(f"Employee file is missing required columns: {missing_columns}")
    employees = employees.replace(r"^\s*$", pd.NA, regex=True)
    logger.info("Loaded %d employee rows", len(employees))
    logger.info("Employee null counts: %s", employees.isna().sum().to_dict())
    return employees


def _log_issue(summary: dict[str, int], name: str, mask: pd.Series) -> None:
    # The helper keeps counting and logging consistent for every quality rule.
    count = int(mask.fillna(False).sum())
    summary[name] = count
    logger.info("Employee quality issue %-35s %d", name, count)


def clean_employees(employees: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Detect and repair employee completeness, validity, and consistency issues."""
    clean = employees.copy()
    summary: dict[str, int] = {"rows_before_cleaning": len(clean)}

    text_columns = [
        "employee_id",
        "full_name",
        "email",
        "department",
        "role",
        "level",
        "manager_id",
        "region",
        "status",
    ]
    for column in text_columns:
        clean[column] = clean[column].str.strip()

    # Issue 1: Missing and duplicate employee IDs cannot be repaired safely.
    missing_id = clean["employee_id"].isna()
    duplicate_id = clean["employee_id"].duplicated(keep="first") & clean["employee_id"].notna()
    _log_issue(summary, "missing_employee_id_dropped", missing_id)
    _log_issue(summary, "duplicate_employee_id_dropped", duplicate_id)
    clean = clean.loc[~(missing_id | duplicate_id)].copy()

    # Issue 2: Fill missing required text values with visible defaults.
    required_defaults = {
        "full_name": "Unknown Employee",
        "email": "unknown@presight.ai",
        "department": "Unknown",
        "role": "Unknown",
        "level": "Mid",
        "region": "Unknown",
        "status": "Inactive",
    }
    for column, default in required_defaults.items():
        missing = clean[column].isna()
        _log_issue(summary, f"missing_{column}", missing)
        clean.loc[missing, column] = default

    # Issue 3: Replace invalid email addresses with a standard placeholder.
    invalid_email = ~clean["email"].str.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", na=False)
    _log_issue(summary, "invalid_email", invalid_email)
    clean.loc[invalid_email, "email"] = "unknown@presight.ai"

    # Issue 4: Detect invalid or unreasonable hire dates.
    parsed_hire_date = pd.to_datetime(clean["hire_date"], errors="coerce")
    missing_hire_date = clean["hire_date"].isna()
    invalid_hire_date = clean["hire_date"].notna() & parsed_hire_date.isna()
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    implausible_hire_date = parsed_hire_date.lt("1950-01-01") | parsed_hire_date.gt(today)
    _log_issue(summary, "missing_hire_date", missing_hire_date)
    _log_issue(summary, "invalid_hire_date", invalid_hire_date)
    _log_issue(summary, "implausible_hire_date", implausible_hire_date)

    # Issue 5: Active status cannot be set before the hire date. 
    active_before_hire = clean["status"].str.title().eq("Active") & parsed_hire_date.gt(today)
    _log_issue(summary, "active_before_hire_status_conflict", active_before_hire)
    clean.loc[active_before_hire, "status"] = "Inactive"

    # Issue 6: Experience must be between 0 and 50 years.
    years_experience = pd.to_numeric(clean["years_experience"], errors="coerce")
    invalid_experience = years_experience.isna() | years_experience.lt(0) | years_experience.gt(50)
    _log_issue(summary, "invalid_years_experience", invalid_experience)
    level_experience_midpoint = clean["level"].map(
        {level: (bounds[0] + bounds[1]) // 2 for level, bounds in LEVEL_EXPERIENCE_RANGES.items()}
    )
    years_experience = years_experience.mask(invalid_experience, level_experience_midpoint).fillna(0)
    clean["years_experience"] = years_experience.round().astype("Int64")

    replacement_hire_date = today - pd.to_timedelta(clean["years_experience"].mul(365.25), unit="D")
    clean["hire_date"] = parsed_hire_date.mask(missing_hire_date | invalid_hire_date | implausible_hire_date, replacement_hire_date)
    

 
    # Issue 7: Salary must be in the global range and match the employee level.
    salary = pd.to_numeric(clean["salary"], errors="coerce")
    global_invalid_salary = salary.isna() | salary.lt(10000) | salary.gt(100000)
    salary_min = clean["level"].map({level: bounds[0] for level, bounds in LEVEL_SALARY_RANGES.items()})
    salary_max = clean["level"].map({level: bounds[1] for level, bounds in LEVEL_SALARY_RANGES.items()})
    salary_level_mismatch = salary.notna() & ((salary.lt(salary_min)) | (salary.gt(salary_max)))
    _log_issue(summary, "salary_out_of_range", global_invalid_salary)
    _log_issue(summary, "salary_level_mismatch", salary_level_mismatch & ~global_invalid_salary)
    level_salary_mean = clean["level"].map(
        {level: (bounds[0] + bounds[1]) / 2 for level, bounds in LEVEL_SALARY_RANGES.items()}
    )
    clean["salary"] = salary.mask(global_invalid_salary | salary_level_mismatch, level_salary_mean).round(2)

    # Issue 8: Standardize status and replace unsupported values.
    clean["status"] = clean["status"].str.title()
    known_status = clean["status"].isin(["Active", "Inactive", "Terminated", "On Leave"])
    _log_issue(summary, "invalid_status", ~known_status)
    clean.loc[~known_status, "status"] = "Inactive"

    # Issue 9: An employee cannot be their own manager.
    manager_self_reference = clean["manager_id"].eq(clean["employee_id"])
    _log_issue(summary, "manager_self_reference", manager_self_reference)
    clean.loc[manager_self_reference, "manager_id"] = pd.NA

    summary["rows_after_cleaning"] = len(clean)
    logger.info("Employee quality summary: %s", summary)
    return clean, summary


def write_outputs(projects: pd.DataFrame, employees: pd.DataFrame, summary: dict[str, int]) -> None:
    """Write clean datasets and a reproducible quality summary."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    projects_path = os.path.join(OUTPUT_DIR, "projects_clean.csv")
    employees_path = os.path.join(OUTPUT_DIR, "employees_clean.csv")
    summary_path = os.path.join(OUTPUT_DIR, "employee_quality_summary.json")

    projects.to_csv(projects_path, index=False, date_format="%Y-%m-%d")
    employees.to_csv(employees_path, index=False, date_format="%Y-%m-%d")
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "projects_rows": len(projects),
        "employees_rows": len(employees),
        "employee_fixes": summary,
    }
    with open(summary_path, "w", encoding="utf-8") as summary_file:
        json.dump(report, summary_file, indent=2)

    logger.info("Wrote projects output to %s", projects_path)
    logger.info("Wrote employees output to %s", employees_path)
    logger.info("Wrote quality summary to %s", summary_path)


def run_pipeline() -> None:
    projects_file = os.path.join(DATA_DIR, "projects.csv")
    employees_file = os.path.join(DATA_DIR, "employees.csv")

    projects = transform_projects(load_projects(projects_file))
    employees, quality_summary = clean_employees(load_employees(employees_file))
    write_outputs(projects, employees, quality_summary)
    logger.info("Foundations outputs written to %s", OUTPUT_DIR)


if __name__ == "__main__":
    run_pipeline()
