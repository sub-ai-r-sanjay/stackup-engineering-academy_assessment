"""Config-driven data quality framework shared by batch and Airflow pipelines."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[4]
REPORT_DIR = Path(os.getenv("OUTPUT_DIR", REPO_ROOT / "outputs" / "results" / "sanjay_subair" / "04_infrastructure"))

DQ_CONFIG: dict[str, dict[str, Any]] = {
    "projects": {
        "completeness_threshold": 0.90,
        "key_columns": ["project_id", "project_name", "department", "status"],
        "pk_columns": ["project_id"],
        "numeric_ranges": {"budget": {"min": 0, "max": 10000000}, "actual_cost": {"min": 0, "max": 10000000}},
        "date_columns": {"start_date": {"allow_future": False}, "end_date": {"allow_future": True}},
        "consistency_rules": [
            {"type": "before", "columns": ["start_date", "end_date"]},
            {"type": "non_negative", "column": "actual_cost"},
        ],
        "foreign_keys": {"project_manager_id": ("employees", "employee_id")},
    },
    "employees": {
        "completeness_threshold": 0.85,
        "key_columns": ["employee_id", "full_name", "department", "role", "level", "hire_date", "salary"],
        "pk_columns": ["employee_id"],
        "numeric_ranges": {"salary": {"min": 10000, "max": 100000}, "years_experience": {"min": 0, "max": 50}},
        "date_columns": {"hire_date": {"allow_future": False}},
        "consistency_rules": [{"type": "salary_level", "salary": "salary", "level": "level"}],
        "foreign_keys": {"manager_id": ("employees", "employee_id", True)},
    },
    "transactions": {
        "completeness_threshold": 0.90,
        "key_columns": ["transaction_id", "project_id", "vendor_id", "transaction_date", "payment_status"],
        "pk_columns": ["transaction_id"],
        "numeric_ranges": {"amount": {"min": 0, "max": 10000000}},
        "date_columns": {"transaction_date": {"allow_future": False}},
        "consistency_rules": [{"type": "non_negative", "column": "amount"}],
        "foreign_keys": {
            "project_id": ("projects", "project_id"),
            "approved_by": ("employees", "employee_id", True),
        },
    },
}

SALARY_LEVEL_RANGES = {
    "Junior": (10000, 22000), "Mid": (15000, 32000),
    "Senior": (25000, 48000), "Lead": (35000, 65000),
    "Executive": (50000, 100000),
}


def _result(status: bool, details: Any, **extra: Any) -> dict[str, Any]:
    return {"status": "PASS" if status else "FAIL", "details": details, **extra}


def _completeness(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    columns = [column for column in config["key_columns"] if column in frame]
    ratios = frame[columns].notna().mean().round(4).to_dict()
    threshold = config["completeness_threshold"]
    failed = [column for column, ratio in ratios.items() if ratio < threshold]
    return _result(not failed, ratios, failed_columns=failed, threshold=threshold)


def _uniqueness(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    columns = config["pk_columns"]
    duplicate_count = int(frame.duplicated(columns, keep=False).sum())
    return _result(duplicate_count == 0, f"{columns}: {duplicate_count} rows participate in duplicate keys")


def _numeric_validity(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    passed = True
    for column, bounds in config.get("numeric_ranges", {}).items():
        if column not in frame:
            details[column] = "column missing"
            passed = False
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        below = int(values.lt(bounds["min"]).sum())
        above = int(values.gt(bounds["max"]).sum())
        unparseable = int(frame[column].notna().sum() - values.notna().sum())
        details[column] = {"below_min": below, "above_max": above, "unparseable": unparseable}
        passed &= below == 0 and above == 0 and unparseable == 0
    return _result(passed, details)


def _date_validity(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, Any] = {}
    passed = True
    today = pd.Timestamp.now(tz="UTC").tz_localize(None).normalize()
    for column, rule in config.get("date_columns", {}).items():
        if column not in frame:
            details[column] = "column missing"
            passed = False
            continue
        parsed = pd.to_datetime(frame[column], errors="coerce")
        invalid = int((frame[column].notna() & parsed.isna()).sum())
        future = int(parsed.gt(today).sum()) if not rule.get("allow_future", False) else 0
        details[column] = {"invalid": invalid, "unexpected_future": future}
        passed &= invalid == 0 and future == 0
    return _result(passed, details)


def _consistency(frame: pd.DataFrame, config: dict[str, Any]) -> dict[str, Any]:
    details: dict[str, int] = {}
    for index, rule in enumerate(config.get("consistency_rules", []), start=1):
        name = f"rule_{index}_{rule['type']}"
        if rule["type"] == "before":
            left = pd.to_datetime(frame[rule["columns"][0]], errors="coerce")
            right = pd.to_datetime(frame[rule["columns"][1]], errors="coerce")
            failures = left.notna() & right.notna() & left.gt(right)
        elif rule["type"] == "non_negative":
            failures = pd.to_numeric(frame[rule["column"]], errors="coerce").lt(0)
        elif rule["type"] == "salary_level":
            salary = pd.to_numeric(frame[rule["salary"]], errors="coerce")
            minimum = frame[rule["level"]].map({level: bounds[0] for level, bounds in SALARY_LEVEL_RANGES.items()})
            maximum = frame[rule["level"]].map({level: bounds[1] for level, bounds in SALARY_LEVEL_RANGES.items()})
            failures = salary.notna() & (salary.lt(minimum) | salary.gt(maximum))
        else:
            raise ValueError(f"Unsupported consistency rule: {rule['type']}")
        details[name] = int(failures.sum())
    return _result(all(count == 0 for count in details.values()), details)


def _referential_integrity(
    frame: pd.DataFrame,
    config: dict[str, Any],
    references: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    details: dict[str, int | str] = {}
    passed = True
    for column, relationship in config.get("foreign_keys", {}).items():
        reference_name, reference_column, *options = relationship
        allow_null = bool(options[0]) if options else False
        if reference_name not in references or column not in frame:
            details[column] = f"reference unavailable: {reference_name}.{reference_column}"
            passed = False
            continue
        source = frame[column]
        invalid = source.notna() & ~source.isin(references[reference_name][reference_column].dropna())
        if not allow_null:
            invalid |= source.isna()
        details[column] = int(invalid.sum())
        passed &= int(invalid.sum()) == 0
    return _result(passed, details)


def write_markdown_report(report: dict[str, Any]) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"dq_report_{report['dataset_name']}.md"
    lines = [f"# Data Quality Report: {report['dataset_name']}", "", f"- Checks run: {report['checks_run']}", f"- Passed: {report['checks_passed']}", f"- Failed: {report['checks_failed']}", "", "| Check | Status | Details |", "|---|---|---|"]
    for name, result in report["results"].items():
        details = str(result["details"]).replace("|", "\\|")
        lines.append(f"| {name} | {result['status']} | {details} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_data_quality_checks(
    frame: pd.DataFrame,
    dataset_name: str,
    references: dict[str, pd.DataFrame] | None = None,
    write_report: bool = True,
) -> dict[str, Any]:
    """Run six configured checks and return the required structured result."""
    if dataset_name not in DQ_CONFIG:
        raise KeyError(f"No DQ configuration for dataset: {dataset_name}")
    config = DQ_CONFIG[dataset_name]
    results = {
        "completeness": _completeness(frame, config),
        "uniqueness": _uniqueness(frame, config),
        "validity_numeric": _numeric_validity(frame, config),
        "validity_date": _date_validity(frame, config),
        "consistency": _consistency(frame, config),
        "referential_integrity": _referential_integrity(frame, config, references or {}),
    }
    for check_name, result in results.items():
        if result["status"] == "FAIL":
            logger.warning("DQ FAIL | %s | %s | %s", dataset_name, check_name, result["details"])
    report = {
        "dataset_name": dataset_name,
        "checks_run": len(results),
        "checks_passed": sum(result["status"] == "PASS" for result in results.values()),
        "checks_failed": sum(result["status"] == "FAIL" for result in results.values()),
        "results": results,
    }
    if write_report:
        write_markdown_report(report)
    return report
