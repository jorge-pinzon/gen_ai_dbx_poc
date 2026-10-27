"""Minimal PDF uploader and vector index refresh for the document volumes.

Reads credentials and VOLUME_CATALOGS_JSON from the repo-root .env, writes
files with the Databricks Files API, and rebuilds the chunk tables and Vector
Search indexes that the Knowledge Assistants read from. Run with:
python simple_upload/app.py
"""

import json
import os
import threading
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
from flask import Flask, redirect, render_template_string, request, url_for

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def load_env(path):
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip().strip("'\"")
    return {**values, **os.environ}


env = load_env(ENV_FILE)
HOST = env["DATABRICKS_HOST"].rstrip("/")
WAREHOUSE_ID = env.get("DATABRICKS_WAREHOUSE_ID")
VOLUMES = {v["id"]: v for v in json.loads(env["VOLUME_CATALOGS_JSON"])}
DEFAULT_VOLUME = "branch-operations"

# Same pipeline as the RAG_Pipeline_Auto_Refresh notebook, but pointing at the
# indexes the Knowledge Assistants actually use.
PIPELINES = {
    "branch_operations": {
        "label": "Branch Operations (mariner-policy-assistant)",
        "volume": "/Volumes/workspace/default/branch_operations_docs/",
        "index": "workspace.default.branch_ops_index",
        "chunks": "workspace.default.branch_operations_chunks", "embedding_col": "embedding_text",
        "file_col": "file_name", "time_col": "created_at",
    },
    "employee_handbook": {
        "label": "Employee Handbook (mariner-handbook-assistant)",
        "volume": "/Volumes/workspace/default/employee_handbook_docs/",
        "index": "workspace.default.employee_handbook_new_index",
        "chunks": "workspace.default.employee_handbook_chunks", "embedding_col": "embedding_text",
        "file_col": "file_name", "time_col": "created_at",
    },
    "benefits": {
        "label": "Employee Benefits (mariner-benefits-assistant)",
        "volume": "/Volumes/workspace/default/benefits_docs/",
        "index": "workspace.default.benefits_new_index",
        "chunks": "workspace.default.benefits_chunks", "embedding_col": "embedding_text",
        "file_col": "file_name", "time_col": "created_at",
    },
    "coaching360": {
        "label": "Coaching360 Guide (mariner-coaching360-guide)",
        "volume": "/Volumes/workspace/coaching360demo/coaching360_docs/",
        "index": "workspace.default.coaching360_index",
        "chunks": "workspace.default.coaching360_chunks", "embedding_col": "embedding_text",
        "file_col": "file_name", "time_col": "created_at",
    },
    "performance": {
        "label": "Employee Performance (mariner-performance-assistant)",
        "volume": "/Volumes/workspace/performance_test/data/",
        "index": "workspace.performance_test.performance_index",
        "chunks": "workspace.performance_test.app_policy_chunks", "embedding_col": "chunk_to_embed",
        "file_col": "document_name", "time_col": "processed_timestamp",
    },
}
# Used to recreate an index when it no longer exists.
INDEX_ENDPOINT = "mariner-bot-endpoint"
EMBEDDING_MODEL = "databricks-qwen3-embedding-0-6b"
RUNS = {}  # domain -> {"running": bool, "started": str, "steps": [[label, state, detail]]}


def access_token(scope):
    if env.get("DATABRICKS_TOKEN"):
        return env["DATABRICKS_TOKEN"]
    response = requests.post(
        f"{HOST}/oidc/v1/token",
        auth=(env["DATABRICKS_CLIENT_ID"], env["DATABRICKS_CLIENT_SECRET"]),
        data={"grant_type": "client_credentials", "scope": scope},
        timeout=30,
    )
    if not response.ok:
        raise RuntimeError(f"Token for scope '{scope}' refused: {response.text[:300]}")
    return response.json()["access_token"]


def databricks(method, path, scope, **kwargs):
    response = requests.request(
        method,
        f"{HOST}{path}",
        headers={"Authorization": f"Bearer {access_token(scope)}"},
        timeout=60,
        **kwargs,
    )
    if not response.ok:
        raise RuntimeError(f"{response.status_code}: {response.text[:500]}")
    return response.json() if response.content else {}


def upload_to_volume(volume_path, filename, data):
    target = f"{volume_path.rstrip('/')}/{filename}"
    response = requests.put(
        f"{HOST}/api/2.0/fs/files{quote(target)}",
        params={"overwrite": "true"},
        headers={"Authorization": f"Bearer {access_token('files')}",
                 "Content-Type": "application/octet-stream"},
        data=data,
        timeout=300,
    )
    if not response.ok:
        raise RuntimeError(f"{response.status_code}: {response.text[:500]}")
    return target


def run_sql(statement):
    """Run a statement on the SQL warehouse and wait for it, however long parsing takes."""
    result = databricks("POST", "/api/2.0/sql/statements", "sql", json={
        "warehouse_id": WAREHOUSE_ID, "statement": statement,
        "wait_timeout": "30s", "on_wait_timeout": "CONTINUE",
    })
    while result["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(5)
        result = databricks("GET", f"/api/2.0/sql/statements/{result['statement_id']}", "sql")
    if result["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(json.dumps(result["status"].get("error", result["status"]))[:500])
    return result


def performance_steps(volume_files):
    # Mirrors the "Compare KA Agent Responses" notebook: one chunk per page in a
    # different table layout, re-parsing every PDF in the folder on each run.
    return [
        ("Parse PDFs and rebuild page chunks", f"""
        INSERT OVERWRITE workspace.performance_test.app_policy_chunks
            (chunk_id, document_name, document_version, chunk_to_embed, chunk_text,
             chunk_position, source_volume_path, processed_timestamp, document_title,
             page_start, page_end)
        WITH documents AS (
            SELECT regexp_replace(path, '^dbfs:', '') AS source_volume_path,
                   regexp_extract(path, '([^/]+)$', 1) AS document_name,
                   ai_parse_document(content, map('version', '2.0')) AS parsed_content
            FROM {volume_files}
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
                concat_ws('\\n\\n', transform(array_sort(collect_list(
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
                 ELSE regexp_replace(document_name, '(?i)\\\\.pdf$', '') END,
            page_num, page_num
        FROM chunked
        """),
    ]


def pipeline_steps(domain, config):
    parsed = f"workspace.default.{domain}_parsed_documents"
    elements = f"workspace.default.{domain}_document_elements"
    chunks = f"workspace.default.{domain}_chunks"
    volume_files = (f"read_files('{config['volume']}', format => 'binaryFile', "
                    "pathGlobFilter => '*.pdf', recursiveFileLookup => 'true')")
    if domain == "performance":
        return performance_steps(volume_files)
    return [
        # A file is new when its content or its location is new. A moved or
        # renamed PDF keeps its earlier parse, so it is not parsed again and its
        # chunks (and chunk ids) stay the same; only the path changes.
        ("Parse new, changed or moved PDFs", f"""
        INSERT INTO {parsed}
            (document_id, domain, source_path, file_name, file_size_bytes,
             source_modified_at, parsed_content, parsed_at)
        WITH files AS (
            SELECT path, content, length, modificationTime, sha2(content, 256) AS document_id
            FROM {volume_files}
        ),
        known AS (
            SELECT document_id, parsed_content FROM {parsed}
            QUALIFY row_number() OVER (PARTITION BY document_id ORDER BY parsed_at DESC) = 1
        )
        SELECT f.document_id, '{domain}', f.path, regexp_extract(f.path, '([^/]+)$', 1),
               f.length, f.modificationTime,
               CASE WHEN k.document_id IS NOT NULL THEN k.parsed_content
                    ELSE ai_parse_document(f.content, map('version', '2.0')) END,
               current_timestamp()
        FROM files AS f LEFT JOIN known AS k ON k.document_id = f.document_id
        WHERE NOT EXISTS (
            SELECT 1 FROM {parsed} AS p
            WHERE p.document_id = f.document_id AND p.source_path = f.path
        )
        """),
        # Uses only the latest parse of each file still in the volume, so
        # replaced, moved or deleted PDFs drop out of the old location. If the
        # same PDF sits in two folders, only the newest copy is used, because
        # chunk ids come from the content and must stay unique in the index.
        ("Extract document elements", f"""
        CREATE OR REPLACE TABLE {elements}
        USING DELTA
        AS
        WITH current_paths AS (
            SELECT * FROM {parsed}
            WHERE source_path IN (SELECT path FROM {volume_files})
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
                regexp_replace(p.file_name, '(?i)\\\\.pdf$', '') AS document_title,
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
                    '\\\\s+', ' '
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
        """),
        # Truncate + insert keeps the Change Data Feed the index sync relies on.
        ("Clear chunk table", f"TRUNCATE TABLE {chunks}"),
        ("Rebuild chunks", f"""
        INSERT INTO {chunks}
        WITH ordered_elements AS (
            SELECT *,
                sum(length(cleaned_content) + 2) OVER (
                    PARTITION BY document_id, page_number
                    ORDER BY element_position
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS cumulative_chars
            FROM {elements}
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
                concat_ws('\\n\\n',
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
            concat('Document: ', document_title, '\\nPage: ', cast(page_number AS string), '\\n\\n', chunk_text) AS embedding_text,
            length(chunk_text) AS character_count,
            concat(document_title, ' - page ', cast(page_number AS string)) AS citation_label,
            current_timestamp() AS created_at
        FROM aggregated
        WHERE length(trim(chunk_text)) > 0
        """),
    ]


def refresh_index(domain):
    config, run = PIPELINES[domain], RUNS[domain]

    def step(label, action):
        run["steps"].append([label, "running", ""])
        started = time.time()
        action()
        run["steps"][-1][1:] = ["done", f"{time.time() - started:.0f}s"]

    try:
        # Long retention keeps the change history the index sync reads, even
        # when weeks pass between updates.
        step("Keep change history 90 days", lambda: run_sql(
            f"ALTER TABLE {config['chunks']} SET TBLPROPERTIES ("
            "'delta.enableChangeDataFeed' = 'true', "
            "'delta.deletedFileRetentionDuration' = 'interval 90 days', "
            "'delta.logRetentionDuration' = 'interval 90 days')"))
        for label, statement in pipeline_steps(domain, config):
            step(label, lambda statement=statement: run_sql(statement))
        try:
            step("Sync vector index", lambda: sync_index(config["index"]))
        except Exception as error:
            if not needs_recreate(error):
                raise
            run["steps"][-1][1:] = ["warn", f"Sync cannot recover, recreating the index: {error}"]
            step("Recreate vector index", lambda: recreate_index(config))
    except Exception as error:
        run["steps"][-1][1:] = ["failed", str(error)]
    finally:
        run["running"] = False


def needs_recreate(error):
    message = str(error)
    return "OUT_OF_RETENTION" in message or message.startswith("404")


def recreate_index(config):
    """Delete and recreate a Delta Sync index, then wait until every chunk is indexed."""
    name = config["index"]
    path = f"/api/2.0/vector-search/indexes/{name}"
    try:
        current = databricks("GET", path, "vector-search")
    except RuntimeError as error:
        if not str(error).startswith("404"):
            raise
        current = None
    if current:
        spec = current["delta_sync_index_spec"]
        body = {"name": name, "endpoint_name": current["endpoint_name"],
                "primary_key": current["primary_key"], "index_type": "DELTA_SYNC",
                "delta_sync_index_spec": {k: spec[k] for k in
                                          ("source_table", "embedding_source_columns", "pipeline_type")}}
        databricks("DELETE", path, "vector-search")
        while True:
            try:
                databricks("GET", path, "vector-search")
                time.sleep(5)
            except RuntimeError:
                break
    else:
        body = {"name": name, "endpoint_name": INDEX_ENDPOINT, "primary_key": "chunk_id",
                "index_type": "DELTA_SYNC",
                "delta_sync_index_spec": {
                    "source_table": config["chunks"], "pipeline_type": "TRIGGERED",
                    "embedding_source_columns": [{"name": config["embedding_col"],
                                                  "embedding_model_endpoint_name": EMBEDDING_MODEL}]}}

    for attempt in range(12):
        try:
            databricks("POST", "/api/2.0/vector-search/indexes", "vector-search", json=body)
            break
        except RuntimeError:
            if attempt == 11:
                raise
            time.sleep(10)

    expected = int(run_sql(f"SELECT count(*) FROM {config['chunks']}")["result"]["data_array"][0][0])
    deadline = time.time() + 30 * 60
    while time.time() < deadline:
        time.sleep(15)
        status = databricks("GET", path, "vector-search")["status"]
        if status.get("ready") and status.get("indexed_row_count") == expected:
            return
        if "FAILED" in status.get("detailed_state", ""):
            raise RuntimeError(f"Recreated index failed: {status.get('message', '')}")
    raise RuntimeError("Recreated index did not finish within 30 minutes")


def sync_index(index_name):
    """Trigger a sync and wait for its pipeline update, raising the pipeline error on failure."""
    spec = databricks("GET", f"/api/2.0/vector-search/indexes/{index_name}", "vector-search")
    pipeline = f"/api/2.0/pipelines/{spec['delta_sync_index_spec']['pipeline_id']}"
    previous = {u["update_id"] for u in databricks("GET", pipeline, "all-apis").get("latest_updates", [])}
    databricks("POST", f"/api/2.0/vector-search/indexes/{index_name}/sync", "vector-search")
    deadline = time.time() + 30 * 60
    while time.time() < deadline:
        time.sleep(10)
        updates = databricks("GET", pipeline, "all-apis").get("latest_updates", [])
        update = next((u for u in updates if u["update_id"] not in previous), None)
        if update and update["state"] == "COMPLETED":
            return
        if update and update["state"] in ("FAILED", "CANCELED"):
            events = databricks("GET", f"{pipeline}/events", "all-apis", params={"max_results": 25})
            for event in events.get("events", []):
                exceptions = (event.get("error") or {}).get("exceptions") or []
                if event.get("origin", {}).get("update_id") == update["update_id"] and exceptions:
                    raise RuntimeError(exceptions[0].get("message", "")[:800])
            raise RuntimeError(f"Index sync {update['state'].lower()}")
    raise RuntimeError("Index sync did not finish within 30 minutes")


def index_status(index_name):
    try:
        status = databricks("GET", f"/api/2.0/vector-search/indexes/{index_name}", "vector-search")["status"]
        return f"{status.get('detailed_state')}, {status.get('indexed_row_count')} rows"
    except Exception as error:
        return f"unavailable: {error}"


def volume_pdfs(path):
    """Return {file name: last modified ms} for every PDF under a volume folder."""
    files, folders = {}, [path]
    while folders:
        folder, page_token = folders.pop(), None
        while True:
            listing = databricks("GET", f"/api/2.0/fs/directories{quote(folder)}", "files",
                                 params={"page_token": page_token} if page_token else None)
            for entry in listing.get("contents", []):
                if entry.get("is_directory"):
                    folders.append(entry["path"])
                elif entry["name"].lower().endswith(".pdf"):
                    files[entry["name"]] = entry.get("last_modified", 0)
            page_token = listing.get("next_page_token")
            if not page_token:
                break
    return files


def document_coverage():
    """Compare the PDFs in each volume with the files in its chunk table."""
    union = " UNION ALL ".join(
        f"SELECT '{domain}' AS domain, {c['file_col']} AS file_name, "
        f"unix_millis(max({c['time_col']})) AS chunked_at, count(*) AS chunks "
        f"FROM {c['chunks']} GROUP BY {c['file_col']}"
        for domain, c in PIPELINES.items()
    )
    indexed = {domain: {} for domain in PIPELINES}
    for domain, name, chunked_at, _ in run_sql(union).get("result", {}).get("data_array") or []:
        indexed[domain][name] = int(chunked_at or 0)
    coverage = {}
    for domain, config in PIPELINES.items():
        in_volume, in_chunks = volume_pdfs(config["volume"]), indexed[domain]
        coverage[domain] = {
            "volume": len(in_volume),
            "indexed": len(in_volume.keys() & in_chunks.keys()),
            "missing": sorted(in_volume.keys() - in_chunks.keys()),
            "changed": sorted(n for n in in_volume.keys() & in_chunks.keys()
                              if in_volume[n] > in_chunks[n]),
            "removed": sorted(in_chunks.keys() - in_volume.keys()),
        }
    return coverage


# Serve the Ask Mariner static folder so the page uses the same logo.
app = Flask(__name__, static_folder=str(Path(__file__).resolve().parent.parent / "src" / "mariner_genai_dbx" / "static"))
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


@app.route("/", methods=["GET", "POST"])
def index():
    results = []
    selected = request.form.get("volume", DEFAULT_VOLUME)
    if request.method == "POST":
        volume = VOLUMES.get(selected)
        for file in request.files.getlist("files"):
            # Keep the original name (spaces included) so re-uploads replace existing documents.
            name = Path((file.filename or "").replace("\\", "/")).name.strip()
            if not volume:
                results.append((name, False, "Unknown volume"))
            elif not name.lower().endswith(".pdf"):
                results.append((name or "(empty)", False, "Only .pdf files are allowed"))
            else:
                try:
                    path = upload_to_volume(volume["volumePath"], name, file.read())
                    results.append((name, True, f"Uploaded to {path}"))
                except Exception as error:
                    results.append((name, False, str(error)))
    return render_template_string(PAGE, tab="upload", volumes=VOLUMES.values(),
                                  selected=selected, results=results)


@app.route("/indexes", methods=["GET", "POST"])
def indexes():
    if request.method == "POST":
        domain = request.form["domain"]
        if domain in PIPELINES and not RUNS.get(domain, {}).get("running"):
            RUNS[domain] = {"running": True, "steps": [],
                            "started": datetime.now().strftime("%H:%M:%S")}
            threading.Thread(target=refresh_index, args=(domain,), daemon=True).start()
        return redirect(url_for("indexes"))
    statuses = {domain: index_status(config["index"]) for domain, config in PIPELINES.items()}
    coverage, coverage_error = {}, None
    try:
        coverage = document_coverage()
    except Exception as error:
        coverage_error = str(error)
    return render_template_string(PAGE, tab="indexes", pipelines=PIPELINES, statuses=statuses,
                                  coverage=coverage, coverage_error=coverage_error,
                                  runs=RUNS, results=[],
                                  any_running=any(r["running"] for r in RUNS.values()))


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mariner Document Upload</title>
{% if any_running %}<meta http-equiv="refresh" content="5">{% endif %}
<style>
  /* Same palette and chrome as the Ask Mariner app (src/mariner_genai_dbx/static/chat.css). */
  :root {
    color-scheme: light;
    font-family: Oxygen, "Segoe UI", Arial, sans-serif;
    color: #333333;
    --mariner-blue: #013474; --mariner-navy: #171d43;
    --mariner-gold: #febd10; --mariner-gold-hover: #e8a900; --mariner-green: #006b4d;
    --danger: #b42318; --warning: #8a6100;
    --surface: #ffffff; --line: #dce2ea; --muted: #647184; --soft: #f3f6fa;
  }
  * { box-sizing: border-box; }
  body {
    min-height: 100vh; margin: 0;
    background: radial-gradient(circle at 15% 15%, rgb(1 52 116 / 7%), transparent 30rem), #f6f6f6;
  }
  button, input, select { font: inherit; }
  .brand-bar { height: 78px; background: var(--surface); border-bottom: 1px solid #e7e7e7;
    box-shadow: 0 2px 12px rgb(23 29 67 / 7%); }
  .brand-bar-inner { width: min(1080px, calc(100% - 2rem)); height: 100%; margin: 0 auto;
    display: flex; align-items: center; justify-content: space-between; gap: 1rem; }
  .brand-logo { width: 148px; height: auto; display: block; }
  .portal-label { color: var(--mariner-blue); font-size: .78rem; font-weight: 700;
    letter-spacing: .08em; text-transform: uppercase; }
  main { width: min(1078px, calc(100% - 2rem)); margin: 32px auto 48px; }
  .shell { background: var(--surface); border: 1px solid #e0e3e8; border-radius: 20px;
    box-shadow: 0 18px 48px rgb(23 29 67 / 14%); overflow: hidden; }
  .app-header { position: relative; padding: 1.8rem 2rem 0; color: #ffffff;
    background: radial-gradient(circle at 92% 0%, rgb(255 255 255 / 12%), transparent 17rem),
                linear-gradient(130deg, var(--mariner-blue) 0%, var(--mariner-navy) 100%); }
  .eyebrow { margin: 0 0 .4rem; color: var(--mariner-gold); font-size: .74rem; font-weight: 700;
    letter-spacing: .1em; text-transform: uppercase; }
  h1 { margin: 0; font-family: Lato, "Segoe UI", Arial, sans-serif; font-size: clamp(1.6rem, 4vw, 2.2rem);
    font-weight: 600; line-height: 1.15; }
  .header-description { margin: .5rem 0 0; color: rgb(255 255 255 / 82%); max-width: 46rem; }
  nav { display: flex; gap: .4rem; margin-top: 1.4rem; }
  nav a { padding: .7rem 1.2rem; border-radius: 10px 10px 0 0; color: #ffffff; text-decoration: none;
    font-weight: 700; background: rgb(255 255 255 / 10%); }
  nav a:hover { background: rgb(255 255 255 / 18%); }
  nav a.active { color: var(--mariner-navy); background: var(--surface); }
  .content { padding: 1.8rem 2rem 2rem; }
  h2 { margin: 0 0 .4rem; color: var(--mariner-blue); font-family: Lato, "Segoe UI", Arial, sans-serif;
    font-size: 1.35rem; font-weight: 700; }
  h3 { margin: 1.6rem 0 .5rem; color: var(--mariner-navy); font-size: 1rem; }
  .lead { margin: 0 0 1.2rem; color: var(--muted); line-height: 1.55; }
  form.upload { display: grid; gap: 1rem; max-width: 640px; }
  label { display: grid; gap: .35rem; color: var(--mariner-navy); font-size: .82rem; font-weight: 700;
    letter-spacing: .06em; text-transform: uppercase; }
  select, input[type=file] { width: 100%; padding: .7rem .8rem; color: #333333; background: var(--surface);
    border: 1px solid var(--line); border-radius: 8px; font-size: .95rem; letter-spacing: 0; text-transform: none; font-weight: 400; }
  select:focus, input[type=file]:focus { outline: 2px solid var(--mariner-gold); outline-offset: 1px; }
  input[type=file]::file-selector-button { margin-right: .8rem; padding: .45rem .9rem; color: #ffffff;
    background: var(--mariner-blue); border: 0; border-radius: 4px; font-weight: 700; cursor: pointer; }
  button { justify-self: start; min-width: 112px; padding: .72rem 1.2rem; color: #333333; background: var(--mariner-gold);
    border: 0; border-radius: 4px; box-shadow: 0 3px 8px rgb(0 0 0 / 14%); cursor: pointer; font-weight: 700;
    transition: background 150ms ease, transform 150ms ease, box-shadow 150ms ease; }
  button:hover:not(:disabled) { background: var(--mariner-gold-hover); box-shadow: 0 5px 12px rgb(0 0 0 / 18%);
    transform: translateY(-1px); }
  button:focus-visible { outline: 3px solid rgb(254 189 16 / 38%); outline-offset: 3px; }
  button:disabled { cursor: wait; opacity: .62; }
  .results { display: grid; gap: .5rem; margin-bottom: 1.4rem; }
  .result { margin: 0; padding: .75rem 1rem; border-radius: 10px; border-left: 4px solid; overflow-wrap: anywhere; }
  .result.ok { color: #0b4a37; background: #e8f5ef; border-color: var(--mariner-green); }
  .result.err { color: #7a1a12; background: #fdecea; border-color: var(--danger); white-space: pre-wrap; }
  .ok, .done { color: var(--mariner-green); font-weight: 700; }
  .err, .failed { color: var(--danger); white-space: pre-wrap; }
  .running, .warn { color: var(--warning); }
  .table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; margin: .5rem 0 1.5rem; }
  table { border-collapse: collapse; width: 100%; }
  th, td { padding: .7rem .8rem; text-align: left; font-size: .9rem; vertical-align: top;
    border-bottom: 1px solid var(--line); overflow-wrap: anywhere; }
  tr:last-child td { border-bottom: 0; }
  th { color: #ffffff; background: var(--mariner-blue); font-size: .76rem; letter-spacing: .06em; text-transform: uppercase; }
  tbody tr:nth-child(even) { background: var(--soft); }
  small { color: var(--muted); }
  td form { margin: 0; }
  .state { display: inline-block; padding: .15rem .55rem; border-radius: 999px; font-size: .78rem; font-weight: 700;
    text-transform: capitalize; }
  .state.done { color: var(--mariner-green); background: #e8f5ef; }
  .state.running, .state.warn { color: var(--warning); background: #fff4d1; }
  .state.failed { color: var(--danger); background: #fdecea; }
  @media (max-width: 640px) {
    .brand-logo { width: 120px; }
    .app-header, .content { padding-left: 1.2rem; padding-right: 1.2rem; }
    nav a { padding: .6rem .9rem; }
  }
</style></head>
<body>
<header class="brand-bar"><div class="brand-bar-inner">
  <img class="brand-logo" src="{{ url_for('static', filename='mariner-logo.png') }}" alt="Mariner Finance" width="274" height="101">
  <span class="portal-label">Employee resources</span>
</div></header>
<main><div class="shell">
<header class="app-header">
  <p class="eyebrow">Document library</p>
  <h1>Ask Mariner documents</h1>
  <p class="header-description">Upload PDFs to the document volumes, then refresh the indexes the Knowledge Assistants search.</p>
  <nav>
    <a href="/" class="{{ 'active' if tab == 'upload' }}">Upload</a>
    <a href="/indexes" class="{{ 'active' if tab == 'indexes' }}">Update index</a>
  </nav>
</header>
<section class="content">
{% if results %}<div class="results">
{% for name, ok, message in results %}
  <p class="result {{ 'ok' if ok else 'err' }}"><b>{{ name }}</b>: {{ message }}</p>
{% endfor %}
</div>{% endif %}
{% if tab == 'upload' %}
<h2>Upload PDFs to a volume</h2>
<p class="lead">Files keep their original names, so uploading a file with the same name replaces the earlier version.</p>
<form class="upload" method="post" enctype="multipart/form-data">
  <label>Volume
    <select name="volume">
      {% for v in volumes %}
        <option value="{{ v.id }}" {% if v.id == selected %}selected{% endif %}>{{ v.label }} ({{ v.volumePath }})</option>
      {% endfor %}
    </select>
  </label>
  <label>PDF files
    <input type="file" name="files" accept="application/pdf,.pdf" multiple required>
  </label>
  <button>Upload</button>
</form>
{% else %}
<h2>Update vector index</h2>
<p class="lead">Parses new PDFs in the volume, rebuilds the chunk table, and syncs the index the
Knowledge Assistant searches. Parsing takes a few minutes per new document.</p>
{% if coverage_error %}<p class="result err">Could not compare documents: {{ coverage_error }}</p>{% endif %}
<div class="table-wrap"><table>
  <thead><tr><th>Document set</th><th>Index</th><th>Index status</th><th>Documents</th><th></th></tr></thead>
  <tbody>
  {% for domain, p in pipelines.items() %}
    <tr><td><b>{{ p.label }}</b><br><small>{{ p.volume }}</small></td><td>{{ p.index }}</td>
      <td>{{ statuses[domain] }}</td>
      <td>{% set c = coverage.get(domain) %}{% if c %}
        <span class="{{ 'ok' if not (c.missing or c.changed or c.removed) }}">{{ c.indexed }} of {{ c.volume }} PDFs indexed</span>
        {% for n in c.missing %}<br><span class="err">missing: {{ n }}</span>{% endfor %}
        {% for n in c.changed %}<br><span class="warn">changed since indexed: {{ n }}</span>{% endfor %}
        {% for n in c.removed %}<br><span class="warn">no longer in volume: {{ n }}</span>{% endfor %}
      {% endif %}</td>
      <td><form method="post"><input type="hidden" name="domain" value="{{ domain }}">
        <button {% if runs.get(domain, {}).running %}disabled{% endif %}>Update</button></form></td></tr>
  {% endfor %}
  </tbody>
</table></div>
{% for domain, run in runs.items() %}
  <h3>{{ pipelines[domain].label }} (started {{ run.started }})</h3>
  <div class="table-wrap"><table><tbody>
    {% for label, state, detail in run.steps %}
      <tr><td>{{ label }}</td><td><span class="state {{ state }}">{{ state }}</span></td><td class="{{ state }}">{{ detail }}</td></tr>
    {% endfor %}
  </tbody></table></div>
{% endfor %}
{% endif %}
</section>
</div></main>
</body></html>"""


if __name__ == "__main__":
    app.run(port=5002, debug=True)
