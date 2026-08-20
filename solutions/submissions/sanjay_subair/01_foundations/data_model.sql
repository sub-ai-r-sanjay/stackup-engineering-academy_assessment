-- Presight analytics warehouse schema and SCD Type 2 load (DuckDB SQL).
-- Run after the Foundations ETL has produced its clean CSV outputs.

-- ===========================================================================
-- SECTION 1 — TASK 1.2: Design the data model (Star Schema)
-- ===========================================================================


CREATE SEQUENCE IF NOT EXISTS date_key_seq START 1;
CREATE SEQUENCE IF NOT EXISTS project_key_seq START 1;
CREATE SEQUENCE IF NOT EXISTS employee_key_seq START 1;
CREATE SEQUENCE IF NOT EXISTS vendor_key_seq START 1;
CREATE SEQUENCE IF NOT EXISTS transaction_key_seq START 1;

CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER PRIMARY KEY DEFAULT nextval('date_key_seq'),
    full_date DATE NOT NULL UNIQUE,
    year SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    month SMALLINT NOT NULL CHECK (month BETWEEN 1 AND 12),
    month_name VARCHAR NOT NULL,
    week SMALLINT NOT NULL,
    day SMALLINT NOT NULL,
    day_of_week VARCHAR NOT NULL,
    is_weekend BOOLEAN NOT NULL
);

-- Project attributes are separated from transaction measures and retain project_id.
CREATE TABLE IF NOT EXISTS dim_project (
    project_key INTEGER PRIMARY KEY DEFAULT nextval('project_key_seq'),
    project_id VARCHAR NOT NULL UNIQUE,
    project_name VARCHAR NOT NULL,
    department VARCHAR,
    status VARCHAR,
    status_category VARCHAR,
    start_date DATE,
    end_date DATE,
    budget DECIMAL(18, 2) NOT NULL DEFAULT 0,
    actual_cost DECIMAL(18, 2) NOT NULL DEFAULT 0,
    project_manager_id VARCHAR,
    priority VARCHAR,
    region VARCHAR,
    risk_level VARCHAR
);

-- Employee is SCD2: the surrogate key identifies a version while employee_id
-- identifies the person. Half-open timestamp periods [valid_from, valid_to)
-- preserve distinct same-day source changes without creating negative date ranges;
-- source order deterministically sequences events because the export has no times.
CREATE TABLE IF NOT EXISTS dim_employee (
    employee_key INTEGER PRIMARY KEY DEFAULT nextval('employee_key_seq'),
    employee_id VARCHAR NOT NULL,
    full_name VARCHAR NOT NULL,
    email VARCHAR,
    department VARCHAR,
    role VARCHAR,
    level VARCHAR,
    hire_date DATE,
    salary DECIMAL(18, 2),
    manager_id VARCHAR,
    region VARCHAR,
    employment_status VARCHAR,
    years_experience INTEGER,
    valid_from TIMESTAMP NOT NULL,
    valid_to TIMESTAMP NOT NULL,
    is_current BOOLEAN NOT NULL,
    change_reason VARCHAR,
    CHECK (valid_from < valid_to),
    CHECK ((is_current AND valid_to = TIMESTAMP '9999-12-31 00:00:00') OR NOT is_current),
    UNIQUE (employee_id, valid_from)
);

-- Vendor is deduplicated independently because one vendor serves many projects.
CREATE TABLE IF NOT EXISTS dim_vendor (
    vendor_key INTEGER PRIMARY KEY DEFAULT nextval('vendor_key_seq'),
    vendor_id VARCHAR NOT NULL UNIQUE,
    vendor_name VARCHAR NOT NULL
);

-- The bridge resolves the employee/project many-to-many relationship. A role and
-- effective period support team membership changes without altering the fact grain.
CREATE TABLE IF NOT EXISTS bridge_employee_project (
    employee_key INTEGER NOT NULL REFERENCES dim_employee(employee_key),
    project_key INTEGER NOT NULL REFERENCES dim_project(project_key),
    assignment_role VARCHAR NOT NULL,
    valid_from DATE NOT NULL,
    valid_to DATE NOT NULL,
    PRIMARY KEY (employee_key, project_key, valid_from),
    CHECK (valid_from <= valid_to)
);

-- One fact row represents one source transaction; all dimensions use surrogate FKs.
CREATE TABLE IF NOT EXISTS fact_transactions (
    transaction_key BIGINT PRIMARY KEY DEFAULT nextval('transaction_key_seq'),
    transaction_id VARCHAR NOT NULL UNIQUE,
    project_key INTEGER NOT NULL REFERENCES dim_project(project_key),
    employee_key INTEGER REFERENCES dim_employee(employee_key),
    vendor_key INTEGER NOT NULL REFERENCES dim_vendor(vendor_key),
    date_key INTEGER NOT NULL REFERENCES dim_date(date_key),
    amount DECIMAL(18, 2) NOT NULL,
    category VARCHAR,
    payment_status VARCHAR
);

-- Staging tables retain source shape and make the load repeatable.
CREATE OR REPLACE TEMP TABLE stg_projects AS
SELECT * FROM read_csv_auto(
    'outputs/results/sanjay_subair/01_foundations/projects_clean.csv',
    header = true
);
CREATE OR REPLACE TEMP TABLE stg_employees AS
SELECT * FROM read_csv_auto(
    'outputs/results/sanjay_subair/01_foundations/employees_clean.csv',
    header = true
);

-- ===========================================================================
-- SECTION 2 — Load staging data
-- ===========================================================================

CREATE OR REPLACE TEMP TABLE stg_salary_history AS
SELECT
    *,
    ROW_NUMBER() OVER () AS source_row_number
FROM read_csv_auto('datasets/employees_salary_history.csv', header = true);
CREATE OR REPLACE TEMP TABLE stg_transactions AS
SELECT * FROM read_json_auto('datasets/transactions.json');

INSERT INTO dim_date (full_date, year, quarter, month, month_name, week, day, day_of_week, is_weekend)
SELECT
    calendar_date,
    year(calendar_date),
    quarter(calendar_date),
    month(calendar_date),
    monthname(calendar_date),
    week(calendar_date),
    day(calendar_date),
    dayname(calendar_date),
    dayofweek(calendar_date) IN (0, 6)
FROM generate_series(DATE '2010-01-01', DATE '2035-12-31', INTERVAL 1 DAY) AS dates(calendar_date)
ON CONFLICT (full_date) DO NOTHING;

INSERT INTO dim_project (
    project_id, project_name, department, status, status_category, start_date,
    end_date, budget, actual_cost, project_manager_id, priority, region, risk_level
)
SELECT
    project_id, project_name, department, status, status_category,
    CAST(start_date AS DATE), CAST(end_date AS DATE), budget, actual_cost,
    project_manager_id, priority, region, risk_level
FROM stg_projects
ON CONFLICT (project_id) DO NOTHING;

-- The source supplies dates but can contain multiple ordered changes on one day.
-- A one-second offset based on export order preserves every record as a distinct
-- version. Half-open periods meet at exact boundaries, so no day subtraction is
-- needed and same-day changes cannot produce a valid_to before valid_from.
WITH ordered_history AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id, CAST(effective_date AS DATE)
            ORDER BY source_row_number
        ) AS same_day_sequence
    FROM stg_salary_history
),
history_states AS (
    SELECT
        e.employee_id, e.full_name, e.email, e.department,
        h.new_role AS role, h.new_level AS level, CAST(e.hire_date AS DATE) AS hire_date,
        h.new_salary AS salary, e.manager_id, e.region, e.status AS employment_status,
        e.years_experience,
        CAST(h.effective_date AS TIMESTAMP)
            + (h.same_day_sequence - 1) * INTERVAL 1 SECOND AS valid_from,
        h.change_reason
    FROM ordered_history h
    JOIN stg_employees e USING (employee_id)
),
latest_history AS (
    SELECT employee_id, MAX(CAST(effective_date AS DATE)) AS latest_effective_date
    FROM ordered_history
    GROUP BY employee_id
),
current_states AS (
    SELECT
        e.employee_id, e.full_name, e.email, e.department, e.role, e.level,
        CAST(e.hire_date AS DATE) AS hire_date, e.salary, e.manager_id, e.region,
        e.status AS employment_status, e.years_experience,
        CASE
            WHEN h.latest_effective_date IS NULL THEN CAST(e.hire_date AS TIMESTAMP)
            ELSE h.latest_effective_date + INTERVAL 1 DAY
        END::TIMESTAMP AS valid_from,
        CASE WHEN h.latest_effective_date IS NULL THEN 'Initial current record'
             ELSE 'Current source snapshot' END AS change_reason
    FROM stg_employees e
    LEFT JOIN latest_history h USING (employee_id)
),
all_states AS (
    SELECT * FROM history_states
    UNION ALL
    SELECT * FROM current_states
),
versioned AS (
    SELECT
        *,
        LEAD(valid_from) OVER (PARTITION BY employee_id ORDER BY valid_from) AS next_valid_from
    FROM all_states
)
INSERT INTO dim_employee (
    employee_id, full_name, email, department, role, level, hire_date, salary,
    manager_id, region, employment_status, years_experience, valid_from,
    valid_to, is_current, change_reason
)
SELECT
    employee_id, full_name, email, department, role, level, hire_date, salary,
    manager_id, region, employment_status, years_experience, valid_from,
    COALESCE(next_valid_from, TIMESTAMP '9999-12-31 00:00:00'),
    next_valid_from IS NULL,
    change_reason
FROM versioned
ON CONFLICT (employee_id, valid_from) DO NOTHING;

INSERT INTO dim_vendor (vendor_id, vendor_name)
SELECT DISTINCT vendor_id, vendor_name
FROM stg_transactions
WHERE vendor_id IS NOT NULL
ON CONFLICT (vendor_id) DO NOTHING;

INSERT INTO bridge_employee_project (employee_key, project_key, assignment_role, valid_from, valid_to)
SELECT
    e.employee_key,
    p.project_key,
    'Project Manager',
    COALESCE(p.start_date, e.hire_date),
    GREATEST(
        COALESCE(p.end_date, DATE '9999-12-31'),
        COALESCE(p.start_date, e.hire_date)
    )
FROM dim_project p
JOIN dim_employee e
  ON e.employee_id = p.project_manager_id
 AND e.is_current
ON CONFLICT DO NOTHING;

INSERT INTO fact_transactions (
    transaction_id, project_key, employee_key, vendor_key, date_key,
    amount, category, payment_status
)
SELECT
    t.transaction_id, p.project_key, e.employee_key, v.vendor_key, d.date_key,
    COALESCE(t.amount, 0), t.category, t.payment_status
FROM stg_transactions t
JOIN dim_project p USING (project_id)
JOIN dim_vendor v USING (vendor_id)
JOIN dim_date d ON d.full_date = CAST(t.transaction_date AS DATE)
LEFT JOIN dim_employee e
  ON e.employee_id = t.approved_by
 -- Transactions have date-only granularity, so use the final employee state of
 -- that day while retaining the half-open timestamp validity contract.
 AND CAST(t.transaction_date AS TIMESTAMP) + INTERVAL 1 DAY - INTERVAL 1 MICROSECOND >= e.valid_from
 AND CAST(t.transaction_date AS TIMESTAMP) + INTERVAL 1 DAY - INTERVAL 1 MICROSECOND < e.valid_to
ON CONFLICT (transaction_id) DO NOTHING;


-- ===========================================================================
-- SECTION 3 — TASK 2.1: Answer five business questions
-- ===========================================================================

-- Q1: must return zero rows; exactly one current row is required per employee.
SELECT employee_id, COUNT(*) FILTER (WHERE is_current) AS current_count
FROM dim_employee
GROUP BY employee_id
HAVING COUNT(*) FILTER (WHERE is_current) <> 1;

-- Q2: shows employees with the deepest version history.
SELECT employee_id, COUNT(*) AS version_count
FROM dim_employee
GROUP BY employee_id
ORDER BY version_count DESC
LIMIT 10;

-- Q3: must return zero rows; touching half-open boundaries do not overlap.
SELECT current.employee_id, current.employee_key, comparison.employee_key
FROM dim_employee current
JOIN dim_employee comparison
  ON current.employee_id = comparison.employee_id
 AND current.employee_key < comparison.employee_key
 AND current.valid_from < comparison.valid_to
 AND comparison.valid_from < current.valid_to;
