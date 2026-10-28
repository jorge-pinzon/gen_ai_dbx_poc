# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Unity Catalog objects (prod)
# MAGIC Creates the schemas, volumes, tables, views and log table, then applies grants.
# MAGIC Run on **serverless** notebook compute in the prod workspace. Safe to re-run.
# MAGIC The materialized views (`sql/05_fast_views.sql`) are created later, in notebook 02, after data is loaded.
# MAGIC The Coaching360 access layer (`sql/coaching360`) is built by notebook 02b, after its data is loaded.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

steps = [
    ("sql/01_catalog_schemas_volumes.sql", "catalog, schemas, volumes"),
    ("sql/02_document_tables.sql", "document pipeline tables"),
    ("sql/03_performance_tables.sql", "performance tables"),
    ("sql/04_views.sql", "views and citation registries"),
    ("sql/06_app_tables.sql", "app log table"),
]
for path, label in steps:
    ran = run_sql_file(path)
    print(f"{label:32} {len(ran)} statements")

# COMMAND ----------

# MAGIC %md ## Grants for the app service principal

# COMMAND ----------

if APP_SP.startswith("<"):
    print("Skipped: set APP_SP in 00_config, then re-run this cell.")
else:
    ran = run_sql_file("sql/07_grants.sql", {"<app-sp-application-id>": APP_SP})
    print(f"grants: {len(ran)} statements")
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import WarehouseAccessControlRequest, WarehousePermissionLevel
    WorkspaceClient().warehouses.update_permissions(warehouse_id(), access_control_list=[
        WarehouseAccessControlRequest(service_principal_name=APP_SP, permission_level=WarehousePermissionLevel.CAN_USE)])
    print("warehouse: CAN_USE granted")

# COMMAND ----------

# MAGIC %md ## Check

# COMMAND ----------

display(spark.sql(f"""
  SELECT table_schema, table_type, COUNT(*) AS objects
  FROM {CATALOG}.information_schema.tables
  WHERE table_schema IN ('default', 'performance_test')
    AND (table_name RLIKE '_(parsed_documents|chunks)$' OR table_name IN ('flask_app_logs', 'app_citation_registry')
         OR table_schema = 'performance_test')
  GROUP BY 1, 2 ORDER BY 1, 2"""))
volumes = spark.sql(f"SHOW VOLUMES IN {DOCS_SCHEMA}").unionByName(spark.sql(f"SHOW VOLUMES IN {PERF_SCHEMA}"))
if COACHING360:
    volumes = volumes.unionByName(spark.sql(f"SHOW VOLUMES IN {C360_SOURCE_SCHEMA}"))
display(volumes)
