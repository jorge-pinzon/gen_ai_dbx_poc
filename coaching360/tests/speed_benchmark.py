"""Coaching360 answer-time benchmark: a fixed set of questions per level, timed per stage.

Runs each question through the Supervisor exactly as the chat does (level directive, empty
history), as the app's service principal, and splits the time from the streamed events:
  plan     request sent -> Supervisor picks the Coaching360 tool
  genie    tool called  -> Genie's result arrives
  rewrite  Genie result -> Supervisor's answer is complete
Usage (repo root):
    python3 coaching360/tests/speed_benchmark.py baseline            # all levels, 10 questions each
    python3 coaching360/tests/speed_benchmark.py after-sql --levels branch --limit 3
    python3 coaching360/tests/speed_benchmark.py --compare baseline after-sql
Results are saved to coaching360/tests/results/speed_<label>.json. The run changes the service
principal's demo persona (user_map) per level and puts the original person back at the end.
"""
import argparse, base64, json, pathlib, statistics, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from mariner_genai_dbx.coaching360 import Coaching360Service  # noqa: E402

RESULTS = pathlib.Path(__file__).resolve().parent / "results"
SUPERVISOR = "mas-53dbd2d7-endpoint"
SEC = "workspace.c360_security"
PERSONAS = {"employee": 500371, "branch": 500054, "district": 500003}
QUESTIONS = {
    "employee": [
        "What was my production last month?",
        "Show me my scorecard for September",
        "What's in my Success Plan?",
        "What are my open tasks?",
        "What coaching have I received recently?",
        "How many outbound calls did I make last month?",
        "What is my estimated ACE payout?",
        "Do I have any open policy violations?",
        "How has my volume trended over the last six months?",
        "Who is my manager?",
    ],
    "branch": [
        "Who are my employees?",
        "Rank my team by volume last month",
        "Which team members have overdue tasks?",
        "Which coaching records are waiting for acknowledgement?",
        "How did each employee do on the DPR scorecard this month?",
        "How is my branch scorecard trending?",
        "What came out of the latest branch visit?",
        "What are the estimated ACE payouts for my team?",
        "Which employees have no coaching in the last 90 days?",
        "Give me an overview of my team",
    ],
    "district": [
        "Compare the branches in my district by volume last month",
        "Which branches have the most overdue tasks?",
        "Who are the branch managers in my area?",
        "How is my district scorecard trending?",
        "How much coaching did each branch document in the last 90 days?",
        "Which branches had a visit this quarter?",
        "Open policy violations by branch",
        "What is the trailing 12-month turnover for my district?",
        "Which branch has the highest delinquency?",
        "Rank all employees in my district by volume last month",
    ],
}

env = dict(l.strip().split("=", 1) for l in open(ROOT / ".env") if "=" in l and not l.lstrip().startswith("#"))
HOST, WAREHOUSE = env["DATABRICKS_HOST"].rstrip("/"), env["DATABRICKS_WAREHOUSE_ID"]


def token(scope):
    auth = base64.b64encode(f"{env['DATABRICKS_CLIENT_ID']}:{env['DATABRICKS_CLIENT_SECRET']}".encode()).decode()
    request = urllib.request.Request(f"{HOST}/oidc/v1/token", urllib.parse.urlencode(
        {"grant_type": "client_credentials", "scope": scope}).encode(), {"Authorization": "Basic " + auth})
    return json.load(urllib.request.urlopen(request))["access_token"]


def sql(statement, sql_token):
    request = urllib.request.Request(f"{HOST}/api/2.0/sql/statements", json.dumps(
        {"warehouse_id": WAREHOUSE, "statement": statement, "wait_timeout": "50s"}).encode(),
        {"Authorization": "Bearer " + sql_token, "Content-Type": "application/json"})
    result = json.load(urllib.request.urlopen(request, timeout=120))
    if result["status"]["state"] != "SUCCEEDED":
        raise RuntimeError(result["status"].get("error", {}).get("message", "")[:300])
    return result.get("result", {}).get("data_array") or []


def set_persona(user_dwid, sql_token):
    sql(f"""MERGE INTO {SEC}.user_map AS t
            USING (SELECT current_user() AS databricks_user, {int(user_dwid)} AS user_dwid) AS s
            ON lower(t.databricks_user) = lower(s.databricks_user)
            WHEN MATCHED THEN UPDATE SET user_dwid = s.user_dwid, updated_at = current_timestamp()
            WHEN NOT MATCHED THEN INSERT (databricks_user, user_dwid, note, updated_at)
              VALUES (s.databricks_user, s.user_dwid, 'coaching360 speed benchmark', current_timestamp())""", sql_token)


def ask(level, question, serving_token):
    body = {"input": [{"role": "user", "content": Coaching360Service.directive(level, question)}], "stream": True}
    request = urllib.request.Request(f"{HOST}/serving-endpoints/{SUPERVISOR}/invocations", json.dumps(body).encode(),
                                     {"Authorization": "Bearer " + serving_token, "Content-Type": "application/json"})
    started = time.monotonic()
    at = lambda: round(time.monotonic() - started, 2)
    marks, tools, answer, final = {}, [], "", False
    with urllib.request.urlopen(request, timeout=240) as response:
        for raw in response:
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            if event.get("type") == "response.output_text.delta" and final:
                marks.setdefault("first_text", at())
            if event.get("type") != "response.output_item.done":
                continue
            item = event.get("item") or {}
            text = "".join(p.get("text", "") for p in item.get("content") or [] if isinstance(p, dict))
            if item.get("type") == "function_call":
                marks.setdefault("tool_called", at())
                tools.append(item.get("name"))
            elif item.get("type") == "message" and item.get("call_id"):
                marks["tool_result"] = at()
                if text.startswith("Genie query failed"):
                    marks["genie_error"] = text[:300]
            elif item.get("type") == "message" and text.strip().startswith("<name>"):
                final = "coaching360" not in text  # the Supervisor's own name tag (spelled "supevisor")
            elif item.get("type") == "message" and final:
                answer = text
    marks["done"] = at()
    called, result, done = marks.get("tool_called"), marks.get("tool_result"), marks["done"]
    if "genie_error" in marks:  # a fast failure is not an answer: keep it out of the timings
        return {"level": level, "question": question, "tools": tools, "error": marks["genie_error"], "total": None,
                "plan": None, "genie": None, "rewrite": None, "answer": answer[:400]}
    return {"level": level, "question": question, "tools": tools, "total": done,
            "plan": called, "genie": round(result - called, 2) if called and result else None,
            "rewrite": round(done - result, 2) if result else None, "answer": answer[:400]}


def percentile(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    return round(values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))], 1)


def summary(rows):
    out = {}
    for level in [l for l in QUESTIONS if any(r["level"] == l for r in rows)] + ["all"]:
        sel = [r for r in rows if level == "all" or r["level"] == level]
        out[level] = {stage: {"p50": percentile([r[stage] for r in sel], 50), "p90": percentile([r[stage] for r in sel], 90)}
                      for stage in ("total", "plan", "genie", "rewrite")}
    return out


def show(label, result):
    failed = [r for r in result["rows"] if r.get("error")]
    print(f"\n{label}: {len(result['rows'])} questions, {len(failed)} failed (left out of the timings)")
    print(f"{'level':10} " + " ".join(f"{s:>16}" for s in ("total p50/p90", "plan", "genie", "rewrite")))
    for level, stages in result["summary"].items():
        print(f"{level:10} " + " ".join(f"{str(stages[s]['p50']) + ' / ' + str(stages[s]['p90']):>16}"
                                       for s in ("total", "plan", "genie", "rewrite")))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("label", nargs="?")
    parser.add_argument("--levels", default="employee,branch,district")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--compare", nargs=2, metavar=("BEFORE", "AFTER"))
    args = parser.parse_args()
    if args.compare:
        for label in args.compare:
            show(label, json.loads((RESULTS / f"speed_{label}.json").read_text()))
        return
    sql_token, serving_token = token("sql"), token("model-serving")
    original = sql(f"SELECT max(user_dwid) FROM {SEC}.user_map WHERE lower(databricks_user) = lower(current_user())", sql_token)
    rows = []
    try:
        for level in args.levels.split(","):
            set_persona(PERSONAS[level], sql_token)
            for question in QUESTIONS[level][: args.limit]:
                try:
                    row = ask(level, question, serving_token)
                except Exception as error:  # keep going; a failure is a data point too
                    row = {"level": level, "question": question, "error": str(error)[:200], "total": None,
                           "plan": None, "genie": None, "rewrite": None}
                rows.append(row)
                print(f"{level:9} {row['total'] or 0:6.1f}s  plan {row['plan']}  genie {row['genie']}  "
                      f"rewrite {row['rewrite']}  {question}", flush=True)
    finally:
        if original and original[0][0]:
            set_persona(original[0][0], sql_token)
    result = {"label": args.label, "rows": rows, "summary": summary(rows)}
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"speed_{args.label}.json").write_text(json.dumps(result, indent=1))
    show(args.label, result)


if __name__ == "__main__":
    main()
