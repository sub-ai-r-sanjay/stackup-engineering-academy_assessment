-- Task 2.3 query optimization
-- Run both EXPLAIN ANALYZE statements in the same populated database session.


-- 4a: Baseline plan. The original query is unchanged from the starter file.
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

-- Baseline evidence (DuckDB, 1,000 employees / 500 projects / 50,000 transactions):
-- Total execution time: 0.0129s (12.9 ms); result: 923 rows.
-- Condensed EXPLAIN ANALYZE output (operator, access method, output rows):
--   TABLE_SCAN transactions | Sequential Scan | Pending filter       | 8,927
--   UNGROUPED_AGGREGATE     | avg(amount)                            |     1
--   TABLE_SCAN transactions | Sequential Scan | amount > 64552.30    | 2,127
--   TABLE_SCAN projects     | Sequential Scan | open-status filter   |   239
--   HASH_JOIN               | project_id = project_id                |   923
--   TABLE_SCAN employees    | Sequential Scan | dynamic ID filters   |   147
--   HASH_JOIN               | employee_id = project_manager_id       |   923
--   ORDER_BY                | department ASC, amount DESC             |   923
-- Bottleneck join: no join is a material bottleneck at this scale; both hash joins
-- report 0.00s. The transaction side of the project join is the largest join input.
-- Highest-cost work: two scans of transactions, followed by sorting the 923 results.
-- Full scans: all three tables use Sequential Scan. Indexes could help at larger
-- scale when Pending and above-average rows are more selective; scans are cheaper
-- for this 50,000-row columnar DuckDB workload.
-- Subquery execution: despite looking correlated, it references no outer column.
-- DuckDB executes AVG once as a one-row aggregate rather than once per result row.

-- 4c: Production indexes and trade-offs.
-- Accelerates payment-status equality plus the amount range. payment_status comes
-- first because it is tested with equality, amount follows for the range predicate,
-- and project_id is last to carry the subsequent join key. Each transaction insert
-- or update pays one extra composite-index maintenance operation and storage cost.
CREATE INDEX IF NOT EXISTS idx_transactions_status_amount_project
    ON transactions (payment_status, amount, project_id);
-- Accelerates filtering projects by status before retrieving manager and project
-- join keys. status leads because it is the query predicate; manager and project IDs
-- support the downstream joins. The 500-row table gets little benefit today, while
-- every project status, manager, or ID change must maintain a wider index.
CREATE INDEX IF NOT EXISTS idx_projects_status_manager_project
    ON projects (status, project_manager_id, project_id);
-- Accelerates the natural-key manager lookup used by the employee/project join.
-- It is a narrow index, so employee inserts and employee_id changes incur one small
-- additional index write. In production this should be UNIQUE if IDs are guaranteed.
CREATE INDEX IF NOT EXISTS idx_employees_employee_id
    ON employees (employee_id);

-- 4b: Rewritten query, benchmarked for 4d below.
-- Changes: explicit JOINs expose join intent; pending_average replaces the scalar
-- subquery; transaction and project predicates are pushed into CTEs; every CTE and
-- the final SELECT project only required columns. MATERIALIZED guarantees that the
-- one-row threshold is calculated once. These satisfy four requested optimizations.
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
    transactions.amount,
    transactions.category,
    transactions.payment_status,
    transactions.transaction_date
FROM material_pending transactions
JOIN open_projects project ON project.project_id = transactions.project_id
JOIN employees employee ON employee.employee_id = project.project_manager_id
ORDER BY employee.department, transactions.amount DESC;

-- Optimized evidence (same populated DuckDB session, after index creation):
-- Total execution time: 0.0091s (9.1 ms); result: 923 rows.
-- Condensed EXPLAIN ANALYZE output (operator, access method, output rows):
--   TABLE_SCAN transactions | Sequential Scan | Pending filter       | 8,927
--   UNGROUPED_AGGREGATE     | avg(amount), materialized CTE           |     1
--   CTE_SCAN                | pending_average                         |     1
--   TABLE_SCAN transactions | Sequential Scan | amount > 64552.30    | 2,127
--   NESTED_LOOP_JOIN        | amount > average_pending_amount         | 2,127
--   TABLE_SCAN projects     | Sequential Scan | open-status filter   |   239
--   HASH_JOIN               | project_id = project_id                 |   923
--   TABLE_SCAN employees    | Sequential Scan | dynamic ID filters   |   147
--   HASH_JOIN               | employee_id = project_manager_id        |   923
--   ORDER_BY                | department ASC, amount DESC             |   923
-- Speedup factor: 1.42x faster (12.9 ms -> 9.1 ms, a 29.5% reduction).
-- Index confirmation: no Index Scan appeared. DuckDB chose vectorized sequential
-- scans because Pending matches 8,927 of 50,000 rows and the dimension tables are
-- small. The indexes remain appropriate production DDL for larger, more selective
-- workloads, but claiming index use for this measured data would be inaccurate.
