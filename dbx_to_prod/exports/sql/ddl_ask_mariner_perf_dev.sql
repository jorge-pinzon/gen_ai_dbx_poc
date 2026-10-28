-- DDL exported read-only from workspace.ask_mariner_perf_dev (structure only, no data)

-- MANAGED: workspace.ask_mariner_perf_dev.app_policy_chunks_version_test
CREATE TABLE workspace.ask_mariner_perf_dev.app_policy_chunks_version_test (
  chunk_id STRING COLLATE UTF8_BINARY,
  document_name STRING COLLATE UTF8_BINARY,
  source_volume_path STRING COLLATE UTF8_BINARY,
  page_start INT,
  chunk_text STRING COLLATE UTF8_BINARY)
USING delta
COMMENT 'DEV test fixture: copy of app_policy_chunks with page 2 edited to simulate a policy document update'
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.ask_mariner_perf_dev.bench_results
CREATE TABLE workspace.ask_mariner_perf_dev.bench_results (
  qid STRING COLLATE UTF8_BINARY,
  latency STRING COLLATE UTF8_BINARY,
  error STRING COLLATE UTF8_BINARY,
  approvals STRING COLLATE UTF8_BINARY,
  words STRING COLLATE UTF8_BINARY,
  quality STRING COLLATE UTF8_BINARY,
  critical_ok STRING COLLATE UTF8_BINARY,
  success_u30 STRING COLLATE UTF8_BINARY,
  answer STRING COLLATE UTF8_BINARY,
  concurrency STRING COLLATE UTF8_BINARY,
  label STRING COLLATE UTF8_BINARY,
  checks STRING COLLATE UTF8_BINARY,
  tool_calls STRING COLLATE UTF8_BINARY,
  ts STRING COLLATE UTF8_BINARY,
  timings STRING COLLATE UTF8_BINARY,
  run STRING COLLATE UTF8_BINARY)
USING delta
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- VIEW: workspace.ask_mariner_perf_dev.perf_citation_registry
CREATE VIEW ask_mariner_perf_dev.perf_citation_registry (
  document_id COMMENT 'Registry document_id: SHA2(domain, source path)',
  document_version COMMENT 'Registry document_version: SHA2 of all (page,text) of the document',
  chunk_id COMMENT 'Registry chunk_id: SHA2(version, page, text)',
  document_title COMMENT 'Registry document_title (exact value Flask validates)',
  domain,
  source_volume_path,
  page_start,
  page_end,
  chunk_text COMMENT 'Exact approved passage text (same bytes as registry chunk_text)',
  retrieval_id COMMENT 'SHA2-256 of document_id|document_version|chunk_id; index primary key')
COMMENT 'DEV: authoritative citation registry for the shared Employee Performance Policy documents only. Same IDs as workspace.default.app_citation_registry. Flask DATABRICKS_CITATION_REGISTRY_TABLE (dev).'
WITH SCHEMA COMPENSATION
AS SELECT document_id, document_version, chunk_id, document_title, domain, source_volume_path,
          page_start, page_end, chunk_text, retrieval_id
   FROM workspace.ask_mariner_perf_dev.perf_policy_retrieval;

-- VIEW: workspace.ask_mariner_perf_dev.perf_policy_candidates_v
CREATE VIEW ask_mariner_perf_dev.perf_policy_candidates_v (
  source_chunk_id,
  document_id,
  document_version,
  chunk_id,
  document_title,
  domain,
  source_volume_path,
  page_start,
  page_end,
  chunk_text,
  retrieval_id,
  registry_match_count,
  registry_id_match_count,
  source_dup_count)
COMMENT 'DEV: perf policy passages with registry-formula IDs and exact-match validation against workspace.default.app_citation_registry'
WITH SCHEMA COMPENSATION
AS WITH src AS (
  SELECT chunk_id AS source_chunk_id,
         'Employee Performance Policy' AS domain,
         document_name AS document_title,
         source_volume_path,
         TRY_CAST(page_start AS INT) AS page_start,
         CAST(chunk_text AS STRING) AS chunk_text
  FROM workspace.performance_test.app_policy_chunks
  WHERE source_volume_path LIKE '/Volumes/workspace/performance_test/data/%'   -- approved Volume root
),
valid AS (
  SELECT * FROM src
  WHERE page_start >= 1 AND chunk_text IS NOT NULL AND document_title IS NOT NULL AND source_volume_path IS NOT NULL
),
docs AS (
  SELECT domain, document_title, source_volume_path,
         SHA2(TO_JSON(NAMED_STRUCT('domain', domain, 'path', source_volume_path)), 256) AS document_id,
         SHA2(TO_JSON(SORT_ARRAY(COLLECT_SET(NAMED_STRUCT('page', page_start, 'text', chunk_text)))), 256) AS document_version
  FROM valid GROUP BY domain, document_title, source_volume_path
),
cand AS (
  SELECT v.source_chunk_id, d.document_id, d.document_version,
         SHA2(TO_JSON(NAMED_STRUCT('version', d.document_version, 'page', v.page_start, 'text', v.chunk_text)), 256) AS chunk_id,
         d.document_title, d.domain, d.source_volume_path, v.page_start, v.page_start AS page_end, v.chunk_text
  FROM docs d JOIN valid v
    ON d.domain = v.domain AND d.document_title = v.document_title AND d.source_volume_path = v.source_volume_path
)
SELECT c.*,
       SHA2(CONCAT_WS('|', c.document_id, c.document_version, c.chunk_id), 256) AS retrieval_id,
       (SELECT COUNT(*) FROM workspace.default.app_citation_registry r
         WHERE r.domain = c.domain AND r.source_volume_path = c.source_volume_path
           AND r.page_start = c.page_start AND r.chunk_text = c.chunk_text) AS registry_match_count,
       (SELECT COUNT(*) FROM workspace.default.app_citation_registry r
         WHERE r.domain = c.domain AND r.source_volume_path = c.source_volume_path
           AND r.page_start = c.page_start AND r.chunk_text = c.chunk_text
           AND r.document_id = c.document_id AND r.document_version = c.document_version
           AND r.chunk_id = c.chunk_id AND r.document_title = c.document_title) AS registry_id_match_count,
       (SELECT COUNT(*) FROM valid v2
         WHERE v2.source_volume_path = c.source_volume_path AND v2.page_start = c.page_start
           AND v2.chunk_text = c.chunk_text) AS source_dup_count
FROM cand c;

-- MANAGED: workspace.ask_mariner_perf_dev.perf_policy_retrieval
CREATE TABLE workspace.ask_mariner_perf_dev.perf_policy_retrieval (
  retrieval_id STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'SHA2-256 of document_id|document_version|chunk_id; index primary key',
  chunk_text STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Exact approved passage text (same bytes as registry chunk_text)',
  document_id STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry document_id: SHA2(domain, source path)',
  document_version STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry document_version: SHA2 of all (page,text) of the document',
  chunk_id STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry chunk_id: SHA2(version, page, text)',
  document_title STRING COLLATE UTF8_BINARY NOT NULL COMMENT 'Registry document_title (exact value Flask validates)',
  page_start INT NOT NULL,
  page_end INT NOT NULL,
  domain STRING COLLATE UTF8_BINARY NOT NULL,
  source_volume_path STRING COLLATE UTF8_BINARY NOT NULL,
  source_chunk_id STRING COLLATE UTF8_BINARY COMMENT 'Lineage: chunk_id in workspace.performance_test.app_policy_chunks',
  refreshed_at TIMESTAMP NOT NULL)
USING delta
COMMENT 'DEV: approved Employee Performance Policy passages with authoritative citation metadata for structured retrieval'
TBLPROPERTIES (
  'delta.enableChangeDataFeed' = 'true',
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.changeDataFeed' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.domainMetadata' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');

-- MANAGED: workspace.ask_mariner_perf_dev.perf_policy_retrieval_rejects
CREATE TABLE workspace.ask_mariner_perf_dev.perf_policy_retrieval_rejects (
  source_chunk_id STRING COLLATE UTF8_BINARY,
  source_volume_path STRING COLLATE UTF8_BINARY,
  page_start INT,
  reason STRING COLLATE UTF8_BINARY,
  registry_match_count BIGINT,
  rejected_at TIMESTAMP)
USING delta
COMMENT 'DEV: source chunks rejected from structured retrieval (missing/ambiguous registry match, invalid page, out-of-scope path)'
TBLPROPERTIES (
  'delta.enableDeletionVectors' = 'true',
  'delta.enableRowTracking' = 'true',
  'delta.feature.appendOnly' = 'supported',
  'delta.feature.deletionVectors' = 'supported',
  'delta.feature.domainMetadata' = 'supported',
  'delta.feature.invariants' = 'supported',
  'delta.feature.rowTracking' = 'supported',
  'delta.minReaderVersion' = '3',
  'delta.minWriterVersion' = '7',
  'delta.parquet.compression.codec' = 'zstd',
  'delta.parquet.format.version' = '2.12.0',
  'delta.parquet.format.version.afe.internal' = '2.12.0');
