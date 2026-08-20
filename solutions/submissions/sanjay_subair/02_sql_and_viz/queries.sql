-- Task 2.1 business queries against the warehouse schema in data_model.sql.

-- Q1: Which departments have spent more than 90% of their total allocated budget? Include departments that are over budget.
-- Approach: Aggregate project budget and cost by department, then filter the grouped totals with HAVING.
-- Reason: Department utilisation must be calculated from combined values, and NULLIF prevents division by zero.
SELECT
    department,
    SUM(budget) AS total_budget,
    SUM(actual_cost) AS total_actual_cost,
    ROUND(SUM(actual_cost) / NULLIF(SUM(budget), 0)*100.0, 2) AS spend_percentage,
    SUM(actual_cost) > SUM(budget) AS over_budget
FROM dim_project
GROUP BY department
HAVING SUM(actual_cost) > 0.90 * SUM(budget)
ORDER BY spend_percentage DESC;

-- Q2: Which managers are currently overseeing more than three active projects?
-- Approach: Join projects to the current employee dimension version, filter active projects, and aggregate by manager.
-- Reason: The SCD2 current flag avoids duplicate historical employee versions, while DISTINCT protects the project count.
SELECT
    employee.full_name,
    employee.email,
    COUNT(DISTINCT project.project_id) AS active_project_count,
    SUM(project.budget) AS combined_budget_responsibility,
    SUM(project.actual_cost) AS combined_actual_spend
FROM dim_project project
JOIN dim_employee employee
  ON employee.employee_id = project.project_manager_id
 AND employee.is_current
WHERE project.status = 'In Progress'
GROUP BY employee.employee_key, employee.full_name, employee.email
HAVING COUNT(DISTINCT project.project_id) > 3
ORDER BY active_project_count DESC;

-- Q3:Identify vendors who account for more than 5% of total transaction spend. With 50,000 transactions, even a 5% share represents meaningful concentration.
-- Approach: Calculate spend once per vendor, calculate overall spend once, and cross join the single total to each vendor.
-- Reason: Separating the aggregations avoids repeatedly calculating the grand total and makes percentage thresholds explicit.
WITH vendor_spend AS (
    SELECT
        vendor.vendor_name,
        SUM(fact.amount) AS total_spend,
        COUNT(*) AS transaction_count
    FROM fact_transactions fact
        JOIN dim_vendor vendor
            ON fact.vendor_key = vendor.vendor_key
    GROUP BY vendor.vendor_name
),
total AS (
    SELECT SUM(total_spend) AS all_vendor_spend FROM vendor_spend
)
SELECT
    vendor_name,
    total_spend,
    transaction_count,
    ROUND(total_spend / NULLIF(all_vendor_spend, 0)*100.0, 2) AS percentage_of_total_spend,
    CASE
        WHEN total_spend > 0.10 * all_vendor_spend THEN 'HIGH'
        WHEN total_spend > 0.05 * all_vendor_spend THEN 'MEDIUM'
        ELSE 'NORMAL'
    END AS risk_flag
FROM vendor_spend
CROSS JOIN total
WHERE total_spend > 0.05 * all_vendor_spend
ORDER BY percentage_of_total_spend DESC;

-- Q4: Find all projects with pending or disputed transactions totalling more than 50,000 AED. These need finance team attention.
-- Approach: Filter unresolved transactions before grouping them by project, then retain groups above the value threshold.
-- Reason: Early filtering limits the aggregation to relevant records, while HAVING correctly filters aggregate results.
SELECT
    project.project_id,
    project.project_name,
    project.department,
    project.status AS project_status,
    COUNT(*) AS open_transaction_count,
    SUM(fact.amount) AS open_transaction_value
FROM fact_transactions fact
JOIN dim_project project
    ON fact.project_key = project.project_key
WHERE fact.payment_status IN ('Pending', 'Disputed')
GROUP BY project.project_id, project.project_name, project.department, project.status
HAVING SUM(fact.amount) > 50000
ORDER BY open_transaction_value DESC;

-- Q5: Show total transaction spend per month, per category, with a running total accumulating within each category over time. This view drives the Finance dashboard.
-- Approach: Aggregate facts to monthly category totals first, then apply LAG and a cumulative window over that smaller result.
-- Reason: Window functions operate on the required monthly grain; partitioning keeps each category's trend independent.
WITH monthly AS (
    SELECT
        strftime('%Y-%m', date.full_date) AS year_month,
        fact.category,
        SUM(fact.amount) AS monthly_spend
    FROM fact_transactions fact
    JOIN dim_date date USING (date_key)
    GROUP BY year_month, fact.category
),
with_previous AS (
    SELECT
        *,
        LAG(monthly_spend) OVER (PARTITION BY category ORDER BY year_month) AS previous_month_spend
    FROM monthly
)
SELECT
    year_month,
    category,
    monthly_spend,
    SUM(monthly_spend) OVER (
        PARTITION BY category ORDER BY year_month ROWS UNBOUNDED PRECEDING
    ) AS running_total,
    ROUND(
        (monthly_spend - previous_month_spend) / NULLIF(previous_month_spend, 0) * 100.0,
        2
    ) AS month_over_month_pct_change
FROM with_previous
ORDER BY category, year_month;

-- Q6: Using `dim_employee` SCD2 data, identify employees who received the largest single salary increase (in absolute AED terms).
-- Approach: Self-join employee versions where one half-open period ends exactly when the next version begins.
-- Reason: Matching adjacent SCD2 boundaries compares consecutive salaries without pairing unrelated historical versions.
SELECT
    current.employee_id,
    current.full_name,
    current.valid_from AS change_date,
    previous.salary AS previous_salary,
    current.salary AS new_salary,
    current.salary - previous.salary AS increase_amount,
    ROUND((current.salary - previous.salary) / NULLIF(previous.salary, 0) * 100.0, 2) AS increase_pct
FROM dim_employee current
JOIN dim_employee previous
  ON previous.employee_id = current.employee_id
 AND previous.valid_to = current.valid_from
WHERE current.salary > previous.salary
ORDER BY increase_amount DESC
LIMIT 20;
