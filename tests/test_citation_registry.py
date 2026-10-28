import unittest
import json
from types import SimpleNamespace

from mariner_genai_dbx.citation_registry import CitationRegistry, validate_citations
from mariner_genai_dbx.errors import CitationResolutionError
from mariner_genai_dbx.citation_resolver import DatabricksCitationResolver
from mariner_genai_dbx.config import Settings
from mariner_genai_dbx.models import SupervisorConfig
from mariner_genai_dbx.supervisor_service import DatabricksSupervisorService
from mariner_genai_dbx.web import create_app


def citation(doc="doc", chunk="chunk", page=2):
    return dict(document_id=doc, document_version="v1", chunk_id=chunk,
                document_title="Policy", page=page)


def row(doc="doc", chunk="chunk", path="/Volumes/main/policies/Policy.pdf"):
    return [doc, "v1", chunk, "Policy", "Performance", path, "2", "3"]


class Statements:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []
        self.truncated = False

    def execute_statement(self, **kwargs):
        self.calls.append(kwargs)
        return {"status": {"state": "SUCCEEDED"},
                "manifest": {"truncated": self.truncated},
                "result": {"data_array": self.rows}}


class CitationRegistryTests(unittest.TestCase):
    def registry(self, rows, **kwargs):
        statements = Statements(rows)
        registry = CitationRegistry(
            workspace_client=SimpleNamespace(statement_execution=statements),
            warehouse_id="warehouse", table_name="main.docs.registry",
            volume_roots=["/Volumes/main/policies"], **kwargs)
        return registry, statements

    def test_background_refresh_stops_after_idle_period(self):
        now = [0.0]
        registry, statements = self.registry(
            [row()], ttl_seconds=60, idle_seconds=100,
            clock=lambda: now[0], sleep=lambda seconds: now.__setitem__(0, now[0] + seconds))
        registry._worker = object()  # stands in for the running thread

        registry._refresh_loop()  # returns instead of refreshing forever

        self.assertEqual(len(statements.calls), 4)  # t=0, 30, 60, 90; idle at t=120
        self.assertIsNone(registry._worker)

    def test_chat_activity_keeps_refresh_running(self):
        now = [0.0]

        def sleep(seconds):
            now[0] += seconds
            if now[0] <= 90:
                registry._last_used = now[0]  # a chat arrived during this interval

        registry, statements = self.registry(
            [row()], ttl_seconds=60, idle_seconds=100, clock=lambda: now[0], sleep=sleep)
        registry._worker = object()

        registry._refresh_loop()

        self.assertEqual(len(statements.calls), 7)  # last chat at t=90, idle after t=210
        self.assertIsNone(registry._worker)

    def test_warm_cache_resolves_without_sql_and_preserves_requested_page(self):
        registry, statements = self.registry([row()])
        registry.warm()
        sources = registry.resolve([citation(page=3)])
        self.assertEqual(len(statements.calls), 1)
        self.assertEqual(sources[0].page, 3)
        self.assertEqual(sources[0].location, "/Volumes/main/policies/Policy.pdf")

    def test_all_misses_use_one_parameterized_batch_then_cache(self):
        registry, statements = self.registry([row(), row("doc2", "chunk2")])
        refs = [citation(), citation("doc2", "chunk2", 3)]
        registry.resolve(refs)
        registry.resolve(refs)
        self.assertEqual(len(statements.calls), 1)
        self.assertEqual(len(statements.calls[0]["parameters"]), 6)
        self.assertNotIn("doc2", statements.calls[0]["statement"])

    def test_expired_entries_are_revalidated(self):
        now = [0]
        registry, statements = self.registry([row()], clock=lambda: now[0])
        registry.resolve([citation()])
        now[0] = 61
        statements.rows = []
        with self.assertRaises(CitationResolutionError):
            registry.resolve([citation()])
        self.assertEqual(len(statements.calls), 2)

    def test_rejects_unknown_id_version_title_and_page(self):
        for changes in ({"document_id": "unknown"}, {"document_version": "v2"},
                        {"document_title": "Forged title"}, {"page": 99}):
            with self.subTest(changes=changes):
                registry, _ = self.registry([row()])
                registry.warm()
                ref = citation()
                ref.update(changes)
                with self.assertRaises(CitationResolutionError):
                    registry.resolve([ref])

    def test_rejects_unapproved_and_traversal_paths(self):
        for path in ("/Volumes/other/policies/Policy.pdf",
                     "/Volumes/main/policies/../secret/Policy.pdf",
                     "/Volumes/main/policies2/Policy.pdf"):
            with self.subTest(path=path):
                registry, _ = self.registry([row(path=path)])
                with self.assertRaises(CitationResolutionError):
                    registry.resolve([citation()])

    def test_rejects_ambiguous_metadata(self):
        conflicting = row()
        conflicting[3] = "Conflicting title"
        registry, _ = self.registry([row(), conflicting])
        with self.assertRaises(CitationResolutionError):
            registry.warm()

    def test_rejects_truncated_results(self):
        registry, statements = self.registry([row()])
        statements.truncated = True
        with self.assertRaises(CitationResolutionError):
            registry.warm()

    def test_rejects_oversized_preload(self):
        registry, _ = self.registry([row(), row("doc2", "chunk2")], max_entries=1)
        with self.assertRaises(CitationResolutionError):
            registry.warm()

    def test_validates_shape_before_querying(self):
        registry, statements = self.registry([row()])
        for invalid in (None, {}, [citation()] * 11,
                        [dict(citation(), page=True)],
                        [dict(citation(), url="https://untrusted.example")]):
            with self.subTest(invalid=invalid):
                with self.assertRaises(CitationResolutionError):
                    registry.resolve(invalid)
        self.assertEqual(statements.calls, [])

    def test_empty_citations_need_no_sql(self):
        registry, statements = self.registry([])
        self.assertEqual(registry.resolve([]), ())
        self.assertEqual(statements.calls, [])

    def test_flask_returns_plain_answer_and_sources_without_request_sql(self):
        registry, statements = self.registry([row()])
        registry.warm()
        # Disable background refresh in this deterministic integration test.
        registry.start_background_refresh = lambda: None
        resolver = DatabricksCitationResolver(
            workspace_client=SimpleNamespace(statement_execution=statements),
            warehouse_id="warehouse", tables=(), registry=registry)
        text = json.dumps({"answer": "Managers document feedback.", "citations": [citation()]})

        class Http:
            def post(self, *args, **kwargs):
                return SimpleNamespace(
                    status_code=200, raise_for_status=lambda: None,
                    json=lambda: {"output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": text}]}]})

        service = DatabricksSupervisorService(
            SupervisorConfig(workspace_host="https://workspace.example.test",
                             endpoint_name="supervisor", token="test-token"),
            http_session=Http(), citation_resolver=resolver)
        app = create_app(Settings(app_env="test"), supervisor_service=service)
        response = app.test_client().post("/api/v1/chat", json={"message": "Explain feedback"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["answer"], "Managers document feedback.")
        self.assertEqual(response.json["sources"][0]["label"], "Policy")
        self.assertEqual(response.json["sources"][0]["page"], 2)
        self.assertEqual(len(statements.calls), 1)  # Only the explicit warmup.



if __name__ == "__main__":
    unittest.main()
