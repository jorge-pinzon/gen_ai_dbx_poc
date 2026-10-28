# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Validate prod
# MAGIC Read-only checks that prod matches the trial setup and uses the cost and speed settings from the guide.
# MAGIC Fill the endpoint names printed by notebook 06, then **Run all**. Every check prints PASS or FAIL.

# COMMAND ----------

# MAGIC %pip install -U databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

SUPERVISOR_ENDPOINT = "<from notebook 06>"
KA_ENDPOINTS = {"policy": "<ka-...-endpoint>", "handbook": "<ka-...-endpoint>", "benefits": "<ka-...-endpoint>"}
if COACHING360:
    KA_ENDPOINTS["coaching360"] = "<ka-...-endpoint>"  # mariner-coaching360-guide

# COMMAND ----------

import json, time
from databricks.sdk import WorkspaceClient

w = WorkspaceClient()
results = []


def check(name, ok, detail=""):
    results.append((name, bool(ok)))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")

# COMMAND ----------

# MAGIC %md ## Data, views and registries

# COMMAND ----------

for table, expected in PERF_TABLES.items():
    rows = spark.table(f"{PERF_SCHEMA}.{table}").count()
    check(f"rows {table}", rows == expected, f"{rows} (trial {expected})")
for view in ("employee_profile", "employee_quarterly_performance", "employee_competency_summary", "employee_goal_status",
             "employee_performance_history", "branch_quarterly_summary", "review_compliance"):
    live, fast = spark.table(f"{PERF_SCHEMA}.app_vw_{view}"), spark.table(f"{PERF_SCHEMA}.app_fast_{view}")
    check(f"app_fast_{view} = app_vw_{view}", live.exceptAll(fast).count() == 0 and fast.exceptAll(live).count() == 0)
for domain, cfg in DOMAINS.items():
    rows = spark.table(cfg["chunks"]).count()
    check(f"chunks {domain}", rows > 0, f"{rows} (trial {cfg['expected_chunks']})")
registry = spark.sql(f"SELECT COUNT(*) FROM {DOCS_SCHEMA}.app_citation_registry").first()[0]
retrieval = spark.table(f"{PERF_SCHEMA}.perf_policy_retrieval").count()
check("citation registry has passages", registry > 0, str(registry))
check("perf_policy_retrieval approved passages", retrieval > 0, str(retrieval))
log_columns = spark.table(f"{DOCS_SCHEMA}.flask_app_logs").columns
check("flask_app_logs has stage_timings_json", "stage_timings_json" in log_columns)

# COMMAND ----------

# MAGIC %md ## Coaching360 data and access layer

# COMMAND ----------

if COACHING360:
    sources = spark.sql(f"SHOW TABLES IN {C360_SOURCE_SCHEMA}").count()
    check("coaching360demo source tables", sources > 0, str(sources))
    for schema in C360_SCHEMAS:
        objects = spark.sql(f"SELECT COUNT(*) FROM {CATALOG}.information_schema.tables WHERE table_schema = '{schema}'").first()[0]
        functions = spark.sql(f"SELECT COUNT(*) FROM {CATALOG}.information_schema.routines WHERE routine_schema = '{schema}'").first()[0]
        check(f"{schema} objects", objects > 0, f"{objects} tables/views, {functions} functions")
    status = spark.sql(f"SELECT * FROM {CATALOG}.c360_prepared.data_status").collect()
    check("c360_prepared.data_status has the latest KPI month", len(status) == 1 and status[0]["LatestKpiMonth"] is not None,
          str(status[0].asDict() if status else None))
    levels = {r["level"]: r["n"] for r in spark.sql(f"SELECT level, COUNT(*) AS n FROM {CATALOG}.c360_security.user_level GROUP BY 1").collect()}
    check("directory people at every level", all(levels.get(l) for l in ("employee", "branch", "district")), str(levels))

# COMMAND ----------

# MAGIC %md ## Vector search

# COMMAND ----------

endpoint = w.vector_search_endpoints.get_endpoint(VS_ENDPOINT)
check("vector search endpoint is STANDARD", str(endpoint.endpoint_type).endswith("STANDARD"), str(endpoint.endpoint_type))
for spec in INDEXES:
    index = w.vector_search_indexes.get_index(spec["name"])
    rows = spark.table(spec["source"]).count()
    pipeline = index.delta_sync_index_spec.pipeline_type
    check(f"index {spec['name'].split('.')[-1]}", index.status.ready and index.status.indexed_row_count == rows,
          f"{index.status.indexed_row_count}/{rows} rows, {pipeline}")
    check(f"index {spec['name'].split('.')[-1]} is TRIGGERED", str(pipeline).endswith("TRIGGERED"))

# COMMAND ----------

# MAGIC %md ## Serving endpoints and agents

# COMMAND ----------


def ask(endpoint_name, question):
    started = time.time()
    reply = w.api_client.do("POST", f"/serving-endpoints/{endpoint_name}/invocations",
                            body={"input": [{"role": "user", "content": question}]})
    text = "".join(c.get("text", "") for item in reply.get("output", []) if item.get("type") == "message"
                   for c in item.get("content", []) if isinstance(c, dict))
    return text, time.time() - started


custom = w.serving_endpoints.get(PERF_AGENT_ENDPOINT)
check("perf-policy-citations scales to zero", all(e.scale_to_zero_enabled for e in custom.config.served_entities))
text, seconds = ask(PERF_AGENT_ENDPOINT, "How often must managers hold performance review meetings?")
payload = json.loads(text)
check("perf-policy-citations returns cited JSON", payload.get("citations"), f"{seconds:.1f}s, {len(payload.get('citations', []))} citations")

questions = {"policy": "What does the policy say about paid loan file retention?",
             "handbook": "What does the handbook say about jury duty leave?",
             "benefits": "What PPO and HMO medical plans are available?",
             "coaching360": "What is a Success Plan in Coaching360?"}
for key, endpoint_name in KA_ENDPOINTS.items():
    if endpoint_name.startswith("<"):
        check(f"knowledge assistant {key}", False, "set KA_ENDPOINTS above"); continue
    text, seconds = ask(endpoint_name, questions[key])
    check(f"knowledge assistant {key} answers with a Source line", "Source:" in text, f"{seconds:.1f}s")

if not SUPERVISOR_ENDPOINT.startswith("<"):
    text, seconds = ask(SUPERVISOR_ENDPOINT, "What is the dress code at Mariner?")
    check("supervisor routes and answers", len(text) > 50, f"{seconds:.1f}s")
else:
    check("supervisor routes and answers", False, "set SUPERVISOR_ENDPOINT above")

if COACHING360:
    genie_titles = {s.get("title") for s in w.api_client.do("GET", "/api/2.0/genie/spaces").get("spaces", [])}
    for item in json.load(open(f"{ROOT}/agents/agent_bricks/coaching360/genie_spaces.json"))["spaces"]:
        check(f"Genie space {item['title']}", item["title"] in genie_titles)
    sup_name = json.load(open(f"{ROOT}/agents/agent_bricks/supervisor/supervisor.json"))["name"]
    supervisor = next((s for s in w.supervisor_agents.list_supervisor_agents() if s.display_name == sup_name), None)
    have = {t.tool_id for t in w.supervisor_agents.list_tools(parent=supervisor.name)} if supervisor else set()
    for tool_id in ("coaching360_employee_data", "coaching360_branch_data", "coaching360_district_data", "coaching360_guide"):
        check(f"supervisor tool {tool_id}", tool_id in have)
    check("supervisor instructions have the Coaching360 section",
          supervisor and "COACHING360 (application-directed only)" in (w.supervisor_agents.get_supervisor_agent(supervisor.name).instructions or ""))

# COMMAND ----------

# MAGIC %md ## Cost and speed settings

# COMMAND ----------

wh = w.warehouses.get(warehouse_id())
check("warehouse is serverless", wh.enable_serverless_compute)
check("warehouse auto-stop <= 30 min", (wh.auto_stop_mins or 0) <= 30, f"{wh.auto_stop_mins} min")
check("warehouse is Small or smaller", wh.cluster_size in ("2X-Small", "X-Small", "Small"), wh.cluster_size)
for name in [n for n in [SUPERVISOR_ENDPOINT, *KA_ENDPOINTS.values()] if not n.startswith("<")] + [PERF_AGENT_ENDPOINT]:
    served = w.serving_endpoints.get(name).config.served_entities or []
    custom_entities = [e for e in served if e.entity_name]
    if custom_entities:
        check(f"{name} scales to zero", all(e.scale_to_zero_enabled for e in custom_entities))
mv = spark.sql(f"SHOW TBLPROPERTIES {PERF_SCHEMA}.app_fast_employee_profile").collect()
check("materialized views exist", len(mv) > 0)

# COMMAND ----------

failed = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("Failed:", *failed, sep="\n  ")
