-- DDL exported read-only from workspace.default (structure only, no data)

-- MANAGED: workspace.default.759781574023970_otel_annotations
CREATE TABLE workspace.default.`759781574023970_otel_annotations` (
  annotation_id STRING COLLATE UTF8_BINARY,
  target_type STRING COLLATE UTF8_BINARY,
  target_id STRING COLLATE UTF8_BINARY,
  annotation_type STRING COLLATE UTF8_BINARY,
  name STRING COLLATE UTF8_BINARY,
  value VARIANT,
  comment STRING COLLATE UTF8_BINARY,
  metadata VARIANT,
  created_at TIMESTAMP,
  created_by STRING COLLATE UTF8_BINARY,
  updated_at TIMESTAMP,
  updated_by STRING COLLATE UTF8_BINARY,
  deleted_at TIMESTAMP,
  deleted_by STRING COLLATE UTF8_BINARY,
  _change_type STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (annotation_id,target_id,updated_at)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v1');

-- MANAGED: workspace.default.759781574023970_otel_logs
CREATE TABLE workspace.default.`759781574023970_otel_logs` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  event_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  time_unix_nano BIGINT,
  observed_time_unix_nano BIGINT,
  severity_number STRING COLLATE UTF8_BINARY,
  severity_text STRING COLLATE UTF8_BINARY,
  body VARIANT,
  attributes VARIANT,
  dropped_attributes_count INT,
  flags INT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  log_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.759781574023970_otel_metrics
CREATE TABLE workspace.default.`759781574023970_otel_metrics` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  time_unix_nano BIGINT,
  name STRING COLLATE UTF8_BINARY,
  description STRING COLLATE UTF8_BINARY,
  unit STRING COLLATE UTF8_BINARY,
  metric_type STRING COLLATE UTF8_BINARY,
  gauge STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT>,
  sum STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, aggregation_temporality: STRING COLLATE UTF8_BINARY, is_monotonic: BOOLEAN>,
  histogram STRUCT<count: BIGINT, sum: DOUBLE, bucket_counts: ARRAY<BIGINT>, explicit_bounds: ARRAY<DOUBLE>, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, min: DOUBLE, max: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  exponential_histogram STRUCT<attributes: VARIANT, count: BIGINT, sum: DOUBLE, scale: INT, zero_count: BIGINT, positive_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, negative_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, flags: INT, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, min: DOUBLE, max: DOUBLE, zero_threshold: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  summary STRUCT<count: BIGINT, sum: DOUBLE, quantile_values: ARRAY<STRUCT<quantile: DOUBLE, value: DOUBLE>>, attributes: VARIANT, flags: INT>,
  metadata VARIANT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  metric_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.759781574023970_otel_spans
CREATE TABLE workspace.default.`759781574023970_otel_spans` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  trace_state STRING COLLATE UTF8_BINARY,
  parent_span_id STRING COLLATE UTF8_BINARY,
  flags INT,
  name STRING COLLATE UTF8_BINARY,
  kind STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  end_time_unix_nano BIGINT,
  attributes VARIANT,
  dropped_attributes_count INT,
  events ARRAY<STRUCT<time_unix_nano: BIGINT, name: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>>,
  dropped_events_count INT,
  links ARRAY<STRUCT<trace_id: STRING COLLATE UTF8_BINARY, span_id: STRING COLLATE UTF8_BINARY, trace_state: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT, flags: INT>>,
  dropped_links_count INT,
  status STRUCT<message: STRING COLLATE UTF8_BINARY, code: STRING COLLATE UTF8_BINARY>,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  span_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name,trace_id)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- VIEW: workspace.default.759781574023970_trace_metadata
CREATE VIEW default.`759781574023970_trace_metadata` (
  trace_id,
  client_request_id,
  tags,
  trace_metadata,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574023970_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`759781574023970_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574023970_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 4. Main query - join metadata with tags and assessments
SELECT
  tm.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  COALESCE(ta.tags, MAP()) AS tags,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        tm.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  trace_metadata tm
  LEFT JOIN tags_agg ta ON tm.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON tm.trace_id = aa.trace_id;

-- VIEW: workspace.default.759781574023970_trace_unified
CREATE VIEW default.`759781574023970_trace_unified` (
  trace_id,
  client_request_id,
  request_time,
  state,
  execution_duration_ms,
  request,
  response,
  trace_metadata,
  tags,
  spans,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574023970_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`759781574023970_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Extract the root span which contains the full request/response and trace-level info (handling duplicates by taking the most recent)
root_span AS (
  SELECT
    trace_id,
    span_id,
    name,
    request_time,
    state,
    execution_duration_ms,
    request,
    response
  FROM (
    SELECT
      trace_id,
      span_id,
      name,
      time AS request_time,
      CASE
        WHEN status.code = 'STATUS_CODE_OK' OR status.code IS NULL THEN 'OK' -- Convert from OTEL status code semantics to the MLflow status code
        WHEN status.code = 'STATUS_CODE_ERROR' THEN 'ERROR'
        ELSE status.code
      END AS state,
      (end_time_unix_nano / 1000000.0 - UNIX_MILLIS(time)) AS execution_duration_ms,
      COALESCE(
      attributes:['mlflow.spanInputs']::string,
      attributes:['gen_ai.input.messages']::string,
      attributes:['gen_ai.tool.call.arguments']::string,
      attributes:['input.value']::string,
      attributes:['traceloop.entity.input']::string,
      attributes:['gcp.vertex.agent.llm_request']::string,
      attributes:['gcp.vertex.agent.tool_call_args']::string
    ) AS request,
      COALESCE(
      attributes:['mlflow.spanOutputs']::string,
      attributes:['gen_ai.output.messages']::string,
      attributes:['gen_ai.tool.call.result']::string,
      attributes:['output.value']::string,
      attributes:['traceloop.entity.output']::string,
      attributes:['gcp.vertex.agent.llm_response']::string,
      attributes:['gcp.vertex.agent.tool_response']::string
    ) AS response,
      ROW_NUMBER() OVER (
        PARTITION BY trace_id
        ORDER BY time DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574023970_otel_spans`
    WHERE
      COALESCE(parent_span_id, "") = ""  -- Root span has empty parent
  )
  WHERE rn = 1
),
-- 4. Aggregate all spans grouped by trace_id
spans_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(STRUCT(*)) AS spans
  FROM
    `workspace`.`default`.`759781574023970_otel_spans`
  GROUP BY
    trace_id
),
-- 5. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574023970_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 6. Main query - join the trace data from spans with metadata, tags, and assessments
SELECT
  rs.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  rs.request_time,
  rs.state,
  rs.execution_duration_ms,
  rs.request,
  rs.response,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(ta.tags, MAP()) AS tags,
  sa.spans,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        rs.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  root_span rs
  LEFT JOIN trace_metadata tm ON rs.trace_id = tm.trace_id
  LEFT JOIN tags_agg ta ON rs.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON rs.trace_id = aa.trace_id
  LEFT JOIN spans_agg sa ON rs.trace_id = sa.trace_id;

-- MANAGED: workspace.default.759781574024206_otel_annotations
CREATE TABLE workspace.default.`759781574024206_otel_annotations` (
  annotation_id STRING COLLATE UTF8_BINARY,
  target_type STRING COLLATE UTF8_BINARY,
  target_id STRING COLLATE UTF8_BINARY,
  annotation_type STRING COLLATE UTF8_BINARY,
  name STRING COLLATE UTF8_BINARY,
  value VARIANT,
  comment STRING COLLATE UTF8_BINARY,
  metadata VARIANT,
  created_at TIMESTAMP,
  created_by STRING COLLATE UTF8_BINARY,
  updated_at TIMESTAMP,
  updated_by STRING COLLATE UTF8_BINARY,
  deleted_at TIMESTAMP,
  deleted_by STRING COLLATE UTF8_BINARY,
  _change_type STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (annotation_id,target_id,updated_at)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v1');

-- MANAGED: workspace.default.759781574024206_otel_logs
CREATE TABLE workspace.default.`759781574024206_otel_logs` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  event_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  time_unix_nano BIGINT,
  observed_time_unix_nano BIGINT,
  severity_number STRING COLLATE UTF8_BINARY,
  severity_text STRING COLLATE UTF8_BINARY,
  body VARIANT,
  attributes VARIANT,
  dropped_attributes_count INT,
  flags INT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  log_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.759781574024206_otel_metrics
CREATE TABLE workspace.default.`759781574024206_otel_metrics` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  time_unix_nano BIGINT,
  name STRING COLLATE UTF8_BINARY,
  description STRING COLLATE UTF8_BINARY,
  unit STRING COLLATE UTF8_BINARY,
  metric_type STRING COLLATE UTF8_BINARY,
  gauge STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT>,
  sum STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, aggregation_temporality: STRING COLLATE UTF8_BINARY, is_monotonic: BOOLEAN>,
  histogram STRUCT<count: BIGINT, sum: DOUBLE, bucket_counts: ARRAY<BIGINT>, explicit_bounds: ARRAY<DOUBLE>, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, min: DOUBLE, max: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  exponential_histogram STRUCT<attributes: VARIANT, count: BIGINT, sum: DOUBLE, scale: INT, zero_count: BIGINT, positive_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, negative_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, flags: INT, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, min: DOUBLE, max: DOUBLE, zero_threshold: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  summary STRUCT<count: BIGINT, sum: DOUBLE, quantile_values: ARRAY<STRUCT<quantile: DOUBLE, value: DOUBLE>>, attributes: VARIANT, flags: INT>,
  metadata VARIANT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  metric_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.759781574024206_otel_spans
CREATE TABLE workspace.default.`759781574024206_otel_spans` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  trace_state STRING COLLATE UTF8_BINARY,
  parent_span_id STRING COLLATE UTF8_BINARY,
  flags INT,
  name STRING COLLATE UTF8_BINARY,
  kind STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  end_time_unix_nano BIGINT,
  attributes VARIANT,
  dropped_attributes_count INT,
  events ARRAY<STRUCT<time_unix_nano: BIGINT, name: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>>,
  dropped_events_count INT,
  links ARRAY<STRUCT<trace_id: STRING COLLATE UTF8_BINARY, span_id: STRING COLLATE UTF8_BINARY, trace_state: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT, flags: INT>>,
  dropped_links_count INT,
  status STRUCT<message: STRING COLLATE UTF8_BINARY, code: STRING COLLATE UTF8_BINARY>,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  span_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name,trace_id)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- VIEW: workspace.default.759781574024206_trace_metadata
CREATE VIEW default.`759781574024206_trace_metadata` (
  trace_id,
  client_request_id,
  tags,
  trace_metadata,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024206_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`759781574024206_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024206_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 4. Main query - join metadata with tags and assessments
SELECT
  tm.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  COALESCE(ta.tags, MAP()) AS tags,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        tm.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  trace_metadata tm
  LEFT JOIN tags_agg ta ON tm.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON tm.trace_id = aa.trace_id;

-- VIEW: workspace.default.759781574024206_trace_unified
CREATE VIEW default.`759781574024206_trace_unified` (
  trace_id,
  client_request_id,
  request_time,
  state,
  execution_duration_ms,
  request,
  response,
  trace_metadata,
  tags,
  spans,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024206_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`759781574024206_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Extract the root span which contains the full request/response and trace-level info (handling duplicates by taking the most recent)
root_span AS (
  SELECT
    trace_id,
    span_id,
    name,
    request_time,
    state,
    execution_duration_ms,
    request,
    response
  FROM (
    SELECT
      trace_id,
      span_id,
      name,
      time AS request_time,
      CASE
        WHEN status.code = 'STATUS_CODE_OK' OR status.code IS NULL THEN 'OK' -- Convert from OTEL status code semantics to the MLflow status code
        WHEN status.code = 'STATUS_CODE_ERROR' THEN 'ERROR'
        ELSE status.code
      END AS state,
      (end_time_unix_nano / 1000000.0 - UNIX_MILLIS(time)) AS execution_duration_ms,
      COALESCE(
      attributes:['mlflow.spanInputs']::string,
      attributes:['gen_ai.input.messages']::string,
      attributes:['gen_ai.tool.call.arguments']::string,
      attributes:['input.value']::string,
      attributes:['traceloop.entity.input']::string,
      attributes:['gcp.vertex.agent.llm_request']::string,
      attributes:['gcp.vertex.agent.tool_call_args']::string
    ) AS request,
      COALESCE(
      attributes:['mlflow.spanOutputs']::string,
      attributes:['gen_ai.output.messages']::string,
      attributes:['gen_ai.tool.call.result']::string,
      attributes:['output.value']::string,
      attributes:['traceloop.entity.output']::string,
      attributes:['gcp.vertex.agent.llm_response']::string,
      attributes:['gcp.vertex.agent.tool_response']::string
    ) AS response,
      ROW_NUMBER() OVER (
        PARTITION BY trace_id
        ORDER BY time DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024206_otel_spans`
    WHERE
      COALESCE(parent_span_id, "") = ""  -- Root span has empty parent
  )
  WHERE rn = 1
),
-- 4. Aggregate all spans grouped by trace_id
spans_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(STRUCT(*)) AS spans
  FROM
    `workspace`.`default`.`759781574024206_otel_spans`
  GROUP BY
    trace_id
),
-- 5. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024206_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 6. Main query - join the trace data from spans with metadata, tags, and assessments
SELECT
  rs.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  rs.request_time,
  rs.state,
  rs.execution_duration_ms,
  rs.request,
  rs.response,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(ta.tags, MAP()) AS tags,
  sa.spans,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        rs.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  root_span rs
  LEFT JOIN trace_metadata tm ON rs.trace_id = tm.trace_id
  LEFT JOIN tags_agg ta ON rs.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON rs.trace_id = aa.trace_id
  LEFT JOIN spans_agg sa ON rs.trace_id = sa.trace_id;

-- MANAGED: workspace.default.759781574024441_otel_annotations
CREATE TABLE workspace.default.`759781574024441_otel_annotations` (
  annotation_id STRING COLLATE UTF8_BINARY,
  target_type STRING COLLATE UTF8_BINARY,
  target_id STRING COLLATE UTF8_BINARY,
  annotation_type STRING COLLATE UTF8_BINARY,
  name STRING COLLATE UTF8_BINARY,
  value VARIANT,
  comment STRING COLLATE UTF8_BINARY,
  metadata VARIANT,
  created_at TIMESTAMP,
  created_by STRING COLLATE UTF8_BINARY,
  updated_at TIMESTAMP,
  updated_by STRING COLLATE UTF8_BINARY,
  deleted_at TIMESTAMP,
  deleted_by STRING COLLATE UTF8_BINARY,
  _change_type STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (annotation_id,target_id,updated_at)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v1');

-- MANAGED: workspace.default.759781574024441_otel_logs
CREATE TABLE workspace.default.`759781574024441_otel_logs` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  event_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  time_unix_nano BIGINT,
  observed_time_unix_nano BIGINT,
  severity_number STRING COLLATE UTF8_BINARY,
  severity_text STRING COLLATE UTF8_BINARY,
  body VARIANT,
  attributes VARIANT,
  dropped_attributes_count INT,
  flags INT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  log_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.759781574024441_otel_metrics
CREATE TABLE workspace.default.`759781574024441_otel_metrics` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  time_unix_nano BIGINT,
  name STRING COLLATE UTF8_BINARY,
  description STRING COLLATE UTF8_BINARY,
  unit STRING COLLATE UTF8_BINARY,
  metric_type STRING COLLATE UTF8_BINARY,
  gauge STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT>,
  sum STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, aggregation_temporality: STRING COLLATE UTF8_BINARY, is_monotonic: BOOLEAN>,
  histogram STRUCT<count: BIGINT, sum: DOUBLE, bucket_counts: ARRAY<BIGINT>, explicit_bounds: ARRAY<DOUBLE>, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, min: DOUBLE, max: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  exponential_histogram STRUCT<attributes: VARIANT, count: BIGINT, sum: DOUBLE, scale: INT, zero_count: BIGINT, positive_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, negative_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, flags: INT, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, min: DOUBLE, max: DOUBLE, zero_threshold: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  summary STRUCT<count: BIGINT, sum: DOUBLE, quantile_values: ARRAY<STRUCT<quantile: DOUBLE, value: DOUBLE>>, attributes: VARIANT, flags: INT>,
  metadata VARIANT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  metric_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.759781574024441_otel_spans
CREATE TABLE workspace.default.`759781574024441_otel_spans` (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  trace_state STRING COLLATE UTF8_BINARY,
  parent_span_id STRING COLLATE UTF8_BINARY,
  flags INT,
  name STRING COLLATE UTF8_BINARY,
  kind STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  end_time_unix_nano BIGINT,
  attributes VARIANT,
  dropped_attributes_count INT,
  events ARRAY<STRUCT<time_unix_nano: BIGINT, name: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>>,
  dropped_events_count INT,
  links ARRAY<STRUCT<trace_id: STRING COLLATE UTF8_BINARY, span_id: STRING COLLATE UTF8_BINARY, trace_state: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT, flags: INT>>,
  dropped_links_count INT,
  status STRUCT<message: STRING COLLATE UTF8_BINARY, code: STRING COLLATE UTF8_BINARY>,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  span_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name,trace_id)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- VIEW: workspace.default.759781574024441_trace_metadata
CREATE VIEW default.`759781574024441_trace_metadata` (
  trace_id,
  client_request_id,
  tags,
  trace_metadata,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024441_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`759781574024441_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024441_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 4. Main query - join metadata with tags and assessments
SELECT
  tm.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  COALESCE(ta.tags, MAP()) AS tags,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        tm.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  trace_metadata tm
  LEFT JOIN tags_agg ta ON tm.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON tm.trace_id = aa.trace_id;

-- VIEW: workspace.default.759781574024441_trace_unified
CREATE VIEW default.`759781574024441_trace_unified` (
  trace_id,
  client_request_id,
  request_time,
  state,
  execution_duration_ms,
  request,
  response,
  trace_metadata,
  tags,
  spans,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024441_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`759781574024441_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Extract the root span which contains the full request/response and trace-level info (handling duplicates by taking the most recent)
root_span AS (
  SELECT
    trace_id,
    span_id,
    name,
    request_time,
    state,
    execution_duration_ms,
    request,
    response
  FROM (
    SELECT
      trace_id,
      span_id,
      name,
      time AS request_time,
      CASE
        WHEN status.code = 'STATUS_CODE_OK' OR status.code IS NULL THEN 'OK' -- Convert from OTEL status code semantics to the MLflow status code
        WHEN status.code = 'STATUS_CODE_ERROR' THEN 'ERROR'
        ELSE status.code
      END AS state,
      (end_time_unix_nano / 1000000.0 - UNIX_MILLIS(time)) AS execution_duration_ms,
      COALESCE(
      attributes:['mlflow.spanInputs']::string,
      attributes:['gen_ai.input.messages']::string,
      attributes:['gen_ai.tool.call.arguments']::string,
      attributes:['input.value']::string,
      attributes:['traceloop.entity.input']::string,
      attributes:['gcp.vertex.agent.llm_request']::string,
      attributes:['gcp.vertex.agent.tool_call_args']::string
    ) AS request,
      COALESCE(
      attributes:['mlflow.spanOutputs']::string,
      attributes:['gen_ai.output.messages']::string,
      attributes:['gen_ai.tool.call.result']::string,
      attributes:['output.value']::string,
      attributes:['traceloop.entity.output']::string,
      attributes:['gcp.vertex.agent.llm_response']::string,
      attributes:['gcp.vertex.agent.tool_response']::string
    ) AS response,
      ROW_NUMBER() OVER (
        PARTITION BY trace_id
        ORDER BY time DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024441_otel_spans`
    WHERE
      COALESCE(parent_span_id, "") = ""  -- Root span has empty parent
  )
  WHERE rn = 1
),
-- 4. Aggregate all spans grouped by trace_id
spans_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(STRUCT(*)) AS spans
  FROM
    `workspace`.`default`.`759781574024441_otel_spans`
  GROUP BY
    trace_id
),
-- 5. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`759781574024441_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 6. Main query - join the trace data from spans with metadata, tags, and assessments
SELECT
  rs.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  rs.request_time,
  rs.state,
  rs.execution_duration_ms,
  rs.request,
  rs.response,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(ta.tags, MAP()) AS tags,
  sa.spans,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        rs.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  root_span rs
  LEFT JOIN trace_metadata tm ON rs.trace_id = tm.trace_id
  LEFT JOIN tags_agg ta ON rs.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON rs.trace_id = aa.trace_id
  LEFT JOIN spans_agg sa ON rs.trace_id = sa.trace_id;

-- VIEW: workspace.default.app_citation_registry
CREATE VIEW default.app_citation_registry (
  document_id,
  document_version,
  chunk_id,
  document_title,
  domain,
  source_volume_path,
  page_start,
  page_end,
  chunk_text)
COMMENT 'The table contains records related to documents and their respective citations. It includes details such as document IDs, versions, titles, and chunked text along with pagination information. Possible use cases include managing document versions, tracking citations across different domains, and analyzing the contents of documents for research or compliance purposes.'
WITH SCHEMA COMPENSATION
AS WITH source_chunks AS (
  SELECT 'Branch Operations' AS domain, document_title,
         volume_path AS source_volume_path, TRY_CAST(page_start AS INT) AS page_start,
         CAST(chunk_text AS STRING) AS chunk_text
  FROM workspace.default.branch_operations_chunks
  UNION ALL
  SELECT 'Employee Handbook', document_title, volume_path,
         TRY_CAST(page_start AS INT), CAST(chunk_text AS STRING)
  FROM workspace.default.employee_handbook_chunks
  UNION ALL
  SELECT 'Employee Benefits', document_title, volume_path,
         TRY_CAST(page_start AS INT), CAST(chunk_text AS STRING)
  FROM workspace.default.benefits_chunks
  UNION ALL
  SELECT 'Employee Performance Policy', document_name, source_volume_path,
         TRY_CAST(page_start AS INT), CAST(chunk_text AS STRING)
  FROM workspace.performance_test.app_policy_chunks
), valid_chunks AS (
  SELECT DISTINCT * FROM source_chunks
  WHERE page_start >= 1 AND chunk_text IS NOT NULL
    AND document_title IS NOT NULL AND source_volume_path IS NOT NULL
), documents AS (
  SELECT domain, document_title, source_volume_path,
         SHA2(TO_JSON(NAMED_STRUCT('domain', domain, 'path', source_volume_path)), 256) AS document_id,
         SHA2(TO_JSON(SORT_ARRAY(COLLECT_SET(
           NAMED_STRUCT('page', page_start, 'text', chunk_text)))), 256) AS document_version
  FROM valid_chunks
  GROUP BY domain, document_title, source_volume_path
)
SELECT d.document_id, d.document_version,
       SHA2(TO_JSON(NAMED_STRUCT('version', d.document_version,
         'page', c.page_start, 'text', c.chunk_text)), 256) AS chunk_id,
       d.document_title, d.domain, d.source_volume_path,
       c.page_start, c.page_start AS page_end, c.chunk_text
FROM documents d JOIN valid_chunks c
  ON d.domain = c.domain AND d.document_title = c.document_title
 AND d.source_volume_path = c.source_volume_path;

-- MANAGED: workspace.default.benefits_agent_otel_annotations
CREATE TABLE workspace.default.benefits_agent_otel_annotations (
  annotation_id STRING COLLATE UTF8_BINARY,
  target_type STRING COLLATE UTF8_BINARY,
  target_id STRING COLLATE UTF8_BINARY,
  annotation_type STRING COLLATE UTF8_BINARY,
  name STRING COLLATE UTF8_BINARY,
  value VARIANT,
  comment STRING COLLATE UTF8_BINARY,
  metadata VARIANT,
  created_at TIMESTAMP,
  created_by STRING COLLATE UTF8_BINARY,
  updated_at TIMESTAMP,
  updated_by STRING COLLATE UTF8_BINARY,
  deleted_at TIMESTAMP,
  deleted_by STRING COLLATE UTF8_BINARY,
  _change_type STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (annotation_id,target_id,updated_at)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v1');

-- MANAGED: workspace.default.benefits_agent_otel_logs
CREATE TABLE workspace.default.benefits_agent_otel_logs (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  event_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  time_unix_nano BIGINT,
  observed_time_unix_nano BIGINT,
  severity_number STRING COLLATE UTF8_BINARY,
  severity_text STRING COLLATE UTF8_BINARY,
  body VARIANT,
  attributes VARIANT,
  dropped_attributes_count INT,
  flags INT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  log_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.benefits_agent_otel_metrics
CREATE TABLE workspace.default.benefits_agent_otel_metrics (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  time_unix_nano BIGINT,
  name STRING COLLATE UTF8_BINARY,
  description STRING COLLATE UTF8_BINARY,
  unit STRING COLLATE UTF8_BINARY,
  metric_type STRING COLLATE UTF8_BINARY,
  gauge STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT>,
  sum STRUCT<value: DOUBLE, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, aggregation_temporality: STRING COLLATE UTF8_BINARY, is_monotonic: BOOLEAN>,
  histogram STRUCT<count: BIGINT, sum: DOUBLE, bucket_counts: ARRAY<BIGINT>, explicit_bounds: ARRAY<DOUBLE>, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, attributes: VARIANT, flags: INT, min: DOUBLE, max: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  exponential_histogram STRUCT<attributes: VARIANT, count: BIGINT, sum: DOUBLE, scale: INT, zero_count: BIGINT, positive_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, negative_bucket: STRUCT<offset: INT, bucket_counts: ARRAY<BIGINT>>, flags: INT, exemplars: ARRAY<STRUCT<time_unix_nano: BIGINT, value: DOUBLE, span_id: STRING COLLATE UTF8_BINARY, trace_id: STRING COLLATE UTF8_BINARY, filtered_attributes: VARIANT>>, min: DOUBLE, max: DOUBLE, zero_threshold: DOUBLE, aggregation_temporality: STRING COLLATE UTF8_BINARY>,
  summary STRUCT<count: BIGINT, sum: DOUBLE, quantile_values: ARRAY<STRUCT<quantile: DOUBLE, value: DOUBLE>>, attributes: VARIANT, flags: INT>,
  metadata VARIANT,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  metric_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- MANAGED: workspace.default.benefits_agent_otel_spans
CREATE TABLE workspace.default.benefits_agent_otel_spans (
  record_id STRING COLLATE UTF8_BINARY,
  time TIMESTAMP,
  date DATE,
  service_name STRING COLLATE UTF8_BINARY,
  trace_id STRING COLLATE UTF8_BINARY,
  span_id STRING COLLATE UTF8_BINARY,
  trace_state STRING COLLATE UTF8_BINARY,
  parent_span_id STRING COLLATE UTF8_BINARY,
  flags INT,
  name STRING COLLATE UTF8_BINARY,
  kind STRING COLLATE UTF8_BINARY,
  start_time_unix_nano BIGINT,
  end_time_unix_nano BIGINT,
  attributes VARIANT,
  dropped_attributes_count INT,
  events ARRAY<STRUCT<time_unix_nano: BIGINT, name: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>>,
  dropped_events_count INT,
  links ARRAY<STRUCT<trace_id: STRING COLLATE UTF8_BINARY, span_id: STRING COLLATE UTF8_BINARY, trace_state: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT, flags: INT>>,
  dropped_links_count INT,
  status STRUCT<message: STRING COLLATE UTF8_BINARY, code: STRING COLLATE UTF8_BINARY>,
  resource STRUCT<attributes: VARIANT, dropped_attributes_count: INT>,
  resource_schema_url STRING COLLATE UTF8_BINARY,
  instrumentation_scope STRUCT<name: STRING COLLATE UTF8_BINARY, version: STRING COLLATE UTF8_BINARY, attributes: VARIANT, dropped_attributes_count: INT>,
  span_schema_url STRING COLLATE UTF8_BINARY)
USING delta
CLUSTER BY (time,service_name,trace_id)
TBLPROPERTIES (
  'delta.checkpointPolicy' = 'classic',
  'delta.enableInCommitTimestamps' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.catalogManaged' = 'supported',
  'delta.feature.inCommitTimestamp' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.feature.vacuumProtocolCheck' = 'supported',
  'delta.feature.variantShredding-preview' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.feature.variantType-preview' = 'supported',
  'delta.parquet.compression.codec' = 'zstd',
  'otel.schemaVersion' = 'v2');

-- VIEW: workspace.default.benefits_agent_trace_metadata
CREATE VIEW default.benefits_agent_trace_metadata (
  trace_id,
  client_request_id,
  tags,
  trace_metadata,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`benefits_agent_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`benefits_agent_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`benefits_agent_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 4. Main query - join metadata with tags and assessments
SELECT
  tm.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  COALESCE(ta.tags, MAP()) AS tags,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        tm.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  trace_metadata tm
  LEFT JOIN tags_agg ta ON tm.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON tm.trace_id = aa.trace_id;

-- VIEW: workspace.default.benefits_agent_trace_unified
CREATE VIEW default.benefits_agent_trace_unified (
  trace_id,
  client_request_id,
  request_time,
  state,
  execution_duration_ms,
  request,
  response,
  trace_metadata,
  tags,
  spans,
  assessments)
WITH SCHEMA BINDING
AS WITH
-- 1. Extract trace metadata from annotations table (handling duplicates by taking the most recent)
trace_metadata AS (
  SELECT
    trace_id,
    metadata_data
  FROM (
    SELECT
      target_id AS trace_id,
      value AS metadata_data,
      ROW_NUMBER() OVER (
        PARTITION BY target_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`benefits_agent_otel_annotations`
    WHERE
      annotation_type = 'METADATA'
  )
  WHERE rn = 1
),
-- 2. Extract and aggregate individual tag annotations (handling duplicates by taking the most recent)
tags_agg AS (
  SELECT
    trace_id,
    MAP_FROM_ENTRIES(
      COLLECT_LIST(
        STRUCT(
          key,
          value
        )
      )
    ) AS tags
  FROM (
    SELECT
      target_id AS trace_id,
      name AS key,
      value::STRING AS value,
      ROW_NUMBER() OVER (
        PARTITION BY target_id, name
        ORDER BY updated_at DESC
      ) AS rn,
      deleted_at
    FROM
      `workspace`.`default`.`benefits_agent_otel_annotations`
    WHERE
      annotation_type = 'TAG'
  )
  WHERE rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
),
-- 3. Extract the root span which contains the full request/response and trace-level info (handling duplicates by taking the most recent)
root_span AS (
  SELECT
    trace_id,
    span_id,
    name,
    request_time,
    state,
    execution_duration_ms,
    request,
    response
  FROM (
    SELECT
      trace_id,
      span_id,
      name,
      time AS request_time,
      CASE
        WHEN status.code = 'STATUS_CODE_OK' OR status.code IS NULL THEN 'OK' -- Convert from OTEL status code semantics to the MLflow status code
        WHEN status.code = 'STATUS_CODE_ERROR' THEN 'ERROR'
        ELSE status.code
      END AS state,
      (end_time_unix_nano / 1000000.0 - UNIX_MILLIS(time)) AS execution_duration_ms,
      COALESCE(
      attributes:['mlflow.spanInputs']::string,
      attributes:['gen_ai.input.messages']::string,
      attributes:['gen_ai.tool.call.arguments']::string,
      attributes:['input.value']::string,
      attributes:['traceloop.entity.input']::string,
      attributes:['gcp.vertex.agent.llm_request']::string,
      attributes:['gcp.vertex.agent.tool_call_args']::string
    ) AS request,
      COALESCE(
      attributes:['mlflow.spanOutputs']::string,
      attributes:['gen_ai.output.messages']::string,
      attributes:['gen_ai.tool.call.result']::string,
      attributes:['output.value']::string,
      attributes:['traceloop.entity.output']::string,
      attributes:['gcp.vertex.agent.llm_response']::string,
      attributes:['gcp.vertex.agent.tool_response']::string
    ) AS response,
      ROW_NUMBER() OVER (
        PARTITION BY trace_id
        ORDER BY time DESC
      ) AS rn
    FROM
      `workspace`.`default`.`benefits_agent_otel_spans`
    WHERE
      COALESCE(parent_span_id, "") = ""  -- Root span has empty parent
  )
  WHERE rn = 1
),
-- 4. Aggregate all spans grouped by trace_id
spans_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(STRUCT(*)) AS spans
  FROM
    `workspace`.`default`.`benefits_agent_otel_spans`
  GROUP BY
    trace_id
),
-- 5. Aggregated valid assessments from annotations table grouped by trace_id
assessments_agg AS (
  SELECT
    trace_id,
    COLLECT_LIST(
      STRUCT(
        annotation_id,
        annotation_type,
        name,
        value,
        comment,
        metadata,
        created_at,
        updated_at
      )
    ) AS assessments
  FROM
    (
    SELECT
      target_id AS trace_id,
      annotation_id,
      annotation_type,
      name,
      value,
      comment,
      metadata,
      created_at,
      updated_at,
      deleted_at,
      ROW_NUMBER() OVER (
        PARTITION BY annotation_id
        ORDER BY updated_at DESC
      ) AS rn
    FROM
      `workspace`.`default`.`benefits_agent_otel_annotations`
    WHERE
      annotation_type IN ('FEEDBACK', 'EXPECTATION')
    )
  WHERE
    rn = 1 AND deleted_at IS NULL
  GROUP BY
    trace_id
)
-- 6. Main query - join the trace data from spans with metadata, tags, and assessments
SELECT
  rs.trace_id,
  tm.metadata_data:client_request_id::STRING AS client_request_id,
  rs.request_time,
  rs.state,
  rs.execution_duration_ms,
  rs.request,
  rs.response,
  tm.metadata_data:trace_metadata AS trace_metadata,
  COALESCE(ta.tags, MAP()) AS tags,
  sa.spans,
  COALESCE(
    TRANSFORM(
      aa.assessments,
      a -> STRUCT(
        a.annotation_id AS assessment_id,
        rs.trace_id AS trace_id,
        a.name AS assessment_name,
        STRUCT(
          a.metadata:['mlflow.source.source_id']::STRING AS source_id,
          a.metadata:['mlflow.source.source_type']::STRING AS source_type
        ) AS source,
        a.created_at AS create_time,
        a.updated_at AS last_update_time,
        CASE
          WHEN a.annotation_type = 'EXPECTATION' THEN
            STRUCT(
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN NULL
                ELSE a.value::STRING
              END AS value,
              CASE
                WHEN a.metadata:['mlflow.expectation.serialization_format']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.expectation.serialization_format']::STRING AS serialization_format,
                  a.value::STRING AS value,
                  CAST(NULL AS STRING) AS stack_trace
                )
                ELSE NULL
              END AS serialized_value
            )
          ELSE NULL
        END AS expectation,
        CASE
          WHEN a.annotation_type = 'FEEDBACK' THEN
            STRUCT(
              a.value::STRING AS value,
              CASE
                WHEN a.metadata:['mlflow.error.error_code']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.error_message']::STRING IS NOT NULL
                  OR a.metadata:['mlflow.error.stack_trace']::STRING IS NOT NULL
                THEN STRUCT(
                  a.metadata:['mlflow.error.error_code']::STRING AS error_code,
                  a.metadata:['mlflow.error.error_message']::STRING AS error_message,
                  a.metadata:['mlflow.error.stack_trace']::STRING AS stack_trace
                )
                ELSE NULL
              END AS error
            )
          ELSE NULL
        END AS feedback,
        a.comment AS rationale,
        a.metadata::MAP<STRING, STRING> AS metadata,
        a.metadata:['mlflow.span_id']::STRING AS span_id,
        a.metadata:['mlflow.overrides']::STRING AS overrides,
        a.metadata:['mlflow.valid']::STRING AS valid
      )
    ),
    ARRAY()
  ) AS assessments
FROM
  root_span rs
  LEFT JOIN trace_metadata tm ON rs.trace_id = tm.trace_id
  LEFT JOIN tags_agg ta ON rs.trace_id = ta.trace_id
  LEFT JOIN assessments_agg aa ON rs.trace_id = aa.trace_id
  LEFT JOIN spans_agg sa ON rs.trace_id = sa.trace_id;

-- MANAGED: workspace.default.benefits_chunks
CREATE TABLE workspace.default.benefits_chunks (
  chunk_id STRING COLLATE UTF8_BINARY,
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  volume_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  document_title STRING COLLATE UTF8_BINARY,
  page_start INT,
  page_end INT,
  page_chunk_number INT,
  first_element_position INT,
  last_element_position INT,
  minimum_confidence DOUBLE,
  chunk_text STRING COLLATE UTF8_BINARY,
  embedding_text STRING COLLATE UTF8_BINARY,
  character_count INT,
  citation_label STRING COLLATE UTF8_BINARY,
  created_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.changeDataFeed' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.logRetentionDuration' = 'interval 90 days',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.default.benefits_document_elements
CREATE TABLE workspace.default.benefits_document_elements (
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  document_title STRING COLLATE UTF8_BINARY,
  element_position INT,
  element_id BIGINT,
  element_type STRING COLLATE UTF8_BINARY,
  raw_content STRING COLLATE UTF8_BINARY,
  cleaned_content STRING COLLATE UTF8_BINARY,
  confidence DOUBLE,
  page_id INT,
  page_number INT,
  bbox VARIANT,
  parsed_at TIMESTAMP,
  is_retrievable BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.checkpoint.writeStatsAsJson' = 'false',
  'delta.checkpoint.writeStatsAsStruct' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.variantShredding' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.default.benefits_parsed_documents
CREATE TABLE workspace.default.benefits_parsed_documents (
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  file_size_bytes BIGINT,
  source_modified_at TIMESTAMP,
  parsed_content VARIANT,
  parsed_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.variantShredding' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0',
  'delta.workloadBasedColumns.deltaFileStatistics' = '`parsed_content`',
  'delta.workloadBasedVariantFields.deltaFileStatistics' = 'parsed_content:[\'error_status\']');

-- MANAGED: workspace.default.branch_operations_chunks
CREATE TABLE workspace.default.branch_operations_chunks (
  chunk_id STRING COLLATE UTF8_BINARY,
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  volume_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  document_title STRING COLLATE UTF8_BINARY,
  page_start INT,
  page_end INT,
  page_chunk_number INT,
  first_element_position INT,
  last_element_position INT,
  minimum_confidence DOUBLE,
  chunk_text STRING COLLATE UTF8_BINARY,
  embedding_text STRING COLLATE UTF8_BINARY,
  character_count INT,
  citation_label STRING COLLATE UTF8_BINARY,
  created_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.changeDataFeed' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.logRetentionDuration' = 'interval 90 days',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.default.branch_operations_document_elements
CREATE TABLE workspace.default.branch_operations_document_elements (
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  document_title STRING COLLATE UTF8_BINARY,
  element_position INT,
  element_id BIGINT,
  element_type STRING COLLATE UTF8_BINARY,
  raw_content STRING COLLATE UTF8_BINARY,
  cleaned_content STRING COLLATE UTF8_BINARY,
  confidence DOUBLE,
  page_id INT,
  page_number INT,
  bbox VARIANT,
  parsed_at TIMESTAMP,
  is_retrievable BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.checkpoint.writeStatsAsJson' = 'false',
  'delta.checkpoint.writeStatsAsStruct' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.variantShredding' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.default.branch_operations_parsed_documents
CREATE TABLE workspace.default.branch_operations_parsed_documents (
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  file_size_bytes BIGINT,
  source_modified_at TIMESTAMP,
  parsed_content VARIANT,
  parsed_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.variantShredding' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0',
  'delta.workloadBasedColumns.deltaFileStatistics' = '`parsed_content`',
  'delta.workloadBasedVariantFields.deltaFileStatistics' = 'parsed_content:[\'error_status\']');

-- MANAGED: workspace.default.employee_handbook_chunks
CREATE TABLE workspace.default.employee_handbook_chunks (
  chunk_id STRING COLLATE UTF8_BINARY,
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  volume_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  document_title STRING COLLATE UTF8_BINARY,
  page_start INT,
  page_end INT,
  page_chunk_number INT,
  first_element_position INT,
  last_element_position INT,
  minimum_confidence DOUBLE,
  chunk_text STRING COLLATE UTF8_BINARY,
  embedding_text STRING COLLATE UTF8_BINARY,
  character_count INT,
  citation_label STRING COLLATE UTF8_BINARY,
  created_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.deletedFileRetentionDuration' = 'interval 90 days',
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.changeDataFeed' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.logRetentionDuration' = 'interval 90 days',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.default.employee_handbook_document_elements
CREATE TABLE workspace.default.employee_handbook_document_elements (
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  document_title STRING COLLATE UTF8_BINARY,
  element_position INT,
  element_id BIGINT,
  element_type STRING COLLATE UTF8_BINARY,
  raw_content STRING COLLATE UTF8_BINARY,
  cleaned_content STRING COLLATE UTF8_BINARY,
  confidence DOUBLE,
  page_id INT,
  page_number INT,
  bbox VARIANT,
  parsed_at TIMESTAMP,
  is_retrievable BOOLEAN)
USING delta
TBLPROPERTIES (
  'delta.checkpoint.writeStatsAsJson' = 'false',
  'delta.checkpoint.writeStatsAsStruct' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.variantShredding' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.default.employee_handbook_parsed_documents
CREATE TABLE workspace.default.employee_handbook_parsed_documents (
  document_id STRING COLLATE UTF8_BINARY,
  domain STRING COLLATE UTF8_BINARY,
  source_path STRING COLLATE UTF8_BINARY,
  file_name STRING COLLATE UTF8_BINARY,
  file_size_bytes BIGINT,
  source_modified_at TIMESTAMP,
  parsed_content VARIANT,
  parsed_at TIMESTAMP)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.enableVariantShredding' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.variantShredding' = 'supported',
  'delta.feature.variantType' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0',
  'delta.workloadBasedColumns.deltaFileStatistics' = '`parsed_content`',
  'delta.workloadBasedVariantFields.deltaFileStatistics' = 'parsed_content:[\'error_status\']');

-- MANAGED: workspace.default.flask_app_logs
CREATE TABLE workspace.default.flask_app_logs (
  user_id STRING COLLATE UTF8_BINARY COMMENT 'Internal corporate user identifier',
  session_id STRING COLLATE UTF8_BINARY COMMENT 'Application session identifier',
  app_version STRING COLLATE UTF8_BINARY COMMENT 'Deployed Flask application version',
  latency_ms BIGINT COMMENT 'End-to-end latency in milliseconds',
  event_id STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Unique identifier for the logged event',
  event_timestamp TIMESTAMP NOT NULL COMMENT 'UTC timestamp when the event occurred',
  question STRING COLLATE UTF8_BINARY COMMENT 'Question submitted by the user',
  answer STRING COLLATE UTF8_BINARY COMMENT 'Answer returned by the application',
  sources_json STRING COLLATE UTF8_BINARY COMMENT 'JSON array or object containing source metadata',
  source_count INT COMMENT 'Number of sources represented in sources_json',
  status STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Event outcome: success, error, or timeout',
  error_message STRING COLLATE UTF8_BINARY COMMENT 'Failure details when status is error or timeout',
  ingested_at TIMESTAMP NOT NULL COMMENT 'Timestamp when the row was written to Databricks',
  input_tokens BIGINT COMMENT 'Tokens submitted to the supervisor',
  output_tokens BIGINT COMMENT 'Tokens generated by the supervisor',
  total_tokens BIGINT COMMENT 'Total tokens consumed',
  agents_used_json STRING COLLATE UTF8_BINARY,
  inference_ms BIGINT COMMENT 'Supervisor/fast-path model time for the request',
  citations_ms BIGINT COMMENT 'Citation validation time after the model answered')
USING delta
COMMENT 'Application event and question-answer logs for the corporate Flask application'
TBLPROPERTIES (
  'delta.checkpoint.writeStatsAsJson' = 'false',
  'delta.checkpoint.writeStatsAsStruct' = 'true',
  'delta.constraints.valid_latency' = 'latency_ms IS NULL OR latency_ms >= 0',
  'delta.constraints.valid_source_count' = 'source_count IS NULL OR source_count >= 0',
  'delta.constraints.valid_status' = 'status IN (\'success\', \'error\', \'timeout\')',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.checkConstraints' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.domainMetadata' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- METRIC_VIEW: workspace.default.metrics_applications_funnel
CREATE VIEW workspace.default.metrics_applications_funnel (
  application_status COMMENT 'APPROVED, DECLINED or WITHDRAWN.',
  decline_reason COMMENT 'NULL for APPROVED applications. Populated only for DECLINED and WITHDRAWN.',
  product_type,
  channel COMMENT 'DIRECT_MAIL, PHONE, PARTNER, BRANCH, ONLINE.',
  loan_purpose,
  application_date,
  decision_date,
  decision_month COMMENT 'Prefer this over application month for time series - decision_date is always populated.',
  credit_score_band,
  dti_band,
  branch_name,
  region,
  branch_state,
  employment_status,
  housing_status,
  application_count,
  approved_count,
  declined_count,
  withdrawn_count,
  approval_rate COMMENT 'Approved applications divided by all applications (including withdrawn).',
  decline_rate,
  withdrawal_rate,
  avg_credit_score,
  avg_dti_ratio COMMENT 'Source column is a decimal fraction, so percentage formatting renders it correctly.',
  total_requested_amount,
  avg_requested_amount,
  avg_decision_lag_days)
COMMENT 'Origination funnel metrics at application grain, sourced from silver_applications (749 applications). Use for approval rate, decline reasons, channel performance and underwriting analysis. This view covers ALL applications including DECLINED and WITHDRAWN, so it is the correct source for approval rate. Do NOT use metrics_loan_portfolio for that - it only contains funded loans.'
WITH METRICS
LANGUAGE YAML
AS
$$
version: 1.1

source: workspace.default.silver_applications

joins:
  - name: customers
    source: workspace.default.silver_customers
    "on": source.customer_id = customers.customer_id
  - name: branches
    source: workspace.default.silver_branches
    "on": source.branch_id = branches.branch_id

comment: "Origination funnel metrics at application grain, sourced from silver_applications\
  \ (749 applications). Use for approval rate, decline reasons, channel performance\
  \ and underwriting analysis. This view covers ALL applications including DECLINED\
  \ and WITHDRAWN, so it is the correct source for approval rate. Do NOT use metrics_loan_portfolio\
  \ for that - it only contains funded loans."

dimensions:
  - name: application_status
    expr: application_status
    comment: "APPROVED, DECLINED or WITHDRAWN."
    display_name: Application Status
    synonyms:
      - outcome
      - decision

  - name: decline_reason
    expr: decline_reason
    comment: NULL for APPROVED applications. Populated only for DECLINED and WITHDRAWN.
    display_name: Decline Reason

  - name: product_type
    expr: product_type
    display_name: Product Type

  - name: channel
    expr: channel
    comment: "DIRECT_MAIL, PHONE, PARTNER, BRANCH, ONLINE."
    display_name: Acquisition Channel
    synonyms:
      - source
      - lead channel

  - name: loan_purpose
    expr: loan_purpose
    display_name: Loan Purpose

  - name: application_date
    expr: application_date
    display_name: Application Date

  - name: decision_date
    expr: decision_date
    display_name: Decision Date

  - name: decision_month
    expr: "DATE_TRUNC('MONTH', decision_date)"
    comment: Prefer this over application month for time series - decision_date is
      always populated.
    display_name: Decision Month

  - name: credit_score_band
    expr: |-
      CASE
        WHEN credit_score IS NULL THEN 'Unknown'
        WHEN credit_score < 580 THEN '1. Poor (<580)'
        WHEN credit_score < 670 THEN '2. Fair (580-669)'
        WHEN credit_score < 740 THEN '3. Good (670-739)'
        ELSE '4. Very Good+ (740+)'
      END
    display_name: Credit Score Band

  - name: dti_band
    expr: |-
      CASE
        WHEN dti_ratio IS NULL THEN 'Unknown'
        WHEN dti_ratio < 0.20 THEN '1. Low (<20%)'
        WHEN dti_ratio < 0.35 THEN '2. Moderate (20-35%)'
        WHEN dti_ratio < 0.45 THEN '3. High (35-45%)'
        ELSE '4. Very High (45%+)'
      END
    display_name: DTI Band

  - name: branch_name
    expr: branches.branch_name
    display_name: Branch

  - name: region
    expr: branches.region
    display_name: Region

  - name: branch_state
    expr: branches.state
    display_name: Branch State

  - name: employment_status
    expr: customers.employment_status
    display_name: Employment Status

  - name: housing_status
    expr: customers.housing_status
    display_name: Housing Status

measures:
  - name: application_count
    expr: COUNT(1)
    display_name: Application Count
    synonyms:
      - applications
      - volume

  - name: approved_count
    expr: COUNT(1) FILTER (WHERE application_status = 'APPROVED')
    display_name: Approved Count

  - name: declined_count
    expr: COUNT(1) FILTER (WHERE application_status = 'DECLINED')
    display_name: Declined Count

  - name: withdrawn_count
    expr: COUNT(1) FILTER (WHERE application_status = 'WITHDRAWN')
    display_name: Withdrawn Count

  - name: approval_rate
    expr: MEASURE(approved_count) / MEASURE(application_count)
    comment: Approved applications divided by all applications (including withdrawn).
    display_name: Approval Rate
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2
    synonyms:
      - approval percentage

  - name: decline_rate
    expr: MEASURE(declined_count) / MEASURE(application_count)
    display_name: Decline Rate
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2

  - name: withdrawal_rate
    expr: MEASURE(withdrawn_count) / MEASURE(application_count)
    display_name: Withdrawal Rate
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2

  - name: avg_credit_score
    expr: AVG(credit_score)
    display_name: Average Credit Score
    format:
      type: number
      decimal_places:
        type: exact
        places: 0

  - name: avg_dti_ratio
    expr: AVG(dti_ratio)
    comment: "Source column is a decimal fraction, so percentage formatting renders\
      \ it correctly."
    display_name: Average DTI Ratio
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2

  - name: total_requested_amount
    expr: SUM(requested_amount)
    display_name: Total Requested Amount
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: avg_requested_amount
    expr: SUM(requested_amount) / COUNT(1)
    display_name: Average Requested Amount
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: avg_decision_lag_days
    expr: "AVG(DATEDIFF(decision_date, application_date))"
    display_name: Average Decision Lag (Days)
    format:
      type: number
      decimal_places:
        type: exact
        places: 1
$$;

-- METRIC_VIEW: workspace.default.metrics_collections
CREATE VIEW workspace.default.metrics_collections (
  payment_status COMMENT 'ON_TIME or LATE.',
  payment_method COMMENT 'CASH, MONEY_ORDER, CHECK, ACH, DEBIT_CARD.',
  payment_date,
  payment_month,
  days_late_band,
  is_reversal COMMENT 'True where payment_amount is negative, indicating a reversal or refund.',
  loan_product_type,
  loan_status,
  region,
  branch_name,
  employment_status,
  payment_count,
  total_collected COMMENT 'Gross cash collected including negative reversals.',
  interest_revenue,
  principal_recovered,
  late_fee_revenue,
  on_time_count,
  late_count,
  on_time_rate,
  late_rate,
  avg_payment_amount,
  avg_days_late_when_late COMMENT 'Averaged only over LATE payments, so on-time zeros do not dilute it.',
  reversal_count)
COMMENT 'Collections and payment metrics at payment grain, sourced from silver_loan_payments (4229 payments). Use for collections cash flow, interest revenue, late fee revenue and on-time payment behaviour. Loan, branch and customer attributes are reached through the loans join. NOTE: 10 payments totalling 1086.36 USD belong to LN0000007, which was filtered out of silver_loans as a sentinel. Those payments have NULL loan/branch attributes, so breakdowns by branch or product will not sum exactly to the unbroken grand total.'
WITH METRICS
LANGUAGE YAML
AS
$$
version: 1.1

source: workspace.default.silver_loan_payments

joins:
  - name: loans
    source: workspace.default.silver_loans
    "on": source.loan_id = loans.loan_id
    joins:
      - name: branches
        source: workspace.default.silver_branches
        "on": loans.branch_id = branches.branch_id
      - name: customers
        source: workspace.default.silver_customers
        "on": loans.customer_id = customers.customer_id

comment: "Collections and payment metrics at payment grain, sourced from silver_loan_payments\
  \ (4229 payments). Use for collections cash flow, interest revenue, late fee revenue\
  \ and on-time payment behaviour. Loan, branch and customer attributes are reached\
  \ through the loans join. NOTE: 10 payments totalling 1086.36 USD belong to LN0000007,\
  \ which was filtered out of silver_loans as a sentinel. Those payments have NULL\
  \ loan/branch attributes, so breakdowns by branch or product will not sum exactly\
  \ to the unbroken grand total."

dimensions:
  - name: payment_status
    expr: payment_status
    comment: ON_TIME or LATE.
    display_name: Payment Status

  - name: payment_method
    expr: payment_method
    comment: "CASH, MONEY_ORDER, CHECK, ACH, DEBIT_CARD."
    display_name: Payment Method
    synonyms:
      - method
      - how paid

  - name: payment_date
    expr: payment_date
    display_name: Payment Date

  - name: payment_month
    expr: "DATE_TRUNC('MONTH', payment_date)"
    display_name: Payment Month
    synonyms:
      - collections month

  - name: days_late_band
    expr: |-
      CASE
        WHEN days_late = 0 THEN '0. On time'
        WHEN days_late <= 7 THEN '1. 1-7 days'
        WHEN days_late <= 14 THEN '2. 8-14 days'
        WHEN days_late <= 21 THEN '3. 15-21 days'
        ELSE '4. 22+ days'
      END
    display_name: Days Late Band

  - name: is_reversal
    expr: CASE WHEN payment_amount < 0 THEN true ELSE false END
    comment: "True where payment_amount is negative, indicating a reversal or refund."
    display_name: Is Reversal

  - name: loan_product_type
    expr: loans.product_type
    display_name: Loan Product Type

  - name: loan_status
    expr: loans.loan_status
    display_name: Loan Status

  - name: region
    expr: loans.branches.region
    display_name: Region

  - name: branch_name
    expr: loans.branches.branch_name
    display_name: Branch

  - name: employment_status
    expr: loans.customers.employment_status
    display_name: Employment Status

measures:
  - name: payment_count
    expr: COUNT(1)
    display_name: Payment Count
    synonyms:
      - payments
      - number of payments

  - name: total_collected
    expr: SUM(payment_amount)
    comment: Gross cash collected including negative reversals.
    display_name: Total Collected
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2
    synonyms:
      - collections
      - cash collected

  - name: interest_revenue
    expr: SUM(interest_portion)
    display_name: Interest Revenue
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: principal_recovered
    expr: SUM(principal_portion)
    display_name: Principal Recovered
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: late_fee_revenue
    expr: SUM(late_fee)
    display_name: Late Fee Revenue
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: on_time_count
    expr: COUNT(1) FILTER (WHERE payment_status = 'ON_TIME')
    display_name: On-Time Payment Count

  - name: late_count
    expr: COUNT(1) FILTER (WHERE payment_status = 'LATE')
    display_name: Late Payment Count

  - name: on_time_rate
    expr: MEASURE(on_time_count) / MEASURE(payment_count)
    display_name: On-Time Payment Rate
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2
    synonyms:
      - on time percentage

  - name: late_rate
    expr: MEASURE(late_count) / MEASURE(payment_count)
    display_name: Late Payment Rate
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2

  - name: avg_payment_amount
    expr: SUM(payment_amount) / COUNT(1)
    display_name: Average Payment Amount
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: avg_days_late_when_late
    expr: AVG(days_late) FILTER (WHERE payment_status = 'LATE')
    comment: "Averaged only over LATE payments, so on-time zeros do not dilute it."
    display_name: Average Days Late (Late Payments Only)
    format:
      type: number
      decimal_places:
        type: exact
        places: 1

  - name: reversal_count
    expr: COUNT(1) FILTER (WHERE payment_amount < 0)
    display_name: Reversal Count
$$;

-- METRIC_VIEW: workspace.default.metrics_loan_portfolio
CREATE VIEW workspace.default.metrics_loan_portfolio (
  loan_status COMMENT 'CURRENT, PAID_OFF, DELINQUENT_30, DELINQUENT_60, DELINQUENT_90, CHARGED_OFF.',
  is_delinquent COMMENT 'True for the three DELINQUENT buckets. CHARGED_OFF is NOT counted as delinquent.',
  product_type,
  collateral_flag,
  term_months,
  funded_date,
  funded_month,
  credit_score_band,
  channel,
  loan_purpose,
  branch_name,
  region COMMENT 'Only CENTRAL and EAST exist. There is no WEST region.',
  branch_state,
  employment_status,
  housing_status,
  loan_count,
  outstanding_balance COMMENT 'Current principal outstanding. This is the correct measure for portfolio exposure.',
  original_principal COMMENT 'Sum of original loan amounts. Do NOT use for current exposure - use outstanding_balance.',
  avg_loan_amount,
  avg_interest_rate COMMENT 'Already a percentage (13.02 means 13.02 percent). Do not multiply by 100.',
  delinquent_loan_count,
  delinquent_balance,
  delinquency_rate_by_count COMMENT 'Delinquent loans divided by total loans. Differs from the balance-weighted rate.',
  delinquency_rate_by_balance COMMENT 'Delinquent balance divided by total outstanding balance. Balance-weighted.',
  charged_off_loan_count,
  charge_off_rate COMMENT 'Charged-off loans divided by total loans. Separate loss category from delinquency.',
  paid_off_loan_count,
  current_loan_count,
  total_requested_amount COMMENT 'From the originating application. Excludes LN0000004 which has no matching application.',
  funded_to_requested_ratio COMMENT 'Below 1.0 means loans are funded for less than applicants requested.')
COMMENT 'Loan portfolio metrics at loan grain, sourced from silver_loans (388 funded loans). Use for outstanding balance, delinquency, charge-off and portfolio composition. Delinquency is exposed BOTH by loan count and by outstanding balance because the two give materially different answers - pick deliberately. NOTE: LN0000004 has no matching row in silver_applications, so application-sourced measures (requested amount) exclude it.'
WITH METRICS
LANGUAGE YAML
AS
$$
version: 1.1

source: workspace.default.silver_loans

joins:
  - name: customers
    source: workspace.default.silver_customers
    "on": source.customer_id = customers.customer_id
  - name: branches
    source: workspace.default.silver_branches
    "on": source.branch_id = branches.branch_id
  - name: applications
    source: workspace.default.silver_applications
    "on": source.application_id = applications.application_id

comment: "Loan portfolio metrics at loan grain, sourced from silver_loans (388 funded\
  \ loans). Use for outstanding balance, delinquency, charge-off and portfolio composition.\
  \ Delinquency is exposed BOTH by loan count and by outstanding balance because the\
  \ two give materially different answers - pick deliberately. NOTE: LN0000004 has\
  \ no matching row in silver_applications, so application-sourced measures (requested\
  \ amount) exclude it."

dimensions:
  - name: loan_status
    expr: loan_status
    comment: "CURRENT, PAID_OFF, DELINQUENT_30, DELINQUENT_60, DELINQUENT_90, CHARGED_OFF."
    display_name: Loan Status
    synonyms:
      - status
      - loan state

  - name: is_delinquent
    expr: "CASE WHEN loan_status IN ('DELINQUENT_30','DELINQUENT_60','DELINQUENT_90')\
      \ THEN true ELSE false END"
    comment: True for the three DELINQUENT buckets. CHARGED_OFF is NOT counted as
      delinquent.
    display_name: Is Delinquent

  - name: product_type
    expr: product_type
    display_name: Product Type
    synonyms:
      - product

  - name: collateral_flag
    expr: collateral_flag
    display_name: Collateral Flag

  - name: term_months
    expr: term_months
    display_name: Term (Months)

  - name: funded_date
    expr: funded_date
    display_name: Funded Date

  - name: funded_month
    expr: "DATE_TRUNC('MONTH', funded_date)"
    display_name: Funded Month
    synonyms:
      - origination month
      - vintage

  - name: credit_score_band
    expr: |-
      CASE
        WHEN applications.credit_score IS NULL THEN 'Unknown'
        WHEN applications.credit_score < 580 THEN '1. Poor (<580)'
        WHEN applications.credit_score < 670 THEN '2. Fair (580-669)'
        WHEN applications.credit_score < 740 THEN '3. Good (670-739)'
        ELSE '4. Very Good+ (740+)'
      END
    display_name: Credit Score Band

  - name: channel
    expr: applications.channel
    display_name: Acquisition Channel

  - name: loan_purpose
    expr: applications.loan_purpose
    display_name: Loan Purpose

  - name: branch_name
    expr: branches.branch_name
    display_name: Branch

  - name: region
    expr: branches.region
    comment: Only CENTRAL and EAST exist. There is no WEST region.
    display_name: Region

  - name: branch_state
    expr: branches.state
    display_name: Branch State

  - name: employment_status
    expr: customers.employment_status
    display_name: Employment Status

  - name: housing_status
    expr: customers.housing_status
    display_name: Housing Status

measures:
  - name: loan_count
    expr: COUNT(1)
    display_name: Loan Count
    synonyms:
      - number of loans
      - loans

  - name: outstanding_balance
    expr: SUM(current_balance)
    comment: Current principal outstanding. This is the correct measure for portfolio
      exposure.
    display_name: Outstanding Balance
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2
    synonyms:
      - portfolio balance
      - exposure

  - name: original_principal
    expr: SUM(loan_amount)
    comment: Sum of original loan amounts. Do NOT use for current exposure - use outstanding_balance.
    display_name: Original Principal Funded
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: avg_loan_amount
    expr: SUM(loan_amount) / COUNT(1)
    display_name: Average Loan Amount
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: avg_interest_rate
    expr: AVG(interest_rate)
    comment: Already a percentage (13.02 means 13.02 percent). Do not multiply by
      100.
    display_name: Average Interest Rate (%)
    format:
      type: number
      decimal_places:
        type: exact
        places: 2

  - name: delinquent_loan_count
    expr: "COUNT(1) FILTER (WHERE loan_status IN ('DELINQUENT_30','DELINQUENT_60','DELINQUENT_90'))"
    display_name: Delinquent Loan Count

  - name: delinquent_balance
    expr: "SUM(current_balance) FILTER (WHERE loan_status IN ('DELINQUENT_30','DELINQUENT_60','DELINQUENT_90'))"
    display_name: Delinquent Balance
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: delinquency_rate_by_count
    expr: MEASURE(delinquent_loan_count) / MEASURE(loan_count)
    comment: Delinquent loans divided by total loans. Differs from the balance-weighted
      rate.
    display_name: Delinquency Rate (by Loan Count)
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2

  - name: delinquency_rate_by_balance
    expr: MEASURE(delinquent_balance) / MEASURE(outstanding_balance)
    comment: Delinquent balance divided by total outstanding balance. Balance-weighted.
    display_name: Delinquency Rate (by Balance)
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2

  - name: charged_off_loan_count
    expr: COUNT(1) FILTER (WHERE loan_status = 'CHARGED_OFF')
    display_name: Charged Off Loan Count

  - name: charge_off_rate
    expr: MEASURE(charged_off_loan_count) / MEASURE(loan_count)
    comment: Charged-off loans divided by total loans. Separate loss category from
      delinquency.
    display_name: Charge-Off Rate
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2

  - name: paid_off_loan_count
    expr: COUNT(1) FILTER (WHERE loan_status = 'PAID_OFF')
    display_name: Paid Off Loan Count

  - name: current_loan_count
    expr: COUNT(1) FILTER (WHERE loan_status = 'CURRENT')
    display_name: Current Loan Count

  - name: total_requested_amount
    expr: SUM(applications.requested_amount)
    comment: From the originating application. Excludes LN0000004 which has no matching
      application.
    display_name: Total Requested Amount
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 2

  - name: funded_to_requested_ratio
    expr: SUM(loan_amount) / SUM(applications.requested_amount)
    comment: Below 1.0 means loans are funded for less than applicants requested.
    display_name: Funded to Requested Ratio
    format:
      type: percentage
      decimal_places:
        type: exact
        places: 2
$$;
