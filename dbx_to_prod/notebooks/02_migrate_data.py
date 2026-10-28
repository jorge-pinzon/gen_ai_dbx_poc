# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Move the performance data (trial → prod)
# MAGIC Two modes, chosen with the **mode** widget:
# MAGIC 1. **export** – run in the **trial** workspace. Writes the 19 performance tables as Parquet
# MAGIC    into the `migration_staging` volume (structure and rows only; no views, no indexes).
# MAGIC 2. **import** – run in the **prod** workspace after copying the files with
# MAGIC    `scripts/copy_between_workspaces.sh`. Loads the rows, checks counts, then builds the
# MAGIC    materialized views from `sql/05_fast_views.sql`.
# MAGIC
# MAGIC With `COACHING360 = True` both modes also move every table of `coaching360demo` (directory,
# MAGIC Coaching360 app, BranchKPI, policy violations, ACE payout). Export saves each table's DDL next to
# MAGIC its rows, so import creates the tables with the trial columns and comments. Then run notebook 02b.
# MAGIC
# MAGIC Document PDFs are not handled here: copy the five volumes with the same script; notebook 03
# MAGIC parses them in prod. The chunk tables and indexes are rebuilt, not copied.
# MAGIC
# MAGIC Alternative without file copies: Delta Sharing (Databricks-to-Databricks) from trial to prod,
# MAGIC then `INSERT OVERWRITE <prod table> SELECT * FROM <shared catalog>.<table>` per table.

# COMMAND ----------

dbutils.widgets.dropdown("mode", "import", ["export", "import"])
MODE = dbutils.widgets.get("mode")

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

if MODE == "export":
    spark.sql(f"CREATE VOLUME IF NOT EXISTS {PERF_SCHEMA}.migration_staging")
    for table, expected in PERF_TABLES.items():
        df = spark.table(f"{PERF_SCHEMA}.{table}")
        df.write.mode("overwrite").parquet(f"{STAGING_VOLUME}{table}")
        print(f"exported {table:26} {df.count():5} rows (trial count when this kit was made: {expected})")
    print(f"\nNext: copy {STAGING_VOLUME} and the document volumes to prod with scripts/copy_between_workspaces.sh")

# COMMAND ----------

if MODE == "import":
    problems = []
    for table, expected in PERF_TABLES.items():
        target = f"{PERF_SCHEMA}.{table}"
        columns = spark.table(target).columns
        source = spark.read.parquet(f"{STAGING_VOLUME}{table}")
        missing = set(columns) - set(source.columns)
        if missing:
            problems.append(f"{table}: missing columns {sorted(missing)}")
            continue
        source.select(*columns).createOrReplaceTempView("migration_source")
        spark.sql(f"INSERT OVERWRITE {target} SELECT * FROM migration_source")
        loaded = spark.table(target).count()
        flag = "" if loaded == expected else f"  <-- trial had {expected}"
        print(f"loaded {table:26} {loaded:5} rows{flag}")
    if problems:
        raise RuntimeError("Import stopped: " + "; ".join(problems))

# COMMAND ----------

# MAGIC %md ## Coaching360 source tables (`coaching360demo`)
# MAGIC Trial row counts are not in this kit: export records them in `_manifest.json` and import compares against it.

# COMMAND ----------

import json, re

C360_STAGING = f"{STAGING_VOLUME}coaching360demo/"
if COACHING360 and MODE == "export":
    schema_name = C360_SOURCE_SCHEMA.split(".")[1]
    kinds = {r.table_name: r.table_type for r in spark.sql(
        f"SELECT table_name, table_type FROM {CATALOG}.information_schema.tables WHERE table_schema = '{schema_name}'").collect()}
    manifest = {}
    for table, kind in sorted(kinds.items()):
        if kind not in ("MANAGED", "EXTERNAL"):
            print(f"skipped {table} ({kind}): recreate it by hand"); continue
        df = spark.table(f"{C360_SOURCE_SCHEMA}.{table}")
        df.write.mode("overwrite").parquet(f"{C360_STAGING}{table}")
        ddl = spark.sql(f"SHOW CREATE TABLE {C360_SOURCE_SCHEMA}.{table}").first()[0]
        manifest[table] = {"rows": df.count(), "ddl": ddl}
        print(f"exported {table:70} {manifest[table]['rows']:7} rows")
    dbutils.fs.put(f"{C360_STAGING}_manifest.json", json.dumps(manifest, indent=1), overwrite=True)
    print(f"\n{len(manifest)} Coaching360 tables in {C360_STAGING}")

if COACHING360 and MODE == "import":
    manifest = json.loads(open(f"{C360_STAGING}_manifest.json").read())
    existing = {r.tableName for r in spark.sql(f"SHOW TABLES IN {C360_SOURCE_SCHEMA}").collect()}
    mismatched = []
    for table, item in manifest.items():
        target = f"{C360_SOURCE_SCHEMA}.{table}"
        if table not in existing:
            # The DDL names the trial catalog and schema; point it at this one.
            ddl = re.sub(r"^CREATE TABLE\s+\S+?\.\S+?\.", f"CREATE TABLE IF NOT EXISTS {C360_SOURCE_SCHEMA}.", item["ddl"].lstrip(), count=1)
            try:
                spark.sql(ddl)
            except Exception as error:
                # e.g. a table property prod does not allow: keep the columns, lose the comments.
                print(f"DDL failed for {table} ({str(error)[:120]}); creating it from the Parquet schema")
                spark.read.parquet(f"{C360_STAGING}{table}").limit(0).write.saveAsTable(target)
        columns = spark.table(target).columns
        spark.read.parquet(f"{C360_STAGING}{table}").select(*columns).createOrReplaceTempView("migration_source")
        spark.sql(f"INSERT OVERWRITE {target} SELECT * FROM migration_source")
        loaded = spark.table(target).count()
        if loaded != item["rows"]:
            mismatched.append(table)
        print(f"loaded {table:70} {loaded:7} rows{'' if loaded == item['rows'] else '  <-- trial had ' + str(item['rows'])}")
    if mismatched:
        raise RuntimeError(f"Coaching360 row counts differ from trial: {mismatched}")
    print(f"\nNext: notebook 02b builds the c360_* access layer on these {len(manifest)} tables.")

# COMMAND ----------

# MAGIC %md ## Materialized copies of the performance views
# MAGIC Built after the data is loaded. If serverless notebook compute rejects
# MAGIC `CREATE MATERIALIZED VIEW`, run `sql/05_fast_views.sql` in the SQL editor on the serverless warehouse.

# COMMAND ----------

if MODE == "import":
    run_sql_file("sql/05_fast_views.sql")
    for view in ("employee_profile", "employee_quarterly_performance", "employee_competency_summary",
                 "employee_goal_status", "employee_performance_history", "branch_quarterly_summary", "review_compliance"):
        live = spark.table(f"{PERF_SCHEMA}.app_vw_{view}")
        fast = spark.table(f"{PERF_SCHEMA}.app_fast_{view}")
        same = live.exceptAll(fast).count() == 0 and fast.exceptAll(live).count() == 0
        print(f"app_fast_{view:32} rows={fast.count():4}  identical to app_vw_{view}: {same}")
