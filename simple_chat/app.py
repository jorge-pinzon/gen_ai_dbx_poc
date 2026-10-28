"""Minimal chat UI for the Databricks Supervisor agent.

Reads credentials from the repo-root .env and forwards each message to the
Supervisor serving endpoint. Run with: python simple_chat/app.py
"""

import os
from pathlib import Path

import requests
from flask import Flask, jsonify, request

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
ENDPOINT = env.get("DATABRICKS_SUPERVISOR_ENDPOINT") or env["SUPERVISOR_ENDPOINT"]
URL = f"{HOST}/serving-endpoints/{ENDPOINT}/invocations"


def access_token():
    if env.get("DATABRICKS_TOKEN"):
        return env["DATABRICKS_TOKEN"]
    response = requests.post(
        f"{HOST}/oidc/v1/token",
        auth=(env["DATABRICKS_CLIENT_ID"], env["DATABRICKS_CLIENT_SECRET"]),
        data={"grant_type": "client_credentials", "scope": "model-serving"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]


def ask_supervisor(messages):
    headers = {"Authorization": f"Bearer {access_token()}"}
    items = list(messages)
    # The Supervisor pauses for approval before calling worker agents; approve and continue.
    for _ in range(5):
        response = requests.post(URL, headers=headers, json={"input": items}, timeout=300)
        response.raise_for_status()
        output = response.json().get("output", [])
        approvals = [o for o in output if o.get("type") == "mcp_approval_request"]
        if not approvals:
            break
        items += output + [
            {"type": "mcp_approval_response", "id": a["id"],
             "approval_request_id": a["id"], "approve": True}
            for a in approvals
        ]
    texts = [
        c["text"]
        for o in output if o.get("type") == "message" and o.get("role") == "assistant"
        for c in o.get("content", []) if c.get("type") == "output_text"
    ]
    return texts[-1] if texts else "(no answer)"


app = Flask(__name__)


@app.post("/chat")
def chat():
    try:
        return jsonify(answer=ask_supervisor(request.json["messages"]))
    except Exception as error:
        detail = getattr(getattr(error, "response", None), "text", "")
        app.logger.exception("Supervisor call failed")
        return jsonify(answer=f"Error: {error}\n{detail[:1000]}"), 500


@app.get("/")
def index():
    return PAGE


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Simple Chat</title>
<style>
  body { font-family: sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
  #log div { margin: .5rem 0; padding: .6rem; border-radius: 6px; white-space: pre-wrap; }
  .user { background: #e3f0ff; } .assistant { background: #f2f2f2; }
  form { display: flex; gap: .5rem; } input { flex: 1; padding: .5rem; }
</style></head>
<body>
<h2>Supervisor Chat</h2>
<div id="log"></div>
<form id="f"><input id="q" autocomplete="off" placeholder="Ask something..."><button>Send</button></form>
<script>
const messages = [];
const log = document.getElementById("log"), q = document.getElementById("q");
function add(role, text) {
  const d = document.createElement("div"); d.className = role; d.textContent = text;
  log.appendChild(d); return d;
}
document.getElementById("f").onsubmit = async (e) => {
  e.preventDefault();
  const text = q.value.trim(); if (!text) return;
  q.value = ""; add("user", text); messages.push({role: "user", content: text});
  const pending = add("assistant", "Thinking... 0:00");
  const start = Date.now();
  const elapsed = () => {
    const s = Math.floor((Date.now() - start) / 1000);
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  };
  const timer = setInterval(() => pending.textContent = `Thinking... ${elapsed()}`, 1000);
  try {
    const r = await fetch("/chat", {method: "POST", headers: {"Content-Type": "application/json"},
                                    body: JSON.stringify({messages})});
    const body = await r.text();
    let answer;
    try { answer = JSON.parse(body).answer; } catch { answer = `Error ${r.status}: ${body.slice(0, 500)}`; }
    pending.textContent = `${answer}\n\nTime: ${elapsed()}`;
    if (r.ok) messages.push({role: "assistant", content: answer});
    else messages.pop();
  } catch (err) {
    pending.textContent = `Error: ${err}\n\nTime: ${elapsed()}`;
    messages.pop();
  } finally {
    clearInterval(timer);
  }
};
</script>
</body></html>"""


if __name__ == "__main__":
    app.run(port=5001, debug=True)
