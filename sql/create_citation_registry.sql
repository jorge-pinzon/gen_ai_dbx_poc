-- Run in Databricks SQL using an identity authorized for these policy sources.
-- This creates a NEW view; it does not change source documents or permissions.
-- Restrict SELECT to the app/retrieval identities that can read ALL these policies.
-- Use separate registries and app identities for different document entitlements.
-- IDs below must be returned by retrieval, never calculated by the language model.
CREATE OR REPLACE VIEW workspace.default.app_citation_registry AS
WITH source_chunks AS (
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
