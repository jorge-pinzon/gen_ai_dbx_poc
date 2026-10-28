"""Apply the Coaching360 speed-ups: SQL objects first, then the three Genie spaces.

    python3 coaching360/apply_speedups.py            # SQL + Genie
    python3 coaching360/apply_speedups.py --sql      # SQL only
    python3 coaching360/apply_speedups.py --genie    # Genie only
    python3 coaching360/apply_speedups.py --sql-files 06_genie_functions.sql --genie   # functions + Genie

Runs as you, with DATABRICKS_TOKEN from .env (the c360_* schemas are yours; the app's service
principal cannot create objects or edit Genie spaces). Every statement is rerunnable.
Order: scope tables (01c), prepared tables (01d), level views (02-04), trusted functions (06),
then the service principal's grants (05b, which now include EXECUTE for the functions).
"""
import argparse, json, pathlib, re, sys, time, urllib.error, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
HERE = pathlib.Path(__file__).resolve().parent
SQL_FILES = ["01c_scope_once.sql", "01d_prepared.sql", "02_employee_views.sql", "03_branch_views.sql",
             "04_district_views.sql", "06_genie_functions.sql", "05b_demo_grants_app.sql"]
TITLES = {"employee": "Coaching360 - My Development", "branch": "Coaching360 - Branch Leader",
          "district": "Coaching360 - District and Above"}

env = dict(l.strip().split("=", 1) for l in open(ROOT / ".env") if "=" in l and not l.lstrip().startswith("#"))
if not env.get("DATABRICKS_TOKEN"):
    sys.exit("DATABRICKS_TOKEN is not set in .env (uncomment it to run this script).")
HOST, WAREHOUSE, TOKEN = env["DATABRICKS_HOST"].rstrip("/"), env["DATABRICKS_WAREHOUSE_ID"], env["DATABRICKS_TOKEN"]


def api(method, path, body=None):
    request = urllib.request.Request(f"{HOST}{path}", json.dumps(body).encode() if body is not None else None,
                                     {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}, method=method)
    try:
        return json.load(urllib.request.urlopen(request, timeout=120))
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"{method} {path}: {error.code} {error.read().decode()[:500]}") from None


def statements(text):
    """Split a generated file into statements; comments after a ';' and comment-only chunks are dropped."""
    for chunk in re.split(r";[ \t]*(?:--[^\n]*)?\n", text + "\n"):
        body = "\n".join(line for line in chunk.splitlines() if not line.lstrip().startswith("--")).strip()
        if body:
            yield body


def run_sql(statement):
    result = api("POST", "/api/2.0/sql/statements", {"warehouse_id": WAREHOUSE, "statement": statement, "wait_timeout": "50s"})
    while result["status"]["state"] in ("PENDING", "RUNNING"):
        time.sleep(2)
        result = api("GET", f"/api/2.0/sql/statements/{result['statement_id']}")
    if result["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(result["status"].get("error", {}).get("message", "")[:500])


def apply_sql(files=SQL_FILES):
    for name in files:
        items = list(statements((HERE / "sql" / name).read_text()))
        print(f"{name}: {len(items)} statements", flush=True)
        for statement in items:
            first = " ".join(statement.split()[:6])
            started = time.monotonic()
            run_sql(statement)
            print(f"   {time.monotonic() - started:5.1f}s  {first}", flush=True)


def apply_genie():
    spaces = {s["title"]: s["space_id"] for s in api("GET", "/api/2.0/genie/spaces").get("spaces", [])}
    for level, title in TITLES.items():
        space = json.loads((HERE / "agents" / f"genie_{level}.json").read_text())
        api("PATCH", f"/api/2.0/genie/spaces/{spaces[title]}", {"serialized_space": json.dumps(space)})
        saved = json.loads(api("GET", f"/api/2.0/genie/spaces/{spaces[title]}?include_serialized_space=true")["serialized_space"])
        functions = len(saved.get("instructions", {}).get("sql_functions", []))
        notes = sum(len(t.get("column_configs", [])) for t in saved.get("data_sources", {}).get("tables", []))
        print(f"Genie {level}: {len(saved['data_sources']['tables'])} tables, {functions} functions, "
              f"{len(saved['instructions'].get('example_question_sqls', []))} examples, {notes} column notes", flush=True)
        check_space(level, spaces[title])


def check_space(level, space_id):
    """Ask one question: Genie validates the whole space configuration (functions included) on use."""
    started = api("POST", f"/api/2.0/genie/spaces/{space_id}/start-conversation", {"content": "How many rows are in kpi_definitions?"})
    path = f"/api/2.0/genie/spaces/{space_id}/conversations/{started['conversation_id']}/messages/{started['message_id']}"
    for _ in range(60):
        message = api("GET", path)
        if message.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(2)
    error = message.get("error") or {}
    ok = message.get("status") == "COMPLETED"
    print(f"   check {level}: {'OK' if ok else 'FAILED'} {message.get('status')} {str(error)[:300] if error else ''}", flush=True)
    if not ok:
        raise SystemExit(f"Genie {level} space is not usable; see the error above.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--sql", action="store_true")
    parser.add_argument("--genie", action="store_true")
    parser.add_argument("--sql-files", nargs="+", metavar="FILE", help="run only these files from coaching360/sql")
    args = parser.parse_args()
    if args.sql_files:
        apply_sql(args.sql_files)
    elif args.sql or not args.genie:
        apply_sql()
    if args.genie or not args.sql:
        apply_genie()
