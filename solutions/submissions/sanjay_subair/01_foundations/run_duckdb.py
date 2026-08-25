import duckdb

connection = duckdb.connect("warehouse.duckdb")

with open(
    "solutions/submissions/sanjay_subair/01_foundations/data_model.sql",
    encoding="utf-8",
) as sql_file:
    connection.execute(sql_file.read())

result = connection.execute("""
    -- SELECT employee_id, COUNT(*) AS version_count
    -- FROM dim_employee
    -- GROUP BY employee_id
    -- ORDER BY version_count DESC
    -- LIMIT 10
    SHOW TABLES
""").fetchdf()

print(result)
connection.close()