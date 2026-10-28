"""Coaching360 regression test: conversations through the running app, with checked answers.

Start the app locally (AUTH_MODE=local), then from the repo root:
    python3 coaching360/tests/regression_test.py                       # http://127.0.0.1:8080
    python3 coaching360/tests/regression_test.py --url http://127.0.0.1:5000 --only "Felicia"
Cases are in regression_cases.json (add questions there). Each conversation starts a new chat,
so the month and person carry forward the way they do for a user. The run changes the shared
demo persona, so do not use Coaching360 in the app at the same time. Exit code 1 if any check fails.
Results are saved to coaching360/tests/results/regression_<time>.json.
"""
import argparse, json, pathlib, re, sys, time, urllib.error, urllib.request

HERE = pathlib.Path(__file__).resolve().parent


def chat(url, message, conversation_id, timeout):
    body = {"message": message, **({"conversationId": conversation_id} if conversation_id else {})}
    request = urllib.request.Request(f"{url.rstrip('/')}/api/v1/chat/stream", json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    answer, conversation, error = "", conversation_id, None
    with urllib.request.urlopen(request, timeout=timeout) as response:
        event = None
        for raw in response:
            line = raw.decode("utf-8", "replace").rstrip("\n")
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = json.loads(line[5:].strip())
                conversation = data.get("conversationId", conversation)
                if event == "answer":
                    answer = data.get("answer", "")
                elif event == "error":
                    error = f"{data.get('code')}: {data.get('message')}"
    return answer, conversation, error


def check(turn, answer, error, seconds, cases):
    problems = [error] if error else []
    if seconds > cases.get("max_seconds", 120):
        problems.append(f"took {seconds:.0f}s (limit {cases['max_seconds']}s)")
    for pattern in turn.get("expect", []):
        if not re.search(pattern, answer, re.IGNORECASE):
            problems.append(f"missing /{pattern}/")
    for pattern in turn.get("reject", []) + cases.get("always_reject", []):
        if re.search(pattern, answer, re.IGNORECASE):
            problems.append(f"unexpected /{pattern}/")
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8080")
    parser.add_argument("--cases", default=str(HERE / "regression_cases.json"))
    parser.add_argument("--only", help="run conversations whose name contains this text")
    args = parser.parse_args()
    cases = json.loads(pathlib.Path(args.cases).read_text())
    results, failures = [], 0
    for conversation in cases["conversations"]:
        if args.only and args.only.lower() not in conversation["name"].lower():
            continue
        print(f"\n== {conversation['name']}", flush=True)
        conversation_id = None
        for turn in conversation["turns"]:
            started = time.monotonic()
            try:
                answer, conversation_id, error = chat(args.url, turn["ask"], conversation_id, timeout=cases.get("max_seconds", 120) + 60)
            except (urllib.error.URLError, TimeoutError) as exc:
                answer, error = "", f"request failed: {exc}"
            seconds = time.monotonic() - started
            problems = check(turn, answer, error, seconds, cases)
            failures += bool(problems)
            print(f"{'PASS' if not problems else 'FAIL'} {seconds:6.1f}s  {turn.get('id', '  ')} {turn['ask']}", flush=True)
            for problem in problems:
                print(f"         {problem}")
            if problems:
                print("         answer: " + answer[:500].replace("\n", " "))
            results.append({"conversation": conversation["name"], "id": turn.get("id"), "ask": turn["ask"], "seconds": round(seconds, 1),
                            "problems": problems, "answer": answer})
    total = len(results)
    print(f"\n{total - failures}/{total} turns passed")
    out = HERE / "results"
    out.mkdir(exist_ok=True)
    (out / f"regression_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(json.dumps(results, indent=1))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
