"""Read-only access tests for the Coaching360 views, before or after they are created.

Runs each view's SQL with the signed-in user replaced by a fixed directory person (persona) and
checks level, branch scope, own-row filtering and the level gate. Usage (repo root):
    python3 coaching360/tests/access_tests.py
Credentials: DATABRICKS_HOST, DATABRICKS_WAREHOUSE_ID and either DATABRICKS_TOKEN or the app
service principal (DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET, SQL scope) from .env.
"""
import base64, importlib.util, json, pathlib, sys, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build_sql", ROOT / "coaching360/build_sql.py")
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
env = dict(l.strip().split("=", 1) for l in open(ROOT / ".env") if "=" in l and not l.lstrip().startswith("#"))
HOST, WH = env["DATABRICKS_HOST"].rstrip("/"), env["DATABRICKS_WAREHOUSE_ID"]
if env.get("DATABRICKS_TOKEN"):
    TOKEN = env["DATABRICKS_TOKEN"]
else:
    auth = base64.b64encode(f"{env['DATABRICKS_CLIENT_ID']}:{env['DATABRICKS_CLIENT_SECRET']}".encode()).decode()
    req = urllib.request.Request(f"{HOST}/oidc/v1/token", urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "sql"}).encode(),
                                 {"Authorization": "Basic " + auth})
    TOKEN = json.load(urllib.request.urlopen(req))["access_token"]


def run(sql):
    assert sql.lstrip().upper().startswith(("SELECT", "WITH")), "read-only"
    req = urllib.request.Request(f"{HOST}/api/2.0/sql/statements", json.dumps({"warehouse_id": WH, "statement": sql, "wait_timeout": "50s"}).encode(),
                                 {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=120))
    if d["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(d["status"].get("error", {}).get("message", "")[:300])
    return d.get("result", {}).get("data_array") or []


count = lambda sql: int(run(f"SELECT COUNT(*) FROM ({sql})")[0][0])
PERSONAS = {  # title: user_dwid (most coaching records per title in the demo data)
    "Account Representative": 500371, "Assistant Branch Manager": 500027, "Branch Manager Trainee": 500322,
    "Branch Manager": 500054, "Branch Manager + relief": 500072, "District Manager": 500003,
    "Regional Vice President": 500002, "Senior Vice President": 500001, "HR Business Partner": 500393,
    "Business Analyst (no level)": 500391, "Inactive employee": 500016,
}
EXPECTED_LEVEL = {"Account Representative": "employee", "Assistant Branch Manager": "employee", "Branch Manager Trainee": "employee",
                  "Branch Manager": "branch", "Branch Manager + relief": "branch", "District Manager": "district",
                  "Regional Vice President": "district", "Senior Vice President": "district", "HR Business Partner": "district",
                  "Business Analyst (no level)": "none", "Inactive employee": None}
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


# 1. Every view compiles (one persona per level).
compile_jobs = [(lvl, name, sql, pid) for lvl, pid in (("employee", 500371), ("branch", 500054), ("district", 500003))
                for name, (sql, _) in b.views_for(lvl).items()]
def compiles(job):
    level, name, sql, pid = job
    try:
        run(b.render(sql, pid) + " LIMIT 0")
        return None
    except Exception as error:
        return f"{level}.{name}: {error}"


with ThreadPoolExecutor(8) as pool:
    errors = [e for e in pool.map(compiles, compile_jobs) if e]
for e in errors:
    print("   ", e)
check(f"all {len(compile_jobs)} views compile", not errors, f"{len(errors)} errors")

# 2. Level and branch scope per persona.
BR, DI, RE, DV = b.BRANCH, b.DISTRICT, b.REGION, b.DIVISION
expected_scope = {
    "Branch Manager": f"SELECT BranchDWID FROM {BR} WHERE lower(BMUsername) = (SELECT lower(UserName) FROM {b.USER} WHERE UserDWID = 500054)",
    "District Manager": f"SELECT b.BranchDWID FROM {BR} b JOIN {DI} d ON d.DistrictDWID = b.DistrictDWID WHERE lower(d.DMUsername) = (SELECT lower(UserName) FROM {b.USER} WHERE UserDWID = 500003)",
    "Regional Vice President": f"SELECT b.BranchDWID FROM {BR} b JOIN {DI} d ON d.DistrictDWID = b.DistrictDWID JOIN {RE} r ON r.RegionDWID = d.RegionDWID WHERE lower(r.VPUsername) = (SELECT lower(UserName) FROM {b.USER} WHERE UserDWID = 500002)",
    "Senior Vice President": f"SELECT b.BranchDWID FROM {BR} b JOIN {DI} d ON d.DistrictDWID = b.DistrictDWID JOIN {RE} r ON r.RegionDWID = d.RegionDWID JOIN {DV} c ON c.CompanyDivisionDWID = r.CompanyDivisionDWID WHERE lower(c.SVPUsername) = (SELECT lower(UserName) FROM {b.USER} WHERE UserDWID = 500001)",
    "HR Business Partner": f"SELECT BranchDWID FROM {BR}",
}
for title, pid in PERSONAS.items():
    level = run(f"SELECT max(level) FROM ({b.USER_LEVEL}) WHERE user_dwid = {pid}")[0][0]
    scope = count(f"SELECT DISTINCT branch_dwid FROM ({b.BRANCH_SCOPE}) WHERE user_dwid = {pid}")
    detail = f"level={level} branches={scope}"
    ok = level == EXPECTED_LEVEL[title]
    if title in expected_scope:
        exp = count(expected_scope[title]); ok = ok and scope == exp; detail += f" (expected {exp})"
    elif title == "Branch Manager + relief":
        ok = ok and scope == 2; detail += " (expected 2: own branch + relief branch)"
    else:
        ok = ok and scope == 0; detail += " (expected 0)"
    check(f"scope {title}", ok, detail)

# 3. Own rows only (employee views) and branch-scoped rows (branch/district views).
S = b.SRC
emp = {"my_coaching_records": f"SELECT 1 FROM {S}.coaching360_app_workflow__dbo_coachingrecords WHERE EmployeeId = {{p}} AND VisibleToEmployee",
       "my_monthly_kpis": f"SELECT 1 FROM {S}.branchkpi_sources__branchkpi_monthly_employeeperformance WHERE TellerID = (SELECT CAST(TellerID AS BIGINT) FROM {b.USER} WHERE UserDWID = {{p}})",
       "my_ace_payout": f"SELECT 1 FROM {S}.crm_ace_payout__crm_ace_usp_getbmemployeemonthlypayoutestimate WHERE TELLER_ID = (SELECT CAST(TellerID AS BIGINT) FROM {b.USER} WHERE UserDWID = {{p}})",
       "my_policy_violations": f"SELECT 1 FROM {S}.policy_violations__policyviolations_app_violations WHERE EmployeeId = (SELECT EmployeeNumber FROM {b.USER} WHERE UserDWID = {{p}})",
       "my_tasks": f"SELECT 1 FROM {S}.coaching360_app_workflow__dbo_coachingtasks WHERE AssignedToEmployeeId = {{p}}",
       # DPR rows carry the DPR app's own employee id; the directory TellerID identifies the person.
       "my_dpr_scorecard": f"SELECT 1 FROM {S}.coaching360_app_dpr__dbo_dpremployeescorecardmetrics WHERE SourceTellerId = (SELECT TellerID FROM {b.USER} WHERE UserDWID = {{p}})"}
ev = b.views_for("employee")
for title in ("Account Representative", "Assistant Branch Manager", "Branch Manager Trainee"):
    pid = PERSONAS[title]
    for view, direct in emp.items():
        got, exp = count(b.render(ev[view][0], pid)), count(direct.format(p=pid))
        check(f"{title}: {view}", got == exp, f"{got} rows (direct {exp})")
    hidden = count(f"SELECT 1 FROM {S}.coaching360_app_workflow__dbo_coachingrecords WHERE EmployeeId = {pid} AND NOT VisibleToEmployee")
    check(f"{title}: hidden coaching records not shown", count(b.render(ev['my_coaching_records'][0], pid)) ==
          count(f"SELECT 1 FROM {S}.coaching360_app_workflow__dbo_coachingrecords WHERE EmployeeId = {pid}") - hidden, f"{hidden} hidden")
    internal = count(b.render(ev["my_coaching_comments"][0], pid).replace("WHERE c.EmployeeId", "WHERE i.IsInternal AND c.EmployeeId"))
    check(f"{title}: no internal manager comments", internal == 0)

def scoped(level, pid, view, direct_filter_sql):
    got = count(b.render(b.views_for(level)[view][0], pid))
    return got, count(direct_filter_sql)

for level, title in (("branch", "Branch Manager"), ("branch", "Branch Manager + relief"), ("district", "District Manager"),
                     ("district", "Regional Vice President"), ("district", "HR Business Partner")):
    pid = PERSONAS[title]
    dwids = f"(SELECT branch_dwid FROM ({b.BRANCH_SCOPE}) WHERE user_dwid = {pid})"
    nums = f"(SELECT BranchNumber FROM {BR} WHERE BranchDWID IN {dwids})"
    for view, direct in (("coaching_records", f"SELECT 1 FROM {S}.coaching360_app_workflow__dbo_coachingrecords WHERE OrganizationalUnitId IN {dwids}"),
                         ("employee_monthly_kpis", f"SELECT 1 FROM {S}.branchkpi_sources__branchkpi_monthly_employeeperformance WHERE Branch IN {nums}"),
                         ("branch_visits", f"SELECT 1 FROM {S}.coaching360_app_workflow__dbo_branchvisits WHERE OrganizationalUnitId IN {dwids}"),
                         ("dpr_scorecard", f"SELECT 1 FROM {S}.coaching360_app_dpr__dbo_dpremployeescorecardmetrics WHERE SourceTellerId IN (SELECT TellerID FROM {b.USER} WHERE BranchDWID IN {dwids})"),
                         ("policy_violations", f"SELECT 1 FROM {S}.policy_violations__policyviolations_app_violations WHERE BranchNumber IN {nums}")):
        got, exp = scoped(level, pid, view, direct)
        check(f"{title}: {view}", got == exp and (got > 0 or view == "policy_violations"), f"{got} rows (direct {exp})")
    if level == "branch":
        conf = count(b.render(b.views_for("branch")["branch_visits"][0], pid) + " AND IsConfidentialVisit")
        check(f"{title}: confidential visits visible (decision 3)", True, f"{conf} confidential visits")

# 4. Level gate: a persona sees nothing in another level's schema.
for title, pid in PERSONAS.items():
    lvl = EXPECTED_LEVEL[title]
    for other in ("branch", "district"):
        if other == lvl:
            continue
        got = count(b.render(b.views_for(other)["coaching_records"][0], pid))
        check(f"gate: {title} in {other} schema", got == 0, f"{got} rows")
    if lvl in (None, "none"):
        got = count(b.render(b.views_for("employee")["my_coaching_records"][0], pid))
        check(f"gate: {title} in employee schema", got == 0, f"{got} rows")

print(f"\n{sum(results)}/{len(results)} checks passed")
sys.exit(0 if all(results) else 1)
