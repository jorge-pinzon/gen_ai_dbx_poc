# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Parse documents and build chunk tables (prod)
# MAGIC Same SQL as the upload tool (`simple_upload/app.py`), including the fix for moved or renamed PDFs.
# MAGIC Run after the PDFs are in the volumes (five with the Coaching360 BRD). Re-run any time documents change, then run notebook 04 to sync the indexes.
# MAGIC Cost: `ai_parse_document` runs once per new PDF; unchanged or moved PDFs reuse the earlier parse.

# COMMAND ----------

# MAGIC %run ./00_config

# COMMAND ----------

import time

STEPS = {}

# COMMAND ----------

STEPS['branch_operations'] = [
    ('Parse new, changed or moved PDFs', r'''
        INSERT INTO workspace.default.branch_operations_parsed_documents
            (document_id, domain, source_path, file_name, file_size_bytes,
             source_modified_at, parsed_content, parsed_at)
        WITH files AS (
            SELECT path, content, length, modificationTime, sha2(content, 256) AS document_id
            FROM read_files('/Volumes/workspace/default/branch_operations_docs/', format => 'binaryFile', pathGlobFilter => '*.pdf', recursiveFileLookup => 'true')
        ),
        known AS (
            SELECT document_id, parsed_content FROM workspace.default.branch_operations_parsed_documents
            QUALIFY row_number() OVER (PARTITION BY document_id ORDER BY parsed_at DESC) = 1
        )
        SELECT f.document_id, 'branch_operations', f.path, regexp_extract(f.path, '([^/]+)$', 1),
               f.length, f.modificationTime,
               CASE WHEN k.document_id IS NOT NULL THEN k.parsed_content
                    ELSE ai_parse_document(f.content, map('version', '2.0')) END,
               current_timestamp()
        FROM files AS f LEFT JOIN known AS k ON k.document_id = f.document_id
        WHERE NOT EXISTS (
            SELECT 1 FROM workspace.default.branch_operations_parsed_documents AS p
            WHERE p.document_id = f.document_id AND p.source_path = f.path
        )
        '''),
    ('Extract document elements', r'''
        CREATE OR REPLACE TABLE workspace.default.branch_operations_document_elements
        USING DELTA
        AS
        WITH current_paths AS (
            SELECT * FROM workspace.default.branch_operations_parsed_documents
            WHERE source_path IN (SELECT path FROM read_files('/Volumes/workspace/default/branch_operations_docs/', format => 'binaryFile', pathGlobFilter => '*.pdf', recursiveFileLookup => 'true'))
            QUALIFY row_number() OVER (PARTITION BY source_path ORDER BY parsed_at DESC) = 1
        ),
        current_documents AS (
            SELECT * FROM current_paths
            QUALIFY row_number() OVER (
                PARTITION BY document_id ORDER BY source_modified_at DESC, parsed_at DESC) = 1
        ),
        extracted AS (
            SELECT
                p.document_id, p.domain, p.source_path, p.file_name,
                regexp_replace(p.file_name, '(?i)\\.pdf$', '') AS document_title,
                e.pos AS element_position,
                try_variant_get(e.value, '$.id', 'bigint') AS element_id,
                try_variant_get(e.value, '$.type', 'string') AS element_type,
                try_variant_get(e.value, '$.content', 'string') AS raw_content,
                try_variant_get(e.value, '$.description', 'string') AS figure_description,
                try_variant_get(e.value, '$.confidence', 'double') AS confidence,
                try_variant_get(e.value, '$.bbox[0].page_id', 'int') AS page_id,
                e.value:bbox AS bbox,
                p.parsed_at
            FROM current_documents AS p,
            LATERAL variant_explode(p.parsed_content:document.elements) AS e
            WHERE p.parsed_content:error_status IS NULL
               OR is_variant_null(p.parsed_content:error_status)
        ),
        cleaned AS (
            SELECT *,
                trim(regexp_replace(
                    CASE WHEN element_type = 'figure' THEN coalesce(figure_description, raw_content)
                         ELSE raw_content END,
                    '\\s+', ' '
                )) AS cleaned_content
            FROM extracted
        )
        SELECT
            document_id, domain, source_path, file_name, document_title,
            element_position, element_id, element_type, raw_content, cleaned_content,
            confidence, page_id, page_id + 1 AS page_number, bbox, parsed_at,
            CASE
                WHEN element_type IN ('text','table','title','caption','section_header','footnote','figure')
                AND cleaned_content IS NOT NULL AND length(cleaned_content) > 1
                AND upper(cleaned_content) NOT IN ('MARINER FINANCE', 'N')
                THEN true ELSE false
            END AS is_retrievable
        FROM cleaned
        WHERE raw_content IS NOT NULL OR figure_description IS NOT NULL
        '''),
    ('Clear chunk table', r'''TRUNCATE TABLE workspace.default.branch_operations_chunks'''),
    ('Rebuild chunks', r'''
        INSERT INTO workspace.default.branch_operations_chunks
        WITH ordered_elements AS (
            SELECT *,
                sum(length(cleaned_content) + 2) OVER (
                    PARTITION BY document_id, page_number
                    ORDER BY element_position
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_chars
            FROM workspace.default.branch_operations_document_elements
            WHERE is_retrievable = true AND page_number IS NOT NULL
        ),
        bucketed AS (
            SELECT *, cast(floor((cumulative_chars - 1) / 3500) AS int) AS chunk_number
            FROM ordered_elements
        ),
        aggregated AS (
            SELECT
                document_id, domain, source_path,
                regexp_replace(source_path, '^dbfs:', '') AS volume_path,
                file_name, document_title, page_number, chunk_number,
                min(element_position) AS first_element_position,
                max(element_position) AS last_element_position,
                min(confidence) AS minimum_confidence,
                concat_ws('\n\n',
                    transform(array_sort(collect_list(
                        named_struct('element_position', element_position, 'content', cleaned_content)
                    )), x -> x.content)
                ) AS chunk_text
            FROM bucketed
            GROUP BY document_id, domain, source_path, file_name, document_title, page_number, chunk_number
        )
        SELECT
            sha2(concat_ws('||', document_id, cast(page_number AS string), cast(chunk_number AS string)), 256) AS chunk_id,
            document_id, domain, source_path, volume_path, file_name, document_title,
            page_number AS page_start, page_number AS page_end,
            chunk_number + 1 AS page_chunk_number,
            first_element_position, last_element_position, minimum_confidence,
            chunk_text,
            concat('Document: ', document_title, '\nPage: ', cast(page_number AS string), '\n\n', chunk_text) AS embedding_text,
            length(chunk_text) AS character_count,
            concat(document_title, ' - page ', cast(page_number AS string)) AS citation_label,
            current_timestamp() AS created_at
        FROM aggregated
        WHERE length(trim(chunk_text)) > 0
        '''),
]

# COMMAND ----------

STEPS['employee_handbook'] = [
    ('Parse new, changed or moved PDFs', r'''
        INSERT INTO workspace.default.employee_handbook_parsed_documents
            (document_id, domain, source_path, file_name, file_size_bytes,
             source_modified_at, parsed_content, parsed_at)
        WITH files AS (
            SELECT path, content, length, modificationTime, sha2(content, 256) AS document_id
            FROM read_files('/Volumes/workspace/default/employee_handbook_docs/', format => 'binaryFile', pathGlobFilter => '*.pdf', recursiveFileLookup => 'true')
        ),
        known AS (
            SELECT document_id, parsed_content FROM workspace.default.employee_handbook_parsed_documents
            QUALIFY row_number() OVER (PARTITION BY document_id ORDER BY parsed_at DESC) = 1
        )
        SELECT f.document_id, 'employee_handbook', f.path, regexp_extract(f.path, '([^/]+)$', 1),
               f.length, f.modificationTime,
               CASE WHEN k.document_id IS NOT NULL THEN k.parsed_content
                    ELSE ai_parse_document(f.content, map('version', '2.0')) END,
               current_timestamp()
        FROM files AS f LEFT JOIN known AS k ON k.document_id = f.document_id
        WHERE NOT EXISTS (
            SELECT 1 FROM workspace.default.employee_handbook_parsed_documents AS p
            WHERE p.document_id = f.document_id AND p.source_path = f.path
        )
        '''),
    ('Extract document elements', r'''
        CREATE OR REPLACE TABLE workspace.default.employee_handbook_document_elements
        USING DELTA
        AS
        WITH current_paths AS (
            SELECT * FROM workspace.default.employee_handbook_parsed_documents
            WHERE source_path IN (SELECT path FROM read_files('/Volumes/workspace/default/employee_handbook_docs/', format => 'binaryFile', pathGlobFilter => '*.pdf', recursiveFileLookup => 'true'))
            QUALIFY row_number() OVER (PARTITION BY source_path ORDER BY parsed_at DESC) = 1
        ),
        current_documents AS (
            SELECT * FROM current_paths
            QUALIFY row_number() OVER (
                PARTITION BY document_id ORDER BY source_modified_at DESC, parsed_at DESC) = 1
        ),
        extracted AS (
            SELECT
                p.document_id, p.domain, p.source_path, p.file_name,
                regexp_replace(p.file_name, '(?i)\\.pdf$', '') AS document_title,
                e.pos AS element_position,
                try_variant_get(e.value, '$.id', 'bigint') AS element_id,
                try_variant_get(e.value, '$.type', 'string') AS element_type,
                try_variant_get(e.value, '$.content', 'string') AS raw_content,
                try_variant_get(e.value, '$.description', 'string') AS figure_description,
                try_variant_get(e.value, '$.confidence', 'double') AS confidence,
                try_variant_get(e.value, '$.bbox[0].page_id', 'int') AS page_id,
                e.value:bbox AS bbox,
                p.parsed_at
            FROM current_documents AS p,
            LATERAL variant_explode(p.parsed_content:document.elements) AS e
            WHERE p.parsed_content:error_status IS NULL
               OR is_variant_null(p.parsed_content:error_status)
        ),
        cleaned AS (
            SELECT *,
                trim(regexp_replace(
                    CASE WHEN element_type = 'figure' THEN coalesce(figure_description, raw_content)
                         ELSE raw_content END,
                    '\\s+', ' '
                )) AS cleaned_content
            FROM extracted
        )
        SELECT
            document_id, domain, source_path, file_name, document_title,
            element_position, element_id, element_type, raw_content, cleaned_content,
            confidence, page_id, page_id + 1 AS page_number, bbox, parsed_at,
            CASE
                WHEN element_type IN ('text','table','title','caption','section_header','footnote','figure')
                AND cleaned_content IS NOT NULL AND length(cleaned_content) > 1
                AND upper(cleaned_content) NOT IN ('MARINER FINANCE', 'N')
                THEN true ELSE false
            END AS is_retrievable
        FROM cleaned
        WHERE raw_content IS NOT NULL OR figure_description IS NOT NULL
        '''),
    ('Clear chunk table', r'''TRUNCATE TABLE workspace.default.employee_handbook_chunks'''),
    ('Rebuild chunks', r'''
        INSERT INTO workspace.default.employee_handbook_chunks
        WITH ordered_elements AS (
            SELECT *,
                sum(length(cleaned_content) + 2) OVER (
                    PARTITION BY document_id, page_number
                    ORDER BY element_position
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_chars
            FROM workspace.default.employee_handbook_document_elements
            WHERE is_retrievable = true AND page_number IS NOT NULL
        ),
        bucketed AS (
            SELECT *, cast(floor((cumulative_chars - 1) / 3500) AS int) AS chunk_number
            FROM ordered_elements
        ),
        aggregated AS (
            SELECT
                document_id, domain, source_path,
                regexp_replace(source_path, '^dbfs:', '') AS volume_path,
                file_name, document_title, page_number, chunk_number,
                min(element_position) AS first_element_position,
                max(element_position) AS last_element_position,
                min(confidence) AS minimum_confidence,
                concat_ws('\n\n',
                    transform(array_sort(collect_list(
                        named_struct('element_position', element_position, 'content', cleaned_content)
                    )), x -> x.content)
                ) AS chunk_text
            FROM bucketed
            GROUP BY document_id, domain, source_path, file_name, document_title, page_number, chunk_number
        )
        SELECT
            sha2(concat_ws('||', document_id, cast(page_number AS string), cast(chunk_number AS string)), 256) AS chunk_id,
            document_id, domain, source_path, volume_path, file_name, document_title,
            page_number AS page_start, page_number AS page_end,
            chunk_number + 1 AS page_chunk_number,
            first_element_position, last_element_position, minimum_confidence,
            chunk_text,
            concat('Document: ', document_title, '\nPage: ', cast(page_number AS string), '\n\n', chunk_text) AS embedding_text,
            length(chunk_text) AS character_count,
            concat(document_title, ' - page ', cast(page_number AS string)) AS citation_label,
            current_timestamp() AS created_at
        FROM aggregated
        WHERE length(trim(chunk_text)) > 0
        '''),
]

# COMMAND ----------

STEPS['benefits'] = [
    ('Parse new, changed or moved PDFs', r'''
        INSERT INTO workspace.default.benefits_parsed_documents
            (document_id, domain, source_path, file_name, file_size_bytes,
             source_modified_at, parsed_content, parsed_at)
        WITH files AS (
            SELECT path, content, length, modificationTime, sha2(content, 256) AS document_id
            FROM read_files('/Volumes/workspace/default/benefits_docs/', format => 'binaryFile', pathGlobFilter => '*.pdf', recursiveFileLookup => 'true')
        ),
        known AS (
            SELECT document_id, parsed_content FROM workspace.default.benefits_parsed_documents
            QUALIFY row_number() OVER (PARTITION BY document_id ORDER BY parsed_at DESC) = 1
        )
        SELECT f.document_id, 'benefits', f.path, regexp_extract(f.path, '([^/]+)$', 1),
               f.length, f.modificationTime,
               CASE WHEN k.document_id IS NOT NULL THEN k.parsed_content
                    ELSE ai_parse_document(f.content, map('version', '2.0')) END,
               current_timestamp()
        FROM files AS f LEFT JOIN known AS k ON k.document_id = f.document_id
        WHERE NOT EXISTS (
            SELECT 1 FROM workspace.default.benefits_parsed_documents AS p
            WHERE p.document_id = f.document_id AND p.source_path = f.path
        )
        '''),
    ('Extract document elements', r'''
        CREATE OR REPLACE TABLE workspace.default.benefits_document_elements
        USING DELTA
        AS
        WITH current_paths AS (
            SELECT * FROM workspace.default.benefits_parsed_documents
            WHERE source_path IN (SELECT path FROM read_files('/Volumes/workspace/default/benefits_docs/', format => 'binaryFile', pathGlobFilter => '*.pdf', recursiveFileLookup => 'true'))
            QUALIFY row_number() OVER (PARTITION BY source_path ORDER BY parsed_at DESC) = 1
        ),
        current_documents AS (
            SELECT * FROM current_paths
            QUALIFY row_number() OVER (
                PARTITION BY document_id ORDER BY source_modified_at DESC, parsed_at DESC) = 1
        ),
        extracted AS (
            SELECT
                p.document_id, p.domain, p.source_path, p.file_name,
                regexp_replace(p.file_name, '(?i)\\.pdf$', '') AS document_title,
                e.pos AS element_position,
                try_variant_get(e.value, '$.id', 'bigint') AS element_id,
                try_variant_get(e.value, '$.type', 'string') AS element_type,
                try_variant_get(e.value, '$.content', 'string') AS raw_content,
                try_variant_get(e.value, '$.description', 'string') AS figure_description,
                try_variant_get(e.value, '$.confidence', 'double') AS confidence,
                try_variant_get(e.value, '$.bbox[0].page_id', 'int') AS page_id,
                e.value:bbox AS bbox,
                p.parsed_at
            FROM current_documents AS p,
            LATERAL variant_explode(p.parsed_content:document.elements) AS e
            WHERE p.parsed_content:error_status IS NULL
               OR is_variant_null(p.parsed_content:error_status)
        ),
        cleaned AS (
            SELECT *,
                trim(regexp_replace(
                    CASE WHEN element_type = 'figure' THEN coalesce(figure_description, raw_content)
                         ELSE raw_content END,
                    '\\s+', ' '
                )) AS cleaned_content
            FROM extracted
        )
        SELECT
            document_id, domain, source_path, file_name, document_title,
            element_position, element_id, element_type, raw_content, cleaned_content,
            confidence, page_id, page_id + 1 AS page_number, bbox, parsed_at,
            CASE
                WHEN element_type IN ('text','table','title','caption','section_header','footnote','figure')
                AND cleaned_content IS NOT NULL AND length(cleaned_content) > 1
                AND upper(cleaned_content) NOT IN ('MARINER FINANCE', 'N')
                THEN true ELSE false
            END AS is_retrievable
        FROM cleaned
        WHERE raw_content IS NOT NULL OR figure_description IS NOT NULL
        '''),
    ('Clear chunk table', r'''TRUNCATE TABLE workspace.default.benefits_chunks'''),
    ('Rebuild chunks', r'''
        INSERT INTO workspace.default.benefits_chunks
        WITH ordered_elements AS (
            SELECT *,
                sum(length(cleaned_content) + 2) OVER (
                    PARTITION BY document_id, page_number
                    ORDER BY element_position
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_chars
            FROM workspace.default.benefits_document_elements
            WHERE is_retrievable = true AND page_number IS NOT NULL
        ),
        bucketed AS (
            SELECT *, cast(floor((cumulative_chars - 1) / 3500) AS int) AS chunk_number
            FROM ordered_elements
        ),
        aggregated AS (
            SELECT
                document_id, domain, source_path,
                regexp_replace(source_path, '^dbfs:', '') AS volume_path,
                file_name, document_title, page_number, chunk_number,
                min(element_position) AS first_element_position,
                max(element_position) AS last_element_position,
                min(confidence) AS minimum_confidence,
                concat_ws('\n\n',
                    transform(array_sort(collect_list(
                        named_struct('element_position', element_position, 'content', cleaned_content)
                    )), x -> x.content)
                ) AS chunk_text
            FROM bucketed
            GROUP BY document_id, domain, source_path, file_name, document_title, page_number, chunk_number
        )
        SELECT
            sha2(concat_ws('||', document_id, cast(page_number AS string), cast(chunk_number AS string)), 256) AS chunk_id,
            document_id, domain, source_path, volume_path, file_name, document_title,
            page_number AS page_start, page_number AS page_end,
            chunk_number + 1 AS page_chunk_number,
            first_element_position, last_element_position, minimum_confidence,
            chunk_text,
            concat('Document: ', document_title, '\nPage: ', cast(page_number AS string), '\n\n', chunk_text) AS embedding_text,
            length(chunk_text) AS character_count,
            concat(document_title, ' - page ', cast(page_number AS string)) AS citation_label,
            current_timestamp() AS created_at
        FROM aggregated
        WHERE length(trim(chunk_text)) > 0
        '''),
]

# COMMAND ----------

STEPS['performance_policy'] = [
    ('Parse PDFs and rebuild page chunks', r'''
        INSERT OVERWRITE workspace.performance_test.app_policy_chunks
            (chunk_id, document_name, document_version, chunk_to_embed, chunk_text,
             chunk_position, source_volume_path, processed_timestamp, document_title,
             page_start, page_end)
        WITH documents AS (
            SELECT regexp_replace(path, '^dbfs:', '') AS source_volume_path,
                   regexp_extract(path, '([^/]+)$', 1) AS document_name,
                   ai_parse_document(content, map('version', '2.0')) AS parsed_content
            FROM read_files('/Volumes/workspace/performance_test/data/', format => 'binaryFile', pathGlobFilter => '*.pdf', recursiveFileLookup => 'true')
        ),
        page_elements AS (
            SELECT source_volume_path, document_name, elem_index,
                try_cast(elem:bbox AS ARRAY<VARIANT>)[0]:page_id::INT + 1 AS page_num,
                try_cast(elem:content AS STRING) AS content
            FROM documents
            LATERAL VIEW posexplode(try_cast(parsed_content:document:elements AS ARRAY<VARIANT>)) AS elem_index, elem
            WHERE try_cast(elem:content AS STRING) IS NOT NULL
              AND length(trim(try_cast(elem:content AS STRING))) > 0
              AND try_cast(elem:type AS STRING) NOT IN ('page_number')
        ),
        page_text AS (
            SELECT source_volume_path, document_name, page_num,
                concat_ws('\n\n', transform(array_sort(collect_list(
                    named_struct('elem_index', elem_index, 'content', content)
                )), x -> x.content)) AS page_content
            FROM page_elements
            GROUP BY source_volume_path, document_name, page_num
        ),
        chunked AS (
            SELECT *, ROW_NUMBER() OVER (PARTITION BY source_volume_path ORDER BY page_num) - 1 AS chunk_position
            FROM page_text
            WHERE length(trim(page_content)) > 0
        )
        SELECT
            sha2(concat_ws('|', source_volume_path, CAST(page_num AS STRING),
                           CAST(chunk_position AS STRING), page_content), 256),
            document_name, '0.1', page_content, page_content, chunk_position,
            source_volume_path, current_timestamp(),
            CASE WHEN document_name = 'INSTRUCTIONS_PERFORMANCE.pdf' THEN 'Employee Performance Policy'
                 ELSE regexp_replace(document_name, '(?i)\\.pdf$', '') END,
            page_num, page_num
        FROM chunked
        '''),
    ('Refresh structured retrieval (sql/08)', None),
]

# COMMAND ----------

# Coaching360 BRD: the same four steps as the other domains, generated for its volume
# (coaching360/build_agents.py; identical to the upload tool's Coaching360 domain).
if COACHING360:
    import json
    STEPS['coaching360'] = [tuple(step) for step in json.load(open(f"{ROOT}/agents/agent_bricks/coaching360/brd_pipeline_steps.json"))]

# COMMAND ----------

# Keep 90 days of change history so a TRIGGERED index sync can always catch up.
for table in [c["chunks"] for c in DOMAINS.values()] + [f"{PERF_SCHEMA}.app_policy_chunks", f"{PERF_SCHEMA}.perf_policy_retrieval"]:
    spark.sql(f"""ALTER TABLE {table} SET TBLPROPERTIES ('delta.enableChangeDataFeed' = 'true',
              'delta.deletedFileRetentionDuration' = 'interval 90 days', 'delta.logRetentionDuration' = 'interval 90 days')""")

for domain, steps in STEPS.items():
    print(f"== {domain}")
    for label, statement in steps:
        started = time.time()
        if statement is None:
            run_sql_file("sql/08_refresh_perf_policy_retrieval.sql")
        else:
            spark.sql(statement)
        print(f"   {label:45} {time.time() - started:5.0f}s")

# COMMAND ----------

# MAGIC %md ## Check chunk counts against the trial workspace

# COMMAND ----------

checks = [(c["chunks"], c["expected_chunks"]) for c in DOMAINS.values()] + [
    (f"{PERF_SCHEMA}.app_policy_chunks", 9), (f"{PERF_SCHEMA}.perf_policy_retrieval", 9)]
for table, expected in checks:
    rows = spark.table(table).count()
    duplicates = rows - spark.table(table).select("chunk_id" if "retrieval" not in table else "retrieval_id").distinct().count()
    if expected is None:
        note = "" if rows else "  <-- no rows"
    else:
        note = "" if rows == expected else f"  (trial had {expected}; different PDFs or parser version can change this)"
    print(f"{table:55} {rows:4} rows, {duplicates} duplicate ids{note}")
display(spark.sql(f"SELECT domain, COUNT(*) AS passages FROM {DOCS_SCHEMA}.app_citation_registry GROUP BY 1 ORDER BY 1"))
