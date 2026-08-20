-- Task 2.3 query optimization (DuckDB/PostgreSQL-compatible query body).
-- Run both EXPLAIN ANALYZE statements in the same populated database session.
-- Timings and plan text are intentionally not fabricated because code execution was prohibited.

-- 4a: Baseline plan. This preserves the supplied implicit joins and correlated-looking scalar subquery.
EXPLAIN ANALYZE
SELECT
    e.full_name, e.department, e.role, p.project_name, p.status,
    p.budget, p.actual_cost, t.amount, t.category, t.payment_status,
    t.transaction_date
FROM employees e, projects p, transactions t
WHERE e.employee_id = p.project_manager_id
  AND p.project_id = t.project_id
  AND p.status NOT IN ('Completed', 'On Hold')
  AND t.payment_status = 'Pending'
  AND t.amount > (
      SELECT AVG(amount)
      FROM transactions
      WHERE payment_status = 'Pending'
  )
ORDER BY e.department, t.amount DESC;

-- Baseline evidence to paste after execution:
-- Total execution time: [NOT RUN]
-- EXPLAIN ANALYZE output: [NOT RUN]
-- Expected bottlenecks to verify: transaction scan for Pending rows, repeated/scalar
-- aggregate handling, join cardinality before selective filtering, and final sort.

-- 4c: Production indexes. Composite order starts with equality predicates and then
-- the amount range; write overhead is one index update per inserted transaction.
CREATE INDEX IF NOT EXISTS idx_transactions_status_amount_project
    ON transactions (payment_status, amount, project_id);
-- Supports employee/project lookup. Read-heavy dashboards benefit; project updates
-- pay a small additional index maintenance cost.
CREATE INDEX IF NOT EXISTS idx_projects_status_manager_project
    ON projects (status, project_manager_id, project_id);
-- Supports the manager natural-key join; employee writes incur minimal extra cost.
CREATE INDEX IF NOT EXISTS idx_employees_employee_id
    ON employees (employee_id);

-- 4b/4d: Filter early, aggregate Pending once, use explicit joins, and project only
-- required columns. The MATERIALIZED keyword prevents recalculating the threshold.
EXPLAIN ANALYZE
WITH pending_average AS MATERIALIZED (
    SELECT AVG(amount) AS average_pending_amount
    FROM transactions
    WHERE payment_status = 'Pending'
),
material_pending AS (
    SELECT project_id, amount, category, payment_status, transaction_date
    FROM transactions
    CROSS JOIN pending_average
    WHERE payment_status = 'Pending'
      AND amount > average_pending_amount
),
open_projects AS (
    SELECT
        project_id, project_name, status, budget, actual_cost, project_manager_id
    FROM projects
    WHERE status NOT IN ('Completed', 'On Hold')
)
SELECT
    employee.full_name,
    employee.department,
    employee.role,
    project.project_name,
    project.status,
    project.budget,
    project.actual_cost,
    transaction.amount,
    transaction.category,
    transaction.payment_status,
    transaction.transaction_date
FROM material_pending transaction
JOIN open_projects project ON project.project_id = transaction.project_id
JOIN employees employee ON employee.employee_id = project.project_manager_id
ORDER BY employee.department, transaction.amount DESC;

-- Optimized evidence to paste after execution:
-- Total execution time: [NOT RUN]
-- EXPLAIN ANALYZE output: [NOT RUN]
-- Speedup factor: [NOT RUN]
-- Confirm the populated engine uses an index scan where selective enough. DuckDB may
-- choose a vectorized sequential scan for 50K rows; that is an optimizer choice, not
-- evidence that the index DDL is invalid.
