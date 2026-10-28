-- Refresh the structured performance policy retrieval table
-- Generated from the trial workspace DDL (structure only, no data).
-- Run in order in the prod workspace with a serverless SQL warehouse.

-- Rebuilds perf_policy_retrieval from app_policy_chunks through perf_policy_candidates_v.
-- Only passages that match the citation registry exactly once are approved; the rest
-- are recorded in perf_policy_retrieval_rejects. Then sync perf_policy_retrieval_index.
TRUNCATE TABLE workspace.performance_test.perf_policy_retrieval;
INSERT INTO workspace.performance_test.perf_policy_retrieval
  (retrieval_id, chunk_text, document_id, document_version, chunk_id, document_title,
   page_start, page_end, domain, source_volume_path, source_chunk_id, refreshed_at)
SELECT retrieval_id, chunk_text, document_id, document_version, chunk_id, document_title,
       page_start, page_end, domain, source_volume_path, source_chunk_id, current_timestamp()
FROM workspace.performance_test.perf_policy_candidates_v
WHERE registry_id_match_count = 1 AND source_dup_count = 1;

INSERT INTO workspace.performance_test.perf_policy_retrieval_rejects
SELECT source_chunk_id, source_volume_path, page_start,
       CASE WHEN registry_match_count = 0 THEN 'no registry match'
            WHEN registry_id_match_count <> 1 THEN 'ambiguous registry match'
            ELSE 'duplicate source passage' END,
       registry_match_count, current_timestamp()
FROM workspace.performance_test.perf_policy_candidates_v
WHERE NOT (registry_id_match_count = 1 AND source_dup_count = 1);
