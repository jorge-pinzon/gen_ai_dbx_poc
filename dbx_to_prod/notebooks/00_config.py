# Databricks notebook source
# MAGIC %md
# MAGIC # 00 · Migration settings
# MAGIC Shared settings for every migration notebook (`%run ./00_config`). Edit the values in the
# MAGIC **Edit for prod** cell only. Names match the trial workspace, so the app code needs no change.
# MAGIC If prod uses another catalog, run `scripts/retarget.py` on the `dbx_to_prod` folder first.

# COMMAND ----------

# Edit for prod
CATALOG = "workspace"
DOCS_SCHEMA = f"{CATALOG}.default"
PERF_SCHEMA = f"{CATALOG}.performance_test"

# Application ID of the prod app's service principal (Settings > Identity and access).
APP_SP = "<app-sp-application-id>"

# Serverless SQL warehouse used by the app, Genie and the fast path.
WAREHOUSE_NAME = "Serverless Starter Warehouse"

# Vector search: one STANDARD endpoint serves all indexes (lowest query latency).
VS_ENDPOINT = "mariner-bot-endpoint"
EMBEDDING_MODEL = "databricks-qwen3-embedding-0-6b"

# Foundation models used outside Agent Bricks.
PERF_AGENT_LLM = "databricks-claude-haiku-4-5"        # perf_policy_citations_agent
FAST_PATH_MODEL = "databricks-gpt-5-4-mini"           # Flask performance fast path (non-prod only)
BENEFITS_AGENT_LLM = "databricks-claude-sonnet-4-5"   # legacy benefits agent (not recommended)

# Custom agent names in prod.
PERF_AGENT_MODEL = f"{PERF_SCHEMA}.perf_policy_citations_agent"
PERF_AGENT_ENDPOINT = "perf-policy-citations"

# Coaching360: False skips every Coaching360 step (data, views, BRD index, Genie spaces, guide, Supervisor tools).
COACHING360 = True
# Source tables (directory, Coaching360 app, BranchKPI, policy violations, ACE payout) and the BRD volume.
C360_SOURCE_SCHEMA = f"{CATALOG}.coaching360demo"

# COMMAND ----------

# Derived settings (normally no edits below)
import os

NOTEBOOK_PATH = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
# dbx_to_prod/ root inside the Git folder, readable as workspace files.
ROOT = "/Workspace" + os.path.dirname(os.path.dirname(NOTEBOOK_PATH))

DOMAINS = {
    "branch_operations": {
        "label": "Branch Operations (mariner-policy-assistant)",
        "volume": f"/Volumes/{CATALOG}/default/branch_operations_docs/",
        "chunks": f"{DOCS_SCHEMA}.branch_operations_chunks",
        "index": f"{DOCS_SCHEMA}.branch_ops_index",
        "expected_chunks": 29,
    },
    "employee_handbook": {
        "label": "Employee Handbook (mariner-handbook-assistant)",
        "volume": f"/Volumes/{CATALOG}/default/employee_handbook_docs/",
        "chunks": f"{DOCS_SCHEMA}.employee_handbook_chunks",
        "index": f"{DOCS_SCHEMA}.employee_handbook_new_index",
        "expected_chunks": 90,
    },
    "benefits": {
        "label": "Employee Benefits (mariner-benefits-assistant)",
        "volume": f"/Volumes/{CATALOG}/default/benefits_docs/",
        "chunks": f"{DOCS_SCHEMA}.benefits_chunks",
        "index": f"{DOCS_SCHEMA}.benefits_new_index",
        "expected_chunks": 6,
    },
}
if COACHING360:
    DOMAINS["coaching360"] = {
        "label": "Coaching360 Guide (mariner-coaching360-guide)",
        "volume": f"/Volumes/{CATALOG}/coaching360demo/coaching360_docs/",
        "chunks": f"{DOCS_SCHEMA}.coaching360_chunks",
        "index": f"{DOCS_SCHEMA}.coaching360_index",
        "expected_chunks": None,  # not recorded in trial; checks only require rows
    }
PERF_VOLUME = f"/Volumes/{CATALOG}/performance_test/data/"
STAGING_VOLUME = f"/Volumes/{CATALOG}/performance_test/migration_staging/"

# Delta Sync indexes (TRIGGERED = sync on demand, no always-on pipeline cost).
INDEXES = [
    {"name": f"{DOCS_SCHEMA}.branch_ops_index", "source": f"{DOCS_SCHEMA}.branch_operations_chunks",
     "primary_key": "chunk_id", "embedding_col": "embedding_text", "expected_rows": 29},
    {"name": f"{DOCS_SCHEMA}.employee_handbook_new_index", "source": f"{DOCS_SCHEMA}.employee_handbook_chunks",
     "primary_key": "chunk_id", "embedding_col": "embedding_text", "expected_rows": 90},
    {"name": f"{DOCS_SCHEMA}.benefits_new_index", "source": f"{DOCS_SCHEMA}.benefits_chunks",
     "primary_key": "chunk_id", "embedding_col": "embedding_text", "expected_rows": 6},
    {"name": f"{PERF_SCHEMA}.performance_index", "source": f"{PERF_SCHEMA}.app_policy_chunks",
     "primary_key": "chunk_id", "embedding_col": "chunk_to_embed", "expected_rows": 9},
    {"name": f"{PERF_SCHEMA}.perf_policy_retrieval_index", "source": f"{PERF_SCHEMA}.perf_policy_retrieval",
     "primary_key": "retrieval_id", "embedding_col": "chunk_text", "expected_rows": 9},
]
if COACHING360:
    INDEXES.append({"name": f"{DOCS_SCHEMA}.coaching360_index", "source": f"{DOCS_SCHEMA}.coaching360_chunks",
                    "primary_key": "chunk_id", "embedding_col": "embedding_text", "expected_rows": None})

# Performance source data copied from the trial account, with trial row counts.
PERF_TABLES = {
    "region": 2, "branch": 6, "job_role": 3, "employee": 23, "employee_assignment": 23,
    "performance_cycle": 7, "performance_target": 147, "metric_snapshot": 105, "loan_transaction": 953,
    "employee_review": 105, "review_meeting": 105, "employee_acknowledgment": 105, "competency": 4,
    "competency_rating": 420, "performance_goal": 60, "goal_progress": 210, "career_aspiration": 30,
    "meeting_note": 420, "app_evaluation_dataset": 30,
}

# Coaching360 access layer, in run order for a new workspace (sql/coaching360, generated by
# coaching360/build_sql.py). 01_security already holds the materialized scope tables, so the
# trial-only upgrade scripts 01b and 01c are not needed. Run through the SQL warehouse (notebook 02b).
C360_SQL_FILES = ["01_security.sql", "01d_prepared.sql", "02_employee_views.sql", "03_branch_views.sql",
                  "04_district_views.sql", "06_genie_functions.sql"]
C360_SCHEMAS = ["c360_security", "c360_prepared", "c360_employee", "c360_branch", "c360_district"]
# Account groups for real users (sql/coaching360/05_grants.sql); create them before granting.
C360_GROUPS = ["c360_employees", "c360_branch_managers", "c360_district_leaders"]


def sql_statements(text):
    """Split a .sql file into statements. A ';' ends a statement at the end of a line, even when a
    trailing -- comment follows it; comment-only chunks are dropped."""
    import re
    for chunk in re.split(r";[ \t]*(?:--[^\n]*)?\n", text + "\n"):
        body = "\n".join(line for line in chunk.splitlines() if not line.lstrip().startswith("--")).strip()
        if body:
            yield body


def run_sql_file(relative_path, replacements=None):
    """Run every statement of a .sql file from dbx_to_prod/sql; returns the statements run."""
    text = open(f"{ROOT}/{relative_path}").read()
    for old, new in (replacements or {}).items():
        text = text.replace(old, new)
    statements = list(sql_statements(text))
    for statement in statements:
        spark.sql(statement)
    return statements


def warehouse_id(name=WAREHOUSE_NAME):
    from databricks.sdk import WorkspaceClient
    matches = [w.id for w in WorkspaceClient().warehouses.list() if w.name == name]
    if not matches:
        raise ValueError(f"SQL warehouse {name!r} not found; set WAREHOUSE_NAME in 00_config")
    return matches[0]


print(f"dbx_to_prod root: {ROOT}\ncatalog: {CATALOG}  docs: {DOCS_SCHEMA}  performance: {PERF_SCHEMA}")
if APP_SP.startswith("<"):
    print("NOTE: APP_SP is not set yet; grant and permission steps will be skipped.")
