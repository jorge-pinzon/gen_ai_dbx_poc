# Databricks notebook source
# MAGIC %md
# MAGIC # 02b · Coaching360 access layer (prod)
# MAGIC Builds the five `c360_*` schemas on the `coaching360demo` tables loaded by notebook 02:
# MAGIC
# MAGIC | Schema | What |
# MAGIC |---|---|
# MAGIC | `c360_security` | Login → directory person (`user_map`), level, branch scope, `me()`, `my_level()` (admins only) |
# MAGIC | `c360_prepared` | Daily pre-joined sources: KPIs and goals, DPR metrics, coaching records, `data_status` |
# MAGIC | `c360_employee` / `c360_branch` / `c360_district` | Level views, overview tables and trusted functions read by the three Genie spaces |
# MAGIC
# MAGIC Statements run on the **SQL warehouse** (materialized views and SQL functions need it), as you:
# MAGIC you become the owner of the schemas. Safe to re-run. Source of the SQL: `coaching360/build_sql.py`,
# MAGIC copied to `sql/coaching360`. The materialized views refresh daily (`SCHEDULE EVERY 1 DAY`).

# COMMAND ----------

# MAGIC %pip install -U databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import re, time
from databricks.sdk import WorkspaceClient

assert COACHING360, "COACHING360 is False in 00_config; nothing to do"
w = WorkspaceClient()
WAREHOUSE_ID = warehouse_id()


def run_on_warehouse(statement):
    result = w.statement_execution.execute_statement(statement=statement, warehouse_id=WAREHOUSE_ID, wait_timeout="50s")
    while result.status.state.value in ("PENDING", "RUNNING"):
        time.sleep(2)
        result = w.statement_execution.get_statement(result.statement_id)
    if result.status.state.value != "SUCCEEDED":
        raise RuntimeError(f"{' '.join(statement.split()[:8])}: {result.status.error.message[:400]}")
    return result.result.data_array if result.result else []


def run_c360_file(name, replacements=None):
    text = open(f"{ROOT}/sql/coaching360/{name}").read()
    for old, new in (replacements or {}).items():
        text = text.replace(old, new)
    statements = list(sql_statements(text))
    started = time.time()
    for statement in statements:
        run_on_warehouse(statement)
    print(f"{name:28} {len(statements):3} statements {time.time() - started:6.0f}s")
    return statements

# COMMAND ----------

# MAGIC %md ## 1 · Schemas, scope tables, prepared tables, level views and functions

# COMMAND ----------

created = {}
for name in C360_SQL_FILES:
    for statement in run_c360_file(name):
        match = re.match(r"CREATE\s+(?:OR\s+REPLACE\s+)?(MATERIALIZED\s+VIEW|VIEW|TABLE|FUNCTION)\s+(?:IF\s+NOT\s+EXISTS\s+)?(\S+?)(?:\(|\s)",
                         statement, re.IGNORECASE)
        if match:
            created[match.group(2)] = match.group(1).upper()

# COMMAND ----------

# MAGIC %md ## 2 · Grants
# MAGIC `05b` gives the app's service principal what the demo chat needs (level views and functions,
# MAGIC `user_map`, the directory tables for the name lookup). `05` is for real users through account groups;
# MAGIC set `GRANT_GROUPS = True` once the three groups exist in the account.

# COMMAND ----------

GRANT_GROUPS = False

if APP_SP.startswith("<"):
    print("Skipped 05b: set APP_SP in 00_config, then re-run this cell.")
else:
    run_c360_file("05b_demo_grants_app.sql", {"<app-sp-application-id>": APP_SP})
if GRANT_GROUPS:
    run_c360_file("05_grants.sql")
else:
    print(f"Skipped 05_grants.sql (groups {', '.join(C360_GROUPS)})")

# COMMAND ----------

# MAGIC %md ## 3 · Check

# COMMAND ----------

problems = []
for full_name, kind in sorted(created.items()):
    catalog_name, schema_name, object_name = full_name.split(".")
    view = "routines" if kind == "FUNCTION" else "tables"
    column = "routine" if kind == "FUNCTION" else "table"
    found = spark.sql(f"SELECT 1 FROM {catalog_name}.information_schema.{view} WHERE {column}_schema = '{schema_name}' "
                      f"AND {column}_name = '{object_name}'").count()
    if not found:
        problems.append(full_name)
by_schema = {}
for full_name in created:
    by_schema[full_name.split(".")[1]] = by_schema.get(full_name.split(".")[1], 0) + 1
print("objects per schema:", by_schema)
print("missing:", problems or "none")

status = run_on_warehouse(f"SELECT CAST(LatestKpiMonth AS STRING), CAST(AsOfDate AS STRING) FROM {CATALOG}.c360_prepared.data_status")
print("data_status (latest KPI month, as-of date):", status)
levels = run_on_warehouse(f"SELECT level, COUNT(*) FROM {CATALOG}.c360_security.user_level GROUP BY 1 ORDER BY 1")
print("people per level:", levels)
if problems or not status:
    raise RuntimeError("Coaching360 access layer is incomplete")
print("\nNext: notebook 03 (parses the BRD with the other documents).")
