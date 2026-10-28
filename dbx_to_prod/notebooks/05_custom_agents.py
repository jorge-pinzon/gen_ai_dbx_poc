# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Custom code agents (prod)
# MAGIC Logs, registers and serves **perf_policy_citations_agent** (Responses API, structured citations).
# MAGIC Source: `agents/custom/perf_policy_citations_agent/perf_policy_citations_agent.py`, exported from the
# MAGIC trial model `workspace.ask_mariner_perf_dev.perf_policy_citations_agent` v2.
# MAGIC
# MAGIC The trial **benefits_agent** is included for reference only: it has no retrieval step, so it answers
# MAGIC from the model's own knowledge. Use the `mariner-benefits-assistant` Knowledge Assistant (notebook 06)
# MAGIC instead. The last cell can deploy it if you still need it.

# COMMAND ----------

# MAGIC %pip install -U "mlflow[databricks]>=3.1" databricks-agents databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import json
import mlflow
from mlflow.models.resources import DatabricksServingEndpoint, DatabricksVectorSearchIndex

mlflow.set_registry_uri("databricks-uc")
AGENT_DIR = f"{ROOT}/agents/custom/perf_policy_citations_agent"
code_path = f"{AGENT_DIR}/perf_policy_citations_agent.py"
source = open(code_path).read()
assert f'INDEX = "{PERF_SCHEMA}.perf_policy_retrieval_index"' in source, "agent INDEX does not match PERF_SCHEMA"
assert f'LLM_ENDPOINT = "{PERF_AGENT_LLM}"' in source, "agent LLM_ENDPOINT does not match PERF_AGENT_LLM"
requirements = [l.strip() for l in open(f"{AGENT_DIR}/requirements.txt") if l.strip() and not l.startswith("#")]
input_example = json.load(open(f"{AGENT_DIR}/input_example.json"))

with mlflow.start_run(run_name="perf_policy_citations_agent"):
    info = mlflow.pyfunc.log_model(
        name="agent", python_model=code_path, input_example=input_example, pip_requirements=requirements,
        # Automatic auth passthrough: the endpoint gets short-lived credentials for exactly these resources.
        resources=[DatabricksVectorSearchIndex(index_name=f"{PERF_SCHEMA}.perf_policy_retrieval_index"),
                   DatabricksServingEndpoint(endpoint_name=PERF_AGENT_LLM)])
version = mlflow.register_model(info.model_uri, PERF_AGENT_MODEL).version
print(f"registered {PERF_AGENT_MODEL} v{version}")

# COMMAND ----------

# MAGIC %md ## Quick local check before serving

# COMMAND ----------

agent = mlflow.pyfunc.load_model(f"models:/{PERF_AGENT_MODEL}/{version}")
reply = agent.predict({"input": [{"role": "user", "content": "How often must managers hold performance review meetings?"}]})
text = reply["output"][0]["content"][0]["text"]
payload = json.loads(text)
print(payload["answer"][:300], "\ncitations:", len(payload["citations"]))
assert payload["citations"], "expected at least one citation"

# COMMAND ----------

# MAGIC %md ## Serve it (scale to zero, small CPU)

# COMMAND ----------

from databricks import agents

deployment = agents.deploy(PERF_AGENT_MODEL, version, endpoint_name=PERF_AGENT_ENDPOINT, scale_to_zero=True)
print("endpoint:", deployment.endpoint_name)

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ServingEndpointAccessControlRequest, ServingEndpointPermissionLevel

w = WorkspaceClient()
endpoint = w.serving_endpoints.get(PERF_AGENT_ENDPOINT)
print("state:", endpoint.state.ready, "| scale to zero:", [e.scale_to_zero_enabled for e in endpoint.config.served_entities])
if not APP_SP.startswith("<"):
    w.serving_endpoints.update_permissions(endpoint.id, access_control_list=[ServingEndpointAccessControlRequest(
        service_principal_name=APP_SP, permission_level=ServingEndpointPermissionLevel.CAN_QUERY)])
    print("app service principal: CAN_QUERY")

# COMMAND ----------

# MAGIC %md ## Optional: legacy benefits_agent (not recommended)
# MAGIC Set `DEPLOY_LEGACY_BENEFITS = True` only if something outside this app still calls `benefits-agent-endpoint`.

# COMMAND ----------

DEPLOY_LEGACY_BENEFITS = False
if DEPLOY_LEGACY_BENEFITS:
    bdir = f"{ROOT}/agents/custom/benefits_agent"
    with mlflow.start_run(run_name="benefits_agent"):
        binfo = mlflow.pyfunc.log_model(
            name="agent", python_model=f"{bdir}/agent.py", input_example=json.load(open(f"{bdir}/input_example.json")),
            pip_requirements=[l.strip() for l in open(f"{bdir}/requirements.txt") if l.strip()],
            resources=[DatabricksServingEndpoint(endpoint_name=BENEFITS_AGENT_LLM)])
    bversion = mlflow.register_model(binfo.model_uri, f"{DOCS_SCHEMA}.benefits_agent_model").version
    agents.deploy(f"{DOCS_SCHEMA}.benefits_agent_model", bversion, endpoint_name="benefits-agent-endpoint", scale_to_zero=True)
