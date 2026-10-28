import json
import unittest

from mariner_genai_dbx.config import Settings
from mariner_genai_dbx.models import Source, SupervisorConfig
from mariner_genai_dbx.supervisor_service import DatabricksSupervisorService, _parse_answer_contract
from mariner_genai_dbx.web import create_app
from mariner_genai_dbx.performance_fast_path import PerformanceFastPathService


class Http:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def post(self, url, **kwargs):
        self.requests.append(kwargs["json"])
        return self

    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload


class LegacyResolver:
    def __init__(self, title):
        self.title = title
        self.labels = None

    def resolve_labels(self, labels, answer=None):
        self.labels = labels
        return (Source(number=1, label=self.title, page=2,
                       url="https://documents.example/approved.pdf"),)

    def resolve_citations(self, citations):
        raise AssertionError("Legacy domain must not require registry citation metadata")


class OtherAgentCompatibilityTests(unittest.TestCase):
    def application(self, answer, title, agent):
        payload = {"output": [{"type": "message", "role": "assistant", "content": [
            {"type": "output_text", "text": f"<name>{agent}</name>"}]},
            {"type": "message", "role": "assistant", "content": [
                {"type": "output_text", "text": answer + "\n\nSource: " + title}]}]}
        http = Http(payload)
        resolver = LegacyResolver(title)
        service = DatabricksSupervisorService(
            SupervisorConfig(workspace_host="https://workspace.example", endpoint_name="supervisor",
                             token="test-token"), http_session=http, citation_resolver=resolver)
        def unexpected_fast_path(*args, **kwargs):
            raise AssertionError('Other domains must bypass performance model calls')
        service = PerformanceFastPathService(service, retriever=None, model_endpoint='unused',
                                             transport=unexpected_fast_path)
        return create_app(Settings(app_env="test"), supervisor_service=service), http, resolver

    def test_other_domains_preserve_routing_markdown_and_source_links_in_both_apis(self):
        domains = [
            ("/policy", "mariner-policy-assistant", "Branch Operations", "Record Retention"),
            ("/handbook", "mariner-handbook-assistant", "Employee Handbook", "2026 Employee Handbook v1"),
            ("/benefits", "benefits-agent-endpoint", "Benefits Agent", "Benefits Guide"),
            ("/benfits", "benefits-agent-endpoint", "Benefits Agent", "Benefits Guide"),
        ]
        answer = "## Guidance\n\n- First requirement\n- Second requirement\n\n| Item | Value |\n| --- | ---: |\n| A | 2 |"
        for command, agent, specialist, title in domains:
            with self.subTest(command=command):
                json_app, json_http, _ = self.application(answer, title, agent)
                stream_app, stream_http, resolver = self.application(answer, title, agent)
                ordinary = json_app.test_client().post("/api/v1/chat", json={"message": command + " Explain this policy"})
                progressive = stream_app.test_client().post("/api/v1/chat/stream", json={"message": command + " Explain this policy"})
                try:
                    frames = [chunk.decode().splitlines() for chunk in progressive.response]
                    events = {lines[0][7:]: json.loads(lines[1][6:]) for lines in frames}
                    self.assertEqual(ordinary.status_code, 200)
                    self.assertIn("done", events)
                    self.assertEqual(events["answer"]["answer"], ordinary.json["answer"])
                    self.assertEqual(events["sources"]["sources"], ordinary.json["sources"])
                    self.assertEqual(events["answer"]["answer"], answer)
                    self.assertEqual(events["sources"]["sources"][0]["page"], 2)
                    self.assertEqual(events["sources"]["sources"][0]["url"], "https://documents.example/approved.pdf")
                    self.assertIn(title, resolver.labels)
                    self.assertIn(specialist, stream_http.requests[0]["input"][0]["content"])
                    self.assertEqual(stream_http.requests[0]["input"], json_http.requests[0]["input"])
                finally:
                    progressive.close()

    def test_other_agent_json_examples_are_not_misclassified_as_citation_envelopes(self):
        for text in ('{"coverage":"PPO"}', '```json\n{"coverage":"HMO"}\n```',
                     '{Example policy wording}', '{"coverage":"PPO",'):
            with self.subTest(text=text):
                self.assertEqual(_parse_answer_contract(text), (text, None))
