# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · Agent Bricks: Knowledge Assistants, Genie space and Supervisor (prod)
# MAGIC Recreates the trial Agent Bricks agents from `agents/agent_bricks/`:
# MAGIC 1. Three **Knowledge Assistants** (policy, handbook, benefits) on the vector indexes from notebook 04;
# MAGIC    the performance assistant is optional (`CREATE_PERFORMANCE_KA`).
# MAGIC 2. The **Genie space** `mariner-performance-data-assitant` on the `app_fast_*` copies.
# MAGIC 3. The **Supervisor** with its tools: policy, handbook and benefits assistants, Genie,
# MAGIC    `system.ai.python_exec` and the `perf-policy-citations` endpoint from notebook 05.
# MAGIC 4. With `COACHING360 = True`: the **mariner-coaching360-guide** assistant (BRD), three Coaching360
# MAGIC    **Genie spaces** (one per level, on the `c360_*` schemas from notebook 02b) and their four
# MAGIC    Supervisor tools, plus the Coaching360 section of the Supervisor instructions.
# MAGIC
# MAGIC Uses the Databricks SDK `knowledge_assistants` / `supervisor_agents` services. Each step is
# MAGIC idempotent (existing objects are reused by name). If a call fails, the printed values are the
# MAGIC ones to enter in the Agent Bricks UI (see the HTML guide, section 6).

# COMMAND ----------

# MAGIC %pip install -U databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import json, time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.knowledgeassistants import IndexSpec, KnowledgeAssistant, KnowledgeSource
from databricks.sdk.service.serving import ServingEndpointAccessControlRequest, ServingEndpointPermissionLevel

w = WorkspaceClient()
AB = f"{ROOT}/agents/agent_bricks"


def grant_query(endpoint_name):
    if APP_SP.startswith("<"):
        return
    endpoint = w.serving_endpoints.get(endpoint_name)
    w.serving_endpoints.update_permissions(endpoint.id, access_control_list=[ServingEndpointAccessControlRequest(
        service_principal_name=APP_SP, permission_level=ServingEndpointPermissionLevel.CAN_QUERY)])


def wait_for_endpoint(get, label, minutes=30):
    deadline = time.time() + minutes * 60
    while time.time() < deadline:
        obj = get()
        if getattr(obj, "endpoint_name", None):
            try:
                if str(w.serving_endpoints.get(obj.endpoint_name).state.ready).endswith("READY"):
                    return obj
            except Exception:
                pass
        time.sleep(20)
    raise TimeoutError(f"{label}: endpoint not ready after {minutes} minutes")

# COMMAND ----------

# MAGIC %md ## 1 · Knowledge Assistants

# COMMAND ----------

# mariner-performance-assistant is not a Supervisor tool and the app does not call it (/performance uses
# perf-policy-citations). Leave it off unless something else needs it: every assistant is an endpoint.
CREATE_PERFORMANCE_KA = False

existing = {ka.display_name: ka for ka in w.knowledge_assistants.list_knowledge_assistants()}
KAS = {}
for key in ("policy", "handbook", "benefits") + (("performance",) if CREATE_PERFORMANCE_KA else ()) + (("coaching360",) if COACHING360 else ()):
    spec = json.load(open(f"{AB}/knowledge_assistants/{key}.json"))
    instructions = open(f"{AB}/knowledge_assistants/{spec['instructions_file']}").read()
    ka = existing.get(spec["name"])
    if ka is None:
        ka = w.knowledge_assistants.create_knowledge_assistant(KnowledgeAssistant(
            display_name=spec["name"], description=spec["description"], instructions=instructions))
        src = spec["knowledge_source"]
        w.knowledge_assistants.create_knowledge_source(parent=ka.name, knowledge_source=KnowledgeSource(
            display_name=src["name"], description=src["description"] or "Managed Vector Index with Delta Sync",
            source_type="index",
            index=IndexSpec(index_name=src["index"], text_col=src["text_col"], doc_uri_col=src["doc_uri_col"])))
        print(f"created  {spec['name']} on {src['index']}")
    else:
        print(f"exists   {spec['name']}")
    KAS[key] = wait_for_endpoint(lambda n=ka.name: w.knowledge_assistants.get_knowledge_assistant(n), spec["name"])
    grant_query(KAS[key].endpoint_name)
    print(f"         endpoint {KAS[key].endpoint_name} ready")

# COMMAND ----------

# MAGIC %md ## 2 · Genie space (reads the app_fast_* copies)

# COMMAND ----------

genie = json.load(open(f"{AB}/genie/genie_space.json"))
space = json.load(open(f"{AB}/genie/{genie['serialized_space_file']}"))
spaces = w.api_client.do("GET", "/api/2.0/genie/spaces").get("spaces", [])
match = [s for s in spaces if s.get("title") == genie["title"]]
if match:
    GENIE_ID = match[0]["space_id"]
    print("exists  ", genie["title"], GENIE_ID)
else:
    me = w.current_user.me().user_name
    created = w.api_client.do("POST", "/api/2.0/genie/spaces", body={
        "warehouse_id": warehouse_id(), "title": genie["title"], "description": genie["description"],
        "parent_path": f"/Workspace/Users/{me}", "serialized_space": json.dumps(space)})
    GENIE_ID = created["space_id"]
    print("created ", genie["title"], GENIE_ID)
if not APP_SP.startswith("<"):
    w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{GENIE_ID}", body={"access_control_list": [
        {"service_principal_name": APP_SP, "permission_level": "CAN_RUN"}]})
check = json.loads(w.api_client.do("GET", f"/api/2.0/genie/spaces/{GENIE_ID}",
                                   query={"include_serialized_space": "true"})["serialized_space"])
print("tables:", [t["identifier"].split(".")[-1] for t in check["data_sources"]["tables"]],
      "| examples:", len(check["instructions"].get("example_question_sqls", [])),
      "| joins:", len(check["instructions"].get("join_specs", [])))

# COMMAND ----------

# MAGIC %md ## 2b · Coaching360 Genie spaces (one per level)
# MAGIC Re-running updates an existing space with the definition in `agents/agent_bricks/coaching360`.

# COMMAND ----------

C360_GENIE = {}
if COACHING360:
    c360 = json.load(open(f"{AB}/coaching360/genie_spaces.json"))
    by_title = {s.get("title"): s["space_id"] for s in w.api_client.do("GET", "/api/2.0/genie/spaces").get("spaces", [])}
    for item in c360["spaces"]:
        space = json.load(open(f"{AB}/coaching360/{item['serialized_space_file']}"))
        if item["title"] in by_title:
            C360_GENIE[item["level"]] = by_title[item["title"]]
            w.api_client.do("PATCH", f"/api/2.0/genie/spaces/{by_title[item['title']]}", body={"serialized_space": json.dumps(space)})
            print("updated ", item["title"], by_title[item["title"]])
        else:
            me = w.current_user.me().user_name
            C360_GENIE[item["level"]] = w.api_client.do("POST", "/api/2.0/genie/spaces", body={
                "warehouse_id": warehouse_id(), "title": item["title"], "description": item["description"],
                "parent_path": f"/Workspace/Users/{me}", "serialized_space": json.dumps(space)})["space_id"]
            print("created ", item["title"], C360_GENIE[item["level"]])
        if not APP_SP.startswith("<"):
            w.api_client.do("PATCH", f"/api/2.0/permissions/genie/{C360_GENIE[item['level']]}", body={"access_control_list": [
                {"service_principal_name": APP_SP, "permission_level": "CAN_RUN"}]})
        print("          tables:", len(space["data_sources"]["tables"]), "| functions:", len(space["instructions"].get("sql_functions", [])),
              "| examples:", len(space["instructions"].get("example_question_sqls", [])))

# COMMAND ----------

# MAGIC %md ## 3 · Supervisor and its tools

# COMMAND ----------

from databricks.sdk.service.supervisoragents import GenieSpace, SupervisorAgent, Tool, UcFunction
from databricks.sdk.service.supervisoragents import KnowledgeAssistant as KnowledgeAssistantTool

sup = json.load(open(f"{AB}/supervisor/supervisor.json"))
instructions = open(f"{AB}/supervisor/{sup['instructions_file']}").read()
C360_SECTION = "COACHING360 (application-directed only)"
if not COACHING360:
    instructions = instructions.split("\n\n" + C360_SECTION)[0].rstrip() + "\n"
descriptions = {a.get("knowledge_assistant") or a.get("genie_space") or a.get("unity_catalog_function") or a.get("serving_endpoint"): a["description"]
                for a in sup["agents"]}
benefits_description = descriptions["benefits-agent-endpoint"]  # benefits KA replaces the no-retrieval endpoint

existing = {s.display_name: s for s in w.supervisor_agents.list_supervisor_agents()}
supervisor = existing.get(sup["name"]) or w.supervisor_agents.create_supervisor_agent(SupervisorAgent(
    display_name=sup["name"], description=sup["description"], instructions=instructions))
print("supervisor:", supervisor.name)

tools = {
    "branch_operations": Tool(tool_type="knowledge_assistant", description=descriptions["mariner-policy-assistant"],
                              knowledge_assistant=KnowledgeAssistantTool(knowledge_assistant_id=KAS["policy"].id)),
    "employee_handbook": Tool(tool_type="knowledge_assistant", description=descriptions["mariner-handbook-assistant"],
                              knowledge_assistant=KnowledgeAssistantTool(knowledge_assistant_id=KAS["handbook"].id)),
    "employee_benefits": Tool(tool_type="knowledge_assistant", description=benefits_description,
                              knowledge_assistant=KnowledgeAssistantTool(knowledge_assistant_id=KAS["benefits"].id)),
    "performance_data": Tool(tool_type="genie_space", description=descriptions["mariner-performance-data-assitant"],
                             genie_space=GenieSpace(id=GENIE_ID)),
    "python_exec": Tool(tool_type="uc_function", description=descriptions["system.ai.python_exec"],
                        uc_function=UcFunction(name="system.ai.python_exec")),
}
if COACHING360:
    for spec in json.load(open(f"{AB}/coaching360/supervisor_tools.json"))["tools"]:
        if spec["tool_type"] == "genie_space":
            level = spec["tool_id"].split("_")[1]  # coaching360_<level>_data
            tools[spec["tool_id"]] = Tool(tool_type="genie_space", description=spec["description"],
                                          genie_space=GenieSpace(id=C360_GENIE[level]))
        else:
            tools[spec["tool_id"]] = Tool(tool_type="knowledge_assistant", description=spec["description"],
                                          knowledge_assistant=KnowledgeAssistantTool(knowledge_assistant_id=KAS["coaching360"].id))
have = {t.tool_id for t in w.supervisor_agents.list_tools(parent=supervisor.name)}
for tool_id, tool in tools.items():
    if tool_id not in have:
        w.supervisor_agents.create_tool(parent=supervisor.name, tool=tool, tool_id=tool_id)
    print(f"tool  {tool_id:26} {tool.tool_type}")

# An existing Supervisor keeps its instructions; add the Coaching360 section once (as the trial did on 2026-10-23).
current = w.supervisor_agents.get_supervisor_agent(supervisor.name)
if COACHING360 and C360_SECTION not in (current.instructions or ""):
    addition = C360_SECTION + instructions.split(C360_SECTION, 1)[1]
    try:
        from databricks.sdk.common.types.fieldmask import FieldMask
        mask = FieldMask(field_mask=["instructions"])
    except ImportError:
        mask = "instructions"
    try:
        w.supervisor_agents.update_supervisor_agent(name=supervisor.name, update_mask=mask, supervisor_agent=SupervisorAgent(
            display_name=current.display_name, instructions=(current.instructions or "").rstrip() + "\n\n" + addition))
        print("instructions: Coaching360 section added")
    except Exception as error:
        print(f"PASTE IN THE UI at the end of the Supervisor instructions:\n\n{addition}\n({str(error)[:160]})")

# The SDK has no typed spec for serving-endpoint tools yet; try the REST body, else add it in the UI.
if "performance_policy" not in have:
    try:
        w.api_client.do("POST", f"/api/2.0/{supervisor.name}/tools", query={"tool_id": "performance_policy"}, body={
            "tool_type": "serving_endpoint", "description": descriptions["perf-policy-citations-dev"],
            "serving_endpoint": {"name": PERF_AGENT_ENDPOINT}})
        print(f"tool  performance_policy  serving_endpoint {PERF_AGENT_ENDPOINT}")
    except Exception as error:
        print(f"ADD IN THE UI: Supervisor > Add agent > Agent endpoint `{PERF_AGENT_ENDPOINT}`, description:\n"
              f"  {descriptions['perf-policy-citations-dev']}\n  (API said: {str(error)[:160]})")

supervisor = wait_for_endpoint(lambda: w.supervisor_agents.get_supervisor_agent(supervisor.name), sup["name"])
grant_query(supervisor.endpoint_name)
print("supervisor endpoint:", supervisor.endpoint_name)

# COMMAND ----------

# MAGIC %md ## 4 · Values for the app (`app/env.prod.template`)

# COMMAND ----------

routes = {
    "/policy": {"endpoint": KAS["policy"].endpoint_name, "api": "responses", "agent": "mariner-policy-assistant"},
    "/handbook": {"endpoint": KAS["handbook"].endpoint_name, "api": "responses", "agent": "mariner-handbook-assistant"},
    "/benefits": {"endpoint": KAS["benefits"].endpoint_name, "api": "responses", "agent": "mariner-benefits-assistant"},
    "/performance": {"endpoint": PERF_AGENT_ENDPOINT, "api": "responses", "agent": "endpoint-perf-policy-citations"},
}
print(f"DATABRICKS_SUPERVISOR_ENDPOINT={supervisor.endpoint_name}")
print("DIRECT_SPECIALIST_ROUTES_JSON=" + json.dumps(routes, separators=(",", ":")))
if COACHING360:
    print("COACHING360 Genie spaces:", C360_GENIE, "| guide endpoint:", KAS["coaching360"].endpoint_name)
    print("COACHING360_ENABLED=true  (only after the persona issue in the guide, section 11, is resolved)")
