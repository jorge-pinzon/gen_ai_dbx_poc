"""DEV Performance Policy agent with structured citations (ASK Mariner).
Retrieval: workspace.performance_test.perf_policy_retrieval_index (text + citation metadata in one call).
The LLM only selects passage labels; citation objects are built in code from retrieved metadata."""
import json, re, time, uuid
import mlflow
from mlflow.pyfunc import ResponsesAgent
from mlflow.types.responses import ResponsesAgentRequest, ResponsesAgentResponse, ResponsesAgentStreamEvent
from databricks.sdk import WorkspaceClient

INDEX = "workspace.performance_test.perf_policy_retrieval_index"
LLM_ENDPOINT = "databricks-claude-haiku-4-5"
REQUIRED = ["chunk_text", "document_id", "document_version", "chunk_id", "document_title", "page_start", "page_end"]
META = REQUIRED + ["retrieval_id", "domain", "source_volume_path"]
MAX_CITATIONS = 10
K = 5
NO_EVIDENCE = ("I could not find this in the approved Employee Performance Policy passages available to me, "
               "so I cannot state a documented policy rule. Please consult HR for binding policy interpretation.")
SYSTEM = """You answer managers' questions about the Employee Performance Policy using ONLY the numbered passages provided.
Return ONLY a JSON object: {"answer": "<manager-facing Markdown>", "used_passages": ["P1", ...], "has_policy_claims": true|false}
Rules:
- used_passages lists ONLY the labels of passages that directly support statements in the answer.
- Do not write document IDs, versions, chunk IDs, titles, page numbers or 'Source:' lines; citations are attached by the system.
- If the passages do not support an answer, say the policy documents do not cover it, set used_passages to [] and has_policy_claims to false.
- Never make binding HR decisions. Mark policy statements with [POLICY]."""


class PerfPolicyCitationsAgent(ResponsesAgent):
    def __init__(self):
        self._w = None

    @property
    def w(self):
        if self._w is None:
            self._w = WorkspaceClient()
        return self._w

    def retrieve(self, query, k=K):
        r = self.w.api_client.do("POST", f"/api/2.0/vector-search/indexes/{INDEX}/query",
                                 body={"columns": META, "query_text": query, "num_results": k})
        names = [c["name"] for c in r["manifest"]["columns"]]
        out = []
        for row in (r.get("result", {}).get("data_array") or []):
            p = dict(zip(names, row))
            if any(p.get(f) in (None, "") for f in REQUIRED):
                continue
            p["page_start"], p["page_end"] = int(p["page_start"]), int(p["page_end"])
            out.append(p)
        return out

    def _llm(self, messages):
        r = self.w.api_client.do("POST", f"/serving-endpoints/{LLM_ENDPOINT}/invocations",
                                 body={"messages": messages, "max_tokens": 1200, "temperature": 0})
        return r["choices"][0]["message"]["content"]

    @staticmethod
    def build_citations(passages, labels):
        by_label = {f"P{i+1}": p for i, p in enumerate(passages)}
        cites, seen = [], set()
        for lab in labels or []:
            p = by_label.get(str(lab).strip())
            if not p or p["chunk_id"] in seen:
                continue
            seen.add(p["chunk_id"])
            cites.append({"document_id": p["document_id"], "document_version": p["document_version"],
                          "chunk_id": p["chunk_id"], "document_title": p["document_title"], "page": p["page_start"]})
            if len(cites) >= MAX_CITATIONS:
                break
        return cites

    def answer(self, question):
        t0 = time.time()
        passages = self.retrieve(question)
        t_ret = time.time() - t0
        ctx = "\n\n".join(f"[P{i+1}]\n{p['chunk_text']}" for i, p in enumerate(passages)) or "(no passages)"
        raw = self._llm([{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": f"Passages:\n{ctx}\n\nQuestion: {question}"}])
        m = re.search(r"\{.*\}", raw, re.S)
        try:
            parsed = json.loads(m.group(0)) if m else {}
        except ValueError:
            parsed = {}
        citations = self.build_citations(passages, parsed.get("used_passages"))
        ans = parsed.get("answer") or NO_EVIDENCE
        if parsed.get("has_policy_claims") and not citations:
            ans = NO_EVIDENCE
        final = {"answer": ans, "citations": citations}
        meta = {"retrieval_ms": round(t_ret * 1000), "total_ms": round((time.time() - t0) * 1000),
                "retrieved": [{k: p[k] for k in META if k != "chunk_text"} for p in passages]}
        return final, meta

    @staticmethod
    def _question(request):
        for item in reversed(request.input):
            d = item.model_dump() if hasattr(item, "model_dump") else dict(item)
            if d.get("role") == "user":
                c = d.get("content")
                return c if isinstance(c, str) else " ".join(
                    x.get("text", "") for x in (c or []) if isinstance(x, dict))
        return ""

    def _final_item(self, request):
        final, meta = self.answer(self._question(request))
        item_id = f"msg_{uuid.uuid4().hex}"
        text = json.dumps(final, ensure_ascii=False)
        return item_id, text, self.create_text_output_item(text=text, id=item_id), meta

    def predict(self, request: ResponsesAgentRequest) -> ResponsesAgentResponse:
        _, _, item, meta = self._final_item(request)
        return ResponsesAgentResponse(output=[item], custom_outputs=meta)

    def predict_stream(self, request: ResponsesAgentRequest):
        """stream: true support. The JSON is built fully before streaming, then sent as ONE delta
        plus the done item, so the final message text is byte-identical to the non-stream response."""
        item_id, text, item, meta = self._final_item(request)
        yield ResponsesAgentStreamEvent(**self.create_text_delta(delta=text, item_id=item_id))
        yield ResponsesAgentStreamEvent(type="response.output_item.done", item=item)


AGENT = PerfPolicyCitationsAgent()
mlflow.models.set_model(AGENT)
