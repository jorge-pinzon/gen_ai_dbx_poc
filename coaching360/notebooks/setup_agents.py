# Databricks notebook source
# MAGIC %md
# MAGIC # Coaching360 agents: one-time setup (trial workspace)
# MAGIC Run as yourself from the repo's Git folder, on serverless compute. Attaches everything to the
# MAGIC **existing** infrastructure:
# MAGIC 1. BRD pipeline: parse `coaching360_docs/Coaching_360_BRD_Version2.3.pdf` into `workspace.default.coaching360_chunks`.
# MAGIC 2. Vector index `workspace.default.coaching360_index` on the existing endpoint **mariner-bot-endpoint**.
# MAGIC 3. Knowledge Assistant **mariner-coaching360-guide** on that index.
# MAGIC 4. Three Genie spaces (employee, branch, district) on the existing **Serverless Starter Warehouse**.
# MAGIC 5. Four new tools on the existing Supervisor **mas-53dbd2d7-endpoint**, plus a Coaching360 section in its instructions.
# MAGIC 6. Grants for the app's service principal.
# MAGIC
# MAGIC Every step reuses what already exists, so re-running is safe. Prerequisite: `sql/01`-`04` and `05b` have run.

# COMMAND ----------

# MAGIC %pip install -U databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

import json, os, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ServingEndpointAccessControlRequest, ServingEndpointPermissionLevel
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn, PipelineType, VectorIndexType)

w = WorkspaceClient()
NOTEBOOK = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
AGENTS = "/Workspace" + os.path.dirname(os.path.dirname(NOTEBOOK)) + "/agents"
APP_SP = "9480056c-9708-40af-92da-c35b15cf61fa"
guide = json.load(open(f"{AGENTS}/guide_knowledge_assistant.json"))
tools_spec = json.load(open(f"{AGENTS}/supervisor_tools.json"))
print("agents folder:", AGENTS)

# COMMAND ----------

# MAGIC %md ## 1 · BRD pipeline (same SQL as the upload tool's Coaching360 domain)

# COMMAND ----------

spark.sql("CREATE TABLE IF NOT EXISTS workspace.default.coaching360_parsed_documents LIKE workspace.default.branch_operations_parsed_documents")
spark.sql("CREATE TABLE IF NOT EXISTS workspace.default.coaching360_chunks LIKE workspace.default.branch_operations_chunks")
spark.sql("""ALTER TABLE workspace.default.coaching360_chunks SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true',
             'delta.deletedFileRetentionDuration' = 'interval 90 days', 'delta.logRetentionDuration' = 'interval 90 days')""")
for label, statement in json.load(open(f"{AGENTS}/brd_pipeline_steps.json")):
    started = time.time()
    spark.sql(statement)
    print(f"{label:35} {time.time() - started:5.0f}s")
display(spark.sql("SELECT document_title, COUNT(*) AS chunks, MIN(page_start) AS first_page, MAX(page_start) AS last_page "
                  "FROM workspace.default.coaching360_chunks GROUP BY 1"))

# COMMAND ----------

# MAGIC %md ## 2 · Vector index on the existing endpoint

# COMMAND ----------

existing = {i.name for i in w.vector_search_indexes.list_indexes(endpoint_name=guide["vector_search_endpoint"])}
if guide["knowledge_source"]["index"] in existing:
    # A sync is refused while the previous one is still running; wait for it, then sync.
    for attempt in range(40):
        try:
            w.vector_search_indexes.sync_index(guide["knowledge_source"]["index"])
            print("sync requested")
            break
        except Exception as error:
            if "not ready to sync" not in str(error):
                raise
            time.sleep(30)
    else:
        raise TimeoutError("The index sync pipeline stayed busy for 20 minutes")
else:
    w.vector_search_indexes.create_index(
        name=guide["knowledge_source"]["index"], endpoint_name=guide["vector_search_endpoint"], primary_key="chunk_id",
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=guide["chunks_table"], pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[EmbeddingSourceColumn(name="embedding_text", embedding_model_endpoint_name=guide["embedding_model"])]))
    print("index created")
rows = spark.table(guide["chunks_table"]).count()
for _ in range(90):
    status = w.vector_search_indexes.get_index(guide["knowledge_source"]["index"]).status
    if status.ready and status.indexed_row_count == rows:
        break
    time.sleep(20)
print(f"index ready={status.ready} rows={status.indexed_row_count}/{rows}")

# COMMAND ----------

# MAGIC %md ## 3 · Knowledge Assistant (Coaching360 Guide)

# COMMAND ----------

from databricks.sdk.service.knowledgeassistants import IndexSpec, KnowledgeAssistant, KnowledgeSource

kas = {ka.display_name: ka for ka in w.knowledge_assistants.list_knowledge_assistants()}
ka = kas.get(guide["name"])
if ka is None:
    ka = w.knowledge_assistants.create_knowledge_assistant(KnowledgeAssistant(
        display_name=guide["name"], description=guide["description"],
        instructions=open(f"{AGENTS}/{guide['instructions_file']}").read()))
    src = guide["knowledge_source"]
    w.knowledge_assistants.create_knowledge_source(parent=ka.name, knowledge_source=KnowledgeSource(
        display_name=src["name"], description=src["description"], source_type="index",
        index=IndexSpec(index_name=src["index"], text_col=src["text_col"], doc_uri_col=src["doc_uri_col"])))
    print("created", guide["name"])
for _ in range(90):
    ka = w.knowledge_assistants.get_knowledge_assistant(ka.name)
    if ka.endpoint_name and str(w.serving_endpoints.get(ka.endpoint_name).state.ready).endswith("READY"):
        break
    time.sleep(20)
print("Knowledge Assistant endpoint:", ka.endpoint_name)

# COMMAND ----------

# MAGIC %md ## 4 · Genie spaces (one per level) on the existing warehouse

# COMMAND ----------

me = w.current_user.me().user_name
spaces = {s["title"]: s["space_id"] for s in w.api_client.do("GET", "/api/2.0/genie/spaces").get("spaces", [])}
GENIE = {}
for level in ("employee", "branch", "district"):
    meta = json.load(open(f"{AGENTS}/genie_{level}_meta.json"))
    space = json.load(open(f"{AGENTS}/{meta['serialized_space_file']}"))
    if meta["title"] in spaces:
        GENIE[level] = spaces[meta["title"]]
        w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{GENIE[level]}", body={"serialized_space": json.dumps(space)})
        print(f"updated {meta['title']}")
    else:
        GENIE[level] = w.api_client.do("POST", "/api/2.0/genie/spaces", body={
            "warehouse_id": meta["warehouse_id"], "title": meta["title"], "description": meta["description"],
            "parent_path": f"/Workspace/Users/{me}", "serialized_space": json.dumps(space)})["space_id"]
        print(f"created {meta['title']}")
    w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{GENIE[level]}", body={"access_control_list": [
        {"service_principal_name": APP_SP, "permission_level": "CAN_RUN"}]})
print(GENIE)

# COMMAND ----------

# MAGIC %md ## 5 · Add the tools to the existing Supervisor (mas-53dbd2d7-endpoint)

# COMMAND ----------

from databricks.sdk.service.supervisoragents import GenieSpace, SupervisorAgent, Tool
from databricks.sdk.service.supervisoragents import KnowledgeAssistant as KnowledgeAssistantTool

supervisor = next(s for s in w.supervisor_agents.list_supervisor_agents()
                  if s.endpoint_name == tools_spec["supervisor_endpoint"])
print("supervisor:", supervisor.display_name, supervisor.name)
have = {t.tool_id for t in w.supervisor_agents.list_tools(parent=supervisor.name)}
targets = {"coaching360_employee_data": ("genie", GENIE["employee"]), "coaching360_branch_data": ("genie", GENIE["branch"]),
           "coaching360_district_data": ("genie", GENIE["district"]), "coaching360_guide": ("ka", ka.id)}
for tool in tools_spec["tools"]:
    if tool["tool_id"] in have:
        print("exists ", tool["tool_id"]); continue
    kind, target = targets[tool["tool_id"]]
    spec = (Tool(tool_type="genie_space", description=tool["description"], genie_space=GenieSpace(id=target)) if kind == "genie"
            else Tool(tool_type="knowledge_assistant", description=tool["description"],
                      knowledge_assistant=KnowledgeAssistantTool(knowledge_assistant_id=target)))
    try:
        w.supervisor_agents.create_tool(parent=supervisor.name, tool=spec, tool_id=tool["tool_id"])
        print("added  ", tool["tool_id"])
    except Exception as error:
        print(f"ADD IN THE UI: Supervisor > Add agent > {'Genie space' if kind == 'genie' else 'Knowledge Assistant'} "
              f"{target}, name {tool['tool_id']}, description:\n  {tool['description']}\n  ({str(error)[:160]})")

# COMMAND ----------

# MAGIC %md ## 6 · Coaching360 section in the Supervisor instructions
# MAGIC The current instructions are printed first as a backup. The section is appended once.

# COMMAND ----------

current = w.supervisor_agents.get_supervisor_agent(supervisor.name)
addition = open(f"{AGENTS}/supervisor_instructions_addition.md").read()
print("BACKUP of the current instructions:\n", current.instructions)
if "COACHING360 (application-directed only)" in (current.instructions or ""):
    print("\nCoaching360 section already present")
else:
    try:
        from databricks.sdk.common.types.fieldmask import FieldMask
        mask = FieldMask(field_mask=["instructions"])
    except ImportError:
        mask = "instructions"
    try:
        w.supervisor_agents.update_supervisor_agent(
            name=supervisor.name, update_mask=mask,
            supervisor_agent=SupervisorAgent(display_name=current.display_name, instructions=current.instructions.rstrip() + "\n\n" + addition))
        print("\nCoaching360 section added")
    except Exception as error:
        print(f"\nPASTE IN THE UI at the end of the Supervisor instructions:\n\n{addition}\n({str(error)[:160]})")

# COMMAND ----------

# MAGIC %md ## 7 · Grants for the app's service principal

# COMMAND ----------

spark.sql(f"GRANT SELECT ON TABLE workspace.default.coaching360_chunks TO `{APP_SP}`")
endpoint = w.serving_endpoints.get(ka.endpoint_name)
w.serving_endpoints.update_permissions(endpoint.id, access_control_list=[ServingEndpointAccessControlRequest(
    service_principal_name=APP_SP, permission_level=ServingEndpointPermissionLevel.CAN_QUERY)])
print("app service principal: SELECT on coaching360_chunks, CAN_QUERY on", ka.endpoint_name, ", CAN_RUN on the 3 Genie spaces")
print("\nNext: set COACHING360_ENABLED=true in the app settings and restart the app.")
