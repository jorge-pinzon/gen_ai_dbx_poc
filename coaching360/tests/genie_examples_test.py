"""Run every Genie example SQL as a real persona of its level (via user_map) and report rows.

Writes one user_map row for the identity running the test and deletes it at the end.
Usage (repo root): python3 coaching360/tests/genie_examples_test.py
"""
import importlib.util, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("access_tests_conn", ROOT / "coaching360/tests/access_tests.py")
# Reuse the connection helper without running the access tests.
src = open(ROOT / "coaching360/tests/access_tests.py").read()
ns = {"__file__": str(ROOT / "coaching360/tests/access_tests.py")}
exec(src[:src.index("count = lambda")], ns)
run = ns["run"]
spec = importlib.util.spec_from_file_location("build_agents", ROOT / "coaching360/build_agents.py")
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)

PERSONAS = {"employee": (500371, "Account Representative"), "branch": (500054, "Branch Manager"), "district": (500003, "District Manager")}
SEC = "workspace.c360_security"
ok = True
try:
    for level, (pid, title) in PERSONAS.items():
        run(f"SELECT 1 FROM {SEC}.user_map LIMIT 0")
        ns["urllib"].request  # keep import
        for stmt in (f"DELETE FROM {SEC}.user_map WHERE databricks_user = current_user()",
                     f"INSERT INTO {SEC}.user_map VALUES (current_user(), {pid}, 'genie example test: {title}', current_timestamp())"):
            req = ns["urllib"].request.Request(f"{ns['HOST']}/api/2.0/sql/statements", ns["json"].dumps({"warehouse_id": ns["WH"], "statement": stmt, "wait_timeout": "50s"}).encode(),
                                               {"Authorization": "Bearer " + ns["TOKEN"], "Content-Type": "application/json"})
            ns["json"].load(ns["urllib"].request.urlopen(req, timeout=60))
        level_now = run(f"SELECT {SEC}.my_level()")[0][0]
        print(f"== {level} as {title} ({pid}); my_level() = {level_now}")
        for question, sql in a.EXAMPLES[level]:
            try:
                rows = run(sql)
                print(f"   OK   {len(rows):3} rows  {question}")
            except Exception as error:
                ok = False
                print(f"   FAIL {question}: {error}")
finally:
    req = ns["urllib"].request.Request(f"{ns['HOST']}/api/2.0/sql/statements", ns["json"].dumps({"warehouse_id": ns["WH"], "statement": f"DELETE FROM {SEC}.user_map WHERE databricks_user = current_user()", "wait_timeout": "50s"}).encode(),
                                       {"Authorization": "Bearer " + ns["TOKEN"], "Content-Type": "application/json"})
    ns["json"].load(ns["urllib"].request.urlopen(req, timeout=60))
    print("user_map test row removed")
sys.exit(0 if ok else 1)
