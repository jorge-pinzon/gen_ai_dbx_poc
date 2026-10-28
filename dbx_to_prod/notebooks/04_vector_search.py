# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Vector search endpoint and indexes (prod)
# MAGIC Creates one **STANDARD** endpoint and the Delta Sync indexes (five, six with `coaching360_index`), or syncs them if they exist.
# MAGIC Indexes are **TRIGGERED**: they sync only when this notebook (or the upload tool) asks, so there
# MAGIC is no always-on sync pipeline to pay for. Run after notebook 03, and again after every document refresh.

# COMMAND ----------

# MAGIC %pip install -U databricks-sdk
# MAGIC %restart_python

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import time
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest, EmbeddingSourceColumn, EndpointType, PipelineType, VectorIndexType)

w = WorkspaceClient()
if VS_ENDPOINT not in {e.name for e in w.vector_search_endpoints.list_endpoints()}:
    print(f"creating endpoint {VS_ENDPOINT} (STANDARD) ...")
    w.vector_search_endpoints.create_endpoint_and_wait(name=VS_ENDPOINT, endpoint_type=EndpointType.STANDARD)
print("endpoint:", w.vector_search_endpoints.get_endpoint(VS_ENDPOINT).endpoint_status.state)

# COMMAND ----------

existing = {i.name for i in w.vector_search_indexes.list_indexes(endpoint_name=VS_ENDPOINT)}
for spec in INDEXES:
    if spec["name"] in existing:
        w.vector_search_indexes.sync_index(spec["name"])
        print(f"sync requested  {spec['name']}")
        continue
    w.vector_search_indexes.create_index(
        name=spec["name"], endpoint_name=VS_ENDPOINT, primary_key=spec["primary_key"],
        index_type=VectorIndexType.DELTA_SYNC,
        delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
            source_table=spec["source"], pipeline_type=PipelineType.TRIGGERED,
            embedding_source_columns=[EmbeddingSourceColumn(
                name=spec["embedding_col"], embedding_model_endpoint_name=EMBEDDING_MODEL)]))
    print(f"created         {spec['name']}  <- {spec['source']}.{spec['embedding_col']}")

# COMMAND ----------

# MAGIC %md ## Wait until every index has all rows of its source table

# COMMAND ----------

deadline = time.time() + 45 * 60
pending = {s["name"]: spark.table(s["source"]).count() for s in INDEXES}
while pending and time.time() < deadline:
    for name, rows in list(pending.items()):
        status = w.vector_search_indexes.get_index(name).status
        if status.ready and status.indexed_row_count == rows:
            print(f"ready  {name:60} {rows} rows")
            del pending[name]
    if pending:
        time.sleep(20)
if pending:
    raise TimeoutError(f"Indexes not ready after 45 minutes: {sorted(pending)}")
