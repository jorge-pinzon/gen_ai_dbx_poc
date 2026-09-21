import unittest

from mariner_genai_dbx.citation_resolver import (
    DatabricksCitationResolver,
    extract_source_labels,
)
from mariner_genai_dbx.config import CITATION_TABLES
from mariner_genai_dbx.errors import CitationResolutionError


class FakeStatementExecution:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def execute_statement(self, **kwargs):
        self.calls.append(kwargs)
        return self.response

    def get_statement(self, statement_id):
        raise AssertionError(f"Unexpected polling for {statement_id}")


class FakeWorkspaceClient:
    def __init__(self, response):
        self.statement_execution = FakeStatementExecution(response)


def response(rows, state="SUCCEEDED"):
    return {
        "statement_id": "statement-id",
        "status": {"state": state},
        "result": {"data_array": rows},
    }


class CitationResolverTests(unittest.TestCase):
    def test_extracts_plain_and_markdown_source_labels(self):
        self.assertEqual(
            extract_source_labels(
                "Answer one.\n\nSource: Record Retention\n"
                "Answer two.\n\n**Source:** Employee Handbook"
            ),
            ("Record Retention", "Employee Handbook"),
        )

    def test_resolves_label_with_parameterized_union_query(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Branch Operations",
                        "Record Retention.pdf",
                        "/Volumes/main/branch/Record Retention.pdf",
                        "4",
                        "Paid loan files must be retained for five years.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="55cdb78d4d2a62d0",
            tables=CITATION_TABLES,
        )

        sources = resolver.resolve_labels(("Record Retention",))

        self.assertEqual(sources[0].label, "Record Retention.pdf")
        self.assertEqual(sources[0].domain, "Branch Operations")
        self.assertEqual(sources[0].page, 4)
        call = client.statement_execution.calls[0]
        self.assertEqual(call["warehouse_id"], "55cdb78d4d2a62d0")
        self.assertNotIn("Record Retention", call["statement"])
        self.assertIn(":source_label", call["statement"])
        self.assertIn("CONCAT", call["statement"])
        self.assertIn("',%'", call["statement"])
        self.assertIn("' - %'", call["statement"])
        self.assertIn("' – %'", call["statement"])
        self.assertIn("' — %'", call["statement"])
        self.assertIn("'^[0-9]{4}", call["statement"])
        self.assertIn("workspace`.`default`.`branch_operations_chunks", call["statement"])
        parameter = call["parameters"][0]
        value = parameter.get("value") if isinstance(parameter, dict) else parameter.value
        self.assertEqual(value, "Record Retention")

    def test_omits_page_when_title_matches_chunks_on_multiple_pages(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Employee Handbook",
                        "Handbook.pdf",
                        "/Volumes/main/handbook/Handbook.pdf",
                        "2",
                        "Attendance and workplace conduct.",
                        "1",
                    ],
                    [
                        "Employee Handbook",
                        "Handbook.pdf",
                        "/Volumes/main/handbook/Handbook.pdf",
                        "19",
                        "Benefits and enrollment information.",
                        "1",
                    ]
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        self.assertIsNone(resolver.resolve_labels(("Handbook",))[0].page)

    def test_selects_page_whose_chunk_supports_the_answer(self):
        client = FakeWorkspaceClient(
            response(
                [
                    [
                        "Branch Operations",
                        "Record Retention",
                        "/Volumes/main/branch/Record Retention.pdf",
                        "1",
                        "Policy overview and definitions.",
                        "1",
                    ],
                    [
                        "Branch Operations",
                        "Record Retention",
                        "/Volumes/main/branch/Record Retention.pdf",
                        "3",
                        "Paid loan files must be retained for five years after payoff.",
                        "1",
                    ],
                ]
            )
        )
        resolver = DatabricksCitationResolver(
            workspace_client=client,
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        source = resolver.resolve_labels(
            ("Record Retention",),
            "Paid loan files are retained for five years after payoff.",
        )[0]

        self.assertEqual(source.page, 3)

    def test_failed_statement_is_sanitized(self):
        resolver = DatabricksCitationResolver(
            workspace_client=FakeWorkspaceClient(response([], state="FAILED")),
            warehouse_id="warehouse",
            tables=CITATION_TABLES,
        )

        with self.assertRaises(CitationResolutionError):
            resolver.resolve_labels(("Record Retention",))


if __name__ == "__main__":
    unittest.main()
